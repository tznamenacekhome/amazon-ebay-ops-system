from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
EXPORT_DIR = ROOT / "exports"
LOG_DIR = ROOT / "logs" / "scheduled_job_instrumentation"
CSV_PATH = EXPORT_DIR / "scheduled_job_instrumentation_run.csv"
SUMMARY_PATH = EXPORT_DIR / "scheduled_job_instrumentation_summary.md"

STATUS_OK = "success"
STATUS_FAILED = "failure"
STATUS_BLOCKED = "blocked"
STATUS_SKIPPED = "skipped"


@dataclass
class JobRun:
    job_name: str
    command: str
    group_currently_assigned: str
    start_timestamp: str
    end_timestamp: str
    runtime_seconds: float
    status: str
    error_summary: str
    external_service_used: str
    estimated_external_api_calls: str
    rows_inserted: str
    rows_updated: str
    rows_skipped_noop: str
    rows_read_scanned: str
    sync_shape: str
    writes_raw_snapshots_or_high_volume_events: str
    log_size_bytes: int
    retry_rate_limit_behavior: str
    lock_collision_behavior: str
    proposed_aws_job_group: str
    proposed_initial_frequency: str
    proposed_trigger_mode: str
    safe_to_run_in_cloud_mode: str
    required_secrets_environment_variables: str
    concerns: str
    log_path: str


