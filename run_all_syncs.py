from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import uuid
from collections import defaultdict
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
TELEMETRY_CLIENT = None
ECS_METADATA: dict[str, object] | None = None


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
        command=static_command(
            "integrations/ebay_sync_buyer_purchases.py",
            "--days-back",
            "7",
            "--missing-tracking-lookback-days",
            "90",
            "--missing-tracking-limit",
            "250",
        ),
        groups=("core", "purchases", "dashboard", "purchase-ingestion"),
        timeout_seconds=60 * 60,
    ),
    SyncJob(
        name="Sourcing purchase matching",
        command=static_command("integrations/match_sourcing_purchases.py", "--limit", "300"),
        groups=("core", "purchases", "dashboard", "purchase-ingestion"),
        timeout_seconds=20 * 60,
    ),
    SyncJob(
        name="EasyPost shipments",
        command=static_command("integrations/easypost_sync_shipments.py", "--limit", "150"),
        groups=("core", "purchases", "dashboard", "purchase-tracking"),
        timeout_seconds=45 * 60,
    ),
    SyncJob(
        name="eBay order problem returns/inquiries",
        command=static_command(
            "integrations/ebay_sync_order_problem_returns.py",
            "--lookback-days",
            "60",
            "--limit",
            "100",
            "--apply",
        ),
        groups=("core", "purchases", "dashboard", "returns-order-problems"),
        blocking=False,
        timeout_seconds=30 * 60,
    ),
    SyncJob(
        name="EasyPost order problem returns",
        command=static_command("integrations/easypost_sync_order_problem_returns.py", "--limit", "100"),
        groups=("core", "purchases", "dashboard", "returns-order-problems"),
        blocking=False,
        timeout_seconds=20 * 60,
    ),
    SyncJob(
        name="RevSeller enrichment",
        command=static_command(
            "integrations/sync_revseller_sheet.py",
            "--ai-review",
            "--ai-review-limit",
            "25",
        ),
        groups=("core", "purchases", "dashboard", "purchase-enrichment"),
        timeout_seconds=45 * 60,
    ),
    SyncJob(
        name="Keepa missing purchase titles",
        command=static_command(
            "integrations/backfill_amazon_titles_from_keepa.py",
            "--limit",
            "25",
            "--fetch-missing",
            "--min-tokens",
            "25",
            "--apply",
        ),
        groups=("core", "purchases", "dashboard", "purchase-enrichment"),
        blocking=False,
        timeout_seconds=20 * 60,
    ),
    SyncJob(
        name="Amazon sales orders",
        command=static_command("integrations/amazon_sync_sales_orders.py", "--apply"),
        groups=("core", "sales-orders", "amazon-sales-recent"),
        blocking=False,
        timeout_seconds=90 * 60,
    ),
    SyncJob(
        name="Recent Amazon sales finances",
        command=lambda: [
            "integrations/amazon_sync_sales_finances.py",
            "--purchase-date-start",
            days_ago_iso(14),
            "--order-finance-delay-seconds",
            "1.5",
            "--apply",
        ],
        groups=("core", "sales-orders", "amazon-sales-recent"),
        blocking=False,
        timeout_seconds=45 * 60,
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
        groups=("core", "sales-orders", "amazon-sales-recent"),
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
        groups=("core", "amazon-sales-recent"),
        blocking=False,
        timeout_seconds=45 * 60,
    ),
    SyncJob(
        name="Amazon FBA inventory",
        command=static_command(
            "integrations/amazon_sync_fba_inventory.py",
            "--page-delay-seconds",
            "0.25",
        ),
        groups=("daily", "dashboard", "repricing", "fba", "fba-inventory-daily"),
        timeout_seconds=45 * 60,
    ),
    SyncJob(
        name="Amazon merchant listings",
        command=static_command("integrations/amazon_sync_merchant_listings.py"),
        groups=("daily", "dashboard", "repricing", "fba", "fba-inventory-daily"),
        timeout_seconds=45 * 60,
    ),
    SyncJob(
        name="Amazon inactive merchant listings",
        command=static_command(
            "integrations/amazon_sync_merchant_listings.py",
            "--report-type",
            "GET_MERCHANT_LISTINGS_INACTIVE_DATA",
        ),
        groups=("daily", "dashboard", "repricing", "fba", "fba-inventory-daily"),
        blocking=False,
        timeout_seconds=45 * 60,
    ),
    SyncJob(
        name="Amazon FBA shipments",
        command=static_command("integrations/amazon_sync_fba_shipments.py"),
        groups=("daily", "dashboard", "fba", "fba-shipments"),
        timeout_seconds=30 * 60,
    ),
    SyncJob(
        name="FBA EasyPost carrier tracking",
        command=static_command(
            "integrations/easypost_sync_fba_shipments.py",
            "--limit",
            "25",
            "--max-new-trackers",
            "10",
        ),
        groups=("daily", "dashboard", "fba", "fba-shipments"),
        timeout_seconds=30 * 60,
    ),
    SyncJob(
        name="Inventory reconciliation",
        command=static_command("integrations/inventory_reconcile.py", "--skip-if-unchanged"),
        groups=("core", "dashboard", "reconciliation", "fba"),
        timeout_seconds=45 * 60,
    ),
    SyncJob(
        name="Amazon listing status",
        command=static_command(
            "integrations/amazon_sync_listing_status.py",
            "--active-only",
            "--stale-days",
            "3",
        ),
        groups=("daily", "dashboard", "repricing", "repricing-catalog"),
        timeout_seconds=60 * 60,
    ),
    SyncJob(
        name="Amazon inventory planning",
        command=static_command("integrations/amazon_sync_inventory_planning.py"),
        groups=("daily", "dashboard", "repricing", "fba-inventory-daily"),
        timeout_seconds=60 * 60,
    ),
    SyncJob(
        name="YNAB Business transactions",
        command=static_command(
            "integrations/ynab_sync_business_transactions.py",
            "--incremental",
            "--apply",
        ),
        groups=("daily", "dashboard", "finance-refresh"),
        timeout_seconds=30 * 60,
    ),
    SyncJob(
        name="YNAB cash balance",
        command=static_command("integrations/ynab_sync_cash_balance.py", "--apply"),
        groups=("daily", "dashboard", "finance-refresh"),
        timeout_seconds=20 * 60,
    ),
    SyncJob(
        name="Amazon finance balances",
        command=static_command("integrations/amazon_sync_finance_balances.py", "--apply"),
        groups=("daily", "dashboard", "finance-refresh"),
        timeout_seconds=30 * 60,
    ),
    SyncJob(
        name="Amazon missing-fee sales finances",
        command=lambda: [
            "integrations/amazon_sync_sales_finances.py",
            "--purchase-date-start",
            days_ago_iso(60),
            "--order-finance-delay-seconds",
            "1.5",
            "--missing-fees-only",
            "--apply",
        ],
        groups=("daily", "sales-orders", "dashboard"),
        blocking=False,
        timeout_seconds=2 * 60 * 60,
    ),
    SyncJob(
        name="Daily missing-fee sales profitability",
        command=lambda: [
            "integrations/amazon_sales_profitability.py",
            "--purchase-date-start",
            days_ago_iso(60),
            "--missing-fees-only",
            "--apply",
        ],
        groups=("daily", "sales-orders", "dashboard"),
        blocking=False,
        timeout_seconds=60 * 60,
    ),
    SyncJob(
        name="Amazon sales finances audit",
        command=lambda: [
            "integrations/amazon_sync_sales_finances.py",
            "--purchase-date-start",
            days_ago_iso(60),
            "--order-finance-delay-seconds",
            "1.5",
            "--apply",
        ],
        groups=("finance-audit",),
        blocking=False,
        timeout_seconds=2 * 60 * 60,
    ),
    SyncJob(
        name="Sales profitability audit",
        command=lambda: [
            "integrations/amazon_sales_profitability.py",
            "--purchase-date-start",
            days_ago_iso(60),
            "--apply",
        ],
        groups=("finance-audit",),
        blocking=False,
        timeout_seconds=60 * 60,
    ),
    SyncJob(
        name="Amazon listing status audit",
        command=static_command("integrations/amazon_sync_listing_status.py", "--active-only"),
        groups=("listing-audit",),
        timeout_seconds=60 * 60,
    ),
    SyncJob(
        name="Inventory reconciliation audit",
        command=static_command("integrations/inventory_reconcile.py"),
        groups=("inventory-audit",),
        timeout_seconds=45 * 60,
    ),
    SyncJob(
        name="Informed repricing reports",
        command=static_command("integrations/informed_sync_reports.py", "--write"),
        groups=("daily", "repricing", "repricing-catalog"),
        timeout_seconds=60 * 60,
    ),
    SyncJob(
        name="Business value snapshot",
        command=static_command("integrations/business_value_snapshot.py", "--apply"),
        groups=("daily", "dashboard", "fba", "finance-refresh", "business-value-finalizer"),
        timeout_seconds=30 * 60,
    ),
    SyncJob(
        name="ZFI business summary push",
        command=static_command(
            "integrations/push_zfi_business_summary.py",
            "--generated-by",
            "aws-scheduler",
            "--apply",
        ),
        groups=(
            "amazon-sales-recent",
            "finance-refresh",
            "business-value-finalizer",
            "fba-inventory-daily",
            "fba-shipments",
        ),
        blocking=False,
        timeout_seconds=20 * 60,
    ),
    SyncJob(
        name="Sourcing opportunity discovery",
        command=static_command(
            "integrations/run_daily_sourcing_discovery.py",
            "--run-type",
            "full_listings",
            "--seed-limit",
            "5000",
        ),
        groups=("daily", "catalog", "sourcing-catalog"),
        blocking=False,
        timeout_seconds=4 * 60 * 60,
    ),
    SyncJob(
        name="Sourcing listing availability",
        command=static_command(
            "integrations/refresh_sourcing_listing_availability.py",
            "--apply",
            "--limit",
            "250",
        ),
        groups=("daily", "catalog", "sourcing-catalog"),
        blocking=False,
        timeout_seconds=30 * 60,
    ),
    SyncJob(
        name="Matching intelligence refresh",
        command=static_command(
            "integrations/refresh_matching_intelligence.py",
            "--runs-per-mode",
            "1",
        ),
        groups=("core", "daily", "catalog", "purchases", "sourcing-catalog"),
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
            "150",
            "--offers",
            "20",
            "--stock",
            "--no-history",
            "--write",
        ),
        groups=("catalog", "repricing", "keepa-rolling-refresh"),
        timeout_seconds=45 * 60,
    ),
    SyncJob(
        name="Keepa sourcing opportunities",
        command=static_command(
            "integrations/keepa_sync_products.py",
            "--source",
            "sourcing_active",
            "--limit",
            "25",
            "--batch-size",
            "25",
            "--stale-days",
            "7",
            "--min-tokens",
            "25",
            "--no-history",
            "--no-rating",
            "--write",
        ),
        groups=("catalog", "sourcing-catalog", "keepa-rolling-refresh"),
        blocking=False,
        timeout_seconds=30 * 60,
    ),
    SyncJob(
        name="Keepa catalog priority refresh",
        command=static_command(
            "integrations/keepa_sync_products.py",
            "--source",
            "catalog_priority",
            "--limit",
            "25",
            "--batch-size",
            "25",
            "--stale-days",
            "7",
            "--min-tokens",
            "25",
            "--no-history",
            "--no-rating",
            "--write",
        ),
        groups=("keepa-catalog-priority",),
        blocking=False,
        timeout_seconds=30 * 60,
    ),
    SyncJob(
        name="Keepa FBA prep pricing",
        command=static_command(
            "integrations/keepa_sync_products.py",
            "--source",
            "received_fba_prep",
            "--limit",
            "10",
            "--batch-size",
            "10",
            "--min-tokens",
            "150",
            "--offers",
            "20",
            "--stock",
            "--no-history",
            "--write",
        ),
        groups=("fba-pricing",),
        timeout_seconds=30 * 60,
    ),
    SyncJob(
        name="Amazon Product Fees estimates",
        command=static_command("integrations/amazon_sync_fee_estimates.py"),
        groups=("fba-pricing",),
        timeout_seconds=45 * 60,
    ),
)

