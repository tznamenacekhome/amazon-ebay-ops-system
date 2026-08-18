# FBA Pricing Refresh and eBay Cancellation Sync - 2026-08-18

## Summary

This change covers two operational fixes:

- eBay buyer purchase sync now treats `OrderStatus=Cancelled`, meaningful
  `CancelStatus` values, and fully refunded Trading API orders as cancelled,
  even when the existing MBOP order already has tracking.
- FBA prep pricing refresh now runs as a long-lived scheduler group that waits
  for Keepa token refills, reports scheduler telemetry back to the UI, and
  persists the operator-facing refresh notice across page reloads.

## eBay Cancellation Sync

Observed issue:

- eBay order `11-14971-19701` was cancelled and refunded by eBay, but MBOP still
  showed it as `awaiting_carrier_scan`.
- The stored MBOP payload was stale: `OrderStatus=Completed` and
  `CancelStatus=NotApplicable`.
- A targeted Trading API read returned the current eBay state:
  `OrderStatus=Cancelled`, `CancelStatus=CancelClosedWithRefund`,
  `AmountPaid=0.0`, payment `13.99`, refund `-13.99`.

Root cause:

- The buyer purchase sync skipped existing orders whose tracking numbers were
  already known.
- That skip happened before cancellation/refund state could update
  `purchases.order_status`, `purchases.raw_import_json`, and
  `purchase_items.current_status`.

Implementation:

- Added `order_is_cancelled_or_refunded`.
- Cancellation detection now uses:
  - `OrderStatus` of `Cancelled` or `Canceled`
  - meaningful `CancelStatus` values other than `NotApplicable`
  - fully refunded payment/refund totals
- Existing orders with tracking are no longer skipped when eBay reports a
  cancellation/refund signal.
- Tests cover pending cancellation before refund confirmation and a tracked
  existing order that must be updated to `cancelled`.

One-off repair performed:

- Order `11-14971-19701` was refreshed through the normal buyer-purchase upsert
  path.
- Its purchase item is now `current_status=cancelled`.
- Its stale tracking candidate case was converted to
  `cancelled_refund_followup / refund_pending` with next action
  `Confirm refund received.`

## FBA Pricing Refresh

Observed issue:

- FBA pricing refresh can outlive a normal browser request because Keepa token
  availability varies.
- The previous on-demand refresh UX did not have enough durable state to follow
  an AWS scheduler run after page refresh or navigation.

Implementation:

- Added `integrations/fba_pricing_keepa_until_complete.py`.
- The script selects the current `received_fba_prep` ASIN set, refreshes missing
  snapshots in explicit Keepa batches, waits for token refills, and exits only
  when every initially selected ASIN has a fresh snapshot or the attempt budget
  is exhausted.
- `run_all_syncs.py` now routes the `fba-pricing` group through this wrapper.
- `fba-pricing` is included in distributed scheduler locking and shares Keepa
  quota protection with `keepa-catalog-priority`.
- A manual `fba-pricing` run waits for scheduled Keepa catalog priority to
  finish; scheduled Keepa catalog priority is blocked while manual FBA pricing
  is active.
- `run_all_syncs.py` accepts `--run-id`, and AWS scheduler task launch passes
  that run id both as a command argument and `MBOP_RUN_ID`.

## UI and API

- `/api/sync-refresh?runId=<id>` reads scheduler run/job telemetry and returns a
  compact summary for polling UI.
- On-demand refresh starts local or AWS scheduler work with a stable run id.
- `web/app/syncRefresh.ts` can poll scheduler telemetry, fall back to legacy
  local lock polling, summarize completion warnings, and persist active refresh
  state in `localStorage`.
- FBA prep uses persisted refresh state under `mbop:fba-pricing-refresh` so the
  pricing notice resumes after reload.
- FBA prep price cells now color Keepa price age:
  - green for fresh snapshots under 3 days
  - amber for snapshots 3-7 days old
  - red for older snapshots
  - muted gray when no cache timestamp exists

## Verification

- `python -m unittest tests.test_ebay_sync_buyer_purchases`
- `python -m py_compile integrations/ebay_sync_buyer_purchases.py integrations/fba_pricing_keepa_until_complete.py run_all_syncs.py`
- `npm run build` from `web`

Production verification still requires the AWS web deployment workflow and
browser verification at `https://mbop.midnightblueenterprises.com`.
