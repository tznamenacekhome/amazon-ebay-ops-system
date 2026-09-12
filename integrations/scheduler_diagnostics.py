"""Opt-in catalog diagnostics. Never log headers, payloads or query values."""
from __future__ import annotations

import atexit
import datetime as dt
import json
import os
from pathlib import Path
try:
    import resource
except ImportError:  # Local Windows development; production is Linux.
    resource = None
import sys
import threading
import time
import traceback

_installed = False
_lock = threading.Lock()


def emit(event, **values):
    record = dict(at=dt.datetime.now(dt.UTC).isoformat(), event=event,
                  run_id=os.getenv("MBOP_RUN_ID"), pid=os.getpid(), ppid=os.getppid(),
                  process=Path(sys.argv[0]).name, **values)
    try:
        with _lock:
            print("CATALOG_DIAGNOSTIC " + json.dumps(record, separators=(",", ":")), flush=True)
    except (OSError, ValueError):
        pass


def memory():
    result = {"peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024} if resource else {}
    for name in ("current", "peak", "max", "events"):
        try:
            text = Path("/sys/fs/cgroup/memory." + name).read_text().strip()
            result["cgroup_memory_" + name] = dict(line.split() for line in text.splitlines()) if name == "events" else text
        except OSError:
            pass
    if "cgroup_memory_current" not in result:
        for name, filename in {"current": "memory.usage_in_bytes", "peak": "memory.max_usage_in_bytes",
                               "max": "memory.limit_in_bytes", "failcnt": "memory.failcnt",
                               "oom_control": "memory.oom_control"}.items():
            try:
                result["cgroup_memory_" + name] = Path("/sys/fs/cgroup/memory", filename).read_text().strip()
            except OSError:
                pass
    try:
        result["rss_bytes"] = int(Path("/proc/self/statm").read_text().split()[1]) * os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError, IndexError):
        pass
    return result


def request_label(request):
    # Only the table/RPC name is retained. Pagination values are numeric only.
    path = request.url.path.split("/")
    endpoint = "/".join(path[:5] if path[:4] == ["", "rest", "v1", "rpc"] else path[:4])
    label = {"method": request.method, "endpoint": endpoint,
             "callers": [frame.name for frame in traceback.extract_stack()
                         if "integrations/" in frame.filename.replace("\\", "/")
                         and Path(frame.filename).name != "scheduler_diagnostics.py"][-4:]}
    for key in ("offset", "limit"):
        value = request.url.params.get(key)
        if value and value.isdigit():
            label[key] = int(value)
    return label


def parse_pressure(body):
    names = {"node_memory_MemAvailable_bytes", "node_memory_MemTotal_bytes",
             "node_memory_SwapTotal_bytes", "node_memory_SwapFree_bytes",
             "node_memory_Committed_AS_bytes", "node_memory_CommitLimit_bytes",
             "node_vmstat_oom_kill", "node_vmstat_pswpin", "node_vmstat_pswpout",
             "pg_postmaster_start_time_seconds", "pg_postmaster_start_time",
             "pg_up", "pg_stat_database_deadlocks", "pg_stat_database_temp_bytes"}
    result = {}
    for line in body.splitlines():
        if not line or line.startswith("#"):
            continue
        name = line.split("{", 1)[0].split(" ", 1)[0]
        if name in names or (name in {"node_filesystem_avail_bytes", "node_filesystem_size_bytes"} and 'mountpoint="/data"' in line):
            try:
                result[name] = result.get(name, 0) + float(line.rsplit(" ", 1)[-1])
            except ValueError:
                pass
    return result


def pressure_loop():
    import requests
    from urllib.parse import urlparse
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if urlparse(url).hostname != "froeucjkcepuhgwisped.supabase.co" or not key:
        emit("database_pressure_unavailable", reason="missing_or_unexpected_configuration")
        return
    session = requests.Session()
    session.auth = ("username", key)
    while True:
        try:
            response = session.get(url + "/customer/v1/privileged/metrics", timeout=8)
            response.raise_for_status()
            values = parse_pressure(response.text)
            emit("database_pressure", values=values)
        except Exception as error:
            emit("database_pressure_error", error_type=type(error).__name__)
        time.sleep(60)


def install(*, monitor_database=False):
    global _installed
    if _installed:
        return
    _installed = True
    import httpx
    original = httpx.Client.send

    def traced_send(client, request, *args, **kwargs):
        if request.url.host != "froeucjkcepuhgwisped.supabase.co" or not request.url.path.startswith("/rest/v1/"):
            return original(client, request, *args, **kwargs)
        request_id = f"{os.getpid()}-{time.monotonic_ns()}"
        label = request_label(request)
        emit("db_request_start", request_id=request_id, **label, **memory())
        started = time.monotonic()
        try:
            response = original(client, request, *args, **kwargs)
            # Do not consume streaming responses or change application behavior.
            size = len(response.content) if response.is_stream_consumed else None
            emit("db_request_end", request_id=request_id, **label, status=response.status_code,
                 seconds=round(time.monotonic() - started, 3), response_bytes=size, **memory())
            return response
        except Exception as error:
            emit("db_request_error", request_id=request_id, **label,
                 seconds=round(time.monotonic() - started, 3), error_type=type(error).__name__, **memory())
            raise

    httpx.Client.send = traced_send
    emit("process_start", diagnostics_version=2, **memory())
    atexit.register(lambda: emit("process_exit", **memory()))

    def heartbeat():
        while True:
            time.sleep(15)
            emit("process_heartbeat", **memory())

    threading.Thread(target=heartbeat, daemon=True).start()
    if monitor_database:
        threading.Thread(target=pressure_loop, daemon=True).start()
        from .sourcing_workload_diagnostics import workload_loop
        threading.Thread(target=workload_loop, daemon=True).start()
