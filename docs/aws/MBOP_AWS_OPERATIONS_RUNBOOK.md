# MBOP AWS Operations Runbook

Last updated: 2026-06-20

## Deploy Web Updates

1. Build the web image from `web/`.
2. Push it to the ECR repository used by `mbop-web-task`.
3. Resolve the pushed image digest and register a new `mbop-web-task` revision pinned to that digest.
4. Keep `CLOUD_DEPLOYMENT=true` and `LOCAL_SYNC_ENABLED=false`.
5. Preserve required secrets such as `SUPABASE_SERVICE_ROLE_KEY` and, while the
   webhook is enabled, `EASYPOST_WEBHOOK_TOKEN` / `EASYPOST_WEBHOOK_SECRET`.
6. Update `mbop-web-service` to the new task revision.
7. Wait for the ECS service to stabilize, then verify target health and `https://mbop.midnightblueenterprises.com`.

```powershell
aws ecs update-service --region us-west-2 --cluster mbop-cluster1 --service mbop-web-service --task-definition mbop-web-task:<revision>
```

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

If pushing `:latest`, the registered task definition `mbop-scheduler-task:1` can be smoke-tested immediately after the push. If pushing a different tag, register a new task definition revision with that image tag or digest.

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
- If the secret name or ARN changes, register a new `mbop-web-task` revision and
  redeploy the web service.
- Keep scheduled EasyPost polling until real webhook deliveries have been
  observed updating Supabase shipment rows.

## Logout

The shared app shell links to `/api/logout`. Cognito app-client logout URLs must
include:

```text
https://mbop.midnightblueenterprises.com/
```

If logout redirects fail, verify the Cognito app client callback/logout URL
lists and the hosted UI domain recorded in `MBOP_AWS_DEPLOYMENT.md`.

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

AWS EventBridge Scheduler supersedes local Windows Task Scheduler jobs. If old
tasks remain on the workstation, remove them from an Administrator PowerShell:

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

Expected current AWS cost from handoff: roughly `$35-$50/month`. Expected total MBOP hosting with Supabase: roughly `$60-$75/month`. Scheduler cost increase should be small if groups remain bounded and staggered.
