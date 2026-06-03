"""Sync read-only Amazon Finance balance signals into MBOP.

This integration does not write Amazon orders, customer data, purchases, or
inventory workflow rows. It stores Amazon-held cash and Amazon-to-bank transfer
signals in Amazon-specific snapshot tables for dashboard valuation.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
from typing import Any

from dotenv import load_dotenv
from supabase import create_client

from amazon_spapi_client import AmazonSPAPIClient, AmazonSPAPIError

LOGGER = logging.getLogger("amazon_finance_balance_sync")
DEFAULT_LOOKBACK_DAYS = 180
DEFAULT_TRANSACTION_LOOKBACK_DAYS = 60
DEFAULT_COMPLETED_TRANSFER_BRIDGE_DAYS = 2
BATCH_PAGE_LIMIT = 20


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    load_dotenv()

    try:
        client = AmazonSPAPIClient.from_env()
        snapshot = build_finance_snapshot(
            client,
            lookback_days=args.lookback_days,
            transaction_lookback_days=args.transaction_lookback_days,
            completed_transfer_bridge_days=args.completed_transfer_bridge_days,
        )
        print_summary(snapshot, write=args.apply)

        if not args.apply:
            LOGGER.info("Dry run complete. No Supabase writes performed.")
            return 0

        supabase = get_supabase_client()
        supabase.table("amazon_finance_balance_snapshots").insert(snapshot).execute()
        LOGGER.info(
            "Amazon finance balance snapshot inserted: total_cash=%s in_transit=%s",
            snapshot["total_amazon_cash"],
            snapshot["in_transit_to_bank"],
        )
        return 0
    except Exception as error:  # noqa: BLE001 - integration should fail safely
        LOGGER.exception("Amazon finance balance sync failed safely: %s", error)
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync read-only Amazon Finance balance signals into MBOP."
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=DEFAULT_LOOKBACK_DAYS,
        help="Financial event group lookback window. Max 180 days per Amazon API behavior.",
    )
    parser.add_argument(
        "--transaction-lookback-days",
        type=int,
        default=DEFAULT_TRANSACTION_LOOKBACK_DAYS,
        help="Transaction lookback window for deferred cash calculation.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write a finance balance snapshot to Supabase.",
    )
    parser.add_argument(
        "--completed-transfer-bridge-days",
        type=int,
        default=int(os.getenv("AMAZON_COMPLETED_TRANSFER_BRIDGE_DAYS", DEFAULT_COMPLETED_TRANSFER_BRIDGE_DAYS)),
        help=(
            "Keep recently completed Amazon fund transfers in in-transit cash "
            "for this many days so payouts do not disappear before YNAB cash "
            "reflects the deposit."
        ),
    )
    return parser.parse_args()


def get_supabase_client():
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not supabase_url or not supabase_key:
        raise AmazonSPAPIError(
            "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY environment variable."
        )

    return create_client(supabase_url, supabase_key)


def build_finance_snapshot(
    client: AmazonSPAPIClient,
    *,
    lookback_days: int,
    transaction_lookback_days: int,
    completed_transfer_bridge_days: int,
) -> dict[str, Any]:
    financial_event_groups = fetch_financial_event_groups(client, lookback_days)
    transactions = fetch_transactions(client, transaction_lookback_days)

    bridge_cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(
        days=max(completed_transfer_bridge_days, 0)
    )
    open_group_cash = sum(
        money_amount(group.get("OriginalTotal"))
        for group in financial_event_groups
        if group.get("ProcessingStatus") == "Open"
    )
    processing_transfer_groups = [
        group
        for group in financial_event_groups
        if group.get("ProcessingStatus") == "Closed"
        and group.get("FundTransferStatus") == "Processing"
    ]
    completed_transfer_bridge_groups = [
        group
        for group in financial_event_groups
        if is_recent_completed_transfer(group, bridge_cutoff)
    ]
    processing_transfer_cash = sum(
        money_amount(group.get("OriginalTotal"))
        for group in processing_transfer_groups
    )
    completed_transfer_bridge_cash = sum(
        money_amount(group.get("OriginalTotal"))
        for group in completed_transfer_bridge_groups
    )
    in_transit_to_bank = processing_transfer_cash + completed_transfer_bridge_cash
    deferred_cash = sum(
        transaction_amount(transaction)
        for transaction in transactions
        if transaction.get("transactionStatus") == "DEFERRED"
    )
    total_amazon_cash = deferred_cash + open_group_cash
    currency = first_currency(financial_event_groups, transactions)

    notes = (
        "total_amazon_cash is DEFERRED transactions plus Open financial event "
        "group totals. available_to_withdraw is the API Open financial event "
        "group total; Seller Central's withdrawable UI can differ if Amazon "
        "applies additional reserve/availability adjustments not exposed in "
        "these payloads. in_transit_to_bank includes Processing fund transfers "
        "plus recently Succeeded transfers inside the completed-transfer bridge "
        "window so payouts do not disappear before YNAB cash reflects the bank "
        "deposit."
    )

    return {
        "marketplace_id": client.config.marketplace_id,
        "currency": currency,
        "total_amazon_cash": round(total_amazon_cash, 2),
        "available_to_withdraw": round(open_group_cash, 2),
        "in_transit_to_bank": round(in_transit_to_bank, 2),
        "deferred_or_reserved_cash": round(deferred_cash, 2),
        "financial_event_group_count": len(financial_event_groups),
        "transaction_count": len(transactions),
        "raw_financial_event_groups_json": {
            "financialEventGroups": financial_event_groups,
            "inTransitBreakdown": {
                "processingTransferCash": round(processing_transfer_cash, 2),
                "completedTransferBridgeCash": round(completed_transfer_bridge_cash, 2),
                "completedTransferBridgeDays": max(completed_transfer_bridge_days, 0),
                "completedTransferBridgeGroupIds": [
                    group.get("FinancialEventGroupId")
                    for group in completed_transfer_bridge_groups
                ],
            },
        },
        "raw_transactions_json": {
            "transactions": transactions,
        },
        "notes": notes,
    }


def fetch_financial_event_groups(
    client: AmazonSPAPIClient,
    lookback_days: int,
) -> list[dict[str, Any]]:
    lookback_days = min(max(lookback_days, 1), 180)
    end = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=3)
    start = end - dt.timedelta(days=lookback_days)
    payload = client.request(
        "GET",
        "/finances/v0/financialEventGroups",
        params={
            "MaxResultsPerPage": str(BATCH_PAGE_LIMIT),
            "FinancialEventGroupStartedAfter": iso_z(start),
            "FinancialEventGroupStartedBefore": iso_z(end),
        },
    )
    groups = (payload.get("payload") or {}).get("FinancialEventGroupList") or []
    return groups


def is_recent_completed_transfer(
    group: dict[str, Any],
    bridge_cutoff: dt.datetime,
) -> bool:
    if group.get("ProcessingStatus") != "Closed":
        return False
    if group.get("FundTransferStatus") not in {"Succeeded", "Successful"}:
        return False

    transfer_date = parse_amazon_datetime(group.get("FundTransferDate"))
    if not transfer_date:
        return False

    return transfer_date >= bridge_cutoff


def fetch_transactions(
    client: AmazonSPAPIClient,
    transaction_lookback_days: int,
) -> list[dict[str, Any]]:
    start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(
        days=max(transaction_lookback_days, 1)
    )
    params: dict[str, Any] = {
        "postedAfter": iso_z(start),
        "marketplaceId": client.config.marketplace_id,
    }
    transactions: list[dict[str, Any]] = []
    next_token: str | None = None

    while True:
        request_params = {"nextToken": next_token} if next_token else params
        payload = client.request(
            "GET",
            "/finances/2024-06-19/transactions",
            params=request_params,
        )
        container = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
        rows = container.get("transactions") or []
        transactions.extend(rows)
        next_token = container.get("nextToken")
        if not next_token:
            return transactions


def money_amount(value: Any) -> float:
    if not isinstance(value, dict):
        return 0.0
    try:
        return float(value.get("CurrencyAmount") or value.get("amount") or 0)
    except (TypeError, ValueError):
        return 0.0


def transaction_amount(transaction: dict[str, Any]) -> float:
    try:
        return float((transaction.get("totalAmount") or {}).get("currencyAmount") or 0)
    except (TypeError, ValueError):
        return 0.0


def first_currency(
    groups: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
) -> str | None:
    for group in groups:
        currency = (group.get("OriginalTotal") or {}).get("CurrencyCode")
        if currency:
            return currency
    for transaction in transactions:
        currency = (transaction.get("totalAmount") or {}).get("currencyCode")
        if currency:
            return currency
    return None


def parse_amazon_datetime(value: Any) -> dt.datetime | None:
    if not value:
        return None
    text = str(value).strip()
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def iso_z(value: dt.datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def print_summary(snapshot: dict[str, Any], *, write: bool) -> None:
    print("Amazon finance balance sync write" if write else "Amazon finance balance dry run")
    print("-----------------------------------")
    print(f"Marketplace: {snapshot['marketplace_id']}")
    print(f"Currency: {snapshot['currency'] or '--'}")
    print(f"Financial event groups: {snapshot['financial_event_group_count']}")
    print(f"Transactions: {snapshot['transaction_count']}")
    print(f"Total Amazon cash: ${snapshot['total_amazon_cash']:,.2f}")
    print(f"API open/available balance: ${snapshot['available_to_withdraw']:,.2f}")
    print(f"In transit to bank: ${snapshot['in_transit_to_bank']:,.2f}")
    print(f"Deferred/reserved cash: ${snapshot['deferred_or_reserved_cash']:,.2f}")
    breakdown = snapshot["raw_financial_event_groups_json"].get("inTransitBreakdown") or {}
    print(
        "In transit breakdown: "
        f"processing ${breakdown.get('processingTransferCash', 0):,.2f}; "
        f"recent completed bridge ${breakdown.get('completedTransferBridgeCash', 0):,.2f} "
        f"({breakdown.get('completedTransferBridgeDays', 0)} days)"
    )


if __name__ == "__main__":
    raise SystemExit(main())