JOB_METADATA: dict[str, dict[str, str]] = {
    "eBay buyer purchases": {
        "service": "eBay + Supabase",
        "shape": "incremental bounded lookback",
        "raw": "yes: stores raw eBay order JSON on purchase rows",
        "aws_group": "purchase-ingestion-core",
        "frequency": "hourly during operating hours; every 2-4 hours otherwise",
        "trigger": "EventBridge scheduled",
        "safe": "yes",
        "secrets": "SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; EBAY_CLIENT_ID; EBAY_CLIENT_SECRET; EBAY_REFRESH_TOKEN",
        "concerns": "Trading/Browse API quota; 90-day missing-tracking refresh can add reads/API calls.",
        "calls": "Trading pages + no-tracking chunks + optional Browse detail calls; estimate from retrieved pages/log.",
    },
    "Sourcing purchase matching": {
        "service": "Supabase-only",
        "shape": "incremental limited batch",
        "raw": "no",
        "aws_group": "purchase-ingestion-core",
        "frequency": "hourly after purchase ingestion",
        "trigger": "EventBridge scheduled",
        "safe": "yes",
        "secrets": "SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY",
        "concerns": "Supabase read/write load only; bounded by --limit.",
        "calls": "0 external API calls.",
    },
    "EasyPost shipments": {
        "service": "EasyPost + Supabase",
        "shape": "incremental limited batch",
        "raw": "yes: writes tracking detail/events; potentially high-volume tracking events",
        "aws_group": "purchase-tracking",
        "frequency": "hourly for inbound shipments",
        "trigger": "EventBridge scheduled now; webhook-driven long term",
        "safe": "yes",
        "secrets": "SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; EASYPOST_API_KEY",
        "concerns": "Keep <=5 EasyPost requests/sec; retry/backoff on 429.",
        "calls": "approximately processed rows plus tracker creations/retrievals.",
    },
    "eBay order problem returns/inquiries": {
        "service": "eBay + Supabase",
        "shape": "bounded lookback",
        "raw": "yes: writes problem payloads and event rows",
        "aws_group": "returns-and-order-problems",
        "frequency": "every 2-4 hours",
        "trigger": "EventBridge scheduled",
        "safe": "yes",
        "secrets": "SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; EBAY_CLIENT_ID; EBAY_CLIENT_SECRET; EBAY_REFRESH_TOKEN",
        "concerns": "Nonblocking job; event rows can grow with changes.",
        "calls": "Post-Order returns/inquiries/cases plus Trading refunds.",
    },
    "EasyPost order problem returns": {
        "service": "EasyPost + Supabase",
        "shape": "incremental limited batch",
        "raw": "yes: writes return tracking detail/events",
        "aws_group": "returns-and-order-problems",
        "frequency": "every 2-4 hours",
        "trigger": "EventBridge scheduled now; webhook-driven long term",
        "safe": "yes",
        "secrets": "SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; EASYPOST_API_KEY",
        "concerns": "EasyPost quota/rate limit.",
        "calls": "approximately processed return tracking rows.",
    },
    "RevSeller enrichment": {
        "service": "Google Sheets/RevSeller + OpenAI optional + Supabase",
        "shape": "incremental scan/enrichment",
        "raw": "no",
        "aws_group": "purchase-enrichment",
        "frequency": "hourly or every 2 hours",
        "trigger": "EventBridge scheduled",
        "safe": "yes, if Google/OpenAI credentials are available",
        "secrets": "SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; Google Sheets credentials; optional OPENAI_API_KEY",
        "concerns": "AI review limit controls OpenAI usage; sheet access from cloud needs credentials/files.",
        "calls": "Google Sheet read plus up to --ai-review-limit OpenAI calls.",
    },
    "Keepa missing purchase titles": {
        "service": "Keepa + Supabase",
        "shape": "incremental limited batch",
        "raw": "yes: Keepa product snapshots",
        "aws_group": "catalog-intelligence-light",
        "frequency": "every 4-6 hours",
        "trigger": "EventBridge scheduled",
        "safe": "yes with token guard",
        "secrets": "SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; KEEPA_API_KEY",
        "concerns": "Keepa token budget; job skips below min tokens.",
        "calls": "bounded by --limit/--batch-size and token availability.",
    },
    "Amazon sales orders": {
        "service": "Amazon SP-API + Supabase",
        "shape": "incremental bounded lookback",
        "raw": "yes: Amazon sales order/item rows",
        "aws_group": "amazon-sales",
        "frequency": "hourly",
        "trigger": "EventBridge scheduled",
        "safe": "yes",
        "secrets": "SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; Amazon SP-API credentials",
        "concerns": "SP-API throttling; getOrderItems can multiply calls.",
        "calls": "order pages plus item calls for changed/unseen orders.",
    },
    "Recent Amazon sales finances": {
        "service": "Amazon SP-API + Supabase",
        "shape": "bounded lookback",
        "raw": "yes: financial event rows; high-volume possible",
        "aws_group": "amazon-sales",
        "frequency": "hourly or every 2 hours with finance delay",
        "trigger": "EventBridge scheduled",
        "safe": "yes",
        "secrets": "SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; Amazon SP-API credentials",
        "concerns": "SP-API finance quotas; raw financial events can grow.",
        "calls": "approximately orders checked plus transaction fallback pages.",
    },
    "Veeqo MF label costs": {
        "service": "Veeqo + Supabase",
        "shape": "bounded lookback missing-only",
        "raw": "no",
        "aws_group": "amazon-sales",
        "frequency": "hourly or every 2 hours",
        "trigger": "EventBridge scheduled",
        "safe": "yes if Veeqo key is configured; otherwise skipped",
        "secrets": "SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; VEEQO_KEY",
        "concerns": "Veeqo API retry/backoff on 429/5xx.",
        "calls": "one or more Veeqo order lookups for candidate Amazon orders.",
    },
    "Recent sales profitability": {
        "service": "Supabase-only",
        "shape": "bounded lookback",
        "raw": "no",
        "aws_group": "amazon-sales",
        "frequency": "hourly after sales/finance sync",
        "trigger": "EventBridge scheduled",
        "safe": "yes",
        "secrets": "SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY",
        "concerns": "Supabase CPU/read load; backend-owned cost calculations.",
        "calls": "0 external API calls.",
    },
    "Amazon FBA inventory": {
        "service": "Amazon SP-API + Supabase",
        "shape": "broad snapshot",
        "raw": "yes: inserts inventory snapshot rows each run",
        "aws_group": "fba-inventory-daily",
        "frequency": "daily, plus manual on demand",
        "trigger": "EventBridge scheduled",
        "safe": "yes",
        "secrets": "SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; Amazon SP-API credentials",
        "concerns": "Snapshot row growth and SP-API pagination.",
        "calls": "inventory summary pages.",
    },
    "Amazon FBA shipments": {
        "service": "Amazon SP-API + Supabase",
        "shape": "incremental limited shipment sync with discovery",
        "raw": "yes: shipment workflow events",
        "aws_group": "fba-shipments",
        "frequency": "every 2-4 hours when shipping; daily otherwise",
        "trigger": "EventBridge scheduled",
        "safe": "yes",
        "secrets": "SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; Amazon SP-API credentials",
        "concerns": "SP-API shipment calls per selected shipment; event row growth.",
        "calls": "selected shipments times status/items/availability calls.",
    },
    "FBA EasyPost carrier tracking": {
        "service": "EasyPost + Supabase",
        "shape": "incremental limited batch",
        "raw": "yes: FBA carrier tracking details",
        "aws_group": "fba-shipments",
        "frequency": "every 2-4 hours while shipments are in transit",
        "trigger": "EventBridge scheduled now; webhook-driven long term",
        "safe": "yes",
        "secrets": "SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; EASYPOST_API_KEY",
        "concerns": "EasyPost request cap and max-new-trackers guard.",
        "calls": "approximately processed rows plus new tracker creations.",
    },
    "Inventory reconciliation": {
        "service": "Supabase-only",
        "shape": "incremental skip-if-unchanged",
        "raw": "no",
        "aws_group": "reconciliation",
        "frequency": "after inventory/FBA updates; hourly or daily depending source freshness",
        "trigger": "EventBridge scheduled",
        "safe": "yes",
        "secrets": "SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY",
        "concerns": "Can scan multiple operational tables; skip-if-unchanged reduces load.",
        "calls": "0 external API calls.",
    },
    "Amazon listing status": {
        "service": "Amazon SP-API + Supabase",
        "shape": "incremental stale active-listing batch",
        "raw": "yes: listing status snapshots",
        "aws_group": "repricing-catalog",
        "frequency": "daily with stale-days guard",
        "trigger": "EventBridge scheduled",
        "safe": "yes",
        "secrets": "SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; Amazon SP-API credentials",
        "concerns": "Listings Items calls are rate limited; default delay stays near 4 requests/sec.",
        "calls": "one Listings Items call per selected SKU.",
    },
    "Amazon inventory planning": {
        "service": "Amazon SP-API Reports + Supabase",
        "shape": "broad report snapshot",
        "raw": "yes: planning snapshot rows",
        "aws_group": "fba-inventory-daily",
        "frequency": "daily",
        "trigger": "EventBridge scheduled",
        "safe": "yes",
        "secrets": "SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; Amazon SP-API credentials",
        "concerns": "Report polling time and snapshot row growth.",
        "calls": "create/get report plus polling/document download.",
    },
    "YNAB Business transactions": {
        "service": "YNAB + Supabase",
        "shape": "incremental",
        "raw": "no",
        "aws_group": "finance-daily",
        "frequency": "daily",
        "trigger": "EventBridge scheduled",
        "safe": "yes",
        "secrets": "SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; YNAB_ACCESS_TOKEN; YNAB_BUDGET_ID",
        "concerns": "YNAB API availability; low volume.",
        "calls": "YNAB budget/transactions call(s).",
    },
    "YNAB cash balance": {
        "service": "YNAB + Supabase",
        "shape": "point-in-time snapshot",
        "raw": "yes: cash balance snapshot row",
        "aws_group": "finance-daily",
        "frequency": "daily",
        "trigger": "EventBridge scheduled",
        "safe": "yes",
        "secrets": "SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; YNAB_ACCESS_TOKEN; YNAB_BUDGET_ID",
        "concerns": "Low volume snapshot growth.",
        "calls": "YNAB budget/category call(s).",
    },
    "Amazon finance balances": {
        "service": "Amazon SP-API + Supabase",
        "shape": "point-in-time finance snapshot",
        "raw": "yes: finance balance snapshot row",
        "aws_group": "finance-daily",
        "frequency": "daily",
        "trigger": "EventBridge scheduled",
        "safe": "yes",
        "secrets": "SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; Amazon SP-API credentials",
        "concerns": "SP-API finance calls; low row volume.",
        "calls": "financial event group/transaction pages.",
    },
    "Amazon missing-fee sales finances": {
        "service": "Amazon SP-API + Supabase",
        "shape": "bounded lookback missing-only",
        "raw": "yes: financial event rows; high-volume possible",
        "aws_group": "amazon-sales-fee-repair",
        "frequency": "daily",
        "trigger": "EventBridge scheduled",
        "safe": "yes, but keep separate from hourly sales",
        "secrets": "SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; Amazon SP-API credentials",
        "concerns": "Longer 60-day lookback; SP-API quotas and Supabase write volume.",
        "calls": "orders missing fees plus transaction fallback pages.",
    },
    "Daily missing-fee sales profitability": {
        "service": "Supabase-only",
        "shape": "bounded lookback missing-only",
        "raw": "no",
        "aws_group": "amazon-sales-fee-repair",
        "frequency": "daily after missing-fee finance",
        "trigger": "EventBridge scheduled",
        "safe": "yes",
        "secrets": "SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY",
        "concerns": "Supabase scan/write load over 60-day window.",
        "calls": "0 external API calls.",
    },
    "Amazon sales finances audit": {
        "service": "Amazon SP-API + Supabase",
        "shape": "broad audit bounded lookback",
        "raw": "yes: financial event rows; high-volume possible",
        "aws_group": "finance-audit",
        "frequency": "weekly or manual",
        "trigger": "manual-only initially",
        "safe": "yes, but isolate from normal hourly jobs",
        "secrets": "SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; Amazon SP-API credentials",
        "concerns": "Potentially long runtime and SP-API quota pressure.",
        "calls": "all eligible orders in 60-day window plus transaction fallback pages.",
    },
    "Sales profitability audit": {
        "service": "Supabase-only",
        "shape": "broad audit bounded lookback",
        "raw": "no",
        "aws_group": "finance-audit",
        "frequency": "weekly or manual after finance audit",
        "trigger": "manual-only initially",
        "safe": "yes",
        "secrets": "SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY",
        "concerns": "Supabase read/write load over 60-day window.",
        "calls": "0 external API calls.",
    },
    "Amazon listing status audit": {
        "service": "Amazon SP-API + Supabase",
        "shape": "broad audit active listings",
        "raw": "yes: listing status snapshots",
        "aws_group": "listing-audit",
        "frequency": "weekly or manual",
        "trigger": "manual-only initially",
        "safe": "yes, but quota-sensitive",
        "secrets": "SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; Amazon SP-API credentials",
        "concerns": "One SP-API Listings call per active SKU; can be long.",
        "calls": "one Listings Items call per active SKU.",
    },
    "Inventory reconciliation audit": {
        "service": "Supabase-only",
        "shape": "broad audit",
        "raw": "no",
        "aws_group": "inventory-audit",
        "frequency": "weekly or manual",
        "trigger": "manual-only initially",
        "safe": "yes",
        "secrets": "SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY",
        "concerns": "Broad Supabase scan across inventory tables.",
        "calls": "0 external API calls.",
    },
    "Informed repricing reports": {
        "service": "Informed + Supabase",
        "shape": "report snapshot",
        "raw": "yes: repricing report snapshot rows",
        "aws_group": "repricing-catalog",
        "frequency": "daily",
        "trigger": "EventBridge scheduled",
        "safe": "yes",
        "secrets": "SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; INFORMED_API_KEY or Informed credentials",
        "concerns": "Report request/polling delay and snapshot growth.",
        "calls": "report request/status/download calls.",
    },
    "Business value snapshot": {
        "service": "Supabase-only",
        "shape": "point-in-time snapshot",
        "raw": "yes: business value snapshot row",
        "aws_group": "finance-daily",
        "frequency": "daily after finance/inventory jobs",
        "trigger": "EventBridge scheduled",
        "safe": "yes",
        "secrets": "SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY",
        "concerns": "Reads inventory/value tables; low write volume.",
        "calls": "0 external API calls.",
    },
    "Sourcing listing availability": {
        "service": "eBay Browse + Supabase",
        "shape": "incremental limited batch",
        "raw": "yes: may update raw eBay JSON for candidates",
        "aws_group": "catalog-intelligence-light",
        "frequency": "daily or every 6 hours",
        "trigger": "EventBridge scheduled",
        "safe": "yes",
        "secrets": "SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; EBAY_CLIENT_ID; EBAY_CLIENT_SECRET; EBAY_REFRESH_TOKEN",
        "concerns": "eBay Browse calls bounded by --limit.",
        "calls": "one Browse item call per unique eBay item checked.",
    },
    "Matching intelligence refresh": {
        "service": "Supabase-only",
        "shape": "bounded rebuild/rescore",
        "raw": "yes: matching examples/listing snapshots may be inserted",
        "aws_group": "catalog-intelligence-light",
        "frequency": "daily",
        "trigger": "EventBridge scheduled",
        "safe": "yes",
        "secrets": "SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY",
        "concerns": "Can scan multiple sourcing/history tables; keep isolated from hot purchase ingestion.",
        "calls": "0 external API calls.",
    },
    "Keepa active products": {
        "service": "Keepa + Supabase",
        "shape": "incremental stale limited batch",
        "raw": "yes: Keepa snapshots and optional history rows",
        "aws_group": "repricing-catalog",
        "frequency": "daily or several times daily, token permitting",
        "trigger": "EventBridge scheduled",
        "safe": "yes with token guard",
        "secrets": "SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; KEEPA_API_KEY",
        "concerns": "Keepa token budget; stock/offers cost extra tokens.",
        "calls": "bounded by --limit/--batch-size and tokens.",
    },
    "Keepa FBA prep pricing": {
        "service": "Keepa + Supabase",
        "shape": "incremental FBA prep catalog batch",
        "raw": "yes: Keepa snapshots and optional history rows",
        "aws_group": "fba-pricing",
        "frequency": "hourly while prepping shipments; otherwise daily",
        "trigger": "EventBridge scheduled",
        "safe": "yes with token guard",
        "secrets": "SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; KEEPA_API_KEY",
        "concerns": "Keepa token budget; unbounded source may select all eligible received FBA prep rows.",
        "calls": "bounded by source selection/batch-size and tokens.",
    },
    "Amazon Product Fees estimates": {
        "service": "Amazon SP-API + Supabase",
        "shape": "incremental price-point fee cache",
        "raw": "yes: fee estimate cache rows",
        "aws_group": "fba-pricing",
        "frequency": "hourly while pricing/prepping; otherwise daily",
        "trigger": "EventBridge scheduled",
        "safe": "yes",
        "secrets": "SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; Amazon SP-API credentials",
        "concerns": "Product Fees v0 is rate-limited; keep separate from other SP-API heavy jobs.",
        "calls": "one fee estimate call per selected price point.",
    },
}


