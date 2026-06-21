# MBOP AWS Scheduler Plan

Last updated: 2026-06-20

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
Current revision: mbop-scheduler-task:1
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
297464765814.dkr.ecr.us-west-2.amazonaws.com/mbop-scheduler:latest
digest: sha256:c7a24284e3bf17167e6783600d734c5ae8e1797ebd6cc5e1b112ccfabd253206
```

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
- `amazon-sales-recent`: Amazon sales orders, recent finances, Veeqo labels, profitability
- `finance-refresh`: YNAB transactions, YNAB cash, Amazon finance balances, business value snapshot
- `business-value-finalizer`: business value snapshot
- `fba-inventory-daily`: Amazon FBA inventory, Amazon inventory planning
- `fba-shipments`: Amazon FBA shipments, FBA EasyPost carrier tracking
- `reconciliation`: inventory reconciliation with `--skip-if-unchanged`
- `repricing-catalog`: Amazon listing status, Informed repricing reports
- `sourcing-catalog`: sourcing listing availability, matching intelligence refresh
- `keepa-rolling-refresh`: Keepa active products
- `fba-pricing`: Keepa FBA prep pricing, Amazon Product Fees estimates

Manual/audit groups remain manual-only initially:

- `finance-audit`
- `listing-audit`
- `inventory-audit`

Do not use `all`, `core`, or `daily` for production AWS schedules.

## EventBridge Schedules

Production schedules are enabled in EventBridge Scheduler with timezone `America/Los_Angeles`. They launch `mbop-scheduler-task:1` on `mbop-cluster1` through role `mbopEventBridgeSchedulerEcsRole`.

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
mbop-sourcing-catalog: cron(0 22 ? * * *)
mbop-keepa-rolling-refresh: cron(10 1,9,17 ? * * *)
```

Most schedules use the default scheduler task size of `512 CPU / 1024 MB`.
`mbop-sourcing-catalog` is intentionally overridden to `1024 CPU / 2048 MB`
because `Matching intelligence refresh` was killed by ECS with
`OutOfMemoryError` at the default 1 GiB size. A manual 2 GiB retry on
2026-06-21 completed successfully.

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
```

These secrets exist in AWS Secrets Manager as of 2026-06-20, created from local `.env` values without printing secret contents.

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

## Telemetry

ECS task-local files are not durable. `sql/2026-06-20_add_scheduler_telemetry.sql` has been applied, including service-role grants.

Telemetry tables:

- `scheduler_runs`
- `scheduler_run_jobs`
- `scheduler_job_definitions`
- `scheduler_domain_freshness`
- `scheduler_locks`

`run_all_syncs.py` writes scheduler runs and per-job records to Supabase telemetry tables. System Health reads cloud scheduler run/job history when `CLOUD_DEPLOYMENT=true`.

Smoke validation completed:

- Local container `purchase-ingestion --list`: passed.
- ECS one-off `purchase-ingestion --list`: passed.
- ECS one-off `--list` checks for all AWS scheduler groups: passed.
- Supabase telemetry smoke run: passed after grants were applied.
- Real ECS `purchase-ingestion` run: passed.
- One-time EventBridge Scheduler to ECS target smoke: passed.

## Keepa Guardrails

Current deep `offers=20` plus `stock` mode costs roughly 9.8 tokens per ASIN for active listings. Keepa refills at about 5 tokens/minute with a 300-token cap.

Current scheduler-safe defaults:

```text
keepa-rolling-refresh:
  --batch-size 10
  --limit 10
  --min-tokens 150

fba-pricing:
  --batch-size 10
  --limit 10
  --min-tokens 150
```

Future improvement: add a light stats-only Keepa mode without `offers` and `stock`, and reserve deep offer/stock mode for selected candidates.
