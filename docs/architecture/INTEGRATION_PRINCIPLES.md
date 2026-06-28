# MBOP / ZFI Integration Principles

Status: Phase A final
Last updated: 2026-06-27

## Architecture Docs

Start with [README.md](./README.md), then read
[SYSTEM_BOUNDARIES.md](./SYSTEM_BOUNDARIES.md) for ownership and
[DATA_FLOW.md](./DATA_FLOW.md) for movement across systems. Repo-level
architecture decisions live in [DECISIONS.md](../../DECISIONS.md), and future
work lives in [ROADMAP.md](../../ROADMAP.md).

# Golden Rules

1. Every important dataset has exactly one owner.

2. Summary before replication.

3. Push operational summaries. Pull operational details only when needed.

4. MBOP owns operations.

5. ZFI owns finance.

6. Evidence first. Meaning second.

7. Every important financial number needs lineage:

- source
- timestamp
- calculation
- confidence
- review status

8. Separate authentication forever.

## Purpose

These principles guide the MBOP-to-ZFI integration and future drilldown work.
They are intentionally conservative because MBOP is an operational system and
ZFI is a personal/business finance system.

## Principles

### One Owner Per Important Dataset

Every important dataset has one system of record.

- MBOP owns operational resale facts.
- ZFI owns financial planning, personal finance, tax, cash-flow planning, and
  ongoing business value history after backfill.

Duplicating ownership creates reconciliation ambiguity. If both systems display
a number, one should be the source and the other should label it as imported,
derived, or interpreted.

### Summary Before Replication

MBOP should push summaries before pushing or replicating detail tables.

Normal ZFI reporting should start from:

- Period summaries.
- Inventory value by operational state.
- Sales/fee/fulfillment/COGS totals.
- Operational profit summaries.
- Amazon cash/payout summaries.
- Source timestamps, confidence, and review status.

Full operational replication is not the default.

### Push Operational Summaries, Pull Operational Details Only When Needed

MBOP should push operational summaries to ZFI.

ZFI and Ask Zoltar may eventually pull operational details from MBOP only when a
user needs to explain a financial result.

Examples:

- Why did profit drop this month?
- Which orders created the fee variance?
- Which inventory states explain this business value change?
- Which returns or COGS corrections affected this period?

The drilldown should be scoped to the question. It should not become a broad
copy of MBOP operational tables.

### Separate Auth Domains

MBOP and ZFI must keep separate auth domains.

- No shared user tables.
- No shared sessions.
- No shared browser credentials.
- No ZFI service-role key in MBOP frontend code.
- MBOP backend/service credentials may write only to approved ZFI import tables.
- ZFI users are not automatically MBOP users.
- MBOP users are not automatically ZFI users.

### No ZFI Personal Finance Readback Into MBOP

MBOP should never receive ZFI personal finance data.

Do not send these categories to MBOP:

- Household net worth.
- Tax returns.
- Paystubs.
- Receipts.
- Plaid investments/liabilities.
- Mortgage, HELOC, retirement, or household planning data.
- YNAB data sourced from ZFI.
- Schedule C decisions.
- Owner draw/contribution planning.
- Ask Zoltar answers containing personal finance context.

### Every Financial Number Needs Lineage

Every financial number exchanged or displayed across this boundary needs:

- Source.
- Timestamp.
- Calculation.
- Confidence.
- Review status.

For example, a ZFI business value card should be able to show whether a number
came from MBOP inventory value, Amazon Finance, YNAB/ZFI business cash, a
one-time MBOP backfill, or a ZFI calculation.

### One-Time Migrations Are Not Ongoing Sync

One-time migrations must be clearly distinguished from ongoing sync.

Example:

- Historical MBOP `business_value_snapshots` should be imported into ZFI as a
  one-time backfill.
- After verification, ZFI owns ongoing business value history.
- MBOP should not keep competing long-term business value history as the
  authoritative financial view.

### Operational Profit Is Not Accounting Profit Or Taxable Profit

MBOP operational profit is a resale operations metric. It can include:

- Sales.
- Marketplace fees.
- Shipping and fulfillment costs.
- COGS.
- Modeled return/refund impact.

ZFI transforms operational facts into:

- Accounting profit.
- Taxable profit.
- Schedule C views.
- Quarterly tax support.
- Owner draw/contribution planning.

MBOP must not become the accounting or tax source of truth.

### ZFI Is The Financial Data Warehouse And Intelligence Layer

ZFI is the financial data warehouse/intelligence layer for:

- YNAB.
- Business cash.
- Household net worth.
- Business value history after backfill.
- Cash-flow planning.
- Accounting/tax interpretation.
- Ask Zoltar financial reasoning.

MBOP is an operational source system feeding ZFI, not a personal finance app.

### Future Ask Zoltar Drilldown Should Be Scoped

Ask Zoltar may eventually drill down into MBOP through scoped operational APIs.

Allowed future pattern:

```text
User asks ZFI / Ask Zoltar a finance question
-> ZFI identifies an MBOP operational summary number
-> ZFI calls a scoped MBOP drilldown endpoint
-> MBOP returns only relevant operational records
-> ZFI explains the financial result
```

ZFI should not duplicate MBOP operational tables by default. MBOP remains the
operational source of truth and should never receive ZFI personal finance data.

## Phase A Guardrails

- Do not implement application code as part of Phase A documentation.
- Do not remove dashboards or jobs.
- Keep MBOP YNAB sync active temporarily for parallel comparison.
- Keep ZFI push outbound-only.
- Keep Amazon payout/cash source collection in MBOP, but plan for ZFI to own
  the broad finance view.

# Architecture Review Rule

Every new feature must answer:

1. Which system owns it?

2. What is the source of truth?

3. Is this operational or financial?

4. Is this evidence or a calculation?

5. Does it create duplicate ownership?

6. Does it cross the MBOP/ZFI boundary?

7. If data crosses systems:

Is it:

- summary

or

- drilldown

If these questions cannot be answered clearly, stop implementation and update
the architecture documentation first.
