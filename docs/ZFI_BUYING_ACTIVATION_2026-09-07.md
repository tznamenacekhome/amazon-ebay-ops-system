# ZFI Buying production activation — 2026-09-07

Status: **ACTIVE**, production HTTPS and ECS verification passed.

## Deployed artifacts

- Application commit: `3c1273029d18`.
- Scheduler: `mbop-scheduler-task:84`.
- Scheduler image: `sha256:97ed7bbd30bfad4152cffca1a70b5037c963de4a6aad7f49de6e2c11e47f055c`.
- Stable web: `mbop-web-task:136` (one running task, rollout COMPLETED).
- Web image: `sha256:25e7acc7cdca9ef71d64df1700d93fbac5cc4a344eabe30630ed7306edd6e45b`.
- Supabase project: `froeucjkcepuhgwisped`.
- Applied migration: `20260907000000_mbop_zfi_buying_contract.sql`.
- All 14 local/remote shared migration versions aligned after application.
  The CLI emitted a nonfatal pg-delta catalog-cache certificate-file warning;
  the migration, remote ledger and actual view were independently verified.

The approved view/fields/cost semantics are unchanged. Deployment review found
one real concurrency defect: the existing Purchases/Dashboard refresh groups
also contain the buyer importer. Their orchestrator now claims the same lock,
and their web launcher uses UUID run IDs compatible with scheduler telemetry.
Legacy active runs in those groups are respected by the reservation RPC.

## ZFI server configuration and credential handoff

```dotenv
MBOP_BUYING_BASE_URL=https://mbop.midnightblueenterprises.com
MBOP_BUYING_READ_TOKEN=<read token from the dedicated secret>
MBOP_BUYING_REFRESH_TOKEN=<refresh token from the dedicated secret>
```

Credential values are stored in AWS Secrets Manager, account `297464765814`,
region `us-west-2`:

- `/mbop/prod/zfi-buying/read-token`
- `/mbop/prod/zfi-buying/refresh-token`

Use an authorized operator's Secrets Manager console access to retrieve each
value directly into ZFI's server secret configuration. No values are in this
repository, report, browser, or deployment output. ZFI receives neither MBOP's
Supabase service-role key nor its general administrator credential. ZFI code
and configuration were deliberately not changed by this MBOP activation.

MBOP ECS injects these secrets as `MBOP_ZFI_BUYING_READ_TOKEN` and
`MBOP_ZFI_BUYING_REFRESH_TOKEN`. It also sets `MBOP_ZFI_REFRESH_ENABLED=true`
and `MBOP_ZFI_PURCHASE_TASK_DEFINITION=mbop-scheduler-task:84`.

All calls use HTTPS and `Authorization: Bearer <token>`.
The read token authorizes purchase/status GET only. The separate refresh token
authorizes refresh POST and purchase/status GET. Never use NEXT_PUBLIC_*.

## Production calls

Read facts:

```http
GET /api/integrations/zfi/buying/purchases?from=2024-09-10&to=2024-10-01&limit=200
Authorization: Bearer <MBOP_BUYING_READ_TOKEN>
```

Returns `contract_version`, `from`, `to`, `facts`, `next_cursor`. `from` is
inclusive, `to` exclusive, maximum window 93 days. Follow `next_cursor` as
`after` with the same dates. Upsert by `source_purchase_id`.

Request one refresh:

```http
POST /api/integrations/zfi/buying/refresh
Authorization: Bearer <MBOP_BUYING_REFRESH_TOKEN>
Content-Type: application/json

{}
```

HTTP 202 means accepted for execution, not completed. The response includes
`disposition` (`accepted` or `already_running`), `run_id`, `status`,
`requested_at`, `started_at`, `completed_at`, `error_code`, `result_summary`,
`status_url`, and `contract_version`. An overlapping call returns the existing
run ID. Arbitrary groups/commands are rejected. Empty body is also supported.

```http
GET /api/integrations/zfi/buying/refresh/6f6377f2-942d-4a5b-a4e2-79fa1a0fb3c2
Authorization: Bearer <MBOP_BUYING_READ_TOKEN>
```

Status GET returns the same status fields without `disposition`. States:
`queued`, `running`, `succeeded`, `failed`. Poll with backoff; read updated facts
after `succeeded`. Unknown UUID: 404; bad credential: 401; invalid input: 400;
unavailable dependencies: 503. No raw errors or AWS task ARNs are exposed.

## Production evidence

- Read credential returned HTTP 200 with all 21 approved fields. SQL field
  types and JSON scalar/null types matched the contract.
