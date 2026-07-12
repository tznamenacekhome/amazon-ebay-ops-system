from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from dotenv import load_dotenv
from supabase import create_client


DEFAULT_EXCLUDED_KEYWORDS = [
    "download",
    "gamesharing",
    "message delivery",
    "nfr",
    "no game",
    "not a game",
    "not for resale",
    "steam",
    "vpn",
    "disc only",
]


@dataclass(frozen=True)
class SourcingSettings:
    setting_id: str | None
    min_amazon_price: float
    min_roi_percent: float
    min_profit_dollars: float
    sales_lookback_days: int
    inventory_need_months_threshold: float
    buyer_zip: str
    buyer_country: str
    item_location_countries: list[str]
    delivery_country: str
    best_offer_min_ask_percent: float
    excluded_keywords: list[str]


def load_environment() -> None:
    load_dotenv(".env")
    load_dotenv(".env.local")


def get_supabase_client():
    load_environment()
    return create_client(required_env("SUPABASE_URL"), required_env("SUPABASE_SERVICE_ROLE_KEY"))


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def fetch_settings(supabase) -> SourcingSettings:
    response = (
        supabase.table("sourcing_settings")
        .select("*")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    row = (response.data or [{}])[0]
    return SourcingSettings(
        setting_id=clean_text(row.get("setting_id")) or None,
        min_amazon_price=to_float(row.get("min_amazon_price"), 20.99),
        min_roi_percent=to_float(row.get("min_roi_percent"), 40),
        min_profit_dollars=to_float(row.get("min_profit_dollars"), 5),
        sales_lookback_days=int(to_float(row.get("sales_lookback_days"), 90)),
        inventory_need_months_threshold=to_float(row.get("inventory_need_months_threshold"), 2),
        buyer_zip=clean_text(row.get("buyer_zip")) or "93022",
        buyer_country=clean_text(row.get("buyer_country")) or "US",
        item_location_countries=list(row.get("item_location_countries") or ["US", "CA"]),
        delivery_country=clean_text(row.get("delivery_country")) or "US",
        best_offer_min_ask_percent=to_float(row.get("best_offer_min_ask_percent"), 60),
        excluded_keywords=list(row.get("excluded_keywords") or DEFAULT_EXCLUDED_KEYWORDS),
    )


def paginate_table(
    supabase,
    table_name: str,
    columns: str = "*",
    *,
    page_size: int = 1000,
    max_rows: int | None = None,
    order_column: str | None = None,
    desc: bool = False,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        end = start + page_size - 1
        query = supabase.table(table_name).select(columns)
        if order_column:
            query = query.order(order_column, desc=desc)
        response = query.range(start, end).execute()
        batch = response.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        if max_rows is not None and len(rows) >= max_rows:
            return rows[:max_rows]
        start += page_size
    return rows


def to_float(value: Any, default: float = 0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(Decimal(str(value)))
    except (InvalidOperation, ValueError, TypeError):
        return default


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def money_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    parsed = to_float(value, 0)
    return parsed if parsed != 0 else 0.0


def chunked(rows: list[dict[str, Any]], size: int = 500) -> list[list[dict[str, Any]]]:
    return [rows[index : index + size] for index in range(0, len(rows), size)]