GROUPS = (
    "core",
    "daily",
    "catalog",
    "purchases",
    "sales-orders",
    "finance-audit",
    "listing-audit",
    "inventory-audit",
    "dashboard",
    "reconciliation",
    "repricing",
    "fba",
    "fba-pricing",
    "purchase-ingestion",
    "purchase-tracking",
    "returns-order-problems",
    "purchase-enrichment",
    "amazon-sales-recent",
    "finance-refresh",
    "business-value-finalizer",
    "fba-inventory-daily",
    "fba-shipments",
    "repricing-catalog",
    "sourcing-catalog",
    "keepa-rolling-refresh",
    "keepa-catalog-priority",
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
    run_id = str(uuid.uuid4())
    print(f"Starting sync group={args.group} run_id={run_id}")
    print(started_at)
    start_scheduler_run(run_id=run_id, group=args.group, jobs=selected_jobs, started_at=started_at)

    lock_acquired = False
    if not args.no_lock:
        try:
            acquire_lock(args.group, run_id)
            lock_acquired = True
        except RuntimeError as error:
            message = str(error)
            for job in selected_jobs:
                record_job(
                    job=job,
                    command=job.command(),
                    group=args.group,
                    run_id=run_id,
                    status="blocked",
                    started_at=started_at,
                    message=message,
                )
            print(f"ERROR: {message}")
            finish_scheduler_run(
                run_id=run_id,
                status="blocked",
                started_at=started_at,
                error_summary=message,
            )
            return 1

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
            finish_scheduler_run(
                run_id=run_id,
                status="failed",
                started_at=started_at,
                error_summary="; ".join(failures),
            )
            return 1

        if nonblocking_failures:
            print("\nSync group completed in degraded state.")
            print(now_iso())
            finish_scheduler_run(
                run_id=run_id,
                status="degraded",
                started_at=started_at,
                error_summary="; ".join(nonblocking_failures),
            )
            return 2

        print("\nSync group completed successfully.")
        print(now_iso())
        finish_scheduler_run(run_id=run_id, status="ok", started_at=started_at)
        return 0
    except Exception as error:
        finish_scheduler_run(
            run_id=run_id,
            status="failed",
            started_at=started_at,
            error_summary=str(error),
        )
        raise
    finally:
        if lock_acquired:
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
    record_job(
        job=job,
        command=command,
        group=group,
        run_id=run_id,
        status="running",
        started_at=started_at,
        finished_at=None,
        message="Job is currently running.",
        append_history=False,
    )
    start_scheduler_job(job=job, command=command, group=group, run_id=run_id, started_at=started_at)

    try:
        result = subprocess.run(
            [sys.executable, *command],
            capture_output=True,
            text=True,
            timeout=job.timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        output = combined_process_output(error.stdout, error.stderr)
        if output:
            print(output, end="" if output.endswith("\n") else "\n")
        metrics = parse_job_metrics(output)
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
        finish_scheduler_job(
            job=job,
            command=command,
            group=group,
            run_id=run_id,
            status="failed",
            started_at=started_at,
            error_summary=message,
            metrics=metrics,
            log_bytes=len(output.encode("utf-8")),
        )
        raise RuntimeError(message) from error

    output = combined_process_output(result.stdout, result.stderr)
    if output:
        print(output, end="" if output.endswith("\n") else "\n")
    metrics = parse_job_metrics(output)

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
        finish_scheduler_job(
            job=job,
            command=command,
            group=group,
            run_id=run_id,
            status="failed",
            started_at=started_at,
            error_summary=message,
            metrics=metrics,
            log_bytes=len(output.encode("utf-8")),
        )
        raise RuntimeError(message)

    record_job(job=job, command=command, group=group, run_id=run_id, status="ok", started_at=started_at)
    finish_scheduler_job(
        job=job,
        command=command,
        group=group,
        run_id=run_id,
        status="ok",
        started_at=started_at,
        metrics=metrics,
        log_bytes=len(output.encode("utf-8")),
    )


def record_job(
    *,
    job: SyncJob,
    command: list[str],
    group: str,
    run_id: str,
    status: str,
    started_at: str,
    finished_at: str | None = None,
    message: str | None = None,
    append_history: bool = True,
) -> None:
    command_text = " ".join(command)
    if finished_at is None and status != "running":
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
    write_text_with_retry(
        HEALTH_LOG_PATH,
        json.dumps(records, indent=2, sort_keys=True) + "\n",
    )
    if append_history:
        append_text_with_retry(RUN_HISTORY_PATH, json.dumps(record, sort_keys=True) + "\n")


def read_health_records() -> dict[str, dict[str, object]]:
    try:
        records = json.loads(HEALTH_LOG_PATH.read_text(encoding="utf-8"))
        return records if isinstance(records, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def telemetry_enabled() -> bool:
    explicit = os.getenv("SCHEDULER_TELEMETRY_ENABLED", "").strip().lower()
    if explicit in {"0", "false", "no", "off"}:
        return False
    if explicit in {"1", "true", "yes", "on"}:
        return True
    return os.getenv("CLOUD_DEPLOYMENT", "").strip().lower() in {"1", "true", "yes", "on"}


def telemetry_client():
    global TELEMETRY_CLIENT
    if TELEMETRY_CLIENT is not None:
        return TELEMETRY_CLIENT
    if not telemetry_enabled():
        return None
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        return None
    TELEMETRY_CLIENT = create_client(supabase_url, supabase_key)
    return TELEMETRY_CLIENT


def telemetry_safe(action: Callable[[], None]) -> None:
    try:
        action()
    except Exception as error:  # noqa: BLE001 - telemetry must not break sync jobs.
        print(f"WARNING: scheduler telemetry write failed: {error}")


def start_scheduler_run(*, run_id: str, group: str, jobs: list[SyncJob], started_at: str) -> None:
    client = telemetry_client()
    if client is None:
        return

    def write() -> None:
        metadata = get_ecs_metadata()
        task_arn = str(metadata.get("TaskARN") or os.getenv("ECS_TASK_ARN") or "")
        client.table("scheduler_runs").insert(
            {
                "run_id": run_id,
                "group_name": group,
                "status": "running",
                "started_at": started_at,
                "trigger_source": os.getenv("SCHEDULER_TRIGGER_SOURCE", "ecs" if task_arn else "local"),
                "ecs_task_arn": task_arn or None,
                "eventbridge_schedule_name": os.getenv("EVENTBRIDGE_SCHEDULE_NAME"),
                "container_cpu": parse_int(os.getenv("CONTAINER_CPU")),
                "container_memory": parse_int(os.getenv("CONTAINER_MEMORY")),
                "metadata": {
                    "aws_execution_env": os.getenv("AWS_EXECUTION_ENV"),
                    "selected_job_count": len(jobs),
                },
            }
        ).execute()
        upsert_scheduler_job_definitions(client, jobs, group)

    telemetry_safe(write)


def finish_scheduler_run(
    *,
    run_id: str,
    status: str,
    started_at: str,
    error_summary: str | None = None,
) -> None:
    client = telemetry_client()
    if client is None:
        return
    finished_at = now_iso()

    def write() -> None:
        client.table("scheduler_runs").update(
            {
                "status": status,
                "finished_at": finished_at,
                "runtime_seconds": runtime_seconds(started_at, finished_at),
                "error_summary": truncate_text(error_summary, 2000),
            }
        ).eq("run_id", run_id).execute()

    telemetry_safe(write)


def upsert_scheduler_job_definitions(client, jobs: list[SyncJob], group: str) -> None:
    rows = []
    for job in jobs:
        rows.append(
            {
                "job_key": scheduler_job_key(job),
                "job_name": job.name,
                "default_group_name": group,
                "command": job.command_key,
                "enabled": job.enabled,
                "blocking": job.blocking,
                "timeout_seconds": job.timeout_seconds,
                "domain": infer_job_domain(job, group),
                "updated_at": now_iso(),
            }
        )
    if rows:
        client.table("scheduler_job_definitions").upsert(rows, on_conflict="job_key").execute()


def start_scheduler_job(
    *,
    job: SyncJob,
    command: list[str],
    group: str,
    run_id: str,
    started_at: str,
) -> None:
    client = telemetry_client()
    if client is None:
        return

    def write() -> None:
        client.table("scheduler_run_jobs").insert(
            {
                "run_id": run_id,
                "job_key": scheduler_job_key(job),
                "group_name": group,
                "job_name": job.name,
                "command": " ".join(command),
                "status": "running",
                "blocking": job.blocking,
                "started_at": started_at,
            }
        ).execute()

    telemetry_safe(write)


def finish_scheduler_job(
    *,
    job: SyncJob,
    command: list[str],
    group: str,
    run_id: str,
    status: str,
    started_at: str,
    error_summary: str | None = None,
    metrics: dict[str, object] | None = None,
    log_bytes: int | None = None,
) -> None:
    client = telemetry_client()
    if client is None:
        return
    finished_at = now_iso()

    def write() -> None:
        counters = normalized_counter_columns(metrics or {})
        client.table("scheduler_run_jobs").update(
            {
                "status": status,
                "finished_at": finished_at,
                "runtime_seconds": runtime_seconds(started_at, finished_at),
                "error_summary": truncate_text(error_summary, 2000),
                "rows_read": counters["rows_read"],
                "rows_inserted": counters["rows_inserted"],
                "rows_updated": counters["rows_updated"],
                "rows_deleted": counters["rows_deleted"],
                "rows_skipped": counters["rows_skipped"],
                "external_api_calls": counters["external_api_calls"],
                "retry_count": counters["retry_count"],
                "rate_limit_count": counters["rate_limit_count"],
                "log_bytes": log_bytes,
                "metadata": {"metrics": metrics.get("metrics", []) if metrics else []},
            }
        ).eq("run_id", run_id).eq("job_name", job.name).eq("command", " ".join(command)).execute()

    telemetry_safe(write)


def combined_process_output(stdout: str | bytes | None, stderr: str | bytes | None) -> str:
    parts = []
    for value in (stdout, stderr):
        if value is None:
            continue
        if isinstance(value, bytes):
            parts.append(value.decode("utf-8", errors="replace"))
        else:
            parts.append(value)
    return "".join(parts)


def parse_job_metrics(output: str) -> dict[str, object]:
    raw_metrics: list[dict[str, object]] = []
    counters: dict[str, int] = defaultdict(int)

    for line in output.splitlines():
        parsed = parse_metric_line(line)
        if not parsed:
            continue
        label, value = parsed
        raw_metrics.append({"label": label, "value": value})
        bucket = metric_bucket(label)
        if bucket:
            counters[bucket] += value

    return {
        "rows_read": counters["rows_read"],
        "rows_inserted": counters["rows_inserted"],
        "rows_updated": counters["rows_updated"],
        "rows_deleted": counters["rows_deleted"],
        "rows_skipped": counters["rows_skipped"],
        "external_api_calls": counters["external_api_calls"],
        "retry_count": counters["retry_count"],
        "rate_limit_count": counters["rate_limit_count"],
        "metrics": raw_metrics[:40],
    }


def parse_metric_line(line: str) -> tuple[str, int] | None:
    match = re.match(r"^\s*[-*]?\s*([A-Za-z][A-Za-z0-9 /_.()+%-]*?):\s*(-?\d[\d,]*)\s*$", line)
    if not match:
        return None
    label = " ".join(match.group(1).strip().split())
    try:
        value = int(match.group(2).replace(",", ""))
    except ValueError:
        return None
    return label, value


def metric_bucket(label: str) -> str | None:
    normalized = re.sub(r"[^a-z0-9]+", " ", label.lower()).strip()
    if not normalized:
        return None
    if any(term in normalized for term in ("rate limit", "throttle")):
        return "rate_limit_count"
    if "retried" in normalized or normalized == "retries" or normalized.endswith(" retries"):
        return "retry_count"
    if any(term in normalized for term in ("error", "failure", "failed")):
        return "rows_skipped"
    if any(term in normalized for term in ("deleted", "removed", "no longer available", "dismissed")):
        return "rows_deleted"
    if any(term in normalized for term in ("inserted", "created", "cached", "imported", "snapshots")):
        return "rows_inserted"
    if any(term in normalized for term in ("updated", "matched", "enriched", "processed", "synced", "active")):
        return "rows_updated"
    if any(term in normalized for term in ("skipped", "missing", "unmatched")):
        return "rows_skipped"
    if any(term in normalized for term in ("api", "calls", "requests", "retrieved", "checked", "selected", "loaded", "scanned", "scored", "rows", "orders", "transactions", "candidates", "examples", "shipments", "items", "asins")):
        return "rows_read"
    return None


def normalized_counter_columns(metrics: dict[str, object]) -> dict[str, int | None]:
    return {
        key: int(value) if isinstance(value, int) and value > 0 else None
        for key, value in {
            "rows_read": metrics.get("rows_read"),
            "rows_inserted": metrics.get("rows_inserted"),
            "rows_updated": metrics.get("rows_updated"),
            "rows_deleted": metrics.get("rows_deleted"),
            "rows_skipped": metrics.get("rows_skipped"),
            "external_api_calls": metrics.get("external_api_calls"),
            "retry_count": metrics.get("retry_count"),
            "rate_limit_count": metrics.get("rate_limit_count"),
        }.items()
    }


def scheduler_job_key(job: SyncJob) -> str:
    name = re.sub(r"[^a-z0-9]+", "_", job.name.lower()).strip("_")
    digest = hashlib.sha1(job.name.encode("utf-8")).hexdigest()[:10]
    return f"{name}_{digest}"


def infer_job_domain(job: SyncJob, group: str) -> str:
    job_name = job.name.lower()
    if "keepa" in job_name:
        return "keepa"
    if "easypost" in job_name:
        return "easypost"
    if "amazon" in job_name or group.startswith("amazon") or group.startswith("fba"):
        return "amazon"
    if "ebay" in job_name:
        return "ebay"
    if "ynab" in job_name:
        return "ynab"
    if "revseller" in job_name:
        return "revseller"
    if "sourcing" in job_name:
        return "sourcing"
    return group


def get_ecs_metadata() -> dict[str, object]:
    global ECS_METADATA
    if ECS_METADATA is not None:
        return ECS_METADATA
    metadata_uri = os.getenv("ECS_CONTAINER_METADATA_URI_V4")
    if not metadata_uri:
        ECS_METADATA = {}
        return ECS_METADATA
    try:
        with urllib.request.urlopen(f"{metadata_uri}/task", timeout=2) as response:
            payload = response.read().decode("utf-8")
        parsed = json.loads(payload)
        ECS_METADATA = parsed if isinstance(parsed, dict) else {}
    except Exception:
        ECS_METADATA = {}
    return ECS_METADATA


def runtime_seconds(started_at: str, finished_at: str) -> float | None:
    start = parse_datetime(started_at)
    finish = parse_datetime(finished_at)
    if not start or not finish:
        return None
    return round((finish - start).total_seconds(), 3)


def parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def truncate_text(value: str | None, limit: int) -> str | None:
    if value is None or len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def write_text_with_retry(path: Path, text: str, *, attempts: int = 5) -> None:
    for attempt in range(1, attempts + 1):
        try:
            path.write_text(text, encoding="utf-8")
            return
        except OSError:
            if attempt == attempts:
                raise
            time.sleep(0.25 * attempt)


def append_text_with_retry(path: Path, text: str, *, attempts: int = 5) -> None:
    for attempt in range(1, attempts + 1):
        try:
            with path.open("a", encoding="utf-8") as file:
                file.write(text)
            return
        except OSError:
            if attempt == attempts:
                raise
            time.sleep(0.25 * attempt)


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
