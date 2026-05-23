import os
import re
import csv
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from collections import defaultdict

import gspread
from dotenv import load_dotenv
from supabase import create_client

try:
    from title_cleaning import clean_marketplace_title_for_search
    from system_detection import (
        detect_system_from_title,
        normalize_spaces,
        normalize_system,
        remove_system_terms,
    )
except ImportError:
    from integrations.title_cleaning import clean_marketplace_title_for_search
    from integrations.system_detection import (
        detect_system_from_title,
        normalize_spaces,
        normalize_system,
        remove_system_terms,
    )


ALLOW_REENRICHMENT = False
PURCHASE_ITEMS_PAGE_SIZE = 1000
DIAGNOSTIC_OUTPUT_PATH = f"data/revseller_enrichment_diagnostics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

REVSELLER_SHEET_ID = None
REVSELLER_WORKSHEET_NAME = None

REQUIRED_REVSELLER_COLUMNS = {
    "ASIN",
    "Title",
    "BuyBox Price",
    "Today's Date",
}


GENERIC_TITLE_WORDS = {
    "brand",
    "sealed",
    "factory",
    "nib",
    "complete",
    "cib",
    "disc",
    "disk",
    "cartridge",
    "cart",
    "case",
    "manual",
    "game",
    "video",
    "edition",
    "standard",
}


def compact_title_key(title: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", title or "")


def normalize_title(title: str | None) -> str:
    if not title:
        return ""

    text = clean_marketplace_title_for_search(title).lower()
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"\[[^]]*\]", " ", text)
    text = remove_system_terms(text)
    text = re.sub(r"[^a-z0-9]+", " ", text)

    words = [
        word
        for word in text.split()
        if word not in GENERIC_TITLE_WORDS
    ]

    return normalize_spaces(" ".join(words))


