"""Build sourcing seed ASINs from Amazon sales or active listing data."""

from __future__ import annotations

import argparse
import datetime as dt
import uuid
from collections import defaultdict
from typing import Any

from sourcing_common import chunked, fetch_settings, get_supabase_client, paginate_table, to_float
from system_detection import detect_system_from_title, normalize_system


def main() -> int:
    args = parse_args()
    supabase = get_supabase_client()
    settings = fetch_settings(supabase)
    run_id = args.run_id or str(uuid.uuid4())
    mode = args.mode

    create_run(supabase, run_id, mode, settings, dry_run=args.dry_run)
    seeds = build_recent_sales_seeds(supabase, settings, args.limit) if mode == "recent_sales" else build_full_listing_seeds(supabase, settings, args.limit)

    print("Sourcing seed ASIN build")
    print("-----------------------")
    print(f"Run ID: {run_id}")
    print(f"Mode: {mode}")
    print(f"Seeds: {len(seeds)}")

    if args.dry_run:
        for seed in seeds[:10]:
            print(f"{seed['asin']} | {seed['amazon_title']} | ${seed['target_sale_price']} | {seed['inventory_need_level']}")
        return 0

    if args.replace_run:
        supabase.table("sourcing_seed_asins").delete().eq("sourcing_run_id", run_id).execute()

    for batch in chunked([{**seed, "sourcing_run_id": run_id} for seed in seeds], 500):
        supabase.table("sourcing_seed_asins").insert(batch).execute()

    supabase.table("sourcing_runs").update(
        {
            "status": "running",
            "source_count": len(seeds),
            "settings_snapshot": settings.__dict__,
        }
    ).eq("sourcing_run_id", run_id).execute()
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create MBOP sourcing seed ASINs.")
    parser.add_argument("--mode", choices=["recent_sales", "full_listings"], default="recent_sales")
    parser.add_argument("--run-id", help="Optional existing sourcing_run_id.")
    parser.add_argument("--limit", type=int, default=250)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--replace-run", action="store_true", help="Delete existing seeds for the run before writing.")
    return parser.parse_args()


def create_run(supabase, run_id: str, mode: str, settings, *, dry_run: bool) -> None:
    if dry_run:
        return
    supabase.table("sourcing_runs").upsert(
        {
            "sourcing_run_id": run_id,
            "run_type": mode,
            "status": "running",
            "started_at": dt.datetime.now(dt.UTC).isoformat(),
            "settings_snapshot": settings.__dict__,
        },
        on_conflict="sourcing_run_id",
    ).execute()


def build_recent_sales_seeds(supabase, settings, limit: int) -> list[dict[str, Any]]:
    cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(days=settings.sales_lookback_days)
    orders = paginate_table(
        supabase,
        "amazon_sales_orders",
        "amazon_order_id,purchase_date,order_status",
        order_column="purchase_date",
        desc=True,
        max_rows=12000,
    )
    order_date_by_id = {
        row["amazon_order_id"]: row["purchase_date"]
        for row in orders
        if row.get("purchase_date") and str(row.get("purchase_date")) >= cutoff.isoformat()
    }
    profitability_rows = paginate_table(
        supabase,
        "amazon_sales_profitability",
        "amazon_order_id,asin,seller_sku,title,quantity,sale_price,amazon_fees_excluding_fulfillment,fulfillment_cost,data_status",
        max_rows=20000,
    )
    inventory_by_asin = latest_inventory_by_asin(supabase)
    planning_by_asin = latest_inventory_planning_by_asin(supabase)
    catalog_by_asin = latest_catalog_context_by_asin(supabase)

    by_asin: dict[str, dict[str, Any]] = {}
    cutoff_60 = dt.datetime.now(dt.UTC) - dt.timedelta(days=60)
    for row in profitability_rows:
        asin = str(row.get("asin") or "").upper()
        sold_at = order_date_by_id.get(str(row.get("amazon_order_id") or ""))
        quantity = int(to_float(row.get("quantity"), 0))
        sale_price = to_float(row.get("sale_price"), 0)
        unit_sale_price = round(sale_price / quantity, 2) if quantity > 0 else 0
        if not asin or not sold_at or quantity <= 0 or unit_sale_price < settings.min_amazon_price:
            continue
        current = by_asin.setdefault(
            asin,
            {
                "asin": asin,
                "amazon_title": row.get("title") or asin,
                "amazon_image_url": None,
                "seller_sku": row.get("seller_sku"),
                "units_sold_60d": 0,
                "units_sold_lookback": 0,
                "last_sold_at": sold_at,
                "target_sale_price": unit_sale_price,
                "fee_samples": [],
            },
        )
        current["units_sold_lookback"] += quantity
        if sold_at >= cutoff_60.isoformat():
            current["units_sold_60d"] += quantity
        if sold_at > current["last_sold_at"]:
            current["last_sold_at"] = sold_at
            current["target_sale_price"] = unit_sale_price
        fees = abs(to_float(row.get("amazon_fees_excluding_fulfillment"), 0)) + abs(to_float(row.get("fulfillment_cost"), 0))
        if fees > 0:
            current["fee_samples"].append(round(fees / quantity, 2))

    return finalize_seeds(by_asin.values(), inventory_by_asin, settings, limit, planning_by_asin, catalog_by_asin, supabase)


