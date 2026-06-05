# Business Rules

Last updated: 2026-06-04

## Cost And Reporting

- Frontend code must never recalculate landed cost.
- Purchase reporting must use backend-provided `vw_purchases_dashboard.unit_cost`.
- eBay reward points or payment methods must not reduce inventory cost to zero.
- Single-item partial refunds where the item is kept may reduce purchase item cost.
- Multi-item partial refunds require explicit workflow/manual handling.
- Personal purchases and business supplies remain traceable but are excluded from resale reporting through `purchase_items.exclude_from_purchase_reporting`.
- Purchases on or after 2026-05-16 are MBOP-canonical, not spreadsheet-canonical.

## Status Ownership

`purchase_items.current_status` is backend-owned.

Workflow-locked statuses include:

- `cancelled`
- `listed`
- `received`
- `return_opened`
- `return_pending`

Carrier/status syncs must not downgrade workflow-owned statuses.

## Matching And Product Identity

- Video games are platform-specific.
- Never auto-match across systems.
- ASIN corrections may propagate only to matching normalized title + system rows and must not overwrite a different existing ASIN.
- `purchase_items.amazon_title` stores the matched Amazon/RevSeller title separately from the supplier/eBay title.
- ASIN is the primary Amazon product identity for MBOP operational inventory. MSKU remains stored for Amazon traceability and InventoryLab/Informed joins.

## Receiving

- Purchases workflow and receiving workflow are separate.
- Receiving owns physical verification and the transition to `received`.
- Amazon-bound received items require ASIN and sell price.
- eBay-bound received items do not require Amazon title, ASIN, or sell price.
- Return Pending is separate from Return Opened.
- Cancelled items require future refund follow-up.

## Order Problems And Returns

- Order Problems is the unified queue for delivery problem candidates,
  return-needed items, eBay return/case follow-up, missing-item/replacement
  follow-up, and cancelled/refund confirmation.
- `order_problem_cases` owns the persistent workflow case; `order_problem_events`
  owns the append-only timeline.
- `Return Pending` means MBOP identified a return need before an eBay return/case
  necessarily exists.
- `Return Opened` means an eBay return/case exists or the operator has marked it
  opened in eBay.
- Stale tracking candidates use a 14-day order-age threshold for `no_tracking`,
  `shipped_no_tracking`, and `awaiting_carrier_scan`, with a 90-day lookback.
  `in_transit` is not stale while carrier ETA is in the future; it becomes a
  problem only when ETA is past.
- Derived stale/late/carrier candidates should auto-close when the purchase no
  longer matches a candidate rule.
- The current eBay returns integration is read-only. MBOP may store eBay return
  IDs, inquiry IDs, cancellation IDs, statuses, deadlines, escalation dates,
  refund amounts, action URLs, replacement tracking, and raw payloads, but must
  not create returns, send messages, accept offers, escalate cases, issue
  refunds, or upload files.
- For INR inquiries, eBay search results are not enough. MBOP must read inquiry
  details to capture seller make-it-right dates and seller-provided replacement
  tracking. Those dates display as escalation/action availability in the Order
  Problems Next Action column.
- `Close` means the problem is resolved with no further refund or inventory
  consequence. `Close No Refund` means the problem is closed but value was lost
  or unrecoverable and no refund will be received; it must not move the item
  back into Received, Listed, or Amazon-bound inventory.
- Operator actions in the drawer update MBOP workflow state only. The operator
  performs marketplace actions on ebay.com.
- Partial refunds where the item is kept must not automatically change item cost
  until a controlled cost-adjustment workflow exists.

## Amazon FBA Shipment Prep

- The FBA workflow starts from Received Amazon-bound purchase items.
- The FBA page groups rows by ASIN for InventoryLab export.
- Grouped cost is backend-owned and quantity-weighted.
- Operator-entered shipment ID links included items to FBA shipment rows.
- Included quantities move to `listed`; excluded quantities remain `received`.
- Current non-historical FBA shipment links are valued as `outbound_to_amazon` until Amazon/InventoryLab inventory takes over.
- The historical marker `legacy_listed_no_shipment_id` must not create outbound-to-Amazon value.

## Inventory And Valuation

- Current canonical inventory equals current Amazon FBA inventory plus MBOP purchase inventory that has not reached `listed`, plus non-historical MBOP FBA shipment links that are on the way to Amazon.
- Amazon-bound `listed` purchase rows without a current FBA shipment link are historical/sold-through for current inventory purposes; current Amazon inventory is represented by Amazon SP-API snapshots.
- InventoryLab valuation snapshots are legacy opening-balance valuation context for current Amazon FBA inventory.
- MBOP purchase/receiving/FBA workflows own go-forward cost.
- Opening-history boundary adjustments record units sold before MBOP's
  operating-history window and must stay separate from future inventory count or
  discrepancy adjustments.
- The Inventory Source Balance Audit checks that purchase source units equal
  sold units plus active inventory, opening-history boundary units, and explicit
  adjustments. It is a control process for close/tax confidence, not a scheduled
  external-data freshness sync.
- Business value snapshots use MBOP outbound shipment cost for saved FBA shipments and avoid double-counting overlapping Amazon inbound rows for the same ASINs.
- YNAB Business category balance is cash-on-hand context only.
- Amazon Finance cash is value that has moved from inventory into Amazon-held cash or Amazon-to-bank in-transit cash.
- Amazon-to-bank in-transit cash includes transfers Amazon still marks
  `Processing` plus completed/succeeded payout groups that do not yet have a
  matching YNAB Business deposit transaction. This prevents business value from
  dropping during the gap after Amazon completes a payout but before the YNAB
  bank/cash transaction is present, without double-counting deposits that YNAB
  already captured.
- Business value snapshots are reporting snapshots only.
- Dashboard cash/value freshness is limited by the oldest required cash/value
  input: business value snapshot, Amazon Finance balance snapshot, or YNAB cash
  snapshot.
- Amazon reserved inventory is normal Amazon processing and should not be
  surfaced as an operator problem by itself.
- Amazon listing/catalog issue signals should be ignored when your FBA units are
  still sellable/available for sale.
- Amazon damaged/unsellable units should be tracked as a removals workflow, not
  as purchase or receiving cleanup.
- Amazon receiving shortages, lost units, warehouse damage, and customer returns
  that do not come back to the business belong in a future Amazon Inventory
  Discrepancy workflow.

## Repricing Advisor

- The Aged Amazon Inventory Repricing Advisor is manual advice, not an automated repricer.
- Do not write prices to Amazon.
- Do not modify Informed rules, min/max prices, or managed status.
- Use Amazon Inventory Planning age buckets as the preferred active-FBA age source.
- Rows under 90 days old are excluded unless there is an actionable issue.
- Rows with any Informed sales in the last 30 days are excluded from the aged action list.
- FC transfer, inbound movement, future supply, and FC processing are not action issues by themselves.
- Buyable/discoverable Amazon catalog metadata issues are ignored unless inventory becomes suppressed/non-buyable or unsellable.
- Snoozes hide advisory rows from the default queue for 30 days and do not change inventory state.
- Keepa competition data must come from stored snapshots or explicit operator-run scripts, not from page-load token spending.
