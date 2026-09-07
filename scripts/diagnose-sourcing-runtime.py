"""Run a bounded sourcing phase on the deployed ECS image with external capture.

Evidence stays in ignored local logs/. No schema, schedule, or task definition
is changed. Only this diagnostic task is stopped when a guardrail trips.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import boto3
import requests
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_ACCOUNT = "297464765814"
EXPECTED_PROJECT = "froeucjkcepuhgwisped"
MIB = 1024 * 1024

# This runs inside the existing production scheduler image. Do not log credentials
# or query parameter values. Dry runs enforce GET-only; matching-write allows
# only the three derived tables owned by the matching rebuild.
WRAPPER = r'''
import datetime, httpx, json, os, resource, runpy, signal, sys, threading, time, traceback
from pathlib import Path
def emit(event, **values):
    print("DIAGNOSTIC " + json.dumps(dict(at=datetime.datetime.now(datetime.timezone.utc).isoformat(), event=event, **values)), flush=True)
def memory():
    values = dict(max_rss_mib=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 2))
    for path in ("/sys/fs/cgroup/memory.current", "/sys/fs/cgroup/memory/memory.usage_in_bytes"):
        try:
            values["cgroup_memory_mib"] = round(int(Path(path).read_text().strip()) / 1048576, 2)
            break
        except (OSError, ValueError): pass
    return values
def watchdog():
    while True:
        stats = memory()
        if stats.get("cgroup_memory_mib", 0) > 1500:
            emit("task_memory_guard", **stats)
            os._exit(77)
        time.sleep(1)
threading.Thread(target=watchdog, daemon=True).start()
signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
signal.signal(signal.SIGALRM, lambda *_: sys.exit(124))
signal.alarm(900)
send = httpx.Client.send
def traced_send(self, request, *args, **kwargs):
    is_db = request.url.host.endswith(".supabase.co") and request.url.path.startswith("/rest/v1/")
    if is_db and request.method not in ("GET", "HEAD"):
        write_tables = {"/rest/v1/sourcing_listing_snapshots", "/rest/v1/matching_intelligence_examples", "/rest/v1/sourcing_seller_intelligence"}
        allowed = os.environ.get("MBOP_DIAGNOSTIC_MATCHING_WRITE") == "1" and request.url.path in write_tables
        if not allowed:
            raise RuntimeError("Diagnostic refused a database write: " + request.method + " " + request.url.path)
    if not is_db:
        return send(self, request, *args, **kwargs)
    frames = [f.name for f in traceback.extract_stack() if "/app/integrations/" in f.filename][-4:]
    projection = os.environ.get("MBOP_DIAGNOSTIC_SNAPSHOT_SELECT")
    if projection and "fetch_listing_snapshots_by_action_ids" in frames and request.url.path == "/rest/v1/sourcing_listing_snapshots":
        request.url = request.url.copy_set_param("select", projection)
    opportunity_projection = os.environ.get("MBOP_DIAGNOSTIC_OPPORTUNITY_SELECT")
    if opportunity_projection and "fetch_opportunities_by_ids" in frames and request.url.path == "/rest/v1/sourcing_opportunities":
        request.url = request.url.copy_set_param("select", opportunity_projection)
    label = dict(path=request.url.path, method=request.method, callers=frames, offset=request.url.params.get("offset"), limit=request.url.params.get("limit"))
    emit("db_request_start", **label, **memory())
    started = time.monotonic()
    try:
        response = send(self, request, *args, **kwargs)
        emit("db_request_end", **label, status=response.status_code, seconds=round(time.monotonic()-started,3), response_bytes=len(response.content), **memory())
        if len(response.content) > 25000000:
            raise RuntimeError("Diagnostic stopped before decoding a response larger than 25 MB")
        return response
    except Exception as exc:
        emit("db_request_error", **label, error_type=type(exc).__name__, seconds=round(time.monotonic()-started,3), **memory())
        raise
httpx.Client.send = traced_send
script, *arguments = sys.argv[1:]
sys.path.insert(0, "/app/integrations")
sys.argv = [script, *arguments]
emit("phase_start", script=script, **memory())
try:
    runpy.run_path(script, run_name="__main__")
finally:
    emit("phase_end", script=script, **memory())
'''

# Propagate request tracing into the orchestration's Python subprocesses.
# Catalog writes are governed by the existing production workflow. The one-off
# instrumentation changes no deployed image, schedule, or database schema.
CATALOG_HOOK = WRAPPER.split('script, *arguments = sys.argv[1:]')[0]
CATALOG_HOOK = CATALOG_HOOK.replace('signal.alarm(900)', 'signal.alarm(21600)')
CATALOG_HOOK = CATALOG_HOOK.replace('if is_db and request.method not in ("GET", "HEAD"):', 'if False:')
CATALOG_HOOK = CATALOG_HOOK.replace('if len(response.content) > 25000000:', 'if False:')
CATALOG_WRAPPER = (
    'import os, pathlib, runpy, sys\n'
    'p=pathlib.Path("/tmp/mbop-catalog-diagnostic"); p.mkdir(exist_ok=True)\n'
    'p.joinpath("sitecustomize.py").write_text(' + repr(CATALOG_HOOK) + ')\n'
    'os.environ["PYTHONPATH"]=str(p)+os.pathsep+os.environ.get("PYTHONPATH", "")\n'
    'sys.path.insert(0,str(p)); import sitecustomize\n'
    'sys.path.insert(0,"/app/integrations"); sys.argv=sys.argv[1:]\n'
    'runpy.run_path(sys.argv[0], run_name="__main__")\n'
)

ACTIVE_SQL = """select pid, query_id::text, application_name, state,
 wait_event_type, wait_event,
 extract(epoch from (clock_timestamp()-query_start)) as seconds,
 md5(query) as query_hash,
 substring(query from '"public"\\."[a-zA-Z0-9_]+"') as relation,
 pg_postmaster_start_time() as postmaster_started_at
 from pg_catalog.pg_stat_activity
 where datname=current_database() and pid<>pg_backend_pid()
 and state='active' order by query_start limit 12"""


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def parse_metrics(body):
    wanted = {
        "node_memory_MemAvailable_bytes", "node_memory_MemTotal_bytes",
        "node_memory_SwapTotal_bytes", "node_memory_SwapFree_bytes",
        "node_memory_Committed_AS_bytes", "node_memory_CommitLimit_bytes",
        "node_vmstat_oom_kill", "node_vmstat_pswpin", "node_vmstat_pswpout",
    }
    values = {}
    for line in body.splitlines():
        if not line or line.startswith("#"):
            continue
        name = line.split("{", 1)[0].split(" ", 1)[0]
        if name in wanted:
            values[name] = float(line.rsplit(" ", 1)[-1])
        if name == "node_filesystem_avail_bytes" and 'mountpoint="/data"' in line:
            values["data_disk_available_bytes"] = float(line.rsplit(" ", 1)[-1])
    required = wanted - {"node_vmstat_pswpin", "node_vmstat_pswpout"}
    if required - values.keys():
        raise RuntimeError("Metrics response missing required memory counters")
    values["available_mib"] = values["node_memory_MemAvailable_bytes"] / MIB
    values["swap_used_mib"] = (values["node_memory_SwapTotal_bytes"] - values["node_memory_SwapFree_bytes"]) / MIB
    values["commit_ratio"] = values["node_memory_Committed_AS_bytes"] / values["node_memory_CommitLimit_bytes"]
    return values


def pressure_reason(metrics, baseline_oom):
    if metrics.get("data_disk_available_bytes", float("inf")) < 1024 * MIB:
        return "Data disk available space below 1 GiB"
    if metrics["node_vmstat_oom_kill"] > baseline_oom:
        return "Host OOM counter increased"
    if metrics["available_mib"] < 200:
        return "Available memory below 200 MiB"
    if metrics["swap_used_mib"] > 800:
        return "Swap usage above 800 MiB"
    if metrics["commit_ratio"] > 1.40:
        return "Memory commitment above 140% of reported limit"
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["plan", "score", "matching", "matching-write", "matching-refresh", "catalog"], required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--task-definition", help="Validate a registered scheduler revision before changing the schedule")
    parser.add_argument("--compact-matching-snapshots", action="store_true",
                        help="Benchmark the local snapshot projection in the deployed image; does not deploy code")
    parser.add_argument("--max-seconds", type=int, default=600)
    args = parser.parse_args()
    workflow_phase = args.phase in {"catalog", "matching-refresh"}
    maximum = 21600 if workflow_phase else 900
    if not 30 <= args.max_seconds <= maximum:
        parser.error(f"max-seconds must be between 30 and {maximum}")
    if args.phase == "score" and not args.run_id:
        parser.error("score requires --run-id")
    if args.compact_matching_snapshots and args.phase != "matching":
        parser.error("compact-matching-snapshots requires phase matching")

    cfg = dotenv_values(ROOT / ".env.local")
    host = urlparse(cfg["SUPABASE_URL"]).hostname
    if host != EXPECTED_PROJECT + ".supabase.co":
        raise RuntimeError("Unexpected database target")
    session = requests.Session()
    session.headers.update({"Authorization": "Bearer " + cfg["SUPABASE_ACCESS_TOKEN"], "User-Agent": "MBOP-readonly-runtime-diagnostics/1.0"})
    base = "https://api.supabase.com/v1/projects/" + EXPECTED_PROJECT
    metric_session = requests.Session()
    metric_session.auth = ("username", cfg["SUPABASE_SERVICE_ROLE_KEY"])
    metric_session.headers["User-Agent"] = "MBOP-readonly-runtime-diagnostics/1.0"
    metric_cache = None
    metric_fetched_at = 0.0
    out = ROOT / "logs" / "diagnostics" / (dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + args.phase)
    out.mkdir(parents=True, exist_ok=False)

    def record(kind, payload):
        with (out / (kind + ".jsonl")).open("a", encoding="utf-8") as f:
            f.write(json.dumps({"at": utc(), **payload}, default=str) + "\n")

    def sql(query):
        r = session.post(base + "/database/query/read-only", json={"query": query}, timeout=10)
        r.raise_for_status()
        return r.json()

    def metrics():
        nonlocal metric_cache, metric_fetched_at
        # Supabase refreshes these counters once per minute. Faster polling
        # provides no additional resolution and can rate-limit the collector.
        if metric_cache is not None and time.monotonic() - metric_fetched_at < 60:
            return metric_cache
        r = metric_session.get("https://" + host + "/customer/v1/privileged/metrics", timeout=10)
        r.raise_for_status()
        result = parse_metrics(r.text)
        record("metrics", result)
        metric_cache, metric_fetched_at = result, time.monotonic()
        return result

    aws = boto3.Session(profile_name="mbop-admin", region_name="us-west-2")
    if aws.client("sts").get_caller_identity()["Account"] != EXPECTED_ACCOUNT:
        raise RuntimeError("Unexpected AWS account")
    ecs = aws.client("ecs")
    cloudlogs = aws.client("logs")
    scheduler = aws.client("scheduler")
    target = json.loads(scheduler.get_schedule(Name="mbop-sourcing-catalog")["Target"]["Input"])
    if args.task_definition:
        if not re.fullmatch(r"arn:aws:ecs:us-west-2:297464765814:task-definition/mbop-scheduler-task:\d+", args.task_definition):
            raise RuntimeError("Unexpected scheduler task definition")
        target["TaskDefinition"] = args.task_definition
    cluster = target["Cluster"]
    tasks = ecs.list_tasks(cluster=cluster, family="mbop-scheduler-task", desiredStatus="RUNNING")["taskArns"]
    if tasks:
        raise RuntimeError("Scheduler task already running; defer reproduction")
    preflight = sql("select pg_postmaster_start_time() as started_at, 1 as probe")
    record("preflight", {"database": preflight, "phase": args.phase, "task_definition": target["TaskDefinition"]})
    first = metrics()
    oom = first["node_vmstat_oom_kill"]
    for sample in range(3):
        current = metrics()
        reason = pressure_reason(current, oom)
        print(json.dumps({"baseline": sample, "available_mib": round(current["available_mib"]), "swap_mib": round(current["swap_used_mib"]), "commit_ratio": round(current["commit_ratio"], 3), "stop_reason": reason}), flush=True)
        if reason:
            raise RuntimeError("Preflight refused launch: " + reason)
        time.sleep(5)
    record("queries", {"rows": sql(ACTIVE_SQL)})
    if workflow_phase:
        command = (["/app/run_all_syncs.py", "--group", "sourcing-catalog"] if args.phase == "catalog"
                   else ["/app/integrations/refresh_matching_intelligence.py"])
        backup = session.get(base + "/database/backups", timeout=15)
        backup.raise_for_status()
        completed = [b for b in backup.json().get("backups", []) if b.get("status") == "COMPLETED"]
        if not completed:
            raise RuntimeError("No completed recovery backup available")
        record("recovery", {"completed_backups": completed})
    elif args.phase == "plan":
        command = ["/app/integrations/run_daily_catalog_sourcing.py", "--plan-only", "--queue-limit", "20000"]
    elif args.phase == "score":
        command = ["/app/integrations/score_sourcing_opportunities.py", "--run-id", args.run_id, "--dry-run"]
    else:
        command = ["/app/integrations/build_matching_intelligence_examples.py", "--source", "all"]
        if args.phase == "matching-write":
            command.append("--write")
    network = target["NetworkConfiguration"]["AwsvpcConfiguration"]
    environment = [{"name": "PYTHONUNBUFFERED", "value": "1"}]
    if args.phase == "matching-write":
        environment.append({"name": "MBOP_DIAGNOSTIC_MATCHING_WRITE", "value": "1"})
    if args.compact_matching_snapshots:
        import sys
        sys.path.insert(0, str(ROOT / "integrations"))
        from build_matching_intelligence_examples import MATCHING_SNAPSHOT_COLUMNS, OPPORTUNITY_EVIDENCE_SELECT
        environment.append({"name": "MBOP_DIAGNOSTIC_SNAPSHOT_SELECT", "value": MATCHING_SNAPSHOT_COLUMNS})
        environment.append({"name": "MBOP_DIAGNOSTIC_OPPORTUNITY_SELECT", "value": OPPORTUNITY_EVIDENCE_SELECT})
        record("variant", {"snapshot_select": MATCHING_SNAPSHOT_COLUMNS})
    task_arn = None
    stopped = False
    token = None
    started = time.monotonic()

    def stop(reason):
        nonlocal stopped
        record("control", {"event": "stop_requested", "reason": reason, "task": task_arn})
        print("STOP: " + reason, flush=True)
        ecs.stop_task(cluster=cluster, task=task_arn, reason="MBOP diagnostic: " + reason)
        stopped = True

    def collect_logs():
        nonlocal token
        params = dict(logGroupName="/ecs/mbop-scheduler", logStreamName="scheduled/mbop-scheduler/" + task_arn.rsplit("/", 1)[-1], startFromHead=True, limit=1000)
        if token:
            params["nextToken"] = token
        try:
            result = cloudlogs.get_log_events(**params)
        except cloudlogs.exceptions.ResourceNotFoundException:
            return
        token = result["nextForwardToken"]
        for event in result["events"]:
            record("task_logs", event)
            if event["message"].startswith("DIAGNOSTIC "):
                try:
                    trace = json.loads(event["message"][11:])
                except ValueError:
                    continue
                if not stopped and (trace.get("event") == "task_memory_guard" or trace.get("status") in (521, 522)):
                    stop("Task memory guard" if trace.get("event") == "task_memory_guard" else "Database unavailable response")
        traces = [e["message"] for e in result["events"] if e["message"].startswith("DIAGNOSTIC ")]
        if traces:
            print(traces[-1], flush=True)

    try:
        # Recheck after baseline so we do not knowingly overlap a new scheduled task.
        if ecs.list_tasks(cluster=cluster, family="mbop-scheduler-task", desiredStatus="RUNNING")["taskArns"]:
            raise RuntimeError("A scheduler task started during baseline; defer reproduction")
        result = ecs.run_task(
            cluster=cluster, taskDefinition=target["TaskDefinition"], launchType="FARGATE",
            count=1, platformVersion="LATEST", startedBy="mbop-sourcing-diagnostic",
            networkConfiguration={"awsvpcConfiguration": {"subnets": network["Subnets"], "securityGroups": network["SecurityGroups"], "assignPublicIp": network["AssignPublicIp"]}},
            overrides={"cpu": target["Overrides"]["Cpu"], "memory": target["Overrides"]["Memory"], "containerOverrides": [{"name": "mbop-scheduler", "command": ["python", "-u", "-c", CATALOG_WRAPPER if workflow_phase else WRAPPER, *command], "environment": environment}]},
        )
        if result.get("failures") or len(result.get("tasks", [])) != 1:
            raise RuntimeError("ECS launch failed: " + str(result.get("failures")))
        task_arn = result["tasks"][0]["taskArn"]
        (out / "task.json").write_text(json.dumps({"task_arn": task_arn, "command": command, "task_definition": target["TaskDefinition"]}, indent=2), encoding="utf-8")
        print("CAPTURE " + str(out), flush=True)
        print("TASK " + task_arn, flush=True)
        sample_number = 0
        while True:
            current = metrics()
            reason = pressure_reason(current, oom)
            if reason and not stopped:
                stop(reason)
            active = sql(ACTIVE_SQL)
            record("queries", {"rows": active})
            latest_probe = sql("select pg_postmaster_start_time() as started_at, 1 as probe") if sample_number % 3 == 0 else preflight
            if latest_probe != preflight and not stopped:
                stop("Database postmaster restarted")
            status = ecs.describe_tasks(cluster=cluster, tasks=[task_arn])["tasks"][0]
            record("task_status", {"status": status["lastStatus"], "containers": [{k: c.get(k) for k in ("name", "lastStatus", "exitCode", "reason")} for c in status.get("containers", [])], "stop_code": status.get("stopCode"), "stopped_reason": status.get("stoppedReason")})
            if sample_number % 3 == 0 or status["lastStatus"] == "STOPPED":
                collect_logs()
                print(json.dumps({"elapsed_s": round(time.monotonic()-started), "status": status["lastStatus"], "available_mib": round(current["available_mib"]), "swap_mib": round(current["swap_used_mib"]), "commit_ratio": round(current["commit_ratio"], 3)}), flush=True)
            if status["lastStatus"] == "STOPPED":
                time.sleep(5)
                collect_logs()
                if args.phase == "catalog":
                    import importlib.util
                    spec = importlib.util.spec_from_file_location("reconcile_stopped_scheduler", ROOT / "scripts" / "reconcile-stopped-scheduler.py")
                    reconciler = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(reconciler)
                    reconciler.reconcile(task_arn, apply=True)
                return 2 if stopped or any(c.get("exitCode") != 0 for c in status.get("containers", [])) else 0
            if time.monotonic() - started > args.max_seconds and not stopped:
                stop("Diagnostic time limit")
            if time.monotonic() - started > args.max_seconds + 120:
                raise RuntimeError("Task did not stop within grace period")
            sample_number += 1
            time.sleep(5)
    except BaseException as exc:
        record("control", {"event": "collector_error", "error_type": type(exc).__name__})
        if task_arn and not stopped:
            stop("Capture interrupted or unavailable")
        if task_arn:
            for _ in range(24):
                state = ecs.describe_tasks(cluster=cluster, tasks=[task_arn])["tasks"][0]
                collect_logs()
                if state["lastStatus"] == "STOPPED":
                    record("control", {"event": "stop_confirmed", "task": task_arn})
                    break
                time.sleep(5)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