def build_full_listing_seeds(supabase, settings, limit: int) -> list[dict[str, Any]]:
    listing_rows = paginate_table(
        supabase,
        "vw_latest_amazon_listing_snapshot",
        "asin,seller_sku,product_name,listing_status,item_status,condition,issue_count,issue_severity",
        max_rows=10000,
    )
    keepa_rows = paginate_table(
        supabase,
        "vw_latest_keepa_product_snapshot",
        "asin,new_price_current_cents,buy_box_price_avg90_cents,buy_box_price_current_cents,title",
        max_rows=15000,
    )
    keepa_by_asin = {str(row.get("asin") or "").upper(): row for row in keepa_rows}
    inventory_by_asin = latest_inventory_by_asin(supabase)
    planning_by_asin = latest_inventory_planning_by_asin(supabase)
    catalog_by_asin = latest_catalog_context_by_asin(supabase)

    by_asin: dict[str, dict[str, Any]] = {}
    for row in listing_rows:
        asin = str(row.get("asin") or "").upper()
        if not asin:
            continue
        keepa = keepa_by_asin.get(asin, {})
        cents = (
            keepa.get("buy_box_price_avg90_cents")
            or keepa.get("buy_box_price_current_cents")
            or keepa.get("new_price_current_cents")
        )
        target_sale_price = to_float(cents, 0) / 100
        if target_sale_price < settings.min_amazon_price:
            continue
        by_asin[asin] = {
            "asin": asin,
            "amazon_title": row.get("product_name") or keepa.get("title") or asin,
            "amazon_image_url": None,
            "seller_sku": row.get("seller_sku"),
            "units_sold_lookback": 0,
            "last_sold_at": None,
            "target_sale_price": round(target_sale_price, 2),
            "units_sold_60d": 0,
            "fee_samples": [],
            "listing_warnings": {
                "issue_count": row.get("issue_count"),
                "issue_severity": row.get("issue_severity"),
                "listing_status": row.get("listing_status"),
            },
        }

    return finalize_seeds(by_asin.values(), inventory_by_asin, settings, limit, planning_by_asin, catalog_by_asin, supabase)


def latest_inventory_by_asin(supabase) -> dict[str, float]:
    rows = paginate_table(
        supabase,
        "vw_latest_amazon_fba_inventory_snapshot",
        "asin,fulfillable_quantity,total_quantity,reserved_customer_order_quantity,product_name",
        max_rows=15000,
    )
    inventory: dict[str, float] = defaultdict(float)
    for row in rows:
        asin = str(row.get("asin") or "").upper()
        if asin:
            inventory[asin] += to_float(row.get("fulfillable_quantity"), 0)
    return dict(inventory)


def amazon_images_for_asins(supabase, asins: list[str]) -> dict[str, str]:
    image_by_asin: dict[str, str] = {}
    unique_asins = sorted({asin.upper() for asin in asins if asin})
    for batch in chunked(unique_asins, 100):
        response = (
            supabase.table("vw_latest_amazon_listing_snapshot")
            .select("asin,raw_listing_json")
            .in_("asin", batch)
            .execute()
        )
        for row in response.data or []:
            asin = str(row.get("asin") or "").upper()
            if asin and (image_url := amazon_image_url(row)):
                image_by_asin[asin] = image_url

    missing = [asin for asin in unique_asins if asin not in image_by_asin]
    for batch in chunked(missing, 100):
        response = (
            supabase.table("vw_latest_keepa_product_snapshot")
            .select("asin,raw_keepa_json")
            .in_("asin", batch)
            .execute()
        )
        for row in response.data or []:
            asin = str(row.get("asin") or "").upper()
            if asin and asin not in image_by_asin and (image_url := keepa_image_url(row)):
                image_by_asin[asin] = image_url
    return image_by_asin


