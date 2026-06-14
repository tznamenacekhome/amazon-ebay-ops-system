"""Shared helpers for MBOP matching intelligence evidence and labels."""

from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict
from statistics import median
from typing import Any


IDENTITY_REASONS = {
    "wrong_product",
    "wrong_platform",
    "wrong_edition_version",
    "non_north_american_version",
    "incomplete_product",
    "digital_item",
}
CONDITION_REASONS = {
    "missing_shrink_wrap",
    "suspected_reseal",
    "packaging_damage",
    "packaging_condition_issue",
}
BUSINESS_REASONS = {
    "roi_too_low",
    "sales_velocity_too_low",
    "too_much_competition",
    "capital_better_used_elsewhere",
    "valid_product_poor_opportunity",
    "not_worth_selling",
}
AVAILABILITY_SYSTEM_REASONS = {"no_longer_available"}

PRODUCT_CONDITION_RETURN_REASONS = IDENTITY_REASONS | CONDITION_REASONS

REASON_LABELS = {
    **{reason: ("non_match", "negative_identity") for reason in IDENTITY_REASONS},
    **{reason: ("condition_problem", "condition_issue") for reason in CONDITION_REASONS},
    **{reason: ("valid_match_poor_opportunity", "business_issue") for reason in BUSINESS_REASONS},
    **{reason: ("availability_system", "availability_system") for reason in AVAILABILITY_SYSTEM_REASONS},
    "other": ("needs_review", "unknown"),
}


def label_for_dismiss_reason(reason: Any) -> tuple[str, str]:
    return REASON_LABELS.get(normalize_reason(reason), ("needs_review", "unknown"))


def normalize_reason(reason: Any) -> str:
    return str(reason or "").strip().lower().replace("-", "_").replace(" ", "_")


