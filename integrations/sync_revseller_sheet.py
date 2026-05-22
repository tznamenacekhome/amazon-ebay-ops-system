import os
import re
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from collections import defaultdict

import gspread
from dotenv import load_dotenv
from supabase import create_client


ALLOW_REENRICHMENT = True
PURCHASE_ITEMS_PAGE_SIZE = 1000

REVSELLER_SHEET_ID = None
REVSELLER_WORKSHEET_NAME = None

REQUIRED_REVSELLER_COLUMNS = {
    "ASIN",
    "Title",
    "BuyBox Price",
    "Today's Date",
}


SYSTEM_ALIASES = {
    "nintendo switch 2": ["nintendo switch 2", "switch 2"],
    "nintendo switch": ["nintendo switch", "switch"],
    "nintendo 3ds": ["nintendo 3ds", "3ds"],
    "nintendo ds": ["nintendo ds", "ds"],
    "nintendo wii u": ["nintendo wii u", "wii u"],
    "nintendo wii": ["nintendo wii", "wii"],
    "gamecube": ["gamecube", "game cube", "nintendo gamecube"],
    "nintendo 64": ["nintendo 64", "n64"],
    "super nintendo": ["super nintendo", "snes"],
    "nes": ["nes", "nintendo entertainment system"],
    "playstation 5": ["playstation 5", "ps5"],
    "playstation 4": ["playstation 4", "ps4"],
    "playstation 3": ["playstation 3", "ps3"],
    "playstation 2": ["playstation 2", "ps2"],
    "playstation": ["playstation", "ps1", "psx"],
    "psp": ["psp", "playstation portable"],
    "playstation vita": ["playstation vita", "ps vita", "vita"],
    "xbox series x": ["xbox series x", "series x"],
    "xbox series s": ["xbox series s", "series s"],
    "xbox one": ["xbox one", "xbone"],
    "xbox 360": ["xbox 360", "360"],
    "xbox": ["original xbox", "xbox"],
    "pc": ["pc", "windows pc"],
}


GENERIC_TITLE_WORDS = {
    "new",
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


def normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_system(value: str | None) -> str | None:
    if not value:
        return None

    text = normalize_spaces(value.lower())
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = normalize_spaces(text)

    for canonical, aliases in SYSTEM_ALIASES.items():
        for alias in aliases:
            alias_norm = normalize_spaces(re.sub(r"[^a-z0-9]+", " ", alias.lower()))
            if text == alias_norm:
                return canonical

    for canonical, aliases in SYSTEM_ALIASES.items():
        for alias in aliases:
            alias_norm = normalize_spaces(re.sub(r"[^a-z0-9]+", " ", alias.lower()))
            if re.search(rf"\b{re.escape(alias_norm)}\b", text):
                return canonical

    return None


def detect_system_from_title(title: str | None) -> str | None:
    if not title:
        return None

    text = title.lower()
    matches = []

    for canonical, aliases in SYSTEM_ALIASES.items():
        for alias in aliases:
            pattern = rf"(?<![a-z0-9]){re.escape(alias.lower())}(?![a-z0-9])"
            if re.search(pattern, text):
                matches.append((len(alias), canonical))

    if not matches:
        return None

    matches.sort(reverse=True)
    return matches[0][1]


def remove_system_terms(text: str) -> str:
    cleaned = text

    aliases = []
    for alias_list in SYSTEM_ALIASES.values():
        aliases.extend(alias_list)

    aliases.sort(key=len, reverse=True)

    for alias in aliases:
        cleaned = re.sub(
            rf"(?<![a-z0-9]){re.escape(alias.lower())}(?![a-z0-9])",
            " ",
            cleaned,
        )

    return cleaned


def normalize_title(title: str | None) -> str:
    if not title:
        return ""

    text = title.lower()
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


def build_revseller_indexes(rows):
    by_title_system = {}
    by_title = defaultdict(list)

    for row in rows:
        title_key = row["normalized_title"]
        system_key = row["system"]

        if system_key:
            compound_key = (title_key, system_key)

            existing = by_title_system.get(compound_key)
            if existing is None or row["row_date"] >= existing["row_date"]:
                by_title_system[compound_key] = row

        by_title[title_key].append(row)

    latest_by_unique_title = {}

    for title_key, title_rows in by_title.items():
        systems = {
            row["system"]
            for row in title_rows
            if row["system"]
        }

        if len(systems) == 1:
            latest_by_unique_title[title_key] = max(
                title_rows,
                key=lambda row: row["row_date"],
            )

    ambiguous_titles = {
        title_key
        for title_key, title_rows in by_title.items()
        if len({row["system"] for row in title_rows if row["system"]}) > 1
    }

    return by_title_system, latest_by_unique_title, ambiguous_titles, by_title


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
            .select("item_id,title,system,asin,target_price")
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


def update_purchase_item(supabase, item_id, asin, target_price):
    payload = {
        "asin": asin,
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
    latest_by_unique_title,
    ambiguous_titles,
    by_title,
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

        return None, "skipped_no_match"

    if normalized_title in ambiguous_titles:
        return None, "skipped_ambiguous_system"

    matched_row = latest_by_unique_title.get(normalized_title)

    if matched_row:
        return matched_row, "matched_unique_title_no_system"

    if normalized_title in by_title:
        return None, "skipped_no_detected_system"

    return None, "skipped_no_match"


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

    (
        by_title_system,
        latest_by_unique_title,
        ambiguous_titles,
        by_title,
    ) = build_revseller_indexes(revseller_rows)

    print(f"RevSeller title+system keys: {len(by_title_system)}")
    print(f"RevSeller unique-title keys: {len(latest_by_unique_title)}")
    print(f"RevSeller ambiguous title keys: {len(ambiguous_titles)}")

    purchase_items = fetch_purchase_items(supabase)
    print(f"Purchase items scanned: {len(purchase_items)}")

    counts = {
        "matched_with_system": 0,
        "matched_unique_title_no_system": 0,
        "skipped_ambiguous_system": 0,
        "skipped_no_match": 0,
        "skipped_no_detected_system": 0,
        "updated": 0,
        "errors": 0,
    }

    for item in purchase_items:
        matched_row, status = match_purchase_item(
            item,
            by_title_system,
            latest_by_unique_title,
            ambiguous_titles,
            by_title,
        )

        counts[status] += 1

        if not matched_row:
            continue

        try:
            update_purchase_item(
                supabase=supabase,
                item_id=item["item_id"],
                asin=matched_row["asin"],
                target_price=matched_row["target_price"],
            )
            counts["updated"] += 1
        except Exception as exc:
            counts["errors"] += 1
            print(f"ERROR updating item_id={item.get('item_id')}: {exc}")

    print("\nRevSeller enrichment complete.")
    print("--------------------------------")

    for key, value in counts.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()