def amazon_image_url(row: dict[str, Any]) -> str | None:
    raw = row.get("raw_listing_json") or {}
    if not isinstance(raw, dict):
        return None
    summaries = raw.get("summaries") or []
    if not summaries:
        return None
    image = (summaries[0] or {}).get("mainImage") or {}
    return image.get("link")


def keepa_image_url(row: dict[str, Any]) -> str | None:
    raw = row.get("raw_keepa_json") or {}
    if not isinstance(raw, dict):
        return None
    images = raw.get("images")
    if isinstance(images, list):
        for image in images:
            if not isinstance(image, dict):
                continue
            image_name = image.get("l") or image.get("m") or image.get("s")
            if image_name:
                return f"https://images-na.ssl-images-amazon.com/images/I/{image_name}"
    images_csv = raw.get("imagesCSV")
    if not isinstance(images_csv, str) or not images_csv.strip():
        return None
    image_name = images_csv.split(",")[0].strip()
    if not image_name:
        return None
    return f"https://images-na.ssl-images-amazon.com/images/I/{image_name}"


def latest_inventory_planning_by_asin(supabase) -> dict[str, dict[str, Any]]:
    rows = paginate_table(
        supabase,
        "amazon_inventory_planning_snapshots",
        (
            "asin,snapshot_date,captured_at,available_quantity,sales_shipped_last_30_days,"
            "inv_age_0_to_90_days,inv_age_91_to_180_days,inv_age_181_to_270_days,"
            "inv_age_271_to_365_days,inv_age_365_plus_days,raw_planning_json"
        ),
        max_rows=20000,
        order_column="captured_at",
        desc=True,
    )
    by_asin: dict[str, dict[str, Any]] = {}
    for row in rows:
        asin = str(row.get("asin") or "").upper()
        if asin and asin not in by_asin:
            by_asin[asin] = row
    return by_asin


def latest_catalog_context_by_asin(supabase) -> dict[str, dict[str, Any]]:
    context: dict[str, dict[str, Any]] = {}
    listing_rows = paginate_table(
        supabase,
        "vw_latest_amazon_listing_snapshot",
        "asin,product_name",
        max_rows=15000,
    )
    for row in listing_rows:
        asin = str(row.get("asin") or "").upper()
        if not asin:
            continue
        context.setdefault(asin, {})["listing"] = row

    keepa_rows = paginate_table(
        supabase,
        "vw_latest_keepa_product_snapshot",
        "asin,title,product_group,category_tree_json",
        max_rows=15000,
    )
    for row in keepa_rows:
        asin = str(row.get("asin") or "").upper()
        if not asin:
            continue
        context.setdefault(asin, {})["keepa"] = row
    return context


def finalize_seeds(
    rows,
    inventory_by_asin: dict[str, float],
    settings,
    limit: int,
    planning_by_asin: dict[str, dict[str, Any]],
    catalog_by_asin: dict[str, dict[str, Any]],
    supabase,
) -> list[dict[str, Any]]:
    seeds = []
    stale_stock_skipped = 0
    for row in rows:
        velocity = to_float(row.get("units_sold_lookback"), 0) / max(settings.sales_lookback_days / 30, 1)
        inventory_units = inventory_by_asin.get(row["asin"], 0)
        planning = planning_by_asin.get(row["asin"]) or {}
        stale_stock = stale_in_stock_no_recent_sales(row["asin"], inventory_units, planning)
        if stale_stock["skip"]:
            stale_stock_skipped += 1
            continue

        months_supply = inventory_units / velocity if velocity > 0 else None
        need_level = inventory_need_level(months_supply, inventory_units, velocity)
        fee_samples = row.pop("fee_samples", [])
        units_sold_lookback = int(to_float(row.pop("units_sold_lookback", 0), 0))
        units_sold_60d = int(to_float(row.pop("units_sold_60d", 0), 0))
        listing_warnings = row.pop("listing_warnings", {})
        warning_flags = row.pop("warning_flags", [])
        estimated_fee_cost = round(sum(fee_samples) / len(fee_samples), 2) if fee_samples else None
        platform_context = infer_platform_context(row["asin"], row.get("amazon_title"), catalog_by_asin.get(row["asin"]) or {})
        seeds.append(
            {
                **row,
                "current_inventory_units": inventory_units,
                "monthly_velocity": round(velocity, 2),
                "months_of_supply": round(months_supply, 2) if months_supply is not None else None,
                "inventory_need_level": need_level,
                "seed_id": str(uuid.uuid4()),
                "source_mode": "recent_sales" if row.get("last_sold_at") else "full_listings",
                "target_sale_price_source": "most_recent_sale" if row.get("last_sold_at") else "keepa_new_90d_avg",
                "units_sold_60d": units_sold_60d,
                "units_sold_90d": units_sold_lookback,
                "is_restricted": False,
                "is_suppressed": False,
                "is_return_heavy": False,
                "warning_flags": warning_flags,
                "raw_context_json": {
                    "estimated_fee_cost": estimated_fee_cost,
                    "listing_warnings": listing_warnings,
                    "inferred_system": platform_context.get("system"),
                    "inferred_system_source": platform_context.get("source"),
                    "inventory_planning": stale_stock,
                },
            }
        )
    seeds = sorted(seeds, key=lambda item: need_sort(item["inventory_need_level"], item["monthly_velocity"]), reverse=True)[:limit]
    image_by_asin = amazon_images_for_asins(supabase, [seed["asin"] for seed in seeds])
    for seed in seeds:
        seed["amazon_image_url"] = image_by_asin.get(seed["asin"])
    if stale_stock_skipped:
        print(f"Skipped stale in-stock/no-30-day-sale ASINs: {stale_stock_skipped}")
    return seeds


