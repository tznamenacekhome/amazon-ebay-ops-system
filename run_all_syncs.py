from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv
from supabase import create_client


LOG_DIR = Path("logs")
HEALTH_LOG_PATH = LOG_DIR / "sync_health.json"
RUN_HISTORY_PATH = LOG_DIR / "sync_runs.jsonl"
LOCK_PATH = LOG_DIR / "run_all_syncs.lock"
LOCK_STALE_HOURS = 10
DEFAULT_TIMEOUT_SECONDS = 45 * 60


CommandFactory = Callable[[], list[str]]


@dataclass(frozen=True)
class SyncJob:
    name: str
    command: CommandFactory
    groups: tuple[str, ...]
    blocking: bool = True
    enabled: bool = True
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    disabled_reason: str | None = None

    @property
    def command_key(self) -> str:
        return " ".join(self.command())


def static_command(*parts: str) -> CommandFactory:
    return lambda: list(parts)


def days_ago_iso(days: int) -> str:
    value = datetime.now(timezone.utc) - timedelta(days=days)
    return value.isoformat().replace("+00:00", "Z")


JOBS: tuple[SyncJob, ...] = (
    SyncJob(
        name="eBay buyer purchases",
        command=static_command("integrations/ebay_sync_buyer_purchases.py"),
        groups=("core", "purchases", "dashboard"),
        timeout_seconds=60 * 60,
    ),
    SyncJob(
        name="EasyPost shipments",
        command=static_command("integrations/easypost_sync_shipments.py", "--limit", "500"),
        groups=("core", "purchases", "dashboard"),
        timeout_seconds=45 * 60,
    ),
    SyncJob(
        name="eBay supplier returns",
        command=static_command("integrations/ebay_sync_supplier_returns.py"),
        groups=(),
        enabled=False,
        disabled_reason="Disabled pending returns feature redesign.",
    ),
    SyncJob(
        name="RevSeller enrichment",
        command=static_command("integrations/sync_revseller_sheet.py"),
        groups=("core", "purchases", "dashboard"),
        timeout_seconds=45 * 60,
    ),
    SyncJob(
        name="Amazon sales orders",
        command=static_command("integrations/amazon_sync_sales_orders.py", "--apply"),
        groups=("core", "sales-orders"),
        blocking=False,
        timeout_seconds=90 * 60,
    ),
    SyncJob(
        name="Veeqo MF label costs",
        command=lambda: [
            "integrations/veeqo_sync_sales_labels.py",
            "--purchase-date-start",
            days_ago_iso(14),
            "--missing-only",
            "--apply",
        ],
        groups=("core", "sales-orders"),
        blocking=False,
        timeout_seconds=30 * 60,
    ),
    SyncJob(
        name="Recent sales profitability",
        command=lambda: [
            "integrations/amazon_sales_profitability.py",
            "--purchase-date-start",
            days_ago_iso(14),
            "--apply",
        ],
        groups=("core",),
        blocking=False,
        timeout_seconds=45 * 60,
    ),
    SyncJob(
        name="Inventory reconciliation",
        command=static_command("integrations/inventory_reconcile.py"),
        groups=("core", "dashboard", "reconciliation"),
        timeout_seconds=45 * 60,
    ),
    SyncJob(
        name="Amazon FBA inventory",
        command=static_command("integrations/amazon_sync_fba_inventory.py"),
        groups=("daily", "dashboard", "reconciliation", "repricing"),
        timeout_seconds=45 * 60,
    ),
    SyncJob(
        name="Amazon listing status",
        command=static_command("integrations/amazon_sync_listing_status.py", "--active-only"),
        groups=("daily", "dashboard", "repricing"),
        timeout_seconds=60 * 60,
    ),
    SyncJob(
        name="Amazon inventory planning",
        command=static_command("integrations/amazon_sync_inventory_planning.py"),
        groups=("daily", "dashboard", "repricing"),
        timeout_seconds=60 * 60,
    ),
    SyncJob(
        name="Amazon finance balances",
        command=static_command("integrations/amazon_sync_finance_balances.py", "--apply"),
        groups=("daily", "dashboard"),
        timeout_seconds=30 * 60,
    ),
    SyncJob(
        name="Amazon sales finances",
        command=lambda: [
            "integrations/amazon_sync_sales_finances.py",
            "--purchase-date-start",
            days_ago_iso(60),
            "--order-finance-delay-seconds",
            "1.5",
            "--apply",
        ],
        groups=("daily", "sales-orders", "dashboard"),
        blocking=False,
        timeout_seconds=2 * 60 * 60,
    ),
    SyncJob(
        name="Daily sales profitability",
        command=lambda: [
            "integrations/amazon_sales_profitability.py",
            "--purchase-date-start",
            days_ago_iso(60),
            "--apply",
        ],
        groups=("daily", "sales-orders", "dashboard"),
        blocking=False,
        timeout_seconds=60 * 60,
    ),
    SyncJob(
        name="Informed repricing reports",
        command=static_command("integrations/informed_sync_reports.py", "--write"),
        groups=("daily", "repricing"),
        timeout_seconds=60 * 60,
    ),
    SyncJob(
        name="YNAB cash balance",
        command=static_command("integrations/ynab_sync_cash_balance.py", "--apply"),
        groups=("daily", "dashboard"),
        timeout_seconds=20 * 60,
    ),
    SyncJob(
        name="Business value snapshot",
        command=static_command("integrations/business_value_snapshot.py", "--apply"),
        groups=("daily", "dashboard"),
        timeout_seconds=30 * 60,
    ),
    SyncJob(
        name="Keepa active products",
        command=static_command(
            "integrations/keepa_sync_products.py",
            "--source",
            "amazon_active",
            "--limit",
            "10",
            "--batch-size",
            "10",
            "--stale-days",
            "7",
            "--min-tokens",
            "100",
            "--offers",
            "20",
            "--stock",
            "--no-history",
            "--write",
        ),
        groups=("catalog", "repricing"),
        timeout_seconds=45 * 60,
    ),
)

