# MBOP AWS Scheduler Plan

Last updated: 2026-07-12

## Architecture Decision

Use a separate ECS/Fargate scheduled-task path for Python sync jobs. Keep the web service web-only and cloud-safe:

```text
CLOUD_DEPLOYMENT=true
LOCAL_SYNC_ENABLED=false
```

EventBridge Scheduler owns scheduled execution. Web/API routes must not spawn
local Windows or Python scheduler jobs in cloud mode. Local Windows Task
Scheduler jobs are retired and should not be recreated unless a deliberate
local fallback is designed.

## Scheduler Image

The repo now includes `Dockerfile.scheduler` for a scheduler-only image. It includes:

- Python runtime
- `requirements.txt`
- `run_all_syncs.py`
- `integrations/`
- writable `/app/logs`, `/app/data`, and `/app/credentials`
- an entrypoint that writes `GOOGLE_APPLICATION_CREDENTIALS_JSON` to a file if that secret is supplied

Build from the repo root:

```powershell
docker build -f Dockerfile.scheduler -t mbop-scheduler:<tag> .
```

ECR repository:

```text
297464765814.dkr.ecr.us-west-2.amazonaws.com/mbop-scheduler
```

Validate locally or in ECS:

```powershell
docker run --rm mbop-scheduler:<tag> python run_all_syncs.py --group purchase-ingestion --list
```

## ECS Task Definition

Target:

```text
Task definition family: mbop-scheduler-task
Current deployed revision: mbop-scheduler-task:19
Container: mbop-scheduler
CPU: 512
Memory: 1024 MiB
Log group: /ecs/mbop-scheduler
Stream prefix: scheduled
```

Default command:

```json
["python", "run_all_syncs.py", "--group", "purchase-ingestion", "--list"]
```

Current ECR image:

```text
297464765814.dkr.ecr.us-west-2.amazonaws.com/mbop-scheduler@sha256:6d490c279a2cbb6f1f5c95caf6b8f84e72e804a490582d5ec947c51ca7085993
tag: scheduler-32ece9e3435f
```

The current ZFI-enabled scheduler task definition is digest-pinned. Legacy
`mbop-scheduler-task:1` is still tag-based on `:latest` for schedules that were
not changed in the ZFI rollout. Prefer digest-pinned task definition revisions
for future scheduler deployments.

EventBridge Scheduler should override the command per group:

```json
{
  "containerOverrides": [
    {
      "name": "mbop-scheduler",
      "command": ["python", "run_all_syncs.py", "--group", "purchase-ingestion"]
    }
  ]
}
```

## AWS Scheduler Groups

These group names are now accepted by `run_all_syncs.py`:

- `purchase-ingestion`: eBay buyer purchases, sourcing purchase matching
- `purchase-tracking`: EasyPost inbound purchase shipments
- `returns-order-problems`: eBay order problem returns/inquiries, EasyPost order problem returns
- `purchase-enrichment`: RevSeller enrichment, Keepa missing purchase titles
- `amazon-sales-recent`: Amazon sales orders, recent finances, Veeqo labels, profitability, ZFI business summary push
- `finance-refresh`: YNAB transactions, YNAB cash, Amazon finance balances, business value snapshot, ZFI business summary push
- `business-value-finalizer`: business value snapshot, ZFI business summary push
- `fba-inventory-daily`: Amazon FBA inventory, Amazon inventory planning, ZFI business summary push
- `fba-shipments`: Amazon FBA shipments, FBA EasyPost carrier tracking, ZFI business summary push
- `reconciliation`: inventory reconciliation with `--skip-if-unchanged`
- `repricing-catalog`: Amazon listing status, Informed repricing reports
- `sourcing-catalog`: unified daily catalog sourcing, sourcing listing availability,
  Matching Intelligence refresh
- `keepa-rolling-refresh`: Keepa active products
- `keepa-catalog-priority`: fast lightweight Keepa refresh for Send to Amazon,
  active sourcing opportunities, then broader known catalog ASINs
- `fba-pricing`: Keepa FBA prep pricing, Amazon Product Fees estimates

Manual/audit groups remain manual-only initially:

- `finance-audit`
- `listing-audit`
- `inventory-audit`

Do not use `all`, `core`, or `daily` for production AWS schedules.

## EventBridge Schedules

Production schedules are enabled in EventBridge Scheduler with timezone `America/Los_Angeles`. They launch scheduler tasks on `mbop-cluster1` through role `mbopEventBridgeSchedulerEcsRole`.

ZFI-enabled schedules currently launch `mbop-scheduler-task:4`: `mbop-amazon-sales-recent-day`, `mbop-amazon-sales-recent-catchup`, `mbop-finance-refresh-morning`, `mbop-finance-refresh-afternoon`, `mbop-finance-refresh-evening`, `mbop-fba-inventory-daily`, and `mbop-fba-shipments-active-window`. Other production schedules still use the older scheduler revision until their next deployment.

