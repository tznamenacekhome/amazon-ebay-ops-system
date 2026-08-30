"""Dismiss duplicate open/unreviewed sourcing opportunities, keeping one per ASIN."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from collections import defaultdict
from typing import Any

from refresh_sourcing_listing_availability_trading_fallback import chunks, fetch_eligible_opportunities, legacy_item_id
from sourcing_common import get_supabase_client


DISMISS_REASON = "duplicate_open_asin_opportunity"


def main() -> int:
    args = parse_args()
    supabase = get_supabase_client()
    result = plan_duplicate_cleanup(supabase)

    summary = {
        "eligible_open_unreviewed": result["eligible_open_unreviewed"],
        "asins_with_open_opportunities": result["asins_with_open_opportunities"],
        "asins_with_duplicates": result["asins_with_duplicates"],
        "kept_opportunities": len(result["keepers"]),
        "duplicate_opportunities_to_dismiss": len(result["duplicates"]),
        "apply": args.apply,
    }
    print("Duplicate open ASIN opportunity cleanup")
    print("---------------------------------------")
    for key, value in summary.items():
        print(f"{key}: {value}")
    print()
    print(f"Representative duplicate dismissals ({min(args.sample, len(result['duplicates']))} of {len(result['duplicates'])})")
    print(json.dumps([sample_row(row, result["keepers"][asin_key(row)]) for row in result["duplicates"][: args.sample]], indent=2))

    if not args.apply:
        print()
        print("Dry run only. Re-run with --apply to dismiss duplicates.")
        return 0

    dismissed = apply_duplicate_cleanup(supabase, result)
    remaining = plan_duplicate_cleanup(supabase)["eligible_open_unreviewed"]
    print()
    print("Applied duplicate cleanup")
    print("-------------------------")
    print(f"Dismissed duplicate opportunities: {dismissed}")
    print(f"Remaining open/unreviewed opportunities: {remaining}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Keep only one open/unreviewed sourcing opportunity per ASIN.")
    parser.add_argument("--apply", action="store_true", help="Dismiss duplicate rows.")
    parser.add_argument("--sample", type=int, default=25, help="Number of proposed duplicate dismissals to print.")
    return parser.parse_args()


def enforce_one_open_opportunity_per_asin(supabase) -> dict[str, Any]:
    result = plan_duplicate_cleanup(supabase)
    dismissed = apply_duplicate_cleanup(supabase, result)
    return {
        "eligible_open_unreviewed": result["eligible_open_unreviewed"],
        "asins_with_open_opportunities": result["asins_with_open_opportunities"],
        "asins_with_duplicates": result["asins_with_duplicates"],
        "dismissed_duplicate_opportunities": dismissed,
    }


def plan_duplicate_cleanup(supabase) -> dict[str, Any]:
    rows = fetch_eligible_opportunities(supabase, None)
    groups = group_by_asin(rows)
    keepers, duplicates = choose_duplicates(groups)
    return {
        "eligible_open_unreviewed": len(rows),
        "asins_with_open_opportunities": len(groups),
        "asins_with_duplicates": sum(1 for group in groups.values() if len(group) > 1),
        "keepers": keepers,
        "duplicates": duplicates,
    }


def apply_duplicate_cleanup(supabase, result: dict[str, Any]) -> int:
    return apply_duplicates(supabase, result["duplicates"], result["keepers"])


def group_by_asin(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = asin_key(row)
        if key:
            groups[key].append(row)
    return dict(groups)


def choose_duplicates(groups: dict[str, list[dict[str, Any]]]) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    keepers: dict[str, dict[str, Any]] = {}
    duplicates: list[dict[str, Any]] = []
    for asin, group in sorted(groups.items()):
        ranked = sorted(group, key=sort_key)
        keepers[asin] = ranked[0]
        duplicates.extend(ranked[1:])
    duplicates.sort(key=lambda row: (asin_key(row), sort_key(row)))
    return keepers, duplicates


def sort_key(row: dict[str, Any]) -> tuple[int, float, str]:
    return (
        0 if row.get("status") == "open" else 1,
        -score(row),
        reverse_text(str(row.get("created_at") or "")),
    )


def apply_duplicates(supabase, duplicates: list[dict[str, Any]], keepers: dict[str, dict[str, Any]]) -> int:
    now = dt.datetime.now(dt.UTC).isoformat()
    update_ids = [str(row.get("opportunity_id")) for row in duplicates if row.get("opportunity_id")]
    for chunk in chunks(update_ids, 100):
        supabase.table("sourcing_opportunities").update(
            {
                "status": "dismissed",
                "updated_at": now,
            }
        ).in_("opportunity_id", chunk).execute()

    action_rows = []
    for row in duplicates:
        opportunity_id = row.get("opportunity_id")
        if not opportunity_id:
            continue
        keeper = keepers[asin_key(row)]
        action_rows.append(
            {
                "opportunity_id": opportunity_id,
                "candidate_id": row.get("candidate_id"),
                "asin": row.get("asin"),
                "ebay_item_id": row.get("ebay_item_id"),
                "action_type": "dismissed",
                "dismiss_reason": DISMISS_REASON,
                "notes": f"Duplicate open/unreviewed ASIN cleanup; kept opportunity {keeper.get('opportunity_id')}.",
                "raw_action_context": {
                    "cleanup_source": "cleanup_sourcing_duplicate_asin_opportunities",
                    "kept_opportunity_id": keeper.get("opportunity_id"),
                    "kept_ebay_item_id": keeper.get("ebay_item_id"),
                    "kept_score": keeper.get("score"),
                    "dismissed_score": row.get("score"),
                    "checked_at": now,
                },
            }
        )
    for chunk in chunks(action_rows, 500):
        supabase.table("sourcing_actions").insert(chunk).execute()
    return len(update_ids)


def sample_row(row: dict[str, Any], keeper: dict[str, Any]) -> dict[str, Any]:
    candidate = row.get("sourcing_ebay_candidates") or {}
    kept_candidate = keeper.get("sourcing_ebay_candidates") or {}
    return {
        "asin": asin_key(row),
        "dismiss_opportunity_id": row.get("opportunity_id"),
        "dismiss_ebay_item_id": row.get("ebay_item_id"),
        "dismiss_legacy_item_id": legacy_item_id(row.get("ebay_item_id")),
        "dismiss_score": row.get("score"),
        "dismiss_created_at": row.get("created_at"),
        "dismiss_title": candidate.get("ebay_title"),
        "keep_opportunity_id": keeper.get("opportunity_id"),
        "keep_ebay_item_id": keeper.get("ebay_item_id"),
        "keep_legacy_item_id": legacy_item_id(keeper.get("ebay_item_id")),
        "keep_score": keeper.get("score"),
        "keep_created_at": keeper.get("created_at"),
        "keep_title": kept_candidate.get("ebay_title"),
        "reason": DISMISS_REASON,
    }


def asin_key(row: dict[str, Any]) -> str:
    return str(row.get("asin") or "").strip().upper()


def score(row: dict[str, Any]) -> float:
    value = row.get("score")
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("-inf")


def reverse_text(value: str) -> str:
    return "".join(chr(0x10FFFF - ord(char)) for char in value)


if __name__ == "__main__":
    raise SystemExit(main())