def main() -> int:
    sys.path.insert(0, str(ROOT))
    args = parse_args()
    load_dotenv(ROOT / ".env")
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    import run_all_syncs

    group = args.group
    jobs = run_all_syncs.jobs_for_group(group, include_disabled=args.include_disabled)
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")

    lock_acquired = False
    results: list[JobRun] = []
    try:
        if args.from_run_id:
            results = summarize_existing_run(jobs, group=group, run_id=args.from_run_id)
            write_outputs(results, group=group, run_id=args.from_run_id, exit_code=0)
            print(f"Wrote {CSV_PATH.relative_to(ROOT)}")
            print(f"Wrote {SUMMARY_PATH.relative_to(ROOT)}")
            return 0

        if not args.no_lock:
            try:
                run_all_syncs.acquire_lock(group, f"instrument-{run_id}")
                lock_acquired = True
            except RuntimeError as error:
                now = now_iso()
                for job in jobs:
                    results.append(build_blocked_run(job, group, now, str(error)))
                write_outputs(results, group=group, run_id=run_id, exit_code=1)
                return 1

        if not args.skip_supabase_probe:
            run_all_syncs.probe_supabase()

        exit_code = 0
        for index, job in enumerate(jobs, start=1):
            print(f"\n[{index}/{len(jobs)}] {job.name}")
            result = run_one_job(job, group=group, run_id=run_id)
            results.append(result)
            write_outputs(results, group=group, run_id=run_id, exit_code=exit_code)
            if result.status == STATUS_FAILED:
                exit_code = 1 if job.blocking else max(exit_code, 2)

        write_outputs(results, group=group, run_id=run_id, exit_code=exit_code)
        print(f"\nWrote {CSV_PATH.relative_to(ROOT)}")
        print(f"Wrote {SUMMARY_PATH.relative_to(ROOT)}")
        return exit_code
    finally:
        if lock_acquired:
            run_all_syncs.release_lock(f"instrument-{run_id}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run scheduled jobs once and export AWS planning instrumentation.")
    parser.add_argument("--group", default="all", choices=tuple(__import__("run_all_syncs").GROUPS))
    parser.add_argument("--include-disabled", action="store_true")
    parser.add_argument("--no-lock", action="store_true")
    parser.add_argument("--skip-supabase-probe", action="store_true")
    parser.add_argument(
        "--from-run-id",
        help="Regenerate exports from captured instrumentation logs for a previous run without executing jobs.",
    )
    return parser.parse_args()


