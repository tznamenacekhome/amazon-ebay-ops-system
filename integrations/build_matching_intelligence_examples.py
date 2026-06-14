"""Build Matching Intelligence examples from existing MBOP evidence."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import datetime as dt
from statistics import median
from typing import Any

from matching_intelligence import (
    PRODUCT_CONDITION_RETURN_REASONS,
    build_listing_snapshot,
    example_from_snapshot,
    label_for_dismiss_reason,
    seller_status_from_counts,
)
from sourcing_common import chunked, get_supabase_client, paginate_table, to_float


SOURCES = {"sourcing", "manual_matches", "purchases", "returns", "receiving", "all"}


def main() -> int:
    args = parse_args()
    supabase = get_supabase_client()

    examples: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    if args.source in {"sourcing", "all"}:
        sourcing_examples, sourcing_snapshots = build_sourcing_examples(supabase, args.limit)
        examples.extend(sourcing_examples)
        snapshots.extend(sourcing_snapshots)
    if args.source in {"manual_matches", "all"}:
        manual_examples, manual_snapshots = build_manual_match_examples(supabase, args.limit)
        examples.extend(manual_examples)
        snapshots.extend(manual_snapshots)
    if args.source in {"purchases", "all"}:
        purchase_examples, purchase_snapshots = build_verified_purchase_item_examples(supabase, args.limit)
        examples.extend(purchase_examples)
        snapshots.extend(purchase_snapshots)
        examples.extend(build_purchase_match_examples(supabase, args.limit))
    if args.source in {"returns", "all"}:
        examples.extend(build_return_examples(supabase, args.limit))
    if args.source in {"receiving", "all"}:
        examples.extend(build_receiving_outcome_examples(supabase, args.limit))

    print_summary(examples, snapshots)

    if not args.write:
        print("Dry run only. Pass --write to persist examples.")
        return 0

    write_rows(supabase, examples, snapshots, args.source)
    rebuild_seller_intelligence(supabase)
    print("Matching intelligence rebuild complete.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build MBOP matching intelligence examples.")
    parser.add_argument("--source", choices=sorted(SOURCES), default="all")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args()


def build_sourcing_examples(supabase, limit: int | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    actions = paginate_table(
        supabase,
        "sourcing_actions",
        "*",
        max_rows=limit,
        order_column="created_at",
        desc=True,
    )
    snapshots_by_action = {
        row.get("action_id"): row
        for row in paginate_table(
            supabase,
            "sourcing_listing_snapshots",
            "*",
            order_column="captured_at",
            desc=True,
        )
        if row.get("action_id")
    }
    opportunities = rows_by_id(paginate_table(supabase, "sourcing_opportunities", "*,sourcing_ebay_candidates(*),sourcing_seed_asins(*)"), "opportunity_id")

    examples: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    for action in actions:
        action_type = str(action.get("action_type") or "")
        reason = action.get("dismiss_reason")
        label, label_type = label_for_action(action_type, reason)
        snapshot = snapshots_by_action.get(action.get("action_id"))
        if not snapshot:
            opportunity = opportunities.get(action.get("opportunity_id")) or {}
            snapshot = build_listing_snapshot(
                opportunity=opportunity,
                candidate=opportunity.get("sourcing_ebay_candidates") or {},
                seed=opportunity.get("sourcing_seed_asins") or {},
                event=action_type if action_type in {"dismissed", "watching", "purchased", "roi_snoozed"} else "backfill",
                action_id=action.get("action_id"),
                source="matching_intelligence_backfill",
                raw_context={"backfilled_from_action": True},
            )
            snapshots.append(snapshot)
        examples.append(
            example_from_snapshot(
                source_table="sourcing_actions",
                source_id=str(action.get("action_id")),
                source_detail=action_type,
                snapshot=snapshot,
                action=action,
                match_label=label,
                label_type=label_type,
                confidence=0.95 if action_type == "dismissed" else 0.75,
                evidence_strength="medium",
                raw_context={"action": action},
            )
        )
    return examples, snapshots


def label_for_action(action_type: str, reason: Any) -> tuple[str, str]:
    if action_type == "dismissed":
        return label_for_dismiss_reason(reason)
    if action_type == "purchased":
        return "match", "positive_identity"
    if action_type == "roi_snoozed":
        return "valid_match_poor_opportunity", "business_issue"
    return "needs_review", "unknown"


def build_manual_match_examples(supabase, limit: int | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows = paginate_table(supabase, "manual_item_matches", "*", max_rows=limit, order_column="created_at", desc=True)
    examples = []
    snapshots = []
    for row in rows:
        snapshot = snapshot_from_purchase_like(
            source_table="manual_item_matches",
            source_id=str(row.get("match_id")),
            asin=row.get("asin"),
            amazon_title=row.get("amazon_title"),
            amazon_system=row.get("system"),
            ebay_title=row.get("source_title"),
            purchase_item_id=row.get("source_purchase_item_id"),
            created_at=row.get("created_at"),
            raw_context={"manual_match": row},
        )
        snapshots.append(snapshot)
        examples.append(
            {
                "source_table": "manual_item_matches",
                "source_id": str(row.get("match_id")),
                "source_detail": row.get("match_source"),
                "source_weight": 10,
                "purchase_item_id": row.get("source_purchase_item_id"),
                "asin": row.get("asin"),
                "amazon_title": row.get("amazon_title"),
                "amazon_system": row.get("system"),
                "ebay_title": row.get("source_title"),
                "detected_system": row.get("system"),
                "operator_action": "manual_match",
                "match_label": "match",
                "label_type": "positive_identity",
                "confidence": 1,
                "evidence_strength": "very_high",
                "later_purchase_matched": True,
                "raw_context_json": {"manual_match": row},
                "created_at": row.get("created_at"),
                "reviewed_at": row.get("created_at"),
                "_snapshot_source_table": "manual_item_matches",
                "_snapshot_source_id": str(row.get("match_id")),
            }
        )
    return examples, snapshots


def build_verified_purchase_item_examples(supabase, limit: int | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows = paginate_table(
        supabase,
        "purchase_items",
        "*",
        max_rows=limit,
        order_column="created_at",
        desc=True,
    )
    sales_outcomes = sales_outcomes_by_purchase_item_id(supabase)
    examples = []
    snapshots = []
    for row in rows:
        asin = clean_optional_text(row.get("asin"))
        if not asin:
            continue

        status = clean_optional_text(row.get("current_status"))
        received = bool(row.get("received_date")) or status in {"received", "listed", "sold"}
        listed = status in {"listed", "sold"}
        sales = sales_outcomes.get(str(row.get("item_id"))) or {}
        snapshot = snapshot_from_purchase_item(row)
        snapshots.append(snapshot)
        example = {
            "source_table": "purchase_items",
            "source_id": str(row.get("item_id")),
            "source_detail": "verified_purchase_item",
            "source_weight": 10,
            "purchase_item_id": row.get("item_id"),
            "asin": asin,
            "amazon_title": row.get("amazon_title"),
            "amazon_system": row.get("system"),
            "ebay_item_id": ebay_item_id_from_purchase_item(row),
            "ebay_title": row.get("title"),
            "detected_system": row.get("system"),
            "operator_action": "verified_purchase_item",
            "match_label": "match",
            "label_type": "positive_identity",
            "confidence": 1,
            "evidence_strength": "very_high",
            "later_purchase_matched": True,
            "later_received": received,
            "later_listed": listed,
            "later_sold": bool(sales.get("quantity_sold")),
            "later_profit": sales.get("net_profit") if sales.get("net_profit") is not None else row.get("estimated_profit"),
            "raw_context_json": {"purchase_item": row, "sales_outcome": sales},
            "created_at": row.get("created_at"),
            "reviewed_at": row.get("verified_date") or row.get("received_date") or row.get("created_at"),
            "_snapshot_source_table": "purchase_items",
            "_snapshot_source_id": str(row.get("item_id")),
        }
        examples.append(example)
    return examples, snapshots


def build_receiving_outcome_examples(supabase, limit: int | None) -> list[dict[str, Any]]:
    rows = safe_paginate_table(
        supabase,
        "matching_intelligence_receiving_outcomes",
        "*",
        max_rows=limit,
        order_column="created_at",
        desc=True,
    )
    examples = []
    for row in rows:
        label, label_type, reason = label_for_receiving_outcome(row)
        examples.append(
            {
                "source_table": "matching_intelligence_receiving_outcomes",
                "source_id": str(row.get("receiving_outcome_id")),
                "source_detail": row.get("outcome"),
                "source_weight": 9 if label == "match" else 8,
                "purchase_item_id": row.get("purchase_item_id"),
                "asin": row.get("asin"),
                "amazon_title": row.get("amazon_title"),
                "amazon_system": row.get("system"),
                "ebay_item_id": row.get("ebay_item_id"),
                "ebay_title": row.get("ebay_title"),
                "detected_system": row.get("system"),
                "operator_action": "receiving_outcome",
                "return_reason": reason,
                "return_notes": row.get("notes"),
                "match_label": label,
                "label_type": label_type,
                "confidence": 1,
                "evidence_strength": "very_high",
                "later_purchase_matched": True,
                "later_received": row.get("outcome") in {"correct_item", "listed_successfully"},
                "later_listed": row.get("outcome") == "listed_successfully",
                "raw_context_json": {"receiving_outcome": row},
                "created_at": row.get("created_at"),
                "reviewed_at": row.get("created_at"),
            }
        )
    return examples


def build_purchase_match_examples(supabase, limit: int | None) -> list[dict[str, Any]]:
    rows = paginate_table(supabase, "sourcing_purchase_matches", "*", max_rows=limit, order_column="matched_at", desc=True)
    opportunities = rows_by_id(paginate_table(supabase, "sourcing_opportunities", "*,sourcing_ebay_candidates(*),sourcing_seed_asins(*)"), "opportunity_id")
    examples = []
    for row in rows:
        opportunity = opportunities.get(row.get("opportunity_id")) or {}
        snapshot = build_listing_snapshot(
            opportunity=opportunity,
            candidate=opportunity.get("sourcing_ebay_candidates") or {},
            seed=opportunity.get("sourcing_seed_asins") or {},
            event="backfill",
            source="matching_intelligence_backfill",
            raw_context={"sourcing_purchase_match": row},
        )
        example = example_from_snapshot(
            source_table="sourcing_purchase_matches",
            source_id=str(row.get("match_id")),
            source_detail=row.get("match_method"),
            snapshot=snapshot,
            action={"action_type": "purchase_matched", "created_at": row.get("matched_at")},
            match_label="match",
            label_type="positive_identity",
            confidence=to_float(row.get("match_confidence"), 1),
            evidence_strength="high",
            raw_context={"sourcing_purchase_match": row},
        )
        example["purchase_item_id"] = row.get("purchase_item_id")
        example["sourcing_purchase_match_id"] = row.get("match_id")
        example["later_purchase_matched"] = True
        examples.append(example)
    return examples


def build_return_examples(supabase, limit: int | None) -> list[dict[str, Any]]:
    rows = paginate_table(supabase, "order_problem_cases", "*", max_rows=limit, order_column="created_at", desc=True)
    purchase_items = rows_by_id(paginate_table(supabase, "purchase_items", "*"), "item_id")
    examples = []
    for row in rows:
        label, label_type, reason = label_for_return(row)
        if label == "needs_review":
            continue
        item = purchase_items.get(row.get("purchase_item_id")) or {}
        examples.append(
            {
                "source_table": "order_problem_cases",
                "source_id": str(row.get("problem_case_id")),
                "source_detail": row.get("problem_type"),
                "source_weight": 8,
                "problem_case_id": row.get("problem_case_id"),
                "purchase_item_id": row.get("purchase_item_id"),
                "asin": item.get("asin"),
                "amazon_title": item.get("amazon_title"),
                "amazon_system": item.get("system"),
                "ebay_item_id": ebay_item_id_from_case(row, item),
                "ebay_title": item.get("title"),
                "detected_system": item.get("system"),
                "operator_action": "return_outcome",
                "return_reason": reason,
                "return_notes": row.get("notes") or case_comment(row),
                "match_label": label,
                "label_type": label_type,
                "confidence": 0.85,
                "evidence_strength": "high",
                "raw_context_json": {"order_problem_case": row, "purchase_item": item},
                "created_at": row.get("created_at"),
                "reviewed_at": row.get("updated_at"),
            }
        )
    return examples


def label_for_return(row: dict[str, Any]) -> tuple[str, str, str]:
    text = f"{row.get('problem_type') or ''} {row.get('notes') or ''} {case_comment(row)}".lower()
    if any(term in text for term in ["wrong platform", "wrong system"]):
        return "non_match", "negative_identity", "wrong_platform"
    if any(term in text for term in ["wrong edition", "greatest hits", "platinum hits", "player's choice"]):
        return "non_match", "negative_identity", "wrong_edition_version"
    if any(term in text for term in ["pegi", "pal", "cero", "usk", "non-north", "foreign"]):
        return "non_match", "negative_identity", "non_north_american_version"
    if any(term in text for term in ["disc only", "case only", "missing manual", "incomplete"]):
        return "non_match", "negative_identity", "incomplete_product"
    if any(term in text for term in ["shrink", "seal", "sealed", "reseal", "counterfeit", "not as described", "snad"]):
        return "condition_problem", "condition_issue", "packaging_condition_issue"
    if str(row.get("problem_type") or "").lower() in {"not_as_listed", "not_as_described"}:
        return "condition_problem", "condition_issue", "packaging_condition_issue"
    return "needs_review", "unknown", "other"


def label_for_receiving_outcome(row: dict[str, Any]) -> tuple[str, str, str]:
    outcome = clean_optional_text(row.get("outcome"))
    issue = clean_optional_text(row.get("condition_issue"))
    if outcome in {"correct_item", "listed_successfully"}:
        return "match", "positive_identity", "correct_item"
    if outcome == "wrong_item":
        return "non_match", "negative_identity", issue or "wrong_product"
    if outcome == "incomplete_item":
        return "non_match", "negative_identity", issue or "incomplete_product"
    if outcome in {"wrong_condition", "packaging_issue"}:
        condition_issue = issue or "packaging_condition_issue"
        if condition_issue in {"wrong_product", "wrong_platform", "wrong_edition_version", "non_north_american_version", "incomplete_product"}:
            return "non_match", "negative_identity", condition_issue
        return "condition_problem", "condition_issue", condition_issue
    return "needs_review", "unknown", issue or "other"


def case_comment(row: dict[str, Any]) -> str:
    raw = row.get("raw_ebay_json") or {}
    creation = raw.get("creationInfo") if isinstance(raw, dict) else {}
    comments = creation.get("comments") if isinstance(creation, dict) else {}
    return str(comments.get("content") or "") if isinstance(comments, dict) else ""


def ebay_item_id_from_case(row: dict[str, Any], item: dict[str, Any]) -> str | None:
    raw = row.get("raw_ebay_json") or {}
    creation = raw.get("creationInfo") if isinstance(raw, dict) else {}
    ebay_item = creation.get("item") if isinstance(creation, dict) else {}
    return ebay_item.get("itemId") if isinstance(ebay_item, dict) else item.get("supplier_sku")


def ebay_item_id_from_purchase_item(item: dict[str, Any]) -> str | None:
    supplier_sku = clean_optional_text(item.get("supplier_sku"))
    if supplier_sku:
        return supplier_sku

    url = clean_optional_text(item.get("supplier_listing_url"))
    if not url:
        return None
    for token in url.replace("?", "/").replace("#", "/").split("/"):
        cleaned = token.strip()
        if cleaned.isdigit() and len(cleaned) >= 9:
            return cleaned
    return url


def snapshot_from_purchase_item(item: dict[str, Any]) -> dict[str, Any]:
    return snapshot_from_purchase_like(
        source_table="purchase_items",
        source_id=str(item.get("item_id")),
        asin=item.get("asin"),
        amazon_title=item.get("amazon_title"),
        amazon_system=item.get("system"),
        ebay_title=item.get("title"),
        ebay_item_id=ebay_item_id_from_purchase_item(item),
        ebay_listing_url=item.get("supplier_listing_url"),
        price=item.get("unit_cost"),
        landed_cost=item.get("unit_cost"),
        quantity_available=item.get("quantity"),
        purchase_item_id=item.get("item_id"),
        created_at=item.get("created_at"),
        raw_context={"purchase_item": item},
    )


def snapshot_from_purchase_like(
    *,
    source_table: str,
    source_id: str,
    asin: Any,
    amazon_title: Any,
    amazon_system: Any,
    ebay_title: Any,
    ebay_item_id: Any = None,
    ebay_listing_url: Any = None,
    price: Any = None,
    landed_cost: Any = None,
    quantity_available: Any = None,
    purchase_item_id: Any = None,
    created_at: Any = None,
    raw_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "snapshot_event": "backfill",
        "snapshot_source": "matching_intelligence_backfill",
        "asin": asin,
        "amazon_title": amazon_title,
        "amazon_system": amazon_system,
        "ebay_item_id": ebay_item_id,
        "ebay_legacy_item_id": legacy_item_id(ebay_item_id),
        "ebay_title": ebay_title,
        "ebay_listing_url": ebay_listing_url,
        "price": price,
        "landed_cost": landed_cost,
        "quantity_available": quantity_available,
        "listing_status": "historical_purchase",
        "captured_at": created_at or dt.datetime.now(dt.UTC).isoformat(),
        "raw_context_json": {
            **(raw_context or {}),
            "source_table": source_table,
            "source_id": source_id,
            "purchase_item_id": purchase_item_id,
        },
    }


def sales_outcomes_by_purchase_item_id(supabase) -> dict[str, dict[str, Any]]:
    consumptions = safe_paginate_table(
        supabase,
        "amazon_sales_cogs_consumption",
        "source_reference_id,source_reference_type,amazon_order_id,amazon_order_item_id,asin,quantity_consumed,total_cogs",
    )
    by_order_item = {
        str(row.get("amazon_order_item_id")): row
        for row in safe_paginate_table(
            supabase,
            "amazon_sales_profitability",
            "amazon_order_item_id,quantity,sale_price,net_profit,roi",
        )
        if row.get("amazon_order_item_id")
    }
    outcomes: dict[str, dict[str, Any]] = defaultdict(lambda: {"quantity_sold": 0, "net_profit": 0.0, "sale_price": 0.0})
    for row in consumptions:
        if clean_optional_text(row.get("source_reference_type")) != "purchase_item":
            continue
        item_id = clean_optional_text(row.get("source_reference_id"))
        if not item_id:
            continue
        profit = by_order_item.get(str(row.get("amazon_order_item_id"))) or {}
        outcome = outcomes[item_id]
        outcome["quantity_sold"] += int(to_float(row.get("quantity_consumed"), 0))
        outcome["net_profit"] += to_float(profit.get("net_profit"), 0)
        outcome["sale_price"] += to_float(profit.get("sale_price"), 0)
    return {
        key: {
            **value,
            "net_profit": round(value["net_profit"], 2),
            "sale_price": round(value["sale_price"], 2),
        }
        for key, value in outcomes.items()
    }


def legacy_item_id(value: Any) -> str | None:
    text = clean_optional_text(value)
    if not text:
        return None
    if text.startswith("v1|"):
        parts = text.split("|")
        return parts[1] if len(parts) > 1 and parts[1] else None
    if text.isdigit():
        return text
    return None


def safe_paginate_table(supabase, table_name: str, columns: str = "*", **kwargs) -> list[dict[str, Any]]:
    try:
        return paginate_table(supabase, table_name, columns, **kwargs)
    except Exception as error:
        print(f"Skipping {table_name}: {error}")
        return []


def clean_optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def write_rows(supabase, examples: list[dict[str, Any]], snapshots: list[dict[str, Any]], source: str) -> None:
    sources_to_clear = ["sourcing_actions", "manual_item_matches", "purchase_items", "sourcing_purchase_matches", "order_problem_cases", "matching_intelligence_receiving_outcomes"] if source == "all" else source_tables_for(source)
    for table in sources_to_clear:
        supabase.table("matching_intelligence_examples").delete().eq("source_table", table).execute()
    if source in {"all", "sourcing", "manual_matches", "purchases"}:
        supabase.table("sourcing_listing_snapshots").delete().eq("snapshot_source", "matching_intelligence_backfill").execute()

    inserted_snapshots = []
    for batch in chunked(snapshots, 250):
        response = supabase.table("sourcing_listing_snapshots").insert(batch).execute()
        inserted_snapshots.extend(response.data or [])
    snapshots_by_action = {row.get("action_id"): row for row in inserted_snapshots if row.get("action_id")}
    snapshots_by_source = {
        (
            (row.get("raw_context_json") or {}).get("source_table"),
            str((row.get("raw_context_json") or {}).get("source_id")),
        ): row
        for row in inserted_snapshots
        if isinstance(row.get("raw_context_json"), dict)
    }
    for example in examples:
        action_id = example.get("action_id")
        if action_id and action_id in snapshots_by_action:
            example["listing_snapshot_id"] = snapshots_by_action[action_id].get("listing_snapshot_id")
        source_key = (example.pop("_snapshot_source_table", None), str(example.pop("_snapshot_source_id", "")))
        if not example.get("listing_snapshot_id") and source_key in snapshots_by_source:
            example["listing_snapshot_id"] = snapshots_by_source[source_key].get("listing_snapshot_id")
        normalize_example_defaults(example)
    clear_missing_snapshot_references(supabase, examples)

    for batch in chunked(examples, 250):
        supabase.table("matching_intelligence_examples").insert(batch).execute()


def clear_missing_snapshot_references(supabase, examples: list[dict[str, Any]]) -> None:
    snapshot_ids = sorted({row.get("listing_snapshot_id") for row in examples if row.get("listing_snapshot_id")})
    valid_ids: set[str] = set()
    for batch in [snapshot_ids[index : index + 100] for index in range(0, len(snapshot_ids), 100)]:
        response = (
            supabase.table("sourcing_listing_snapshots")
            .select("listing_snapshot_id")
            .in_("listing_snapshot_id", batch)
            .execute()
        )
        valid_ids.update(str(row.get("listing_snapshot_id")) for row in response.data or [])
    for row in examples:
        snapshot_id = row.get("listing_snapshot_id")
        if snapshot_id and str(snapshot_id) not in valid_ids:
            row["listing_snapshot_id"] = None


def normalize_example_defaults(example: dict[str, Any]) -> None:
    for key in ("later_purchase_matched", "later_received", "later_listed", "later_sold"):
        example[key] = bool(example.get(key))
    if example.get("confidence") is None:
        example["confidence"] = 1
    if not example.get("evidence_strength"):
        example["evidence_strength"] = "medium"
    if not example.get("rebuilt_at"):
        example["rebuilt_at"] = dt.datetime.now(dt.UTC).isoformat()


def source_tables_for(source: str) -> list[str]:
    if source == "sourcing":
        return ["sourcing_actions"]
    if source == "manual_matches":
        return ["manual_item_matches"]
    if source == "purchases":
        return ["purchase_items", "sourcing_purchase_matches"]
    if source == "returns":
        return ["order_problem_cases"]
    if source == "receiving":
        return ["matching_intelligence_receiving_outcomes"]
    return []


def rebuild_seller_intelligence(supabase) -> None:
    examples = paginate_table(supabase, "matching_intelligence_examples", "*")
    by_seller: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for example in examples:
        seller = str(example.get("ebay_seller_username") or "").strip()
        if seller:
            by_seller[seller].append(example)

    rows = []
    for seller, seller_examples in by_seller.items():
        condition_returns = sum(1 for row in seller_examples if row.get("return_reason") in PRODUCT_CONDITION_RETURN_REASONS or row.get("match_label") in {"non_match", "condition_problem"})
        status, reason, score = seller_status_from_counts(condition_returns)
        opportunities = len({row.get("opportunity_id") for row in seller_examples if row.get("opportunity_id")})
        purchases = sum(1 for row in seller_examples if row.get("later_purchase_matched") or row.get("operator_action") in {"purchased", "purchase_matched"})
        profits = [to_float(row.get("later_profit"), 0) for row in seller_examples if row.get("later_profit") is not None]
        rows.append(
            {
                "seller_username": seller,
                "product_condition_return_count": condition_returns,
                "return_count": sum(1 for row in seller_examples if row.get("source_table") == "order_problem_cases"),
                "wrong_product_return_count": count_return_reason(seller_examples, "wrong_product"),
                "wrong_platform_return_count": count_return_reason(seller_examples, "wrong_platform"),
                "wrong_edition_return_count": count_return_reason(seller_examples, "wrong_edition_version"),
                "non_na_return_count": count_return_reason(seller_examples, "non_north_american_version"),
                "incomplete_product_return_count": count_return_reason(seller_examples, "incomplete_product"),
                "missing_shrink_wrap_return_count": count_return_reason(seller_examples, "missing_shrink_wrap"),
                "suspected_reseal_return_count": count_return_reason(seller_examples, "suspected_reseal"),
                "packaging_damage_return_count": count_return_reason(seller_examples, "packaging_damage"),
                "opportunity_count": opportunities,
                "purchase_conversion_count": purchases,
                "purchase_conversion_rate": round(purchases / opportunities, 4) if opportunities else None,
                "total_profit": round(sum(profits), 2) if profits else None,
                "seller_trust_score": score,
                "seller_status": status,
                "status_reason": reason,
                "raw_metrics_json": {"example_count": len(seller_examples)},
            }
        )

    supabase.table("sourcing_seller_intelligence").delete().neq("seller_username", "").execute()
    for batch in chunked(rows, 250):
        supabase.table("sourcing_seller_intelligence").insert(batch).execute()


def count_return_reason(rows: list[dict[str, Any]], reason: str) -> int:
    return sum(1 for row in rows if row.get("return_reason") == reason or row.get("dismiss_reason") == reason)


def rows_by_id(rows: list[dict[str, Any]], key: str) -> dict[Any, dict[str, Any]]:
    return {row.get(key): row for row in rows if row.get(key)}


def print_summary(examples: list[dict[str, Any]], snapshots: list[dict[str, Any]]) -> None:
    labels = Counter(row.get("match_label") for row in examples)
    reasons = Counter(row.get("dismiss_reason") for row in examples if row.get("dismiss_reason"))
    sources = Counter(row.get("source_table") for row in examples)
    missing_notes = sum(1 for row in examples if row.get("dismiss_reason") and not row.get("dismissal_note"))
    print("Matching Intelligence example rebuild")
    print("-------------------------------------")
    print(f"Examples prepared: {len(examples)}")
    print(f"Backfill snapshots prepared: {len(snapshots)}")
    print(f"Dismiss examples missing notes: {missing_notes}")
    print(f"By source: {dict(sources)}")
    print(f"By label: {dict(labels)}")
    print(f"By dismiss reason: {dict(reasons)}")


if __name__ == "__main__":
    raise SystemExit(main())
