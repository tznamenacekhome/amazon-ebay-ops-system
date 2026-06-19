# MBOP Cloud Deployment Phase 1

Phase 1 deploys the Next.js web app and API to AWS as a container while keeping
Supabase as the database and scheduled Python sync jobs on the local Windows
machine.

## Required Cloud Environment Variables

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

Recommended for Phase 1:

- `CLOUD_DEPLOYMENT=true`
- `LOCAL_SYNC_ENABLED=false`
- `MBOP_ADMIN_API_TOKEN=<long random internal token>`

Webhook-specific:

- `EASYPOST_WEBHOOK_SECRET`
- `EASYPOST_WEBHOOK_TOLERANCE_MINUTES` defaults to `1` when omitted

Optional repricing identifier overrides:

- `AMAZON_SP_API_SELLER_ID`
- `AMAZON_SELLER_ID`
- `AMAZON_MERCHANT_ID`

Do not expose `SUPABASE_SERVICE_ROLE_KEY` or `MBOP_ADMIN_API_TOKEN` to browser
code. Do not prefix them with `NEXT_PUBLIC_`.

## Cloud Flags

Cloud mode is active when either of these is true:

- `CLOUD_DEPLOYMENT=true`
- `LOCAL_SYNC_ENABLED=false`

Local development remains unchanged when neither flag is set.

## Disabled Local Execution In Cloud Mode

The following endpoints do not run local Python, batch files, or Windows shell
commands in cloud mode:

- `POST /api/sync-refresh`
- `POST /api/sourcing/runs` when `execute=true`
- `POST /api/sourcing/settings/apply`
- Receiving background Keepa/Amazon fee refresh after `POST /api/receiving`

These jobs remain on the local scheduler for Phase 1.

## Health And Freshness Signals

System health and freshness routes continue to read Supabase signals in cloud
mode. Local file signals from `logs/` and `data/` are reported as unavailable
instead of being treated as application failures.

Affected local file signals include:

- `logs/scheduler.log`
- `logs/sync_health.json`
- `logs/sync_runs.jsonl`
- `logs/inventory_source_balance_audit_latest.json`
- `data/revseller_enrichment_diagnostics_*.csv`

## Temporary Admin Protection

When `MBOP_ADMIN_API_TOKEN` is set, privileged mutation endpoints require either:

- `x-mbop-admin-token: <token>`
- `Authorization: Bearer <token>`

The EasyPost webhook is not protected by this token. It continues to use its own
HMAC secret.

## ECS Container Deployment

Build the web container from the `web/` directory:

```bash
docker build -t mbop-web:phase1 ./web
```

Run locally with cloud-safe flags:

```bash
docker run --rm -p 3103:3103 -e PORT=3103 -e CLOUD_DEPLOYMENT=true -e LOCAL_SYNC_ENABLED=false -e SUPABASE_URL=<supabase-url> -e SUPABASE_SERVICE_ROLE_KEY=<service-role-key> mbop-web:phase1
```

Required ECS task environment variables:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `CLOUD_DEPLOYMENT=true`
- `LOCAL_SYNC_ENABLED=false`

Recommended:

- `MBOP_ADMIN_API_TOKEN=<long random internal token>`

Scheduled Python jobs remain local during Phase 1. Local job routes are disabled
in cloud mode and return a clear JSON response instead of attempting to run
Windows shell commands or local Python scripts.

## Container Start

Use the web package start script:

```bash
npm run build
npm start
```

The start script binds Next.js to `0.0.0.0` and respects the container `PORT`
environment variable.
