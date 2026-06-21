# MBOP AWS Scheduler Plan and Outstanding AWS Items

## 1. Current AWS Deployment State

MBOP is currently deployed to AWS with:

* ECS cluster: `mbop-cluster1`
* Web service: `mbop-web-service`
* Web task definition: `mbop-web-task:2`
* Web container: `mbop-web`
* Region: `us-west-2`
* Runtime: ECS/Fargate
* Web task size: `0.5 vCPU / 1 GiB`
* Public HTTPS custom domain: `https://mbop.midnightblueenterprises.com`
* Homepage/static site through S3 + CloudFront
* CloudFront distribution: `dfmaesup5ihuk.cloudfront.net`
* `www.midnightblueenterprises.com` points to CloudFront
* Google OAuth → Cognito → ALB Authentication → MBOP is working
* OAuth secret rotation completed
* No NAT Gateway
* One ALB
* One running ECS web task

Current web image limitation:

* The deployed web image is built from `web/Dockerfile`.
* It contains only the Next.js web app.
* It does not include Python, `run_all_syncs.py`, `integrations/`, or `requirements.txt`.
* Therefore, the current web image cannot run scheduled sync jobs.

## 2. Scheduler Architecture Decision

Use a separate ECS/Fargate scheduled-task path.

Preferred next implementation:

* Create scheduler-capable image.
* Create task definition: `mbop-scheduler-task`
* Create container name: `mbop-scheduler`
* Use EventBridge Scheduler to run ECS tasks.
* Use command overrides per schedule:

```text
python run_all_syncs.py --group <GROUP_NAME>
```

Keep:

```text
CLOUD_DEPLOYMENT=true
LOCAL_SYNC_ENABLED=false
```

Reason:

* `CLOUD_DEPLOYMENT=true` marks cloud runtime.
* `LOCAL_SYNC_ENABLED=false` prevents web/API routes from spawning local scheduler jobs.
* EventBridge/ECS should own scheduled execution.

Initial scheduler task sizing:

```text
CPU: 512
Memory: 1024 MiB
```

Escalate later to:

```text
CPU: 1024
Memory: 2048 MiB
```

only if Amazon sales finance, RevSeller, or broad jobs show memory or runtime pressure.

Recommended logs:

```text
/ecs/mbop-scheduler
stream prefix: scheduled
retention: 30 days initially
```

## 3. Scheduler Groups

New AWS-ready groups already validated with `--list` only:

### purchase-ingestion

Jobs:

1. eBay buyer purchases
2. Sourcing purchase matching

Purpose:

* Root purchase source.
* Imports new/updated eBay purchases.
* Matches accepted sourcing opportunities to imported purchases.

Initial cadence:

```text
Hourly from 7:00 AM–10:00 PM Pacific
Optional overnight catch-up once around 4:00 AM
```

### purchase-tracking

Jobs:

1. EasyPost shipments

Purpose:

* Updates inbound shipment tracking from EasyPost.
* Later should be reduced when EasyPost webhooks are implemented.

Initial cadence:

```text
Hourly from 7:00 AM–10:00 PM Pacific
Optional overnight catch-up once around 4:15 AM
```

### returns-order-problems

Jobs:

1. eBay order problem returns/inquiries
2. EasyPost order problem returns

Purpose:

* Updates eBay return/inquiry/problem cases.
* Updates EasyPost return tracking tied to order-problem cases.

Initial cadence:

```text
Every 2–4 hours from 7:00 AM–10:00 PM Pacific
```

Recommended first cadence:

```text
7:15 AM, 11:15 AM, 3:15 PM, 7:15 PM, 10:00 PM
```

### purchase-enrichment

Jobs:

1. RevSeller enrichment
2. Keepa missing purchase titles

Purpose:

* Enriches purchase rows with ASIN/title/pricing data.
* Uses Google Sheets/RevSeller, optional OpenAI review, and Keepa.

Initial cadence:

```text
Every 2 hours from 8:00 AM–10:00 PM Pacific
```

Must not overlap with other Keepa jobs.

### amazon-sales-recent

Jobs:

1. Amazon sales orders
2. Recent Amazon sales finances
3. Veeqo MF label costs
4. Recent sales profitability

Purpose:

* Keeps Amazon sales, fees, MF label costs, and profitability current.
* Must remain a sequential chain.

