# September 8, 2026 sourcing release

The operator authorized SQL application, documentation of all uncommitted work,
commit, push, and deployment. This release includes every pending repository
change, including work predating declined-offer suppression.

## Included changes

1. Declined buyer offers: read-only eBay import; compact service-only evidence
   table/RPC; amount-aware API suppression for open/Watch/prior-run opportunities;
   scoring and duplicate-ASIN selection; both reprocessing entrypoints; bounded
   price-only projection for duplicate checks; existing scheduler group integration;
   importer/API/scoring tests. See `DECLINED_EBAY_OFFERS_2026-09-08.md`.
2. Earlier item-only Best Offer rule: search prefilter now reserves full known
   shipping before accepting the minimum item offer; scorer comment and regression
   tests document the existing final calculation. See
   `BEST_OFFER_ITEM_ONLY_RULE_2026-09-07.md`. The earlier 109-row production check
   found no invalid opportunities requiring cost corrections.
3. Earlier sourcing stability investigation: `sourcing_status_review_2026-09-08.md`
   records the successful nightly run, continued disk pressure monitoring, and
   outstanding quota/error reporting discrepancies. These discrepancies are
   documented, not silently represented as fixed by this release.
4. Operator's AGENTS.md change removes a separate explicit-SQL-approval condition
   and requires non-destructive commands. `docs/CODEX_WORKFLOW.md` is aligned.
   Target verification, exact SQL visibility, shared-ledger reconciliation and
   the documented workflow remain required.
5. `docs/business_rules.md` documents both offer rules. The web deployment helper
   accepts an explicit immutable `-ZfiPurchaseTaskDefinition` so ZFI on-demand
   purchase refresh runs the same new offer-import code as scheduled purchases.

No eBay offers are submitted or modified. Purchase/COGS data, ZFI contract
semantics, scheduler cadence, and unrelated operational jobs are unchanged.

Release review caught a stream-consumption defect in the initial decline lookup:
it exhausted the scorer's generator before scoring. The three schedule targets
were restored immediately to their captured prior revisions. The corrected
implementation fetches decline evidence and scores in batches of 100, preserving
the existing bounded-memory design. A 205-candidate generator regression checks
all candidates are scored in 100/100/5 batches. Revision 85 is superseded by the
corrected release and must not be used for catalog scoring.

## Activation evidence

- AWS account verified: `297464765814`, `us-west-2`, profile `mbop-admin`.
- Supabase project verified: `froeucjkcepuhgwisped`.
- All fourteen preexisting shared migrations matched before SQL application.
- `20260908000000_mbop_declined_buying_offers.sql` applied successfully; all
  fifteen local/remote migration entries now match. CLI catalog-cache export
  emitted a missing pg-delta certificate warning after SQL success; the follow-up
  migration ledger check confirmed application. No migration repair was needed.
- First production import wrote evidence for 35 declined listings out of 95
  returned offers (30 countered, 26 expired, 4 pending). The live feed changes over
  time; earlier preflight returned 36 declines. No absent decline is invented.
- Rollback configuration saved for all 20 schedules, web task 136, scheduler task
  84, and current web service in Git-ignored
  `logs/diagnostics/declined-offers-release-20260908/`.
- Release source tests: 102 sourcing tests, 7 importer/stream tests, 5 scheduler
  diagnostics tests; Node declined-offer and blocked-ASIN tests passed.
- Local web production build passed during implementation. Deployment smoke
  results and immutable task revisions are recorded below.

## Deployed revisions

- Implementation: `ccee005a8ce4`; streamed-scoring correction/release source:
  `11dfabd0a41c`, both pushed to origin/main.
- Scheduler: `mbop-scheduler-task:86`, image digest
  `sha256:13d2d19ad82042be59f7666d1d465429f7a4a1abdcdf68b91ec62395a7a49a06`.
- Web: `mbop-web-task:138`, image digest
  `sha256:85313930cc92ba7f1108b4c5a1801e0d74b2c2944a5b607e45c340fdd6b50e2d`.
- `MBOP_ZFI_PURCHASE_TASK_DEFINITION=mbop-scheduler-task:86` verified in the
  production web task. Existing ZFI authenticated read returned HTTP 200.
- Corrected scheduler smoke task `7ecf09d30db34d64a3a1e5a3b994eec7` exited 0:
  both job-group lists correct, 36 declined listings imported, and two real
  candidates scored successfully in a one-seed dry run. No scoring writes.
- Evidence retained after imports: 36 listings. RLS enabled; anon/authenticated
  read privileges and anon RPC execution are false; service-role read is true.
- All 20 schedules verified after activation: only the three intended task
  revisions changed. No schedule cadence or network access was changed.
- Web rollout reached `COMPLETED` with one running task, zero pending, and a
  healthy ALB target. The prior web task was drained normally.

The open Best Offer smoke scope currently returns an empty queue because existing
eligibility rules already cover its 69 stored open rows: 65 active sales-velocity
suppressions, two blocked ASINs, and two ended listings. This was investigated
using a bounded production aggregate rather than treating an empty response as
proof of decline suppression. Watch is used for the non-empty API smoke.

Watch API smoke task `2b69f0e6f6854f3ca63c1639f94970d5`, production image/task
revision 138, returned HTTP 200 and 33 opportunities against 36 retained
decline records. Zero returned opportunities had a recommended item offer at
or below their listing's declined amount. Reported build was `11dfabd0a41c`.

Browser automation reported no available browser, so an authenticated visual
check cannot be claimed. The public sourcing URL still returns a Cognito login
redirect. A separate Fargate task runs the same compiled production web image
and production configuration to smoke-test the API; this is not a local dev
server and does not replace the unavailable Cognito/browser workflow check.

Outstanding issues remain as documented in the sourcing log review: disk
headroom, quota-counter discrepancies, and availability success classification.
Image dependency installation also reported five npm vulnerability findings
(one moderate, three high, one critical); the existing lockfile was unchanged
and dependency remediation is separate work.

## Activation scope / rollback

Deploy the scheduler and move only `mbop-sourcing-catalog` and the two
`mbop-purchase-ingestion-*` schedules to the new revision, preserving every
other schedule field. Pin ZFI refresh to that same revision when deploying web.
Run a bounded ECS offer import smoke rather than a full catalog scan; verify
CloudWatch exit status, table evidence, and deployed application behavior.

Rollback restores the saved web task and three affected schedule targets. Keep
the additive migration/evidence table; older images ignore it. Do not roll back
purchase data or reset historical costs.
