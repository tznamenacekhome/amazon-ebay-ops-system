"""Sync read-only Keepa product snapshots into MBOP.

Default behavior is a dry run. Use --write to insert snapshots.

Keepa data is catalog intelligence for price history, sales rank, sales-rank
drop frequency, offers, reviews, and rating. It must remain separate from
purchases, purchase_items, and Amazon seller workflow ownership.
"""

from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from supabase import create_client

from keepa_client import KeepaAPIError, KeepaClient

LOGGER = logging.getLogger("keepa_product_sync")
BATCH_SIZE = 500
KEEPA_EPOCH_SECONDS = 1293840000

CSV_AMAZON = 0
CSV_NEW = 1
CSV_USED = 2
CSV_SALES_RANK = 3
CSV_NEW_FBA = 10
CSV_COUNT_NEW = 11
CSV_RATING = 16
CSV_COUNT_REVIEWS = 17
CSV_BUY_BOX = 18

HISTORY_METRICS = {
    CSV_AMAZON: "amazon_price",
    CSV_NEW: "new_price",
    CSV_USED: "used_price",
    CSV_SALES_RANK: "sales_rank",
    CSV_NEW_FBA: "new_fba_price",
    CSV_COUNT_NEW: "offer_count",
    CSV_RATING: "rating",
    CSV_COUNT_REVIEWS: "review_count",
    CSV_BUY_BOX: "buy_box_price",
}


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    load_dotenv()

    try:
        client = KeepaClient.from_env()
        supabase = get_supabase_client()
        captured_at = utc_now_iso()
        asins = collect_source_asins(supabase, source=args.source)
        if args.asin:
            asins = sorted(set(asins) | {asin.strip().upper() for asin in args.asin if asin.strip()})
        if args.limit is not None:
            asins = asins[: args.limit]

        LOGGER.info("Keepa ASINs selected: %s source=%s", len(asins), args.source)
        if not asins:
            LOGGER.info("No ASINs selected. Nothing to do.")
            return 0

        token_status_before = client.get_token_status()
        LOGGER.info(
            "Keepa tokens before sync: tokens_left=%s refill_in_ms=%s refill_rate=%s",
            token_status_before.get("tokens_left"),
            token_status_before.get("refill_in"),
            token_status_before.get("refill_rate"),
        )

        if args.plan_only:
            print_plan_summary(asins, token_status_before)
            LOGGER.info("Plan-only mode complete. No Keepa product call made.")
            return 0

        snapshot_rows: list[dict[str, Any]] = []
        history_rows: list[dict[str, Any]] = []
        rows_read = 0
        missing_products = 0
        failures = 0

        for chunk in chunks(asins, args.batch_size):
            try:
                payload = client.get_products(
                    chunk,
                    stats_days=args.stats_days,
                    history=not args.no_history,
                    offers=args.offers,
                    rating=True,
                    wait=True,
                )
            except KeepaAPIError as error:
                failures += len(chunk)
                LOGGER.warning("Keepa product batch failed for %s ASINs: %s", len(chunk), error)
                continue

            products = payload.get("products") or []
            rows_read += len(products)
            seen_asins = {clean_asin(product.get("asin")) for product in products}
            missing_products += len([asin for asin in chunk if clean_asin(asin) not in seen_asins])

            for product in products:
                snapshot = build_snapshot_row(
                    product=product,
                    captured_at=captured_at,
                    domain_id=client.config.domain_id,
                    token_cost=to_int(payload.get("tokenFlowReduction"), default=None),
                    tokens_left=to_int(payload.get("tokensLeft"), default=None),
                )
                snapshot_rows.append(snapshot)
                history_rows.extend(
                    build_history_rows(
                        product=product,
                        snapshot_id_placeholder=None,
                        domain_id=client.config.domain_id,
                        max_points_per_metric=args.max_history_points,
                    )
                )

            LOGGER.info(
                "Keepa batch complete: requested=%s returned=%s tokens_left=%s",
                len(chunk),
                len(products),
                payload.get("tokensLeft"),
            )

        print_summary(
            write=args.write,
            selected=len(asins),
            rows_read=rows_read,
            snapshots=len(snapshot_rows),
            history_points=len(history_rows),
            missing_products=missing_products,
            failures=failures,
            token_status_before=token_status_before,
        )

        if not args.write:
            LOGGER.info("Dry run complete. Use --write to insert Keepa snapshots.")
            return 0

        inserted_snapshots, inserted_history = insert_keepa_rows(
            supabase,
            snapshot_rows,
            build_history=args.write_history and not args.no_history,
            domain_id=client.config.domain_id,
            max_points_per_metric=args.max_history_points,
        )
        LOGGER.info("Keepa product sync complete.")
        LOGGER.info("Product snapshots inserted: %s", inserted_snapshots)
        LOGGER.info("History points inserted: %s", inserted_history)
        LOGGER.info("Failures: %s", failures)
        return 0
    except KeepaAPIError as error:
        LOGGER.error("Keepa sync failed safely: %s", error)
        return 1
    except Exception as error:  # noqa: BLE001 - top-level integration guard
        LOGGER.exception("Unexpected Keepa sync failure: %s", error)
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync Keepa product snapshots into MBOP.")
    parser.add_argument(
        "--write",
        action="store_true",
        help="Insert Keepa product snapshots. Default is dry-run only.",
    )
    parser.add_argument(
        "--source",
        choices=["canonical", "amazon_active", "purchase_pre_listed"],
        default="canonical",
        help="ASIN source. canonical = current Amazon FBA plus pre-Listed MBOP purchase inventory.",
    )
    parser.add_argument("--asin", action="append", default=[], help="Additional ASIN to include.")
    parser.add_argument("--limit", type=int, default=None, help="Limit selected ASINs.")
    parser.add_argument("--batch-size", type=int, default=50, help="Keepa ASINs per product request.")
    parser.add_argument("--stats-days", type=int, default=90, help="Keepa stats window in days.")
    parser.add_argument("--offers", type=int, default=None, help="Optional Keepa offers parameter.")
    parser.add_argument("--no-history", action="store_true", help="Do not request Keepa history arrays.")
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Count selected ASINs and token status without calling the Keepa product endpoint.",
    )
    parser.add_argument(
        "--write-history",
        action="store_true",
        help="Also write normalized history points. Raw history is always preserved on the product snapshot.",
    )
    parser.add_argument(
        "--max-history-points",
        type=int,
        default=60,
        help="Maximum history points per metric when --write-history is used.",
    )
    return parser.parse_args()


