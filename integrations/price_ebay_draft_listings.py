"""Price eBay draft listings from a Google Sheet.

The sheet is expected to have draft listing titles in column D. This script
uses AI to create a compact eBay sold-search query, writes that query as a
clickable sold-search link in column E, and writes a shipping-inclusive
suggested listing price in column F when sold comps are available.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import statistics
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any
from urllib.parse import urlencode

import gspread
import requests
from dotenv import load_dotenv


DEFAULT_SHEET_ID = "1HIO1960IiDkrRz5ljlh0IIt199ilMxeMwYQO4A7Jto4"
DEFAULT_WORKSHEET_NAME = "Sheet1"
DEFAULT_AI_MODEL = "gpt-4.1-mini"
FINDING_API_URL = "https://svcs.ebay.com/services/search/FindingService/v1"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
USER_AGENT = "MBOP draft pricing/1.0"


@dataclass(frozen=True)
class SoldComp:
    title: str
    item_price: Decimal
    shipping_price: Decimal
    total_price: Decimal
    url: str | None
    sold_at: str | None


def main() -> int:
    args = parse_args()
    load_dotenv()

    worksheet = open_worksheet(args.sheet_id, args.worksheet)
    values = worksheet.get(args.range)
    if not values:
        print("No rows found.")
        return 0

    rows = rows_to_process(values, args.start_row, args.limit, args.only_blank)
    print("Draft pricing")
    print("-------------")
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

        comps = fetch_sold_comps(search_terms, max_results=args.max_comps)
        suggested_price = suggest_price(comps)
        if suggested_price is None:
            print("  Suggested price: -- (no usable sold comps)")
        else:
            print(f"  Suggested price: ${suggested_price}")
            print(f"  Comps used: {len(comps)}")

        updates.append(
            {
                "range": f"E{row_number}:F{row_number}",
                "values": [[
                    f'=HYPERLINK("{escape_formula_string(sold_search_url)}","{escape_formula_string(search_terms)}")',
                    money_text(suggested_price) if suggested_price is not None else "",
                ]],
            }
        )
        time.sleep(args.pause_seconds)

    if not args.apply:
        print("\nDry run complete. Add --apply to write columns E/F.")
        return 0

    if updates:
        worksheet.batch_update(updates, value_input_option="USER_ENTERED")
    print(f"\nUpdated {len(updates)} rows.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Suggest eBay draft prices from sold comps.")
    parser.add_argument("--sheet-id", default=os.getenv("EBAY_DRAFTS_GOOGLE_SHEET_ID", DEFAULT_SHEET_ID))
    parser.add_argument("--worksheet", default=os.getenv("EBAY_DRAFTS_WORKSHEET_NAME", DEFAULT_WORKSHEET_NAME))
    parser.add_argument("--range", default="A1:F1000", help="Bounded sheet range to read.")
    parser.add_argument("--start-row", type=int, default=2)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--only-blank", action="store_true", help="Only process rows where columns E and F are blank.")
    parser.add_argument("--max-comps", type=int, default=30)
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
        if only_blank and (cell(row, 4) or cell(row, 5)):
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


def fetch_sold_comps(search_terms: str, *, max_results: int) -> list[SoldComp]:
    app_id = os.getenv("EBAY_CLIENT_ID")
    if not app_id:
        raise RuntimeError("Missing EBAY_CLIENT_ID.")
    params = {
        "OPERATION-NAME": "findCompletedItems",
        "SERVICE-VERSION": "1.13.0",
        "SECURITY-APPNAME": app_id,
        "RESPONSE-DATA-FORMAT": "JSON",
        "REST-PAYLOAD": "",
        "keywords": search_terms,
        "itemFilter(0).name": "SoldItemsOnly",
        "itemFilter(0).value": "true",
        "itemFilter(1).name": "LocatedIn",
        "itemFilter(1).value": "US",
        "paginationInput.entriesPerPage": str(min(max_results, 100)),
        "sortOrder": "EndTimeSoonest",
    }
    response = requests.get(
        FINDING_API_URL,
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=45,
    )
    if not response.ok:
        print(f"  eBay sold comps unavailable: HTTP {response.status_code}")
        return []

    try:
        payload = response.json()
    except ValueError:
        print("  eBay sold comps unavailable: non-JSON response")
        return []

    root = first(payload.get("findCompletedItemsResponse"))
    ack = first(root.get("ack") if isinstance(root, dict) else None)
    if ack and str(ack).lower() not in {"success", "warning"}:
        print(f"  eBay sold comps unavailable: ack={ack}")
        return []

    search_result = first(root.get("searchResult") if isinstance(root, dict) else None) or {}
    items = search_result.get("item") or []
    comps = [comp for item in items if (comp := map_sold_comp(item))]
    return remove_outliers(comps)


def map_sold_comp(item: dict[str, Any]) -> SoldComp | None:
    selling_status = first(item.get("sellingStatus")) or {}
    price = money_value(first(selling_status.get("currentPrice") or []))
    shipping_info = first(item.get("shippingInfo") or [{}]) or {}
    shipping = first(shipping_info.get("shippingServiceCost") or [])
    shipping_price = money_value(shipping) or Decimal("0")
    if price is None or price <= 0:
        return None
    return SoldComp(
        title=str(first(item.get("title")) or ""),
        item_price=price,
        shipping_price=shipping_price,
        total_price=price + shipping_price,
        url=str(first(item.get("viewItemURL")) or "") or None,
        sold_at=str(first(selling_status.get("timeLeft")) or "") or None,
    )


def money_value(value: Any) -> Decimal | None:
    if isinstance(value, dict):
        value = value.get("__value__")
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def first(value: Any) -> Any:
    if isinstance(value, list):
        return value[0] if value else None
    return value


def remove_outliers(comps: list[SoldComp]) -> list[SoldComp]:
    if len(comps) < 6:
        return comps
    totals = sorted(float(comp.total_price) for comp in comps)
    q1 = statistics.quantiles(totals, n=4, method="inclusive")[0]
    q3 = statistics.quantiles(totals, n=4, method="inclusive")[2]
    iqr = q3 - q1
    low = q1 - 1.5 * iqr
    high = q3 + 1.5 * iqr
    return [comp for comp in comps if low <= float(comp.total_price) <= high]


def suggest_price(comps: list[SoldComp]) -> Decimal | None:
    if not comps:
        return None
    totals = sorted(comp.total_price for comp in comps)
    median = totals[len(totals) // 2] if len(totals) % 2 else (totals[len(totals) // 2 - 1] + totals[len(totals) // 2]) / 2
    # List slightly above median sold landed value, then use familiar eBay pricing.
    target = median * Decimal("1.05")
    return charm_price(target)


def charm_price(value: Decimal) -> Decimal:
    rounded_up = Decimal(str(math.ceil(float(value))))
    return (rounded_up - Decimal("0.01")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


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


def money_text(value: Decimal | None) -> str:
    return "" if value is None else f"${value:,.2f}"


def normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


if __name__ == "__main__":
    raise SystemExit(main())
