"""Backfill dynamic sourcing suppressions from Sales Velocity Too Low dismissals."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

from sourcing_common import fetch_settings, get_supabase_client, paginate_table, to_float


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    args = parse_args()
    supabase = get_supabase_client()
    settings = fetch_settings(supabase)
    actions = fetch_sales_velocity_actions(supabase)
    latest_by_asin = latest_action_by_asin(actions)
    rows = [suppression_row(action, settings) for action in latest_by_asin.values()]
    artifact = write_artifact(rows, args.write)
    print("Sales Velocity suppression backfill")
    print("-----------------------------------")
    print(f"Mode: {'write' if args.write else 'dry-run'}")
    print(f"Dismissal actions found: {len(actions)}")
    print(f"ASINs selected: {len(rows)}")
    print(f"Artifact: {artifact}")
    if args.write:
        written = write_rows(supabase, rows)
        print(f"Rows written: {written}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill sales velocity sourcing suppressions.")
    parser.add_argument("--write", action="store_true")
    return parser.parse_args()


def fetch_sales_velocity_actions(supabase) -> list[dict[str, Any]]:
    return paginate_table(
        supabase,
        "sourcing_actions",
        "action_id,opportunity_id,asin,dismiss_reason,created_at,raw_action_context,sourcing_opportunities(sourcing_seed_asins(monthly_velocity,inventory_need_level,months_of_supply))",
        order_column="created_at",
        desc=True,
    )


def latest_action_by_asin(actions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for action in actions:
        if str(action.get("dismiss_reason") or "") != "sales_velocity_too_low":
            continue
        asin = str(action.get("asin") or "").upper()
        if asin and asin not in output:
            output[asin] = action
    return output


def suppression_row(action: dict[str, Any], settings) -> dict[str, Any]:
    asin = str(action.get("asin") or "").upper()
    opportunity = action.get("sourcing_opportunities") if isinstance(action.get("sourcing_opportunities"), dict) else {}
    seed = opportunity.get("sourcing_seed_asins") if isinstance(opportunity.get("sourcing_seed_asins"), dict) else {}
    current_velocity = nullable_number(seed.get("monthly_velocity"))
    lookback_days = int(settings.sales_lookback_days or 90)
    required_velocity = round(1 / max(lookback_days / 30, 1), 4)
    created_at = action.get("created_at") or dt.datetime.now(dt.UTC).isoformat()
    return {
        "asin": asin,
        "source_action_id": action.get("action_id"),
        "dismissed_at": created_at,
        "velocity_at_dismissal": current_velocity,
        "metric_window_days": lookback_days,
        "required_velocity": required_velocity,
        "current_velocity": current_velocity,
        "status": "active",
        "last_evaluated_at": dt.datetime.now(dt.UTC).isoformat(),
        "reactivated_at": None,
        "reason_code": "sales_velocity_too_low",
        "raw_context_json": {
            "opportunityId": action.get("opportunity_id"),
            "backfill": True,
            "inventoryNeedLevel": seed.get("inventory_need_level"),
            "monthsOfSupply": seed.get("months_of_supply"),
        },
        "updated_at": dt.datetime.now(dt.UTC).isoformat(),
    }


def write_rows(supabase, rows: list[dict[str, Any]]) -> int:
    written = 0
    for row in rows:
        existing = (
            supabase.table("sourcing_sales_velocity_suppressions")
            .select("suppression_id")
            .eq("asin", row["asin"])
            .eq("status", "active")
            .limit(1)
            .execute()
        )
        existing_row = (existing.data or [{}])[0]
        if existing_row.get("suppression_id"):
            supabase.table("sourcing_sales_velocity_suppressions").update(row).eq(
                "suppression_id",
                existing_row["suppression_id"],
            ).execute()
        else:
            supabase.table("sourcing_sales_velocity_suppressions").insert(
                {**row, "created_at": dt.datetime.now(dt.UTC).isoformat()}
            ).execute()
        written += 1
    return written


def write_artifact(rows: list[dict[str, Any]], write: bool) -> Path:
    timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d%H%M%S")
    path = ROOT / "tmp" / f"sales_velocity_suppression_backfill_{'write' if write else 'dry_run'}_{timestamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"count": len(rows), "rows": rows}, indent=2, default=str), encoding="utf-8")
    return path


def nullable_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return round(to_float(value, 0), 4)


if __name__ == "__main__":
    raise SystemExit(main())