def get_supabase_client():
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not supabase_url or not supabase_key:
        raise RuntimeError(
            "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY environment variable."
        )

    return create_client(supabase_url, supabase_key)


def collect_source_asins(supabase, *, source: str) -> list[str]:
    asins: set[str] = set()

    if source in {"canonical", "amazon_active"}:
        for row in fetch_all(
            supabase,
            "vw_latest_amazon_fba_inventory_snapshot",
            "asin,total_quantity,fulfillable_quantity,inbound_working_quantity,"
            "inbound_shipped_quantity,inbound_receiving_quantity,reserved_quantity,"
            "unfulfillable_quantity",
        ):
            asin = clean_asin(row.get("asin"))
            if asin and current_quantity(row) > 0:
                asins.add(asin)

    if source in {"canonical", "purchase_pre_listed"}:
        purchase_rows = fetch_all(
            supabase,
            "vw_purchases_dashboard",
            "item_id,asin,current_status",
        )
        excluded_item_ids = fetch_excluded_item_ids(supabase, purchase_rows)
        for row in purchase_rows:
            asin = clean_asin(row.get("asin"))
            status = clean_text(row.get("current_status"))
            if (
                asin
                and status not in {"listed", "cancelled", "return_opened", "return_pending"}
                and row.get("item_id") not in excluded_item_ids
            ):
                asins.add(asin)

    return sorted(asins)


