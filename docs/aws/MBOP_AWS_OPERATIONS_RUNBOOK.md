# MBOP AWS Operations Runbook

Last updated: 2026-06-28

## AWS CLI Preflight

Before inspecting or changing live AWS resources, verify the local AWS CLI
session is still valid:

```powershell
aws sts get-caller-identity --profile mbop-admin
```

If this returns `NoCredentials`, an SSO/login prompt, or an expired-token error,
run the repo login helper before proceeding:

```powershell
.\scripts\aws-login.ps1
```

Use `.\scripts\aws-login.ps1 -RootFallback` only for account recovery,
billing, or other break-glass root-account work.

## Deploy Web Updates

For the day-to-day solo developer workflow, prefer the wrapper scripts in
`scripts/` and the short guide in `docs/aws/MBOP_SOLO_DEV_WORKFLOW.md`.

For web changes, a local build is only a compile/type check. It does not prove
production behavior because MBOP runs behind ALB/Cognito on ECS/Fargate. When a
change must be verified in production, deploy with `.\scripts\deploy-web.ps1`,
confirm service stability with `.\scripts\aws-web-status.ps1`, then verify in
the browser at `https://mbop.midnightblueenterprises.com`.

1. Build the web image from `web/`.
2. Push it to the ECR repository used by `mbop-web-task`.
3. Resolve the pushed image digest and register a new `mbop-web-task` revision pinned to that digest.
4. Keep `CLOUD_DEPLOYMENT=true` and `LOCAL_SYNC_ENABLED=false`.
5. Preserve required secrets such as `SUPABASE_SERVICE_ROLE_KEY`,
   `MBOP_ADMIN_API_TOKEN`, and, while the webhook is enabled,
   `EASYPOST_WEBHOOK_TOKEN` / `EASYPOST_WEBHOOK_SECRET`.
6. Keep the web task execution role set to
   `arn:aws:iam::297464765814:role/mbop-web-task-execution-role`.
7. Update `mbop-web-service` to the new task revision.
8. Wait for the ECS service to stabilize, then verify target health and `https://mbop.midnightblueenterprises.com`.

```powershell
aws ecs update-service --region us-west-2 --cluster mbop-cluster1 --service mbop-web-service --task-definition mbop-web-task:<revision>
```

The live service intentionally uses only two public subnets:

```text
us-west-2a: subnet-0acbbc29cdf301200
us-west-2b: subnet-07558cd00060ff69d
```

Keep the ALB and ECS service on the same two public subnets unless a future
availability decision accepts the extra public IPv4 cost of more AZs.

## Deploy Scheduler Image

Build from the repo root:

```powershell
docker build -f Dockerfile.scheduler -t mbop-scheduler:<tag> .
```

Push to ECR, then register `mbop-scheduler-task` with:

```text
Container: mbop-scheduler
CPU: 512
Memory: 1024
Log group: /ecs/mbop-scheduler
```

Before changing schedule cadence, run `--list` smoke tests in ECS.

Current scheduler ECR repository:

```text
297464765814.dkr.ecr.us-west-2.amazonaws.com/mbop-scheduler
```

Push example:

```powershell
aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin 297464765814.dkr.ecr.us-west-2.amazonaws.com
docker tag mbop-scheduler:<tag> 297464765814.dkr.ecr.us-west-2.amazonaws.com/mbop-scheduler:<tag>
docker push 297464765814.dkr.ecr.us-west-2.amazonaws.com/mbop-scheduler:<tag>
```

Current scheduler task definition `mbop-scheduler-task:1` uses
`mbop-scheduler:latest`. Pushing `:latest` is therefore a production-affecting
change for scheduled jobs. Prefer registering a new task definition revision
pinned to a digest when changing scheduler code; at minimum, run ECS `--list`
smoke tests and verify `/ecs/mbop-scheduler` logs before relying on the new
image.

## One-Off ECS Scheduler Task

Use the same VPC/subnet/security group pattern as `mbop-web-service`. Because there is no NAT Gateway, verify whether the task needs a public IP for outbound calls.

Command override example:

```json
["python", "run_all_syncs.py", "--group", "purchase-ingestion", "--list"]
```

After `--list` succeeds for every group, a safe real smoke test is:

