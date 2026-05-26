"""Sync read-only YNAB Business category balance into MBOP.

YNAB cash context is stored separately from MBOP workflow data. This script
reads the configured YNAB plan/category and writes a point-in-time category
balance snapshot for dashboard cash-on-hand reporting.
"""

from __future__ import annotations

import argparse
import logging
import os
from typing import Any

import requests
from dotenv import load_dotenv
from supabase import create_client

LOGGER = logging.getLogger("ynab_sync_cash_balance")
YNAB_BASE_URL = "https://api.ynab.com/v1"
DEFAULT_CATEGORY_NAME = "Business"
DEFAULT_TIMEOUT_SECONDS = 30


class YNABSyncError(RuntimeError):
    """Raised when YNAB sync cannot safely continue."""


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    load_dotenv()

    try:
        token = get_ynab_token()
        plan = resolve_plan(token, args.plan_name)
        category_group, category = find_category(token, plan["id"], args.category_name)
        snapshot = build_snapshot(plan, category_group, category)

        print_summary(snapshot, write=args.apply)
        if not args.apply:
            LOGGER.info("Dry run complete. No Supabase writes performed.")
            return 0

        supabase = get_supabase_client()
        supabase.table("ynab_category_balance_snapshots").insert(snapshot).execute()
        LOGGER.info(
            "YNAB category balance snapshot inserted for %s: %s",
            snapshot["category_name"],
            snapshot["balance_formatted"] or snapshot["balance_currency"],
        )
        return 0
    except Exception as error:  # noqa: BLE001 - integration should fail safely
        LOGGER.exception("YNAB cash balance sync failed safely: %s", error)
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync YNAB Business category balance into MBOP."
    )
    parser.add_argument(
        "--plan-name",
        default=os.getenv("YNAB_PLAN_NAME"),
        help="YNAB plan/budget name. Defaults to first available plan.",
    )
    parser.add_argument(
        "--category-name",
        default=os.getenv("YNAB_BUSINESS_CATEGORY_NAME", DEFAULT_CATEGORY_NAME),
        help="YNAB category name to use as MBOP cash on hand.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write a category balance snapshot to Supabase.",
    )
    return parser.parse_args()


def get_ynab_token() -> str:
    token = os.getenv("YNAB_PERSONAL_TOKEN") or os.getenv("YNAB_ACCESS_TOKEN")
    if not token:
        raise YNABSyncError("Missing YNAB_PERSONAL_TOKEN or YNAB_ACCESS_TOKEN.")
    return token


def get_supabase_client():
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not supabase_url or not supabase_key:
        raise YNABSyncError(
            "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY environment variable."
        )

    return create_client(supabase_url, supabase_key)


def ynab_get(token: str, path: str) -> dict[str, Any]:
    response = requests.get(
        f"{YNAB_BASE_URL}{path}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=DEFAULT_TIMEOUT_SECONDS,
    )
    if not response.ok:
        raise YNABSyncError(
            f"YNAB API {path} failed with HTTP {response.status_code}: "
            f"{response.text[:500]}"
        )
    return response.json()


def resolve_plan(token: str, plan_name: str | None) -> dict[str, Any]:
    payload = ynab_get(token, "/plans")
    plans = (payload.get("data") or {}).get("plans") or []
    if not plans:
        raise YNABSyncError("YNAB returned no plans.")

    if plan_name:
        matches = [
            plan
            for plan in plans
            if (plan.get("name") or "").strip().lower() == plan_name.strip().lower()
        ]
        if len(matches) != 1:
            raise YNABSyncError(
                f"Expected one YNAB plan named {plan_name!r}, found {len(matches)}."
            )
        return matches[0]

    default_plan = (payload.get("data") or {}).get("default_plan")
    if default_plan:
        return default_plan

    if len(plans) > 1:
        raise YNABSyncError(
            "Multiple YNAB plans found. Set YNAB_PLAN_NAME or pass --plan-name."
        )

    return plans[0]


def find_category(
    token: str,
    plan_id: str,
    category_name: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = ynab_get(token, f"/plans/{plan_id}/categories")
    groups = (payload.get("data") or {}).get("category_groups") or []
    matches: list[tuple[dict[str, Any], dict[str, Any]]] = []

    for group in groups:
        for category in group.get("categories") or []:
            if (category.get("name") or "").strip().lower() == category_name.strip().lower():
                matches.append((group, category))

    if len(matches) != 1:
        raise YNABSyncError(
            f"Expected one YNAB category named {category_name!r}, found {len(matches)}."
        )

    return matches[0]


def build_snapshot(
    plan: dict[str, Any],
    category_group: dict[str, Any],
    category: dict[str, Any],
) -> dict[str, Any]:
    balance_currency = category.get("balance_currency")
    balance_milliunits = category.get("balance")

    if balance_currency is None and balance_milliunits is not None:
        balance_currency = round(float(balance_milliunits) / 1000, 2)

    return {
        "plan_id": plan.get("id"),
        "plan_name": plan.get("name"),
        "category_group_id": category_group.get("id"),
        "category_group_name": category_group.get("name"),
        "category_id": category.get("id"),
        "category_name": category.get("name"),
        "balance_milliunits": balance_milliunits,
        "balance_currency": balance_currency,
        "balance_formatted": category.get("balance_formatted"),
        "currency_code": category.get("currency_code"),
        "raw_category_json": category,
    }


def print_summary(snapshot: dict[str, Any], *, write: bool) -> None:
    print("YNAB cash balance sync write" if write else "YNAB cash balance dry run")
    print("-------------------------")
    print(f"Plan: {snapshot['plan_name']} ({snapshot['plan_id']})")
    print(
        f"Category: {snapshot['category_group_name']} / "
        f"{snapshot['category_name']} ({snapshot['category_id']})"
    )
    print(f"Balance: {snapshot['balance_formatted'] or snapshot['balance_currency']}")


if __name__ == "__main__":
    raise SystemExit(main())
