"""Report eBay purchase units and spend by month for an ad hoc date range."""

from __future__ import annotations

import argparse
import datetime as dt
import os
from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from dotenv import load_dotenv
from supabase import create_client


EXCLUDED_REPORTING_STATUSES = {"cancelled", "return_opened"}


def main() -> int:
    args = parse_args()
    load_dotenv(".env.local")
    supabase_url = required_env("SUPABASE_URL")
    supabase_key = required_env("SUPABASE_SERVICE_ROLE_KEY")
    supabase = create_client(supabase_url, supabase_key)

    start_date = parse_date(args.start)
    end_date = parse_date(args.end)
    if end_date < start_date:
        raise SystemExit("--end must be on or after --start")

    rows = fetch_ebay_purchase_items(
        supabase,
        f"{start_date.isoformat()}T00:00:00Z",
        f"{end_date.isoformat()}T23:59:59Z",
    )
    reportable = monthly_totals(rows, reportable_only=True)
    raw = monthly_totals(rows, reportable_only=False)

    print(f"eBay purchases from {start_date.isoformat()} through {end_date.isoformat()}")
    print()
    print_table(reportable, "Reportable totals")
    if args.raw:
        print()
        print_table(raw, "Raw totals before reporting/status exclusions")
    return 0


def parse_args() -> argparse.Namespace:
    today = dt.date.today()
    parser = argparse.ArgumentParser(
        description="Summarize eBay purchase units and dollars by month."
    )
    parser.add_argument(
        "--start",
        default=dt.date(today.year, 1, 1).isoformat(),
        help="Start date in YYYY-MM-DD format. Defaults to Jan 1 of the current year.",
    )
    parser.add_argument(
        "--end",
        default=today.isoformat(),
        help="End date in YYYY-MM-DD format. Defaults to today.",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Also print raw totals before exclude_from_purchase_reporting/cancelled/return_opened exclusions.",
    )
    return parser.parse_args()


def required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def parse_date(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError as error:
        raise SystemExit(f"Invalid date {value!r}; expected YYYY-MM-DD") from error


def fetch_ebay_purchase_items(supabase, start_iso: str, end_iso: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page_size = 1000
    offset = 0
    while True:
        response = (
            supabase.table("purchase_items")
            .select(
                "item_id,quantity,unit_cost,current_status,exclude_from_purchase_reporting,"
                "purchases!inner(order_date,supplier)"
            )
            .eq("purchases.supplier", "eBay")
            .gte("purchases.order_date", start_iso)
            .lte("purchases.order_date", end_iso)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        data = response.data or []
        rows.extend(data)
        if len(data) < page_size:
            return rows
        offset += page_size


def monthly_totals(rows: list[dict[str, Any]], *, reportable_only: bool) -> dict[str, dict[str, Decimal]]:
    monthly: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: {"units": Decimal("0"), "dollars": Decimal("0")}
    )

    for row in rows:
        if reportable_only and excluded_from_reporting(row):
            continue
        purchase = row.get("purchases") or {}
        month = str(purchase.get("order_date") or "")[:7]
        if not month:
            continue
        quantity = decimal_value(row.get("quantity"))
        unit_cost = decimal_value(row.get("unit_cost"))
        monthly[month]["units"] += quantity
        monthly[month]["dollars"] += quantity * unit_cost

    return monthly


def excluded_from_reporting(row: dict[str, Any]) -> bool:
    return bool(row.get("exclude_from_purchase_reporting")) or normalize_status(
        row.get("current_status")
    ) in EXCLUDED_REPORTING_STATUSES


def normalize_status(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def decimal_value(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def print_table(monthly: dict[str, dict[str, Decimal]], title: str) -> None:
    total_units = Decimal("0")
    total_dollars = Decimal("0")
    print(title)
    print("Month\tUnits\tDollars")
    for month in sorted(monthly):
        units = monthly[month]["units"]
        dollars = money(monthly[month]["dollars"])
        total_units += units
        total_dollars += monthly[month]["dollars"]
        print(f"{month}\t{format_decimal(units)}\t${dollars}")
    print(f"TOTAL\t{format_decimal(total_units)}\t${money(total_dollars)}")


def money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def format_decimal(value: Decimal) -> str:
    if value == value.to_integral_value():
        return str(value.quantize(Decimal("1")))
    return str(value.normalize())


if __name__ == "__main__":
    raise SystemExit(main())
