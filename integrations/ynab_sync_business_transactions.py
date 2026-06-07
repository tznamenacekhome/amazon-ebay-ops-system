"""Sync read-only YNAB Business category transactions into MBOP.

These rows are source data for future P&L, Schedule C, and cash reconciliation
features. The script reads YNAB transaction data and writes only to
ynab_business_transactions.
"""

from __future__ import annotations

import argparse
import logging
import os
from datetime import date, timedelta
from typing import Any

import requests
from dotenv import load_dotenv
from supabase import create_client

LOGGER = logging.getLogger("ynab_sync_business_transactions")
YNAB_BASE_URL = "https://api.ynab.com/v1"
DEFAULT_CATEGORY_NAME = "Business"
DEFAULT_SINCE_DATE = "2026-01-01"
DEFAULT_INCREMENTAL_OVERLAP_DAYS = 14
DEFAULT_TIMEOUT_SECONDS = 30


class YNABTransactionSyncError(RuntimeError):
    """Raised when the YNAB transaction sync cannot safely continue."""


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    load_dotenv()

    try:
        token = get_ynab_token()
        plan = resolve_plan(token, args.plan_name)
        supabase = get_supabase_client() if args.apply or args.incremental else None
        since_date = args.since_date
        if args.incremental:
            since_date = resolve_incremental_since_date(
                supabase,
                plan_id=plan["id"],
                category_name=args.category_name,
                fallback_since_date=args.since_date,
                overlap_days=args.incremental_overlap_days,
            )

        transactions = fetch_business_transactions(
            token,
            plan_id=plan["id"],
            category_name=args.category_name,
            since_date=since_date,
            include_deleted=args.include_deleted,
        )
        rows = [map_transaction(plan, transaction) for transaction in transactions]

        print_summary(
            plan=plan,
            category_name=args.category_name,
            since_date=since_date,
            rows=rows,
            write=args.apply,
        )

        if not args.apply:
            LOGGER.info("Dry run complete. No Supabase writes performed.")
            return 0

        if supabase is None:
            supabase = get_supabase_client()
        upserted = upsert_rows(supabase, rows)
        LOGGER.info("YNAB Business transactions upserted: %s", upserted)
        return 0
    except Exception as error:  # noqa: BLE001 - integration should fail safely
        LOGGER.exception("YNAB Business transaction sync failed safely: %s", error)
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync YNAB Business category transactions into MBOP."
    )
    parser.add_argument(
        "--plan-name",
        default=os.getenv("YNAB_PLAN_NAME"),
        help="YNAB plan/budget name. Defaults to first available plan.",
    )
    parser.add_argument(
        "--category-name",
        default=os.getenv("YNAB_BUSINESS_CATEGORY_NAME", DEFAULT_CATEGORY_NAME),
        help="Only import transactions with this YNAB category name.",
    )
    parser.add_argument(
        "--since-date",
        default=DEFAULT_SINCE_DATE,
        help="Import transactions on or after this YYYY-MM-DD date.",
    )
    parser.add_argument(
        "--include-deleted",
        action="store_true",
        help="Keep deleted YNAB transactions in the local copy.",
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Start from the latest stored matching transaction date minus an overlap window.",
    )
    parser.add_argument(
        "--incremental-overlap-days",
        type=int,
        default=DEFAULT_INCREMENTAL_OVERLAP_DAYS,
        help="Days to reread before the latest stored transaction date in incremental mode.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write matching transactions to Supabase.",
    )
    return parser.parse_args()


def get_ynab_token() -> str:
    token = os.getenv("YNAB_PERSONAL_TOKEN") or os.getenv("YNAB_ACCESS_TOKEN")
    if not token:
        raise YNABTransactionSyncError("Missing YNAB_PERSONAL_TOKEN or YNAB_ACCESS_TOKEN.")
    return token


def get_supabase_client():
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not supabase_url or not supabase_key:
        raise YNABTransactionSyncError(
            "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY environment variable."
        )

    return create_client(supabase_url, supabase_key)


