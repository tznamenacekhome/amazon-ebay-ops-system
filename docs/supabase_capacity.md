# Supabase Capacity Guardrails

Last updated: 2026-09-15

## Current compute - Medium, September 15, 2026

**Completed-run verification:** The authorized recovery run subsequently completed successfully at 21:10:05 UTC, with all five jobs successful. Across 125 capacity samples, available RAM never fell below 1.459 GiB and swap remained at least 99.9977% free. No capacity waits, database request errors or OOM events were logged. See [full run review](sourcing_medium_run_review_2026-09-15.md). The startup-only statements below are the original launch checkpoint.

After the disk expansion, the operator explicitly authorized upgrading compute and then running sourcing. The shared MBOP/College Planner project was upgraded from Small (2 GB RAM) to **Medium (4 GB RAM)** using the documented Management API billing-addon PATCH with `{"addon_type":"compute_instance","addon_variant":"ci_medium"}`. HTTP 200 was received at 19:02:14 UTC. During the expected restart, one metrics read timed out and another returned 521 while project status was `RESIZING`; sourcing was not launched during recovery.

At 19:03:09 UTC the project reported `ACTIVE_HEALTHY`, selected addon `ci_medium`, PostgreSQL up, and a successful HTTP 200 tiny sourcing-runs read. Metrics showed 4,009,824,256 bytes OS-visible RAM, 3,389,849,600 bytes available (3.16 GiB), all 1,073,737,728 swap bytes free, and 26,392,846,336 filesystem bytes free (24.58 GiB). The unchanged `pressure_reason` safety gate returned no blocker. Medium is $0.0822/hour (approximately $60/month), versus Small at $0.0206/hour (approximately $15/month): **about $45/month additional compute**, separate from the approximately $3/month additional disk. See [compute pricing](https://supabase.com/docs/guides/platform/manage-your-usage/compute).

One manual `sourcing-catalog` task was launched using the existing live EventBridge target's scheduler93 image, CPU/memory, command, and networking. Only the invocation's trigger-source label was changed to `manual-capacity-recovery`; no saved schedule or task definition was changed. Task: `d79fa556897e4082a54b88b2b6714ff6`; scheduler run: `33f583b3-41bf-4f26-bea5-0fc2b2e81877`; command: `python run_all_syncs.py --group sourcing-catalog`. At 19:04:50 UTC the task was RUNNING, production `database_guard_ready` passed, and Daily catalog sourcing had started. This is startup verification, not a completed-run claim.

Launch preflight checked fresh capacity, a tiny DB read, no recent running sourcing record and no running scheduler ECS tasks. An initial broad status check found historical rows still marked `running` (the latest started September 6 and already has a completion timestamp); those records were left unchanged. No application/matcher deployment, guard weakening, schema change, cleanup, or separate marketplace-write workflow was performed. The authorized sourcing group retains its ordinary configured provider reads and internal decision writes. ZFI's project is unchanged. Local evidence: `tmp/ops-20260915/compute-upgrade.json`, `compute-verified.json`, `sourcing-medium-run.json`, and `sourcing-medium-status.json`.

## Current provisioned disk - September 15, 2026

At the operator's request, the shared MBOP/College Planner project `amazon-ebay-ops` (`froeucjkcepuhgwisped`) was expanded from **8 GB to 32 GB**. The Management API accepted the disk-only update with HTTP 201 at 18:53:32 UTC and subsequently confirmed 32 GB provisioned. Storage remains gp3 with 3,000 IOPS and 125 MiB/s throughput; compute is unchanged.

At 18:55:45 UTC, live filesystem metrics confirmed **33,780,875,264 bytes (31.46 GiB)** total and **26,392,883,200 bytes (24.58 GiB)** available. PostgreSQL reports `pg_up=1`; a tiny database read after the resize request succeeded. This resolves the disk-headroom shortfall. Swap free was **236,785,664 of 1,073,737,728 bytes (22.05%)**, still below the sourcing guard's 25% requirement: `low_swap_headroom`. No sourcing rerun, schedule change, guard change, cleanup, migration, or application deployment accompanied this resize. ZFI's separate project was unchanged.

At the published rate of $0.125 per provisioned GB-month above the included 8 GB, 32 GB adds approximately **$3/month** at a full month's allocation, before taxes or credits. The included allowance below remains 8 GB. See [Supabase disk pricing](https://supabase.com/docs/guides/platform/manage-your-usage/disk-size) and the [pre-expansion storage inventory](database_storage_report_2026-09-15.md). Local operation evidence is in `tmp/ops-20260915/disk-resize.json` and `disk-resize-verified.json`.

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
- A task will run Amazon FBA inventory, listing status, inventory planning,
  reconciliation, Keepa, Informed, and other large snapshot/history writers
  back-to-back.
- Available disk approaches the sourcing guard minimum (the greater of 1 GiB or 15% of the filesystem); current provisioned capacity is 32 GB, with only 8 GB included in the plan.
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
- a sync writes duplicate snapshots with no new operational value.
- a dashboard/API query performs avoidable full-table reads.
- old raw snapshots/history can be retained less aggressively.

## MBOP Optimization Priorities

September 10, 2026: finance transaction source payloads now have a private,
lossless S3 archive path. Balance snapshots and transfer breakdowns remain in
PostgreSQL; historical cleanup retains the newest seven days inline. See
[finance payload storage](FINANCE_PAYLOAD_STORAGE_2026-09-10.md) for production
activation, access, verification, and restore commands. Do not remove FBA or
Keepa history based on PostgreSQL's stale row estimates.

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

## September 7 catalog safeguard

The catalog now uses a fail-closed metrics/tiny-read capacity gate and 25-row
opportunity writes. See [catalog recovery](sourcing_catalog_recovery_2026-09-07.md)
for thresholds and limitations. This does not measure remaining Disk IO Budget
or establish the exact cause of the observed database restart.
