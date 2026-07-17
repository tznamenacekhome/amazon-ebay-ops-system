"""Resumable Amazon sales-order history backfill.

This runner processes historical sales in small date chunks and records
phase-level progress in a JSON state file. It is designed for a separate
PowerShell window: if the window closes, Supabase has a temporary problem, or
an API throttles/fails, rerun the same command with --resume and completed work
will be skipped.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from supabase import create_client

LOGGER = logging.getLogger("amazon_sales_history_backfill")
ROOT_DIR = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT_DIR / "logs"
DEFAULT_STATE_FILE = LOG_DIR / "amazon_sales_backfill_state.json"
DEFAULT_LOG_FILE = LOG_DIR / "amazon_sales_backfill.log"
DEFAULT_CHUNK_DAYS = 3
DEFAULT_ORDER_PAGE_DELAY_SECONDS = 6.0
DEFAULT_ORDER_ITEM_DELAY_SECONDS = 2.5
DEFAULT_ORDER_FINANCE_DELAY_SECONDS = 1.5
DEFAULT_PHASE_DELAY_SECONDS = 10.0
DEFAULT_CHUNK_DELAY_SECONDS = 60.0
MIN_START_DATE = "2025-01-01"
AMAZON_ORDER_RETRIEVAL_DELAY_MINUTES = 5
PHASES = ("orders", "finances", "veeqo", "profitability")
ORDER_ONLY_PHASES = ("orders",)


def main() -> int:
    args = parse_args()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    configure_logging(args.log_file)
    load_dotenv(ROOT_DIR / ".env")
    load_dotenv(ROOT_DIR / ".env.local")

    state_path = Path(args.state_file)
    if args.status:
        print_status(load_state(state_path))
        return 0

    if not args.apply:
        LOGGER.info("Planning mode only. Add --apply to write to Supabase.")

    state = load_state(state_path) if args.resume else new_state(args)
    if args.force:
        state = new_state(args)
    state["last_run_apply"] = bool(args.apply)
    state["last_run_started_at"] = utc_now()
    state["phases"] = list(active_phases(args))

    chunks = build_chunks(args.start_date, args.end_date, args.chunk_days, active_phases(args))
    state["chunks"] = merge_chunks(state.get("chunks", []), chunks)
    save_state(state_path, state)

    LOGGER.info(
        "Backfill prepared: chunks=%s range=%s..%s state=%s",
        len(state["chunks"]),
        args.start_date,
        args.end_date,
        state_path,
    )

    if args.plan:
        print_plan(state)
        return 0

    try:
        probe_supabase(max_attempts=args.supabase_probe_attempts)
        for chunk in state["chunks"]:
            if chunk.get("status") == "complete" and not args.force:
                LOGGER.info("Skipping completed chunk %s", chunk["key"])
                continue

            run_chunk(args, state_path, state, chunk)
            if args.chunk_delay_seconds > 0:
                time.sleep(args.chunk_delay_seconds)

        state["status"] = "complete"
        state["completed_at"] = utc_now()
        save_state(state_path, state)
        LOGGER.info("Amazon sales backfill complete.")
        return 0
    except KeyboardInterrupt:
        mark_interrupted(state_path, state, "KeyboardInterrupt")
        LOGGER.warning("Backfill interrupted. Re-run the same command with --resume.")
        return 130
    except Exception as error:  # noqa: BLE001
        mark_interrupted(state_path, state, str(error))
        LOGGER.exception("Backfill stopped safely. Re-run with --resume after fixing the issue.")
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill Amazon sales history in resumable date chunks."
    )
    parser.add_argument("--start-date", help="Inclusive YYYY-MM-DD.")
    parser.add_argument("--end-date", help="Inclusive YYYY-MM-DD.")
    parser.add_argument("--chunk-days", type=int, default=DEFAULT_CHUNK_DAYS)
    parser.add_argument("--state-file", default=str(DEFAULT_STATE_FILE))
    parser.add_argument("--log-file", default=str(DEFAULT_LOG_FILE))
    parser.add_argument("--resume", action="store_true", help="Resume from state file.")
    parser.add_argument("--force", action="store_true", help="Rebuild state and rerun all chunks.")
    parser.add_argument("--plan", action="store_true", help="Show chunks without running them.")
    parser.add_argument("--status", action="store_true", help="Print progress from state file.")
    parser.add_argument("--apply", action="store_true", help="Write to Supabase.")
    parser.add_argument(
        "--order-page-delay-seconds",
        type=float,
        default=DEFAULT_ORDER_PAGE_DELAY_SECONDS,
    )
    parser.add_argument(
        "--order-item-delay-seconds",
        type=float,
        default=DEFAULT_ORDER_ITEM_DELAY_SECONDS,
    )
    parser.add_argument(
        "--order-finance-delay-seconds",
        type=float,
        default=DEFAULT_ORDER_FINANCE_DELAY_SECONDS,
    )
    parser.add_argument(
        "--phase-delay-seconds",
        type=float,
        default=DEFAULT_PHASE_DELAY_SECONDS,
    )
    parser.add_argument(
        "--chunk-delay-seconds",
        type=float,
        default=DEFAULT_CHUNK_DELAY_SECONDS,
    )
    parser.add_argument(
        "--skip-veeqo",
        action="store_true",
        help="Skip Veeqo label lookup phase.",
    )
    parser.add_argument(
        "--orders-only",
        action="store_true",
        help="Only backfill Amazon sales orders and order items.",
    )
    parser.add_argument(
        "--supabase-probe-attempts",
        type=int,
        default=3,
        help="Tiny Supabase read attempts before each chunk.",
    )
    args = parser.parse_args()
    if not args.status and (not args.start_date or not args.end_date):
        parser.error("--start-date and --end-date are required unless --status is used.")
    if not args.status and args.start_date < MIN_START_DATE:
        parser.error(f"--start-date must be {MIN_START_DATE} or later for MBOP sales data.")
    return args


def configure_logging(log_file: str) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        handlers=handlers,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


def new_state(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "status": "planned",
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "start_date": args.start_date,
        "end_date": args.end_date,
        "chunk_days": args.chunk_days,
        "phases": list(active_phases(args)),
        "apply": bool(args.apply),
        "chunks": [],
    }


def active_phases(args: argparse.Namespace) -> tuple[str, ...]:
    return ORDER_ONLY_PHASES if args.orders_only else PHASES


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"State file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(path: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = utc_now()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    temp_path.replace(path)


def build_chunks(start_date: str, end_date: str, chunk_days: int, phases: tuple[str, ...] = PHASES) -> list[dict[str, Any]]:
    if chunk_days < 1:
        raise ValueError("--chunk-days must be at least 1")
    start = parse_day(start_date)
    inclusive_end = parse_day(end_date)
    requested_exclusive_end = inclusive_end + dt.timedelta(days=1)
    safe_exclusive_end = dt.datetime.now(dt.timezone.utc) - dt.timedelta(
        minutes=AMAZON_ORDER_RETRIEVAL_DELAY_MINUTES,
    )
    exclusive_end = min(requested_exclusive_end, safe_exclusive_end)
    if start >= exclusive_end:
        raise ValueError(
            "--start-date must be before Amazon's safe order retrieval cutoff "
            f"({to_iso_z(safe_exclusive_end)})"
        )

    chunks: list[dict[str, Any]] = []
    cursor = start
    while cursor < exclusive_end:
        next_cursor = min(cursor + dt.timedelta(days=chunk_days), exclusive_end)
        start_iso = to_iso_z(cursor)
        end_iso = to_iso_z(next_cursor)
        key = f"{chunk_key_part(cursor)}__{chunk_key_part(next_cursor)}"
        chunks.append(
            {
                "key": key,
                "start": start_iso,
                "end": end_iso,
                "status": "pending",
                "phases": {
                    phase: {"status": "pending", "attempts": 0}
                    for phase in phases
                },
            }
        )
        cursor = next_cursor
    return chunks


def merge_chunks(existing: list[dict[str, Any]], planned: list[dict[str, Any]]) -> list[dict[str, Any]]:
    existing_by_key = {chunk.get("key"): chunk for chunk in existing}
    merged: list[dict[str, Any]] = []
    for chunk in planned:
        saved = existing_by_key.get(chunk["key"])
        merged.append(saved if saved else chunk)
    return merged


def run_chunk(
    args: argparse.Namespace,
    state_path: Path,
    state: dict[str, Any],
    chunk: dict[str, Any],
) -> None:
    LOGGER.info("Starting chunk %s (%s to %s)", chunk["key"], chunk["start"], chunk["end"])
    probe_supabase(max_attempts=args.supabase_probe_attempts)
    chunk["status"] = "in_progress"
    chunk["started_at"] = chunk.get("started_at") or utc_now()
    save_state(state_path, state)

    for phase in active_phases(args):
        if phase == "veeqo" and args.skip_veeqo:
            mark_phase_skipped(chunk, phase)
            save_state(state_path, state)
            continue
        phase_state = chunk["phases"][phase]
        if phase_state.get("status") == "complete":
            LOGGER.info("Skipping completed phase %s for chunk %s", phase, chunk["key"])
            continue

        run_phase(args, state_path, state, chunk, phase)
        if args.phase_delay_seconds > 0:
            time.sleep(args.phase_delay_seconds)

    chunk["status"] = "complete"
    chunk["completed_at"] = utc_now()
    save_state(state_path, state)
    LOGGER.info("Completed chunk %s", chunk["key"])


def run_phase(
    args: argparse.Namespace,
    state_path: Path,
    state: dict[str, Any],
    chunk: dict[str, Any],
    phase: str,
) -> None:
    phase_state = chunk["phases"][phase]
    phase_state["status"] = "in_progress"
    phase_state["attempts"] = int(phase_state.get("attempts") or 0) + 1
    phase_state["started_at"] = utc_now()
    save_state(state_path, state)

    command = phase_command(args, chunk, phase)
    phase_state["command"] = command
    LOGGER.info("Running %s for %s: %s", phase, chunk["key"], " ".join(command))
    completed = subprocess.run(
        command,
        cwd=ROOT_DIR,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.stdout:
        LOGGER.info("%s stdout:\n%s", phase, completed.stdout.strip())
    if completed.stderr:
        LOGGER.warning("%s stderr:\n%s", phase, completed.stderr.strip())

    phase_state["returncode"] = completed.returncode
    phase_state["finished_at"] = utc_now()
    if completed.returncode != 0:
        phase_state["status"] = "failed"
        save_state(state_path, state)
        raise RuntimeError(
            f"Phase {phase} failed for chunk {chunk['key']} with exit code {completed.returncode}"
        )

    phase_state["status"] = "complete"
    save_state(state_path, state)


def phase_command(args: argparse.Namespace, chunk: dict[str, Any], phase: str) -> list[str]:
    apply_flag = ["--apply"] if args.apply else []
    if phase == "orders":
        return [
            sys.executable,
            "integrations/amazon_sync_sales_orders.py",
            "--created-after",
            chunk["start"],
            "--created-before",
            chunk["end"],
            "--order-item-delay-seconds",
            str(args.order_item_delay_seconds),
            "--order-page-delay-seconds",
            str(args.order_page_delay_seconds),
            *apply_flag,
        ]
    if phase == "finances":
        return [
            sys.executable,
            "integrations/amazon_sync_sales_finances.py",
            "--purchase-date-start",
            chunk["start"],
            "--purchase-date-end",
            chunk["end"],
            "--order-finance-delay-seconds",
            str(args.order_finance_delay_seconds),
            *apply_flag,
        ]
    if phase == "veeqo":
        return [
            sys.executable,
            "integrations/veeqo_sync_sales_labels.py",
            "--purchase-date-start",
            chunk["start"],
            "--purchase-date-end",
            chunk["end"],
            *apply_flag,
        ]
    if phase == "profitability":
        return [
            sys.executable,
            "integrations/amazon_sales_profitability.py",
            "--purchase-date-start",
            chunk["start"],
            "--purchase-date-end",
            chunk["end"],
            *apply_flag,
        ]
    raise ValueError(f"Unknown phase: {phase}")


def mark_phase_skipped(chunk: dict[str, Any], phase: str) -> None:
    chunk["phases"][phase] = {
        "status": "skipped",
        "attempts": int(chunk["phases"].get(phase, {}).get("attempts") or 0),
        "finished_at": utc_now(),
    }


def mark_interrupted(path: Path, state: dict[str, Any], reason: str) -> None:
    state["status"] = "interrupted"
    state["last_error"] = reason
    save_state(path, state)


def probe_supabase(*, max_attempts: int) -> None:
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY.")

    last_error: Exception | None = None
    for attempt in range(1, max(max_attempts, 1) + 1):
        try:
            client = create_client(supabase_url, supabase_key)
            result = client.table("import_batches").select("import_batch_id").limit(1).execute()
            LOGGER.info("Supabase probe ok. rows=%s", len(result.data or []))
            return
        except Exception as error:  # noqa: BLE001
            last_error = error
            delay = min(60, attempt * 10)
            LOGGER.warning("Supabase probe failed on attempt %s: %s", attempt, error)
            if attempt < max_attempts:
                time.sleep(delay)
    raise RuntimeError(f"Supabase probe failed; pausing backfill: {last_error}")


def print_plan(state: dict[str, Any]) -> None:
    print("Amazon sales history backfill plan")
    print("----------------------------------")
    print(f"Range: {state['start_date']} to {state['end_date']}")
    print(f"Chunk days: {state['chunk_days']}")
    print(f"Chunks: {len(state['chunks'])}")
    for chunk in state["chunks"][:10]:
        print(f"- {chunk['key']} status={chunk['status']}")
    if len(state["chunks"]) > 10:
        print(f"... {len(state['chunks']) - 10} more")


def print_status(state: dict[str, Any]) -> None:
    chunks = state.get("chunks", [])
    counts: dict[str, int] = {}
    for chunk in chunks:
        status = chunk.get("status") or "unknown"
        counts[status] = counts.get(status, 0) + 1

    print("Amazon sales history backfill status")
    print("------------------------------------")
    print(f"Range: {state.get('start_date')} to {state.get('end_date')}")
    print(f"Overall: {state.get('status') or 'unknown'}")
    print(f"Updated: {state.get('updated_at') or '--'}")
    print(f"Chunks: {len(chunks)}")
    for status in ("complete", "in_progress", "failed", "pending"):
        print(f"{status}: {counts.get(status, 0)}")

    active = [
        chunk
        for chunk in chunks
        if chunk.get("status") in {"in_progress", "failed"}
        or any(
            phase.get("status") in {"in_progress", "failed"}
            for phase in (chunk.get("phases") or {}).values()
        )
    ]
    for chunk in active[:10]:
        phase_bits = [
            f"{name}={phase.get('status')}"
            for name, phase in (chunk.get("phases") or {}).items()
        ]
        print(f"- {chunk.get('key')} {chunk.get('status')} {' '.join(phase_bits)}")
    if state.get("last_error"):
        print(f"Last error: {state['last_error']}")


def parse_day(value: str) -> dt.datetime:
    return dt.datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)


def to_iso_z(value: dt.datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def utc_now() -> str:
    return to_iso_z(dt.datetime.now(dt.timezone.utc))


def chunk_key_part(value: dt.datetime) -> str:
    if value.time() == dt.time(0, 0):
        return value.date().isoformat()
    return value.strftime("%Y-%m-%dT%H%M%SZ")


if __name__ == "__main__":
    raise SystemExit(main())
