"""Provider-native cost collection for the MBOP provider-cost dashboard.

Sources are intentionally limited to provider APIs, provider reports, and
calculations from automatically collected MBOP/provider records. No banking,
credit-card, manual invoice, or manual cost-entry data is used here.
"""

from __future__ import annotations

import argparse
import calendar
import datetime as dt
import json
import os
import time
import uuid
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable

import requests
from dotenv import load_dotenv
from supabase import create_client

try:
    import boto3
except ImportError:  # pragma: no cover - boto3 is only required for live AWS syncs.
    boto3 = None


PROVIDERS = ("aws", "supabase", "easypost")
AWS_COST_METRIC = "NetUnblendedCost"
USD = "USD"
EASYPOST_TRACKER_PRICING_EFFECTIVE_DATE = "2026-05-11"
EASYPOST_USPS_TRACKER_FEE = Decimal("0.03")
EASYPOST_NON_USPS_TRACKER_FEE = Decimal("0.02")
EASYPOST_PRICING_SOURCE = (
    "EasyPost Billing & Payments support article, updated 2026-05-11: "
    "USPS standalone trackers $0.03; non-USPS standalone trackers $0.02."
)


@dataclass(frozen=True)
class BillingPeriod:
    start: dt.date
    end: dt.date
    status: str
    cycle_type: str
    source: str


@dataclass(frozen=True)
class EasyPostWalletReconciliation:
    opening_balance: Decimal | None
    funding_and_credits: Decimal
    tracker_charges_and_debits: Decimal
    other_debits: Decimal
    closing_balance: Decimal | None
    unreconciled_difference: Decimal | None


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def iso_now() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


