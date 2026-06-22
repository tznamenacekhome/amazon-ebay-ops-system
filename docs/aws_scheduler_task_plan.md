# MBOP AWS Scheduler Task Plan

Superseded note: this was the first scheduler task analysis and is retained
only as historical planning context. Do not use task revisions, blockers, or
"before schedules can run" statements in this file as current state. The
current authoritative scheduler plan is
`docs/aws/MBOP_AWS_SCHEDULER_PLAN.md`, and the current operations runbook is
`docs/aws/MBOP_AWS_OPERATIONS_RUNBOOK.md`.

## Goal

Create a separate ECS/Fargate scheduled-task path for MBOP sync jobs using EventBridge Scheduler. Supabase remains the source of truth. The scheduler task should run:

```text
python run_all_syncs.py --group <GROUP_NAME>
```

Target ECS state:

- ECS cluster: `mbop-cluster1`
- Web service: `mbop-web-service`
- Historical web task definition at the time of this analysis:
  `mbop-web-task:2`
- Current web container name: `mbop-web`
- Proposed scheduler task definition: `mbop-scheduler-task`
- Proposed scheduler container name: `mbop-scheduler`

## Image Review

The current deployed web image should not be used for scheduler jobs as-is.

Evidence from `web/Dockerfile`:

- Build context is `./web`, per `docs/cloud_deployment_phase1.md`.
- Final image is `node:24-alpine`.
- Final image copies only:
  - `package.json`
  - `package-lock.json`
  - `.next`
  - `public`
  - `scripts`
- Final command is `npm start`.
- It does not copy repository-root files such as:
  - `run_all_syncs.py`
  - `integrations/`
  - `requirements.txt`
- It does not install Python or Python dependencies.

Historical conclusion at the time of this analysis: `mbop-web-task:2` could
not run `python run_all_syncs.py --group <GROUP_NAME>`.

Recommended path: build a scheduler-capable MBOP image from the repository root, or adjust the Docker build so the same image contains both the Next.js app and Python scheduler assets. Until that image exists, ECS command overrides alone are not enough.

## Image Recommendation

Use the same ECR repository/tag family as the web task only after the image includes scheduler assets. Two viable options:

1. Unified MBOP image:
   - Include Next.js web runtime.
   - Include Python runtime.
   - Copy `run_all_syncs.py`, `integrations/`, and `requirements.txt`.
   - Install `requirements.txt`.
   - Web service keeps command `npm start`.
   - Scheduler tasks override command to `python run_all_syncs.py --group <GROUP_NAME>`.

2. Separate scheduler image:
   - Use a Python base image.
   - Copy only scheduler/integration files.
   - Install `requirements.txt`.
   - Smaller and cleaner, but not the same image as the web task.

Given the stated goal, prefer option 1 only if keeping one image is operationally important. Otherwise, option 2 is simpler and lower risk.

## Scheduler Task Definition

Name:

```text
mbop-scheduler-task
```

Launch type:

```text
Fargate
```

Container name:

```text
mbop-scheduler
```

Image:

```text
Same MBOP image as web only after the image includes Python scheduler assets.
```

Default command:

```json
["python", "run_all_syncs.py", "--group", "purchase-ingestion"]
```

EventBridge Scheduler should override the command per schedule.

Working directory:

```text
/app
```

This assumes `run_all_syncs.py` is copied to `/app/run_all_syncs.py` and `integrations/` is copied to `/app/integrations/`.

## Cloud Flags

Use:

```text
CLOUD_DEPLOYMENT=true
LOCAL_SYNC_ENABLED=false
```

Reasoning:

- `CLOUD_DEPLOYMENT=true` makes cloud behavior explicit.
- `LOCAL_SYNC_ENABLED=false` should remain false because it controls web/API endpoints that spawn local Windows/Python jobs. In ECS, scheduled jobs should be launched by EventBridge Scheduler, not by web endpoints.
- Directly running `python run_all_syncs.py --group ...` is not blocked by `LOCAL_SYNC_ENABLED=false`; that flag is used by web/API safety checks.

