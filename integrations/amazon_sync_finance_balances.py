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
DEFAULT_UNMATCHED_COMPLETED_TRANSFER_LOOKBACK_DAYS = 14
COMPLETED_TRANSFER_MATCH_LAG_DAYS = 10
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
        supabase = get_supabase_client()
        snapshot = build_finance_snapshot(
            client,
            supabase,
            lookback_days=args.lookback_days,
            transaction_lookback_days=args.transaction_lookback_days,
            unmatched_completed_transfer_lookback_days=(
                args.unmatched_completed_transfer_lookback_days
            ),
        )
        print_summary(snapshot, write=args.apply)

        if not args.apply:
            LOGGER.info("Dry run complete. No Supabase writes performed.")
            return 0

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
        "--unmatched-completed-transfer-lookback-days",
        type=int,
        default=int(
            os.getenv(
                "AMAZON_UNMATCHED_COMPLETED_TRANSFER_LOOKBACK_DAYS",
                DEFAULT_UNMATCHED_COMPLETED_TRANSFER_LOOKBACK_DAYS,
            )
        ),
        help=(
            "Review completed Amazon fund transfers this many days back and "
            "keep only those without a matching YNAB Business deposit in "
            "in-transit cash."
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
    supabase,
    *,
    lookback_days: int,
    transaction_lookback_days: int,
    unmatched_completed_transfer_lookback_days: int,
) -> dict[str, Any]:
    financial_event_groups = fetch_financial_event_groups(client, lookback_days)
    transactions = fetch_transactions(client, transaction_lookback_days)

    unmatched_lookback_cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(
        days=max(unmatched_completed_transfer_lookback_days, 0)
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
    completed_transfer_groups = [
        group
        for group in financial_event_groups
        if is_completed_transfer(group, unmatched_lookback_cutoff)
    ]
    processing_transfer_cash = sum(
        money_amount(group.get("OriginalTotal"))
        for group in processing_transfer_groups
    )

    ynab_start_date = ynab_transaction_start_date(completed_transfer_groups)
    ynab_transactions = fetch_ynab_business_transactions(supabase, ynab_start_date)
    ynab_matches, unmatched_completed_transfer_groups = match_completed_transfers_to_ynab(
        completed_transfer_groups,
        ynab_transactions,
    )
    ynab_matched_completed_transfer_cash = sum(match["amount"] for match in ynab_matches)
    unmatched_completed_transfer_cash = sum(
        money_amount(group.get("OriginalTotal"))
        for group in unmatched_completed_transfer_groups
    )
    in_transit_to_bank = processing_transfer_cash + unmatched_completed_transfer_cash
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
        "plus completed/succeeded transfers that do not yet have a matching "
        "YNAB Business deposit by amount/date/payee."
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
                "ynabMatchedCompletedTransferCash": round(
                    ynab_matched_completed_transfer_cash,
                    2,
                ),
                "unmatchedCompletedTransferCash": round(
                    unmatched_completed_transfer_cash,
                    2,
                ),
                "unmatchedCompletedTransferLookbackDays": max(
                    unmatched_completed_transfer_lookback_days,
                    0,
                ),
                "ynabBusinessTransactionStartDate": ynab_start_date.isoformat(),
                "ynabMatchedCompletedTransfers": ynab_matches,
                "unmatchedCompletedTransferGroupIds": [
                    group.get("FinancialEventGroupId")
                    for group in unmatched_completed_transfer_groups
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


def is_completed_transfer(
    group: dict[str, Any],
    lookback_cutoff: dt.datetime,
) -> bool:
    if group.get("ProcessingStatus") != "Closed":
        return False
    if group.get("FundTransferStatus") not in {"Succeeded", "Successful"}:
        return False

    transfer_date = parse_amazon_datetime(group.get("FundTransferDate"))
    if not transfer_date:
        return False

    return transfer_date >= lookback_cutoff


def ynab_transaction_start_date(groups: list[dict[str, Any]]) -> dt.date:
    transfer_dates = [
        transfer_date.date()
        for group in groups
        if (transfer_date := parse_amazon_datetime(group.get("FundTransferDate")))
    ]
    if not transfer_dates:
        return dt.date.today() - dt.timedelta(
            days=DEFAULT_UNMATCHED_COMPLETED_TRANSFER_LOOKBACK_DAYS + 1
        )
    return min(transfer_dates) - dt.timedelta(days=1)


def fetch_ynab_business_transactions(
    supabase,
    start_date: dt.date,
) -> list[dict[str, Any]]:
    response = (
        supabase.table("ynab_business_transactions")
        .select(
            "ynab_transaction_id,transaction_date,amount_currency,payee_name,"
            "import_payee_name,import_payee_name_original,memo,account_name,deleted"
        )
        .gte("transaction_date", start_date.isoformat())
        .eq("deleted", False)
        .execute()
    )
    return response.data or []


def match_completed_transfers_to_ynab(
    completed_transfer_groups: list[dict[str, Any]],
    ynab_transactions: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    matches: list[dict[str, Any]] = []
    unmatched_groups: list[dict[str, Any]] = []
    used_ynab_ids: set[str] = set()

    for group in sorted(
        completed_transfer_groups,
        key=lambda value: parse_amazon_datetime(value.get("FundTransferDate"))
        or dt.datetime.min.replace(tzinfo=dt.timezone.utc),
    ):
        amount = round(money_amount(group.get("OriginalTotal")), 2)
        transfer_date = parse_amazon_datetime(group.get("FundTransferDate"))
        if not transfer_date:
            unmatched_groups.append(group)
            continue

        candidates = [
            transaction
            for transaction in ynab_transactions
            if str(transaction.get("ynab_transaction_id")) not in used_ynab_ids
            and is_ynab_amazon_deposit_match(
                transaction,
                transfer_amount=amount,
                transfer_date=transfer_date.date(),
            )
        ]
        if not candidates:
            unmatched_groups.append(group)
            continue

        match = sorted(
            candidates,
            key=lambda transaction: (
                abs(
                    (
                        parse_date(transaction.get("transaction_date"))
                        or transfer_date.date()
                    )
                    - transfer_date.date()
                ).days,
                str(transaction.get("ynab_transaction_id") or ""),
            ),
        )[0]
        used_ynab_ids.add(str(match.get("ynab_transaction_id")))
        matches.append(
            {
                "financialEventGroupId": group.get("FinancialEventGroupId"),
                "fundTransferDate": transfer_date.date().isoformat(),
                "amount": amount,
                "ynabTransactionId": match.get("ynab_transaction_id"),
                "ynabTransactionDate": match.get("transaction_date"),
                "ynabPayee": match.get("payee_name")
                or match.get("import_payee_name")
                or match.get("import_payee_name_original"),
                "ynabAccount": match.get("account_name"),
            }
        )

    return matches, unmatched_groups


def is_ynab_amazon_deposit_match(
    transaction: dict[str, Any],
    *,
    transfer_amount: float,
    transfer_date: dt.date,
) -> bool:
    try:
        ynab_amount = round(float(transaction.get("amount_currency") or 0), 2)
    except (TypeError, ValueError):
        return False

    if abs(ynab_amount - transfer_amount) > 0.01:
        return False

    transaction_date = parse_date(transaction.get("transaction_date"))
    if not transaction_date:
        return False

    if transaction_date < transfer_date - dt.timedelta(days=1):
        return False
    latest_match_date = transfer_date + dt.timedelta(
        days=COMPLETED_TRANSFER_MATCH_LAG_DAYS,
    )
    if transaction_date > latest_match_date:
        return False

    return "amazon" in ynab_match_text(transaction)


def ynab_match_text(transaction: dict[str, Any]) -> str:
    return " ".join(
        str(transaction.get(field) or "")
        for field in (
            "payee_name",
            "import_payee_name",
            "import_payee_name_original",
            "memo",
            "account_name",
        )
    ).lower()


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


def parse_date(value: Any) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


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
        f"completed matched in YNAB "
        f"${breakdown.get('ynabMatchedCompletedTransferCash', 0):,.2f}; "
        f"completed not yet in YNAB "
        f"${breakdown.get('unmatchedCompletedTransferCash', 0):,.2f}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
