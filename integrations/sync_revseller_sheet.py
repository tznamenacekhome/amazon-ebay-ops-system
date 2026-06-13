import os
import re
import csv
import json
import argparse
import requests
import time
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from collections import defaultdict
from difflib import SequenceMatcher

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
DEFAULT_AI_MODEL = "gpt-4.1-mini"
AI_CONFIDENCE_THRESHOLD = Decimal("0.86")
AI_MIN_LOCAL_SCORE = 0.25
AI_CANDIDATE_LIMIT = 8
AI_REVIEW_LIMIT = 50
OPEN_PURCHASE_WORK_EXCLUDED_STATUSES = {
    "listed",
    "cancelled",
    "return_opened",
    "return_pending",
}

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
    "games",
    "only",
    "video",
    "edition",
    "standard",
    "studio",
    "wildcard",
}

SYSTEM_COMPATIBLE_RESELLER_INDEXES = {
    "Xbox One": ["xbox one", "xbone", "xb1"],
    "Xbox Series X": ["xbox series x", "series x"],
    "Xbox Series S": ["xbox series s", "series s"],
    "PS 4": ["playstation 4", "ps4", "ps 4"],
    "PS 5": ["playstation 5", "ps5", "ps 5"],
}

EDITION_EQUIVALENCE_PHRASES = (
    "greatest hits",
    "platinum hits",
    "playstation hits",
    "player s choice",
    "players choice",
    "nintendo selects",
)