def ynab_get(token: str, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    response = requests.get(
        f"{YNAB_BASE_URL}{path}",
        headers={"Authorization": f"Bearer {token}"},
        params=params,
        timeout=DEFAULT_TIMEOUT_SECONDS,
    )
    if not response.ok:
        raise YNABTransactionSyncError(
            f"YNAB API {path} failed with HTTP {response.status_code}: "
            f"{response.text[:500]}"
        )
    return response.json()


def resolve_plan(token: str, plan_name: str | None) -> dict[str, Any]:
    payload = ynab_get(token, "/plans")
    plans = (payload.get("data") or {}).get("plans") or []
    if not plans:
        raise YNABTransactionSyncError("YNAB returned no plans.")

    if plan_name:
        matches = [
            plan
            for plan in plans
            if (plan.get("name") or "").strip().lower() == plan_name.strip().lower()
        ]
        if len(matches) != 1:
            raise YNABTransactionSyncError(
                f"Expected one YNAB plan named {plan_name!r}, found {len(matches)}."
            )
        return matches[0]

    default_plan = (payload.get("data") or {}).get("default_plan")
    if default_plan:
        return default_plan

    if len(plans) > 1:
        raise YNABTransactionSyncError(
            "Multiple YNAB plans found. Set YNAB_PLAN_NAME or pass --plan-name."
        )

    return plans[0]


def fetch_business_transactions(
    token: str,
    *,
    plan_id: str,
    category_name: str,
    since_date: str,
    include_deleted: bool,
) -> list[dict[str, Any]]:
    payload = ynab_get(
        token,
        f"/plans/{plan_id}/transactions",
        params={"since_date": since_date},
    )
    transactions = (payload.get("data") or {}).get("transactions") or []
    category_key = category_name.strip().lower()
    return [
        transaction
        for transaction in transactions
        if (transaction.get("category_name") or "").strip().lower() == category_key
        and (include_deleted or not transaction.get("deleted"))
    ]


def resolve_incremental_since_date(
    supabase,
    *,
    plan_id: str,
    category_name: str,
    fallback_since_date: str,
    overlap_days: int,
) -> str:
    if supabase is None:
        return fallback_since_date

    result = (
        supabase.table("ynab_business_transactions")
        .select("transaction_date")
        .eq("plan_id", plan_id)
        .eq("category_name", category_name)
        .order("transaction_date", desc=True)
        .limit(1)
        .execute()
    )
    latest = (result.data or [{}])[0].get("transaction_date")
    if not latest:
        return fallback_since_date

    try:
        latest_date = date.fromisoformat(str(latest))
        since = latest_date - timedelta(days=max(overlap_days, 0))
        fallback = date.fromisoformat(fallback_since_date)
        if since < fallback:
            since = fallback
        return since.isoformat()
    except ValueError:
        return fallback_since_date


def map_transaction(plan: dict[str, Any], transaction: dict[str, Any]) -> dict[str, Any]:
    amount_milliunits = int(transaction.get("amount") or 0)
    amount_currency = transaction.get("amount_currency")
    if amount_currency is None:
        amount_currency = round(amount_milliunits / 1000, 2)

    return {
        "plan_id": plan.get("id"),
        "plan_name": plan.get("name"),
        "ynab_transaction_id": transaction.get("id"),
        "transaction_date": transaction.get("date"),
        "account_id": transaction.get("account_id"),
        "account_name": transaction.get("account_name"),
        "payee_id": transaction.get("payee_id"),
        "payee_name": transaction.get("payee_name"),
        "import_payee_name": transaction.get("import_payee_name"),
        "import_payee_name_original": transaction.get("import_payee_name_original"),
        "category_id": transaction.get("category_id"),
        "category_name": transaction.get("category_name"),
        "amount_milliunits": amount_milliunits,
        "amount_currency": round(float(amount_currency), 2),
        "amount_formatted": transaction.get("amount_formatted"),
        "memo": transaction.get("memo"),
        "cleared": transaction.get("cleared"),
        "approved": transaction.get("approved"),
        "deleted": bool(transaction.get("deleted")),
        "flag_color": transaction.get("flag_color"),
        "flag_name": transaction.get("flag_name"),
        "import_id": transaction.get("import_id"),
        "matched_transaction_id": transaction.get("matched_transaction_id"),
        "transfer_account_id": transaction.get("transfer_account_id"),
        "transfer_transaction_id": transaction.get("transfer_transaction_id"),
        "debt_transaction_type": transaction.get("debt_transaction_type"),
        "raw_transaction_json": transaction,
    }


def upsert_rows(supabase, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0

    total = 0
    for chunk in chunks(rows, 500):
        response = (
            supabase.table("ynab_business_transactions")
            .upsert(
                chunk,
                on_conflict="plan_id,ynab_transaction_id",
            )
            .execute()
        )
        total += len(response.data or chunk)
    return total


def chunks(values: list[dict[str, Any]], size: int):
    for index in range(0, len(values), size):
        yield values[index:index + size]


def print_summary(
    *,
    plan: dict[str, Any],
    category_name: str,
    since_date: str,
    rows: list[dict[str, Any]],
    write: bool,
) -> None:
    total_inflow = sum(row["amount_currency"] for row in rows if row["amount_currency"] > 0)
    total_outflow = sum(row["amount_currency"] for row in rows if row["amount_currency"] < 0)
    print("YNAB Business transaction sync write" if write else "YNAB Business transaction dry run")
    print("------------------------------------")
    print(f"Plan: {plan.get('name')} ({plan.get('id')})")
    print(f"Category: {category_name}")
    print(f"Since date: {since_date}")
    print(f"Transactions: {len(rows)}")
    print(f"Inflows: ${total_inflow:,.2f}")
    print(f"Outflows: ${total_outflow:,.2f}")


if __name__ == "__main__":
    raise SystemExit(main())
