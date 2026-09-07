# ZFI Buying integration

Version: 2026-09-07. **ACTIVE in production**, verified 2026-09-07.
Migration applied; scheduler revision 84 and stable web revision 136 use
commit 3c1273029d18. Read/auth/history and concurrent-refresh smoke tests
passed. [Activation report and secure credential handoff](ZFI_BUYING_ACTIVATION_2026-09-07.md).

## Ownership and accounting

MBOP owns purchases, purchase-item quantity/cost, and ingestion execution.
ZFI owns Buying Power, monthly financial interpretation and purchase-to-YNAB
reconciliation. This is an explicitly authorized narrow operational facts
pull, in addition to the existing summary push. It does not give MBOP access
to ZFI, YNAB, or personal finance data.

Acquisition cost uses the existing normalized purchase_items.unit_cost times
quantity, after recorded adjustments. Do not add order-header shipping or tax
to that cost or subtract a refund again in ZFI. Vendor shipping and handling
are already included by the importer. Later FBA freight, prep, labels,
fulfillment and selling fees are not added to this contract.

Per the operator's updated requirement, rare sales-tax differences are not a
blocker: routine purchases use a reseller permit. No historical acquisition
cost audit, tax redesign, cost backfill or FIFO recalculation is included.

The partial-refund fix allocates a USD multi-product refund by merchandise
price times quantity. A $5 refund on $20/$30 lines reduces stored costs to
$18/$27. Quantity is included in the weighting, and shipping does not change
the weights. Tests verify those corrected values reach build_item_payload's
unit_cost and are read as FIFO source-lot unit costs. Manual cost overrides
remain authoritative. Existing sales COGS is not retroactively recalculated.
The existing single-transaction/foreign-currency/full-cancellation paths
remain separate. The importer processes refunds returned in its existing
lookup window even if tracking is present; it does not discover every older
refund automatically.

## Database contract

Migration: supabase/migrations/20260907000000_mbop_zfi_buying_contract.sql.
View: public.zfi_ebay_purchase_facts.
Grain: ONE logical eBay order, grouping all its purchase headers and DISTINCT
stored purchase-item rows through their purchase_id relationship. There is no
shipment join, no multiplication from tracking rows, and no sum of repeated
order-header totals. Items are not deduplicated by title or price: separate
legacy item rows and manual split children can represent legitimate units.

| Field | Meaning |
|---|---|
| contract_version | 2026-09-07 |
| source_purchase_id | Deterministic UUID from the logical eBay order key; not an arbitrary winning purchase header UUID |
| ebay_order_id | Trimmed supplier order ID; null if unavailable, with separate per-purchase grouping for missing IDs |
| purchase_date | Earliest normalized order_date within the logical order |
| date_needs_review | Headers disagree on date or a date is missing |
| cost_currency | USD, the MBOP normalized cost currency; not a claim about original checkout currency |
| unit_count | Sum of reportable item quantities |
| recorded_unit_count | Sum of all stored item quantities, including excluded items |
| excluded_unit_count | Quantity excluded by explicit flag, Cancelled/Return Opened item status, or cancelled order header |
| acquisition_cost_total | Reportable quantity times current unit_cost; null if a reportable item has missing cost or invalid quantity |
| recorded_acquisition_cost_total | Same calculation across all stored items; null if any item is incomplete |
| cost_needs_review | A reportable item has missing cost or invalid quantity |
| exclusion_status | included, partially_excluded, excluded or no_items |
| purchase_status | Single normalized item status, or mixed; cancelled order headers override their item statuses |
| source_purchase_count | Number of grouped purchase headers; greater than one signals legacy multi-header representation |
| source_item_count | Number of stored item rows, not number of units |
| manual_split_item_count | Number of manual split child rows included in the logical order |
| cost_basis | mbop_item_cost_after_recorded_adjustments |
| refund_amount | Null: no independently authoritative normalized order-refund ledger is exposed |
| refund_status | not_separately_normalized; null refund amount does NOT mean no refund |
| source_updated_at | Latest dedicated source-change timestamp across the order's headers and items |

Do not interpret recorded_acquisition_cost_total as an exact bank charge.
It provides the stored cost total before reporting exclusions, suitable for
matching/review alongside order ID and date. Per-unit cent rounding, overrides,
split allocation and net refunds can differ from individual vendor payment
transactions. ZFI must reconcile this fact against its own transaction history;
MBOP does not send card/account details or raw checkout JSON.

Monthly units/spend: group purchase_date by month and sum unit_count and
acquisition_cost_total. Do not silently convert a null acquisition total to
zero; surface cost_needs_review/date_needs_review. Preserve excluded orders
for reconciliation while their reportable quantities/costs are zero.

