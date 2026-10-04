# Royal Electronics email ingestion

MBOP polls only `tim@midnightbe.com` for messages from `sales@royalelec.com` and
`gp@royalelec.com`. It reads `.xlsx`, `.xls`, and `.csv` attachments or HTTPS
download links whose host is explicitly configured. It never sends mail.

The job validates the file with the existing Royal parser, records a message
checkpoint and SHA-256, imports through `wholesale_apply_import`, queues only new
or stale identities for Amazon matching, and requests cached evaluation for
already matched products. Failures retry with bounded backoff. Permanent failures
appear in the MBOP notification bell and Wholesale **Import history**.

## One-time Microsoft setup

1. Create a Microsoft Entra application for this integration.
2. Add Microsoft Graph **Application** permission `Mail.Read` and grant admin
   consent. Do not add `Mail.Send`, delegated permissions, or broader write
   permissions.
3. Restrict the app to `tim@midnightbe.com` with Exchange Online application
   access policy (or the current Exchange Application RBAC equivalent), then run
   `Test-ApplicationAccessPolicy` for that mailbox and for an unrelated mailbox.
4. Create a client secret and put the tenant ID, client ID, and client secret in
   AWS Secrets Manager. The scheduler task exposes them as
   `ROYAL_GRAPH_TENANT_ID`, `ROYAL_GRAPH_CLIENT_ID`, and
   `ROYAL_GRAPH_CLIENT_SECRET`.
5. Set `ROYAL_GRAPH_MAILBOX=tim@midnightbe.com`. Set
   `ROYAL_DOWNLOAD_ALLOWED_DOMAINS` to a comma-separated allowlist of the Royal
   download host names observed in a real supplier message. Redirects are checked
   against the same list and URLs are never stored.

Suggested Exchange Online policy sequence (run by the Microsoft 365 admin after
creating a mail-enabled security group containing only the MBOP mailbox):

```powershell
Connect-ExchangeOnline
New-ApplicationAccessPolicy -AppId <entra-client-id> -PolicyScopeGroupId <scope-group-address> -AccessRight RestrictAccess -Description "MBOP Royal price-list reader"
Test-ApplicationAccessPolicy -Identity tim@midnightbe.com -AppId <entra-client-id>
Test-ApplicationAccessPolicy -Identity <unrelated-mailbox> -AppId <entra-client-id>
```

The first test must return `Granted`; the unrelated mailbox test must return
`Denied`.

## Database and deployment

Apply `supabase/migrations/20261004033000_mbop_royal_email_ingestion.sql` through
the canonical MBOP migration workflow. Build and deploy the scheduler and web
images, then configure the EventBridge schedule:

```powershell
.\scripts\aws-login.ps1
supabase migration list
supabase db push
.\scripts\deploy-scheduler.ps1 -EnableRoyalEmail -RoyalDownloadAllowedDomains "<royal-download-host>" -TaskRoleArn arn:aws:iam::297464765814:role/mbop-scheduler-task-role
.\scripts\configure-royal-wholesale-schedule.ps1 -TaskDefinitionArn <new-task-definition-arn>
.\scripts\deploy-web.ps1
.\scripts\aws-web-status.ps1
```

The schedule runs `python run_all_syncs.py --group wholesale-email-ingestion`
every 15 minutes. That group has a Supabase distributed lock, so overlapping
schedule invocations cannot mutate the wholesale workflow concurrently.

## Controlled validation

Forward or place one known Royal message in the scoped inbox. Run one ECS task
with the wholesale group, then verify:

- the email checkpoint contains sender, received time, source type, SHA-256,
  effective date, and import ID;
- `/wholesale` shows the import and its row count;
- replaying the same task records no duplicate observations;
- a deliberately invalid test file produces one deduplicated notification;
- the scheduler remains successful on the following idle run.

Never paste a signed download URL, Graph token, client secret, or attachment body
into logs or database fields.
