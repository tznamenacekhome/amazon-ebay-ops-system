# Manual Flipmine sourcing

Opportunities has an **Import Flipmine** button. Export each batch to a new tab
of the configured Google Sheet. The import reads every unprocessed numeric tab
ID, validates required ASIN/eBay Item ID columns, and stores a durable row ledger.
Blank rows are ignored; malformed rows remain audited. Source titles and prices
are untrusted evidence, never matched identity or purchase economics.

## Architecture and evaluation

The authenticated Next.js POST claims one database lease and launches the existing
on-demand ECS scheduler task with `python integrations/import_flipmine.py --run-id
<uuid>`. There is no EventBridge schedule, Google polling, new service, or separate
opportunity workflow. The browser polls MBOP status only while evaluating.

`flipmine_sheet.py` uses existing gspread/service-account authentication with
the Sheets **read-only** scope. `flipmine_context.py` bounds the ordinary seed
builders to the proposed ASIN, uses fresh existing New-condition restrictions,
catalog and Keepa evidence, and refreshes stale/missing evidence using existing
read APIs. Catalog/Keepa discovery-only ASINs use the normal seed finalizer.
Keepa requests check the token budget and print the existing plan summary first.

`import_flipmine.py` fetches current eBay US detail by legacy ID using Browse
`/buy/browse/v1/item/get_item_by_legacy_id`, checks returned identity and normal
availability, and reuses `map_item` and `score_candidate_batches`. The ordinary
matcher, seller/history/declined-offer intelligence, phase-3 scoped reviews,
profit/ROI, inventory, velocity, restrictions, offer/bid and hold rules own the
decision. Export titles/prices never enter these calculations. Unknown shipping
remains unknown. A parent variation is retained as failed/reviewable, not guessed.

Hard-rule failures are audited exclusions, without opportunity insertion, matching
the normal Browse discovery rejection policy. Other evaluated decisions use the
existing opportunity table. Existing duplicate-ASIN cleanup and initial snapshots
are reused. Both Buy List and Closest Excluded use the original backend gates,
global deduplication/ranking, and source membership from the import ledger. A
compact FM badge appears inside their shared Opportunity cell; original source
tags are retained.

## Schema, concurrency and retries

Migration: `supabase/migrations/20261124022809_mbop_flipmine_sourcing_import.sql`.
It changes candidate uniqueness to `(ebay_item_id, asin)` as approved, updates the
normal writer's conflict target, adds source tags and three private audit tables:
`sourcing_flipmine_runs`, `sourcing_flipmine_tabs`, `sourcing_flipmine_rows`.
RLS and explicit service-role-only grants protect the ledger and RPCs. Lookup
indexes cover row references and existing opportunity pair reuse.

Spreadsheet ID + numeric sheet ID is the stable tab identity. Completed tabs are
skipped even after renaming. The first successfully parsed snapshot is immutable:
retries use retained row evidence; later exports belong on a new tab. Retained
incomplete tabs are retried even if removed from Google after snapshotting.

Candidate binding and opportunity insertion/row acknowledgement are transactional.
Repeated rows/tabs reuse the same candidate/opportunity pair. Different proposed
ASINs retain separate candidates. An already evaluated pair gains provenance only;
its operator status, holds and evaluation are preserved. Missing evaluation remains
an explicit retry/review error. Source import never promotes a dismissed/held row.

One global launch lease prevents duplicate workers. Heartbeats renew it; after
90 minutes without a heartbeat a new manual import can recover the retained tabs.
RPCs fence expired workers. Provider/row failures remain failed and retryable;
other safe rows/tabs continue. A partial import is never reported as complete.
Unavailable/ended listings are terminal exclusions, not successful buy candidates.

After evaluation, a tab is `evaluated`, not completed. The status API counts its
surviving results through the real Opportunities GET for both views, after global
deduplication. Only successful presentation checks can complete the tab/run.
Unavailable counts remain pending and retry on status refresh. Closing the browser
does not lose evaluation; reopening Opportunities resumes these presentation checks.
An already-completed source produces a successful **Nothing new to import** result.

