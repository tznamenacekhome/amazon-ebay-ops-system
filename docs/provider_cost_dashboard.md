# Provider Cost Dashboard

Status: MVP implemented. Migration `20260719000000` was applied to the linked
Supabase project `froeucjkcepuhgwisped` on 2026-07-19.

The provider-cost dashboard stores and displays provider-native cost and usage
signals for AWS, Supabase, and EasyPost. It does not use bank transactions,
credit-card transactions, manual invoice uploads, or manual cost-entry records.

## Data Sources

Allowed monetary sources:

- `api`: directly returned by a supported provider API.
- `report`: returned by a generated provider report.
- `calculated`: reproducibly calculated from automatically collected provider or
  MBOP records.

`manual` and `invoice_import` are intentionally unsupported.

## Storage

Apply:

```powershell
sql/2026-07-19_mbop_provider_cost_dashboard.sql
```

The migration creates:

- `provider_billing_periods`
- `provider_cost_line_items`
- `provider_usage_snapshots`
- `provider_cost_sync_runs`
- `provider_raw_payloads`

Billing periods are unique by provider, external account, start, end, and cycle
type so reruns update the same period instead of duplicating it.

## Sync Commands

Run all providers:

```powershell
.\.venv\Scripts\python.exe integrations\provider_costs.py --provider all
```

Run one provider:

```powershell
.\.venv\Scripts\python.exe integrations\provider_costs.py --provider aws
.\.venv\Scripts\python.exe integrations\provider_costs.py --provider supabase
.\.venv\Scripts\python.exe integrations\provider_costs.py --provider easypost
```

Scheduler group:

```powershell
.\.venv\Scripts\python.exe run_all_syncs.py --group provider-costs
```

Expected cadence: daily. The dashboard reads only stored database rows and does
not call provider APIs on page load.

## AWS

AWS uses Cost Explorer for the MVP. The selected metric is
`NetUnblendedCost`, chosen because it is a practical Cost Explorer net-cost
metric for expected account cost after discounts/credits represented in Cost
Explorer.

Collected when credentials allow:

- daily current and previous month costs
- cost grouped by AWS service
- current month forecast
- accessible AWS Budgets values

Billing cycle: calendar month, `[first day, first day of next month)`.

Required Python dependency: `boto3`.

Required IAM actions:

- `ce:GetCostAndUsage`
- `ce:GetCostForecast`
- `budgets:DescribeBudgets`
- `sts:GetCallerIdentity`

Environment:

- standard AWS SDK credentials/profile or task role
- optional `AWS_ACCOUNT_ID`
- optional `AWS_COST_REGION` (defaults to `us-east-1`)

## Supabase

Supabase uses only official Management API/account data when configured. If the
organization billing anchor or monetary totals are not automatically returned,
the dashboard leaves Supabase totals unavailable instead of guessing.

Collected when available:

- organization metadata
- project metadata
- billing add-on/config payloads
- API availability/error state
- selected billing add-on price metadata
- calculated monthly run-rate for selected add-ons when Supabase returns price
  amount and interval metadata

Environment:

- `SUPABASE_ACCESS_TOKEN` or `SUPABASE_MANAGEMENT_ACCESS_TOKEN`
- optional `SUPABASE_ORG_SLUG`
- optional `SUPABASE_PROJECT_REF`

Known limitation: Supabase monetary totals are omitted until an official API
returns them or until maintainable pricing inputs plus automatically collected
usage are sufficient for reproducible calculation. Current Supabase monetary
display is a selected add-on monthly run-rate estimate only; it is not an
invoice total and does not include organization plan fees, credits, discounts,
taxes, billing-cycle proration, or usage overages that are not returned by the
collected API payloads.

## EasyPost

MBOP uses EasyPost only for standalone Tracking API usage. The dashboard does
not implement or display postage, labels, rates, insurance, carrier invoices,
shipment adjustments, purchased-label metrics, or rate-shopping savings.

Collected/calculated:

- standalone tracker counts from MBOP `inbound_shipments` rows with
  `easypost_tracker_id`
- tracker fee totals by carrier from automatically collected tracker records
- optional EasyPost wallet balance when returned by the EasyPost API

Billing/usage period: calculated calendar month, clearly marked as calculated.

Tracker pricing is isolated in `integrations/provider_costs.py` with effective
date and source notes. Wallet funding is not counted as tracker expense.

Environment:

- `EASYPOST_API_KEY`

Known limitation: payment-log/report rows and exact wallet reconciliation are
stored only when exposed through supported EasyPost APIs or reports available to
the configured account.

## Dashboard

Open:

```text
/dashboard?view=provider-costs
```

The dashboard displays:

- one summary row per provider
- independent billing/usage periods
- current, forecast, previous, and dollar variance values
- source labels: API, Report, Calculated
- provider breakdown rows
- up to 12 stored periods of history
- sync/error/unavailable states

It deliberately does not display:

- percentage variance
- combined current-cycle total across providers
- optimization recommendations
- anomaly explanations
- raw JSON payloads

## References

- AWS Cost Explorer is the MVP source for AWS billing data.
- Supabase Management API supports authenticated organization/project
  management and usage endpoints:
  https://supabase.com/docs/reference/api/introduction
- Supabase billing is organization based:
  https://supabase.com/docs/guides/platform/billing-on-supabase
- EasyPost Tracker API supports standalone trackers:
  https://docs.easypost.com/docs/trackers
- EasyPost tracker overage pricing is documented in Billing & Payments:
  https://support.easypost.com/hc/en-us/articles/360042414212-Billing-Payments
