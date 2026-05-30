# Supabase Capacity Guardrails

Last updated: 2026-05-29

MBOP uses Supabase as the operational source of truth. Treat Supabase capacity as an operational dependency before adding broad syncs, large backfills, snapshot tables, or dashboard queries that scan large tables.

## Current Billing Plan Limits

The project has been upgraded from Free to a paid Supabase plan with these included limits:

| Resource | Included | Over Included Limit |
|---|---:|---:|
| Monthly active users | 100,000 MAU | $0.00325 per MAU |
| Disk size per project | 8 GB | $0.125 per GB |
| Egress | 250 GB | $0.09 per GB |
| Cached egress | 250 GB | $0.03 per GB |
| File storage | 100 GB | $0.0213 per GB |
| Daily backups | 7 days stored | Included |
| Log retention | 7 days | Included |
| Log drains | Not included | $60 per drain, per project |
| Support | Email support | Included |

Important: these plan limits are not the same thing as compute size, sustained IOPS, or sustained disk throughput. A paid plan can still exhaust Disk IO Budget if the selected compute size is too small for MBOP's sync workload.

## IO Risk Lessons

On 2026-05-28, Supabase became unavailable for MBOP after Disk IO Budget exhaustion. Symptoms included:

- Supabase Table Editor failed to load schemas and tables.
- Table Editor showed `Failed to run sql query: connect ECONNREFUSED ...:5432`.
- API reads returned Cloudflare `522 Connection timed out`.
- Even a one-row `import_batches` read failed.

This means the database can become unreachable before application-level code can recover. Avoid treating retries as the primary fix for sustained IO exhaustion.

## When To Warn Before Running Work

Warn the operator before running or adding work if any of these are true:

- Database Health shows Disk IO Budget materially consumed, especially above 50%.
- Disk IO Budget is near or at 100%.
- Supabase table editor, SQL editor, or API probes are timing out.
- A task will write more than a few thousand snapshot rows in one run.
- A task will repeatedly scan full snapshot/history tables.
- A task will run Amazon FBA inventory, listing status, inventory planning, reconciliation, Keepa, Informed, and business value snapshots back-to-back.
- Database size is approaching 6 GB, because the included project disk size is 8 GB.
- A new feature adds unbounded raw payload/history storage.

If Disk IO Budget is already exhausted or the database is refusing connections, stop scheduled syncs and do not rerun full orchestration until Supabase responds to a tiny read.

## Upgrade Guidance

If MBOP hits Disk IO Budget during normal syncs, first optimize obvious waste, then upgrade compute if the workload is still legitimate.

Prefer upgrading compute when:

- the workload is normal daily operations, not a one-time mistake.
- Disk IO Budget is consumed repeatedly.
- the database remains slow after snapshot retention and query improvements.
- broad syncs are needed during business hours.

Prefer optimization first when:

- the issue came from a one-time backfill.
- a sync writes duplicate snapshots with no new business value.
- a dashboard/API query performs avoidable full-table reads.
- old raw snapshots/history can be retained less aggressively.

## MBOP Optimization Priorities

Before increasing sync volume, check or improve:

- snapshot retention for Amazon FBA, Amazon listings, Keepa, Informed, and InventoryLab tables.
- batch sizes and pacing in `run_all_syncs.py`.
- whether health checks use `logs/sync_health.json` or a future sync ledger instead of heavy domain-table inference.
- whether dashboard APIs aggregate in SQL/backend views instead of frontend/client scans.
- indexes for high-volume filters and latest-snapshot views.
- whether raw API payloads can be stored only where they are operationally useful.

## Recovery Playbook

When Supabase is unreachable:

1. Disable or pause scheduled syncs.
2. Confirm Supabase status and project Database Health.
3. Upgrade compute or restart the database if the project is unhealthy.
4. Wait until a tiny read succeeds.
5. Rerun failed syncs or `run_all_syncs.py`.
6. Review `logs/sync_health.json` and `/system-health`.

Use a tiny read probe before rerunning expensive work:

```powershell
.\.venv\Scripts\python.exe -c "import os; from dotenv import load_dotenv; from supabase import create_client; load_dotenv(); s=create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_ROLE_KEY']); r=s.table('import_batches').select('import_batch_id').limit(1).execute(); print('ok', len(r.data or []))"
```