The migration adds zfi_source_updated_at to purchases and purchase_items,
initialized at migration time. Triggers advance it on changes, including
parent changes when an item is inserted, moved, updated or deleted. This is
an initial synchronization baseline, NOT reconstructed historical edit times.
The HTTP contract uses date-window rescans and stable-ID upserts, not a
deletion-complete change feed. Do not depend on it as a deletion ledger.

## Historical coverage

Earliest validated normalized reporting date: **2024-09-10**. September 2024
is a partial opening month, not a claim of all pre-MBOP business history.
Read-only checks on September 7 found:

- 3,408 eBay purchase headers, 3,440 item rows, 5,521 recorded units.
  These are raw coverage counts, not exclusion-adjusted reporting totals.
- Every month from September 2024 through September 2026 is represented.
- No missing normalized dates and no null/nonpositive quantities.
- Five missing-cost rows, all explicitly excluded from purchase reporting.
- Four costed/reportable items on the first date; ten manual split children
  across the history.
- Several legacy eBay IDs span multiple headers. For example,
  04-14542-23405 has two headers and two item rows. They must both contribute
  their respective units/costs, while the API returns one order fact.

Existing repository reconciliation records show 2024/2025 matched the legacy
spreadsheet, with current MBOP purchases authoritative from 2026-05-16. A
previous $4.05 spreadsheet variance is documented in KNOWN_ISSUES.md. This
task validates structural continuity and usable current quantities/costs; it
does not re-audit historical cost basis or certify completeness before
2024-09-10. No history is deleted or reimported.

## HTTP contract

All endpoints use Authorization: Bearer <dedicated token>, are server-only,
and return Cache-Control: no-store. No cookie/Cognito identity or general
MBOP admin token substitutes for these dedicated credentials.

### Read purchase facts

GET /api/integrations/zfi/buying/purchases?from=2026-07-01&to=2026-08-01&limit=200

from is inclusive; to is exclusive. Maximum window: 93 days. limit: 1-500,
default 200. Response: contract_version, from, to, facts, next_cursor.
Follow next_cursor as the after UUID using the SAME dates. Null cursor means
the window is complete. Only fixed contract columns can be requested.
Refetch date windows after successful refresh, upserting by source_purchase_id.
For history, iterate monthly windows beginning 2024-09-10.

### Request refresh

POST /api/integrations/zfi/buying/refresh with empty body or {}.
Only the refresh token authorizes this method. Arbitrary groups/commands/body
fields are rejected. Response HTTP 202 includes disposition accepted or
already_running, run_id, status, requested_at, started_at, completed_at,
error_code, result_summary and status_url.

The fixed command is python run_all_syncs.py --group purchase-ingestion
--run-id <UUID>. This invokes existing buyer purchase ingestion and sourcing
purchase matching through _awsScheduler.ts. No local Python/Windows process
is started by this API.

### Poll status

GET /api/integrations/zfi/buying/refresh/<run_id> using either token.
States: queued, running, succeeded, failed. Poll every 5-10 seconds with
backoff. Only succeeded means ZFI should immediately read updated facts.
Degraded/blocked/cancelled scheduler results map to failed. An ECS STOPPED
task without successful telemetry maps to failed even if its process exit
code is zero. Status checks reconcile terminal scheduler/ECS results into
the request row; they never launch work. Raw error messages, task ARNs and
operational payloads are not exposed to ZFI.

Responses: 400 invalid input, 401 bad credential, 404 unknown request,
503 unconfigured/unavailable dependency. The API does not manufacture a
successful result when AWS or database status cannot be read.

## Concurrency and recovery

mbop_claim_purchase_ingestion serializes reservation under a PostgreSQL
transaction advisory lock and a partial unique index permitting one active
request. Both API requests and every orchestrator group containing the buyer importer claim this
same reservation, including existing Purchases/Dashboard refresh. Those web refreshes now use UUID run IDs required by scheduler telemetry. Other requests reference the owner. Existing running
purchase-ingestion telemetry is also respected. Schedules keep their group,
cadence and arguments; the worker startup guard prevents overlapping work.

ECS launch retries use the reservation UUID as clientToken and the pinned
task definition. A lost response leaves the reservation queued, with
launch_unconfirmed_retry_post. Retrying POST reuses the same launch identity.
Retries after 30 minutes require operator reconciliation instead of automatic
relaunch. AWS token retention can be shorter than 24 hours (task lifetime plus
one hour), so the API uses a conservative retry window.
[AWS ECS idempotency](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ECS_Idempotency.html).

