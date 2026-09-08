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
- Release source tests: 102 sourcing tests, 6 importer tests, 5 scheduler
  diagnostics tests; Node declined-offer and blocked-ASIN tests passed.
- Local web production build passed during implementation. Deployment smoke
  results and immutable task revisions will be recorded after rollout.

## Activation scope / rollback

Deploy the scheduler and move only `mbop-sourcing-catalog` and the two
`mbop-purchase-ingestion-*` schedules to the new revision, preserving every
other schedule field. Pin ZFI refresh to that same revision when deploying web.
Run a bounded ECS offer import smoke rather than a full catalog scan; verify
CloudWatch exit status, table evidence, and deployed application behavior.

Rollback restores the saved web task and three affected schedule targets. Keep
the additive migration/evidence table; older images ignore it. Do not roll back
purchase data or reset historical costs.
