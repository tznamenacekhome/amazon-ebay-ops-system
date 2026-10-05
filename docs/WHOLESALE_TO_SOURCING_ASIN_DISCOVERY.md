# Wholesale to Sourcing ASIN Discovery

## Purpose

Wholesale matching may discover a valid Amazon ASIN before that ASIN appears in
MBOP sales, purchase, or Amazon listing history. A selected wholesale ASIN now
feeds the normal Amazon-to-eBay sourcing coverage queue after it passes the same
product and account safety gates used by wholesale review.

This is ASIN discovery only. It does not submit a wholesale order, create owned
inventory, change accounting, or use a supplier price as eBay sourcing cost.
The existing eBay candidate economics, thresholds, queue, Browse quota reserve,
and operator buying workflow remain authoritative.

## Admission policy

A wholesale selection is eligible only when all of these facts are current:

- the match state is `matched` and has a selected candidate;
- the selected candidate is compatible with the supplier product;
- shared `amazon_listing_eligibility_evidence` for the configured seller,
  marketplace, ASIN, and `new_new` condition says eligible and has not expired;
- no active wholesale product classification excludes the supplier product;
- the ASIN is absent from `sourcing_blocked_asins`.

Manual and automatic selections use the same gates. Unknown, pending, stale,
incompatible, unselected, restricted, identity-review, and blocked rows do not
enter sourcing. Multiple supplier products selecting one ASIN produce one queue
entry with supplier/import/product provenance retained in the seed snapshot.

Wholesale-only ASINs enter the existing `3_catalog_remaining` priority. An ASIN
already admitted by recent sales, purchases, or the Amazon catalog keeps the
higher-priority seed and economics while gaining wholesale discovery provenance.
Refreshing an active cycle also merges that provenance into existing cycle
items; it does not reorder or repeat them.

## Current restriction suppression

Fresh `new_new` restriction evidence is a central sourcing exclusion, regardless
of whether an ASIN came from wholesale, recent sales, purchases, or the Amazon
catalog. Pending active-cycle rows become `ineligible`. Existing open, watched,
ROI-snoozed, and inventory-snoozed opportunities are dismissed with an
idempotent `sourcing_actions` audit record. Purchased rows and historical
evidence remain intact. Eligible evidence may admit the ASIN again in a later
cycle after the restriction cache is refreshed.

## Pre-deployment production baseline

The read-only October 4, 2026 baseline found 847 unique selected wholesale ASINs.
Of those, 846 passed the selection, compatibility, current eligibility,
classification, and block gates; 605 were already in the active sourcing
universe and 241 were net new. The eligible net-new set contained 237 confirmed
video-game seeds. Two eligible selections were manual. One selected ASIN was
blocked. Restricted wholesale products had no selected ASIN, which is the
expected wholesale matching behavior.

The same snapshot contained 543 unique fresh restricted compatible wholesale
candidate ASINs and 544 fresh restricted ASINs in the shared eligibility cache.
There were no open sourcing opportunities and no pending active-cycle items on
those restricted ASINs before activation.

## Operations

`integrations/run_daily_catalog_sourcing.py` performs the admission, dedupe,
restriction suppression, cycle refresh, and normal bounded sourcing work. The
AWS `mbop-sourcing-catalog` schedule remains the owner. No new schedule, provider
loop, or client-side job is introduced.

Migration `20261005003000_mbop_wholesale_sourcing_seed_source.sql` adds
`wholesale_catalog` to the allowed `sourcing_seed_asins.source_mode` values.

## Production activation (October 4, 2026)

The migration is applied and reconciled in the shared production ledger.
Scheduler revision `mbop-scheduler-task:123` runs commit `c0d4ccf64c28` from
digest `sha256:f0355d9d45b9c37462f6b658219e4f753dfce625195429040189838e643cff52`.
The enabled `mbop-sourcing-catalog` schedule remains `cron(10 0 ? * * *)` in
`America/Los_Angeles` and retains its existing command and quota policy.

A controlled zero-call activation refreshed active cycle
`ff3d0e2d-1652-4f95-9587-30771bc15808`. Its eligible universe grew from 2,108
to 2,184 rows, so 76 ASINs entered after the normal video-game, pricing,
inventory, velocity, stale-stock, block, and dedupe controls. In the resulting
cycle, 679 rows retain wholesale provenance; 251 of the 253 pending rows have
that provenance. The first pending row is ASIN `B0F6SRFLCF`, WUCHANG: Fallen
Feathers Day 1 Edition for PlayStation 5, at catalog priority and queue position
1,932.

The current shared cache contains 544 fresh restricted ASINs. One occurs only
in already-searched cycle history, which is retained by design; zero restricted
ASINs are pending or retryable in the active cycle. No restricted open sourcing
opportunities existed during activation.

The bounded one-ASIN search attempt completed normally with zero Browse calls
because live quota was already exhausted at 5,060 calls against the 5,000-call
daily limit. Its quota reset is `2026-10-05T07:00:00Z`. The runner stopped with
`quota_reserve_reached`, proving the existing budget guard remains authoritative;
it did not create a purchase, bid, or offer. The enabled normal schedule will
resume with the wholesale-derived row first after quota resets.

One auto-deleting controlled retry is scheduled for `2026-10-05T07:02:00Z`,
after the quota reset and before the normal 07:10 UTC run. Schedule
`mbop-wholesale-sourcing-validation-20261005` is limited to one ASIN, at most
eight Browse calls, and at most 50 results for that ASIN.
