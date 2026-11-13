# Amazon outbound shipping reconciliation

The worker is `integrations/veeqo_sync_sales_labels.py`. It reads Veeqo orders
and shipments and updates MBOP sales evidence and shipping profitability only.
It never purchases labels or changes marketplace orders or prices.

## Eligibility and bounded processing

An imported Veeqo order is not proof of a shipping cost. Reconciliation checks
complete actual shipment evidence, verified Amazon postage events, and active
USD fulfillment overrides against the stored item allocations. Shipped and
legacy `Shipped - Delivered to Buyer` orders are eligible. Cancelled orders and
orders whose profitability rows are all refunded/cancelled are excluded.
Unshipped/pending orders are reported separately and become eligible when the
Amazon import records shipment. The existing sales-history boundary is January
1, 2025; all stored Veeqo orders missing labels in this recovery were within it.

The normal Amazon-sales schedule reserves 20 older-order slots within a
50-order limit and uses the other slots for the recent 14-day window. Spare
recent capacity can be used for the backlog. Selection rotates by stable order
ID using separate recent/backlog cursors in `scheduler_run_jobs.metadata`.
Failed and unmatched orders advance the cursor too, so they cannot monopolize
later batches. Streamed metadata checkpoints preserve continuation even if the
task times out inside a provider request. The next scheduled pass retries remaining work; there is no
tight loop retrying unmatched orders. Database reads paginate in 100-row pages
and fail visibly after 100 pages instead of declaring a truncated queue empty.

Known Veeqo IDs use one detail GET. New matches use exact Amazon order-ID fields,
up to six search pages and one detail GET. Calls are paced at four per second;
transport errors, HTTP 429 and transient server errors get at most four attempts
with bounded backoff. Response bodies and tracking/customer data are not logged.

## Actual cost evidence

The documented Veeqo field is `outbound_label_charges.value`, with currency in
`outbound_label_charges.unit`. Actual stored responses sometimes have a null
unit; the Veeqo order's explicit `currency_code` is then used. Only USD evidence
is accepted in this USD profitability workflow. Missing/unknown currencies are
unresolved, never converted implicitly. Explicit source zero is valid; absent
amounts, generic `cost`, rates and customer delivery charges are not substitutes.

Only top-level shipments and allocation shipment containers are inspected.
Nested tracking records are not shipments. Stable shipment IDs deduplicate
repeated containers; unidentified shipments prevent a complete cost. Every
shipment must have cost evidence before summing multiple shipments. Voided,
cancelled or refunded labels and undocumented adjustment structures require
review. Their original amount evidence is retained, but not treated as a newly
reconciled active label. Incomplete later responses preserve previously valid
amounts and source fields.

Amazon fallback requires an actual `AdjustmentEventList` money row at
`AdjustmentAmount` with an outbound `PostageBilling_` or `PostageRefund_` type,
USD currency and the associated order. Signed refunds/adjustments are netted and
financial-event IDs deduplicate repeats. Unrelated negative adjustments and
return-postage events are excluded. Veeqo and Amazon totals are alternatives,
not additive sources for the same order. Active overrides retain precedence.

Official references checked during implementation:

- [Veeqo shipment response](https://developers.veeqo.com/api/operations/create-a-shipment)
- [Veeqo label charge response](https://developers.veeqo.com/api/operations/purchase-shipping-labels/)
- [Amazon Finances v0 model](https://github.com/amzn/selling-partner-api-models/blob/main/models/finances-api-model/financesV0.json)

The exact `PostageBilling_Postage` type was also verified in stored production
payloads; a negative amount alone is not sufficient evidence.

## Allocation and profitability repair

Order-level actual shipping is allocated once by ordered unit quantity across
all order items. Fractions are rounded in integer cents, with remaining cents
assigned in ascending Amazon order-item ID order. Item-specific overrides replace
the corresponding item's share. Item totals always retain their source label;
no shipping estimates are introduced. This rule is backend-owned.

After persisting evidence, `refresh_shipping_profitability` repairs that order
regardless of purchase date, updating only fulfillment cost/source, profit, ROI
and completeness status. It preserves existing sale values, fees, COGS and COGS
consumption. A failed profitability write remains eligible for retry even if the
label has already been imported. Absent profitability rows are reported as a
write failure requiring initialization by the regular profitability workflow.

## Health and operations

Each run emits `METADATA_JSON.shipping_reconciliation`: eligible, selected,
attempted, matched, reconciled, pending and unresolved shipped orders; API and
write failures; source outcomes; actual request/retry/rate-limit counts; oldest
unresolved purchase date and backlog age; and continuation cursors. Scheduler
counter columns use these explicit counts rather than adding metric lines.
An empty verified queue is distinct from missing credentials, failed reads,
incomplete writes and an unresolved backlog. Missing Veeqo credentials exit
nonzero. System Health shows shipping-specific metrics and status.

The notification key `sales-shipping:unresolved` is persistent and deduplicated.
Ongoing occurrences preserve `read_at`; recovery resolves the notification,
and a later recurrence makes it unread again. Four Veeqo label gaps in the
November 7 recovery had valid Amazon postage/manual evidence, so they do not
produce a false unresolved-cost alert.

Use the existing AWS scheduler deployment/run-task workflow in
[`aws/MBOP_AWS_OPERATIONS_RUNBOOK.md`](aws/MBOP_AWS_OPERATIONS_RUNBOOK.md).
Use `Dockerfile.scheduler`, production scheduler credentials and a digest-pinned
`mbop-scheduler-task`. Keep `CLOUD_DEPLOYMENT=true`, `LOCAL_SYNC_ENABLED=false`.
Check database capacity and a tiny read first. Apply mode also requires the
existing fresh capacity gate before writes. This gate checks disk/memory/swap
headroom and reachability; it does not measure remaining Disk IO Budget.

Read-only plan command override:

```json
["python", "integrations/veeqo_sync_sales_labels.py", "--asin", "B092FLB415", "--last-units", "25", "--limit", "30", "--dry-run"]
```

The dry run makes no Veeqo requests or database writes and reports the maximum
number of source requests including retries. Replace `--dry-run` with `--apply`
only for a reviewed bounded cohort. The shipping-only orchestration group is:

```json
["python", "run_all_syncs.py", "--group", "amazon-shipping-reconciliation"]
```

For the regular schedules, retain `amazon-sales-recent`; only that group's two
schedule targets need the shipping release. Never run broad orchestration just
to repair shipping. Defer a recovery when another Amazon sales worker is active.

## Unit audit CSV

```json
["python", "integrations/amazon_shipping_reconciliation_audit.py", "--asin", "B092FLB415", "--units", "25"]
```

This read-only audit emits `AUDIT_JSON` and a `CSV_BEGIN`/`CSV_END` block, with
one row per shipped unit, order/item IDs, actual order cost, allocated item/unit
cost, source IDs, Veeqo observation time/status and stored profitability fields.
It excludes customer names, addresses, contact details and tracking numbers.
Order totals repeat on unit rows: use the allocated-unit column for unit sums,
not the repeated order-total column. Unit allocations may have four decimal
places when an item-level cent amount is divided across multiple units.

Regression command:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_sales_shipping_reconciliation tests.test_amazon_sales_profitability_fees tests.test_scheduler_diagnostics
```
