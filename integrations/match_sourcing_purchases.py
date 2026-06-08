"""Match purchased sourcing opportunities to imported eBay buyer purchases."""

from __future__ import annotations

import argparse
import datetime as dt
import re
from typing import Any

from sourcing_common import get_supabase_client, paginate_table


ITEM_ID_RE = re.compile(r"(?:/itm/|[?&]item=)?(\d{9,15})(?:\D|$)")


def main() -> int:
    args = parse_args()
    supabase = get_supabase_client()
    opportunities = fetch_purchased_opportunities(supabase, args.limit)
    keepa_prices_by_asin = fetch_keepa_prices_by_asin(supabase, [row.get("asin") for row in opportunities])
    purchase_index = build_purchase_index(supabase)
    purchased_action_at_by_opportunity = latest_purchased_action_at_by_opportunity(supabase, opportunities)
    matched = 0
    skipped = 0
    enriched_existing = 0
    moved_to_watch = 0

    for opportunity in opportunities:
        item_ids = candidate_item_ids(opportunity)
        match = first_match(item_ids, purchase_index)
        if not match:
            if should_move_unmatched_to_watch(
                opportunity,
                purchased_action_at_by_opportunity,
                args.pending_expire_hours,
            ):
                if args.dry_run:
                    print_expired(opportunity, dry_run=True)
                else:
                    move_unmatched_to_watch(supabase, opportunity, args.pending_expire_hours)
                    print_expired(opportunity, dry_run=False)
                moved_to_watch += 1
            else:
                skipped += 1
            continue

        if existing_match(supabase, opportunity["opportunity_id"]):
            sell_price = matched_purchase_sell_price(opportunity, keepa_prices_by_asin)
            if not args.dry_run:
                update_matched_purchase_item(supabase, opportunity, match, sell_price)
            print_match(opportunity, match, dry_run=args.dry_run, sell_price=sell_price)
            enriched_existing += 1
            continue

        if not args.dry_run:
            sell_price = matched_purchase_sell_price(opportunity, keepa_prices_by_asin)
            supabase.table("sourcing_purchase_matches").insert(
                {
                    "opportunity_id": opportunity["opportunity_id"],
                    "ebay_item_id": match["matched_item_id"],
                    "purchase_id": match["purchase_id"],
                    "purchase_item_id": match["item_id"],
                    "match_method": match["match_method"],
                    "match_confidence": 1.0,
                    "review_required": False,
                    "review_status": "not_required",
                }
            ).execute()
            update_matched_purchase_item(supabase, opportunity, match, sell_price)
            supabase.table("sourcing_opportunities").update(
                {
                    "status": "matched_to_purchase",
                    "updated_at": dt.datetime.now(dt.UTC).isoformat(),
                }
            ).eq(
                "opportunity_id",
                opportunity["opportunity_id"],
            ).execute()
        print_match(
            opportunity,
            match,
            dry_run=args.dry_run,
            sell_price=matched_purchase_sell_price(opportunity, keepa_prices_by_asin),
        )
        matched += 1

    print("Sourcing purchase matching")
    print("-------------------------")
    print(f"Purchased opportunities checked: {len(opportunities)}")
    print(f"Matched: {matched}")
    print(f"Existing matches enriched: {enriched_existing}")
    print(f"Moved to watch after {args.pending_expire_hours}h unmatched: {moved_to_watch}")
    print(f"Skipped: {skipped}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Match sourcing purchased-pending rows to eBay purchases.")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--pending-expire-hours", type=float, default=72)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def fetch_purchased_opportunities(supabase, limit: int) -> list[dict[str, Any]]:
    response = (
        supabase.table("sourcing_opportunities")
        .select(
            "opportunity_id,asin,ebay_item_id,status,"
            "candidate_id,"
            "sourcing_seed_asins(amazon_title,target_sale_price,last_sold_at),"
            "sourcing_ebay_candidates(ebay_item_id,ebay_legacy_item_id,ebay_title)"
        )
        .eq("status", "purchased_pending_match")
        .limit(limit)
        .execute()
    )
    return response.data or []