Initial cadence:

```text
Every 2 hours from 7:00 AM–10:00 PM Pacific
Optional overnight catch-up once around 4:30 AM
```

Reason:

* Amazon sales are low overnight.
* Recent sales finance is one of the heavier normal jobs, so hourly may be unnecessary at first.

### finance-refresh

Jobs:

1. YNAB Business transactions
2. YNAB cash balance
3. Amazon finance balances
4. Business value snapshot

Purpose:

* Keeps financial dashboard and business value reasonably fresh.

Initial cadence:

```text
6:30 AM Pacific
2:00 PM Pacific
9:00 PM Pacific
```

Observed overhead is low, roughly around 30 seconds total plus ECS startup overhead.

### business-value-finalizer

Jobs:

1. Business value snapshot

Purpose:

* Optional lightweight finalizer after inventory/reconciliation/finance inputs.

Initial cadence:

```text
Run only if needed after larger inventory/reconciliation jobs.
```

For now, this may be redundant because `finance-refresh` already includes Business value snapshot.

### fba-inventory-daily

Jobs to include:

1. Amazon FBA inventory
2. Amazon inventory planning

Purpose:

* Refreshes Amazon FBA inventory and planning snapshots.
* Feeds reconciliation, listing status, repricing, and business value views.

Initial cadence:

```text
Daily, evening/off-hours
```

Recommended first time:

```text
8:30 PM Pacific
```

### fba-shipments

Jobs:

1. Amazon FBA shipments
2. FBA EasyPost carrier tracking

Purpose:

* Tracks Amazon FBA shipment workflow and carrier movement.

Initial cadence:

```text
Every 2–4 hours while shipment prep/transit is active
Daily otherwise
```

This could become manually triggered or dashboard-triggered later.

### reconciliation

Jobs:

1. Inventory reconciliation with `--skip-if-unchanged`

Purpose:

* Updates inventory positions and reconciliation findings.

Initial cadence:

```text
After FBA inventory refresh
Possibly also once after purchase-tracking window
```

Recommended first time:

```text
9:00 PM Pacific
```

Avoid overlapping broad Supabase read/write jobs.

### repricing-catalog

Jobs:

1. Amazon listing status
2. Informed repricing reports

Purpose:

* Keeps repricing and listing health current.

Initial cadence:

```text
Daily
```

Recommended first time:

```text
9:30 PM Pacific
```

### sourcing-catalog

Jobs:

1. Sourcing listing availability
2. Matching intelligence refresh

Purpose:

* Keeps sourcing candidates and matching intelligence fresh.
* Should not remain in hot purchase path unless needed for immediate buying workflow.

Initial cadence:

```text
Daily or every 6 hours during buying windows
```

Recommended first version:

```text
Daily at 10:00 PM Pacific
```

### keepa-rolling-refresh

Jobs:

1. Keepa active products

Purpose:

* Refresh Keepa data for active Amazon listings for ongoing buy opportunity detection.

Important finding:

* Current deep config with `offers=20` and `stock` costs about 9.8 tokens per ASIN.
* Full refresh of ~1,028 ASINs costs about 10,074 tokens.
* Keepa refills at 5 tokens/minute with 300 max tokens.
* This is feasible as rolling refresh, but it must be token-paced and must not overlap any other Keepa job.

Recommended first version:

```text
Run current deep config with:
--batch-size 10
--limit 10
--min-tokens 150
```

Cadence options:

```text
Every 6 hours = targets roughly 3-day refresh
Every 8 hours = targets roughly 5-day refresh
Every 12 hours = targets roughly 7-day refresh
```

Recommended starting point:

```text
Every 8 hours
```

Future improvement:

* Add light stats-only mode without `offers` and `stock`.
* Use deep offer/stock mode only for candidate ASINs needing offer depth.

### fba-pricing

Jobs:

1. Keepa FBA prep pricing
2. Amazon Product Fees estimates

Purpose:

* Supports pricing for received Amazon-bound items before FBA shipment creation.

Important finding:

* Current FBA prep Keepa command is too aggressive for unattended cloud scheduling.
* Observed 20-ASIN batch consumed 228 tokens and then hit 429 on second batch.

Recommendation:

```text
Manual/on-demand first
or hourly during FBA prep only with --limit 5 or --limit 10 and --min-tokens 150
```

