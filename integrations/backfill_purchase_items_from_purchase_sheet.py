import argparse
import os
import sys
from decimal import Decimal, InvalidOperation

import openpyxl
from dotenv import load_dotenv
from supabase import create_client

try:
    from sync_revseller_sheet import compact_title_key, normalize_title
    from system_detection import normalize_system
except ImportError:
    from integrations.sync_revseller_sheet import compact_title_key, normalize_title
    from integrations.system_detection import normalize_system


PAGE_SIZE = 1000


def get_supabase_client():
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not supabase_url or not supabase_key:
        raise RuntimeError(
            "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY environment variable."
        )

    return create_client(supabase_url, supabase_key)


def normalize_order_number(value):
    return str(value or "").strip()


def normalize_asin(value):
    text = str(value or "").strip().upper()
    return text or None


def parse_money(value):
    if value is None or value == "":
        return None

    text = str(value).replace("$", "").replace(",", "").strip()

    if not text:
        return None

    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def header_key(value):
    return str(value or "").replace("\xa0", " ").strip().lower()


def load_purchase_sheet_rows(path):
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    worksheet = workbook["Purchases"]
    rows = worksheet.iter_rows(values_only=True)
    headers = [header_key(value) for value in next(rows)]
    header_index = {header: index for index, header in enumerate(headers)}

    required_headers = ["asin", "title", "system", "list price", "order number"]
    missing_headers = [
        header for header in required_headers if header not in header_index
    ]

    if missing_headers:
        raise RuntimeError(f"Purchases sheet missing columns: {missing_headers}")

    by_order = {}
    sheet_row_count = 0

    for row in rows:
        order_number = normalize_order_number(row[header_index["order number"]])
        asin = normalize_asin(row[header_index["asin"]])
        title = str(row[header_index["title"]] or "").strip()
        system = normalize_system(str(row[header_index["system"]] or "").strip())
        list_price = parse_money(row[header_index["list price"]])

        if not order_number or (not asin and list_price is None):
            continue

        normalized_title = normalize_title(title)
        sheet_row = {
            "order_number": order_number,
            "asin": asin,
            "title": title,
            "system": system,
            "list_price": list_price,
            "normalized_title": normalized_title,
            "compact_title": compact_title_key(normalized_title),
        }

        by_order.setdefault(order_number, []).append(sheet_row)
        sheet_row_count += 1

    return by_order, sheet_row_count


def fetch_missing_purchase_items(supabase):
    all_items = []
    offset = 0

    while True:
        response = (
            supabase.table("purchase_items")
            .select(
                "item_id,title,amazon_title,system,asin,target_price,"
                "purchases(supplier_order_id)"
            )
            .or_("asin.is.null,target_price.is.null")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        rows = response.data or []
        all_items.extend(rows)

        if len(rows) < PAGE_SIZE:
            break

        offset += PAGE_SIZE

    return all_items


def choose_sheet_match(item, sheet_rows):
    if not sheet_rows:
        return None, "no_order_match"

    if len(sheet_rows) == 1:
        return sheet_rows[0], "single_order_row"

    item_asin = normalize_asin(item.get("asin"))

    if item_asin:
        asin_matches = [row for row in sheet_rows if row["asin"] == item_asin]
        if len(asin_matches) == 1:
            return asin_matches[0], "asin_match"

    item_system = normalize_system(item.get("system"))
    item_title = normalize_title(item.get("title") or item.get("amazon_title"))
    item_compact_title = compact_title_key(item_title)

    exact_matches = [
        row
        for row in sheet_rows
        if row["system"] == item_system and row["normalized_title"] == item_title
    ]

    if len(exact_matches) == 1:
        return exact_matches[0], "title_system_match"

    compact_matches = [
        row
        for row in sheet_rows
        if row["system"] == item_system
        and row["compact_title"]
        and row["compact_title"] == item_compact_title
    ]

    if len(compact_matches) == 1:
        return compact_matches[0], "compact_title_system_match"

    system_matches = [row for row in sheet_rows if row["system"] == item_system]

    if len(system_matches) == 1:
        return system_matches[0], "single_system_order_row"

    return None, "ambiguous_order_match"


def update_purchase_item(supabase, item, sheet_match, dry_run):
    updates = {}

    if not item.get("asin") and sheet_match["asin"]:
        updates["asin"] = sheet_match["asin"]
        updates["amazon_title"] = sheet_match["title"]

    if item.get("target_price") is None and sheet_match["list_price"] is not None:
        updates["target_price"] = str(sheet_match["list_price"])

    if not updates:
        return {}

    if not dry_run:
        (
            supabase.table("purchase_items")
            .update(updates)
            .eq("item_id", item["item_id"])
            .execute()
        )

    return updates


def main():
    parser = argparse.ArgumentParser(
        description="Backfill missing ASIN and target sell price from the old Purchases sheet."
    )
    parser.add_argument("workbook_path")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    load_dotenv()
    supabase = get_supabase_client()

    sheet_rows_by_order, sheet_row_count = load_purchase_sheet_rows(args.workbook_path)
    missing_items = fetch_missing_purchase_items(supabase)

    counts = {
        "sheet_rows_loaded": sheet_row_count,
        "missing_items_scanned": len(missing_items),
        "order_matches": 0,
        "items_updated": 0,
        "asin_updates": 0,
        "target_price_updates": 0,
        "amazon_title_updates": 0,
        "ambiguous_order_match": 0,
        "no_order_match": 0,
        "no_field_update_needed": 0,
    }
    match_method_counts = {}

    for item in missing_items:
        purchase = item.get("purchases") or {}
        order_number = normalize_order_number(purchase.get("supplier_order_id"))
        sheet_rows = sheet_rows_by_order.get(order_number, [])
        sheet_match, match_method = choose_sheet_match(item, sheet_rows)
        match_method_counts[match_method] = match_method_counts.get(match_method, 0) + 1

        if not sheet_match:
            counts[match_method] = counts.get(match_method, 0) + 1
            continue

        counts["order_matches"] += 1
        updates = update_purchase_item(
            supabase=supabase,
            item=item,
            sheet_match=sheet_match,
            dry_run=not args.apply,
        )

        if not updates:
            counts["no_field_update_needed"] += 1
            continue

        counts["items_updated"] += 1

        if "asin" in updates:
            counts["asin_updates"] += 1

        if "target_price" in updates:
            counts["target_price_updates"] += 1

        if "amazon_title" in updates:
            counts["amazon_title_updates"] += 1

    print("Backfill purchase items from Purchases sheet")
    print("------------------------------------------")
    print(f"Mode: {'APPLY' if args.apply else 'DRY RUN'}")

    for key, value in counts.items():
        print(f"{key}: {value}")

    print("\nMatch methods")
    print("-------------")

    for key, value in sorted(match_method_counts.items()):
        print(f"{key}: {value}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
