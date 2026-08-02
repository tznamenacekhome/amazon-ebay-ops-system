from __future__ import annotations

import argparse
import datetime as dt
from typing import Any

from sourcing_common import get_supabase_client


SOURCE_TABLE = "operator_positive_conflict_review"
REVIEWED_AT = "2026-08-02T16:15:00-07:00"


EXAMPLES: list[dict[str, Any]] = [
    {
        "source_id": "2026-08-02-rock-band-3-vs-base-406156557010",
        "source_detail": "numeric_identity_operator_review",
        "asin": "B003RS8I92",
        "amazon_title": "Rock Band 3 [video game]",
        "amazon_system": "PS 3",
        "ebay_item_id": "v1|406156557010|0",
        "ebay_legacy_item_id": "406156557010",
        "ebay_title": "Rock Band (Sony PlayStation 3, PS3) New Sealed In Box",
        "ebay_item_specifics_json": {
            "Game Name": "Rock Band",
            "Platform": "Sony PlayStation 3",
        },
        "detected_system": "PS 3",
        "dismiss_reason": "wrong_edition_version",
        "dismissal_note": "Operator review confirmed historical purchase mistake: base Rock Band is not Rock Band 3.",
    },
    {
        "source_id": "2026-08-02-rock-band-3-vs-base-117010162581",
        "source_detail": "numeric_identity_operator_review",
        "asin": "B003RS8I92",
        "amazon_title": "Rock Band 3 [video game]",
        "amazon_system": "PS 3",
        "ebay_item_id": "v1|117010162581|0",
        "ebay_legacy_item_id": "117010162581",
        "ebay_title": "Rock Band Game PS3 Brand New & Factory Sealed-PlayStation 3 Rare Harmonix",
        "ebay_item_specifics_json": {
            "Game Name": "Rock Band",
            "Platform": "Sony PlayStation 3",
        },
        "detected_system": "PS 3",
        "dismiss_reason": "wrong_edition_version",
        "dismissal_note": "Operator review confirmed historical purchase mistake: base Rock Band is not Rock Band 3.",
    },
    {
        "source_id": "2026-08-02-just-dance-2014-vs-2015-sourcing-167831909062",
        "source_detail": "numeric_identity_operator_review",
        "asin": "B00D8S4GRY",
        "amazon_title": "Just Dance 2014 - PlayStation 4 [video game]",
        "amazon_system": "PS 4",
        "ebay_item_id": "v1|167831909062|0",
        "ebay_legacy_item_id": "167831909062",
        "ebay_title": "NEW Just Dance 2015 ( Sony Playstation 4, PS4, 2014 )",
        "ebay_item_specifics_json": {
            "Game Name": "Just Dance 2015",
            "Platform": "Sony PlayStation 4",
        },
        "detected_system": "PS 4",
        "dismiss_reason": "wrong_edition_version",
        "dismissal_note": "Operator review confirmed historical purchase mistake: Just Dance 2015 is not Just Dance 2014.",
    },
    {
        "source_id": "2026-08-02-just-dance-2014-vs-2015-purchase-item-167831909062",
        "source_detail": "numeric_identity_operator_review",
        "asin": "B00D8S4GRY",
        "amazon_title": "Just Dance 2014 - PlayStation 4 [video game]",
        "amazon_system": "PS 4",
        "ebay_item_id": "167831909062-10083395144115",
        "ebay_legacy_item_id": "167831909062",
        "ebay_title": "NEW Just Dance 2015 ( Sony Playstation 4, PS4, 2014 )",
        "ebay_item_specifics_json": {
            "Game Name": "Just Dance 2015",
            "Platform": "Sony PlayStation 4",
        },
        "detected_system": "PS 4",
        "dismiss_reason": "wrong_edition_version",
        "dismissal_note": "Operator review confirmed historical purchase mistake: Just Dance 2015 is not Just Dance 2014.",
    },
]


def main() -> int:
    args = parse_args()
    rows = [build_row(example) for example in EXAMPLES]

    print("Numeric identity operator-review negative examples")
    for row in rows:
        print(f"- {row['asin']} | {row['ebay_legacy_item_id']} | {row['ebay_title']}")

    if not args.write:
        print("Dry run only. Pass --write to persist these reviewed negatives.")
        return 0

    supabase = get_supabase_client()
    source_ids = [row["source_id"] for row in rows]
    (
        supabase.table("matching_intelligence_examples")
        .delete()
        .eq("source_table", SOURCE_TABLE)
        .in_("source_id", source_ids)
        .execute()
    )
    supabase.table("matching_intelligence_examples").insert(rows).execute()
    print(f"Inserted {len(rows)} reviewed negative examples.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed operator-confirmed negative examples from the 2026-08-02 numeric identity review."
    )
    parser.add_argument("--write", action="store_true", help="Persist the four reviewed negative examples.")
    return parser.parse_args()


def build_row(example: dict[str, Any]) -> dict[str, Any]:
    now = dt.datetime.now(dt.UTC).isoformat()
    return {
        "source_table": SOURCE_TABLE,
        "source_id": example["source_id"],
        "source_detail": example["source_detail"],
        "source_weight": 8,
        "asin": example["asin"],
        "amazon_title": example["amazon_title"],
        "amazon_system": example["amazon_system"],
        "ebay_item_id": example["ebay_item_id"],
        "ebay_legacy_item_id": example["ebay_legacy_item_id"],
        "ebay_title": example["ebay_title"],
        "ebay_item_specifics_json": example["ebay_item_specifics_json"],
        "detected_system": example["detected_system"],
        "operator_action": "operator_positive_conflict_review",
        "dismiss_reason": example["dismiss_reason"],
        "dismissal_note": example["dismissal_note"],
        "match_label": "non_match",
        "label_type": "negative_identity",
        "confidence": 1,
        "evidence_strength": "high",
        "later_purchase_matched": False,
        "later_received": False,
        "later_listed": False,
        "later_sold": False,
        "raw_context_json": {
            "reviewed_at": REVIEWED_AT,
            "review_outcome": "historical_purchase_mistake",
            "review_scope": "post_deployment_numeric_identity_positive_conflict_review",
            "note": "Operator confirmed these were not valid matches and should be treated as negative training examples.",
        },
        "created_at": REVIEWED_AT,
        "reviewed_at": REVIEWED_AT,
        "rebuilt_at": now,
    }


if __name__ == "__main__":
    raise SystemExit(main())