def fetch_keepa_prices_by_asin(supabase, asins: list[Any]) -> dict[str, dict[str, float | None]]:
    unique_asins = sorted({str(asin or "").upper() for asin in asins if asin})
    by_asin: dict[str, dict[str, float | None]] = {}
    for batch in chunks(unique_asins, 100):
        response = (
            supabase.table("vw_latest_keepa_product_snapshot")
            .select("asin,buy_box_price_current_cents,buy_box_price_avg90_cents,raw_keepa_json")
            .in_("asin", batch)
            .execute()
        )
        for row in response.data or []:
            asin = str(row.get("asin") or "").upper()
            if not asin:
                continue
            by_asin[asin] = {
                "keepa_90": cents_to_dollars(row.get("buy_box_price_avg90_cents"))
                or keepa_stats_cents_to_dollars(row.get("raw_keepa_json"), "avg90", 1),
                "current_buy_box": cents_to_dollars(row.get("buy_box_price_current_cents")),
            }
    return by_asin


def latest_purchased_action_at_by_opportunity(
    supabase,
    opportunities: list[dict[str, Any]],
) -> dict[str, dt.datetime]:
    opportunity_ids = [row["opportunity_id"] for row in opportunities if row.get("opportunity_id")]
    latest_by_id: dict[str, dt.datetime] = {}
    for batch in chunks(opportunity_ids, 100):
        response = (
            supabase.table("sourcing_actions")
            .select("opportunity_id,created_at")
            .in_("opportunity_id", batch)
            .eq("action_type", "purchased")
            .execute()
        )
        for row in response.data or []:
            opportunity_id = row.get("opportunity_id")
            created_at = parse_datetime(row.get("created_at"))
            if not opportunity_id or created_at is None:
                continue
            if opportunity_id not in latest_by_id or created_at > latest_by_id[opportunity_id]:
                latest_by_id[opportunity_id] = created_at
    return latest_by_id


def build_purchase_index(supabase) -> dict[str, dict[str, Any]]:
    purchases = paginate_table(
        supabase,
        "purchases",
        "purchase_id,supplier,supplier_order_id,order_date,"
        "purchase_items(item_id,title,supplier_listing_url,raw_import_json,unit_cost,asin)",
        max_rows=20000,
        order_column="order_date",
        desc=True,
    )
    index: dict[str, dict[str, Any]] = {}
    for purchase in purchases:
        if str(purchase.get("supplier") or "").lower() != "ebay":
            continue
        for item in purchase.get("purchase_items") or []:
            for item_id in purchase_item_ids(item):
                index[item_id] = {
                    **item,
                    "purchase_id": purchase.get("purchase_id"),
                    "supplier_order_id": purchase.get("supplier_order_id"),
                    "matched_item_id": item_id,
                    "match_method": "legacy_item_id",
                }
    return index


