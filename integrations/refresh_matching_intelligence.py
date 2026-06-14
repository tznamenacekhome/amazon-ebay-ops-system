"""Refresh Matching Intelligence examples and rescore recent sourcing runs."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

from sourcing_common import get_supabase_client


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    args = parse_args()
    supabase = get_supabase_client()

    if not args.skip_rebuild:
        command = [
            sys.executable,
            str(ROOT / "integrations" / "build_matching_intelligence_examples.py"),
            "--source",
            "all",
            "--write",
        ]
        if args.dry_run:
            command.remove("--write")
        run_command(command)

    runs = latest_sourcing_runs_by_mode(supabase, args.runs_per_mode)
    print("Matching Intelligence sourcing rescore")
    print("-------------------------------------")
    print(f"Runs selected: {len(runs)}")
    for row in runs:
        print(f"- {row.get('run_type')} {row.get('sourcing_run_id')} started={row.get('started_at')}")
        if args.dry_run:
            continue
        run_command(
            [
                sys.executable,
                str(ROOT / "integrations" / "score_sourcing_opportunities.py"),
                "--run-id",
                str(row["sourcing_run_id"]),
                "--update-existing",
            ]
        )

    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh Matching Intelligence and apply it to live sourcing.")
    parser.add_argument("--runs-per-mode", type=int, default=1)
    parser.add_argument("--skip-rebuild", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def latest_sourcing_runs_by_mode(supabase, runs_per_mode: int) -> list[dict[str, Any]]:
    response = (
        supabase.table("sourcing_runs")
        .select("sourcing_run_id,run_type,started_at,completed_at,status")
        .eq("status", "completed")
        .order("started_at", desc=True)
        .limit(max(20, runs_per_mode * 6))
        .execute()
    )
    selected: list[dict[str, Any]] = []
    counts_by_mode: dict[str, int] = {}
    for row in response.data or []:
        mode = str(row.get("run_type") or "unknown")
        if counts_by_mode.get(mode, 0) >= runs_per_mode:
            continue
        selected.append(row)
        counts_by_mode[mode] = counts_by_mode.get(mode, 0) + 1
    return selected


def run_command(command: list[str]) -> None:
    print(f"\n--- {' '.join(command)} ---")
    subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    raise SystemExit(main())
