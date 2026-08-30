"""Temporary Trading API GetItem fallback for sourcing listing availability.

This is a manual fallback for days when eBay Browse quota is exhausted. The
normal long-term path remains refresh_sourcing_listing_availability.py.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

import requests

from ebay_api_limits import fetch_rate_limits, find_resource_quota
from sourcing_common import get_supabase_client, load_environment, required_env, to_float


TRADING_ENDPOINT = "https://api.ebay.com/ws/api.dll"
COMPATIBILITY_LEVEL = "1423"
SITE_ID = "0"
UNAVAILABLE_DISMISS_REASON = "no_longer_available"
OPERATOR_ACTION_TYPES = {
    "watch",
    "purchased",
    "dismiss",
    "block_asin",
    "mark_valid_match",
    "confirm_exclusion",
    "seller_listing_mismatch",
    "inventory_snoozed",
}
ACTIVE_SOURCING_STATUSES = {"open"}
OUTPUT_SELECTORS = [
    "ItemID",
    "Title",
    "ListingType",
    "Quantity",
    "SellingStatus",
    "ListingDetails",
    "ListingOnHold",
]


@dataclass(frozen=True)
class TradingQuota:
    limit: int | None
    count: int | None
    remaining: int | None
    reset: str | None


@dataclass(frozen=True)
class ListingCheck:
    item_id: str
    status: str
    reason: str
    listing_status: str | None = None
    quantity: int | None = None
    quantity_sold: int | None = None
    available_quantity: int | None = None
    end_time: str | None = None
    ending_reason: str | None = None
    listing_type: str | None = None
    title: str | None = None
    http_status: int | None = None
    ack: str | None = None
    error: str | None = None


def main() -> int:
    args = parse_args()
    load_environment()
    supabase = get_supabase_client()
    quota_before = get_getitem_quota()
    opportunities = fetch_eligible_opportunities(supabase, args.limit)
    item_ids = unique_item_ids(opportunities)
    print(f"Eligible open/unreviewed opportunities: {len(opportunities)}", flush=True)
    print(f"Unique eBay listings to check: {len(item_ids)}", flush=True)
    print(f"Trading GetItem quota before: {quota_before.__dict__}", flush=True)
    if quota_before.remaining is not None and len(item_ids) > quota_before.remaining:
        print(
            f"Trading GetItem quota remaining ({quota_before.remaining}) is lower than unique listings "
            f"to check ({len(item_ids)}); stopping without checks."
        )
        return 2

    token = get_access_token()
    checks: dict[str, ListingCheck] = {}
    for index, item_id in enumerate(item_ids, start=1):
        if index > 1:
            time.sleep(args.pause_seconds)
        checks[item_id] = get_item_availability(token, item_id)
        if index % 25 == 0 or index == len(item_ids):
            print(f"Checked {index}/{len(item_ids)} Trading GetItem listings...", flush=True)

    summary = summarize(opportunities, checks, quota_before)
    summary["applied"] = bool(args.apply)
    dismissals = proposed_dismissals(opportunities, checks)
    print_report(summary, dismissals, args.sample)

    if args.apply:
        dismissed_ids = apply_dismissals(supabase, dismissals, checks)
        quota_after = get_getitem_quota()
        print()
        print("Applied cleanup")
        print("---------------")
        print(f"Dismissed opportunities: {len(dismissed_ids)}")
        print(f"Remaining Trading GetItem quota: {quota_after.remaining}")
        remaining_open = count_remaining_eligible(supabase)
        print(f"Remaining open/unreviewed opportunities: {remaining_open}")
    else:
        print()
        print("Dry run only. Re-run with --apply to dismiss unavailable opportunities.")

    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Trading GetItem fallback availability cleanup for sourcing opportunities.")
    parser.add_argument("--apply", action="store_true", help="Write dismissed/no_longer_available actions.")
    parser.add_argument("--limit", type=int, default=None, help="Optional maximum eligible opportunities to check.")
    parser.add_argument("--pause-seconds", type=float, default=0.15, help="Delay between Trading API calls.")
    parser.add_argument("--sample", type=int, default=20, help="Number of proposed dismissals to print.")
    return parser.parse_args()


def get_getitem_quota() -> TradingQuota:
    try:
        quota = find_resource_quota(fetch_rate_limits(api_context="tradingapi"), "GetItem")
    except Exception as exc:
        print(f"Trading GetItem quota lookup failed: {exc}")
        return TradingQuota(limit=None, count=None, remaining=None, reset=None)
    if quota is None:
        return TradingQuota(limit=None, count=None, remaining=None, reset=None)
    return TradingQuota(limit=quota.limit, count=quota.count, remaining=quota.remaining, reset=quota.reset)


def get_access_token() -> str:
    credentials = f"{required_env('EBAY_CLIENT_ID')}:{required_env('EBAY_CLIENT_SECRET')}"
    response = requests.post(
        "https://api.ebay.com/identity/v1/oauth2/token",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {base64.b64encode(credentials.encode()).decode()}",
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": required_env("EBAY_REFRESH_TOKEN"),
            "scope": "https://api.ebay.com/oauth/api_scope",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def fetch_eligible_opportunities(supabase, limit: int | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0
    page_size = 1000
    while True:
        end = start + page_size - 1
        response = (
            supabase.table("sourcing_opportunities")
            .select(
                "opportunity_id,candidate_id,status,opportunity_type,asin,ebay_item_id,score,ai_flags,matching_diagnostics_json,created_at,"
                "sourcing_ebay_candidates(ebay_item_id,ebay_legacy_item_id,ebay_title,listing_status,auction_end_time)"
            )
            .in_("status", list(ACTIVE_SOURCING_STATUSES))
            .not_.is_("ebay_item_id", "null")
            .order("created_at")
            .range(start, end)
            .execute()
        )
        batch = response.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size

    rows = [row for row in rows if is_displayed_unreviewed(row)]
    rows = exclude_actioned_opportunities(supabase, rows)
    rows = exclude_active_sales_velocity_suppressions(supabase, rows)
    if limit is not None:
        rows = rows[: max(limit, 0)]
    return rows


def is_displayed_unreviewed(row: dict[str, Any]) -> bool:
    if row.get("status") != "open":
        return False
    candidate = row.get("sourcing_ebay_candidates") or {}
    if str(candidate.get("listing_status") or "").strip().lower() == "ended":
        return False
    if has_blocked_diagnostic(row.get("matching_diagnostics_json")):
        return False
    if any(str(flag).startswith("Blocked:") for flag in row.get("ai_flags") or []):
        return False
    return legacy_item_id(row.get("ebay_item_id") or candidate.get("ebay_item_id")) is not None


def exclude_actioned_opportunities(supabase, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ids = [row["opportunity_id"] for row in rows if row.get("opportunity_id")]
    actioned = set()
    for chunk in chunks(ids, 100):
        response = (
            supabase.table("sourcing_actions")
            .select("opportunity_id,action_type")
            .in_("opportunity_id", chunk)
            .execute()
        )
        for action in response.data or []:
            if str(action.get("action_type") or "").lower() in OPERATOR_ACTION_TYPES:
                actioned.add(action.get("opportunity_id"))
    return [row for row in rows if row.get("opportunity_id") not in actioned]


def exclude_active_sales_velocity_suppressions(supabase, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    asins = sorted({str(row.get("asin") or "").upper() for row in rows if row.get("asin")})
    if not asins:
        return rows
    suppressed = set()
    try:
        for chunk in chunks(asins, 100):
            response = (
                supabase.table("sourcing_sales_velocity_suppressions")
                .select("asin")
                .eq("status", "active")
                .in_("asin", chunk)
                .execute()
            )
            suppressed.update(str(row.get("asin") or "").upper() for row in response.data or [])
    except Exception as exc:
        text = str(exc)
        if "sourcing_sales_velocity_suppressions" not in text:
            raise
    return [row for row in rows if str(row.get("asin") or "").upper() not in suppressed]


def has_blocked_diagnostic(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if str(value.get("recommendation") or "") == "Blocked":
        return True
    if has_values(value.get("hard_blocks")) or has_blocked_flags(value.get("flags")):
        return True
    static_rules = value.get("static_rules")
    if isinstance(static_rules, dict):
        if str(static_rules.get("recommendation") or "") == "Blocked":
            return True
        if has_values(static_rules.get("hard_blocks")) or has_blocked_flags(static_rules.get("flags")):
            return True
    return False


def get_item_availability(token: str, item_id: str) -> ListingCheck:
    selector_xml = "\n  ".join(f"<OutputSelector>{selector}</OutputSelector>" for selector in OUTPUT_SELECTORS)
    body = f"""<?xml version="1.0" encoding="utf-8"?>
<GetItemRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <RequesterCredentials>
    <eBayAuthToken>{token}</eBayAuthToken>
  </RequesterCredentials>
  <ItemID>{item_id}</ItemID>
  {selector_xml}
</GetItemRequest>"""
    try:
        response = requests.post(
            TRADING_ENDPOINT,
            headers={
                "Content-Type": "text/xml",
                "X-EBAY-API-CALL-NAME": "GetItem",
                "X-EBAY-API-COMPATIBILITY-LEVEL": COMPATIBILITY_LEVEL,
                "X-EBAY-API-SITEID": SITE_ID,
                "X-EBAY-API-IAF-TOKEN": token,
            },
            data=body,
            timeout=60,
        )
    except requests.RequestException as exc:
        return ListingCheck(item_id=item_id, status="UNKNOWN", reason="request_failed", error=str(exc))
    return parse_get_item_response(item_id, response.status_code, response.text)


def parse_get_item_response(item_id: str, http_status: int, xml_text: str) -> ListingCheck:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        return ListingCheck(item_id=item_id, status="UNKNOWN", reason="xml_parse_error", http_status=http_status, error=str(exc))

    ack = text(root, "Ack")
    if ack not in {"Success", "Warning"}:
        errors = "; ".join(filter(None, [text(error, "LongMessage") or text(error, "ShortMessage") for error in elems(root, "Errors")]))
        return ListingCheck(item_id=item_id, status="UNKNOWN", reason="trading_api_error", http_status=http_status, ack=ack, error=errors[:500] or None)

    item = elem(root, "Item")
    listing_details = elem(item, "ListingDetails")
    selling_status = elem(item, "SellingStatus")
    listing_status = text(selling_status, "ListingStatus")
    quantity = int_or_none(text(item, "Quantity"))
    quantity_sold = int_or_none(text(selling_status, "QuantitySold"))
    available_quantity = quantity - quantity_sold if quantity is not None and quantity_sold is not None else None
    end_time = text(listing_details, "EndTime")
    ending_reason = text(listing_details, "EndingReason")
    listing_on_hold = str(text(selling_status, "ListingOnHold") or text(item, "ListingOnHold") or "").lower() == "true"
    base = {
        "listing_status": listing_status,
        "quantity": quantity,
        "quantity_sold": quantity_sold,
        "available_quantity": available_quantity,
        "end_time": end_time,
        "ending_reason": ending_reason,
        "listing_type": text(item, "ListingType"),
        "title": text(item, "Title"),
        "http_status": http_status,
        "ack": ack,
    }

    normalized_status = str(listing_status or "").strip().lower()
    if listing_on_hold:
        return ListingCheck(item_id=item_id, status="UNAVAILABLE", reason="listing_on_hold", **base)
    if normalized_status in {"completed", "ended"}:
        return ListingCheck(item_id=item_id, status="UNAVAILABLE", reason=f"listing_status_{normalized_status}", **base)
    if normalized_status not in {"active"}:
        return ListingCheck(item_id=item_id, status="UNKNOWN", reason="unknown_listing_status", **base)
    if end_time_has_passed(end_time):
        return ListingCheck(item_id=item_id, status="UNAVAILABLE", reason="end_time_passed", **base)
    if available_quantity is not None and available_quantity <= 0:
        return ListingCheck(item_id=item_id, status="UNAVAILABLE", reason="available_quantity_zero", **base)
    if available_quantity is None:
        return ListingCheck(item_id=item_id, status="UNKNOWN", reason="missing_quantity_signal", **base)
    return ListingCheck(item_id=item_id, status="AVAILABLE", reason="active_with_available_quantity", **base)


def apply_dismissals(supabase, dismissals: list[dict[str, Any]], checks: dict[str, ListingCheck]) -> list[str]:
    now = dt.datetime.now(dt.UTC).isoformat()
    dismissed_ids = []
    for row in dismissals:
        opportunity_id = row["opportunity_id"]
        candidate_id = row.get("candidate_id")
        item_id = row["legacy_item_id"]
        check = checks[item_id]
        candidate_updates: dict[str, Any] = {
            "listing_status": "ended",
            "last_seen_at": now,
            "auction_end_time": check.end_time,
            "available_quantity": max(check.available_quantity or 0, 0),
        }
        if candidate_id:
            supabase.table("sourcing_ebay_candidates").update(candidate_updates).eq("candidate_id", candidate_id).execute()
        supabase.table("sourcing_opportunities").update({"status": "dismissed", "updated_at": now}).eq("opportunity_id", opportunity_id).execute()
        supabase.table("sourcing_actions").insert(
            {
                "opportunity_id": opportunity_id,
                "candidate_id": candidate_id,
                "asin": row.get("asin"),
                "ebay_item_id": row.get("ebay_item_id"),
                "action_type": "dismissed",
                "dismiss_reason": UNAVAILABLE_DISMISS_REASON,
                "notes": f"Trading GetItem fallback cleanup: {check.reason}.",
                "raw_action_context": {
                    "availability_source": "trading_getitem_temporary_fallback",
                    "listing_status": check.listing_status,
                    "quantity": check.quantity,
                    "quantity_sold": check.quantity_sold,
                    "available_quantity": check.available_quantity,
                    "end_time": check.end_time,
                    "ending_reason": check.ending_reason,
                    "checked_at": now,
                },
            }
        ).execute()
        dismissed_ids.append(opportunity_id)
    return dismissed_ids


def proposed_dismissals(opportunities: list[dict[str, Any]], checks: dict[str, ListingCheck]) -> list[dict[str, Any]]:
    rows = []
    for row in opportunities:
        candidate = row.get("sourcing_ebay_candidates") or {}
        item_id = legacy_item_id(row.get("ebay_item_id") or candidate.get("ebay_item_id"))
        check = checks.get(item_id or "")
        if not item_id or not check or check.status != "UNAVAILABLE":
            continue
        rows.append(
            {
                "opportunity_id": row.get("opportunity_id"),
                "candidate_id": row.get("candidate_id"),
                "asin": row.get("asin"),
                "ebay_item_id": row.get("ebay_item_id"),
                "legacy_item_id": item_id,
                "title": candidate.get("ebay_title") or check.title,
                "mbop_status": row.get("status"),
                "opportunity_type": row.get("opportunity_type"),
                "listing_status": check.listing_status,
                "quantity": check.quantity,
                "quantity_sold": check.quantity_sold,
                "available_quantity": check.available_quantity,
                "end_time": check.end_time,
                "ending_reason": check.ending_reason,
                "reason": check.reason,
                "proposed_action": "dismissed/no_longer_available",
            }
        )
    return rows


def summarize(opportunities: list[dict[str, Any]], checks: dict[str, ListingCheck], quota: TradingQuota) -> dict[str, Any]:
    statuses = [check.status for check in checks.values()]
    return {
        "mode": "Trading GetItem temporary fallback",
        "eligible_opportunities": len(opportunities),
        "unique_ebay_items": len(checks),
        "successfully_checked": sum(1 for check in checks.values() if check.ack in {"Success", "Warning"}),
        "available": statuses.count("AVAILABLE"),
        "unavailable": statuses.count("UNAVAILABLE"),
        "unknown": statuses.count("UNKNOWN"),
        "trading_api_errors": sum(1 for check in checks.values() if check.reason in {"trading_api_error", "request_failed", "xml_parse_error"}),
        "proposed_dismissals": len(proposed_dismissals(opportunities, checks)),
        "quota_before": quota.__dict__,
    }


def print_report(summary: dict[str, Any], dismissals: list[dict[str, Any]], sample_size: int) -> None:
    print("Trading GetItem availability dry-run" if not summary.get("applied") else "Trading GetItem availability cleanup")
    print("------------------------------------")
    for key, value in summary.items():
        print(f"{key}: {json.dumps(value) if isinstance(value, dict) else value}")
    print()
    print(f"Representative proposed dismissals ({min(sample_size, len(dismissals))} of {len(dismissals)})")
    print(json.dumps(dismissals[:sample_size], indent=2))


def count_remaining_eligible(supabase) -> int:
    return len(fetch_eligible_opportunities(supabase, None))


def unique_item_ids(opportunities: list[dict[str, Any]]) -> list[str]:
    seen = set()
    output = []
    for row in opportunities:
        candidate = row.get("sourcing_ebay_candidates") or {}
        item_id = legacy_item_id(row.get("ebay_item_id") or candidate.get("ebay_item_id"))
        if item_id and item_id not in seen:
            seen.add(item_id)
            output.append(item_id)
    return output


def legacy_item_id(value: Any) -> str | None:
    text_value = str(value or "").strip()
    if text_value.isdigit():
        return text_value
    if text_value.startswith("v1|"):
        parts = text_value.split("|")
        if len(parts) > 1 and parts[1].isdigit():
            return parts[1]
    return None


def end_time_has_passed(value: str | None) -> bool:
    if not value:
        return False
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.astimezone(dt.UTC) <= dt.datetime.now(dt.UTC)


def elem(parent: ET.Element | None, name: str) -> ET.Element | None:
    if parent is None:
        return None
    for child in parent.iter():
        if strip_ns(child.tag) == name:
            return child
    return None


def elems(parent: ET.Element | None, name: str) -> list[ET.Element]:
    if parent is None:
        return []
    return [child for child in parent.iter() if strip_ns(child.tag) == name]


def text(parent: ET.Element | None, name: str) -> str | None:
    found = elem(parent, name)
    return found.text if found is not None else None


def strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(to_float(value, 0))
    except (TypeError, ValueError):
        return None


def has_values(value: Any) -> bool:
    return isinstance(value, list) and len(value) > 0


def has_blocked_flags(value: Any) -> bool:
    return isinstance(value, list) and any(str(flag).startswith("Blocked:") for flag in value)


def chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


if __name__ == "__main__":
    raise SystemExit(main())