```text
mbop-purchase-ingestion-hourly: cron(0 7-22 ? * * *)
mbop-purchase-ingestion-catchup: cron(0 4 ? * * *)
mbop-purchase-tracking-hourly: cron(20 7-22 ? * * *)
mbop-purchase-tracking-catchup: cron(20 4 ? * * *)
mbop-returns-order-problems-day: cron(15 7,11,15,19 ? * * *)
mbop-returns-order-problems-late: cron(0 22 ? * * *)
mbop-purchase-enrichment: cron(35 8/2 ? * * *)
mbop-amazon-sales-recent-day: cron(50 7,9,11,13,15,17,19,21 ? * * *)
mbop-amazon-sales-recent-catchup: cron(30 4 ? * * *)
mbop-finance-refresh-morning: cron(30 6 ? * * *)
mbop-finance-refresh-afternoon: cron(0 14 ? * * *)
mbop-finance-refresh-evening: cron(45 20 ? * * *)
mbop-fba-inventory-daily: cron(30 20 ? * * *)
mbop-fba-shipments-active-window: cron(40 8,12,16,20 ? * * *)
mbop-reconciliation: cron(0 21 ? * * *)
mbop-repricing-catalog: cron(30 21 ? * * *)
mbop-sourcing-catalog: cron(10 0 ? * * *)
mbop-keepa-rolling-refresh: cron(10 1,9,17 ? * * *)
mbop-keepa-catalog-priority: rate(5 minutes)
```

Most schedules use the default scheduler task size of `512 CPU / 1024 MB`.
`mbop-sourcing-catalog` is intentionally overridden to `1024 CPU / 2048 MB`
because `Matching intelligence refresh` was killed by ECS with
`OutOfMemoryError` at the default 1 GiB size. A manual 2 GiB retry on
2026-06-21 completed successfully.
`mbop-sourcing-catalog` runs at 12:10 AM in `America/Los_Angeles`, shortly
after the eBay Browse quota reset, so the unified daily coverage-cycle runner
can spend the usable quota before lower-priority Browse consumers.

`fba-pricing`, `finance-audit`, `listing-audit`, and `inventory-audit` remain manual/on-demand.

## Secrets Manager Entries

Create these if missing. Map each secret to the listed environment variable in the scheduler task definition.

```text
/mbop/prod/ebay/client-id -> EBAY_CLIENT_ID
/mbop/prod/ebay/client-secret -> EBAY_CLIENT_SECRET
/mbop/prod/ebay/refresh-token -> EBAY_REFRESH_TOKEN
/mbop/prod/easypost/api-key -> EASYPOST_API_KEY
/mbop/prod/easypost/webhook-token -> EASYPOST_WEBHOOK_TOKEN / EASYPOST_WEBHOOK_SECRET (web task)
/mbop/prod/amazon-spapi/client-id -> AMAZON_SP_API_CLIENT_ID
/mbop/prod/amazon-spapi/client-secret -> AMAZON_SP_API_CLIENT_SECRET
/mbop/prod/amazon-spapi/refresh-token -> AMAZON_SP_API_REFRESH_TOKEN
/mbop/prod/amazon-spapi/marketplace-id -> AMAZON_SP_API_MARKETPLACE_ID
/mbop/prod/amazon-spapi/aws-access-key-id -> AMAZON_SP_API_AWS_ACCESS_KEY_ID
/mbop/prod/amazon-spapi/aws-secret-access-key -> AMAZON_SP_API_AWS_SECRET_ACCESS_KEY
/mbop/prod/ynab/access-token -> YNAB_PERSONAL_TOKEN
/mbop/prod/keepa/api-key -> KEEPA_API_KEY
/mbop/prod/revseller/google-sheet-id -> REVSELLER_GOOGLE_SHEET_ID
/mbop/prod/google/service-account-json -> GOOGLE_APPLICATION_CREDENTIALS_JSON
/mbop/prod/veeqo/api-key -> VEEQO_KEY
/mbop/prod/informed/api-key -> INFORMED_REPRICER_API_KEY
/mbop/prod/openai/api-key -> OPENAI_API_KEY
/mbop/prod/zfi/supabase-url -> ZFI_SUPABASE_URL
/mbop/prod/zfi/supabase-service-role-key -> ZFI_SUPABASE_SERVICE_ROLE_KEY
```

These secrets exist in AWS Secrets Manager. Core MBOP scheduler secrets were created as of 2026-06-20, and the ZFI outbound secrets were added on 2026-06-28 from local `.env` values without printing secret contents.

Optional non-secret environment:

