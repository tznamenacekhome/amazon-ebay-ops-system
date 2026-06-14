"""Fill missing purchase item Amazon titles from Keepa catalog data.

This is a narrow repair/sync helper for rows where MBOP already has a reviewed
ASIN but purchase_items.amazon_title is blank. It uses existing Keepa snapshots
first, then optionally makes a small no-history Keepa product request for the
remaining ASINs. It does not change ASINs, prices, costs, statuses, or workflow
state.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
from typing import Any

from dotenv import load_dotenv
from supabase import create_client

from keepa_client import KeepaAPIError, KeepaClient
from keepa_sync_products import build_snapshot_row, insert_keepa_rows


LOGGER = logging.getLogger("keepa_title_backfill")
EXCLUDED_DEFAULT_STATUSES = {"listed", "cancelled", "return_opened", "return_pending"}


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    load_dotenv()

    try:
        supabase = get_supabase_client()
        rows = fetch_missing_title_rows(supabase, include_listed=args.include_listed)
        selected_rows = rows[: args.limit]
        asins = sorted({clean_asin(row.get("asin")) for row in selected_rows if clean_asin(row.get("asin"))})
        title_by_asin = fetch_keepa_titles(supabase, asins)

        missing_asins = [asin for asin in asins if asin not in title_by_asin]
        if args.fetch_missing and args.apply and missing_asins:
            title_by_asin.update(fetch_and_store_keepa_titles(supabase, missing_asins, args))
        elif args.fetch_missing and missing_asins:
            LOGGER.info(
                "Dry run: %s selected ASIN(s) do not have local Keepa snapshots; rerun with --apply to fetch.",
                len(missing_asins),
            )

        planned_updates = [
            {
                "item_id": row["item_id"],
                "asin": clean_asin(row.get("asin")),
                "amazon_title": title_by_asin[clean_asin(row.get("asin"))],
                "supplier_order_id": row.get("supplier_order_id"),
            }
            for row in selected_rows
            if clean_asin(row.get("asin")) in title_by_asin
        ]

        if args.apply:
            for update in planned_updates:
                supabase.table("purchase_items").update({"amazon_title": update["amazon_title"]}).eq(
                    "item_id",
                    update["item_id"],
                ).execute()

        print("Keepa Amazon title backfill")
        print("--------------------------")
        print("Mode:", "write" if args.apply else "dry run")
        print(f"Candidate rows: {len(rows)}")
        print(f"Selected rows: {len(selected_rows)}")
        print(f"Unique ASINs selected: {len(asins)}")
        print(f"Titles from existing Keepa snapshots/API: {len(title_by_asin)}")
        print(f"Rows {'updated' if args.apply else 'planned'}: {len(planned_updates)}")
        for update in planned_updates[:20]:
            print(f"- {update['supplier_order_id'] or '--'} {update['asin']}: {update['amazon_title']}")
        if len(planned_updates) > 20:
            print(f"... {len(planned_updates) - 20} more")
        return 0
    except KeepaAPIError as error:
        LOGGER.error("Keepa title backfill failed safely: %s", error)
        return 1
    except Exception as error:  # noqa: BLE001 - integration should fail safely
        LOGGER.exception("Unexpected Keepa title backfill failure: %s", error)
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fill missing purchase Amazon titles from Keepa.")
    parser.add_argument("--apply", action="store_true", help="Write amazon_title updates.")
    parser.add_argument("--fetch-missing", action="store_true", help="Call Keepa for ASINs without a local snapshot.")
    parser.add_argument("--include-listed", action="store_true", help="Also process listed/history rows.")
    parser.add_argument("--limit", type=int, default=25, help="Maximum candidate rows to process.")
    parser.add_argument("--min-tokens", type=int, default=25, help="Skip Keepa calls below this token floor.")
    parser.add_argument("--stats-days", type=int, default=90)
    return parser.parse_args()


def get_supabase_client():
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY.")
    return create_client(supabase_url, supabase_key)


def fetch_missing_title_rows(supabase, *, include_listed: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    page_size = 1000
    while True:
        response = (
            supabase.table("purchase_items")
            .select("item_id,purchase_id,asin,amazon_title,title,system,current_status")
            .not_.is_("asin", "null")
            .neq("asin", "N/A")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        data = response.data or []
        for row in data:
            if row.get("amazon_title"):
                continue
            if not include_listed and clean_status(row.get("current_status")) in EXCLUDED_DEFAULT_STATUSES:
                continue
            rows.append(row)
        if len(data) < page_size:
            hydrate_supplier_order_ids(supabase, rows)
            return rows
        offset += page_size


def hydrate_supplier_order_ids(supabase, rows: list[dict[str, Any]]) -> None:
    purchase_ids = sorted({row.get("purchase_id") for row in rows if row.get("purchase_id")})
    if not purchase_ids:
        return

    order_id_by_purchase_id: dict[str, str] = {}
    for chunk in chunks(purchase_ids, 200):
        response = (
            supabase.table("purchases")
            .select("purchase_id,supplier_order_id")
            .in_("purchase_id", chunk)
            .execute()
        )
        for purchase in response.data or []:
            purchase_id = clean_text(purchase.get("purchase_id"))
            supplier_order_id = clean_text(purchase.get("supplier_order_id"))
            if purchase_id and supplier_order_id:
                order_id_by_purchase_id[purchase_id] = supplier_order_id

    for row in rows:
        purchase_id = clean_text(row.get("purchase_id"))
        row["supplier_order_id"] = order_id_by_purchase_id.get(purchase_id)


def fetch_keepa_titles(supabase, asins: list[str]) -> dict[str, str]:
    title_by_asin: dict[str, str] = {}
    for chunk in chunks(asins, 200):
        response = (
            supabase.table("vw_latest_keepa_product_snapshot")
            .select("asin,title")
            .in_("asin", chunk)
            .execute()
        )
        for row in response.data or []:
            asin = clean_asin(row.get("asin"))
            title = clean_text(row.get("title"))
            if asin and title:
                title_by_asin[asin] = title
    return title_by_asin


def fetch_and_store_keepa_titles(supabase, asins: list[str], args: argparse.Namespace) -> dict[str, str]:
    client = KeepaClient.from_env()
    token_status = client.get_token_status()
    tokens_left = to_int(token_status.get("tokens_left"), default=0)
    if tokens_left < args.min_tokens:
        LOGGER.warning("Skipping Keepa title fetch because tokens_left=%s < min_tokens=%s.", tokens_left, args.min_tokens)
        return {}

    captured_at = dt.datetime.now(dt.timezone.utc).isoformat()
    title_by_asin: dict[str, str] = {}
    snapshot_rows: list[dict[str, Any]] = []
    payload = client.get_products(asins[:100], stats_days=args.stats_days, history=False)
    token_status_after = {
        "token_cost": payload.get("tokensConsumed"),
        "tokens_left": payload.get("tokensLeft"),
    }
    for product in payload.get("products") or []:
        asin = clean_asin(product.get("asin"))
        title = clean_text(product.get("title"))
        if not asin:
            continue
        snapshot_rows.append(
            build_snapshot_row(
                product=product,
                captured_at=captured_at,
                domain_id=client.config.domain_id,
                token_cost=to_int(token_status_after.get("token_cost"), default=None),
                tokens_left=to_int(token_status_after.get("tokens_left"), default=None),
            )
        )
        if title:
            title_by_asin[asin] = title

    insert_keepa_rows(
        supabase,
        snapshot_rows,
        build_history=False,
        domain_id=client.config.domain_id,
        max_points_per_metric=0,
    )
    return title_by_asin


def chunks(values: list[str], size: int):
    for index in range(0, len(values), size):
        yield values[index : index + size]


def clean_asin(value: Any) -> str | None:
    text = clean_text(value)
    return text.upper() if text else None


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def clean_status(value: Any) -> str:
    return str(value or "").strip().lower()


def to_int(value: Any, default: int | None = 0) -> int | None:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


if __name__ == "__main__":
    raise SystemExit(main())