Do not set `LOCAL_SYNC_ENABLED=true` in the scheduler task unless a future scheduler-specific code path explicitly requires it. Keeping it false avoids accidentally re-enabling local execution endpoints if the same image/env is reused.

## CPU And Memory

Initial recommendation:

```text
CPU: 512 (.5 vCPU)
Memory: 1024 MiB
```

Rationale:

- The requested AWS groups are smaller than the old `all`/`daily` runs.
- Most work is network I/O bound against Supabase or external APIs.
- Python integrations use `requests`, `supabase`, `gspread`, `easypost`, `openpyxl`, and `pandas`; 1 GiB gives enough headroom for modest batch sizes.

Escalate to:

```text
CPU: 1024 (1 vCPU)
Memory: 2048 MiB
```

if Amazon sales finance runs, RevSeller sheet reads, or future broader groups show memory pressure or long CPU-bound phases.

Do not run broad audit groups on the same tight profile until observed in ECS.

## CloudWatch Logs

Recommended log group:

```text
/ecs/mbop-scheduler
```

Recommended stream prefix:

```text
scheduled
```

Optional per-group convention:

```text
/ecs/mbop-scheduler/<group-name>
```

If using one log group, rely on EventBridge schedule name and ECS task metadata to identify the group.

Retention:

```text
30 days initially
```

Increase to 90 days after scheduler stabilization if operational history is useful.

## Required Environment Variables And Secrets By Group

All groups need:

```text
CLOUD_DEPLOYMENT=true
LOCAL_SYNC_ENABLED=false
SUPABASE_URL=https://froeucjkcepuhgwisped.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<secret>
```

### purchase-ingestion

Jobs:

- eBay buyer purchases
- Sourcing purchase matching

Required secrets:

- `SUPABASE_SERVICE_ROLE_KEY`
- `EBAY_CLIENT_ID`
- `EBAY_CLIENT_SECRET`
- `EBAY_REFRESH_TOKEN`

No EasyPost/Amazon/YNAB/Keepa secrets required for this group.

### purchase-tracking

Jobs:

- EasyPost shipments

Required secrets:

- `SUPABASE_SERVICE_ROLE_KEY`
- `EASYPOST_API_KEY`

### returns-order-problems

Jobs:

- eBay order problem returns/inquiries
- EasyPost order problem returns

Required secrets:

- `SUPABASE_SERVICE_ROLE_KEY`
- `EBAY_CLIENT_ID`
- `EBAY_CLIENT_SECRET`
- `EBAY_REFRESH_TOKEN`
- `EASYPOST_API_KEY`

### purchase-enrichment

Jobs:

- RevSeller enrichment
- Keepa missing purchase titles

Required secrets:

- `SUPABASE_SERVICE_ROLE_KEY`
- `GOOGLE_APPLICATION_CREDENTIALS` or equivalent mounted credentials file
- `REVSELLER_GOOGLE_SHEET_ID`
- `KEEPA_API_KEY`

Optional:

- `REVSELLER_WORKSHEET_NAME`
- `OPENAI_API_KEY`
- `OPENAI_MATCHING_MODEL`
- `KEEPA_API_ENDPOINT`
- `KEEPA_DOMAIN_ID`

Important: `GOOGLE_APPLICATION_CREDENTIALS` normally points to a file path. For ECS, either mount the service-account JSON as a file or update the code later to read JSON from a secret value. If using the current code unchanged, plan for a file path inside the container.

### amazon-sales-recent

Jobs:

- Amazon sales orders
- Recent Amazon sales finances
- Veeqo MF label costs
- Recent sales profitability

Required secrets:

