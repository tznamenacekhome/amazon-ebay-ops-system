# MBOP AWS Deployment

Last updated: 2026-06-21

This document records the authoritative AWS production state for MBOP as inspected from AWS CLI on 2026-06-21. Live AWS state remains the highest authority.

## Current Live State

Known from the latest handoff:

- Region: `us-west-2`
- Account: `297464765814`
- Runtime: ECS/Fargate
- ECS cluster: `mbop-cluster1`
- ECS web service: `mbop-web-service`
- Current web task definition: `mbop-web-task:14`
- Current web container: `mbop-web`
- Web task size: `0.5 vCPU / 1 GiB`
- Web container port: `3103`
- App domain: `https://mbop.midnightblueenterprises.com`
- Static homepage: S3 plus CloudFront
- CloudFront domain: `dfmaesup5ihuk.cloudfront.net`
- Public site domain: `www.midnightblueenterprises.com`
- Authentication: Google OAuth to Cognito to ALB authentication to MBOP
- Network: no NAT Gateway, public default subnets in `us-west-2a` and `us-west-2b`, one ALB, one running ECS web task
- Cloud flags: `CLOUD_DEPLOYMENT=true`, `LOCAL_SYNC_ENABLED=false`
- Logout route: `/api/logout`
- EasyPost webhook route: `/api/easypost/webhook`

The deployed web image is built from `web/Dockerfile`. It is web-only: it contains the Next.js app and does not include Python, `run_all_syncs.py`, `integrations/`, or `requirements.txt`.

## ECS Web Service

- Service ARN: `arn:aws:ecs:us-west-2:297464765814:service/mbop-cluster1/mbop-web-service`
- Desired count: `1`
- Running count: `1`
- Capacity provider: `FARGATE`
- Platform version: `1.4.0`
- Deployment circuit breaker: enabled with rollback
- Health check grace period: `300` seconds
- Current target: healthy
- Current web task revision uses `/mbop/prod/supabase/service-role-key`; the
  old phase-1 Supabase secret is scheduled for deletion.

Network configuration:

- VPC: `vpc-0aba3173cb039c55c`
- Subnets:
  - `subnet-07558cd00060ff69d` / `us-west-2b`
  - `subnet-0acbbc29cdf301200` / `us-west-2a`
- ECS service security group: `sg-0b05e7760083c5e31` / `mbop-web-sg`
- Public IP assignment: `ENABLED`

## ECR Images

Web repository:

```text
297464765814.dkr.ecr.us-west-2.amazonaws.com/mbop-web
```

Current web task image:

```text
297464765814.dkr.ecr.us-west-2.amazonaws.com/mbop-web@sha256:3768396b304d3c34030607f1e5353f335e0d3635cf99f52c490ba29a8fa23e58
```

Tag `system-health-drawer-20260621` points at the current digest.

Scheduler repository:

```text
297464765814.dkr.ecr.us-west-2.amazonaws.com/mbop-scheduler
```

Scheduler task definition:

```text
arn:aws:ecs:us-west-2:297464765814:task-definition/mbop-scheduler-task:1
```

The task definition is registered against image tag `297464765814.dkr.ecr.us-west-2.amazonaws.com/mbop-scheduler:latest`.

Current scheduler image digest:

```text
sha256:c7a24284e3bf17167e6783600d734c5ae8e1797ebd6cc5e1b112ccfabd253206
```

## ALB

- Name: `mbop-alb`
- ARN: `arn:aws:elasticloadbalancing:us-west-2:297464765814:loadbalancer/app/mbop-alb/8e84d87a6b73d2a6`
- DNS name: `mbop-alb-1736189201.us-west-2.elb.amazonaws.com`
- Scheme: internet-facing
- Type: application
- VPC: `vpc-0aba3173cb039c55c`
- Security group: `sg-0f50ebb07c1d9bf54` / `mbop-alb-sg`

Listeners:

- HTTP `:80` redirects to HTTPS `:443`.
- HTTPS `:443` uses certificate `arn:aws:acm:us-west-2:297464765814:certificate/7ab1ea57-6d96-4e53-8a9b-e98d7564f21a`.
- HTTPS default actions:
  1. `authenticate-cognito`
  2. forward to `mbop-web-tg`

HTTPS listener rules:

- Priority `10`: path `/api/easypost/webhook` forwards directly to
  `mbop-web-tg` without Cognito authentication so EasyPost can deliver webhook
  POST requests.