def fetch_excluded_item_ids(
    supabase,
    purchase_rows: list[dict[str, Any]],
) -> set[str]:
    item_ids = sorted(
        {
            str(row.get("item_id"))
            for row in purchase_rows
            if row.get("item_id")
        }
    )
    excluded: set[str] = set()

    for chunk in chunks(item_ids, 100):
        response = (
            supabase.table("purchase_items")
            .select("item_id")
            .eq("exclude_from_purchase_reporting", True)
            .in_("item_id", chunk)
            .execute()
        )
        for row in response.data or []:
            if row.get("item_id"):
                excluded.add(str(row["item_id"]))

    return excluded


def fetch_all(supabase, table: str, select: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0

    while True:
        response = (
            supabase.table(table)
            .select(select)
            .range(offset, offset + BATCH_SIZE - 1)
            .execute()
        )
        data = response.data or []
        rows.extend(data)
        if len(data) < BATCH_SIZE:
            return rows
        offset += BATCH_SIZE


def build_snapshot_row(
    *,
    product: dict[str, Any],
    captured_at: str,
    domain_id: int,
    token_cost: int | None,
    tokens_left: int | None,
) -> dict[str, Any]:
    stats = product.get("stats") if isinstance(product.get("stats"), dict) else {}
    current = stats.get("current") if isinstance(stats.get("current"), list) else []
    avg30 = stats.get("avg30") if isinstance(stats.get("avg30"), list) else []
    avg90 = stats.get("avg90") if isinstance(stats.get("avg90"), list) else []
    avg180 = stats.get("avg180") if isinstance(stats.get("avg180"), list) else []

    return {
        "captured_at": captured_at,
        "domain_id": domain_id,
        "asin": clean_asin(product.get("asin")),
        "title": clean_text(product.get("title")),
        "brand": clean_text(product.get("brand")),
        "manufacturer": clean_text(product.get("manufacturer")),
        "product_group": clean_text(product.get("productGroup")),
        "root_category": to_int(product.get("rootCategory"), default=None),
        "category_tree_json": product.get("categoryTree"),
        "buy_box_price_current_cents": stat_value(current, CSV_BUY_BOX),
        "buy_box_price_avg30_cents": stat_value(avg30, CSV_BUY_BOX),
        "buy_box_price_avg90_cents": stat_value(avg90, CSV_BUY_BOX),
        "amazon_price_current_cents": stat_value(current, CSV_AMAZON),
        "new_price_current_cents": stat_value(current, CSV_NEW),
        "new_fba_price_current_cents": stat_value(current, CSV_NEW_FBA),
        "used_price_current_cents": stat_value(current, CSV_USED),
        "sales_rank_current": stat_value(current, CSV_SALES_RANK),
        "sales_rank_avg30": stat_value(avg30, CSV_SALES_RANK),
        "sales_rank_avg90": stat_value(avg90, CSV_SALES_RANK),
        "sales_rank_avg180": stat_value(avg180, CSV_SALES_RANK),
        "sales_rank_drops30": to_int(stats.get("salesRankDrops30"), default=None),
        "sales_rank_drops90": to_int(stats.get("salesRankDrops90"), default=None),
        "sales_rank_drops180": to_int(stats.get("salesRankDrops180"), default=None),
        "offer_count_current": stat_value(current, CSV_COUNT_NEW),
        "review_count_current": stat_value(current, CSV_COUNT_REVIEWS),
        "rating_current": rating_value(stat_value(current, CSV_RATING)),
        "raw_keepa_json": product,
        "token_cost": token_cost,
        "tokens_left": tokens_left,
        "source": "keepa_product",
    }


def build_history_rows(
    *,
    product: dict[str, Any],
    snapshot_id_placeholder: str | None,
    domain_id: int,
    max_points_per_metric: int,
) -> list[dict[str, Any]]:
    asin = clean_asin(product.get("asin"))
    csv_rows = product.get("csv") if isinstance(product.get("csv"), list) else []
    if not asin:
        return []

    rows: list[dict[str, Any]] = []
    for index, metric_name in HISTORY_METRICS.items():
        if index >= len(csv_rows) or not isinstance(csv_rows[index], list):
            continue
        points = csv_rows[index]
        parsed = parse_keepa_history_points(points)
        for observed_at, metric_value in parsed[-max_points_per_metric:]:
            rows.append(
                {
                    "keepa_product_snapshot_id": snapshot_id_placeholder,
                    "domain_id": domain_id,
                    "asin": asin,
                    "metric_name": metric_name,
                    "observed_at": observed_at,
                    "metric_value": metric_value,
                }
            )
    return rows


def insert_keepa_rows(
    supabase,
    snapshot_rows: list[dict[str, Any]],
    *,
    build_history: bool,
    domain_id: int,
    max_points_per_metric: int,
) -> tuple[int, int]:
    inserted_snapshots = 0
    inserted_history = 0

    for row in snapshot_rows:
        response = supabase.table("keepa_product_snapshots").insert(row).execute()
        inserted = (response.data or [{}])[0]
        snapshot_id = inserted.get("keepa_product_snapshot_id")
        inserted_snapshots += 1

        if not build_history or not snapshot_id:
            continue
        history_rows = build_history_rows(
            product=row["raw_keepa_json"],
            snapshot_id_placeholder=snapshot_id,
            domain_id=domain_id,
            max_points_per_metric=max_points_per_metric,
        )
        for chunk in chunks(history_rows, BATCH_SIZE):
            supabase.table("keepa_product_history_points").insert(chunk).execute()
            inserted_history += len(chunk)

    return inserted_snapshots, inserted_history


def print_summary(
    *,
    write: bool,
    selected: int,
    rows_read: int,
    snapshots: int,
    history_points: int,
    missing_products: int,
    failures: int,
    token_status_before: dict[str, Any],
) -> None:
    print("Keepa product sync write" if write else "Keepa product sync dry run")
    print("---------------------------")
    print(f"ASINs selected: {selected}")
    print(f"Products returned: {rows_read}")
    print(f"Snapshot rows prepared: {snapshots}")
    print(f"History points parsed: {history_points}")
    print(f"Missing products: {missing_products}")
    print(f"Failures: {failures}")
    print(f"Tokens before: {token_status_before.get('tokens_left')}")


def print_plan_summary(asins: list[str], token_status_before: dict[str, Any]) -> None:
    print("Keepa product sync plan")
    print("-----------------------")
    print(f"ASINs selected: {len(asins)}")
    print(f"Tokens available: {token_status_before.get('tokens_left')}")
    print(f"Refill in ms: {token_status_before.get('refill_in')}")
    print(f"Refill rate: {token_status_before.get('refill_rate')}")


def current_quantity(row: dict[str, Any]) -> int:
    return sum(
        to_int(row.get(field), default=0) or 0
        for field in (
            "total_quantity",
            "fulfillable_quantity",
            "inbound_working_quantity",
            "inbound_shipped_quantity",
            "inbound_receiving_quantity",
            "reserved_quantity",
            "unfulfillable_quantity",
        )
    )


def parse_keepa_history_points(values: list[Any]) -> list[tuple[str, int | None]]:
    points: list[tuple[str, int | None]] = []
    for index in range(0, len(values) - 1, 2):
        keepa_minute = to_int(values[index], default=None)
        if keepa_minute is None:
            continue
        metric_value = normalized_metric_value(values[index + 1])
        observed_at = datetime.fromtimestamp(
            KEEPA_EPOCH_SECONDS + keepa_minute * 60,
            tz=timezone.utc,
        ).replace(microsecond=0)
        points.append((observed_at.isoformat().replace("+00:00", "Z"), metric_value))
    return points


def stat_value(values: list[Any], index: int) -> int | None:
    if index >= len(values):
        return None
    return normalized_metric_value(values[index])


def normalized_metric_value(value: Any) -> int | None:
    integer = to_int(value, default=None)
    if integer is None or integer < 0:
        return None
    return integer


def rating_value(value: int | None) -> float | None:
    if value is None:
        return None
    if value > 50:
        return round(value / 10, 2)
    return float(value)


def chunks(rows: list[Any], size: int):
    for index in range(0, len(rows), size):
        yield rows[index : index + size]


def clean_asin(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    text = text.upper()
    return text if len(text) == 10 else None


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def to_int(value: Any, default: int | None = 0) -> int | None:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


if __name__ == "__main__":
    raise SystemExit(main())
