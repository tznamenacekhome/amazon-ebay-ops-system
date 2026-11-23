# MF returns sync diagnosis — November 23, 2026

The diagnostic and fixture-testing phase performed no deployments, live
credential/permission changes, return actions, or production database writes.
Its new finance-work migration was initially applied only inside disposable
PostgreSQL containers. The subsequently authorized combined release and its
deployment evidence are tracked in
[the release notes](aws/RELEASE_2026-11-23_RETURNS_AND_LISTING.md).
The pre-existing seven-file web diff (pricing freshness, MF export SKUs and
System Health schedule timing) was inspected first and left intact.

## Confirmed evidence and cause

Read-only checks targeted MBOP project `froeucjkcepuhgwisped`
(`amazon-ebay-ops`, ACTIVE_HEALTHY), configured MF account
`3d91192f-05f9-4543-b7e5-c1976844d230`, seller `A3ILKLL5K4GVWX`, US marketplace
`ATVPDKIKX0DER`. Small indexed order/run/report reads were used; no sync was run.

- Last completed run finished `2026-11-09 01:52:34 UTC`, November 8 at 5:52 p.m. Pacific.
- 133 failed runs reference order `114-8866055-7493009`. There is one additional,
  earlier failed run, unrelated to that repeated-order count.
- 132 report records are IMPORTED; the account has zero normalized MF returns.
- Latest observed run `d202d9da-f617-4354-8dba-eba44c261e53` failed on
  `GET /orders/2026-01-01/orders/114-8866055-7493009`, HTTP 404 NotFound.
- A single read-only Finances request filtered by that exact ORDER_ID returned
  one Refund, transaction `ENnGZIf1dLqH4mrxaGQnUpPI57nUcds67TEe6BbTRUg`,
  posted `2026-11-09T03:44:30Z` (November 8, 7:44 p.m. Pacific), no next page.
  Its item ProductContext explicitly specifies `fulfillmentNetwork: AFN`.
  This is FBA data, not an MF customer-return candidate.

Trace: `report()` downloads/parses the seller-fulfilled TSV and imports its
rows. A header-only valid report has zero rows and makes no order requests.
`synchronize()` then independently reads overlapping account-wide Finances
transactions for roughly 59 days. Previously it considered Refund/ServiceFee/
Adjustment/Reimbursement references without inspecting ProductContext. The
recurring refund passes the 3-7-7 order-ID and US-marketplace checks. There is
no cached operational order for this ID, so `verify_order()` invokes getOrder.
The same transaction remains in the overlap on every run. Thus the imported
empty report does not establish successful full returns synchronization.

The confirmed defect is missing fulfillment scoping of financial candidates.
The patch does not claim to establish why Amazon cannot retrieve this specific
FBA order. Its 404 is not generalized into success or an empty MF result.

## API contract checks

