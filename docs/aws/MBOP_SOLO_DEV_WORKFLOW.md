# MBOP Solo Developer AWS Workflow

This is the day-to-day workflow for one developer making MBOP code changes and
deploying the web app to AWS.

## Mental Model

GitHub and AWS are separate states:

```text
local code -> git commit -> GitHub push -> AWS deploy -> live website
```

`git push` means the code is published to GitHub.

`scripts/deploy-web.ps1` means the live ECS web service is updated.

## Daily AWS Login

Use the daily admin profile:

```powershell
.\scripts\aws-login.ps1
```

That runs AWS SSO for profile `mbop-admin` and verifies the caller identity.

Do not use root for daily deploys. Root is preserved only as a fallback profile:

```powershell
.\scripts\aws-login.ps1 -RootFallback
```

Use root only for account recovery, billing, or break-glass account work.

## Check What Is Live

After login:

```powershell
.\scripts\aws-web-status.ps1
```

This prints:

- Current ECS service task definition.
- Current web image digest/tag.
- Deployment rollout state.
- Desired/running task counts.
- Recent ECS service events.
- Build SHA environment variables when present.

The app shell also shows the deployed build SHA in the lower-left navigation.

## Deploy Web

Commit and push first:

```powershell
git status
git add <files>
git commit -m "Describe the change"
git push
```

Then deploy:

```powershell
.\scripts\deploy-web.ps1
```

Local `npm run build` is useful as a compile/type check, but it is not the
production test for MBOP. The production app runs on ECS/Fargate behind
ALB/Cognito. After deploy, use `.\scripts\aws-web-status.ps1` and browser
verification at `https://mbop.midnightblueenterprises.com`.

The deploy script:

1. Refuses to deploy a dirty working tree by default.
2. Tags the Docker image with the current git SHA.
3. Builds `web/Dockerfile`.
4. Pushes the image to ECR.
5. Registers a new `mbop-web-task` revision pinned to the pushed image digest.
6. Preserves the existing ECS task definition settings and secrets.
7. Forces `CLOUD_DEPLOYMENT=true` and `LOCAL_SYNC_ENABLED=false`.
8. Updates `mbop-web-service`.
9. Waits for ECS to stabilize.

## Troubleshooting Login

If a browser opens to an IAM user sign-in page and rejects known-good
credentials, check whether you are on the wrong sign-in path.

For daily MBOP work, prefer:

```powershell
.\scripts\aws-login.ps1
```

If you intentionally need the account root login, use:

```powershell
.\scripts\aws-login.ps1 -RootFallback
```

On the browser page, choose root sign-in only for the root fallback flow.

## Quick Recovery Commands

Show profiles:

```powershell
aws configure list-profiles
```

Verify daily admin identity:

```powershell
aws sts get-caller-identity --profile mbop-admin
```

Verify current default identity:

```powershell
aws sts get-caller-identity
```

The local AWS config was adjusted so `default` and `mbop-admin` both use the
same SSO admin profile. The old root-style console login is preserved as
`root-console`.