def parse_money(value) -> Decimal | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    text = text.replace("$", "").replace(",", "").strip()

    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def parse_revseller_date(value) -> date:
    if not value:
        return date.min

    text = str(value).strip()

    formats = [
        "%m/%d/%Y",
        "%m/%d/%y",
        "%Y-%m-%d",
        "%m-%d-%Y",
        "%m-%d-%y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass

    return date.min


def get_gspread_client():
    credentials_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

    if not credentials_file:
        raise RuntimeError(
            "Missing GOOGLE_APPLICATION_CREDENTIALS environment variable."
        )

    return gspread.service_account(filename=credentials_file)


def load_revseller_rows():
    if not REVSELLER_SHEET_ID:
        raise RuntimeError("Missing REVSELLER_GOOGLE_SHEET_ID environment variable.")

    gc = get_gspread_client()
    spreadsheet = gc.open_by_key(REVSELLER_SHEET_ID)
    worksheet = spreadsheet.worksheet(REVSELLER_WORKSHEET_NAME)

    rows = worksheet.get_all_records()

    if not rows:
        return []

    missing = REQUIRED_REVSELLER_COLUMNS - set(rows[0].keys())
    if missing:
        raise RuntimeError(
            f"RevSeller sheet is missing required columns: {sorted(missing)}"
        )

    cleaned_rows = []

    for row in rows:
        asin = normalize_spaces(str(row.get("ASIN", "")))
        raw_title = normalize_spaces(str(row.get("Title", "")))
        target_price = parse_money(row.get("BuyBox Price"))
        row_date = parse_revseller_date(row.get("Today's Date"))

        if not asin or not raw_title:
            continue

        rev_system = detect_system_from_title(raw_title)
        norm_title = normalize_title(raw_title)

        if not norm_title:
            continue

        cleaned_rows.append(
            {
                "asin": asin,
                "raw_title": raw_title,
                "normalized_title": norm_title,
                "system": rev_system,
                "target_price": target_price,
                "row_date": row_date,
            }
        )

    return cleaned_rows


def load_manual_match_rows(supabase):
    try:
        response = (
            supabase.table("manual_item_matches")
            .select(
                "asin,amazon_title,source_title,normalized_title,compact_title,"
                "system,target_price,updated_at"
            )
            .execute()
        )
    except Exception as exc:
        print(f"Manual match memory skipped: {exc}")
        return []

    rows = []

    for row in response.data or []:
        asin = normalize_spaces(str(row.get("asin") or ""))
        normalized_title = normalize_spaces(str(row.get("normalized_title") or ""))
        system = normalize_system(row.get("system"))

        if not asin or not normalized_title or not system:
            continue

        raw_title = normalize_spaces(
            str(row.get("amazon_title") or row.get("source_title") or normalized_title)
        )

        rows.append(
            {
                "asin": asin,
                "raw_title": raw_title,
                "normalized_title": normalized_title,
                "system": system,
                "target_price": parse_money(row.get("target_price")),
                "row_date": date.max,
                "source": "manual_ui",
            }
        )

    return rows


def build_revseller_indexes(rows):
    by_title_system = {}
    by_title = defaultdict(list)
    compact_rows_by_title_system = defaultdict(list)

    for row in rows:
        title_key = row["normalized_title"]
        system_key = row["system"]

        if system_key:
            compound_key = (title_key, system_key)

            existing = by_title_system.get(compound_key)
            if existing is None or row["row_date"] >= existing["row_date"]:
                by_title_system[compound_key] = row

            compact_key = compact_title_key(title_key)

            if compact_key:
                compact_rows_by_title_system[(compact_key, system_key)].append(row)

        by_title[title_key].append(row)

    ambiguous_titles = {
        title_key
        for title_key, title_rows in by_title.items()
        if len({row["system"] for row in title_rows if row["system"]}) > 1
    }

    by_compact_title_system = {}
    ambiguous_compact_title_system = set()

    for compound_key, compact_rows in compact_rows_by_title_system.items():
        unique_asins = {row["asin"] for row in compact_rows}

        if len(unique_asins) > 1:
            ambiguous_compact_title_system.add(compound_key)
            continue

        by_compact_title_system[compound_key] = max(
            compact_rows,
            key=lambda row: row["row_date"],
        )

    return (
        by_title_system,
        ambiguous_titles,
        by_title,
        by_compact_title_system,
        ambiguous_compact_title_system,
    )


def get_supabase_client():
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not supabase_url or not supabase_key:
        raise RuntimeError(
            "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY environment variable."
        )

    return create_client(supabase_url, supabase_key)


def fetch_purchase_items(supabase):
    all_items = []
    offset = 0

    while True:
        query = (
            supabase.table("purchase_items")
            .select("item_id,title,amazon_title,system,asin,target_price")
            .range(offset, offset + PURCHASE_ITEMS_PAGE_SIZE - 1)
        )

        if not ALLOW_REENRICHMENT:
            query = query.is_("asin", "null")

        response = query.execute()
        rows = response.data or []

        all_items.extend(rows)

        if len(rows) < PURCHASE_ITEMS_PAGE_SIZE:
            break

        offset += PURCHASE_ITEMS_PAGE_SIZE

    return all_items


def update_purchase_item(supabase, item_id, asin, amazon_title, target_price):
    payload = {
        "asin": asin,
        "amazon_title": amazon_title,
    }

    if target_price is not None:
        payload["target_price"] = str(target_price)

    return (
        supabase.table("purchase_items")
        .update(payload)
        .eq("item_id", item_id)
        .execute()
    )


def match_purchase_item(
    item,
    by_title_system,
    ambiguous_titles,
    by_title,
    by_compact_title_system,
    ambiguous_compact_title_system,
):
    raw_title = item.get("title") or ""
    normalized_title = normalize_title(raw_title)

    if not normalized_title:
        return None, "skipped_no_match"

    detected_system = normalize_system(item.get("system")) or detect_system_from_title(
        raw_title
    )

    if detected_system:
        matched_row = by_title_system.get((normalized_title, detected_system))

        if matched_row:
            return matched_row, "matched_with_system"

        compact_key = compact_title_key(normalized_title)
        compact_compound_key = (compact_key, detected_system)

        if compact_compound_key in ambiguous_compact_title_system:
            return None, "skipped_ambiguous_compact_system"

        matched_row = by_compact_title_system.get(compact_compound_key)

        if matched_row:
            return matched_row, "matched_compact_with_system"

        return None, "skipped_no_match"

    if normalized_title in ambiguous_titles:
        return None, "skipped_ambiguous_system"

    if normalized_title in by_title:
        return None, "skipped_no_detected_system"

    return None, "skipped_no_match"


def write_diagnostics(diagnostic_rows):
    if not diagnostic_rows:
        print("Diagnostic CSV skipped: no diagnostic rows.")
        return

    os.makedirs(os.path.dirname(DIAGNOSTIC_OUTPUT_PATH), exist_ok=True)

    fieldnames = [
        "item_id",
        "status",
        "purchase_item_title",
        "purchase_item_system",
        "detected_system",
        "normalized_title",
        "existing_asin",
        "existing_target_price",
    ]

    with open(DIAGNOSTIC_OUTPUT_PATH, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(diagnostic_rows)

    print(f"Diagnostic CSV written: {DIAGNOSTIC_OUTPUT_PATH}")


def main():
    global REVSELLER_SHEET_ID
    global REVSELLER_WORKSHEET_NAME

    load_dotenv()

    REVSELLER_SHEET_ID = os.getenv("REVSELLER_GOOGLE_SHEET_ID")
    REVSELLER_WORKSHEET_NAME = os.getenv("REVSELLER_WORKSHEET_NAME", "Sheet1")

    print("Starting RevSeller sheet enrichment...")
    print(f"ALLOW_REENRICHMENT: {ALLOW_REENRICHMENT}")

    supabase = get_supabase_client()

    revseller_rows = load_revseller_rows()
    print(f"RevSeller usable rows loaded: {len(revseller_rows)}")
    manual_match_rows = load_manual_match_rows(supabase)
    print(f"Manual match rows loaded: {len(manual_match_rows)}")
    match_rows = revseller_rows + manual_match_rows

    (
        by_title_system,
        ambiguous_titles,
        by_title,
        by_compact_title_system,
        ambiguous_compact_title_system,
    ) = build_revseller_indexes(match_rows)

    print(f"RevSeller title+system keys: {len(by_title_system)}")
    print(f"RevSeller ambiguous title keys: {len(ambiguous_titles)}")
    print(f"RevSeller compact title+system keys: {len(by_compact_title_system)}")
    print(
        "RevSeller ambiguous compact title+system keys: "
        f"{len(ambiguous_compact_title_system)}"
    )

    purchase_items = fetch_purchase_items(supabase)
    print(f"Purchase items scanned: {len(purchase_items)}")

    counts = {
        "matched_with_system": 0,
        "matched_compact_with_system": 0,
        "skipped_ambiguous_system": 0,
        "skipped_ambiguous_compact_system": 0,
        "skipped_no_match": 0,
        "skipped_no_detected_system": 0,
        "updated": 0,
        "errors": 0,
    }

    diagnostic_rows = []

    for item in purchase_items:
        matched_row, status = match_purchase_item(
            item,
            by_title_system,
            ambiguous_titles,
            by_title,
            by_compact_title_system,
            ambiguous_compact_title_system,
        )

        counts[status] += 1

        if not matched_row:
            raw_title = item.get("title") or ""
            diagnostic_rows.append(
                {
                    "item_id": item.get("item_id"),
                    "status": status,
                    "purchase_item_title": raw_title,
                    "purchase_item_system": item.get("system"),
                    "detected_system": normalize_system(item.get("system"))
                    or detect_system_from_title(raw_title),
                    "normalized_title": normalize_title(raw_title),
                    "existing_asin": item.get("asin"),
                    "existing_target_price": item.get("target_price"),
                }
            )
            continue

        try:
            update_purchase_item(
                supabase=supabase,
                item_id=item["item_id"],
                asin=matched_row["asin"],
                amazon_title=matched_row["raw_title"],
                target_price=matched_row["target_price"],
            )
            counts["updated"] += 1
        except Exception as exc:
            counts["errors"] += 1
            print(f"ERROR updating item_id={item.get('item_id')}: {exc}")

    write_diagnostics(diagnostic_rows)

    print("\nRevSeller enrichment complete.")
    print("--------------------------------")

    for key, value in counts.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