def summarize_existing_run(jobs: list[Any], *, group: str, run_id: str) -> list[JobRun]:
    previous = read_previous_csv()
    results: list[JobRun] = []
    for job in jobs:
        command_text = " ".join(job.command())
        existing = previous.get(job.name, {})
        log_path = LOG_DIR / f"{run_id}_{safe_filename(job.name)}.log"
        log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
        started_at = existing.get("start_timestamp") or ""
        ended_at = existing.get("end_timestamp") or ""
        runtime = to_float(existing.get("runtime_seconds"))
        status = existing.get("status") or (STATUS_OK if log_path.exists() else STATUS_SKIPPED)
        error = existing.get("error_summary") or ""
        results.append(
            build_run(
                job,
                group,
                command_text,
                started_at,
                ended_at,
                runtime,
                status,
                error,
                log_path,
                log_text,
            )
        )
    return results


def read_previous_csv() -> dict[str, dict[str, str]]:
    if not CSV_PATH.exists():
        return {}
    with CSV_PATH.open("r", newline="", encoding="utf-8") as file:
        return {row["job_name"]: row for row in csv.DictReader(file)}


def run_one_job(job: Any, *, group: str, run_id: str) -> JobRun:
    command_parts = job.command()
    command_text = " ".join(command_parts)
    started_at = now_iso()
    start_monotonic = time.monotonic()
    log_path = LOG_DIR / f"{run_id}_{safe_filename(job.name)}.log"

    if not job.enabled:
        ended_at = now_iso()
        log_path.write_text(job.disabled_reason or "Job disabled.\n", encoding="utf-8")
        return build_run(
            job,
            group,
            command_text,
            started_at,
            ended_at,
            time.monotonic() - start_monotonic,
            STATUS_SKIPPED,
            job.disabled_reason or "",
            log_path,
            "",
        )

    with log_path.open("w", encoding="utf-8", errors="replace") as log_file:
        log_file.write(f"$ {sys.executable} {command_text}\n")
        log_file.flush()
        try:
            completed = subprocess.run(
                [sys.executable, *command_parts],
                cwd=ROOT,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=job.timeout_seconds,
            )
            returncode = completed.returncode
        except subprocess.TimeoutExpired:
            ended_at = now_iso()
            return build_run(
                job,
                group,
                command_text,
                started_at,
                ended_at,
                time.monotonic() - start_monotonic,
                STATUS_FAILED,
                f"Timed out after {job.timeout_seconds}s",
                log_path,
                log_path.read_text(encoding="utf-8", errors="replace"),
            )

    ended_at = now_iso()
    log_text = log_path.read_text(encoding="utf-8", errors="replace")
    status = STATUS_OK if returncode == 0 else STATUS_FAILED
    error = "" if returncode == 0 else error_summary(log_text, returncode)
    return build_run(
        job,
        group,
        command_text,
        started_at,
        ended_at,
        time.monotonic() - start_monotonic,
        status,
        error,
        log_path,
        log_text,
    )