- Default: Cognito authentication, then forward to `mbop-web-tg`.

Target group:

- Name: `mbop-web-tg`
- ARN: `arn:aws:elasticloadbalancing:us-west-2:297464765814:targetgroup/mbop-web-tg/fd98cb96dbfae8b1`
- Protocol/port: `HTTP:3103`
- Target type: `ip`
- Health check path: `/`
- Matcher: `200-499`

## Cognito

- User pool ID: `us-west-2_IBxxtQ9xL`
- User pool name: `User pool - fqjwyk`
- App client name: `MBOP-rotated-20260621`
- App client ID: `11i581nub6aqvqecjmqddrfj7o`
- Hosted UI domain: `us-west-2ibxxtq9xl`
- Hosted UI CloudFront distribution: `dpp0gtxikpq3y.cloudfront.net`
- Identity provider: `Google`
- Supported identity providers: `Google` only
- Explicit auth flows: `ALLOW_REFRESH_TOKEN_AUTH`
- ALB auth session cookie: `AWSELBAuthSessionCookie`
- ALB auth scope: `openid`
- ALB auth session timeout: `604800` seconds
- Logout URL: `https://mbop.midnightblueenterprises.com/`

## Static Homepage

- S3 bucket: `midnightblueenterprises.com`
- Bucket region: `us-west-2`
- S3 website index: `index.html`
- CloudFront distribution ID: `E2KKKB5MJ8CV3N`
- CloudFront domain: `dfmaesup5ihuk.cloudfront.net`
- CloudFront aliases:
  - `midnightblueenterprises.com`
  - `www.midnightblueenterprises.com`
- CloudFront origin: `midnightblueenterprises.com.s3-website-us-west-2.amazonaws.com`
- Viewer policy: redirect HTTP to HTTPS
- CloudFront certificate: `arn:aws:acm:us-east-1:297464765814:certificate/8c3e6686-2bd5-4437-8f96-b744dfb4f40e`

Route53:

- This AWS account currently has no Route53 hosted zones. DNS appears to be managed outside Route53 or in another account.

## ACM Certificates

ALB certificate in `us-west-2`:

```text
arn:aws:acm:us-west-2:297464765814:certificate/7ab1ea57-6d96-4e53-8a9b-e98d7564f21a
Domain: mbop.midnightblueenterprises.com
Status: ISSUED
```

CloudFront certificate in `us-east-1`:

```text
arn:aws:acm:us-east-1:297464765814:certificate/8c3e6686-2bd5-4437-8f96-b744dfb4f40e
Domains: midnightblueenterprises.com, www.midnightblueenterprises.com
Status: ISSUED
```

## Live Verification Commands

Run these from an AWS-authenticated shell. Do not paste secret values into docs.

```powershell
aws ecs describe-services --region us-west-2 --cluster mbop-cluster1 --services mbop-web-service
aws ecs describe-task-definition --region us-west-2 --task-definition mbop-web-task:14
aws elbv2 describe-load-balancers --region us-west-2
aws elbv2 describe-listeners --region us-west-2 --load-balancer-arn <alb-arn>
aws elbv2 describe-rules --region us-west-2 --listener-arn <https-listener-arn>
aws cognito-idp list-user-pools --region us-west-2 --max-results 20
aws route53 list-hosted-zones
aws cloudfront list-distributions
aws acm list-certificates --region us-west-2
aws acm list-certificates --region us-east-1
aws secretsmanager list-secrets --region us-west-2 --query "SecretList[].Name"
aws logs describe-log-groups --region us-west-2 --log-group-name-prefix /ecs/
```

## Web Deployment

Build the web image from the `web/` directory:

```powershell
Set-Location C:\Dev\amazon-ebay-ops-system\web
docker build -t mbop-web:<tag> .
```

Push to the ECR repository used by `mbop-web-task`, then register a new revision of `mbop-web-task` with the new image URI. Keep:

```text
CLOUD_DEPLOYMENT=true
LOCAL_SYNC_ENABLED=false
SUPABASE_URL=https://froeucjkcepuhgwisped.supabase.co
```

Update the ECS service:

```powershell
aws ecs update-service --region us-west-2 --cluster mbop-cluster1 --service mbop-web-service --task-definition mbop-web-task:<revision>
```

## Auth And Domains