def purchase_item_ids(item: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    url = str(item.get("supplier_listing_url") or "")
    ids.update(extract_item_ids(url))
    raw = item.get("raw_import_json") or {}
    if isinstance(raw, dict):
        for key in ("ItemID", "Item ID", "eBay Item ID", "itemId", "item_id"):
            value = raw.get(key)
            if value:
                ids.update(extract_item_ids(str(value)))
    return ids


def candidate_item_ids(opportunity: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    ids.update(extract_item_ids(str(opportunity.get("ebay_item_id") or "")))
    candidate = opportunity.get("sourcing_ebay_candidates") or {}
    ids.update(extract_item_ids(str(candidate.get("ebay_item_id") or "")))
    ids.update(extract_item_ids(str(candidate.get("ebay_legacy_item_id") or "")))
    return ids


def extract_item_ids(value: str) -> set[str]:
    ids = set(re.findall(r"\b\d{9,15}\b", value or ""))
    for match in ITEM_ID_RE.finditer(value or ""):
        ids.add(match.group(1))
    return ids


def first_match(item_ids: set[str], purchase_index: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    for item_id in sorted(item_ids):
        if item_id in purchase_index:
            return purchase_index[item_id]
    return None


def existing_match(supabase, opportunity_id: str) -> bool:
    response = (
        supabase.table("sourcing_purchase_matches")
        .select("match_id")
        .eq("opportunity_id", opportunity_id)
        .limit(1)
        .execute()
    )
    return bool(response.data)


def update_matched_purchase_item(
    supabase,
    opportunity: dict[str, Any],
    match: dict[str, Any],
    sell_price: float | None,
) -> None:
    seed = opportunity.get("sourcing_seed_asins") or {}
    payload: dict[str, Any] = {
        "asin": opportunity.get("asin"),
        "amazon_title": seed.get("amazon_title"),
    }
    if sell_price is not None:
        payload["target_price"] = sell_price
    payload = {key: value for key, value in payload.items() if value is not None and value != ""}
    if not payload:
        return
    supabase.table("purchase_items").update(payload).eq("item_id", match["item_id"]).execute()


def matched_purchase_sell_price(
    opportunity: dict[str, Any],
    keepa_prices_by_asin: dict[str, dict[str, float | None]],
) -> float | None:
    asin = str(opportunity.get("asin") or "").upper()
    seed = opportunity.get("sourcing_seed_asins") or {}
    keepa = keepa_prices_by_asin.get(asin) or {}
    prices = []
    if seed.get("last_sold_at"):
        prices.append(to_money(seed.get("target_sale_price")))
    prices.append(keepa.get("keepa_90"))
    prices.append(keepa.get("current_buy_box"))
    valid_prices = [price for price in prices if isinstance(price, (int, float)) and price > 0]
    return round(max(valid_prices), 2) if valid_prices else None


def should_move_unmatched_to_watch(
    opportunity: dict[str, Any],
    purchased_action_at_by_opportunity: dict[str, dt.datetime],
    pending_expire_hours: float,
) -> bool:
    purchased_at = purchased_action_at_by_opportunity.get(opportunity.get("opportunity_id"))
    if purchased_at is None:
        return False
    cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(hours=pending_expire_hours)
    return purchased_at <= cutoff


def move_unmatched_to_watch(supabase, opportunity: dict[str, Any], pending_expire_hours: float) -> None:
    now = dt.datetime.now(dt.UTC).isoformat()
    notes = (
        "No matching eBay purchase found within "
        f"{pending_expire_hours:g} hours; moved back to watch."
    )
    supabase.table("sourcing_actions").insert(
        {
            "opportunity_id": opportunity["opportunity_id"],
            "candidate_id": opportunity.get("candidate_id"),
            "asin": opportunity.get("asin"),
            "ebay_item_id": opportunity.get("ebay_item_id"),
            "action_type": "watching",
            "notes": notes,
        }
    ).execute()
    supabase.table("sourcing_opportunities").update(
        {
            "status": "watching",
            "updated_at": now,
        }
    ).eq("opportunity_id", opportunity["opportunity_id"]).execute()


def parse_datetime(value: Any) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC)


def chunks(rows: list[str], size: int) -> list[list[str]]:
    return [rows[index : index + size] for index in range(0, len(rows), size)]


def cents_to_dollars(value: Any) -> float | None:
    money = to_money(value)
    return round(money / 100, 2) if money is not None and money >= 0 else None


def keepa_stats_cents_to_dollars(raw_keepa: Any, stats_key: str, index: int) -> float | None:
    if not isinstance(raw_keepa, dict):
        return None
    stats = raw_keepa.get("stats")
    if not isinstance(stats, dict):
        return None
    values = stats.get(stats_key)
    if not isinstance(values, list) or len(values) <= index:
        return None
    return cents_to_dollars(values[index])


def to_money(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def print_match(opportunity: dict[str, Any], match: dict[str, Any], *, dry_run: bool, sell_price: float | None) -> None:
    prefix = "DRY RUN" if dry_run else "MATCHED"
    print(
        f"{prefix}: {opportunity.get('opportunity_id')} -> "
        f"{match.get('supplier_order_id')} / {match.get('item_id')} "
        f"({match.get('matched_item_id')}); sell price {sell_price if sell_price is not None else '--'}"
    )


def print_expired(opportunity: dict[str, Any], *, dry_run: bool) -> None:
    prefix = "DRY RUN WATCH" if dry_run else "MOVED TO WATCH"
    candidate = opportunity.get("sourcing_ebay_candidates") or {}
    print(
        f"{prefix}: {opportunity.get('opportunity_id')} / "
        f"{candidate.get('ebay_legacy_item_id') or opportunity.get('ebay_item_id')}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
