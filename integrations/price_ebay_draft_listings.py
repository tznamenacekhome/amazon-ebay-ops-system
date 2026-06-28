"""Generate eBay sold-search links for draft listings from a Google Sheet.

The sheet is expected to have draft listing titles in column D. This script
uses AI to create a compact eBay sold-search query, writes that query as a
clickable sold-search link in column E, and leaves pricing columns untouched.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from typing import Any
from urllib.parse import urlencode

import gspread
import requests
from dotenv import load_dotenv


DEFAULT_SHEET_ID = "1HIO1960IiDkrRz5ljlh0IIt199ilMxeMwYQO4A7Jto4"
DEFAULT_WORKSHEET_NAME = "Sheet1"
DEFAULT_AI_MODEL = "gpt-4.1-mini"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"


def main() -> int:
    args = parse_args()
    load_dotenv()

    worksheet = open_worksheet(args.sheet_id, args.worksheet)
    values = worksheet.get(args.range)
    if not values:
        print("No rows found.")
        return 0

    rows = rows_to_process(values, args.start_row, args.limit, args.only_blank)
    print("Draft search links")
    print("------------------")
    print(f"Sheet: {args.sheet_id} / {args.worksheet}")
    print(f"Rows selected: {len(rows)}")
    print(f"Apply: {args.apply}")

    updates: list[dict[str, Any]] = []
    for row_number, row in rows:
        title = cell(row, 3)
        print(f"\nRow {row_number}: {title}")
        search_terms = optimize_search_terms(title, args.ai_model)
        sold_search_url = ebay_sold_search_url(search_terms)
        print(f"  Search: {search_terms}")

        updates.append(
            {
                "range": f"E{row_number}",
                "values": [[
                    f'=HYPERLINK("{escape_formula_string(sold_search_url)}","{escape_formula_string(search_terms)}")',
                ]],
            }
        )
        time.sleep(args.pause_seconds)

    if not args.apply:
        print("\nDry run complete. Add --apply to write column E.")
        return 0

    if updates:
        worksheet.batch_update(updates, value_input_option="USER_ENTERED")
    print(f"\nUpdated {len(updates)} rows.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate eBay sold-search links for draft titles.")
    parser.add_argument("--sheet-id", default=os.getenv("EBAY_DRAFTS_GOOGLE_SHEET_ID", DEFAULT_SHEET_ID))
    parser.add_argument("--worksheet", default=os.getenv("EBAY_DRAFTS_WORKSHEET_NAME", DEFAULT_WORKSHEET_NAME))
    parser.add_argument("--range", default="A1:F1000", help="Bounded sheet range to read.")
    parser.add_argument("--start-row", type=int, default=2)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--only-blank", action="store_true", help="Only process rows where column E is blank.")
    parser.add_argument("--pause-seconds", type=float, default=0.3)
    parser.add_argument("--ai-model", default=os.getenv("OPENAI_DRAFT_PRICING_MODEL", DEFAULT_AI_MODEL))
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def open_worksheet(sheet_id: str, worksheet_name: str):
    credentials_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not credentials_file:
        raise RuntimeError("Missing GOOGLE_APPLICATION_CREDENTIALS.")
    client = gspread.service_account(filename=credentials_file)
    try:
        return client.open_by_key(sheet_id).worksheet(worksheet_name)
    except PermissionError as error:
        service_account = service_account_email(credentials_file)
        raise RuntimeError(
            "Google Sheets service account does not have access to this spreadsheet. "
            f"Share the sheet with {service_account or credentials_file} as Editor, then rerun."
        ) from error


def service_account_email(credentials_file: str) -> str | None:
    try:
        with open(credentials_file, encoding="utf-8") as handle:
            return json.load(handle).get("client_email")
    except (OSError, json.JSONDecodeError):
        return None


def rows_to_process(
    values: list[list[str]],
    start_row: int,
    limit: int,
    only_blank: bool,
) -> list[tuple[int, list[str]]]:
    selected: list[tuple[int, list[str]]] = []
    for row_index, row in enumerate(values, start=1):
        if row_index < start_row:
            continue
        title = cell(row, 3)
        if not title:
            continue
        if only_blank and cell(row, 4):
            continue
        selected.append((row_index, row))
        if len(selected) >= limit:
            break
    return selected


def cell(row: list[str], index: int) -> str:
    return str(row[index]).strip() if index < len(row) else ""


def optimize_search_terms(title: str, model: str) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    fallback = heuristic_search_terms(title)
    if not api_key:
        return fallback

    prompt = (
        "Create the minimum useful eBay sold-search keyword query for this draft listing title. "
        "Keep brand, model, product line, size/capacity, year/edition, and distinguishing nouns. "
        "Remove condition words, filler, color words unless they define the product, and duplicate terms. "
        "Return only JSON with key search_terms. Max 9 words.\n\n"
        f"Title: {title}"
    )
    payload = {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": prompt}],
            }
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "draft_listing_search_terms",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "search_terms": {"type": "string"},
                    },
                    "required": ["search_terms"],
                },
            }
        },
    }
    try:
        response = requests.post(
            OPENAI_RESPONSES_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=45,
        )
        response.raise_for_status()
        data = json.loads(extract_response_text(response.json()))
        terms = normalize_spaces(str(data.get("search_terms") or ""))
        return terms or fallback
    except Exception as error:  # noqa: BLE001 - pricing should continue with fallback
        print(f"  AI fallback used: {error}")
        return fallback


def extract_response_text(payload: dict[str, Any]) -> str:
    if text := payload.get("output_text"):
        return str(text)
    for output in payload.get("output") or []:
        for content in output.get("content") or []:
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                return str(content["text"])
    raise RuntimeError("OpenAI response did not include output text.")


def heuristic_search_terms(title: str) -> str:
    noise = {
        "new",
        "nwt",
        "used",
        "vintage",
        "vtg",
        "rare",
        "nice",
        "black",
        "white",
        "gray",
        "grey",
        "blue",
        "green",
        "red",
        "brown",
        "multicolor",
        "comfort",
    }
    words = re.findall(r"[A-Za-z0-9.&+-]+", title)
    kept: list[str] = []
    for word in words:
        key = word.lower().strip(".")
        if len(key) <= 1 or key in noise:
            continue
        if key not in {existing.lower() for existing in kept}:
            kept.append(word)
        if len(kept) >= 9:
            break
    return normalize_spaces(" ".join(kept)) or normalize_spaces(title)


def ebay_sold_search_url(search_terms: str) -> str:
    return "https://www.ebay.com/sch/i.html?" + urlencode(
        {
            "_nkw": search_terms,
            "LH_Sold": "1",
            "LH_Complete": "1",
            "rt": "nc",
        }
    )


def escape_formula_string(value: str) -> str:
    return value.replace('"', '""')


def normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


if __name__ == "__main__":
    raise SystemExit(main())