The production app domain is fronted by an ALB with Cognito authentication. Cognito uses Google as the identity provider. The Google OAuth secret has been rotated and the old secret was deleted.

The shared MBOP app shell links to `/api/logout`. That route clears ALB auth
cookies and redirects through the Cognito hosted UI logout endpoint.

Verify listener rules before changing auth:

- HTTPS listener should authenticate with Cognito before forwarding to the MBOP target group.
- Cognito callback/logout URLs must match the app domain.
- Google OAuth authorized redirect URIs must match the Cognito domain callback.

## Static Site

`www.midnightblueenterprises.com` points to CloudFront. CloudFront serves the homepage/static site from S3. The CloudFront certificate is issued through ACM in `us-east-1`.

## Secrets

Existing phase-1 web secret:

- `mbop/phase1/supabase-service-role-key` is no longer used by the live web
  task and is scheduled for deletion on 2026-06-28.

Current web and scheduler Supabase secret:

- `/mbop/prod/supabase/service-role-key`

Scheduler production secrets now exist under `/mbop/prod/*`. See [MBOP_AWS_SCHEDULER_PLAN.md](./MBOP_AWS_SCHEDULER_PLAN.md) for environment mappings.

EasyPost webhook validation secret:

- `/mbop/prod/easypost/webhook-token`

Admin mutation token:

- `/mbop/prod/admin/api-token`

Do not store secret values in the repo.

## EasyPost Webhook

Production webhook:

```text
Webhook ID: hook_d9fecfc86d0611f19a5d15e5f9712463
URL: https://mbop.midnightblueenterprises.com/api/easypost/webhook
Mode: production
Status: enabled
```

The route is POST-only. A GET smoke check through the public domain should
return `405`, not a Cognito redirect. The route now rejects a bare static token:
webhook calls must pass EasyPost HMAC headers or the internal token plus
timestamp/signature headers.

Verification on 2026-06-20:

- GET `/api/easypost/webhook` returned `405` through the public domain.
- Authenticated smoke POST with a non-tracker event returned `200` and
  `{ received: true, ignored: true }`.

## Logging

Web log group:

```text
/ecs/mbop-web-task
```

Scheduler logs should use:

```text
/ecs/mbop-scheduler
stream prefix: scheduled
retention: 30 days initially
```

The scheduler log group exists and has 30-day retention.

## IAM

Shared scheduler/default ECS execution role:

```text
arn:aws:iam::297464765814:role/ecsTaskExecutionRole
```

Attached AWS-managed policy:

```text
service-role/AmazonECSTaskExecutionRolePolicy
```

Inline policy:

```text
mbop-phase1-secret-read
```

The inline policy allows `secretsmanager:GetSecretValue` for `/mbop/prod/*`
secrets and is used by scheduler task definitions.

Web ECS execution role:

```text
arn:aws:iam::297464765814:role/mbop-web-task-execution-role
```

Attached AWS-managed policy:

```text
service-role/AmazonECSTaskExecutionRolePolicy
```

Inline policy:

```text
mbop-web-secret-read
```

This role is used by `mbop-web-task:14` and can read only the web runtime
secrets: Supabase service role, EasyPost webhook secret, and admin API token.

## Security Hardening Status

Applied on 2026-06-21:

- `MBOP_ADMIN_API_TOKEN` is configured in ECS from
  `/mbop/prod/admin/api-token`.
- Mutation routes require either the internal admin token or an
  ALB-authenticated same-origin browser request with `x-mbop-csrf: 1`.
- Frontend mutation calls send `x-mbop-csrf: 1`.
- Cognito app client secret was rotated by replacing the old client with
  `MBOP-rotated-20260621`; the old app client was deleted.
- Cognito login is Google-only, with direct user-pool auth flows reduced to
  refresh-token auth.
- ALB now uses dedicated security group `sg-0f50ebb07c1d9bf54` /
  `mbop-alb-sg`, not the default security group.
- ECS web task security group now allows port `3103` from `mbop-alb-sg`.

## CloudFront WAF

The static homepage CloudFront distribution still has AWS WAF web ACL
`CreatedByCloudFront-55bad07c` associated.

Read-only review on 2026-06-21:

- CloudFront distribution: `E2KKKB5MJ8CV3N` /
  `dfmaesup5ihuk.cloudfront.net`.
- Aliases: `www.midnightblueenterprises.com`,
  `midnightblueenterprises.com`.
