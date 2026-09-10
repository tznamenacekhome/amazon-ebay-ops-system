# Lossless finance payload storage optimization

## Scope

Only `amazon_finance_balance_snapshots.raw_transactions_json` moves to private
compressed S3 storage. Every snapshot row, timestamp, monetary value, transaction
count, note, and `raw_financial_event_groups_json` value remains intact. In
particular, the transfer breakdown read by `push_zfi_business_summary.py` stays
inline. No purchase, COGS, FBA inventory, Keepa, or sourcing row is changed.

Repository dependency review found no runtime reader of `raw_transactions_json`.
This internal diagnostic field now supports either the original JSON or an
archive reference. Analysts must use `restore_payload` to recover archived
source transactions; a direct JSON query against that column alone no longer
returns those transactions. This is not a change to the ZFI Buying contract.

Exact live counts corrected misleading PostgreSQL row estimates: 860,617 FBA
inventory snapshots, 67,841 Keepa snapshots, and 278 finance balance snapshots.
These tables hold real history; small estimated counts were not proof of bloat.
FBA and Keepa historical retention is unchanged.

## Archive and access

- Bucket: `mbop-finance-archive-297464765814-us-west-2`.
- Region/account: `us-west-2` / `297464765814`.
- All public access blocked; bucket-owner-enforced ownership; AES256 server-side
  encryption; versioning enabled; bucket policy denies non-TLS requests.
- Worker inline policy `MBOPFinancePayloadArchive` permits only GetObject and
  PutObject under `finance-transactions/v1/`. It grants no deletion or listing.
- Full historical snapshot backups use `finance-snapshot-backups/v1/`, accessible
  to the operator's AWS role, not granted by the worker's new policy.
- No expiration lifecycle is configured. Do not delete these objects: they are
  historical source evidence, not disposable cache.

Objects use canonical JSON, gzip compression, and content-addressed SHA-256
keys. Every upload is downloaded, decompressed, hashed, and compared to its
source before the database receives an archive reference. The reference records
format, bucket, key, uncompressed length, and checksum. Historical references
also contain the verified full snapshot backup reference.

## Writer behavior

`MBOP_FINANCE_PAYLOAD_ARCHIVE=1` enables archiving in the finance importer.
Other jobs do not use this setting. Without it, the importer writes the original
inline payload. An archive failure logs a warning and keeps the full inline
payload, so ingestion and finance balances remain available.

Activation changed only the three existing finance-refresh task
targets. Their complete schedule definitions and cadence were preserved. No web
deployment or schema migration is required. Do not launch sourcing as part of
this change.

## Maintenance and rollback

`scripts/archive-finance-payloads.py` is dry-run by default, allows at most 300
rows per invocation, uses one worker by default (up to three with `--workers`),
keeps seven days inline during historical cleanup, and
verifies all non-payload fields after each update. Snapshot import is append-only;
do not run another maintenance writer concurrently. Recovery manifests live in
ignored `logs/diagnostics/finance-archive-20260910/manifest.jsonl`.

```powershell
.venv/Scripts/python.exe scripts/archive-finance-payloads.py --limit 25
.venv/Scripts/python.exe scripts/archive-finance-payloads.py --limit 25 --apply
.venv/Scripts/python.exe scripts/archive-finance-payloads.py --restore-id <snapshot-uuid>
.venv/Scripts/python.exe scripts/archive-finance-payloads.py --restore-id <snapshot-uuid> --apply
```

Restore verifies the remote object's checksum before updating and compares all
other row fields afterward. Ensure disk headroom before restoring many large
payloads. Restoring the previous finance task definitions disables future archive
writes; existing balances remain readable even with archived diagnostics.

Initial tests cover lossless round trips, deterministic references, corrupted
checksums, destination restrictions, disabled behavior, preserved balance fields,
and failure before reference creation. A production canary was archived and then
restored successfully before the larger historical batch.

Deletion/update alone does not prove physical disk reclamation. Report actual
filesystem measurements after cleanup. Any table rewrite requires a separate
bounded maintenance operation with lock avoidance and adequate free space.

## Production results

- Source commit `d1f739eb1469`; finance task revision `mbop-scheduler-task:88`.
  Image digest `sha256:fb06d0cf52a2307429bbc75f6f53a485a9b93ed85b293d9e59c15f0e91636235`.
  The dirty image tag reflects unrelated untracked documentation; committed
  application source was used. Revision 87 was the build helper's intermediate
  registration; no schedules target it.
- The three finance schedules previously used revision 66. Revision 88 copies
  that configuration and changes only image and archive opt-in environment flag.
  All 20 schedule definitions were compared; only three task references changed.
- Worker smoke `c823722011484fb4815801eea9a58579` exited zero: real ECS role
  uploaded/recovered a real source payload and verified unchanged balance fields.
  The smoke made no database writes and did not call Amazon.
- Archived 257 snapshots older than seven days; retained 21 recent snapshots
  inline. All 278 rows remain. Every archived row's non-payload fields matched
  its original fingerprint both before and after physical compaction.
- Verified full-row backups and original payload objects are retained in S3.
  One production row was restored successfully as a rollback test before cleanup.
- `sql/2026-09-10_compact_finance_payload_storage.sql` ran as standalone
  maintenance through the Supabase Management query API on the verified project.
  There were zero locks on the target table at preflight. The single-table
  `VACUUM (FULL, ANALYZE, SKIP_LOCKED)` returned successfully in 0.78 seconds.
  No schema migration or migration-ledger change was made.
- Table size: 364,486,656 -> 24,264,704 bytes; reclaimed 340,221,952 bytes (93.3%).
  Database size afterward: 6,286,740,627 bytes. Free filesystem space:
  1,568,641,024 / 8,416,882,688 bytes (18.64%). Capacity guard returns no blocking
  reason. These are observations, not a guarantee of future growth headroom.
- Eight archive/importer tests passed, including dry-run and archive-outage
  fallback behavior. Python compile checks and the scheduler Docker build passed.
  No web code changed or web build/deployment was needed.
- No sourcing run was launched; the operator plans to run it later in the day.

This phase leaves the larger FBA, Keepa, and sourcing histories intact. Further
reductions need a separately validated history/diagnostic storage design; no
retention deletion or blanket raw-JSON removal is justified by this work.
