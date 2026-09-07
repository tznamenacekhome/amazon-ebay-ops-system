"""Reconcile only running telemetry for an ECS task confirmed STOPPED.

Saves the exact original rows before writes. This does not restart any work.
"""
import argparse
import datetime as dt
import json
from pathlib import Path
from urllib.parse import urlparse

import boto3
from dotenv import dotenv_values
from supabase import create_client

ROOT = Path(__file__).resolve().parents[1]


def reconcile(task_arn, *, apply=False):
    cfg = dotenv_values(ROOT / ".env.local")
    if urlparse(cfg["SUPABASE_URL"]).hostname != "froeucjkcepuhgwisped.supabase.co":
        raise RuntimeError("Unexpected database")
    aws = boto3.Session(profile_name="mbop-admin", region_name="us-west-2")
    if aws.client("sts").get_caller_identity()["Account"] != "297464765814":
        raise RuntimeError("Unexpected AWS account")
    result = aws.client("ecs").describe_tasks(cluster="mbop-cluster1", tasks=[task_arn])
    tasks = result.get("tasks", [])
    if len(tasks) != 1 or tasks[0]["lastStatus"] != "STOPPED":
        raise RuntimeError("Task is not confirmed stopped")
    task = tasks[0]
    db = create_client(cfg["SUPABASE_URL"], cfg["SUPABASE_SERVICE_ROLE_KEY"])
    runs = db.table("scheduler_runs").select("*").eq("ecs_task_arn", task_arn).eq("status", "running").execute().data
    jobs = []
    for row in runs:
        jobs.extend(db.table("scheduler_run_jobs").select("*").eq("run_id", row["run_id"]).eq("status", "running").execute().data)
    out = ROOT / "logs" / "diagnostics" / ("reconcile-" + task_arn.rsplit("/", 1)[-1] + "-" + dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ"))
    out.mkdir(parents=True)
    (out / "before.json").write_text(json.dumps({"task": task, "runs": runs, "jobs": jobs}, default=str, indent=2), encoding="utf-8")
    if apply:
        finished = task["stoppedAt"].isoformat()
        message = "ECS task stopped before telemetry completion: " + str(task.get("stoppedReason"))
        for table, rows in (("scheduler_run_jobs", jobs), ("scheduler_runs", runs)):
            for row in rows:
                update = {"status": "failed", "finished_at": finished, "error_summary": message,
                          "runtime_seconds": max(0, (task["stoppedAt"] - dt.datetime.fromisoformat(row["started_at"].replace("Z", "+00:00"))).total_seconds())}
                query = db.table(table).update(update).eq("run_id", row["run_id"]).eq("status", "running")
                if table == "scheduler_run_jobs":
                    query = query.eq("job_name", row["job_name"]).eq("command", row["command"])
                else:
                    query = query.eq("ecs_task_arn", task_arn)
                query.execute()
    print(json.dumps({"backup": str(out), "runs": len(runs), "jobs": len(jobs), "applied": apply}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-arn", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    reconcile(args.task_arn, apply=args.apply)