GROUPS = (
    "core",
    "daily",
    "catalog",
    "purchases",
    "sales-orders",
    "dashboard",
    "reconciliation",
    "repricing",
    "all",
)


def main() -> int:
    args = parse_args()
    load_dotenv()
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    selected_jobs = jobs_for_group(args.group, include_disabled=args.include_disabled)
    if args.list:
        print_job_list(selected_jobs)
        return 0

    started_at = now_iso()
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    print(f"Starting sync group={args.group} run_id={run_id}")
    print(started_at)

    if not args.no_lock:
        acquire_lock(args.group, run_id)

    failures: list[str] = []
    nonblocking_failures: list[str] = []
    try:
        if not args.skip_supabase_probe:
            probe_supabase()

        for job in selected_jobs:
            if not job.enabled:
                record_job(
                    job=job,
                    command=job.command(),
                    group=args.group,
                    run_id=run_id,
                    status="skipped",
                    started_at=now_iso(),
                    message=job.disabled_reason,
                )
                continue

            try:
                run_job(job, group=args.group, run_id=run_id)
            except RuntimeError as error:
                if job.blocking:
                    failures.append(str(error))
                    print(f"ERROR: {error}")
                else:
                    nonblocking_failures.append(str(error))
                    print(f"NONBLOCKING ERROR: {error}")

        if nonblocking_failures:
            print("\nNonblocking syncs completed with failures:")
            for failure in nonblocking_failures:
                print(f"- {failure}")

        if failures:
            print("\nSyncs completed with blocking failures:")
            for failure in failures:
                print(f"- {failure}")
            print(now_iso())
            return 1

        if nonblocking_failures:
            print("\nSync group completed in degraded state.")
            print(now_iso())
            return 2

        print("\nSync group completed successfully.")
        print(now_iso())
        return 0
    finally:
        if not args.no_lock:
            release_lock(run_id)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run MBOP sync jobs by operational group.")
    parser.add_argument(
        "--group",
        choices=GROUPS,
        default="core",
        help="Sync group to run. Default: core.",
    )
    parser.add_argument("--list", action="store_true", help="List selected jobs without running.")
    parser.add_argument("--include-disabled", action="store_true", help="Include disabled jobs in --list output.")
    parser.add_argument("--no-lock", action="store_true", help="Skip local overlap protection.")
    parser.add_argument("--skip-supabase-probe", action="store_true", help="Skip Supabase preflight read.")
    return parser.parse_args()