def build_blocked_run(job: Any, group: str, timestamp: str, message: str) -> JobRun:
    command_text = " ".join(job.command())
    return build_run(
        job,
        group,
        command_text,
        timestamp,
        timestamp,
        0.0,
        STATUS_BLOCKED,
        message,
        Path(""),
        "",
    )


def build_run(
    job: Any,
    group: str,
    command_text: str,
    started_at: str,
    ended_at: str,
    runtime: float,
    status: str,
    error: str,
    log_path: Path,
    log_text: str,
) -> JobRun:
    metadata = JOB_METADATA.get(job.name, {})
    metrics = parse_metrics(log_text)
    inserted = first_metric(metrics, ["inserted", "rows inserted", "snapshot rows inserted", "snapshots inserted", "product snapshots inserted", "history points inserted", "cached fee estimates", "initial listing snapshots created", "listing snapshots inserted", "amazon inventory planning sync complete. rows inserted"])
    updated = first_metric(metrics, ["updated", "rows updated", "sku rows upserted", "amazon sku rows updated", "upserted fee estimate rows", "ynab business transactions upserted", "business value snapshot upserted"])
    skipped = sum_metrics(metrics, ["skipped", "skipped existing with tracking", "skipped missing order id", "skipped other", "rows skipped", "missing veeqo matches", "missing products", "failures", "errors"])
    read = first_metric(metrics, ["rows read", "rows fetched", "rows prepared", "orders", "buyer orders retrieved", "candidate shipments", "candidates", "purchase items scanned", "summaries fetched", "fetched amazon fba inventory summaries", "amazon skus selected for listing sync", "selected mbop fba shipments", "products returned", "transactions", "amazon orders checked", "selected price points", "opportunities checked", "candidates scored", "mbop positions projected", "reconciliation findings", "examples prepared"])

    log_size = log_path.stat().st_size if log_path and log_path.exists() else 0
    return JobRun(
        job_name=job.name,
        command=command_text,
        group_currently_assigned=", ".join(job.groups),
        start_timestamp=started_at,
        end_timestamp=ended_at,
        runtime_seconds=round(runtime, 3),
        status=status,
        error_summary=error,
        external_service_used=metadata.get("service", infer_service(command_text)),
        estimated_external_api_calls=estimate_api_calls(job.name, metrics, metadata.get("calls", ""), log_text),
        rows_inserted=str(inserted) if inserted is not None else "",
        rows_updated=str(updated) if updated is not None else "",
        rows_skipped_noop=str(skipped) if skipped is not None else "",
        rows_read_scanned=str(read) if read is not None else "",
        sync_shape=metadata.get("shape", infer_shape(command_text)),
        writes_raw_snapshots_or_high_volume_events=metadata.get("raw", ""),
        log_size_bytes=log_size,
        retry_rate_limit_behavior=retry_behavior(log_text, command_text),
        lock_collision_behavior="run_all_syncs local file lock; this instrumentation run used the same lock unless --no-lock was passed",
        proposed_aws_job_group=metadata.get("aws_group", ""),
        proposed_initial_frequency=metadata.get("frequency", ""),
        proposed_trigger_mode=metadata.get("trigger", ""),
        safe_to_run_in_cloud_mode=metadata.get("safe", ""),
        required_secrets_environment_variables=metadata.get("secrets", ""),
        concerns=metadata.get("concerns", ""),
        log_path=str(log_path.relative_to(ROOT)) if log_path and log_path.exists() else "",
    )