def compact_title_key(title: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", title or "")


def token_set_key(title: str | None) -> str:
    words = normalize_spaces(title or "").split()
    return " ".join(sorted(set(words)))


def title_tokens(title: str | None) -> set[str]:
    return set((normalize_spaces(title or "")).split())


def title_similarity(left: str | None, right: str | None) -> float:
    left_text = normalize_spaces(left or "")
    right_text = normalize_spaces(right or "")
    if not left_text or not right_text:
        return 0.0

    sequence_score = SequenceMatcher(None, left_text, right_text).ratio()
    left_tokens = title_tokens(left_text)
    right_tokens = title_tokens(right_text)
    if not left_tokens or not right_tokens:
        return sequence_score

    overlap_score = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
    subset_score = len(left_tokens & right_tokens) / max(1, min(len(left_tokens), len(right_tokens)))
    return max(sequence_score, overlap_score, subset_score)


def normalize_title(title: str | None) -> str:
    if not title:
        return ""

    text = clean_marketplace_title_for_search(title).lower()
    text = re.sub(r"\bxbox\s+one\s*/\s*series\s+s\s*/\s*x\b", " ", text)
    text = re.sub(r"\bxbox\s+one\s+series\s+s\s+x\b", " ", text)
    text = re.sub(r"\bseries\s+s\s*/\s*x\b", " ", text)
    text = re.sub(r"\bseries\s+s\s+x\b", " ", text)
    text = re.sub(r"\bseries\s+x\s*/\s*s\b", " ", text)
    text = re.sub(r"\bseries\s+x\s+s\b", " ", text)
    text = re.sub(r"\bnintedo\b", "nintendo", text)
    text = re.sub(r"\bsurvior\b", "survivor", text)
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


def clean_catalog_title(title: str | None) -> str:
    text = normalize_spaces(str(title or ""))
    return re.sub(r"\bNintedo\b", "Nintendo", text, flags=re.IGNORECASE)


def clean_status(value) -> str:
    return str(value or "").strip().lower()


def normalized_title_variants(normalized_title: str) -> list[str]:
    variants = [normalized_title]

    # eBay sellers often lead titles with condition text like "New Hitman 3".
    # Keep this as a fallback variant instead of removing "new" globally so
    # real titles such as "New Super Mario Bros." are still matched normally.
    if normalized_title.startswith("new "):
        variants.append(normalize_spaces(normalized_title[4:]))

    if normalized_title.endswith(" new"):
        variants.append(normalize_spaces(normalized_title[:-4]))

    if normalized_title.endswith(" for"):
        variants.append(normalize_spaces(normalized_title[:-4]))

    edition_stripped = normalized_title
    for phrase in EDITION_EQUIVALENCE_PHRASES:
        edition_stripped = re.sub(rf"\b{re.escape(phrase)}\b", " ", edition_stripped)
    edition_stripped = normalize_spaces(edition_stripped)
    if edition_stripped and edition_stripped != normalized_title:
        variants.append(edition_stripped)

    return list(dict.fromkeys(variant for variant in variants if variant))


def detected_systems_from_title(title: str | None) -> list[str]:
    if not title:
        return []

    text = title.lower()
    systems = []
    for system in SYSTEM_COMPATIBLE_RESELLER_INDEXES:
        aliases = SYSTEM_COMPATIBLE_RESELLER_INDEXES[system]
        if any(
            re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", text)
            for alias in aliases
        ):
            systems.append(system)
    if re.search(r"\bxbox\s+one\s*/\s*series\s+s\s*/\s*x\b", text) or re.search(
        r"\bseries\s+s\s*/\s*x\b",
        text,
    ):
        systems.extend(["Xbox One", "Xbox Series X", "Xbox Series S"])
    if "xbox one" in text and "xbox series x" in text:
        systems.extend(["Xbox One", "Xbox Series X", "Xbox Series S"])
    return list(dict.fromkeys(systems))


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


def clean_text(value) -> str | None:
    if value is None:
        return None
    text = normalize_spaces(str(value))
    return text or None


def normalize_asin(value) -> str | None:
    text = clean_text(value)
    return text.upper() if text else None


def cents_to_money(value) -> Decimal | None:
    if value is None:
        return None
    try:
        cents = Decimal(str(value))
    except InvalidOperation:
        return None
    if cents <= 0:
        return None
    return (cents / Decimal("100")).quantize(Decimal("0.01"))


def first_money(*values) -> Decimal | None:
    for value in values:
        money = parse_money(value)
        if money is not None and money > 0:
            return money.quantize(Decimal("0.01"))
    return None


def highest_money(*values) -> Decimal | None:
    valid_values = [
        money
        for value in values
        if (money := parse_money(value)) is not None and money > 0
    ]
    if not valid_values:
        return None
    return max(valid_values).quantize(Decimal("0.01"))


def chunked(values, size):
    for index in range(0, len(values), size):
        yield values[index:index + size]


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
        raw_title = clean_catalog_title(row.get("Title"))
        target_price = parse_money(row.get("BuyBox Price"))
        row_date = parse_revseller_date(row.get("Today's Date"))

        if not asin or not raw_title:
            continue

        rev_system = detect_system_from_title(raw_title)
        index_systems = list(
            dict.fromkeys(
                system
                for system in [rev_system, *detected_systems_from_title(raw_title)]
                if system
            )
        )
        norm_title = normalize_title(raw_title)

        if not norm_title:
            continue

        for rev_system in index_systems or [None]:
            cleaned_rows.append(
                {
                    "asin": asin,
                    "raw_title": raw_title,
                    "amazon_title": raw_title,
                    "normalized_title": norm_title,
                    "system": rev_system,
                    "target_price": target_price,
                    "row_date": row_date,
                    "source": "revseller",
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

        amazon_title = clean_text(row.get("amazon_title"))
        raw_title = normalize_spaces(str(row.get("source_title") or amazon_title or normalized_title))

        rows.append(
            {
                "asin": asin,
                "raw_title": raw_title,
                "amazon_title": amazon_title,
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
    rows_by_system = defaultdict(list)
    compact_rows_by_title_system = defaultdict(list)
    token_rows_by_title_system = defaultdict(list)

    for row in rows:
        title_key = row["normalized_title"]
        system_key = row["system"]

        if system_key:
            rows_by_system[system_key].append(row)
            for title_variant in normalized_title_variants(title_key):
                compound_key = (title_variant, system_key)

                existing = by_title_system.get(compound_key)
                if existing is None or row["row_date"] >= existing["row_date"]:
                    by_title_system[compound_key] = row

                compact_key = compact_title_key(title_variant)

                if compact_key:
                    compact_rows_by_title_system[(compact_key, system_key)].append(row)

                token_key = token_set_key(title_variant)

                if token_key:
                    token_rows_by_title_system[(token_key, system_key)].append(row)

        by_title[title_key].append(row)

    ambiguous_titles = {
        title_key
        for title_key, title_rows in by_title.items()
        if len({row["system"] for row in title_rows if row["system"]}) > 1
    }

    by_compact_title_system = {}
    ambiguous_compact_title_system = set()
    by_token_title_system = {}
    ambiguous_token_title_system = set()

    for compound_key, compact_rows in compact_rows_by_title_system.items():
        unique_asins = {row["asin"] for row in compact_rows}

        if len(unique_asins) > 1:
            ambiguous_compact_title_system.add(compound_key)
            continue

        by_compact_title_system[compound_key] = max(
            compact_rows,
            key=lambda row: row["row_date"],
        )

    for compound_key, token_rows in token_rows_by_title_system.items():
        unique_asins = {row["asin"] for row in token_rows}

        if len(unique_asins) > 1:
            ambiguous_token_title_system.add(compound_key)
            continue

        by_token_title_system[compound_key] = max(
            token_rows,
            key=lambda row: row["row_date"],
        )

    return (
        by_title_system,
        ambiguous_titles,
        by_title,
        by_compact_title_system,
        ambiguous_compact_title_system,
        by_token_title_system,
        ambiguous_token_title_system,
        rows_by_system,
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
            .select(
                "item_id,title,amazon_title,system,asin,target_price,"
                "current_status,exclude_from_purchase_reporting"
            )
            .range(offset, offset + PURCHASE_ITEMS_PAGE_SIZE - 1)
        )

        if not ALLOW_REENRICHMENT:
            query = query.is_("asin", "null")

        response = query.execute()
        rows = response.data or []

        all_items.extend(
            row
            for row in rows
            if clean_status(row.get("current_status"))
            not in OPEN_PURCHASE_WORK_EXCLUDED_STATUSES
            and not row.get("exclude_from_purchase_reporting")
        )

        if len(rows) < PURCHASE_ITEMS_PAGE_SIZE:
            break

        offset += PURCHASE_ITEMS_PAGE_SIZE

    return all_items


def fill_existing_asin_metadata(supabase, match_rows):
    """Fill missing title/target price for rows that already have a reviewed ASIN."""
    candidates = fetch_existing_asin_metadata_candidates(supabase)
    if not candidates:
        return {"candidates": 0, "updated": 0}

    asins = sorted({normalize_asin(row.get("asin")) for row in candidates if normalize_asin(row.get("asin"))})
    revseller_by_asin = latest_revseller_metadata_by_asin(match_rows)
    keepa_by_asin = fetch_keepa_metadata_by_asin(supabase, asins)
    listing_title_by_asin = fetch_listing_titles_by_asin(supabase, asins)

    updated = 0
    for item in candidates:
        asin = normalize_asin(item.get("asin"))
        if not asin:
            continue

        revseller = revseller_by_asin.get(asin, {})
        keepa = keepa_by_asin.get(asin, {})
        updates = {}

        if should_repair_amazon_title(item):
            title = (
                clean_text(revseller.get("amazon_title"))
                or clean_text(keepa.get("amazon_title"))
                or clean_text(listing_title_by_asin.get(asin))
            )
            if title:
                updates["amazon_title"] = title

        if item.get("target_price") is None:
            target_price = first_money(
                revseller.get("target_price"),
                highest_money(
                    keepa.get("buy_box_price_avg90"),
                    keepa.get("buy_box_price_current"),
                    keepa.get("new_fba_price_current"),
                    keepa.get("new_price_current"),
                ),
            )
            if target_price is not None:
                updates["target_price"] = str(target_price)

        if updates:
            supabase.table("purchase_items").update(updates).eq("item_id", item["item_id"]).execute()
            updated += 1

    return {"candidates": len(candidates), "updated": updated}


def fetch_existing_asin_metadata_candidates(supabase):
    rows = []
    offset = 0

    while True:
        response = (
            supabase.table("purchase_items")
            .select(
                "item_id,asin,amazon_title,target_price,current_status,"
                "exclude_from_purchase_reporting,title"
            )
            .not_.is_("asin", "null")
            .neq("asin", "N/A")
            .range(offset, offset + PURCHASE_ITEMS_PAGE_SIZE - 1)
            .execute()
        )
        data = response.data or []
        rows.extend(
            row
            for row in data
            if clean_status(row.get("current_status"))
            not in OPEN_PURCHASE_WORK_EXCLUDED_STATUSES
            and not row.get("exclude_from_purchase_reporting")
            and (should_repair_amazon_title(row) or row.get("target_price") is None)
        )
        if len(data) < PURCHASE_ITEMS_PAGE_SIZE:
            return rows
        offset += PURCHASE_ITEMS_PAGE_SIZE


def latest_revseller_metadata_by_asin(match_rows):
    by_asin = {}
    for row in match_rows:
        asin = normalize_asin(row.get("asin"))
        if not asin:
            continue
        existing = by_asin.get(asin)
        if existing and row.get("row_date") < existing.get("row_date"):
            continue
        by_asin[asin] = {
            "amazon_title": row.get("amazon_title"),
            "target_price": row.get("target_price"),
            "row_date": row.get("row_date"),
        }
    return by_asin


def fetch_keepa_metadata_by_asin(supabase, asins):
    by_asin = {}
    for batch in chunked(asins, 200):
        response = (
            supabase.table("vw_latest_keepa_product_snapshot")
            .select(
                "asin,title,buy_box_price_avg90_cents,buy_box_price_current_cents,"
                "new_fba_price_current_cents,new_price_current_cents"
            )
            .in_("asin", batch)
            .execute()
        )
        for row in response.data or []:
            asin = normalize_asin(row.get("asin"))
            if not asin:
                continue
            by_asin[asin] = {
                "amazon_title": clean_text(row.get("title")),
                "buy_box_price_avg90": cents_to_money(row.get("buy_box_price_avg90_cents")),
                "buy_box_price_current": cents_to_money(row.get("buy_box_price_current_cents")),
                "new_fba_price_current": cents_to_money(row.get("new_fba_price_current_cents")),
                "new_price_current": cents_to_money(row.get("new_price_current_cents")),
            }
    return by_asin


def fetch_listing_titles_by_asin(supabase, asins):
    by_asin = {}
    for batch in chunked(asins, 200):
        response = (
            supabase.table("vw_latest_amazon_listing_snapshot")
            .select("asin,product_name")
            .in_("asin", batch)
            .execute()
        )
        for row in response.data or []:
            asin = normalize_asin(row.get("asin"))
            title = clean_text(row.get("product_name"))
            if asin and title:
                by_asin[asin] = title
    return by_asin


def should_repair_amazon_title(item) -> bool:
    amazon_title = clean_text(item.get("amazon_title"))
    if not amazon_title:
        return True
    supplier_title = clean_text(item.get("title"))
    return bool(supplier_title and amazon_title.casefold() == supplier_title.casefold())


def update_purchase_item(supabase, item_id, asin, amazon_title, target_price):
    payload = {
        "asin": asin,
    }

    if amazon_title:
        payload["amazon_title"] = amazon_title

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
    by_token_title_system,
    ambiguous_token_title_system,
):
    raw_title = item.get("title") or ""
    normalized_title = normalize_title(raw_title)

    if not normalized_title:
        return None, "skipped_no_match"

    detected_system = normalize_system(item.get("system")) or detect_system_from_title(
        raw_title
    )

    if detected_system:
        for title_variant in normalized_title_variants(normalized_title):
            matched_row = by_title_system.get((title_variant, detected_system))

            if matched_row:
                return matched_row, (
                    "matched_with_system"
                    if title_variant == normalized_title
                    else "matched_condition_variant_with_system"
                )

            compact_key = compact_title_key(title_variant)
            compact_compound_key = (compact_key, detected_system)

            if compact_compound_key in ambiguous_compact_title_system:
                return None, "skipped_ambiguous_compact_system"

            matched_row = by_compact_title_system.get(compact_compound_key)

            if matched_row:
                return matched_row, (
                    "matched_compact_with_system"
                    if title_variant == normalized_title
                    else "matched_condition_variant_with_system"
                )

            token_key = token_set_key(title_variant)
            token_compound_key = (token_key, detected_system)

            if token_compound_key in ambiguous_token_title_system:
                return None, "skipped_ambiguous_token_system"

            matched_row = by_token_title_system.get(token_compound_key)

            if matched_row:
                return matched_row, "matched_token_set_with_system"

        return None, "skipped_no_match"

    if normalized_title in ambiguous_titles:
        return None, "skipped_ambiguous_system"

    if normalized_title in by_title:
        return None, "skipped_no_detected_system"

    return None, "skipped_no_match"


def rank_ai_candidates(item, rows_by_system):
    raw_title = item.get("title") or ""
    normalized_title = normalize_title(raw_title)
    detected_system = normalize_system(item.get("system")) or detect_system_from_title(
        raw_title
    )

    if not normalized_title or not detected_system:
        return []

    candidates = []
    for row in rows_by_system.get(detected_system, []):
        score = max(
            title_similarity(normalized_title, row["normalized_title"]),
            title_similarity(compact_title_key(normalized_title), compact_title_key(row["normalized_title"])),
            title_similarity(token_set_key(normalized_title), token_set_key(row["normalized_title"])),
        )
        if score >= AI_MIN_LOCAL_SCORE:
            candidates.append(
                {
                    "row": row,
                    "score": score,
                }
            )

    candidates.sort(
        key=lambda candidate: (
            candidate["score"],
            candidate["row"]["row_date"],
        ),
        reverse=True,
    )
    return candidates[:AI_CANDIDATE_LIMIT]


def ai_match_purchase_item(item, rows_by_system, ai_client):
    if not ai_client:
        return None, "skipped_ai_disabled", None

    candidates = rank_ai_candidates(item, rows_by_system)
    if not candidates:
        return None, "skipped_ai_no_candidates", None

    try:
        decision = ai_client.choose_match(item, candidates)
    except Exception as exc:
        print(f"AI match review failed for item_id={item.get('item_id')}: {exc}")
        decision = None
    if not decision:
        return None, "skipped_ai_error", None

    if decision.get("decision") != "match":
        return None, "skipped_ai_no_match", decision

    candidate_index = decision.get("candidate_index")
    confidence = parse_decimal(decision.get("confidence")) or Decimal("0")
    if (
        not isinstance(candidate_index, int)
        or candidate_index < 0
        or candidate_index >= len(candidates)
        or confidence < ai_client.confidence_threshold
    ):
        return None, "skipped_ai_low_confidence", decision

    return candidates[candidate_index]["row"], "matched_ai_with_system", decision


class AiMatchClient:
    def __init__(self, *, api_key: str, model: str, confidence_threshold: Decimal):
        self.api_key = api_key
        self.model = model
        self.confidence_threshold = confidence_threshold
        self.cache = {}

    def choose_match(self, item, candidates):
        cache_key = (
            normalize_title(item.get("title")),
            normalize_system(item.get("system")) or detect_system_from_title(item.get("title") or ""),
            tuple((candidate["row"]["asin"], candidate["row"]["normalized_title"]) for candidate in candidates),
        )
        if cache_key in self.cache:
            return self.cache[cache_key]

        payload = self.build_payload(item, candidates)
        decision = self.post_with_retries(payload)
        self.cache[cache_key] = decision
        return decision

    def post_with_retries(self, payload):
        last_error = None
        for attempt in range(3):
            try:
                response = requests.post(
                    "https://api.openai.com/v1/responses",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=45,
                )
                response.raise_for_status()
                return extract_response_json(response.json())
            except requests.HTTPError as exc:
                last_error = exc
                status_code = exc.response.status_code if exc.response is not None else None
                if status_code not in {408, 409, 429, 500, 502, 503, 504}:
                    raise
            except requests.RequestException as exc:
                last_error = exc

            if attempt < 2:
                time.sleep(2 ** attempt)

        raise last_error or RuntimeError("OpenAI request failed.")

    def build_payload(self, item, candidates):
        candidate_payload = []
        for index, candidate in enumerate(candidates):
            row = candidate["row"]
            candidate_payload.append(
                {
                    "candidate_index": index,
                    "asin": row["asin"],
                    "title": row["raw_title"],
                    "normalized_title": row["normalized_title"],
                    "system": row["system"],
                    "local_similarity": round(candidate["score"], 4),
                }
            )

        prompt = {
            "task": "Choose whether an eBay video-game purchase title matches one of the supplied RevSeller catalog candidates.",
            "rules": [
                "Return match only when the purchase is clearly the same game/product as one candidate.",
                "Never match across video-game systems or platforms.",
                "Do not treat lot quantity, sealed/new, CIB, standard edition, or game-only wording as a different product unless it changes the actual game/product.",
                "Do not reject same-platform matches only because one title says Greatest Hits, Platinum Hits, PlayStation Hits, Player's Choice, or Nintendo Selects and the other title omits that reprint label.",
                "Reject bundles, collections, sequels, remasters, DLC, accessories, or ambiguous titles unless the candidate clearly describes the same product.",
                "Choose no_match when uncertain.",
            ],
            "purchase_item": {
                "title": item.get("title") or "",
                "normalized_title": normalize_title(item.get("title") or ""),
                "system": normalize_system(item.get("system")) or detect_system_from_title(item.get("title") or ""),
            },
            "candidates": candidate_payload,
        }

        return {
            "model": self.model,
            "input": [
                {
                    "role": "system",
                    "content": (
                        "You are a conservative product matching reviewer for a resale operations system. "
                        "You output only structured JSON. Prefer no_match over a risky match."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(prompt, ensure_ascii=True),
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "revseller_match_decision",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "decision": {"type": "string", "enum": ["match", "no_match"]},
                            "candidate_index": {"type": "integer"},
                            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                            "reason": {"type": "string"},
                        },
                        "required": ["decision", "candidate_index", "confidence", "reason"],
                    },
                }
            },
        }


def extract_response_json(response_payload):
    for output in response_payload.get("output") or []:
        for content in output.get("content") or []:
            if content.get("type") == "output_text" and content.get("text"):
                return json.loads(content["text"])
    text = response_payload.get("output_text")
    if text:
        return json.loads(text)
    raise RuntimeError("OpenAI response did not include output_text.")


def parse_decimal(value) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def build_ai_client(args):
    if not args.ai_review:
        return None

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("AI match review skipped: OPENAI_API_KEY is not configured.")
        return None

    return AiMatchClient(
        api_key=api_key,
        model=args.ai_model,
        confidence_threshold=Decimal(str(args.ai_confidence_threshold)),
    )


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
        "ai_decision",
        "ai_candidate_index",
        "ai_confidence",
        "ai_reason",
        "matched_asin",
        "matched_title",
        "matched_target_price",
    ]

    with open(DIAGNOSTIC_OUTPUT_PATH, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(diagnostic_rows)

    print(f"Diagnostic CSV written: {DIAGNOSTIC_OUTPUT_PATH}")


def parse_args():
    parser = argparse.ArgumentParser(description="Enrich purchase items from RevSeller sheet matches.")
    parser.add_argument("--ai-review", action="store_true", help="Use OpenAI to review unmatched same-system candidates.")
    parser.add_argument("--ai-model", default=os.getenv("OPENAI_MATCHING_MODEL", DEFAULT_AI_MODEL))
    parser.add_argument("--ai-confidence-threshold", type=str, default=str(AI_CONFIDENCE_THRESHOLD))
    parser.add_argument("--ai-review-limit", type=int, default=AI_REVIEW_LIMIT)
    return parser.parse_args()


def main():
    global REVSELLER_SHEET_ID
    global REVSELLER_WORKSHEET_NAME

    args = parse_args()
    load_dotenv()

    REVSELLER_SHEET_ID = os.getenv("REVSELLER_GOOGLE_SHEET_ID")
    REVSELLER_WORKSHEET_NAME = os.getenv("REVSELLER_WORKSHEET_NAME", "Sheet1")

    print("Starting RevSeller sheet enrichment...")
    print(f"ALLOW_REENRICHMENT: {ALLOW_REENRICHMENT}")
    print(f"AI review enabled: {args.ai_review}")

    supabase = get_supabase_client()
    ai_client = build_ai_client(args)

    revseller_rows = load_revseller_rows()
    print(f"RevSeller usable rows loaded: {len(revseller_rows)}")
    manual_match_rows = load_manual_match_rows(supabase)
    print(f"Manual match rows loaded: {len(manual_match_rows)}")
    match_rows = revseller_rows + manual_match_rows
    existing_asin_metadata = fill_existing_asin_metadata(supabase, match_rows)
    print(
        "Existing ASIN metadata repair: "
        f"{existing_asin_metadata['updated']} updated from "
        f"{existing_asin_metadata['candidates']} candidate rows"
    )

    (
        by_title_system,
        ambiguous_titles,
        by_title,
        by_compact_title_system,
        ambiguous_compact_title_system,
        by_token_title_system,
        ambiguous_token_title_system,
        rows_by_system,
    ) = build_revseller_indexes(match_rows)

    print(f"RevSeller title+system keys: {len(by_title_system)}")
    print(f"RevSeller ambiguous title keys: {len(ambiguous_titles)}")
    print(f"RevSeller compact title+system keys: {len(by_compact_title_system)}")
    print(
        "RevSeller ambiguous compact title+system keys: "
        f"{len(ambiguous_compact_title_system)}"
    )
    print(f"RevSeller token-set title+system keys: {len(by_token_title_system)}")
    print(
        "RevSeller ambiguous token-set title+system keys: "
        f"{len(ambiguous_token_title_system)}"
    )

    purchase_items = fetch_purchase_items(supabase)
    print(f"Purchase items scanned: {len(purchase_items)}")

    counts = {
        "matched_with_system": 0,
        "matched_compact_with_system": 0,
        "matched_condition_variant_with_system": 0,
        "matched_token_set_with_system": 0,
        "matched_ai_with_system": 0,
        "skipped_ambiguous_system": 0,
        "skipped_ambiguous_compact_system": 0,
        "skipped_ambiguous_token_system": 0,
        "skipped_ai_disabled": 0,
        "skipped_ai_no_candidates": 0,
        "skipped_ai_no_match": 0,
        "skipped_ai_low_confidence": 0,
        "skipped_ai_error": 0,
        "skipped_no_match": 0,
        "skipped_no_detected_system": 0,
        "updated": 0,
        "errors": 0,
    }

    diagnostic_rows = []
    ai_reviews_used = 0

    for item in purchase_items:
        matched_row, status = match_purchase_item(
            item,
            by_title_system,
            ambiguous_titles,
            by_title,
            by_compact_title_system,
            ambiguous_compact_title_system,
            by_token_title_system,
            ambiguous_token_title_system,
        )

        ai_decision = None
        if (
            not matched_row
            and ai_client
            and status
            in {
                "skipped_no_match",
                "skipped_ambiguous_compact_system",
                "skipped_ambiguous_token_system",
            }
            and ai_reviews_used < args.ai_review_limit
        ):
            ai_reviews_used += 1
            matched_row, status, ai_decision = ai_match_purchase_item(
                item,
                rows_by_system,
                ai_client,
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
                    "ai_decision": (ai_decision or {}).get("decision"),
                    "ai_candidate_index": (ai_decision or {}).get("candidate_index"),
                    "ai_confidence": (ai_decision or {}).get("confidence"),
                    "ai_reason": (ai_decision or {}).get("reason"),
                }
            )
            continue

        if status == "matched_ai_with_system":
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
                    "ai_decision": (ai_decision or {}).get("decision"),
                    "ai_candidate_index": (ai_decision or {}).get("candidate_index"),
                    "ai_confidence": (ai_decision or {}).get("confidence"),
                    "ai_reason": (ai_decision or {}).get("reason"),
                    "matched_asin": matched_row.get("asin"),
                    "matched_title": matched_row.get("raw_title"),
                    "matched_target_price": matched_row.get("target_price"),
                }
            )

        try:
            update_purchase_item(
                supabase=supabase,
                item_id=item["item_id"],
                asin=matched_row["asin"],
                amazon_title=matched_row.get("amazon_title"),
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