def jobs_for_group(group: str, *, include_disabled: bool = False) -> list[SyncJob]:
    if group == "all":
        jobs = list(JOBS)
    else:
        jobs = [job for job in JOBS if group in job.groups]
    if not include_disabled:
        jobs = [job for job in jobs if job.enabled]
    return jobs


def run_job(job: SyncJob, *, group: str, run_id: str) -> None:
    command = job.command()
    started_at = now_iso()
    print(f"\n--- Running [{job.name}] {' '.join(command)} ---")

    try:
        result = subprocess.run(
            [sys.executable, *command],
            capture_output=False,
            text=True,
            timeout=job.timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        message = f"{job.name} timed out after {job.timeout_seconds}s"
        record_job(
            job=job,
            command=command,
            group=group,
            run_id=run_id,
            status="failed",
            started_at=started_at,
            message=message,
        )
        raise RuntimeError(message) from error

    if result.returncode != 0:
        message = f"{job.name} failed with exit code {result.returncode}"
        record_job(
            job=job,
            command=command,
            group=group,
            run_id=run_id,
            status="failed",
            started_at=started_at,
            message=message,
        )
        raise RuntimeError(message)

    record_job(job=job, command=command, group=group, run_id=run_id, status="ok", started_at=started_at)


def record_job(
    *,
    job: SyncJob,
    command: list[str],
    group: str,
    run_id: str,
    status: str,
    started_at: str,
    message: str | None = None,
) -> None:
    command_text = " ".join(command)
    finished_at = now_iso()
    record = {
        "run_id": run_id,
        "group": group,
        "job_name": job.name,
        "command": command_text,
        "status": status,
        "blocking": job.blocking,
        "enabled": job.enabled,
        "started_at": started_at,
        "finished_at": finished_at,
        "timeout_seconds": job.timeout_seconds,
        "message": message,
    }

    records = read_health_records()
    records[job.name] = record
    records[command_text] = record
    HEALTH_LOG_PATH.write_text(
        json.dumps(records, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with RUN_HISTORY_PATH.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, sort_keys=True) + "\n")


def read_health_records() -> dict[str, dict[str, object]]:
    try:
        records = json.loads(HEALTH_LOG_PATH.read_text(encoding="utf-8"))
        return records if isinstance(records, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def probe_supabase() -> None:
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY.")
    client = create_client(supabase_url, supabase_key)
    result = client.table("import_batches").select("import_batch_id").limit(1).execute()
    print(f"Supabase preflight ok. rows={len(result.data or [])}")


def acquire_lock(group: str, run_id: str) -> None:
    if LOCK_PATH.exists():
        try:
            existing = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
        started_at = existing.get("started_at")
        if not is_stale_lock(started_at):
            raise RuntimeError(
                "Another run_all_syncs.py process appears active. "
                f"Lock: {LOCK_PATH} started_at={started_at}"
            )
        print(f"Removing stale sync lock from {started_at or 'unknown time'}.")

    LOCK_PATH.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "group": group,
                "run_id": run_id,
                "started_at": now_iso(),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def release_lock(run_id: str) -> None:
    try:
        existing = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return
    if existing.get("run_id") == run_id:
        LOCK_PATH.unlink(missing_ok=True)


def is_stale_lock(started_at: object) -> bool:
    if not isinstance(started_at, str):
        return True
    timestamp = parse_datetime(started_at)
    if not timestamp:
        return True
    return datetime.now(timezone.utc) - timestamp > timedelta(hours=LOCK_STALE_HOURS)


def parse_datetime(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def print_job_list(jobs: list[SyncJob]) -> None:
    print("Selected sync jobs")
    print("------------------")
    for job in jobs:
        state = "enabled" if job.enabled else "disabled"
        blocking = "blocking" if job.blocking else "nonblocking"
        print(f"- {job.name}: {state}, {blocking}, groups={','.join(job.groups) or '--'}")
        print(f"  {' '.join(job.command())}")
        if job.disabled_reason:
            print(f"  {job.disabled_reason}")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
