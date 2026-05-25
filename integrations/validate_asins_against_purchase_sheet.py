import csv
import os
from collections import Counter, defaultdict
from datetime import datetime

import gspread
from dotenv import load_dotenv
from supabase import create_client


REFERENCE_SHEET_ID = "1K0-G3BJ-dKLA3U3VYGiPD1kVMoQxyBKQzZfx8NKzrcA"
REFERENCE_WORKSHEET = "Purchases"
PAGE_SIZE = 1000
OUTPUT_PATH = (
    f"data/asin_validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
)
EXCLUDED_STATUSES = {"return_opened", "cancelled"}
BLANK_MARKERS = {"", "N/A", "NA", "NONE", "NULL", "-", "--"}


def normalize_header(value):
    return str(value or "").replace("\xa0", " ").strip().lower()


def normalize_text(value):
    return str(value or "").replace("\xa0", " ").strip()


def normalize_asin(value):
    text = normalize_text(value).upper()
    return None if text in BLANK_MARKERS else text


def normalize_order_number(value):
    text = normalize_text(value)
    return "" if text.upper() in BLANK_MARKERS else text


def parse_qty(value):
    try:
        parsed = int(float(str(value or "").replace(",", "").strip()))
        return parsed if parsed > 0 else 1
    except Exception:
        return 1


def get_supabase_client():
    return create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )


def get_gspread_client():
    credentials_file = os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
    return gspread.service_account(filename=credentials_file)


def load_sheet_orders():
    gc = get_gspread_client()
    spreadsheet = gc.open_by_key(REFERENCE_SHEET_ID)
    worksheet = spreadsheet.worksheet(REFERENCE_WORKSHEET)
    values = worksheet.get_all_values()

    if not values:
        return {}, {"rows": 0, "rows_without_order": 0, "rows_without_asin": 0}

    headers = [normalize_header(value) for value in values[0]]
    header_index = {header: index for index, header in enumerate(headers)}
    required = {"asin", "order number", "qty", "title"}
    missing = required - set(header_index)

    if missing:
        raise RuntimeError(f"Missing required Purchases columns: {sorted(missing)}")

    orders = defaultdict(
        lambda: {
            "asin_qty": Counter(),
            "titles_by_asin": defaultdict(list),
            "row_count": 0,
        }
    )
    stats = {"rows": 0, "rows_without_order": 0, "rows_without_asin": 0}

    for row in values[1:]:
        stats["rows"] += 1
        order_number = normalize_order_number(row[header_index["order number"]])
        asin = normalize_asin(row[header_index["asin"]])
        qty = parse_qty(row[header_index["qty"]])
        title = normalize_text(row[header_index["title"]])

        if not order_number:
            stats["rows_without_order"] += 1
            continue

        if not asin:
            stats["rows_without_asin"] += 1
            continue

        order = orders[order_number]
        order["asin_qty"][asin] += qty
        order["titles_by_asin"][asin].append(title)
        order["row_count"] += 1

    return orders, stats