### audits

Jobs:

* Amazon sales finances audit
* Sales profitability audit
* Amazon listing status audit
* Inventory reconciliation audit

Recommendation:

```text
Manual-only initially
Possibly weekly off-hours later
```

Reason:

* Finance audit was the biggest outlier.
* Listing audit performs one Listings API call per active SKU.
* These jobs are not needed for regular freshness.

## 4. Initial EventBridge Schedule Proposal

Use staggered schedules. Do not start multiple jobs at the same minute.

Suggested first production schedule set:

```text
purchase-ingestion:
  hourly 7 AM–10 PM PT
  one catch-up at 4:00 AM PT

purchase-tracking:
  hourly 7 AM–10 PM PT
  one catch-up at 4:15 AM PT

returns-order-problems:
  7:15 AM, 11:15 AM, 3:15 PM, 7:15 PM, 10:00 PM PT

purchase-enrichment:
  every 2 hours from 8 AM–10 PM PT

amazon-sales-recent:
  every 2 hours from 7 AM–10 PM PT
  one catch-up at 4:30 AM PT

finance-refresh:
  6:30 AM, 2:00 PM, 9:00 PM PT

fba-inventory-daily:
  8:30 PM PT

reconciliation:
  9:00 PM PT

repricing-catalog:
  9:30 PM PT

sourcing-catalog:
  10:00 PM PT

keepa-rolling-refresh:
  every 8 hours, staggered away from purchase-enrichment and fba-pricing

audits:
  manual only
```

## 5. Secrets Required

Existing:

```text
SUPABASE_SERVICE_ROLE_KEY
```

Need to create in AWS Secrets Manager:

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
AMAZON_SP_API_SELLER_ID
AMAZON_SP_API_AWS_SESSION_TOKEN
```

### YNAB

```text
/mbop/prod/ynab/access-token
```

Recommended mapping:

```text
YNAB_PERSONAL_TOKEN
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

Implementation note:

* Current code expects `GOOGLE_APPLICATION_CREDENTIALS` to be a file path.
* Either mount/write service-account JSON to a file in the container, or update code to support `GOOGLE_APPLICATION_CREDENTIALS_JSON`.

Optional:

```text
REVSELLER_WORKSHEET_NAME
OPENAI_API_KEY
OPENAI_MATCHING_MODEL
```

### Veeqo

```text
/mbop/prod/veeqo/api-key
```

Recommended mapping:

```text
VEEQO_KEY
```

## 6. System Health and Telemetry Plan

Current issue:

* System Health is blank in cloud because the old scheduler health writes local files:

  * `logs/sync_health.json`
  * `logs/sync_runs.jsonl`
  * `logs/run_all_syncs.lock`
* ECS scheduled tasks are ephemeral, so local files disappear when tasks stop.

Required improvement:

Create a Supabase-backed scheduler telemetry subsystem.

Suggested tables:

```text
scheduler_runs
scheduler_run_jobs
scheduler_job_definitions
scheduler_domain_freshness
scheduler_locks
```

Each job should record:

```text
run_id
group_name
job_name
status
started_at
finished_at
runtime_seconds
rows_read
rows_inserted
rows_updated
rows_deleted
rows_skipped
external_api_calls
retry_count
rate_limit_count
log_bytes
error_summary
ecs_task_arn
eventbridge_schedule_name
container_cpu
container_memory
```

System Health should show:

* Jobs currently running
* Last successful run per group
* Last successful run per domain
* Failed jobs
* Stale domains
* Average runtime
* Retry/rate-limit warnings
* Keepa token status
* EasyPost errors
* Amazon SP-API quota/retry signals

## 7. AWS / MBOP Outstanding Items

### Completed

* ECS/Fargate web deployment.
* HTTPS working.
* Custom app domain working: `https://mbop.midnightblueenterprises.com`
* Google OAuth → Cognito → ALB authentication working.
* S3/CloudFront homepage working.
* `www.midnightblueenterprises.com` points to CloudFront.
* ACM certificate issued and attached to CloudFront.
* Google OAuth secret rotated.
* Old Google OAuth secret deleted.

### Outstanding: AWS Deployment Documentation