def parse_metrics(log_text: str) -> dict[str, int]:
    metrics: dict[str, int] = {}
    for line in log_text.splitlines():
        match = re.search(r"(?:^|\s-\s|\s)(?:[-*]\s*)?([A-Za-z][A-Za-z0-9+/_ -]{1,80}):\s*\$?(-?\d[\d,]*)\b", line)
        if not match:
            continue
        key = normalize_key(match.group(1))
        try:
            value = int(match.group(2).replace(",", ""))
        except ValueError:
            continue
        metrics[key] = value
    for pattern, key in [
        (r"Amazon sales order sync complete\. orders=(\d+) items=(\d+)", "amazon sales order rows"),
        (r"Amazon sales finance sync complete\. financial_rows=(\d+) transaction_rows=(\d+)", "amazon sales finance rows"),
        (r"Amazon sales profitability complete\. rows=(\d+)", "amazon sales profitability rows"),
        (r"Veeqo sales label sync complete\. orders=(\d+) shipments=(\d+) missing=(\d+)", "veeqo sync rows"),
    ]:
        match = re.search(pattern, log_text)
        if match:
            metrics[key] = sum(int(value) for value in match.groups())
    return metrics


def first_metric(metrics: dict[str, int], keys: list[str]) -> int | None:
    for key in keys:
        normalized = normalize_key(key)
        if normalized in metrics:
            return metrics[normalized]
    return None