def stale_in_stock_no_recent_sales(asin: str, inventory_units: float, planning: dict[str, Any]) -> dict[str, Any]:
    raw = planning.get("raw_planning_json") or {}
    aged_31_to_60 = raw_number(raw.get("inv-age-31-to-60-days"))
    aged_61_to_90 = raw_number(raw.get("inv-age-61-to-90-days"))
    aged_91_to_180 = to_float(planning.get("inv_age_91_to_180_days"), 0)
    aged_181_to_270 = to_float(planning.get("inv_age_181_to_270_days"), 0)
    aged_271_to_365 = to_float(planning.get("inv_age_271_to_365_days"), 0)
    aged_365_plus = to_float(planning.get("inv_age_365_plus_days"), 0)
    aged_over_30 = aged_31_to_60 + aged_61_to_90 + aged_91_to_180 + aged_181_to_270 + aged_271_to_365 + aged_365_plus
    sales_30 = to_float(planning.get("sales_shipped_last_30_days"), 0) or raw_number(raw.get("sales-shipped-last-30-days"))
    skip = inventory_units > 0 and aged_over_30 > 0 and sales_30 <= 0
    return {
        "asin": asin,
        "skip": skip,
        "current_inventory_units": inventory_units,
        "aged_units_over_30_days": aged_over_30,
        "sales_shipped_last_30_days": sales_30,
        "snapshot_date": planning.get("snapshot_date"),
    }


def infer_platform_context(asin: str, amazon_title: Any, context: dict[str, Any]) -> dict[str, str | None]:
    title_system = detect_system_from_title(str(amazon_title or ""))
    if title_system:
        return {"system": title_system, "source": "amazon_title"}

    listing = context.get("listing") or {}
    keepa = context.get("keepa") or {}
    candidates = [
        ("amazon_listing_product_name", listing.get("product_name")),
        ("keepa_title", keepa.get("title")),
        ("keepa_product_group", keepa.get("product_group")),
        ("keepa_category_tree", flatten_text(keepa.get("category_tree_json"))),
    ]
    for source, value in candidates:
        system = normalize_system(str(value or "")) or detect_system_from_title(str(value or ""))
        if system:
            return {"system": system, "source": source}
    return {"system": None, "source": None}


def flatten_text(value: Any) -> str:
    parts: list[str] = []
    collect_text(value, parts)
    return " ".join(parts)


def collect_text(value: Any, parts: list[str]) -> None:
    if value is None:
        return
    if isinstance(value, (str, int, float)):
        parts.append(str(value))
        return
    if isinstance(value, dict):
        for item in value.values():
            collect_text(item, parts)
        return
    if isinstance(value, list):
        for item in value:
            collect_text(item, parts)


def raw_number(value: Any) -> float:
    return to_float(value, 0)


def inventory_need_level(months_supply: float | None, inventory_units: float, velocity: float) -> str:
    if inventory_units <= 0:
        return "critical"
    if velocity <= 0:
        return "low"
    if months_supply is not None and months_supply < 1:
        return "critical"
    if months_supply is not None and months_supply < 2:
        return "high"
    if months_supply is not None and months_supply < 4:
        return "medium"
    return "low"


def need_sort(level: str, velocity: float) -> tuple[int, float]:
    return ({"critical": 4, "high": 3, "medium": 2, "low": 1}.get(level, 0), velocity)


if __name__ == "__main__":
    raise SystemExit(main())