def fetch_mbop_items(supabase):
    rows = []
    offset = 0

    while True:
        response = (
            supabase.table("purchase_items")
            .select(
                "item_id,title,amazon_title,asin,quantity,current_status,"
                "exclude_from_purchase_reporting,purchases(supplier_order_id)"
            )
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        page = response.data or []
        rows.extend(page)

        if len(page) < PAGE_SIZE:
            break

        offset += PAGE_SIZE

    return rows


def load_mbop_orders(supabase):
    orders = defaultdict(
        lambda: {
            "asin_qty": Counter(),
            "titles_by_asin": defaultdict(list),
            "items_by_asin": defaultdict(list),
            "blank_asin_items": [],
            "excluded_items": [],
            "row_count": 0,
        }
    )

    for item in fetch_mbop_items(supabase):
        purchase = item.get("purchases") or {}
        order_number = normalize_order_number(purchase.get("supplier_order_id"))

        if not order_number:
            continue

        status = normalize_text(item.get("current_status")).lower()
        excluded = bool(item.get("exclude_from_purchase_reporting"))

        if excluded or status in EXCLUDED_STATUSES:
            orders[order_number]["excluded_items"].append(item)
            continue

        asin = normalize_asin(item.get("asin"))
        qty = parse_qty(item.get("quantity"))
        title = normalize_text(item.get("amazon_title") or item.get("title"))
        order = orders[order_number]
        order["row_count"] += 1

        if not asin:
            order["blank_asin_items"].append(item)
            continue

        order["asin_qty"][asin] += qty
        order["titles_by_asin"][asin].append(title)
        order["items_by_asin"][asin].append(item)

    return orders


def join_values(values):
    return " | ".join(str(value) for value in values if value)


def order_asin_text(counter):
    return "; ".join(
        f"{asin} x{qty}"
        for asin, qty in sorted(counter.items())
    )


def build_validation_rows(sheet_orders, mbop_orders):
    report_rows = []
    summary = Counter()
    all_orders = sorted(set(sheet_orders) | set(mbop_orders))

    for order_number in all_orders:
        sheet = sheet_orders.get(order_number)
        mbop = mbop_orders.get(order_number)

        if not sheet:
            if mbop and mbop["asin_qty"]:
                summary["mbop_order_not_in_sheet"] += 1
                report_rows.append({
                    "issue_type": "mbop_order_not_in_sheet",
                    "order_number": order_number,
                    "sheet_asin": "",
                    "sheet_qty": "",
                    "mbop_qty": "",
                    "sheet_asins": "",
                    "mbop_asins": order_asin_text(mbop["asin_qty"]),
                    "sheet_titles": "",
                    "mbop_titles": join_values(
                        title
                        for titles in mbop["titles_by_asin"].values()
                        for title in titles
                    ),
                    "mbop_item_ids": join_values(
                        item["item_id"]
                        for items in mbop["items_by_asin"].values()
                        for item in items
                    ),
                })
            continue

        if not mbop or (not mbop["asin_qty"] and not mbop["blank_asin_items"]):
            summary["sheet_order_missing_in_mbop"] += 1
            report_rows.append({
                "issue_type": "sheet_order_missing_in_mbop",
                "order_number": order_number,
                "sheet_asin": "",
                "sheet_qty": "",
                "mbop_qty": "",
                "sheet_asins": order_asin_text(sheet["asin_qty"]),
                "mbop_asins": "",
                "sheet_titles": join_values(
                    title
                    for titles in sheet["titles_by_asin"].values()
                    for title in titles
                ),
                "mbop_titles": "",
                "mbop_item_ids": "",
            })
            continue

        order_has_issue = False

        for asin, sheet_qty in sorted(sheet["asin_qty"].items()):
            mbop_qty = mbop["asin_qty"].get(asin, 0)
            if mbop_qty == sheet_qty:
                continue

            issue_type = "asin_qty_mismatch" if mbop_qty else "asin_missing_in_mbop"
            summary[issue_type] += 1
            order_has_issue = True
            report_rows.append({
                "issue_type": issue_type,
                "order_number": order_number,
                "sheet_asin": asin,
                "sheet_qty": sheet_qty,
                "mbop_qty": mbop_qty,
                "sheet_asins": order_asin_text(sheet["asin_qty"]),
                "mbop_asins": order_asin_text(mbop["asin_qty"]),
                "sheet_titles": join_values(sheet["titles_by_asin"].get(asin, [])),
                "mbop_titles": join_values(mbop["titles_by_asin"].get(asin, [])),
                "mbop_item_ids": join_values(
                    item["item_id"] for item in mbop["items_by_asin"].get(asin, [])
                ),
            })

        for asin, mbop_qty in sorted(mbop["asin_qty"].items()):
            if asin in sheet["asin_qty"]:
                continue

            summary["extra_asin_in_mbop"] += 1
            order_has_issue = True
            report_rows.append({
                "issue_type": "extra_asin_in_mbop",
                "order_number": order_number,
                "sheet_asin": asin,
                "sheet_qty": 0,
                "mbop_qty": mbop_qty,
                "sheet_asins": order_asin_text(sheet["asin_qty"]),
                "mbop_asins": order_asin_text(mbop["asin_qty"]),
                "sheet_titles": "",
                "mbop_titles": join_values(mbop["titles_by_asin"].get(asin, [])),
                "mbop_item_ids": join_values(
                    item["item_id"] for item in mbop["items_by_asin"].get(asin, [])
                ),
            })

        if mbop["blank_asin_items"]:
            summary["blank_asin_in_mbop"] += 1
            order_has_issue = True
            report_rows.append({
                "issue_type": "blank_asin_in_mbop",
                "order_number": order_number,
                "sheet_asin": "",
                "sheet_qty": "",
                "mbop_qty": sum(parse_qty(item.get("quantity")) for item in mbop["blank_asin_items"]),
                "sheet_asins": order_asin_text(sheet["asin_qty"]),
                "mbop_asins": order_asin_text(mbop["asin_qty"]),
                "sheet_titles": "",
                "mbop_titles": join_values(
                    normalize_text(item.get("amazon_title") or item.get("title"))
                    for item in mbop["blank_asin_items"]
                ),
                "mbop_item_ids": join_values(
                    item["item_id"] for item in mbop["blank_asin_items"]
                ),
            })

        if not order_has_issue:
            summary["orders_exact_match"] += 1

    summary["orders_compared"] = len(set(sheet_orders) & set(mbop_orders))
    summary["sheet_orders"] = len(sheet_orders)
    summary["mbop_orders"] = len(mbop_orders)

    return report_rows, summary


def write_report(rows, output_path):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fieldnames = [
        "issue_type",
        "order_number",
        "sheet_asin",
        "sheet_qty",
        "mbop_qty",
        "sheet_asins",
        "mbop_asins",
        "sheet_titles",
        "mbop_titles",
        "mbop_item_ids",
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    load_dotenv()
    supabase = get_supabase_client()

    sheet_orders, sheet_stats = load_sheet_orders()
    mbop_orders = load_mbop_orders(supabase)
    report_rows, summary = build_validation_rows(sheet_orders, mbop_orders)
    write_report(report_rows, OUTPUT_PATH)

    print("ASIN validation against reference Purchases sheet")
    print("------------------------------------------------")
    print(f"Reference rows scanned: {sheet_stats['rows']}")
    print(f"Reference rows without order number: {sheet_stats['rows_without_order']}")
    print(f"Reference rows without ASIN: {sheet_stats['rows_without_asin']}")
    print(f"Reference orders with ASINs: {summary['sheet_orders']}")
    print(f"MBOP active orders scanned: {summary['mbop_orders']}")
    print(f"Orders compared: {summary['orders_compared']}")
    print(f"Orders exact ASIN/qty match: {summary['orders_exact_match']}")
    print()
    print("Issues")
    print("------")

    for key in sorted(k for k in summary if k not in {
        "sheet_orders",
        "mbop_orders",
        "orders_compared",
        "orders_exact_match",
    }):
        print(f"{key}: {summary[key]}")

    print()
    print(f"Report: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