def sum_metrics(metrics: dict[str, int], keys: list[str]) -> int | None:
    total = 0
    found = False
    for key in keys:
        normalized = normalize_key(key)
        if normalized in metrics:
            total += metrics[normalized]
            found = True
    return total if found else None


def estimate_api_calls(job_name: str, metrics: dict[str, int], fallback: str, log_text: str) -> str:
    observed_http = len(re.findall(r"\b(?:GET|POST|PUT|PATCH|DELETE)\s+/(?:orders|fba|listings|reports|finances|products|feeds|notifications|uploads|sellers)", log_text))
    observed_retry = len(re.findall(r"returned HTTP 429|retrying in", log_text, re.IGNORECASE))
    numeric_estimates = {
        "EasyPost shipments": first_metric(metrics, ["processed"]),
        "EasyPost order problem returns": first_metric(metrics, ["processed"]),
        "FBA EasyPost carrier tracking": first_metric(metrics, ["processed"]),
        "Sourcing listing availability": first_metric(metrics, ["unique ebay items checked"]),
        "Amazon listing status": first_metric(metrics, ["listing snapshots inserted", "rows fetched"]),
        "Amazon Product Fees estimates": first_metric(metrics, ["selected price points"]),
        "Keepa active products": max(1, (first_metric(metrics, ["asins selected"]) or 0) // 10) if first_metric(metrics, ["asins selected"]) else None,
        "Keepa FBA prep pricing": max(1, (first_metric(metrics, ["asins selected"]) or 0) // 20) if first_metric(metrics, ["asins selected"]) else None,
    }
    estimate = numeric_estimates.get(job_name)
    if estimate is not None:
        retry_note = f"; retries observed: {observed_retry}" if observed_retry else ""
        return f"observed estimate: {estimate}{retry_note}; {fallback}"
    if observed_http:
        retry_note = f"; retries observed: {observed_retry}" if observed_retry else ""
        return f"observed logged HTTP calls: {observed_http}{retry_note}; {fallback}"
    return fallback


def retry_behavior(log_text: str, command_text: str) -> str:
    signals = []
    if re.search(r"429|rate limit|retry|Retry-After|backoff", log_text, re.IGNORECASE):
        signals.append("observed retry/rate-limit log signal")
    if "easypost" in command_text:
        signals.append("EasyPost jobs cap requests and retry 429 with backoff")
    if "amazon_" in command_text or "amazon_sync" in command_text:
        signals.append("Amazon SP-API client retries 429/5xx using Retry-After/backoff")
    if "veeqo" in command_text:
        signals.append("Veeqo client retries 429/5xx with Retry-After/backoff")
    if "keepa" in command_text:
        signals.append("Keepa token threshold guards calls")
    return "; ".join(dict.fromkeys(signals)) or "none observed in run; no script-specific retry found during inspection"


def error_summary(log_text: str, returncode: int) -> str:
    lines = [line.strip() for line in log_text.splitlines() if line.strip()]
    interesting = [
        line
        for line in lines
        if re.search(r"error|exception|failed|traceback|missing|timed out", line, re.IGNORECASE)
    ]
    source = interesting[-3:] if interesting else lines[-3:]
    summary = " | ".join(source)
    return f"exit code {returncode}" + (f": {summary}" if summary else "")


def write_outputs(results: list[JobRun], *, group: str, run_id: str, exit_code: int) -> None:
    fieldnames = list(asdict(results[0]).keys()) if results else list(JobRun.__dataclass_fields__.keys())
    with CSV_PATH.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            writer.writerow(asdict(result))

    lines = [
        "# Scheduled Job Instrumentation Summary",
        "",
        f"- Run ID: `{run_id}`",
        f"- Scheduler group run: `{group}`",
        f"- Generated at: `{now_iso()}`",
        f"- Exit code so far/final: `{exit_code}`",
        f"- Jobs captured: `{len(results)}`",
        f"- CSV: `{CSV_PATH.relative_to(ROOT)}`",
        "",
        "## Observed Run",
        "",
        "| Job | Status | Runtime | Rows read | Inserted | Updated | Skipped/no-op | Log |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for result in results:
        lines.append(
            "| "
            + " | ".join(
                [
                    escape_md(result.job_name),
                    result.status,
                    f"{result.runtime_seconds:.1f}s",
                    result.rows_read_scanned or "",
                    result.rows_inserted or "",
                    result.rows_updated or "",
                    result.rows_skipped_noop or "",
                    f"`{result.log_path}`" if result.log_path else "",
                ]
            )
            + " |"
        )

    lines.extend(["", "## AWS Planning Recommendations", ""])
    for result in results:
        lines.extend(
            [
                f"### {result.job_name}",
                "",
                f"- Current groups: `{result.group_currently_assigned}`",
                f"- Command: `{result.command}`",
                f"- External service: {result.external_service_used}",
                f"- Observed status/runtime: {result.status}, {result.runtime_seconds:.1f}s",
                f"- Proposed AWS group: {result.proposed_aws_job_group}",
                f"- Proposed initial frequency: {result.proposed_initial_frequency}",
                f"- Trigger mode: {result.proposed_trigger_mode}",
                f"- Cloud mode: {result.safe_to_run_in_cloud_mode}",
                f"- Required secrets/env: {result.required_secrets_environment_variables}",
                f"- API calls: {result.estimated_external_api_calls}",
                f"- Data volume: read/scanned={result.rows_read_scanned or 'n/a'}, inserted={result.rows_inserted or 'n/a'}, updated={result.rows_updated or 'n/a'}, skipped/no-op={result.rows_skipped_noop or 'n/a'}, log={result.log_size_bytes} bytes",
                f"- Raw/high-volume writes: {result.writes_raw_snapshots_or_high_volume_events}",
                f"- Retry/rate-limit behavior: {result.retry_rate_limit_behavior}",
                f"- Lock behavior: {result.lock_collision_behavior}",
                f"- Concerns: {result.concerns}",
            ]
        )
        if result.error_summary:
            lines.append(f"- Error summary: {result.error_summary}")
        lines.append("")

    SUMMARY_PATH.write_text("\n".join(lines), encoding="utf-8")


def infer_service(command_text: str) -> str:
    lowered = command_text.lower()
    if "ebay" in lowered:
        return "eBay + Supabase"
    if "easypost" in lowered:
        return "EasyPost + Supabase"
    if "amazon" in lowered:
        return "Amazon SP-API + Supabase"
    if "keepa" in lowered:
        return "Keepa + Supabase"
    if "ynab" in lowered:
        return "YNAB + Supabase"
    if "informed" in lowered:
        return "Informed + Supabase"
    return "Supabase-only"


def infer_shape(command_text: str) -> str:
    lowered = command_text.lower()
    if "backfill" in lowered or "audit" in lowered:
        return "broad/backfill-style"
    if "--days-back" in lowered or "--lookback" in lowered or "--purchase-date-start" in lowered:
        return "bounded lookback"
    if "--limit" in lowered or "--stale-days" in lowered or "--incremental" in lowered:
        return "incremental/limited"
    return "unknown from command"


def normalize_key(value: str) -> str:
    if " - " in value:
        value = value.rsplit(" - ", 1)[-1]
    return re.sub(r"\s+", " ", value.strip().lower())


def to_float(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_")[:100]


def escape_md(value: str) -> str:
    return value.replace("|", "\\|")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