- `SUPABASE_SERVICE_ROLE_KEY`
- `AMAZON_SP_API_CLIENT_ID`
- `AMAZON_SP_API_CLIENT_SECRET`
- `AMAZON_SP_API_REFRESH_TOKEN`
- `AMAZON_SP_API_MARKETPLACE_ID`
- `AMAZON_SP_API_AWS_ACCESS_KEY_ID` or `AWS_ACCESS_KEY_ID`
- `AMAZON_SP_API_AWS_SECRET_ACCESS_KEY` or `AWS_SECRET_ACCESS_KEY`

Required for Veeqo label sync if label costs should run:

- `VEEQO_KEY` or `VEEQO_API_KEY` or `VEEQO_ACCESS_TOKEN`

Optional:

- `AMAZON_SP_API_REGION`
- `AMAZON_SP_API_ENDPOINT`
- `AMAZON_SP_API_AWS_REGION`
- `AMAZON_SP_API_APP_ID`
- `AMAZON_SP_API_SELLER_ID`
- `AMAZON_SELLER_ID`
- `AMAZON_MERCHANT_ID`
- `AMAZON_SP_API_USE_SIGV4`
- `AMAZON_SP_API_AWS_SESSION_TOKEN` or `AWS_SESSION_TOKEN`

### finance-refresh

Jobs:

- YNAB Business transactions
- YNAB cash balance
- Amazon finance balances
- Business value snapshot

Required secrets:

- `SUPABASE_SERVICE_ROLE_KEY`
- `YNAB_PERSONAL_TOKEN` or `YNAB_ACCESS_TOKEN`
- `AMAZON_SP_API_CLIENT_ID`
- `AMAZON_SP_API_CLIENT_SECRET`
- `AMAZON_SP_API_REFRESH_TOKEN`
- `AMAZON_SP_API_MARKETPLACE_ID`
- `AMAZON_SP_API_AWS_ACCESS_KEY_ID` or `AWS_ACCESS_KEY_ID`
- `AMAZON_SP_API_AWS_SECRET_ACCESS_KEY` or `AWS_SECRET_ACCESS_KEY`

Optional:

- `YNAB_PLAN_NAME`
- `YNAB_BUSINESS_CATEGORY_NAME`
- `AMAZON_UNMATCHED_COMPLETED_TRANSFER_LOOKBACK_DAYS`
- Amazon SP-API optional variables listed above

## Secrets Manager Inventory To Create

Existing:

- `SUPABASE_SERVICE_ROLE_KEY`

Create these Secrets Manager entries before enabling schedules.

### eBay

```text
/mbop/prod/ebay/client-id
/mbop/prod/ebay/client-secret
/mbop/prod/ebay/refresh-token
```

Maps to:

```text
EBAY_CLIENT_ID
EBAY_CLIENT_SECRET
EBAY_REFRESH_TOKEN
```

### EasyPost

```text
/mbop/prod/easypost/api-key
```

Maps to:

```text
EASYPOST_API_KEY
```

### Amazon SP-API

```text
/mbop/prod/amazon-spapi/client-id
/mbop/prod/amazon-spapi/client-secret
/mbop/prod/amazon-spapi/refresh-token
/mbop/prod/amazon-spapi/marketplace-id
/mbop/prod/amazon-spapi/aws-access-key-id
/mbop/prod/amazon-spapi/aws-secret-access-key
```

Maps to:

```text
AMAZON_SP_API_CLIENT_ID
AMAZON_SP_API_CLIENT_SECRET
AMAZON_SP_API_REFRESH_TOKEN
AMAZON_SP_API_MARKETPLACE_ID
AMAZON_SP_API_AWS_ACCESS_KEY_ID
AMAZON_SP_API_AWS_SECRET_ACCESS_KEY
```

Optional:

```text
/mbop/prod/amazon-spapi/seller-id
/mbop/prod/amazon-spapi/aws-session-token
```

Maps to:

```text
AMAZON_SP_API_SELLER_ID
AMAZON_SP_API_AWS_SESSION_TOKEN
```

### YNAB

```text
/mbop/prod/ynab/access-token
```

Maps to either:

```text
YNAB_PERSONAL_TOKEN
```

