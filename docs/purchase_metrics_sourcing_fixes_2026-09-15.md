# Purchase delivery totals, exclusion filters and sourcing investigation

## Purchase totals

Purchases displays units and purchase dollars for Not delivered yet and Delivered and not received, independent of search, filter and pagination. The server-only `purchase_delivery_stats()` aggregate uses `vw_purchases_dashboard.unit_cost * quantity`, deduplicated by item ID. No frontend cost or status derivation is added.

Not delivered yet includes no tracking, shipped without tracking, awaiting scan, in transit, multi-package in transit, partially delivered, pickup available, out for delivery and exception. These are purchase-item backlog totals: partially delivered items remain wholly in this bucket until fully delivered. Delivered and not received uses the backend `delivered` status. Received, listed, cancelled, return pending/opened and explicitly reporting-excluded items are excluded. Missing costs are reported as unpriced units; errors display Unavailable rather than zero. Null quantity contributes zero.

The additive migration `20260915145955_mbop_purchase_delivery_stats.sql` is applied to verified project `froeucjkcepuhgwisped`. All 22 shared migration ledger entries match. The CLI again emitted its known pg-delta local certificate-cache warning after successful application; ledger and service-role RPC readback verify success. No migration was edited after application.

Production EXPLAIN (without executing the query) uses `idx_purchase_items_status`, primary-key joins and an estimated 82 results; it does not scan the large snapshot tables. One service-role RPC read returned in 391 ms: Not delivered 44 units / $911.29; Delivered not received 35 units / $837.51. These are point-in-time totals, not fixed UI constants. Evidence: `tmp/ops-20260915/purchase-totals.json`.

## Closest Excluded

The Exclusion reason selector offers All, Match needs review (`review_threshold`), Profitability, and all additional reason codes actually present in the qualified result set. Counts and filtering are API-owned, applied after existing qualification/deduplication/search/inventory filters and before the visible-row limit. Selecting a reason can therefore find rows outside the first 50. Existing matching/routing rules are unchanged. Query parameters are already part of browser/server cache keys.

Returning focus still makes a lightweight freshness probe. An unchanged revision reuses the list. Previously a failed probe unconditionally purged all cached tabs; it now retains the last data with an explicit freshness warning and clears the warning when checks recover. Actual revision changes refresh in the background without replacing the table with a loading state. Manual Refresh and operator mutations still invalidate immediately; existing stale-safe review writes are unchanged.

This fixes two verified code paths, not a claim that every reported focus reload was caused by a failed probe. Source jobs and other operator sessions may legitimately change the revision. Web logs also contain an Amazon listing image query timeout, so transient database query failures are real; that log alone does not establish a failed freshness RPC.

## Two failed sourcing jobs

Both scheduled jobs ran scheduler93 at the existing 00:10 America/Los_Angeles schedule and failed before catalog work at the capacity preflight. Each exhausted 11 checks over about five minutes:

| Local date | Scheduler run | Blocker | Final observed metric |
| --- | --- | --- | --- |
| September 14 | `8b9fa85d-ab6e-4caa-b9d7-5649841ce59c` | `low_swap_headroom` | 210,210,816 bytes free of 1,073,737,728 (~19.6%; requires 25%) |
| September 15 | `5eb2c313-eafd-4fec-8818-452a5f9fde15` | `low_disk_headroom` | 1,038,651,392 bytes free of 8,416,882,688 (~12.3%; requires 15% and at least 1 GiB) |

Both stored errors are `Catalog paused: database capacity did not recover within the bounded wait`. The preceding September 13 run succeeded. The September 14 failure preceded deployment of the new cache migration/runtime, so the cache release did not cause that failure.

Current read-only probe: database up, tiny read succeeds, available RAM 570.5 MiB, swap free 28.2%, disk free 0.962 GiB. The current gate remains blocked by disk headroom. Database metadata reports 6,506 MB. Largest relations including indexes/TOAST: FBA inventory snapshots 1,793 MB, sourcing opportunities 1,247 MB, Keepa snapshots 1,083 MB, sourcing listing snapshots 401 MB, eBay candidates 226 MB, coverage cycle items 212 MB, Amazon listing snapshots 210 MB and Informed snapshots 204 MB. These are size metadata, not a content/retention audit or proof of reclaimable disk space. Disk IO Budget was not measured.

No scheduler change, rerun, provider search, marketplace write, cleanup, database resize or protection reduction was performed. Storage headroom must be restored with an approved disk expansion or a separately reviewed archive/retention operation; recurring swap pressure also needs compute/memory review. Do not blindly delete snapshots or assume DELETE immediately returns filesystem space. After remediation, check fresh capacity metrics and a tiny read before a sourcing rerun. Evidence: `tmp/ops-20260915/{runs,logs-14,logs-15,capacity}.json`.

## Verification and release

- Disposable, network-disabled PostgreSQL executes the actual migration: every inbound state, lifecycle/reporting exclusions, duplicate shipment-view rows, multi-unit costs, missing costs, empty groups and service-only access. Container stopped afterward.
- Purchase API tests preserve authoritative values and surface actual RPC/invalid-response errors.
- Actual Closest Excluded GET regression covers all/review/profitability/other/empty results, total counts and filtering beyond the first 50 rows.
- Resource-cache regression invokes real focus callbacks: unchanged, failed, recovered and changed revisions. Hook regression proves background changes preserve visible rows and reason parameters reach the API.
- Existing Business Excluded GET, server cache, lazy review, comparison diagnostic, declined-offer and actual review-control regressions pass. TypeScript passes. Focused lint passes with ten existing sourcing unused-code warnings; the purchases route has two pre-existing explicit-any findings, unchanged in this work, and passes with only that rule disabled for that file.
- No available browser surface (`apps: [], browsers: []`); authenticated browser click-through is unavailable. Local tests and service-role readback must not be described as browser verification.

Web build/deployment results will be appended after release verification.