```json
["python", "run_all_syncs.py", "--group", "purchase-ingestion"]
```

## On-Demand Sourcing From Web

The Sourcing page `Run Sourcing` button starts an ECS Fargate task in cloud
mode instead of local Python. The web API creates the `sourcing_runs` row and
launches:

```text
python integrations/run_sourcing_workflow.py --run-id <id> --run-type recent_sales|full_listings
```

Default target:

- Cluster: `mbop-cluster1`
- Task definition: `mbop-scheduler-task`
- Container: `mbop-scheduler`
- Subnets: `subnet-0acbbc29cdf301200`, `subnet-07558cd00060ff69d`
- Security group: `sg-0b05e7760083c5e31`
- CPU/memory override: `1024 / 4096`

Required web task role permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "ecs:RunTask",
      "Resource": "arn:aws:ecs:us-west-2:297464765814:task-definition/mbop-scheduler-task:*"
    },
    {
      "Effect": "Allow",
      "Action": "ecs:TagResource",
      "Resource": "arn:aws:ecs:us-west-2:297464765814:task/mbop-cluster1/*"
    },
    {
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": "arn:aws:iam::297464765814:role/ecsTaskExecutionRole"
    }
  ]
}
```

## Check Logs

Web logs: verify the current log group from `mbop-web-task:<revision>`.

Scheduler logs:

```powershell
aws logs tail /ecs/mbop-scheduler --region us-west-2 --since 2h --follow
```

Check recent failed ECS tasks:

```powershell
aws ecs list-tasks --region us-west-2 --cluster mbop-cluster1 --desired-status STOPPED
aws ecs describe-tasks --region us-west-2 --cluster mbop-cluster1 --tasks <task-arn>
```

## EasyPost Webhook

Production webhook:

```text
https://mbop.midnightblueenterprises.com/api/easypost/webhook
```

Operational notes:

- The ALB listener has a priority-10 unauthenticated path rule for
  `/api/easypost/webhook`.
- The route is POST-only; unauthenticated GET should return `405`.
- The EasyPost outbound header token and HMAC secret are stored in
  `/mbop/prod/easypost/webhook-token`.
- Bare static-token webhook auth is not accepted. EasyPost deliveries must use
  HMAC headers, or an internal relay must send the token plus timestamp and
  HMAC signature headers.
- If the secret name or ARN changes, register a new `mbop-web-task` revision and
  redeploy the web service.
- Keep scheduled EasyPost polling until real EasyPost-originated
  `tracker.updated` webhook deliveries have been observed updating Supabase
  shipment rows. Public route and smoke tests are complete; real carrier event
  delivery is the remaining proof point.

## Mutation Security

State-changing MBOP API routes require one of:

- Internal automation header `x-mbop-admin-token` or `Authorization: Bearer`
  matching `MBOP_ADMIN_API_TOKEN`.
- Same-origin browser request with `x-mbop-csrf: 1` and ALB Cognito identity
  headers.

Do not expose `MBOP_ADMIN_API_TOKEN` to browser code. The frontend sends only
the non-secret CSRF marker.

## Logout

The shared app shell links to `/api/logout`. Cognito app-client logout URLs must
include:

```text
https://mbop.midnightblueenterprises.com/
```

If logout redirects fail, verify the Cognito app client callback/logout URL
lists and the hosted UI domain recorded in `MBOP_AWS_DEPLOYMENT.md`.

## CloudFront WAF Removal

The static homepage CloudFront distribution currently has AWS WAF web ACL
`CreatedByCloudFront-55bad07c` attached. This WAF protects only the static
homepage distribution `E2KKKB5MJ8CV3N`; MBOP app/API/webhook traffic routes to
the ALB at `mbop.midnightblueenterprises.com`, not through CloudFront.

The S3 homepage bucket is already public-read through S3 static website hosting,
with no OAC/OAI. Removing WAF does not materially increase risk to MBOP app data.
It only removes WAF filtering for public static homepage requests.

Direct API removal failed with:

```text
Distributions with a pricing plan subscription must have a web ACL resource.
```

The CloudFront console shows this distribution on the CloudFront security
protections Free plan (`$0/month`) with Core protections enabled. The word
"subscription" in the API error refers to the CloudFront security protections
plan state, not to the paid Business plan. Advanced DDoS protection is not
enabled. The console also says included WAF protections are available at no
additional charge, and Cost Explorer month-to-date does not show an AWS WAF
line item for these CloudFront included protections.

Keep these included protections enabled unless AWS later shows WAF charges or
the homepage intentionally no longer needs CloudFront security
metrics/filtering. If removal becomes necessary:

1. In the CloudFront console, open distribution `E2KKKB5MJ8CV3N`.
2. Open the Security / WAF protections area.
3. Use **Manage protections** to disable Core protections / AWS WAF protection
   for the distribution. The distribution can remain on the Free plan.
4. Disassociate web ACL `CreatedByCloudFront-55bad07c`.
5. Delete the web ACL after confirming it is no longer associated with any
   distribution.
6. Verify `www.midnightblueenterprises.com` serves the homepage and
   `mbop.midnightblueenterprises.com` still resolves to the ALB.

Expected savings are `$0/month` while the distribution remains on the
CloudFront Free plan with included Core protections. If a future bill shows a
separate AWS WAF line item, removing the web ACL would avoid roughly the
generic WAF baseline cost for one web ACL plus managed rule/request charges.

## Disable Schedules

Disable an EventBridge schedule before broad maintenance, Supabase IO incidents, or external API credential repair:

```powershell
aws scheduler update-schedule --region us-west-2 --name <schedule-name> --state DISABLED <existing-schedule-fields>
```

The AWS CLI requires the existing schedule fields when updating. In the console, open EventBridge Scheduler, select the schedule, and disable it.

## Rotate Google OAuth Secret

1. Create a new Google OAuth client secret in Google Cloud.
2. Update the Cognito Google IdP secret.
3. Test Cognito hosted UI login through the ALB-authenticated MBOP domain.
4. Delete the old Google secret after the new login path works.
5. Update docs only with rotation date/status, never with secret values.

## Rotate API Secrets

1. Create or update the value in AWS Secrets Manager.
2. Register a new ECS task definition revision if the secret ARN/name changed.
3. Restart affected ECS service or wait for the next scheduled task if only the value changed.
4. Run the smallest safe smoke test, preferably a `--list` or auth-only script.

## Investigate Failed Scheduler Jobs

1. Check System Health for the latest `scheduler_runs` and `scheduler_run_jobs` record.
2. Check `/ecs/mbop-scheduler` for the failed task stream.
3. Confirm whether the failure is missing secret, external API auth, rate limit, Supabase connectivity, or code error.
4. If Supabase returns connection failures or 522/ECONNREFUSED, pause schedules and run only a tiny read before resuming.
5. For Keepa failures, check token balance and avoid overlapping Keepa jobs.
6. For Amazon SP-API failures, identify endpoint family and quota/retry messages.
7. For EasyPost failures, check webhook delivery, route auth, carrier responses,
   and 429 backoff logs.

## Retired Local Windows Tasks

AWS EventBridge Scheduler supersedes local Windows Task Scheduler jobs. The
latest local check found no matching `Amazon eBay Ops*` or `MBOP*` scheduled
tasks. If old tasks reappear on the workstation, remove them from an
Administrator PowerShell:

```powershell
Unregister-ScheduledTask -TaskName 'Amazon eBay Ops Sync AM' -Confirm:$false
Unregister-ScheduledTask -TaskName 'Amazon eBay Ops Sync PM' -Confirm:$false
```

Do not recreate local scheduled tasks unless explicitly designing a local
disaster-recovery fallback.

## Cost Checks

Use AWS Cost Explorer after enough data is available. Monitor:

- ALB
- Fargate web task
- Fargate scheduled tasks
- CloudWatch Logs
- Public IPv4
- CloudFront/S3 homepage
- AWS WAF only if Cost Explorer shows a separate line item for CloudFront
  security protections

Expected current AWS cost after scheduler migration, two-subnet ALB/ECS
networking, and duplicate-secret cleanup: roughly `$65-$72/month` while
CloudFront included WAF protections remain free. Expected total MBOP hosting
with Supabase: roughly `$90-$97/month`. Recheck Cost Explorer after the next
full billing cycle and only revisit WAF removal if an AWS WAF line item appears.