- Origin: S3 website endpoint
  `midnightblueenterprises.com.s3-website-us-west-2.amazonaws.com`.
- The distribution has one origin and one cache behavior. It only allows
  `GET` and `HEAD`.
- The MBOP app and webhook do not route through this distribution.
  `mbop.midnightblueenterprises.com` resolves to the ALB
  `mbop-alb-1736189201.us-west-2.elb.amazonaws.com`.
- The WAF web ACL is attached only to this CloudFront distribution.
- Shield Advanced is inactive, there are no CloudFront distribution tenants,
  and there is no CloudFront monitoring subscription.
- WAF logging is not enabled.
- Recent WAF request metrics had no datapoints yet.

The WAF ACL appears to come from CloudFront one-click AWS WAF protections. The
rule groups are:

- `AWSManagedRulesAmazonIpReputationList`
- `AWSManagedRulesCommonRuleSet`
- `AWSManagedRulesKnownBadInputsRuleSet`

AWS rejected direct WAF removal with:

```text
Distributions with a pricing plan subscription must have a web ACL resource.
```

The CloudFront console shows the distribution on the CloudFront security
protections **Free plan** (`$0/month`) with **Core protections** enabled. The
word "subscription" in the API error refers to the CloudFront security
protections plan state, not to the paid Business plan. Advanced DDoS protection
is not enabled.

This is not protecting MBOP app/API data because MBOP app/API traffic goes to
the ALB/Cognito endpoint, not this CloudFront distribution. The WAF only
protects the static homepage path.

S3 origin exposure:

- Bucket: `midnightblueenterprises.com`
- Static website hosting is enabled.
- Bucket policy is public read for `arn:aws:s3:::midnightblueenterprises.com/*`.
- Public access blocks are disabled.
- There is no CloudFront OAC/OAI because the origin is the public S3 website
  endpoint.

Cost:

- The CloudFront security protections plan shown in the console is the Free
  plan (`$0/month`) and the console says the included WAF protections are
  available at no additional charge.
- Cost Explorer month-to-date service breakdown does not show an AWS WAF line
  item for these included CloudFront protections.
- Generic AWS WAF pricing can still apply to separately created or non-included
  web ACLs, managed rule groups, and request volume. Monitor Cost Explorer for
  AWS WAF after the next full billing cycle.

Recommendation:

- Keep the included CloudFront Core protections enabled while they remain
  free/included. They are blocking unwanted homepage requests at no observed
  added cost.
- If AWS WAF charges appear later, removal is still safe for MBOP app/data
  because the MBOP app, APIs, and EasyPost webhook do not route through this
  CloudFront distribution.
- The homepage remains public static content either way because the S3 website
  bucket is directly public.

Safe removal path:

Use this only if AWS later shows WAF charges or if the homepage intentionally no
longer needs CloudFront security metrics/filtering.

1. In the CloudFront console, open distribution `E2KKKB5MJ8CV3N`.
2. Open the Security / WAF protections area.
3. Use **Manage protections** to disable Core protections / AWS WAF protection
   for the distribution. The distribution can remain on the Free plan.
4. After the subscription is disabled, disassociate the web ACL from the
   distribution.
5. Delete WAF web ACL `CreatedByCloudFront-55bad07c` after confirming it is no
   longer associated with any distribution.
6. Verify `www.midnightblueenterprises.com` still serves the static homepage and
   `mbop.midnightblueenterprises.com` still resolves to the ALB.

Lowest-cost safe alternative if WAF must remain:

- Keep the current WAF ACL as-is. It has no logging enabled and no premium Bot
  Control/Fraud Control rule groups, so it is already close to the lowest-cost
  WAF posture.
- Optionally narrow CloudFront `PriceClass` from `PriceClass_All` to a cheaper
  regional price class for static homepage traffic, but that is separate from
  WAF cost.

EventBridge Scheduler role:

```text
arn:aws:iam::297464765814:role/mbopEventBridgeSchedulerEcsRole
```

This role can run `mbop-scheduler-task:*` on `mbop-cluster1` and pass `ecsTaskExecutionRole`.

## Remaining Deployment Items

- Observe the first full day of EventBridge Scheduler runs and check System Health run history.
- Observe the first real EasyPost webhook delivery and verify Supabase shipment updates.
- Add an independent scheduled Postgres backup outside Supabase managed backups.
