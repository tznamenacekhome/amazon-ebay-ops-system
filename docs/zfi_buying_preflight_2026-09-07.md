# ZFI Buying integration: acquisition-cost preflight

## Follow-up: refund correction and integration deployed

The approved proportional refund behavior is deployed on scheduler revision 84.
Twelve buyer tests include purchase-item/FIFO cost flow. ZFI Buying production
read and concurrent-refresh verification passed. Rare tax-bearing purchases
and historical cost auditing remain outside scope by operator instruction.
[Activation report](ZFI_BUYING_ACTIVATION_2026-09-07.md).

The remaining sections preserve the original read-only preflight findings;
statements about changes not yet made describe that earlier inspection.

## Repository and existing integration

The active checkout is C:\Dev\amazon-ebay-ops-system, origin
tznamenacekhome/amazon-ebay-ops-system. The C:\Dev\mbop path in the brief
was not present during inspection.

The existing server-only ECS launcher is web/app/api/_awsScheduler.ts.
The sync-refresh route already invokes scheduler groups, but its generic
admin credential and current launch/status behavior are not a least-privilege,
atomic ZFI Buying contract. The new integration should reuse this launcher,
with dedicated authorization and durable concurrency/queued-state handling.
It must not invoke local Python from the cloud web process.

## Confirmed discrepancies

integrations/ebay_sync_buyer_purchases.py:

- transaction_landed_total adds transaction price times quantity, actual
  shipping, and actual handling. It does not add vendor sales tax.
- transaction_unit_costs substitutes net payment amounts only for non-USD
  transactions or single-transaction refunded orders. A normal USD
  multi-transaction refund therefore does not reduce allocated unit costs.

Two synthetic XML fixtures were evaluated against the current functions
without making marketplace calls or database writes:

| Fixture | Required acquisition cost | Current result |
|---|---:|---:|
| One unit: $10 item + $2 vendor shipping + $1 tax; payment $13 | $13 | $12 |
| Two units on separate lines: $20 + $30; payment $50; refund -$5 | $45 total | $50 total |

These are reproducible behavioral defects relative to the requested cost
definition, not claims that these exact fixtures occurred in production.
A bounded production search found no eBay purchases with tax_amount > 0;
this does not establish that all historical tax was zero, because the stored
tax field's completeness has not been established.

The live public.vw_purchases_dashboard definition selects pi.unit_cost
directly. It does not allocate purchase-level tax or refunds. The FIFO
allocator, integrations/apply_ebay_purchase_fifo_cogs.py, reads this view's
unit_cost and multiplies it by quantities allocated to sales. Thus the
source-cost defects can flow through to COGS. Allocation is associated with
sales; no purchase-date recognition redesign is indicated by this inspection.

## Initial history findings and limitations

A production read found 3,408 purchases whose supplier is eBay, with stored
order_date from 2024-09-10 through 2026-09-06. September 10, 2024 is the
earliest observed stored eBay purchase date, not yet a certified reliable
start date for the new report.

The model has purchase_items.quantity and unit_cost, manual_split_child and
manual_split_parent_item_id, and explicit reporting exclusion flags. Neither
purchases nor purchase_items has an updated_at column. created_at must not
be mislabeled as a complete source_updated_at watermark.

Existing KNOWN_ISSUES documentation records legacy multi-item orders as
multiple purchase records sharing an eBay order ID (for example,
04-14542-23405). Dropping all but one such purchase can lose legitimate
units; summing repeated order headers can overcount cash. The same document
reports prior 2024/2025 spreadsheet reconciliation and a $4.05 residual cost
variance, but those historical assertions were not re-certified here.

Full quantity/cost completeness, date fallback coverage, refunds, duplicate
line identification, and continuity remain to be audited. No historical
data should be removed or reimported based on this preliminary review.

## Required next decision

Resolve the acquisition-cost discrepancy before finalizing the ZFI facts
contract: define authoritative gross vendor payments, discounts and signed
refunds; allocate them across legitimate units while preserving explicit
manual corrections and avoiding double-subtracting refunds. Audit affected
historical rows before any cost backfill or FIFO recalculation. A broad FIFO
redesign is not proposed or performed.

The requested read-only facts view, service credential, refresh trigger and
status endpoints are not implemented or deployed. No credentials for ZFI
have been created. The existing scheduled purchase-ingestion jobs remain
unchanged, and no ZFI or YNAB data was accessed.