- [Amazon getOrder v2026-01-01](https://developer-docs.amazon/sp-api/reference/getorder-3)
  documents `GET https://sellingpartnerapi-na.amazon.com/orders/2026-01-01/orders/{orderId}`,
  includedData, and 404 for a nonexistent resource. No marketplace query parameter
  is specified for this single-order operation. The existing request path and
  non-PII FULFILLMENT/PROCEEDS/CANCELLATION selection match that contract.
- [Amazon listTransactions](https://developer-docs.amazon/sp-api/reference/listtransactions)
  explicitly requires omitting marketplaceId to retrieve US MFN transactions.
  This is an account-wide feed, not an MF-only feed. ORDER_ID is a supported
  related-identifier filter (used in the diagnostic read).
- [Official Finances model](https://github.com/amzn/selling-partner-api-models/blob/main/models/finances-api-model/finances_2024-06-19.json)
  defines per-item ProductContext.fulfillmentNetwork. Only transactions with
  explicitly AFN contexts for every item are excluded. Missing, mixed or unknown
  contexts still go through verification, with failures visible.
- The local client configuration matches the configured seller/marketplace and
  North America endpoint. Existing worker startup checks seller and marketplace
  equality. Existing getOrder validates returned order ID/items, and MF order
  projection validates returned marketplace. No credentials or API path changed.

## Behavior after the patch

- Explicit FBA financial transactions are excluded before any Orders call and
  counted/logged as outside MF returns. Other Amazon finance workflows are unchanged.
- Valid empty reports can finish a fully successful empty sync when all other
  stages succeed. Blank/malformed documents still fail.
- Order verification explicitly distinguishes confirmed MF, confirmed FBA and
  unverified identities. Confirmed FBA report rows are skipped without failing
  the report or writing MF returns. Invalid/unverified rows and Orders 404s stay
  visible as failures; an unknown scope is never treated as a confirmed FBA skip.
- Each report verifies an order once. An unresolved row does not block safe
  remaining rows. The original report ID remains PARTIAL, with an error and no
  imported_at. Every run discovers account-scoped PARTIAL reports independently
  of UTC dates, the rolling window and normalized return rows, then retries their
  exact original report IDs. Successful replay uses existing account/source-key,
  observation, and transaction uniqueness. Polling/download failures preserve
  PARTIAL status, so an interrupted retry does not disappear from discovery.
- Retry discovery is bounded to six partial reports per run. A larger backlog
  forces incomplete/failed status even if the first six resolve. New rolling
  reports cannot hide unresolved partials or substitute for their document IDs.
- Report/document identity and row order/RMA errors remain available for review.
  Finance candidates are durably enqueued before verification/import in
  amazon_mf_return_finance_work, keyed by account and transaction ID. It stores
  the normalized non-PII payload and its original observation timestamp, not just
  an ID in run stats. Verification and import failures remain pending with errors.
  Every run retries up to 100 pending finance items independently of posted date,
  normalized return rows and the rolling feed. A larger backlog forces failure.
- The finance completion RPC imports and acknowledges work in a single database
  transaction. Rejected imports/crashes cannot acknowledge lost work. Replays
  use the original observation and existing transaction uniqueness; newer
  observations can re-enqueue an updated posting without stale data overwrites.
  Positively verified FBA orders can resolve work as excluded_fba, while unknown
  scope and Orders errors remain pending. No financial transaction is applied
  to an unverified MF order.
- API, pagination, parsing and scope errors remain failures. Partial processing
  never calls the finish RPC with a null error. A final pending-work check and
  a database-side finish guard prevent pending finance work from advancing a
  completed checkpoint. The dashboard last-success query selects completed runs.
- Logs distinguish `Return report imported ... full returns sync not yet complete`
  from `MF returns synchronized`. Failed runs retain partial progress stats and
  explicitly log that progress is not a successful checkpoint.

## Required schema prerequisite (not applied to production)

Before deploying this worker, apply
`supabase/migrations/20261123213947_mbop_mf_return_finance_work.sql` through MBOP's
documented shared-project migration workflow: verify the target, run migration
list, reconcile the complete shared ledger, then apply the reviewed migration.
No remote migration/list/push/repair was executed as part of this patch.
Existing applied migrations and the unrelated web diff were left unchanged.

The migration adds the service-role-only work table (RLS enabled), enqueue and
atomic completion RPCs, and replaces the sync-finish function to reject successful
checkpoints while finance work is pending. No broad raw snapshots or backfill
are introduced. Existing failures recorded only as IDs before this migration
are not automatically reconstructed; historical recovery, if needed, should use
bounded targeted source reads rather than assume the new queue contains them.

## Offline validation

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_amazon_mf_returns*.py'
.venv/Scripts/python.exe -m unittest discover -s tests -p test_amazon_orders_2026.py
.venv/Scripts/python.exe tests/test_mf_returns.py
.venv/Scripts/python.exe tests/test_mf_returns_sync_postgres.py
```

Fixtures cover valid empty/malformed reports, a normal MF return, mixed 404/valid
rows, report resumption and stable identities without duplicate imports, FBA
finance exclusion, conservative unknown/mixed handling, marketplace mismatches,
systemic finance errors, success/failure finish calls and retained failed-run stats.
Unit database calls and HTTP responses are offline doubles. The PostgreSQL
acceptance tests additionally run the real report worker and real schema/RPCs
through a test-only SQL adapter in a disposable postgres:17 container, with
fixture-only Amazon responses and no published port or production connection.
They verify a known FBA report row, an unresolved report with no normalized return,
UTC rollover discovery, a failed checkpoint followed by recovery, and duplicate-free
return/observation/order writes on replay. Additional finance cases put a refund
at the September 26 lookback boundary, fail verification or a real SQL refund
insert before midnight November 23, run after UTC midnight with an empty rolling
feed, and then recover and replay without duplicate finance/return/work rows.
They also call the finish RPC with a null error while work remains and verify
that it records failure rather than advancing last-success.

Results: 28 returns regression/source tests, 14 Orders v2026 contract tests,
10 existing PostgreSQL returns acceptance tests and 4 PostgreSQL worker
acceptance tests passed (56 total). `git diff --check` passed. Docker was started
for the requested tests; the disposable containers were removed by their harness.
No hosted worker was run for testing.

## Verification after an operator-approved deployment

Deploy the scheduler fix through the existing AWS scheduler workflow scoped to
the two `mbop-amazon-sales-recent-*` targets; this document does not authorize or
perform deployment. Observe the next normal scheduled run rather than creating
a return or running a broad backfill.

1. Apply the required reviewed migration first; confirm the scheduler image/task
   revision includes this patch.
2. In `/ecs/mbop-scheduler`, confirm the recurring transaction is logged as explicit
   FBA and excluded before Orders verification. Check imported report row counts
   separately from the final returns-sync result.
3. Inspect the account's newest amazon_mf_return_sync_runs status/error/stats.
   With no other failures, status should be completed, returns may legitimately
   be zero, and fba_financial_transactions_skipped should include the known refund.
4. Verify MF Returns last successful sync advances only for that completed run.
   If a genuine MF lookup still fails, expect failed status, error/source IDs,
   retained progress and an unchanged last-success timestamp.
5. If a PARTIAL report exists, inspect its error and retained report/document IDs.
   Confirm partial_reports_retried increments even after UTC rollover or when the
   original window is outside the rolling window. An unresolved original report
   must keep the overall run failed even if the current rolling report is empty.
   On recovery, verify return/observation counts do not grow from replay alone.
6. Check pending amazon_mf_return_finance_work for the configured account.
   finance_work_retried should advance on later runs even when posted dates have
   left the feed. Pending work must retain errors and keep the run failed; on
   recovery expect imported/excluded_fba and no duplicate refund accounting.