def money(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    except Exception:
        return None


def money_str(value: Any) -> str | None:
    parsed = money(value)
    return str(parsed) if parsed is not None else None


def month_start(value: dt.date) -> dt.date:
    return dt.date(value.year, value.month, 1)


def add_months(value: dt.date, months: int) -> dt.date:
    month = value.month - 1 + months
    year = value.year + month // 12
    month = month % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return dt.date(year, month, day)


def calendar_month_periods(today: dt.date | None = None) -> tuple[BillingPeriod, BillingPeriod]:
    today = today or utc_now().date()
    current_start = month_start(today)
    current_end = add_months(current_start, 1)
    previous_start = add_months(current_start, -1)
    return (
        BillingPeriod(current_start, current_end, "current", "calendar_month", "api"),
        BillingPeriod(previous_start, current_start, "completed", "calendar_month", "api"),
    )


def calculated_month_periods(today: dt.date | None = None) -> tuple[BillingPeriod, BillingPeriod]:
    current, previous = calendar_month_periods(today)
    return (
        BillingPeriod(current.start, current.end, current.status, "calculated_calendar_month", "calculated"),
        BillingPeriod(previous.start, previous.end, previous.status, "calculated_calendar_month", "calculated"),
    )


def dollar_variance(current: Any, previous: Any) -> Decimal | None:
    current_money = money(current)
    previous_money = money(previous)
    if current_money is None or previous_money is None:
        return None
    return money(current_money - previous_money)


def tracker_fee_for_carrier(carrier: str | None) -> Decimal:
    normalized = (carrier or "").strip().lower()
    if normalized == "usps":
        return EASYPOST_USPS_TRACKER_FEE
    return EASYPOST_NON_USPS_TRACKER_FEE


def average_tracker_cost(total: Any, count: int | None) -> Decimal | None:
    total_money = money(total)
    if total_money is None or count is None or count <= 0:
        return None
    return money(total_money / Decimal(count))


def reconcile_easypost_wallet(
    *,
    opening_balance: Any,
    funding_and_credits: Any,
    tracker_charges_and_debits: Any,
    other_debits: Any = 0,
    closing_balance: Any,
) -> EasyPostWalletReconciliation:
    opening = money(opening_balance)
    funding = money(funding_and_credits) or Decimal("0.0000")
    tracker_debits = money(tracker_charges_and_debits) or Decimal("0.0000")
    other = money(other_debits) or Decimal("0.0000")
    closing = money(closing_balance)
    if opening is None or closing is None:
        difference = None
    else:
        expected = opening + funding - tracker_debits - other
        difference = money(closing - expected)
    return EasyPostWalletReconciliation(opening, funding, tracker_debits, other, closing, difference)


class ProviderCostSync:
    def __init__(self, supabase_client):
        self.supabase = supabase_client

    def sync_all(self, providers: Iterable[str] = PROVIDERS) -> dict[str, str]:
        results: dict[str, str] = {}
        for provider in providers:
            try:
                if provider == "aws":
                    self.sync_aws()
                elif provider == "supabase":
                    self.sync_supabase()
                elif provider == "easypost":
                    self.sync_easypost()
                else:
                    raise ValueError(f"Unsupported provider: {provider}")
                results[provider] = "ok"
            except Exception as exc:  # noqa: BLE001 - each provider failure is isolated.
                results[provider] = f"failed: {safe_error(exc)}"
        return results

    def sync_aws(self) -> None:
        run_id = self.start_run("aws", source_type="api")
        records_read = 0
        records_written = 0
        try:
            if boto3 is None:
                raise RuntimeError("boto3 is required for AWS Cost Explorer sync.")
            ce = boto3.client("ce", region_name=os.getenv("AWS_COST_REGION", "us-east-1"))
            budgets = boto3.client("budgets", region_name=os.getenv("AWS_COST_REGION", "us-east-1"))
            account_id = aws_account_id()
            current, previous = calendar_month_periods()
            periods = [previous, current]
            period_ids: dict[str, str] = {}
            for period in periods:
                query_end = min(period.end, utc_now().date() + dt.timedelta(days=1))
                response = ce.get_cost_and_usage(
                    TimePeriod={"Start": period.start.isoformat(), "End": query_end.isoformat()},
                    Granularity="DAILY",
                    Metrics=[AWS_COST_METRIC],
                    GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
                )
                period_total = sum_aws_results(response)
                period_id = self.upsert_period(
                    provider="aws",
                    external_account_id=account_id,
                    period=period,
                    currency=first_aws_currency(response),
                    coverage_status="partial" if period.status == "current" else "complete",
                    provider_reported_total=period_total,
                    metadata={"aws_metric": AWS_COST_METRIC},
                )
                period_ids[period.status] = period_id
                rows = aws_line_items(period_id, period, response)
                records_read += len(rows)
                records_written += self.replace_period_line_items(period_id, rows)
                self.store_raw_payload("aws", account_id, f"cost-explorer-{period.start}", response)

            forecast_total = fetch_aws_forecast(ce, current)
            if forecast_total is not None:
                self.update_period_forecast(period_ids["current"], forecast_total)
            budget_rows = fetch_aws_budgets(budgets, account_id)
            for row in budget_rows:
                self.upsert_usage_snapshot(row)
            records_written += len(budget_rows)
            self.finish_run(run_id, status="ok", records_read=records_read, records_written=records_written)
        except Exception as exc:
            self.finish_run(run_id, status="failed", records_read=records_read, records_written=records_written, error_summary=safe_error(exc))
            raise

    def sync_supabase(self) -> None:
        run_id = self.start_run("supabase", source_type="calculated")
        records_read = 0
        records_written = 0
        try:
            token = os.getenv("SUPABASE_ACCESS_TOKEN") or os.getenv("SUPABASE_MANAGEMENT_ACCESS_TOKEN")
            org_slug = os.getenv("SUPABASE_ORG_SLUG")
            project_ref = os.getenv("SUPABASE_PROJECT_REF") or infer_supabase_project_ref(os.getenv("SUPABASE_URL"))
            account_id = org_slug or project_ref or "default"
            current, previous = unavailable_supabase_periods()
            snapshots: list[dict[str, Any]] = []
            if token:
                snapshots = fetch_supabase_management_snapshots(token, org_slug=org_slug, project_ref=project_ref)
                records_read += len(snapshots)
                for snapshot in snapshots:
                    self.upsert_usage_snapshot(snapshot)
                records_written += len(snapshots)
            else:
                self.upsert_usage_snapshot(
                    {
                        "provider": "supabase",
                        "external_account_id": account_id,
                        "metric_name": "management_api",
                        "metric_value": None,
                        "metric_unit": "unavailable",
                        "source": "api",
                        "raw_metadata": {"reason": "SUPABASE_ACCESS_TOKEN not configured"},
                    }
                )
                records_written += 1

            estimate = supabase_monthly_run_rate_estimate(snapshots)
            for period in (previous, current):
                period_id = self.upsert_period(
                    provider="supabase",
                    external_account_id=account_id,
                    period=period,
                    currency=USD if estimate["total"] is not None else None,
                    coverage_status="partial" if estimate["total"] is not None else "unavailable",
                    forecast_total=estimate["total"] if period.status == "unavailable" and period.start == current.start else None,
                    metadata={
                        "cost_unavailable_reason": (
                            "Supabase invoice totals, credits, discounts, taxes, and actual billing-cycle "
                            "charges were not returned by the Management API in this MVP run."
                        ),
                        "estimate_note": (
                            "forecast_total is a calculated monthly run-rate from Supabase Management API "
                            "billing/addons price metadata for selected project add-ons, not an invoice total."
                            if estimate["total"] is not None
                            else None
                        ),
                    },
                )
                if estimate["line_items"] and period.start == current.start:
                    rows = supabase_estimate_line_items(period_id, current, estimate["line_items"])
                    records_written += self.replace_period_line_items(period_id, rows)
                records_written += 1
            self.finish_run(run_id, status="ok", records_read=records_read, records_written=records_written)
        except Exception as exc:
            self.finish_run(run_id, status="failed", records_read=records_read, records_written=records_written, error_summary=safe_error(exc))
            raise

    def sync_easypost(self) -> None:
        run_id = self.start_run("easypost", source_type="calculated")
        records_read = 0
        records_written = 0
        try:
            current, previous = calculated_month_periods()
            account_id = "default"
            wallet_balance = fetch_easypost_wallet_balance()
            for period in (previous, current):
                trackers = self.fetch_easypost_trackers(period)
                records_read += len(trackers)
                total = sum((tracker_fee_for_carrier(row.get("carrier")) for row in trackers), Decimal("0.0000"))
                period_id = self.upsert_period(
                    provider="easypost",
                    external_account_id=account_id,
                    period=period,
                    currency=USD,
                    coverage_status="partial" if period.status == "current" else "complete",
                    calculated_total=total,
                    metadata={
                        "period_source": "calculated calendar month",
                        "tracker_only": True,
                        "pricing_effective_date": EASYPOST_TRACKER_PRICING_EFFECTIVE_DATE,
                        "pricing_source": EASYPOST_PRICING_SOURCE,
                    },
                )
                rows = easypost_line_items(period_id, period, trackers)
                records_written += self.replace_period_line_items(period_id, rows)
                records_written += self.upsert_easypost_usage_snapshots(account_id, period, trackers, total, wallet_balance)
            self.finish_run(run_id, status="ok", records_read=records_read, records_written=records_written)
        except Exception as exc:
            self.finish_run(run_id, status="failed", records_read=records_read, records_written=records_written, error_summary=safe_error(exc))
            raise

    def fetch_easypost_trackers(self, period: BillingPeriod) -> list[dict[str, Any]]:
        rows = []
        offset = 0
        page_size = 1000
        while True:
            result = (
                self.supabase.table("inbound_shipments")
                .select("inbound_shipment_id,easypost_tracker_id,carrier,last_tracking_sync,created_at,updated_at")
                .not_.is_("easypost_tracker_id", "null")
                .gte("created_at", period.start.isoformat())
                .lt("created_at", period.end.isoformat())
                .range(offset, offset + page_size - 1)
                .execute()
            )
            batch = result.data or []
            rows.extend(batch)
            if len(batch) < page_size:
                break
            offset += page_size
        deduped: dict[str, dict[str, Any]] = {}
        for row in rows:
            tracker_id = row.get("easypost_tracker_id")
            if tracker_id:
                deduped[str(tracker_id)] = row
        return list(deduped.values())

    def start_run(self, provider: str, *, source_type: str) -> str:
        run_id = str(uuid.uuid4())
        self.supabase.table("provider_cost_sync_runs").insert(
            {
                "sync_run_id": run_id,
                "provider": provider,
                "status": "running",
                "started_at": iso_now(),
                "source_type": source_type,
            }
        ).execute()
        return run_id

    def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        records_read: int = 0,
        records_written: int = 0,
        error_summary: str | None = None,
    ) -> None:
        self.supabase.table("provider_cost_sync_runs").update(
            {
                "status": status,
                "finished_at": iso_now(),
                "records_read": records_read,
                "records_written": records_written,
                "error_summary": error_summary,
            }
        ).eq("sync_run_id", run_id).execute()

    def upsert_period(
        self,
        *,
        provider: str,
        external_account_id: str,
        period: BillingPeriod,
        currency: str | None,
        coverage_status: str,
        provider_reported_total: Any = None,
        calculated_total: Any = None,
        forecast_total: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        payload = {
            "provider": provider,
            "external_account_id": external_account_id or "default",
            "period_start": period.start.isoformat(),
            "period_end": period.end.isoformat(),
            "billing_cycle_type": period.cycle_type,
            "period_status": period.status,
            "currency": currency,
            "source": period.source,
            "coverage_status": coverage_status,
            "provider_reported_total": money_str(provider_reported_total),
            "calculated_total": money_str(calculated_total),
            "forecast_total": money_str(forecast_total),
            "last_synchronized_at": iso_now(),
            "metadata": metadata or {},
            "updated_at": iso_now(),
        }
        result = (
            self.supabase.table("provider_billing_periods")
            .upsert(
                payload,
                on_conflict="provider,external_account_id,period_start,period_end,billing_cycle_type",
            )
            .execute()
        )
        row = (result.data or [None])[0]
        if row and row.get("provider_billing_period_id"):
            return row["provider_billing_period_id"]
        lookup = (
            self.supabase.table("provider_billing_periods")
            .select("provider_billing_period_id")
            .eq("provider", provider)
            .eq("external_account_id", external_account_id or "default")
            .eq("period_start", period.start.isoformat())
            .eq("period_end", period.end.isoformat())
            .eq("billing_cycle_type", period.cycle_type)
            .limit(1)
            .execute()
        )
        return lookup.data[0]["provider_billing_period_id"]

    def update_period_forecast(self, period_id: str, forecast_total: Any) -> None:
        self.supabase.table("provider_billing_periods").update(
            {"forecast_total": money_str(forecast_total), "updated_at": iso_now()}
        ).eq("provider_billing_period_id", period_id).execute()

    def replace_period_line_items(self, period_id: str, rows: list[dict[str, Any]]) -> int:
        self.supabase.table("provider_cost_line_items").delete().eq("provider_billing_period_id", period_id).execute()
        if not rows:
            return 0
        self.supabase.table("provider_cost_line_items").insert(rows).execute()
        return len(rows)

    def upsert_usage_snapshot(self, row: dict[str, Any]) -> None:
        payload = {
            "provider": row["provider"],
            "external_account_id": row.get("external_account_id") or "default",
            "project_or_resource_id": row.get("project_or_resource_id"),
            "metric_name": row["metric_name"],
            "metric_value": row.get("metric_value"),
            "metric_unit": row.get("metric_unit"),
            "source": row.get("source") or "api",
            "period_start": row.get("period_start"),
            "period_end": row.get("period_end"),
            "captured_at": row.get("captured_at") or iso_now(),
            "raw_metadata": row.get("raw_metadata") or {},
            "provider_record_id": row.get("provider_record_id"),
        }
        self.supabase.table("provider_usage_snapshots").insert(payload).execute()

    def upsert_easypost_usage_snapshots(
        self,
        account_id: str,
        period: BillingPeriod,
        trackers: list[dict[str, Any]],
        tracker_total: Decimal,
        wallet_balance: Decimal | None,
    ) -> int:
        rows = [
            {
                "provider": "easypost",
                "external_account_id": account_id,
                "metric_name": "standalone_tracker_count",
                "metric_value": len(trackers),
                "metric_unit": "trackers",
                "source": "calculated",
                "period_start": period.start.isoformat(),
                "period_end": period.end.isoformat(),
                "raw_metadata": {"tracker_only": True},
            },
            {
                "provider": "easypost",
                "external_account_id": account_id,
                "metric_name": "tracker_fee_total",
                "metric_value": str(tracker_total),
                "metric_unit": USD,
                "source": "calculated",
                "period_start": period.start.isoformat(),
                "period_end": period.end.isoformat(),
                "raw_metadata": {"funding_not_expense": True},
            },
        ]
        if wallet_balance is not None:
            rows.append(
                {
                    "provider": "easypost",
                    "external_account_id": account_id,
                    "metric_name": "wallet_balance",
                    "metric_value": str(wallet_balance),
                    "metric_unit": USD,
                    "source": "api",
                    "period_start": period.start.isoformat(),
                    "period_end": period.end.isoformat(),
                    "raw_metadata": {"wallet_balance_is_not_tracker_expense": True},
                }
            )
        for row in rows:
            self.upsert_usage_snapshot(row)
        return len(rows)

    def store_raw_payload(self, provider: str, account_id: str, record_id: str, payload: dict[str, Any]) -> None:
        self.supabase.table("provider_raw_payloads").insert(
            {
                "provider": provider,
                "source_type": "api",
                "external_account_id": account_id,
                "provider_record_id": record_id,
                "payload": sanitize_payload(payload),
                "redaction_notes": "Provider payload stored without secrets or signed URLs.",
            }
        ).execute()


def unavailable_supabase_periods(today: dt.date | None = None) -> tuple[BillingPeriod, BillingPeriod]:
    current, previous = calculated_month_periods(today)
    return (
        BillingPeriod(current.start, current.end, "unavailable", "unavailable", "api"),
        BillingPeriod(previous.start, previous.end, "unavailable", "unavailable", "api"),
    )


def aws_account_id() -> str:
    value = os.getenv("AWS_ACCOUNT_ID")
    if value:
        return value
    if boto3 is None:
        return "default"
    try:
        return boto3.client("sts").get_caller_identity().get("Account") or "default"
    except Exception:
        return "default"


def sum_aws_results(response: dict[str, Any]) -> Decimal:
    total = Decimal("0")
    for result in response.get("ResultsByTime", []):
        for group in result.get("Groups", []):
            amount = money(group.get("Metrics", {}).get(AWS_COST_METRIC, {}).get("Amount"))
            if amount is not None:
                total += amount
    return money(total) or Decimal("0.0000")


def first_aws_currency(response: dict[str, Any]) -> str:
    for result in response.get("ResultsByTime", []):
        for group in result.get("Groups", []):
            unit = group.get("Metrics", {}).get(AWS_COST_METRIC, {}).get("Unit")
            if unit:
                return str(unit)
    return USD


def aws_line_items(period_id: str, period: BillingPeriod, response: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in response.get("ResultsByTime", []):
        start = result.get("TimePeriod", {}).get("Start")
        end = result.get("TimePeriod", {}).get("End")
        for group in result.get("Groups", []):
            service = (group.get("Keys") or ["Unclassified"])[0]
            cost = money(group.get("Metrics", {}).get(AWS_COST_METRIC, {}).get("Amount")) or Decimal("0")
            rows.append(
                {
                    "provider_billing_period_id": period_id,
                    "provider": "aws",
                    "category": aws_category_for_service(service),
                    "service": service,
                    "usage_type": AWS_COST_METRIC,
                    "cost": str(cost),
                    "source": period.source,
                    "provider_record_id": f"aws:{period.start}:{start}:{service}",
                    "usage_start": start,
                    "usage_end": end,
                    "raw_metadata": {"aws_metric": AWS_COST_METRIC},
                }
            )
    return rows


def aws_category_for_service(service: str) -> str:
    normalized = service.lower()
    if "tax" in normalized:
        return "taxes"
    if "support" in normalized:
        return "support"
    if "credit" in normalized:
        return "credits"
    if "refund" in normalized:
        return "refunds"
    if "discount" in normalized or "savings plan negation" in normalized:
        return "discounts"
    return "usage"


def fetch_aws_forecast(client: Any, current: BillingPeriod) -> Decimal | None:
    try:
        response = client.get_cost_forecast(
            TimePeriod={"Start": utc_now().date().isoformat(), "End": current.end.isoformat()},
            Metric=AWS_COST_METRIC,
            Granularity="MONTHLY",
        )
        return money(response.get("Total", {}).get("Amount"))
    except Exception:
        return None


def fetch_aws_budgets(client: Any, account_id: str) -> list[dict[str, Any]]:
    try:
        response = client.describe_budgets(AccountId=account_id, MaxResults=20)
    except Exception:
        return []
    rows = []
    for budget in response.get("Budgets", []):
        name = budget.get("BudgetName")
        for field in ("BudgetLimit", "CalculatedSpend"):
            value = budget.get(field)
            rows.append(
                {
                    "provider": "aws",
                    "external_account_id": account_id,
                    "metric_name": f"budget_{field.lower()}",
                    "metric_value": money_str(value.get("Amount")) if isinstance(value, dict) else None,
                    "metric_unit": value.get("Unit") if isinstance(value, dict) else None,
                    "source": "api",
                    "provider_record_id": f"aws-budget:{name}:{field}",
                    "raw_metadata": {"budget_name": name, "field": field},
                }
            )
    return rows


def infer_supabase_project_ref(url: str | None) -> str | None:
    if not url:
        return None
    try:
        host = url.split("//", 1)[-1].split("/", 1)[0]
        return host.split(".")[0] if host.endswith(".supabase.co") else None
    except Exception:
        return None


def fetch_supabase_management_snapshots(token: str, *, org_slug: str | None, project_ref: str | None) -> list[dict[str, Any]]:
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    rows: list[dict[str, Any]] = []
    project_refs: list[str] = []
    if org_slug:
        org = supabase_api_get(f"https://api.supabase.com/v1/organizations/{org_slug}", headers)
        rows.append(supabase_snapshot("organization", org_slug, org))
        projects = supabase_api_get(f"https://api.supabase.com/v1/organizations/{org_slug}/projects?limit=100", headers)
        for project in normalize_supabase_collection(projects):
            ref = project.get("ref") or project.get("id")
            rows.append(supabase_snapshot("project", str(ref or "unknown"), project))
            if ref:
                project_refs.append(str(ref))
    elif project_ref:
        project = supabase_api_get(f"https://api.supabase.com/v1/projects/{project_ref}", headers)
        rows.append(supabase_snapshot("project", project_ref, project))
        project_refs.append(project_ref)
    if project_ref and project_ref not in project_refs:
        project_refs.append(project_ref)
    for ref in project_refs:
        addons = supabase_api_get(f"https://api.supabase.com/v1/projects/{ref}/billing/addons", headers)
        rows.append(supabase_snapshot("billing_addons", ref, addons))
    return rows


def supabase_api_get(url: str, headers: dict[str, str]) -> Any:
    for attempt in range(3):
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 429 and attempt < 2:
            time.sleep(2**attempt)
            continue
        response.raise_for_status()
        return response.json()
    raise RuntimeError(f"Supabase API request failed: {url}")


def normalize_supabase_collection(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("projects", "data", "result"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def supabase_snapshot(metric_name: str, resource_id: str, payload: Any) -> dict[str, Any]:
    return {
        "provider": "supabase",
        "external_account_id": os.getenv("SUPABASE_ORG_SLUG") or "default",
        "project_or_resource_id": resource_id,
        "metric_name": metric_name,
        "metric_value": None,
        "metric_unit": "json",
        "source": "api",
        "provider_record_id": f"supabase:{metric_name}:{resource_id}",
        "raw_metadata": sanitize_payload(payload if isinstance(payload, dict) else {"payload": payload}),
    }


def supabase_monthly_run_rate_estimate(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate only selected add-on run-rate values returned by Supabase APIs.

    This is deliberately not an invoice or billing-cycle total. Supabase invoice
    totals, credits, taxes, discounts, plan subscription fees, overage usage, and
    billing-cycle anchors are not exposed by the Management API data collected
    here, so this function only preserves reproducible configured add-on prices.
    """
    line_items: list[dict[str, Any]] = []
    for snapshot in snapshots:
        if snapshot.get("metric_name") != "billing_addons":
            continue
        project_ref = snapshot.get("project_or_resource_id") or "unknown"
        metadata = snapshot.get("raw_metadata") or {}
        for selected in metadata.get("selected_addons") or []:
            if not isinstance(selected, dict):
                continue
            variant = selected.get("variant") if isinstance(selected.get("variant"), dict) else {}
            price = variant.get("price") if isinstance(variant.get("price"), dict) else {}
            amount = money(price.get("amount"))
            interval = str(price.get("interval") or "").lower()
            price_type = str(price.get("type") or "").lower()
            if amount is None:
                continue
            monthly_cost = None
            quantity = Decimal("1")
            unit = "month"
            if interval == "monthly":
                monthly_cost = amount
            elif interval == "hourly":
                quantity = Decimal("730")
                unit = "hour"
                monthly_cost = amount * quantity
            if monthly_cost is None:
                continue
            line_items.append(
                {
                    "project_ref": project_ref,
                    "addon_type": selected.get("type") or "unknown",
                    "variant_id": variant.get("id") or "unknown",
                    "variant_name": variant.get("name") or variant.get("id") or "Unknown",
                    "price_type": price_type,
                    "interval": interval,
                    "unit_price": amount,
                    "quantity": quantity,
                    "unit": unit,
                    "monthly_cost": money(monthly_cost) or Decimal("0"),
                    "price_description": price.get("description"),
                }
            )
    total = sum((row["monthly_cost"] for row in line_items), Decimal("0"))
    return {
        "total": money(total) if line_items else None,
        "line_items": line_items,
    }


def supabase_estimate_line_items(
    period_id: str,
    period: BillingPeriod,
    line_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in line_items:
        rows.append(
            {
                "provider_billing_period_id": period_id,
                "provider": "supabase",
                "category": "configured_addon_run_rate",
                "subcategory": str(item["addon_type"]),
                "service": f"{item['variant_name']} ({item['variant_id']})",
                "project_or_resource_id": str(item["project_ref"]),
                "usage_type": f"{item['price_type']}_{item['interval']}",
                "quantity": str(item["quantity"]),
                "unit": str(item["unit"]),
                "unit_price": str(item["unit_price"]),
                "cost": str(item["monthly_cost"]),
                "source": "calculated",
                "provider_record_id": (
                    f"supabase:{period.start}:{item['project_ref']}:"
                    f"{item['addon_type']}:{item['variant_id']}"
                ),
                "usage_start": period.start.isoformat(),
                "usage_end": period.end.isoformat(),
                "raw_metadata": {
                    "not_invoice_total": True,
                    "calculation": "Supabase API price amount multiplied by 730 hours for hourly add-ons; monthly fixed add-ons use API price amount.",
                    "price_description": item.get("price_description"),
                },
            }
        )
    return rows


def fetch_easypost_wallet_balance() -> Decimal | None:
    api_key = os.getenv("EASYPOST_API_KEY")
    if not api_key:
        return None
    try:
        response = requests.get("https://api.easypost.com/v2/users", auth=(api_key, ""), timeout=30)
        if response.status_code >= 400:
            return None
        payload = response.json()
        user = payload.get("user") if isinstance(payload, dict) else None
        if isinstance(user, dict):
            return money(user.get("balance") or user.get("wallet_balance"))
    except Exception:
        return None
    return None


def easypost_line_items(period_id: str, period: BillingPeriod, trackers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    by_carrier: dict[str, int] = {}
    for tracker in trackers:
        carrier = str(tracker.get("carrier") or "unknown")
        by_carrier[carrier] = by_carrier.get(carrier, 0) + 1
    for carrier, count in sorted(by_carrier.items()):
        fee = tracker_fee_for_carrier(carrier)
        rows.append(
            {
                "provider_billing_period_id": period_id,
                "provider": "easypost",
                "category": "tracker_fees",
                "subcategory": "standalone_tracker",
                "service": "Tracking API",
                "usage_type": "standalone_tracker",
                "quantity": count,
                "unit": "tracker",
                "unit_price": str(fee),
                "cost": str(money(fee * count) or Decimal("0")),
                "source": "calculated",
                "provider_record_id": f"easypost:{period.start}:{carrier}",
                "usage_start": period.start.isoformat(),
                "usage_end": period.end.isoformat(),
                "raw_metadata": {
                    "carrier": carrier,
                    "pricing_effective_date": EASYPOST_TRACKER_PRICING_EFFECTIVE_DATE,
                    "wallet_funding_not_expense": True,
                },
            }
        )
    return rows


def sanitize_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        sanitized = {}
        for key, value in payload.items():
            lowered = str(key).lower()
            if any(secret in lowered for secret in ("secret", "token", "key", "password", "authorization")):
                sanitized[key] = "[redacted]"
            else:
                sanitized[key] = sanitize_payload(value)
        return sanitized
    if isinstance(payload, list):
        return [sanitize_payload(value) for value in payload]
    return payload


def safe_error(exc: Exception) -> str:
    return " ".join(str(exc).split())[:500]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync provider-native cost data for MBOP.")
    parser.add_argument("--provider", choices=(*PROVIDERS, "all"), default="all")
    parser.add_argument("--list", action="store_true", help="List providers without making API or database calls.")
    return parser.parse_args()


def get_supabase_client():
    load_dotenv()
    load_dotenv(".env.local")
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])


def main() -> int:
    args = parse_args()
    if args.list:
        print("Provider cost syncs")
        for provider in PROVIDERS:
            print(f"- {provider}")
        return 0
    sync = ProviderCostSync(get_supabase_client())
    providers = PROVIDERS if args.provider == "all" else (args.provider,)
    results = sync.sync_all(providers)
    for provider, status in results.items():
        print(f"{provider}: {status}")
    return 0 if all(status == "ok" for status in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
