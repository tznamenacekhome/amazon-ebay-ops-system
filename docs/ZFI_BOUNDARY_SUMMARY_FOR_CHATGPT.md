# MBOP to ZFI Boundary Summary

## 2026-07-14 Status

The replacement is now verified. MBOP has removed active YNAB sync,
business-value snapshot production, and the Financial/Growth planning
dashboards. ZFI owns ongoing financial planning, YNAB, business cash, and
business-value history. MBOP retains operational facts and outbound ZFI summary
pushes.

This note now records the historical MBOP financial-reporting overlap and the
clean boundary with ZoltarFI / ZFI. It is intended as a shareable handoff for
ChatGPT or future planning.

## Historical Overlap

MBOP previously had several finance/reporting surfaces that overlapped with
ZFI:

| Area | Current MBOP files | What it does | Classification |
|---|---|---|---|
| Financial dashboard | `web/app/api/dashboard/financial/route.ts`, `web/app/dashboard/page.tsx` | 30/90/YTD sales, profit, ROI, cash, payout reconciliation, Schedule C placeholder | Retired from MBOP after ZFI verification |
| Business value snapshots | `integrations/business_value_snapshot.py`, `sql/2026-05-26_add_business_value_snapshots.sql` | Total business value from inventory + Amazon cash + YNAB cash | Retired from MBOP; historical rows migrated/available for ZFI |
| YNAB cash balance | `integrations/ynab_sync_cash_balance.py`, `sql/2026-05-26_add_ynab_cash_balance_snapshots.sql` | Pulled YNAB Business category cash into MBOP | Retired from MBOP; ZFI owns YNAB |
| YNAB transactions | `integrations/ynab_sync_business_transactions.py`, `sql/2026-06-03_add_ynab_business_transactions.sql` | Stored Business-category YNAB transaction history for P&L, Schedule C, cash reconciliation planning | Retired from MBOP; ZFI owns YNAB |
| Amazon finance balances | `integrations/amazon_sync_finance_balances.py`, `sql/2026-05-26_add_amazon_finance_balance_snapshots.sql` | Amazon-held cash, funds available, in-transit cash | Keep as operational source, export summary to ZFI |
| Amazon sales profitability | `integrations/amazon_sales_profitability.py`, `web/app/api/sales-orders/route.ts` | Item/order revenue, fees, fulfillment, COGS, net profit, ROI | Keep in MBOP operationally, export aggregates |
| Sales financial events | `sql/2026-05-31_add_amazon_sales_orders_foundation.sql` | Amazon order financial events, fees, refunds, shipping labels via Veeqo | Keep as operational/detail source |
| Inventory value | `web/app/api/dashboard/inventory/route.ts` | Inventory by operational state, value, aged capital | Keep operationally, export aggregates |
| Growth dashboard | `web/app/api/dashboard/growth/route.ts` | Revenue/profit/business-value trends | Retired from MBOP after ZFI verification |
| Tax/Schedule C planning | `ROADMAP.md`, former financial dashboard route | Future MBOP-owned P&L/Schedule C ideas | ZFI owns |

## Proposed Boundary

MBOP should own:

- Operational purchase, receiving, FBA, repricing, sourcing, inventory, return/refund follow-up workflows.
- Item-level and order-level profitability used to run the resale business.
- Marketplace source data needed for operations: Amazon sales orders, Amazon fees, Veeqo label costs, COGS allocation, inventory states.
- Operational inventory value by state.

ZFI should own:

- Household/business combined net worth.
- Cash-flow planning.
- YNAB integration.
- Schedule C/tax categorization.
- Quarterly tax estimates and annual tax packet.
- Owner draws/contributions.
- Long-range profitability trends and personal finance planning.

MBOP should push only summarized business-operational finance data to ZFI. ZFI should not query MBOP directly as its normal pattern, and MBOP should not pull ZFI personal finance data.

## Payload Proposal

Implement a manual server-side script first:

`integrations/push_zfi_business_summary.py`

Dry run by default, live push only with `--apply`. The live target is ZFI
Supabase, not a local/laptop endpoint. ZFI reads the summary out of its own
Supabase table.

Payload shape:

```json
{
  "source": "mbop",
  "schema_version": "2026-06-25",
  "period": {
    "start_date": "YYYY-MM-DD",
    "end_date": "YYYY-MM-DD"
  },
  "sales": {
    "gross_sales": 0,
    "amazon_sales": 0,
    "ebay_sales": 0,
    "other_sales": 0,
    "refunds_returns": 0
  },
  "costs": {
    "marketplace_fees": 0,
    "shipping_label_costs": 0,
    "inbound_shipping_prep_costs": null,
    "cogs": 0,
    "inventory_purchases": 0
  },
  "inventory": {
    "current_inventory_value": 0,
    "aged_inventory_value": 0,
    "fba_inventory_value": 0,
    "merchant_fulfilled_inventory_value": 0,
    "purchased_not_received_value": 0,
    "count_by_state": {}
  },
  "profitability": {
    "gross_profit": 0,
    "estimated_net_profit": 0
  },
  "cash_operational": {
    "amazon_cash": 0,
    "amazon_available_to_withdraw": 0,
    "amazon_to_bank_in_transit": 0
  },
  "alerts": [],
  "source_timestamps": {},
  "confidence_notes": []
}
```

## Historical Implementation Plan

The original approval plan is complete/superseded:

- `docs/ZFI_INTEGRATION.md`
- Update existing docs where present: `CURRENT_STATE.md`, `DECISIONS.md`, `ROADMAP.md`, `KNOWN_ISSUES.md`, `AGENTS.md`

Step 2: Add manual push script:

- `ZFI_SUPABASE_URL`
- `ZFI_SUPABASE_SERVICE_ROLE_KEY`
- `ZFI_BUSINESS_SUMMARY_TABLE`
- Optional `ZFI_PUSH_RETRY_ATTEMPTS`
- Optional `ZFI_PUSH_RETRY_DELAY_SECONDS`
- Dry-run default, `--apply` for live push
- Retry/error logging
- No frontend token exposure

Step 3: Run local checks:

- Python compile for the new script
- Likely no database migration needed for the first pass

## Recommendation

Do not reintroduce MBOP-owned YNAB sync, business-value snapshot production, or
Financial/Growth dashboard planning surfaces. Keep MBOP operational, and keep
ZFI as the financial-planning owner.