There is no timeout-based lock stealing. If telemetry and ECS cannot prove
completion, leave the reservation in place. An operator must verify the ECS
task is terminal, back up the row, and reconcile status. Never clear an active
reservation merely because a browser/ZFI request timed out.

## Required configuration and activation

ZFI SERVER environment (never NEXT_PUBLIC_*):

- MBOP_BUYING_BASE_URL=https://mbop.midnightblueenterprises.com
- MBOP_BUYING_READ_TOKEN=<dedicated random read token>
- MBOP_BUYING_REFRESH_TOKEN=<different dedicated random refresh token>

MBOP web SERVER environment / AWS Secrets Manager:

- MBOP_ZFI_BUYING_READ_TOKEN: same read token, at least 32 characters.
- MBOP_ZFI_BUYING_REFRESH_TOKEN: separate refresh token, at least 32 characters.
- MBOP_ZFI_REFRESH_ENABLED=true: leave unset until coordinated activation.
- MBOP_ZFI_PURCHASE_TASK_DEFINITION: explicit immutable scheduler revision
  containing the refund fix and shared purchase-ingestion lock.
- Existing SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY stay solely in MBOP.
- Existing AWS scheduler cluster, container, subnet and security-group config
  is reused. Web IAM needs RunTask on the approved scheduler revision/family,
  PassRole for its existing task/execution roles, and DescribeTasks for status.

The database view grants SELECT only to service_role and is not granted to
anon/authenticated. ZFI receives neither that role key nor general admin
credentials: its tokens authorize only this fixed HTTP contract. The refresh
token also permits fact/status reads. Equal read/refresh token values fail
closed rather than silently granting write capability to the read token.

Activation order (authorized on 2026-09-07):

1. Review the exact migration above, verify MBOP project
   froeucjkcepuhgwisped, run supabase migration list, and reconcile the COMPLETE
   shared migration history before the documented supabase db push workflow.
   Apply only with the operator's schema authorization. No College Planner
   migration may be altered.
2. Deploy the corrected shared-lock runtime to every purchase-ingestion
   launcher before enabling the ZFI refresh API. Older deployed workers do
   not participate in the lock. Preserving cadence/group arguments is required;
   do not enable refresh while old scheduler revisions can bypass the guard.
   Activation updates only the task revision in the two purchase-ingestion
   schedule targets. Every other schedule field remains unchanged.
3. Provision the two secrets and web IAM permissions. Configure narrowly
   scoped ALB forward rules for the three Buying paths so server requests reach
   their own bearer-token checks instead of Cognito redirects. Do not bypass
   authentication for other /api paths. Keep normal web ingress restrictions.
4. Deploy web, verify anonymous/incorrect/read-token POST rejection and correct
   server-token GET access, then enable refresh and verify one run plus a
   concurrent already_running response in AWS. Verify status and updated facts.

Production activation provisions dedicated secrets, narrow host/method/path
ALB rules, scoped secret/status IAM permissions and updated worker/web task
revisions. Existing schedules retain their cadence and all other settings.
Roll back API enablement first if needed; never roll back workers to
lock-unaware code while the ZFI trigger remains enabled.

## Tests

Local verification on 2026-09-07 passed: 12 buyer/refund tests, 4 worker-lock
tests, 3 PostgreSQL migration/concurrency tests, the Node API contract harness,
targeted ESLint, and the Next.js production build/type check. Production HTTPS/ECS verification also passed; see the activation report.

- Buyer-sync tests verify proportional refunds, quantity, shipping weights,
  repeated calculations, cent rounding, cancellation behavior and FIFO cost flow.
- SQL tests use a disposable network-isolated PostgreSQL container: actual
  migration, legacy multi-header order aggregation, quantities, manual splits,
  exclusions, null costs, source watermark updates, grants, reservation ownership,
  eight concurrent claims and pre-existing scheduled runs.
- API tests cover credential scope, bounded/paginated facts, fixed launch group,
  same-token ambiguous retries, active run, retry expiry, success/degraded/crash
  status and rejection of arbitrary command/group input.
- Worker tests cover fail-closed claims and success/failure finalization.

Run commands:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -p test_ebay_sync_buyer_purchases.py
.venv\Scripts\python.exe -m unittest discover -s tests -p test_purchase_ingestion_lock.py
node --test web/app/api/integrations/zfi/buying/contract.test.mjs
# Optional isolated SQL tests; never point at production:
$env:MBOP_SQL_TEST_CONTAINER='mbop-zfi-contract-test'
.venv\Scripts\python.exe -m unittest discover -s tests -p test_zfi_buying_sql.py
```