- Anonymous/invalid credentials returned 401. Read-token POST returned 401.
  Arbitrary-group refresh POST returned 400. Unrelated `/api/purchases` still
  redirected to Cognito; no broad API authentication bypass was added.
- Earliest date: **2024-09-10**, four reportable orders on that date. The
  September 1–10 exclusive window was empty; September 2024 is partial.
- View contained 3,361 logical eBay orders and 5,521 recorded units at activation.
- Legacy order `04-14542-23405`: two headers, one fact, two units, $12.47.
  `08-13745-49158`: eight headers, one fact, nine units, $170.95.
  Repeated order-header totals are not summed.
- Five missing-cost items remained excluded. Entirely excluded orders return
  zero reportable units/spend; the mixed order retains 30 reportable units and
  $406.01. Its recorded total is null because excluded costs are incomplete.
- Existing schedule's exact ECS target payload ran successfully on revision 84:
  run `7e1ae50b-2914-4547-8366-aa448d75337d`, status `ok`, process exit 0.
  This was a manual invocation of the existing target, not a changed schedule
  or a claim to have waited for the next automatic EventBridge tick. The
  existing EventBridge role already permits revision 84 and both ECS roles.
- Two simultaneous ZFI POSTs returned the SAME run ID, with `accepted` and
  `already_running`. Exactly one corresponding ECS task existed:
  `9b3a45178b8c4cb9bf8fbb9a1fa5c92e`.
- Successful ZFI run: `6f6377f2-942d-4a5b-a4e2-79fa1a0fb3c2`.
  Queued at `2026-09-07T20:40:51.523859Z`, running at
  `2026-09-07T20:41:18.018853Z`, succeeded at
  `2026-09-07T20:41:45.905143Z`. Subsequent status GET with the read token
  confirmed success; refreshed September facts were readable.
- All **20** EventBridge schedule definitions were compared against backups.
  Only `TaskDefinition` changed from revision 74 to 84 inside the hourly and
  catchup purchase-ingestion target payloads. Schedule expression, timezone,
  state, retry/window settings, command, environment, networking and role were
  preserved. The other 18 schedule definitions are unchanged.
- Baselines covered 3,412 purchase headers and 3,444 item rows across suppliers.
  Migration changed no existing business fields. After both ingestion smoke
  runs, 16 headers/items had normal `import_batch_id` updates; quantities,
  costs, other business fields and raw-payload hashes were unchanged. No
  purchase rows were inserted/deleted; no sales COGS was recalculated.
- Tests passed: 12 buyer/refund/FIFO, four worker locking, three isolated SQL
  (including eight concurrent claims), five scheduler diagnostics, Node API
  harness, targeted ESLint, and the deployed Docker Next.js build/type check.
  Production API/ECS tests were performed against the real HTTPS origin.
  Browser UI verification was unavailable because no browser surface was
  available; this server-only integration was verified directly over HTTPS.

## Access and rollback

HTTPS ALB rules at priorities 20/21 require the MBOP hostname and exact GET
purchase/status or POST refresh paths. Other methods/paths retain the existing
Cognito behavior. Existing security groups/subnets are reused. Added IAM grants
are limited to the two secret ARNs for web execution and DescribeTasks in the
MBOP cluster for the web task. Existing RunTask/PassRole scope was sufficient.

Rollback configuration and verification evidence are saved locally under
`logs/diagnostics/zfi-activation-20260907/` (ignored by Git). It contains original
schedules, web/task definitions, ALB rules, IAM policies, normalized purchase
baselines and raw hashes. It contains no new integration token values.

To disable refresh, deploy the same image with `MBOP_ZFI_REFRESH_ENABLED=false`;
revision 135 is the prepared read-enabled/refresh-disabled configuration.
Wait for active ingestion to finish before any worker rollback. Do not restore
revision 74 workers while refresh remains enabled. Original web revision was
133; original purchase schedules used 74. Preserve the additive migration and
history on rollback; no destructive schema rollback is required. Remove only
the dedicated ALB rules if taking the entire integration offline.

## ZFI limitations

Refunds are already in item acquisition costs. `refund_amount=null` is
intentional and MUST NOT trigger another deduction. Manual overrides and
per-unit cent rounding remain authoritative; this is not an exact bank-charge
ledger. No tax redesign, historical backfill or older-refund discovery was
added. Existing sales COGS is not retrospectively recomputed.

History starts September 10, 2024; the opening month is partial. Respect
exclusions and review flags. Source timestamps begin at migration time for
unchanged history. Use bounded date-window rescans; this is not a deletion
change feed. Ambiguous launch retries older than 30 minutes require operator
reconciliation; reservations are never stolen based only on elapsed time.