## Configuration and safe verification

Server worker environment only:

- `FLIPMINE_GOOGLE_SHEET_ID`: configured sheet ID; never a `NEXT_PUBLIC_` variable.
- Existing `GOOGLE_APPLICATION_CREDENTIALS` (or `GOOGLE_SERVICE_ACCOUNT_FILE`).
- Cloud entrypoint already materializes `GOOGLE_APPLICATION_CREDENTIALS_JSON`
  from the existing Secrets Manager credential. No new Google key is needed.
- Existing Amazon, eBay, Keepa, Supabase and sourcing configuration remains in use.

Share the sheet **as Viewer** with the existing MBOP Google service account.
The source remains read-only; MBOP does not modify tabs, cells or sharing.

`python integrations/import_flipmine.py --plan` reads the configured source and
prints tab IDs/names/counts only. It does not evaluate providers or write the DB.
An actual import must be started explicitly in MBOP. Each tab is bounded to 10,000
data rows / 100 columns. Global source presentation currently fails visibly above
10,000 linked rows rather than silently truncating results. Split oversized grids
before first import. Logs redact credentials/tokens and include run/tab/row IDs;
the database ledger retains original source evidence and evaluation/error details.

The production database was about 16.7 GiB at preflight, with 13.6 GiB filesystem
headroom; capacity metrics and a tiny read passed. Imports retain the ordinary
database-pressure guard at startup and every 20 rows. Broad imports still consume
database IO and existing Keepa tokens; no full live import is part of release tests.

## Validation and release

- Python parsing/orchestration/evaluator fixtures: `python -m unittest discover
  -s tests -p 'test_flipmine*.py'` (PostgreSQL cases skip in discovery).
- Explicit disposable database: `python tests/test_flipmine_postgres.py`.
  Starts `postgres:17` with no published port and removes it afterward.
- Existing sourcing: `python -m unittest discover -s tests -p 'test_sourcing*.py'`;
  existing Browse: pattern `test_ebay_sourcing*.py`.
- Web: TypeScript, production build, actual Opportunities GET regression suite,
  `flipmine/route.test.mjs`, `flipmine/presentation.test.mjs`, and
  `FlipmineSourceBadge.test.mjs`.

Release test checkpoint: 28 Flipmine Python fixture tests, 8 explicit disposable
PostgreSQL cases, 188 sourcing tests, 17 Browse tests, and 15 wholesale seed tests.
TypeScript, targeted ESLint, four web regression scripts and the network-enabled
Next.js production build passed. The first sandboxed build could not fetch existing
Google fonts; the normal network-enabled build passed without changing fonts.

Before deployment reconcile the complete shared migration history with
`supabase migration list --linked`, then apply the exact committed migration using
`supabase db push --linked`. Do not edit already-applied migrations. Deploy the
scheduler image before the web image so the manual command exists. The scheduler
deploy script accepts `-FlipmineGoogleSheetId`. Retarget only the existing
`mbop-sourcing-catalog` schedule to the compatible writer revision, preserving
its command, timing and state; no Flipmine schedule is created.
The current web task uses the unpinned scheduler family, resolving its latest
registered revision for on-demand imports. Use `scripts/deploy-web.ps1` and
`scripts/aws-web-status.ps1`, then check the Cognito-protected production browser.

Production verification: open Sourcing, confirm the button, explicitly import a
new tab, wait for evaluation and presentation completion, inspect Buy List and
Closest Excluded FM badges/counts, then import again and confirm no duplicates /
nothing new. For a partial run inspect retained row errors, resolve the provider
issue, retry manually, and verify the same tab and candidate/opportunity IDs.
Do not use localhost or unauthenticated shell HTTP as proof of production UI.

Rollback web/scheduler images together. Keep the additive audit schema and pair
key in place; old scheduler images using the previous single-key upsert are not
compatible with the new pair constraint and must not be launched after migration.
