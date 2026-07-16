"""Unified sourcing coverage-cycle queue and metrics helpers."""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Any

from build_sourcing_seed_asins import (
    build_full_listing_seeds,
    build_recent_sales_seeds,
    catalog_video_game_context,
    fetch_blocked_asins,
    infer_platform_context,
    is_video_game_seed,
    latest_catalog_context_by_asin,
)
from sourcing_common import chunked, fetch_settings, paginate_table, to_float


PRIORITY_RECENTLY_SOLD = "1_recently_sold"
PRIORITY_PURCHASED_NOT_SENT = "2_purchased_not_sent"
PRIORITY_CATALOG_REMAINING = "3_catalog_remaining"
PENDING_STATUSES = {"pending", "retryable_failed", "paused"}
COMPLETED_STATUSES = {"searched", "skipped", "ineligible"}
EXCLUDED_PURCHASE_STATUSES = {"cancelled", "return_opened", "return_pending", "listed"}
SENT_FBA_WORKFLOW_STATUSES = {"finalized", "shipped", "in_transit", "delivered", "receiving", "closed", "historical"}


@dataclass(frozen=True)
class QueueBuildResult:
    rows: list[dict[str, Any]]
    counts: dict[str, int]


def build_unified_priority_queue(
    supabase,
    settings=None,
    *,
    limit: int = 20000,
    exclude_asins: set[str] | None = None,
) -> QueueBuildResult:
    settings = settings or fetch_settings(supabase)
    exclude_asins = {clean_asin(asin) for asin in (exclude_asins or set()) if clean_asin(asin)}
    recent = build_recent_sales_seeds(supabase, settings, limit)
    purchased = build_purchased_not_sent_seeds(supabase, settings, limit)
    catalog = build_full_listing_seeds(supabase, settings, limit)

    by_asin: dict[str, dict[str, Any]] = {}
    for priority, seeds in (
        (PRIORITY_RECENTLY_SOLD, recent),
        (PRIORITY_PURCHASED_NOT_SENT, purchased),
        (PRIORITY_CATALOG_REMAINING, catalog),
    ):
        for seed in seeds:
            asin = clean_asin(seed.get("asin"))
            if not asin or asin in by_asin or asin in exclude_asins:
                continue
            by_asin[asin] = queue_row_from_seed(seed, priority)

    rows = sorted(by_asin.values(), key=queue_sort_key)
    for index, row in enumerate(rows, start=1):
        row["queue_position"] = index

    counts = {
        PRIORITY_RECENTLY_SOLD: len([row for row in rows if row["priority_bucket"] == PRIORITY_RECENTLY_SOLD]),
        PRIORITY_PURCHASED_NOT_SENT: len([row for row in rows if row["priority_bucket"] == PRIORITY_PURCHASED_NOT_SENT]),
        PRIORITY_CATALOG_REMAINING: len([row for row in rows if row["priority_bucket"] == PRIORITY_CATALOG_REMAINING]),
    }
    return QueueBuildResult(rows=rows, counts=counts)


def build_purchased_not_sent_seeds(supabase, settings, limit: int) -> list[dict[str, Any]]:
    cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(days=90)
    rows = paginate_table(
        supabase,
        "purchase_items",
        (
            "item_id,purchase_id,asin,amazon_title,title,current_status,marketplace,quantity,"
            "target_price,received_date,created_at,exclude_from_purchase_reporting,purchases(order_date)"
        ),
        max_rows=20000,
        order_column="created_at",
        desc=True,
    )
    fba_links = fetch_fba_links_by_item_id(supabase, [str(row.get("item_id")) for row in rows if row.get("item_id")])
    catalog_by_asin = latest_catalog_context_by_asin(supabase)
    blocked_asins = fetch_blocked_asins(supabase)
    seeds: list[dict[str, Any]] = []
    for row in rows:
        asin = clean_asin(row.get("asin"))
        if not asin:
            continue
        if asin in blocked_asins:
            continue
        purchase_date = purchase_order_date(row)
        if not purchase_date or parse_datetime(purchase_date) < cutoff:
            continue
        if not is_purchased_not_yet_sent_to_amazon(row, fba_links.get(str(row.get("item_id"))) or []):
            continue
        amazon_title = row.get("amazon_title") or row.get("title") or asin
        catalog_context = catalog_by_asin.get(asin) or {}
        platform_context = infer_platform_context(asin, amazon_title, catalog_context)
        seed = {
            "seed_id": str(uuid.uuid4()),
            "asin": asin,
            "seller_sku": None,
            "amazon_title": amazon_title,
            "amazon_image_url": None,
            "source_mode": "purchased_not_sent",
            "target_sale_price": to_float(row.get("target_price"), 0),
            "target_sale_price_source": "purchase_context",
            "last_sold_at": None,
            "units_sold_60d": 0,
            "units_sold_90d": 0,
            "monthly_velocity": 0,
            "current_inventory_units": to_float(row.get("quantity"), 1),
            "months_of_supply": None,
            "inventory_need_level": "critical",
            "is_restricted": False,
            "is_suppressed": False,
            "is_return_heavy": False,
            "warning_flags": [],
            "raw_context_json": {
                **catalog_video_game_context(catalog_context),
                "eligibility_reason": "purchased_not_sent_to_amazon",
                "purchase_item_id": row.get("item_id"),
                "purchase_id": row.get("purchase_id"),
                "purchase_state": purchase_state(row, fba_links.get(str(row.get("item_id"))) or []),
                "last_purchased_at": purchase_date,
                "inferred_system": platform_context.get("system"),
                "inferred_system_source": platform_context.get("source"),
            },
        }
        if not is_video_game_seed(seed):
            continue
        seeds.append(seed)
        if len(seeds) >= limit:
            break
    return sorted(seeds, key=lambda seed: (seed["raw_context_json"].get("last_purchased_at") or ""), reverse=True)


