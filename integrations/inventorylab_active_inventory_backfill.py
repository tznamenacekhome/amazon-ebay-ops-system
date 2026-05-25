"""Dry-run and optional import for InventoryLab active inventory backfill.

This is a historical Amazon FBA inventory bridge. It stores InventoryLab cost
and date context separately and never overwrites MBOP purchase_items.
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from supabase import create_client

LOGGER = logging.getLogger("inventorylab_active_inventory_backfill")
DEFAULT_INPUT = Path("data/imports/inventorylab_fba_active_inventory_2026-0.csv")
BATCH_SIZE = 500


@dataclass
class InventoryLabRow:
    row_number: int
    raw: dict[str, str]
    title: str | None
    seller_sku: str | None
    asin: str | None
    fnsku: str | None
    on_hand_quantity: int | None
    total_in_stock_buy_cost: float | None
    active_cost_per_unit: float | None
    active_supplier: str | None
    active_date_purchased: str | None
    list_price: float | None
    condition: str | None


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    load_dotenv()

    try:
        rows = read_inventorylab_csv(args.input)
        supabase = get_supabase_client()
        amazon_skus = fetch_amazon_skus(supabase)
        existing_backfill = fetch_existing_backfill(supabase) if args.apply else {}
        analysis = analyze_rows(rows, amazon_skus, include_inactive=args.include_inactive)

        print_summary(analysis)
        if args.show_missing_cost_date:
            print_missing_cost_date_rows(analysis)

        if not args.apply:
            LOGGER.info("Dry run complete. No Supabase writes performed.")
            return 0

        upserts = build_backfill_rows(analysis, args.input, existing_backfill)
        for chunk in chunks(upserts, BATCH_SIZE):
            supabase.table("inventorylab_active_inventory_backfill").upsert(
                chunk,
                on_conflict="source_file,source_row_number",
            ).execute()

        LOGGER.info("Backfill rows upserted: %s", len(upserts))
        return 0
    except Exception as error:  # noqa: BLE001 - integration should fail safely
        LOGGER.exception("InventoryLab backfill failed safely: %s", error)
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze or import InventoryLab active inventory historical backfill."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="InventoryLab active inventory CSV path.",
    )
    parser.add_argument(
        "--include-inactive",
        action="store_true",
        help="Also consider rows with On Hand zero. Default only imports active On Hand rows.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write matched/review/unmatched rows to the legacy backfill table.",
    )
    parser.add_argument(
        "--show-missing-cost-date",
        action="store_true",
        help="Print rows missing Active Cost/Unit or Active Date Purchased.",
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


def read_inventorylab_csv(path: Path) -> list[InventoryLabRow]:
    if not path.exists():
        raise FileNotFoundError(path)

    rows: list[InventoryLabRow] = []
    with path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        for row_number, raw in enumerate(reader, start=2):
            rows.append(
                InventoryLabRow(
                    row_number=row_number,
                    raw={key: value for key, value in raw.items()},
                    title=clean_text(raw.get("Title")),
                    seller_sku=clean_text(raw.get("MSKU")),
                    asin=clean_asin(raw.get("ASIN")),
                    fnsku=clean_text(raw.get("FNSKU")),
                    on_hand_quantity=to_int(raw.get("On Hand")),
                    total_in_stock_buy_cost=to_money(raw.get("Total In Stock Buy Cost")),
                    active_cost_per_unit=to_money(raw.get("Active Cost/Unit")),
                    active_supplier=clean_text(raw.get("Active Supplier")),
                    active_date_purchased=parse_inventorylab_date(raw.get("Active Date Purchased")),
                    list_price=to_money(raw.get("List Price")),
                    condition=clean_text(raw.get("Condition")),
                )
            )
    return rows


def fetch_amazon_skus(supabase) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0

    while True:
        response = (
            supabase.table("amazon_skus")
            .select("amazon_sku_id,seller_sku,marketplace_id,asin,fnsku,product_name,condition")
            .range(offset, offset + BATCH_SIZE - 1)
            .execute()
        )
        data = response.data or []
        rows.extend(data)
        if len(data) < BATCH_SIZE:
            return rows
        offset += BATCH_SIZE


def fetch_existing_backfill(supabase) -> dict[tuple[str, int], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0

    while True:
        response = (
            supabase.table("inventorylab_active_inventory_backfill")
            .select("source_file,source_row_number,inventorylab_active_inventory_backfill_id")
            .range(offset, offset + BATCH_SIZE - 1)
            .execute()
        )
        data = response.data or []
        rows.extend(data)
        if len(data) < BATCH_SIZE:
            break
        offset += BATCH_SIZE

    return {
        (str(row["source_file"]), int(row["source_row_number"])): row
        for row in rows
    }


def analyze_rows(
    rows: list[InventoryLabRow],
    amazon_skus: list[dict[str, Any]],
    include_inactive: bool,
) -> dict[str, Any]:
    skus_by_seller_sku: dict[str, list[dict[str, Any]]] = defaultdict(list)
    skus_by_asin: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for sku in amazon_skus:
        seller_sku = clean_text(sku.get("seller_sku"))
        asin = clean_asin(sku.get("asin"))
        if seller_sku:
            skus_by_seller_sku[seller_sku].append(sku)
        if asin:
            skus_by_asin[asin].append(sku)

    analyzed = []
    counts = defaultdict(int)

    for row in rows:
        counts["rows_read"] += 1
        has_cost = row.active_cost_per_unit is not None and row.active_cost_per_unit > 0
        has_date = row.active_date_purchased is not None
        is_active = (row.on_hand_quantity or 0) > 0

        if not has_cost or not has_date:
            counts["rows_missing_cost_or_date"] += 1

        if not include_inactive and not is_active:
            status = "skipped"
            method = None
            match = None
            notes = "Skipped because On Hand is not greater than zero."
            counts["rows_skipped_inactive"] += 1
        else:
            if not has_cost or not has_date:
                counts["candidate_rows_missing_cost_or_date"] += 1
            status, method, match, notes = classify_match(
                row,
                skus_by_seller_sku,
                skus_by_asin,
            )
            counts[f"rows_{status}"] += 1
            if method == "seller_sku":
                counts["rows_matched_by_sku"] += 1
            if method == "asin_title_review":
                counts["rows_matched_by_asin_fallback"] += 1
            if status == "ambiguous":
                counts["rows_ambiguous"] += 1

        analyzed.append(
            {
                "row": row,
                "match_status": status,
                "match_method": method,
                "matched_amazon_sku": match,
                "requires_review": method == "asin_title_review" or status == "ambiguous",
                "has_cost": has_cost,
                "has_date": has_date,
                "would_insert_or_update": status in {"matched", "review_candidate", "unmatched", "ambiguous"},
                "notes": notes,
            }
        )

    counts["rows_would_insert_or_update"] = sum(
        1 for row in analyzed if row["would_insert_or_update"]
    )

    return {"rows": analyzed, "counts": dict(counts)}


def classify_match(
    row: InventoryLabRow,
    skus_by_seller_sku: dict[str, list[dict[str, Any]]],
    skus_by_asin: dict[str, list[dict[str, Any]]],
) -> tuple[str, str | None, dict[str, Any] | None, str | None]:
    if row.seller_sku:
        sku_matches = skus_by_seller_sku.get(row.seller_sku, [])
        if len(sku_matches) == 1:
            return "matched", "seller_sku", sku_matches[0], None
        if len(sku_matches) > 1:
            return "ambiguous", None, None, "Multiple Amazon SKU rows match the InventoryLab MSKU."

    if row.asin:
        asin_matches = skus_by_asin.get(row.asin, [])
        title_matches = [
            sku
            for sku in asin_matches
            if title_similarity(row.title, clean_text(sku.get("product_name"))) >= 0.65
        ]
        if len(title_matches) == 1:
            return (
                "review_candidate",
                "asin_title_review",
                title_matches[0],
                "Matched by ASIN/title fallback and requires review.",
            )
        if len(title_matches) > 1:
            return "ambiguous", None, None, "Multiple Amazon SKU rows match ASIN/title fallback."
        if len(asin_matches) > 1:
            return "ambiguous", None, None, "Multiple Amazon SKU rows share the ASIN."

    return "unmatched", None, None, None


def build_backfill_rows(
    analysis: dict[str, Any],
    source_file: Path,
    existing_backfill: dict[tuple[str, int], dict[str, Any]],
) -> list[dict[str, Any]]:
    source_name = str(source_file.as_posix())
    rows = []

    for item in analysis["rows"]:
        if not item["would_insert_or_update"]:
            continue

        row: InventoryLabRow = item["row"]
        sku = item["matched_amazon_sku"] or {}
        rows.append(
            {
                "source_file": source_name,
                "source_row_number": row.row_number,
                "match_status": item["match_status"],
                "match_method": item["match_method"],
                "requires_review": item["requires_review"],
                "amazon_sku_id": sku.get("amazon_sku_id"),
                "seller_sku": row.seller_sku,
                "asin": row.asin,
                "fnsku": row.fnsku,
                "title": row.title,
                "on_hand_quantity": row.on_hand_quantity,
                "total_in_stock_buy_cost": row.total_in_stock_buy_cost,
                "active_cost_per_unit": row.active_cost_per_unit,
                "active_supplier": row.active_supplier,
                "active_date_purchased": row.active_date_purchased,
                "list_price": row.list_price,
                "condition": row.condition,
                "raw_inventorylab_json": row.raw,
                "notes": item["notes"],
            }
        )

    return rows


def print_summary(analysis: dict[str, Any]) -> None:
    counts = analysis["counts"]
    print("InventoryLab active inventory dry run")
    print("------------------------------------")
    print(f"Rows read: {counts.get('rows_read', 0)}")
    print(f"Rows matched by SKU/MSKU: {counts.get('rows_matched_by_sku', 0)}")
    print(
        "Rows matched by ASIN/title fallback for review: "
        f"{counts.get('rows_matched_by_asin_fallback', 0)}"
    )
    print(f"Rows ambiguous: {counts.get('rows_ambiguous', 0)}")
    print(f"Rows missing cost/date: {counts.get('rows_missing_cost_or_date', 0)}")
    print(
        "Candidate rows missing cost/date: "
        f"{counts.get('candidate_rows_missing_cost_or_date', 0)}"
    )
    print(f"Rows unmatched: {counts.get('rows_unmatched', 0)}")
    print(f"Rows skipped inactive: {counts.get('rows_skipped_inactive', 0)}")
    print(f"Rows that would be inserted/updated: {counts.get('rows_would_insert_or_update', 0)}")

    ambiguous = [row for row in analysis["rows"] if row["match_status"] == "ambiguous"][:10]
    review = [row for row in analysis["rows"] if row["match_method"] == "asin_title_review"][:10]

    if ambiguous:
        print("\nFirst ambiguous rows:")
        for item in ambiguous:
            row: InventoryLabRow = item["row"]
            print(f"- row {row.row_number}: MSKU={row.seller_sku or '--'} ASIN={row.asin or '--'} {row.title or '--'}")

    if review:
        print("\nFirst ASIN/title review candidates:")
        for item in review:
            row = item["row"]
            sku = item["matched_amazon_sku"] or {}
            print(
                f"- row {row.row_number}: ASIN={row.asin or '--'} "
                f"MSKU={row.seller_sku or '--'} -> Amazon SKU={sku.get('seller_sku') or '--'}"
            )


def print_missing_cost_date_rows(analysis: dict[str, Any]) -> None:
    missing = [
        item
        for item in analysis["rows"]
        if not item["has_cost"] or not item["has_date"]
    ]
    if not missing:
        return

    print("\nRows missing cost/date:")
    for item in missing:
        row: InventoryLabRow = item["row"]
        sku = item["matched_amazon_sku"] or {}
        exists = (
            "MSKU"
            if item["match_method"] == "seller_sku"
            else "ASIN/title review"
            if item["match_method"] == "asin_title_review"
            else "no"
        )
        print(
            f"- row {row.row_number}: exists={exists}; "
            f"on_hand={row.on_hand_quantity}; "
            f"msku={row.seller_sku or '--'}; "
            f"asin={row.asin or '--'}; "
            f"cost={row.raw.get('Active Cost/Unit')!r}; "
            f"date={row.raw.get('Active Date Purchased')!r}; "
            f"title={row.title or '--'}"
        )
        if sku:
            print(
                f"  amazon_skus: seller_sku={sku.get('seller_sku') or '--'}; "
                f"asin={sku.get('asin') or '--'}; "
                f"title={sku.get('product_name') or '--'}"
            )


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def clean_asin(value: Any) -> str | None:
    text = clean_text(value)
    if not text or text.upper() == "N/A":
        return None
    return text.upper()


def to_int(value: Any) -> int | None:
    text = clean_text(value)
    if text is None:
        return None
    try:
        return int(float(text.replace(",", "")))
    except ValueError:
        return None


def to_money(value: Any) -> float | None:
    text = clean_text(value)
    if text is None:
        return None
    text = text.replace("$", "").replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_inventorylab_date(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def title_similarity(left: str | None, right: str | None) -> float:
    left_tokens = title_tokens(left)
    right_tokens = title_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = left_tokens & right_tokens
    return len(overlap) / max(len(left_tokens), len(right_tokens))


def title_tokens(value: str | None) -> set[str]:
    if not value:
        return set()
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.lower())
        if token not in {"the", "and", "for", "new", "edition", "version", "us"}
    }


def chunks(rows: list[Any], size: int):
    for index in range(0, len(rows), size):
        yield rows[index : index + size]


if __name__ == "__main__":
    raise SystemExit(main())