or:

```text
YNAB_ACCESS_TOKEN
```

Recommended: map it to `YNAB_PERSONAL_TOKEN`, because both YNAB scripts check that first.

Optional non-secret env:

```text
YNAB_PLAN_NAME
YNAB_BUSINESS_CATEGORY_NAME
```

### Keepa

```text
/mbop/prod/keepa/api-key
```

Maps to:

```text
KEEPA_API_KEY
```

Optional non-secret env:

```text
KEEPA_DOMAIN_ID=1
KEEPA_API_ENDPOINT=https://api.keepa.com
```

### RevSeller / Google Sheets

```text
/mbop/prod/revseller/google-sheet-id
/mbop/prod/google/service-account-json
```

Maps to:

```text
REVSELLER_GOOGLE_SHEET_ID
GOOGLE_APPLICATION_CREDENTIALS
```

Current code expects `GOOGLE_APPLICATION_CREDENTIALS` to be a file path, not raw JSON. If no code change is made, the task needs the Google service-account JSON available as a file inside the container, and `GOOGLE_APPLICATION_CREDENTIALS` must point to that file.

Possible implementation options:

- Bake no credential into the image; inject at runtime via a mounted secret file or startup wrapper.
- Later code change: support `GOOGLE_APPLICATION_CREDENTIALS_JSON` and write it to a temporary file before calling `gspread.service_account`.

Optional:

```text
REVSELLER_WORKSHEET_NAME
```

### OpenAI

```text
/mbop/prod/openai/api-key
```

Maps to:

```text
OPENAI_API_KEY
```

Optional non-secret env:

```text
OPENAI_MATCHING_MODEL
```

If omitted, RevSeller enrichment still runs but prints that AI match review was skipped.

### Veeqo

Needed for `amazon-sales-recent`.

```text
/mbop/prod/veeqo/api-key
```

Maps to one of:

```text
VEEQO_KEY
VEEQO_API_KEY
VEEQO_ACCESS_TOKEN
```

Recommended: map to `VEEQO_KEY`, because the current script checks that first.

## Task Execution Role And Task Role

Task execution role needs:

- Pull image from ECR.
- Write logs to CloudWatch Logs.
- Read Secrets Manager secrets used by the task definition.
- If secrets use a customer-managed KMS key, decrypt with that KMS key.

Add or verify permissions similar to:

```json
{
  "Effect": "Allow",
  "Action": [
    "secretsmanager:GetSecretValue"
  ],
  "Resource": [
    "arn:aws:secretsmanager:<region>:<account-id>:secret:/mbop/prod/*"
  ]
}
```

If using KMS:

```json
{
  "Effect": "Allow",
  "Action": [
    "kms:Decrypt"
  ],
  "Resource": [
    "<kms-key-arn>"
  ]
}
```

Task role can be minimal for now because integrations call external APIs over HTTPS and Supabase using secrets. If the task later writes logs/artifacts to S3 or invokes other AWS services, add those permissions to the task role, not the execution role.

## EventBridge Scheduler Group Passing

Use one EventBridge schedule per scheduler group.

Recommended schedule names:

```text
mbop-purchase-ingestion
mbop-purchase-tracking
mbop-returns-order-problems
mbop-purchase-enrichment
mbop-amazon-sales-recent
mbop-finance-refresh
```

Each schedule targets ECS `RunTask` on cluster `mbop-cluster1`, task definition `mbop-scheduler-task`.

Use container command override:

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

Change only the final group name per schedule:

```text
purchase-ingestion
purchase-tracking
returns-order-problems
purchase-enrichment
amazon-sales-recent
finance-refresh
```

Do not use `all`, `core`, or `daily` for AWS schedules once these smaller schedules are enabled.

## Suggested Initial Schedules

Start conservative and adjust from CloudWatch/Supabase observations.