def build_listing_snapshot(
    *,
    opportunity: dict[str, Any] | None,
    candidate: dict[str, Any] | None,
    seed: dict[str, Any] | None,
    event: str,
    action_id: str | None = None,
    source: str = "mbop",
    raw_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    opportunity = opportunity or {}
    candidate = candidate or {}
    seed = seed or {}
    raw = candidate.get("raw_ebay_json") or {}
    seller = raw.get("seller") if isinstance(raw, dict) else {}
    category = first_category(raw)
    return {
        "opportunity_id": opportunity.get("opportunity_id"),
        "candidate_id": candidate.get("candidate_id") or opportunity.get("candidate_id"),
        "action_id": action_id,
        "sourcing_run_id": opportunity.get("sourcing_run_id") or candidate.get("sourcing_run_id"),
        "snapshot_event": event,
        "snapshot_source": source,
        "asin": opportunity.get("asin") or candidate.get("asin") or seed.get("asin"),
        "amazon_title": seed.get("amazon_title"),
        "amazon_system": seed.get("system"),
        "amazon_image_url": seed.get("amazon_image_url"),
        "target_sale_price": opportunity.get("target_sale_price") or seed.get("target_sale_price"),
        "target_sale_price_source": opportunity.get("target_sale_price_source") or seed.get("target_sale_price_source"),
        "ebay_item_id": candidate.get("ebay_item_id") or opportunity.get("ebay_item_id"),
        "ebay_legacy_item_id": candidate.get("ebay_legacy_item_id") or raw_value(raw, "legacyItemId"),
        "ebay_title": candidate.get("ebay_title") or raw_value(raw, "title"),
        "ebay_subtitle": raw_value(raw, "subtitle"),
        "ebay_description": raw_value(raw, "description") or raw_value(raw, "shortDescription"),
        "ebay_condition": candidate.get("condition") or raw_value(raw, "condition"),
        "ebay_condition_id": candidate.get("condition_id") or raw_value(raw, "conditionId"),
        "ebay_category": category.get("categoryName") if category else raw_value(raw, "categoryPath"),
        "ebay_category_id": category.get("categoryId") if category else raw_value(raw, "categoryId"),
        "ebay_category_path": raw_value(raw, "categoryPath"),
        "ebay_item_specifics_json": raw.get("localizedAspects") if isinstance(raw, dict) else None,
        "ebay_primary_image_url": candidate.get("ebay_image_url") or nested_value(raw, "image", "imageUrl"),
        "ebay_image_urls": image_urls(raw),
        "ebay_listing_url": candidate.get("ebay_item_web_url") or raw_value(raw, "itemWebUrl"),
        "price": candidate.get("price"),
        "shipping_cost": candidate.get("shipping_cost"),
        "landed_cost": candidate.get("landed_cost") or opportunity.get("landed_cost"),
        "shipping_is_separate": candidate.get("shipping_is_separate"),
        "quantity_available": candidate.get("available_quantity"),
        "buying_options": candidate.get("buying_options") or raw.get("buyingOptions") if isinstance(raw, dict) else None,
        "listing_status": candidate.get("listing_status") or opportunity.get("status"),
        "seller_username": candidate.get("seller_username") or (seller or {}).get("username"),
        "seller_feedback_score": int_or_none((seller or {}).get("feedbackScore")),
        "seller_feedback_percentage": float_or_none((seller or {}).get("feedbackPercentage")),
        "seller_status": None,
        "item_location_country": candidate.get("item_location_country") or nested_value(raw, "itemLocation", "country"),
        "ships_to_configured_zip": has_zip_shipping_estimate(raw),
        "raw_ebay_json": raw if isinstance(raw, dict) else None,
        "raw_context_json": raw_context or {},
        "captured_at": dt.datetime.now(dt.UTC).isoformat(),
    }


def example_from_snapshot(
    *,
    source_table: str,
    source_id: str,
    source_detail: str | None,
    snapshot: dict[str, Any] | None,
    action: dict[str, Any] | None = None,
    match_label: str,
    label_type: str,
    confidence: float = 1,
    evidence_strength: str = "medium",
    raw_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    snapshot = snapshot or {}
    action = action or {}
    return {
        "source_table": source_table,
        "source_id": source_id,
        "source_detail": source_detail,
        "source_weight": source_weight(source_table, match_label),
        "listing_snapshot_id": snapshot.get("listing_snapshot_id"),
        "opportunity_id": snapshot.get("opportunity_id") or action.get("opportunity_id"),
        "candidate_id": snapshot.get("candidate_id") or action.get("candidate_id"),
        "action_id": action.get("action_id"),
        "asin": snapshot.get("asin") or action.get("asin"),
        "amazon_title": snapshot.get("amazon_title"),
        "amazon_image_url": snapshot.get("amazon_image_url"),
        "amazon_system": snapshot.get("amazon_system"),
        "ebay_item_id": snapshot.get("ebay_item_id") or action.get("ebay_item_id"),
        "ebay_legacy_item_id": snapshot.get("ebay_legacy_item_id"),
        "ebay_title": snapshot.get("ebay_title"),
        "ebay_description": snapshot.get("ebay_description"),
        "ebay_primary_image_url": snapshot.get("ebay_primary_image_url"),
        "ebay_image_urls": snapshot.get("ebay_image_urls"),
        "ebay_item_specifics_json": snapshot.get("ebay_item_specifics_json"),
        "ebay_condition": snapshot.get("ebay_condition"),
        "ebay_category": snapshot.get("ebay_category"),
        "ebay_seller_username": snapshot.get("seller_username"),
        "detected_system": snapshot.get("amazon_system"),
        "operator_action": action.get("action_type"),
        "dismiss_reason": action.get("dismiss_reason"),
        "dismissal_note": action.get("notes"),
        "match_label": match_label,
        "label_type": label_type,
        "confidence": confidence,
        "evidence_strength": evidence_strength,
        "later_purchase_matched": False,
        "later_received": False,
        "later_listed": False,
        "later_sold": False,
        "raw_context_json": raw_context or {},
        "created_at": action.get("created_at") or snapshot.get("captured_at") or dt.datetime.now(dt.UTC).isoformat(),
        "reviewed_at": action.get("created_at"),
        "rebuilt_at": dt.datetime.now(dt.UTC).isoformat(),
    }


def source_weight(source_table: str, match_label: str) -> float:
    if source_table == "manual_item_matches":
        return 10
    if source_table == "sourcing_purchase_matches":
        return 7
    if source_table == "order_problem_cases":
        return 8 if match_label in {"non_match", "condition_problem"} else 5
    if source_table == "sourcing_actions":
        return 5
    return 1


def first_category(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    categories = raw.get("categories")
    if isinstance(categories, list) and categories:
        return categories[0] if isinstance(categories[0], dict) else None
    return None


def image_urls(raw: Any) -> list[str]:
    if not isinstance(raw, dict):
        return []
    urls: list[str] = []
    for key in ("image",):
        url = nested_value(raw, key, "imageUrl")
        if url:
            urls.append(str(url))
    for key in ("thumbnailImages", "additionalImages"):
        values = raw.get(key)
        if isinstance(values, list):
            urls.extend(str(row.get("imageUrl")) for row in values if isinstance(row, dict) and row.get("imageUrl"))
    return list(dict.fromkeys(urls))


def has_zip_shipping_estimate(raw: Any) -> bool:
    if not isinstance(raw, dict):
        return False
    for option in raw.get("shippingOptions") or []:
        if isinstance(option, dict) and nested_value(option, "shipToLocationUsedForEstimate", "postalCode"):
            return True
    return False


def raw_value(raw: Any, key: str) -> Any:
    return raw.get(key) if isinstance(raw, dict) else None


def nested_value(raw: Any, *keys: str) -> Any:
    current = raw
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def int_or_none(value: Any) -> int | None:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def float_or_none(value: Any) -> float | None:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def seller_status_from_counts(product_condition_returns: int) -> tuple[str, str, float]:
    if product_condition_returns >= 2:
        return "avoid", "2+ product/condition return strikes", 0
    if product_condition_returns == 1:
        return "watch", "1 product/condition return strike", 45
    return "normal", "No product/condition return strikes", 70
