# Sourcing planning lookup optimization

The seed builder previously scanned up to 20,000 inventory-planning history
rows in 1,000-row pages, sorting by capture time and carrying full raw report
JSON. Both recent-sales and catalog seed paths repeated this scan. Production
diagnostics recorded 40 calls and 3.66 GiB of temporary writes at startup.

Migration `20260912000000_mbop_sourcing_latest_planning_lookup.sql` adds a
service-role-only, security-invoker read function. It accepts at most 200 ASINs
and uses the existing `(asin, captured_at DESC)` index for a lateral latest-row
lookup. It returns age/sales columns and only the three raw fallback values
used by the existing stale-stock exclusion. It changes no history, SKU-level
repricing view, Amazon source tables, or College Planner objects. The complete
shared ledger was reconciled before `supabase db push`; application was verified
in the remote ledger and through real service-role RPC calls. The CLI reported
a local pg-delta catalog-cache warning after application; the migration and RPC
were independently verified successful.

Python requests only candidate ASINs after building each candidate list, in
batches of 100. A cache shared by both paths stores records and missing results
for one queue build only. Failures do not become cached misses and do not fall
back to broad history scans. The purchased-not-sent path is unchanged.

## Selection semantics

The business test remains: inventory exists, some is older than 30 days, and
30-day sales are zero. Raw sales/age fallbacks and missing-report behavior are
unchanged. This remains a single latest row per ASIN, not a new SKU aggregation.

The old query had no tie-breaker for identical capture timestamps. The new
lookup consistently uses descending snapshot UUID to resolve exact ties. In
the live compact old-window comparison, 1,102 of 1,104 ASINs had identical
decision context. B000OCXK6U had a different sales value but no exclusion change.
B07XFNRHZX had a different age value and changes from eligible to excluded in
that comparison (one unit currently held, no 30-day sales). The old arbitrary
selection was not a reliable business rule; exact row identity cannot be
guaranteed against its unstable tied ordering. No attempt was made to change
SKU-level business rules as part of this optimization.

Removing the global 20,000-row cap makes four additional historical ASINs
accessible. All four currently have zero inventory and remain unexcluded.
Historical report storage is retained.

## Verification

- 39 targeted Python tests cover request bounds, deduplication, missing-result
  caching, error handling, shared-cache lifetime, raw fallback parity, queue
  rules, incremental scoring, and existing diagnostics.
- Real service-role RPC returned all 1,104 ASINs covered by the prior window in
  12 requests, about 1.56 seconds client elapsed. PostgreSQL recorded about
  222 ms cumulative execution and zero temporary blocks read/written for
  those 12 calls. This is a lookup benchmark, not an end-to-end run comparison.
- A 100-ASIN EXPLAIN ANALYZE completed in 4.58 ms with zero temporary blocks,
  using the ASIN/date index and small incremental sorts for tied captures.
- Service-role execution is allowed; anonymous/authenticated execution is denied.

Evidence: ignored `logs/diagnostics/planning-optimization-20260912/`.
Retain workload diagnostics and capacity guards for the next complete nightly
run; do not infer a particular bill reduction or a permanent incident fix from
the isolated benchmark.

## Deployment result

Source commit `f904a321e351`; scheduler revision 90 uses image
`sha256:442ee38fb3cc7e9248e3f358a1a74cc465b60370a859c9482753d5221f752258`.
The image's dirty suffix reflects the unrelated untracked wholesale document;
all integration changes were committed before building.
All 39 tests also passed in the exact Linux image. AWS read-only smoke task
`fdea41cb47484a878b891bed18968927` exited zero and verified three real ASIN
lookups, the compact projection, and cache reuse without eBay calls or workflow
writes. The 1,104-ASIN benchmark above used the same applied production RPC.

Only `mbop-sourcing-catalog` changed from task revision 89 to 90. All 20 schedule
definitions were compared, preserving timing, state, overrides and network
configuration. Rollback target is revision 89; leave the additive migration
and history intact. No new full discovery run was launched for this release.
End-to-end runtime and overnight capacity results remain pending the next
scheduled run, with the existing workload collector and capacity guards active.