```text
SUPABASE_URL=https://froeucjkcepuhgwisped.supabase.co
KEEPA_DOMAIN_ID=1
KEEPA_API_ENDPOINT=https://api.keepa.com
REVSELLER_WORKSHEET_NAME=Sheet1
OPENAI_MATCHING_MODEL=<approved model>
```

## IAM

The task execution role needs ECR pull, CloudWatch Logs write, and Secrets Manager read access for scheduler secrets:

```json
{
  "Effect": "Allow",
  "Action": ["secretsmanager:GetSecretValue"],
  "Resource": ["arn:aws:secretsmanager:us-west-2:<account-id>:secret:/mbop/prod/*"]
}
```

Add `kms:Decrypt` only if the secrets use a customer-managed KMS key.

The task role can remain minimal until a workflow needs AWS API writes beyond logs and secret injection.

Current execution role:

```text
arn:aws:iam::297464765814:role/ecsTaskExecutionRole
```

It has the AWS-managed `AmazonECSTaskExecutionRolePolicy` plus inline policy `mbop-phase1-secret-read`, which now allows `secretsmanager:GetSecretValue` for the existing phase-1 Supabase secret and `/mbop/prod/*`.

EventBridge Scheduler role:

```text
arn:aws:iam::297464765814:role/mbopEventBridgeSchedulerEcsRole
```

The schedules are created and enabled. A one-time EventBridge Scheduler smoke test launched an ECS task successfully and auto-deleted after completion.

Live verification on 2026-06-21/2026-06-22 found 18 enabled `mbop-*`
EventBridge schedules targeting ECS `runTask`.

## Telemetry

ECS task-local files are not durable. `sql/2026-06-20_add_scheduler_telemetry.sql` has been applied, including service-role grants.

Telemetry tables:

- `scheduler_runs`
- `scheduler_run_jobs`
- `scheduler_job_definitions`
- `scheduler_domain_freshness`
- `scheduler_locks`

`run_all_syncs.py` writes scheduler runs and per-job records to Supabase telemetry tables. System Health reads cloud scheduler run/job history when `CLOUD_DEPLOYMENT=true`.

The scheduler captures each job's stdout/stderr, parses summary lines into
standard counters such as rows read/inserted/updated/skipped and stores
additional human-readable metrics in `scheduler_run_jobs.metadata.metrics`.
System Health group drawers display those counters and metrics in recent-run
history. Jobs only show the richer metrics after they have run on scheduler
image `sha256:77b46ba7a474bc718fb34c994a763ebb98200c637d48982eb5c1474ca43ca58a`
or later; ZFI-enabled groups now run on image
`sha256:260dfc320f6f55638c90631d3a4823507e4f7d1f9fa5fab79625d7bb7be252dd`.

Smoke validation completed:

- Local container `purchase-ingestion --list`: passed.
- ECS one-off `purchase-ingestion --list`: passed.
- ECS one-off `--list` checks for all AWS scheduler groups: passed.
- Supabase telemetry smoke run: passed after grants were applied.
- Real ECS `purchase-ingestion` run: passed.
- One-time EventBridge Scheduler to ECS target smoke: passed.
- Manual ECS `sourcing-catalog` run at `1024 CPU / 2048 MB`: passed after the
  default 1 GiB task size hit `OutOfMemoryError`.
- Production telemetry after the migration shows successful `ok` runs for every
  enabled scheduler group: `purchase-ingestion`, `purchase-tracking`,
  `returns-order-problems`, `purchase-enrichment`, `amazon-sales-recent`,
  `finance-refresh`, `fba-inventory-daily`, `fba-shipments`,
  `reconciliation`, `repricing-catalog`, `sourcing-catalog`, and
  `keepa-rolling-refresh`.
- ECS one-off expanded ZFI payload smoke run on `mbop-scheduler-task:4`:
  passed on 2026-06-28 with `ZFI business summary pushed`.

## Keepa Guardrails

Current deep `offers=20` plus `stock` mode costs roughly 9.8 tokens per ASIN for active listings. Keepa refills at about 5 tokens/minute with a 300-token cap.

Current scheduler-safe defaults:

```text
keepa-catalog-priority:
  --source catalog_priority
  --batch-size 25
  --limit 25
  --stale-days 7
  --min-tokens 25
  --no-history
  --no-rating

keepa-rolling-refresh:
  --batch-size 10
  --limit 10
  --min-tokens 150

fba-pricing:
  --batch-size 10
  --limit 10
  --min-tokens 150
```

The fast `keepa-catalog-priority` schedule is stats-only and omits rating,
offer, stock, and history payloads. It is intended to track the observed
5-token/minute Keepa refill rate: 25 ASINs every 5 minutes, skipping ASINs with
snapshots newer than 7 days. Deep `offers`/`stock` mode remains reserved for
slower selected candidate/pricing workflows.
