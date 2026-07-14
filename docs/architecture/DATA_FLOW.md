# MBOP / ZFI Data Flow

Status: Phase A final
Last updated: 2026-07-14

## 2026-07-14 Verified Boundary Update

The MBOP-to-ZFI migration is complete for legacy MBOP financial-planning
surfaces. Ongoing YNAB, business cash, and business-value history data flows are
ZFI-owned. MBOP no longer produces YNAB snapshots or daily business-value
snapshots; it only exports operational summaries to ZFI.

## Architecture Docs

Start with [README.md](./README.md). This document defines how data moves. See
[SYSTEM_BOUNDARIES.md](./SYSTEM_BOUNDARIES.md) for ownership and
[INTEGRATION_PRINCIPLES.md](./INTEGRATION_PRINCIPLES.md) for integration rules.
Repo-level decisions live in [DECISIONS.md](../../DECISIONS.md), and future work
lives in [ROADMAP.md](../../ROADMAP.md).

## Purpose

This document describes which system owns each important financial or
operational dataset, who consumes it, how it should move, and how long that
movement should last.

Default direction:

```text
MBOP operational facts -> summarized outbound payloads -> ZFI financial meaning
```

MBOP does not pull ZFI personal finance data.

## Data Flows

| Dataset | Source | Owner | Consumer | Transfer mechanism | Lifetime | Notes |
|---|---|---|---|---|---|---|
| YNAB transactions | YNAB API | ZFI | ZFI finance, tax, cash-flow planning | ZFI syncs directly from YNAB. MBOP's old `ynab_business_transactions` table is legacy audit/comparison data until cleanup. | Retired in MBOP; ongoing in ZFI | MBOP no longer runs active YNAB sync. Do not route YNAB data from ZFI back into MBOP. |
| YNAB business cash/category balance | YNAB API Business category | ZFI | ZFI cash planning and business finance views | ZFI syncs directly from YNAB. MBOP's old `ynab_category_balance_snapshots` table is legacy audit/comparison data until cleanup. | Retired in MBOP; ongoing in ZFI | MBOP no longer owns business-cash planning or YNAB category balance snapshots. |
| MBOP inventory value | MBOP purchase, receiving, FBA, Amazon inventory, InventoryLab, and inventory-position records | MBOP | ZFI business value, capital allocation, cash-flow planning | MBOP pushes summaries by period/state through `integrations/push_zfi_business_summary.py`; future snapshots may be pushed if ZFI needs trend fidelity | Ongoing MBOP-to-ZFI summary | MBOP remains source of truth for inventory value and inventory states. ZFI interprets inventory capital in financial context. |
| MBOP item/order profitability | MBOP sales orders, fees, fulfillment costs, COGS, purchase items | MBOP | ZFI profitability reports and Ask Zoltar explanations | Summary push for normal reporting; future scoped drilldown API for item/order detail | Ongoing summary, on-demand detail | MBOP operational profit is not accounting profit or taxable profit. |
| MBOP sales/orders/fees/COGS | Amazon sales/order APIs, Veeqo labels, COGS allocation, MBOP sales profitability jobs | MBOP | ZFI business finance reporting, accounting/tax interpretation | MBOP summary payload with lineage timestamps and completeness flags; scoped drilldown later | Ongoing | MBOP owns sales/order operational records, marketplace fees, fulfillment costs, and COGS layers. |
| MBOP Amazon payout/cash status | Amazon Finance read-only endpoints | MBOP as operational source; ZFI as financial interpreter | ZFI cash/payout view and cash-flow planning | MBOP pushes Amazon available balance, processing transfers, deferred/reserved funds, and timestamps | Ongoing | MBOP keeps Amazon payout/cash source data for operations and export, but no longer reconciles it against MBOP-owned YNAB data. |
| MBOP historical business value snapshots | `business_value_snapshots` from MBOP | MBOP before migration; ZFI after verified backfill | ZFI long-term business value history | One-time backfill/export to ZFI with original dates, components, raw rollup JSON where available, and confidence notes | One-time migration | Clearly label as migrated MBOP history in ZFI. Do not confuse this with ongoing ZFI-computed history. |
| ZFI ongoing business value history | ZFI calculations from MBOP summaries plus ZFI-owned cash/planning data | ZFI | ZFI dashboards, Ask Zoltar, long-term planning | No transfer back to MBOP | Ongoing in ZFI only | After backfill verification, ZFI owns the history. MBOP continues to own operational inputs. |
| ZFI tax returns | ZFI document/tax records | ZFI | ZFI tax planning and Ask Zoltar financial analysis | No transfer to MBOP | Permanent ZFI-only | MBOP must never receive tax return data. |
| ZFI paystubs | ZFI personal finance records | ZFI | ZFI household cash-flow and tax planning | No transfer to MBOP | Permanent ZFI-only | MBOP must never receive paystub data. |
| ZFI receipts | ZFI receipt/expense intelligence | ZFI | ZFI business/personal expense classification, tax support | No transfer to MBOP | Permanent ZFI-only | MBOP may push operational costs it owns, but should not receive ZFI receipt data or category decisions. |
| Plaid investments/liabilities | Plaid via ZFI | ZFI | ZFI net worth and household planning | No transfer to MBOP | Permanent ZFI-only | MBOP should not store investment, liability, mortgage, HELOC, retirement, or household planning data. |
| Future ZFI-to-MBOP drilldown | ZFI or Ask Zoltar user question | MBOP owns returned operational records; ZFI owns question and financial context | ZFI/Ask Zoltar | Scoped MBOP operational APIs, requested only when explaining a financial result | Future on-demand | Pull operational details only when needed. ZFI should not duplicate MBOP operational tables by default. MBOP must not receive ZFI personal finance data during drilldown. |

## Transfer Patterns

### Ongoing Pushes From MBOP To ZFI

Use for:

- Period summaries.
- Inventory value by state.
- Sales, fees, fulfillment cost, COGS, and operational profit summaries.
- Amazon payout/cash status.
- Confidence, timestamp, lineage, and review-status metadata.
- Expanded ZFI finance replacement summaries, currently published as
  `payload_version = business_finance_replacement_v2`, including
  profitability windows, cash position, payout reconciliation, inventory
  capital, loss prevention, top sellers, growth, sourcing, and financial
  readiness.

Mechanism:

- `integrations/push_zfi_business_summary.py`
- ZFI table `public.mbop_business_summaries`
- Upsert on `(source, period_start, period_end)`

### One-Time Migrations

Use for:

- Historical MBOP business value snapshots.

Rules:

- Label migrated rows clearly in ZFI.
- Preserve source dates and source metadata.
- Do not turn one-time migration into an ongoing sync unless a separate design
  says so.

Current MBOP helper:

- `integrations/backfill_zfi_business_value_history.py`
- dry-run by default
- `--apply` required for live writes
- target: ZFI `public.business_value_snapshots`
- source labels: `source_system = 'mbop'` and
  `source_type = 'migrated_mbop_history'`
- not scheduled

### Future On-Demand Drilldown

Use for:

- Explaining a ZFI financial result.
- Showing the MBOP orders, purchase items, returns, inventory states, COGS
  corrections, FBA shipments, shipping labels, or fee details behind a number.

Rules:

- ZFI calls scoped MBOP operational APIs.
- MBOP returns only operational records needed for the question.
- MBOP remains source of truth.
- ZFI does not copy full MBOP operational tables by default.
- MBOP does not receive ZFI personal finance data.