```text
purchase-ingestion: every 1 hour during working hours, otherwise every 2-4 hours
purchase-tracking: every 1 hour
returns-order-problems: every 2-4 hours
purchase-enrichment: every 2 hours
amazon-sales-recent: every 1-2 hours
finance-refresh: daily after sales/inventory freshness windows
```

Avoid starting schedules at the same minute. Stagger starts by 5-15 minutes to reduce Supabase and external API bursts.

## Required AWS Console Actions

1. Confirm current web image contents.
   - ECS -> Task definitions -> historical `mbop-web-task:2`.
   - Confirm image URI.
   - Confirm it was built from `web/Dockerfile`.
   - Treat it as web-only unless a new image has been built with Python scheduler files.

2. Build and push a scheduler-capable image.
   - Add or prepare a Docker build that includes Python, `run_all_syncs.py`, `integrations/`, and `requirements.txt`.
   - Push the image to the same ECR repository/tag family or a scheduler-specific repository.
   - Do not proceed with schedules until `python run_all_syncs.py --group purchase-ingestion --list` works inside the image.

3. Create missing Secrets Manager secrets.
   - Create the eBay, EasyPost, Amazon SP-API, YNAB, Keepa, Veeqo, RevSeller/Google, and optional OpenAI secrets listed above.
   - Keep `SUPABASE_SERVICE_ROLE_KEY` as the existing secret.

4. Update IAM for the task execution role.
   - Add `secretsmanager:GetSecretValue` for `/mbop/prod/*` or the exact secret ARNs.
   - Add `kms:Decrypt` if applicable.
   - Verify CloudWatch Logs permissions.

5. Create ECS task definition `mbop-scheduler-task`.
   - Launch type: Fargate.
   - Container name: `mbop-scheduler`.
   - Image: scheduler-capable MBOP image.
   - CPU/memory: `512 CPU / 1024 MiB`.
   - Environment:
     - `CLOUD_DEPLOYMENT=true`
     - `LOCAL_SYNC_ENABLED=false`
     - `SUPABASE_URL=https://froeucjkcepuhgwisped.supabase.co`
     - optional non-secret defaults such as `KEEPA_DOMAIN_ID=1`.
   - Secrets:
     - map all needed secret ARNs to the env var names listed above.
   - Logging:
     - awslogs group `/ecs/mbop-scheduler`.
     - stream prefix `scheduled`.

6. Smoke-test the scheduler task manually.
   - ECS -> Run task.
   - Cluster: `mbop-cluster1`.
   - Task definition: `mbop-scheduler-task`.
   - Override command:
     - `python run_all_syncs.py --group purchase-ingestion --list`
   - Confirm logs show only selected jobs and exit successfully.
   - Repeat for the other AWS groups with `--list`.

7. Create EventBridge Scheduler schedules.
   - One schedule per group.
   - Target: ECS RunTask.
   - Cluster: `mbop-cluster1`.
   - Task definition: `mbop-scheduler-task`.
   - Launch type: Fargate.
   - Network: same VPC/subnets/security-group pattern as `mbop-web-service`, with outbound internet/NAT access for external APIs.
   - Assign public IP only if that is how the web task reaches the internet; otherwise use private subnets with NAT.
   - Container override command per group.
   - Use staggered start times.

8. Observe first real scheduled runs.
   - Watch `/ecs/mbop-scheduler`.
   - Check Supabase freshness and row changes.
   - Confirm no lock collisions.
   - Confirm external API errors/throttling are acceptable.

9. Update System Health later.
   - Current health reads local `logs/sync_health.json` and Supabase freshness.
   - ECS task-local log files disappear with the task.
   - Future improvement: write scheduler run telemetry to Supabase or CloudWatch-derived health rather than relying on local `logs/`.

## Open Implementation Gap

Historical conclusion: before the AWS schedules could run, MBOP needed a
scheduler-capable container image. That has since been implemented as the
separate `Dockerfile.scheduler` / `mbop-scheduler-task` path documented in
`docs/aws/MBOP_AWS_SCHEDULER_PLAN.md`.