def is_purchased_not_yet_sent_to_amazon(item: dict[str, Any], fba_links: list[dict[str, Any]] | None = None) -> bool:
    if item.get("exclude_from_purchase_reporting") is True:
        return False
    asin = clean_asin(item.get("asin"))
    if not asin:
        return False
    status = clean_status(item.get("current_status"))
    if status in EXCLUDED_PURCHASE_STATUSES:
        return False
    if status in {"refunded", "returned"}:
        return False
    marketplace = str(item.get("marketplace") or "").strip().casefold()
    if marketplace == "ebay":
        return False
    quantity = max(int(to_float(item.get("quantity"), 1)), 1)
    sent_quantity = 0
    for link in fba_links or []:
        if not link.get("included", True):
            continue
        shipment_code = str((link.get("fba_shipments") or {}).get("shipment_code") or "")
        if shipment_code == "legacy_listed_no_shipment_id":
            return False
        workflow_status = clean_status((link.get("fba_shipments") or {}).get("workflow_status"))
        if workflow_status in SENT_FBA_WORKFLOW_STATUSES:
            sent_quantity += int(to_float(link.get("quantity"), 0))
    return sent_quantity < quantity


def fetch_fba_links_by_item_id(supabase, item_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    by_item_id: dict[str, list[dict[str, Any]]] = {}
    for batch in chunked([item_id for item_id in item_ids if item_id], 100):
        response = (
            supabase.table("fba_shipment_items")
            .select("item_id,quantity,included,fba_shipments(shipment_code,workflow_status,amazon_status_normalized)")
            .in_("item_id", batch)
            .execute()
        )
        for row in response.data or []:
            item_id = str(row.get("item_id") or "")
            by_item_id.setdefault(item_id, []).append(row)
    return by_item_id


def queue_row_from_seed(seed: dict[str, Any], priority_bucket: str) -> dict[str, Any]:
    raw_context = seed.get("raw_context_json") if isinstance(seed.get("raw_context_json"), dict) else {}
    return {
        "asin": clean_asin(seed.get("asin")),
        "seller_sku": seed.get("seller_sku"),
        "amazon_title": seed.get("amazon_title"),
        "amazon_image_url": seed.get("amazon_image_url"),
        "priority_bucket": priority_bucket,
        "priority_sort_date": sort_date_for_seed(seed, priority_bucket),
        "processing_status": "pending",
        "eligibility_reason": eligibility_reason(priority_bucket),
        "last_sold_at": seed.get("last_sold_at"),
        "last_purchased_at": raw_context.get("last_purchased_at"),
        "purchase_state": raw_context.get("purchase_state"),
        "inventory_need_level": seed.get("inventory_need_level"),
        "monthly_velocity": seed.get("monthly_velocity"),
        "current_inventory_units": seed.get("current_inventory_units"),
        "months_of_supply": seed.get("months_of_supply"),
        "target_sale_price": seed.get("target_sale_price"),
        "target_sale_price_source": seed.get("target_sale_price_source"),
        "seed_snapshot_json": seed,
    }


def queue_sort_key(row: dict[str, Any]) -> tuple[int, str, int, str]:
    priority_order = {
        PRIORITY_RECENTLY_SOLD: 1,
        PRIORITY_PURCHASED_NOT_SENT: 2,
        PRIORITY_CATALOG_REMAINING: 3,
    }
    date_text = str(row.get("priority_sort_date") or "")
    need_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(str(row.get("inventory_need_level") or ""), 0)
    return (priority_order.get(row.get("priority_bucket"), 9), invert_date_text(date_text), -need_rank, str(row.get("asin") or ""))


def seed_row_for_run(item: dict[str, Any], run_id: str, coverage_cycle_id: str) -> dict[str, Any]:
    seed = dict(item.get("seed_snapshot_json") or {})
    raw_context = dict(seed.get("raw_context_json") or {})
    raw_context.update(
        {
            "coverage_cycle_id": coverage_cycle_id,
            "coverage_cycle_item_id": item.get("cycle_item_id"),
            "priority_bucket": item.get("priority_bucket"),
            "queue_position": item.get("queue_position"),
        }
    )
    seed.update(
        {
            "seed_id": str(uuid.uuid4()),
            "sourcing_run_id": run_id,
            "asin": item.get("asin"),
            "seller_sku": item.get("seller_sku"),
            "amazon_title": item.get("amazon_title"),
            "amazon_image_url": item.get("amazon_image_url"),
            "source_mode": item.get("priority_bucket"),
            "coverage_cycle_id": coverage_cycle_id,
            "coverage_cycle_item_id": item.get("cycle_item_id"),
            "queue_position": item.get("queue_position"),
            "priority_bucket": item.get("priority_bucket"),
            "raw_context_json": raw_context,
        }
    )
    return seed


def refresh_cycle_metrics(supabase, cycle_id: str, *, run_id: str | None = None, stop_reason: str | None = None) -> dict[str, Any]:
    rows = paginate_cycle_items(supabase, cycle_id)
    total = len(rows)
    searched = len([row for row in rows if row.get("processing_status") == "searched"])
    failed = len([row for row in rows if row.get("processing_status") == "retryable_failed"])
    remaining = len([row for row in rows if row.get("processing_status") in {"pending", "retryable_failed", "paused"}])
    browse_calls = sum(int_value(row.get("browse_calls_used")) for row in rows)
    candidates = sum(int_value(row.get("candidate_count")) for row in rows)
    opportunities = sum(int_value(row.get("qualifying_opportunity_count")) for row in rows)
    counts = {
        PRIORITY_RECENTLY_SOLD: len([row for row in rows if row.get("priority_bucket") == PRIORITY_RECENTLY_SOLD]),
        PRIORITY_PURCHASED_NOT_SENT: len([row for row in rows if row.get("priority_bucket") == PRIORITY_PURCHASED_NOT_SENT]),
        PRIORITY_CATALOG_REMAINING: len([row for row in rows if row.get("priority_bucket") == PRIORITY_CATALOG_REMAINING]),
    }
    completion = round((searched / total) * 100, 2) if total else 0
    update = {
        "total_eligible_asins": total,
        "priority_1_count": counts[PRIORITY_RECENTLY_SOLD],
        "priority_2_count": counts[PRIORITY_PURCHASED_NOT_SENT],
        "priority_3_count": counts[PRIORITY_CATALOG_REMAINING],
        "searched_count": searched,
        "remaining_count": remaining,
        "failed_count": failed,
        "total_browse_calls": browse_calls,
        "total_candidates_found": candidates,
        "total_qualifying_opportunities": opportunities,
        "completion_percentage": completion,
        "updated_at": now_iso(),
    }
    if run_id:
        update["last_run_id"] = run_id
    if stop_reason:
        update["last_stop_reason"] = stop_reason
    if remaining == 0 and total > 0:
        update["status"] = "completed"
        update["completed_at"] = now_iso()
    supabase.table("sourcing_coverage_cycles").update(update).eq("coverage_cycle_id", cycle_id).execute()
    return update


def int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def paginate_cycle_items(supabase, cycle_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        response = (
            supabase.table("sourcing_coverage_cycle_items")
            .select("*")
            .eq("coverage_cycle_id", cycle_id)
            .range(start, start + 999)
            .execute()
        )
        batch = response.data or []
        rows.extend(batch)
        if len(batch) < 1000:
            return rows
        start += 1000


def sort_date_for_seed(seed: dict[str, Any], priority_bucket: str) -> str | None:
    if priority_bucket == PRIORITY_PURCHASED_NOT_SENT:
        raw_context = seed.get("raw_context_json") or {}
        if isinstance(raw_context, dict):
            return raw_context.get("last_purchased_at")
    return seed.get("last_sold_at")


def eligibility_reason(priority_bucket: str) -> str:
    return {
        PRIORITY_RECENTLY_SOLD: "sold_in_last_90_days",
        PRIORITY_PURCHASED_NOT_SENT: "purchased_not_sent_to_amazon",
        PRIORITY_CATALOG_REMAINING: "catalog_remaining",
    }.get(priority_bucket, "eligible")


def purchase_order_date(row: dict[str, Any]) -> str | None:
    purchase = row.get("purchases")
    if isinstance(purchase, dict) and purchase.get("order_date"):
        return str(purchase.get("order_date"))
    return str(row.get("created_at") or "") or None


def purchase_state(item: dict[str, Any], fba_links: list[dict[str, Any]]) -> str:
    status = clean_status(item.get("current_status"))
    if status == "received":
        return "received_at_home_not_sent"
    if fba_links:
        return "staged_not_shipped"
    if status in {"delivered", "in_transit", "awaiting_carrier_scan", "shipped_no_tracking", "no_tracking"}:
        return "purchased_not_received"
    return status or "purchased"


def clean_status(value: Any) -> str:
    return str(value or "").strip().lower()


def clean_asin(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in {"", "N/A", "NA", "NONE", "NULL"}:
        return ""
    return text


def parse_datetime(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC)


def invert_date_text(value: str) -> str:
    if not value:
        return "9999"
    try:
        parsed = parse_datetime(value)
    except ValueError:
        return "9999"
    inverted = dt.datetime.max.replace(tzinfo=dt.UTC) - parsed
    return f"{int(inverted.total_seconds()):020d}"


def now_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat()