* Create authoritative AWS deployment documentation in repo.
* Document final live state, not chronological troubleshooting.
* Later chats override earlier chats.
* Live AWS configuration should be highest authority.
* Repository docs should be updated to match current AWS reality.

Recommended files:

```text
docs/aws/MBOP_AWS_DEPLOYMENT.md
docs/aws/MBOP_AWS_SCHEDULER_PLAN.md
docs/aws/MBOP_AWS_OPERATIONS_RUNBOOK.md
```

### Outstanding: Scheduler Container

* Build scheduler-capable image.
* Decide between:

  * separate Python scheduler image, or
  * unified web + scheduler image.
* Current web image is not sufficient.
* Validate inside container:

```text
python run_all_syncs.py --group purchase-ingestion --list
```

### Outstanding: Secrets

* Create missing AWS Secrets Manager secrets for:

  * eBay
  * EasyPost
  * Amazon SP-API
  * YNAB
  * Keepa
  * Veeqo
  * RevSeller / Google Sheets
  * optional OpenAI

### Outstanding: IAM

* Update ECS task execution role to read all scheduler secrets.
* Add KMS decrypt permissions if needed.
* Keep task role minimal unless future S3/AWS API writes are added.

### Outstanding: ECS Scheduler Task Definition

Create:

```text
mbop-scheduler-task
```

With:

```text
Container: mbop-scheduler
CPU: 512
Memory: 1024
Log group: /ecs/mbop-scheduler
```

### Outstanding: Manual Scheduler Smoke Tests

Run ECS task manually with `--list` first:

```text
python run_all_syncs.py --group purchase-ingestion --list
python run_all_syncs.py --group purchase-tracking --list
python run_all_syncs.py --group returns-order-problems --list
python run_all_syncs.py --group purchase-enrichment --list
python run_all_syncs.py --group amazon-sales-recent --list
python run_all_syncs.py --group finance-refresh --list
```

Then run first real test:

```text
python run_all_syncs.py --group purchase-ingestion
```

### Outstanding: EventBridge Scheduler

* Create one schedule per group.
* Target ECS RunTask.
* Use command override per group.
* Use same VPC/subnet/security group approach as web service unless improved.
* Assign public IP if needed to avoid NAT Gateway.
* Stagger schedules.
* Avoid `all`, `core`, and `daily` for production AWS schedules.

### Outstanding: Supabase Telemetry

* Replace local scheduler health files with Supabase-backed telemetry.
* Update System Health dashboard to read scheduler telemetry.
* Show running jobs in near real time.
* Preserve cost/optimization metrics for AWS scheduling.

### Outstanding: EasyPost Webhooks

* Implement EasyPost webhook endpoint in AWS-hosted MBOP.
* Validate signature/security approach.
* Use webhooks to reduce polling frequency.
* Keep polling as fallback.

### Outstanding: MBOP Logout Button

* Add logout button to MBOP.
* It should clear app/Cognito/ALB session as much as practical.
* Redirect to Cognito logout endpoint and then back to MBOP login/home.

### Outstanding: Keepa Improvements

* Add explicit token accounting:

  * run-level tokens before/after
  * batch-level token cost
  * normalized per-ASIN token cost
* Add per-batch token checks.
* Add light stats-only refresh mode.
* Keep deep offers/stock mode for selected candidates only.
* Prevent overlapping Keepa jobs.

### Outstanding: Cost Monitoring

* Use AWS Cost Explorer after account has enough data.
* Monitor:

  * ALB cost
  * Fargate web task cost
  * Fargate scheduled task cost
  * CloudWatch logs
  * Public IPv4
* Expected current AWS cost: roughly $35–$50/month.
* Expected total MBOP hosting with Supabase: roughly $60–$75/month.
* Expected scheduler cost increase: small, likely a few dollars/month.

### Outstanding: Documentation Updates

Update:

```text
CURRENT_STATE.md
DECISIONS.md
ROADMAP.md
KNOWN_ISSUES.md
AGENTS.md
docs/cloud_deployment_phase1.md
docs/aws/MBOP_AWS_DEPLOYMENT.md
docs/aws/MBOP_AWS_SCHEDULER_PLAN.md
```

Key documentation rule:

* Final working configuration should be documented.
* Obsolete troubleshooting paths should not be preserved as current state.
* If historical notes are useful, put them in a clearly marked “History / Superseded” section.
