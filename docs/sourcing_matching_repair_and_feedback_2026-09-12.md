# Sourcing matching repair — Phases 1 and 2

Phases 1 and 2 are implemented and deployed, with the authenticated production UI access limitation below. Buy List admission is unchanged. Phase 3 matching repairs and bounded current-row refresh remain outstanding under the supplied work order.

## Phase 1 changes

- The existing Python identity engine now emits `evidenceDecision` and per-side `fields`. Values carry state, bounded source spans/hashes, snapshot references when available, parser/evidence versions, and labeled expectations. Unsupported Standard/Complete/Physical/base defaults are not observed values. Confidence remains explicitly an uncalibrated parser heuristic.
- The evidence view uses the existing comparator on evidenced values. Generic `Main Game`/franchise equality does not establish a positive identity verdict. Comparable conflicting source values require review; a missing counterpart remains an unknown comparison. Existing `result`, `hard_block`, recommendations, numeric/edition rules and score adjustments remain unchanged for admission.
- The existing decision trace adds `canonicalDecision`: product verdict, business eligibility/reasons, presentation decision, lifecycle status, evaluation UUID/version/time. Unknown business evidence is not a product mismatch. This is a scoring-time assessment, not an assertion that all subsequently updated holds were evaluated.
- The API adapts both new and legacy JSON. Legacy rows retain their recorded evaluation time or null, never a fabricated current evaluation. The adapter does not reparse titles or infer a fresh verdict. Required seed context is projected; mismatched/missing seed ASIN cannot supply Amazon identity/title/catalog metadata. Exact-ASIN cached Keepa title remains the existing fallback.
- The real diagnostics panel keeps unknown core/edition/installment fields visible; reads recorded comparison results for indicators; removes Country of Origin, Features and Format/Type substitutions; reconciles packageType; includes generation/theme; and uses plain collapsed descriptions, existing small thumbnails and provenance tooltips.
- The dismissal analyzer excludes duplicate cleanup, any cleanup_source key and availability/refresh provenance, adds a stable action-ID ordering and optional cutoff, includes raw feedback/action-time comparisons in JSON/CSV, labels empty feedback as unlabeled, and no longer treats mere item-specific/description presence as causal proof.
- The legacy `derived_identity` alias does not duplicate the new evidence payload. Source spans are bounded to 240 characters and three references per field; original evidence remains in the stored snapshot.

During Phase 1, no schema migration, marketplace/AI calls, feedback writes, opportunity reprocessing, admission-policy change, business-hold release, or sourcing search was performed.

## Frozen audit

Target: `amazon-ebay-ops`, Supabase `froeucjkcepuhgwisped`, MBOP public objects only. Health probe at 16:38:22 UTC: Postgres up, approximately 733 MiB available RAM, 454 MiB free swap, 1.34 GiB filesystem headroom. Disk IO Budget was not observable from that probe. Reads were bounded; no retry/backfill orchestration was launched.

Action cutoff: **2026-09-12T16:39:55.421289Z**. Filter: dismissed; exclude no_longer_available and duplicate_open_asin_opportunity, any cleanup_source key, and availability/refresh in concatenated source/actionType/job/reason. Order created_at DESC, action_id DESC. This is a provenance-filtered human-candidate cohort, not proof that every possible automation signature has been discovered.

The 1,000 candidates match the supplied audit counts: 387 wrong edition, 128 wrong product, 128 missing shrink wrap, 82 blocked ASIN, 52 velocity, 45 packaging damage, 36 incomplete, 32 region, 26 digital, 22 ROI, 22 platform, 17 reseal, 10 NFR, 6 other, 4 listing error and 3 seller/listing mismatch. The newest 250 are separately frozen. Current evidence and action-linked snapshots were found for all 1,000; 534 actions have an action-time diagnosticComparison; 507 have matchingFeedback. None of the latter explicitly marks all fields correct. Empty feedback is not negative feedback.

Private artifacts live in ignored `tmp/sourcing-phase1/`: actions.json, newest250.json, action-snapshots.json, current-evidence.json, holds.json, positive-candidates.json, settings.json, read-only-replay.json, exact-example-traces.json, api-before.json, api-after.json and the recorded GET responses. Action snapshots, action-time comparisons, current stored diagnostics and fresh read-only replay remain separate. No historical record was updated.

`manifest.json` stores the exact selection SQL, cutoff and SHA-256 hashes. The checked-in companion manifest records counts and ordered excluded IDs. Private audit files are intentionally not committed.

### Exact API scope and limits

Executed the actual opportunities GET handler with a read-only Supabase client and captured its GET responses. This is API-equivalent database evidence, **not an authenticated production HTTP/browser test**.

- Buy List: status=open, type=all, sourceMode=all, scope=all_open, limit=150; query limit 3,000. Returned **0**, API total **0**. This does not assert there are no open database records: the handler fetched 71 before existing presentation/filter gates.
- Closest Excluded: same defaults, scope=closest_excluded, limit=50; query limit 1,000. Returned **50**, scoped total **141**. The source fetch returned 877 rows.
- Existing selection uses the latest 20 completed daily_catalog_sourcing/recent_sales/full_listings runs, score/created_at source ordering, block/declined-offer/hold/history/presentation gates, exact-listing deduplication, then descending nearMissRank. Buy List uses its existing ASIN-priority grouping. The 50 IDs/order in the manifest are the displayed selection, not an unrelated latest-500 sample.
- Totals are within these existing bounded API windows, not a full-history census. Related presentation lookup has an existing 5,000-row cap. The capture spans several minutes rather than one database transaction. Before/after comparisons use the identical frozen responses, eliminating later user activity as a comparison confounder.
- Existing GET response bodies were approximately 333 MB in the private fixture file (including raw stored payloads). Replays are offline. This exposes existing read amplification; do not repeatedly recapture the entire fixture to verify UI-only changes.

### Positive evidence reconciliation

5,356 positive_identity-labeled records were captured without hitting the 10,000 cap:

| Existing source | Records | Interpretation for later policy validation |
|---|---:|---|
| purchase_items / verified_purchase_item | 3,460 | Workflow evidence; label name alone is not exact-pair confirmation |
| sourcing_purchase_matches | 828 | Purchase linkage, not independent identity verification |
| sourcing_actions / purchased | 632 | Operator purchasing intent; all 632 feedback objects have allAssumptionsCorrect=false |
| receiving outcomes | 421 | Receiving evidence requiring reconciliation of exact listing/product |
| manual_item_matches | 15 | Title/system/ASIN memory; no exact listing ID in these records |

3,087 records contain an ASIN/listing pair, representing 1,995 distinct raw identifier pairs; 2,269 lack an exact listing ID. No explicit exact-pair identity confirmation or all-fields-correct confirmation was found in this captured positive-label cohort. These records remain useful safety-review candidates, not newly certified ground truth. Do not reuse the older 2,353 “authoritative positives” headline without source reconciliation. Exact-pair identity, field accuracy and buy eligibility remain separate; Phase 2 will add explicit shared feedback.

### Four exact examples

All have their action-linked snapshot and action-time comparison preserved. `exact-example-traces.json` links action/snapshot IDs, current API fields, read-only replay fields and offline HTML rendering.

| ASIN | Exact opportunity | Observed Phase 1 result |
|---|---|---|
| B00ZMBLKPG | c3f0249f-8e52-45bd-81aa-005a5d56fafd | Gears Ultimate vs Ultimate/Rare Replay: core/edition unknown remain visible; no fabricated base/standard assertion |
| B000QL0T36 | 919606c5-9527-45a6-93aa-c4cf49ec4b0d | Dirt vs DiRT 3: installment/core unknown; platform comparison remains the stored match |
| B001IK1BJ0 | 7078668d-09aa-4b83-9302-69ad454200f5 | Origins vs Awakening: unknown remains explicit; no Phase 1 expansion/admission rule added |
| B08H9KGMWK | c2a7158e-30fa-40f7-acdb-c25a210edafa | Mario Set title agreement is not treated as proof of the operator's unstated mismatch reason |

The current parser's evidence verdict is unknown for all four; exposing this limitation is intentional. Resolving the product rules belongs to Phase 3.

## Verification

- 1,000 frozen current-evidence replays: **zero changes to any legacy static scoring output**, after stripping only new observational keys.
- Actual GET handler against frozen responses: exact ordered IDs and summaries unchanged for both scopes. Buy List preservation is vacuous on the empty current sample; nonempty identity/admission regression fixtures also pass.
- 21 existing identity tests, 4 existing decision-trace tests and 7 new evidence/provenance tests pass (32 Python tests). Node tests exercise the actual API adapter and render the actual panel/helper functions, including nulls, legacy defaults, canonical indicators and ASIN changes.
- Local Next.js production build/type check passed. Deployment image build is a separate verification step.
- Offline exact-example HTML artifacts and four Chrome screenshots are under tmp/sourcing-phase1. All four were visually inspected: required unknown rows present, platform comparison consistent, plain collapsed description, no raw developer output. External photos were omitted from these offline test artifacts; the application's existing thumbnail rendering remains. Screenshots are fixture rendering, not authenticated production UI proof.
- CUA exposed no available browser; an in-app browser creation attempt failed. Authenticated production UI remains unverified. No Cognito redirect is being counted as verification.

## Deployment

Verified at **2026-09-12 16:57 UTC**, account 297464765814, us-west-2:

| Consumer | Runtime source commit | Active revision | Image digest |
|---|---|---|---|
| Web | 32c3e5638a2b | mbop-web-task:139 (previous 138) | sha256:c48f32c09ddff8fafedf32b71642c55be63a9ab802376012527c0707a2c0b72f |
| Sourcing scheduler | 6f2ccb74cee8 | mbop-scheduler-task:91 (previous 90) | sha256:2cfead5e99ee699375e75a2dcd8195f8c3f685618d2a1a7ca33ce8d6a9bef2ab |

Both runtime commits are pushed to origin/main. The second commit changes only Python evidence comparison handling and its regression test; web code remains identical. Both Docker builds passed. The scheduler image additionally passed a packaged evidence-contract check with Docker networking disabled.

Web rollout is COMPLETED with one running revision-139 task and a healthy ALB target; the prior target was draining during readback. All 20 schedules were compared semantically: only mbop-sourcing-catalog changed its TaskDefinition, 90 -> 91. Cadence, timezone, overrides, IAM, networking and other target properties are identical. Scheduler/web task settings are identical apart from expected image/build identifiers. Web service networking, load balancers, desired count, capacity strategy and deployment configuration are preserved. Manual sourcing launch uses the scheduler family default, whose new revision is 91.

Private AWS readbacks/proof: aws-before.json, aws-after.json, aws-verification.json. Dirty image-tag suffixes reflect only the unrelated wholesale discovery document, which is outside the web build context and scheduler COPY paths; it was neither committed nor deployed. No sourcing job was triggered. Authenticated production UI remains the explicitly documented verification gap.

## Phase 1 handoff (historical)

Continue from `docs/sourcing_matching_repair_and_feedback_handoff.md`. Phase 2 owns Buy List/Business Excluded tabs and shared feedback. Phase 3 alone owns policy changes and gated current-row reprocessing.

## Phase 2 implementation (2026-09-12)

Buy List retains the existing scopes, ordering and buying controls. Closest Excluded retains its near-miss selection and default 50; shared review actions now remove actioned exact pairs through the existing unreviewed mechanism. Business Excluded accepts only canonical positive identity using the exact ASIN metadata, or the latest explicit exact-pair positive, plus a recorded failed business check or active hold. Unknown/negative identities do not qualify. Active velocity suppression records remain visible separately, including records without any qualifying listing. Other tabs retain their workflows.

Business reasons use structured outcomes from the existing scorer's classify/offer functions, active velocity/blocked-ASIN records, recorded inventory/price-improvement holds, and stored ended-listing checks. They do not infer a positive identity or an exclusion from a warning string. Legacy rows without a supported business evaluation remain unavailable rather than receiving invented thresholds. Historical hold/velocity inputs carry timestamps or explicit unavailable/stale explanations. An allowed Best Offer/auction scenario does not fail solely on asking-price ROI. No numeric threshold changed.

The shared dialog separates pair verdict, displayed-field feedback, explicitly used evidence, photo clues, notes and scoped corrections. Choosing a reason does not save; explicit Dismiss, Confirm Match or Save feedback submits. Cancel writes nothing; errors remain visible in the dialog. Confirm Match does not assert that all fields are correct. Correct Details keeps original snapshot values and corrections separately; eBay corrections stay pair-scoped, while Amazon ASIN scope requires explicit selection. Reload retrieves the latest pair verdict and latest corrections by field/side/scope, including explicitly ASIN-scoped corrections on sibling listings without propagating a pair verdict.

`matching_feedback_v3` records pair verdict, corrections, failed rule families, explicit evidence provenance and available evidence separately. Legacy normalization remains v2/legacy_mixed. The action also records exact opportunity/candidate/ASIN/item/variation, source tab, actor, request ID/fingerprint, build, evaluator identity/time and snapshot ID. Raw/stored action aliases are accepted by the unreviewed filter. Confirm Exclusion requires a real reason; it no longer defaults to wrong-product evidence. Empty/unsure feedback remains unlabeled; business reasons are not identity negatives. Seller/photo reasons retain exact-pair scope. All new review evidence is withheld from automatic admission until Phase 3 validation; this also prevents confirmations from silently promoting listings or clearing business holds.

Migration `20260912171310_mbop_atomic_sourcing_review.sql` adds a service-role-only SECURITY INVOKER transaction and bounded latest-review lookup. An action, snapshot, intelligence example and applicable status/hold writes commit together or roll back together. Stable request IDs serialize retries; mismatched retries and stale ASIN/candidate/item/evaluation saves fail. Protected purchased/completed lifecycle rows are not overwritten. Existing suppressions are not reset or released by feedback. No historical actions are rewritten. The snapshot check expands without scanning historical raw snapshots; the new partial index covers sourcing actions only.

Validation so far: 109 sourcing Python tests plus 10 feedback tests; actual TypeScript adapter/panel and blocked-ASIN API tests; actual shared-dialog handler tests; actual action API through disposable PostgreSQL and latest-review reload (authorization, stale pair, blocked-ASIN positive, correction scope, uncertain verdict, duplicate retries, failed-label rollback and protected purchase). Production build passes. Focused lint has no errors and nine existing unused-helper/type warnings. Frozen API replay preserves exact ordered IDs and summaries: Buy List 0/0; Closest Excluded 50/141. Offline actual-dialog rendering is under ignored `tmp/sourcing-phase2`; it is not an authenticated production UI check.

Database preflight: target froeucjkcepuhgwisped verified; tiny read passed; database 6,417,230,995 bytes and sourcing_actions 11,886,592 bytes. Capacity warning given. Complete shared ledger has 16 applied migrations reconciled; dry-run contains only the new MBOP migration. Deployment and final ledger readback will be recorded below. No sourcing/provider job or production synthetic review has been run.

Live API verification found unnecessary raw-payload transfer during Business Excluded qualification. The final query selects only stored verdicts, business checks and hold inputs, then hydrates full evidence by qualifying opportunity IDs. Buy List and Closest Excluded queries are unchanged. Actual GET contract tests cover positive-row hydration and unknown-row non-hydration. Identical live results (0 matched exclusions in the bounded scope, 33 active suppression records) required 114,602,897 bytes / 12,404 ms before narrowing versus 3,246,708 bytes / 2,253 ms afterward, both 23 reads. This is about 97% less transfer for this observed workload, not a guaranteed billing reduction or universal latency benchmark. Private readback: `tmp/sourcing-phase2/live-api.json`; no production row was mutated by these checks.


## Phase 2 final deployment

Verified 2026-09-12T17:54:23.639224+00:00: web task 144, runtime source 17a49ed94cb4, image sha256:3f10ad423897c16e9b22d96c92db7293cfda2eb25e4d485964745bd244a6e5e5; rollout COMPLETED, one running task, zero pending and its exact private-IP ALB target healthy. Scheduler task 92 uses source 92674f8cb8f0 and image sha256:0545ef77294d675a7315246b8d8f3be57f94c5e369049a5439585a94fa5c1019. Its actual mbop-sourcing-catalog target is revision 92. All 20 schedules and task/service settings were compared: only the intended sourcing TaskDefinition changed (91 -> 92), apart from expected image/build identifiers. Runtime commits are pushed. Earlier web revisions 140/141/142/143 were superseded by 144.

The MBOP migration is applied and all 17 shared ledger entries match. Live permission checks confirm both functions are SECURITY INVOKER and service-role-only. Final live API-equivalent read returned HTTP 200, 0 supported excluded pairs in its bounded scope and the same 33 holds, transferring 3,246,708 bytes in 2.355 seconds. Actual persisted API reviews also passed through the Python analyzer with distinct positive, negative, unsure and correction evidence. The local test container was stopped after testing.

Offline actual UI screenshots for Buy List, Closest Excluded, Business Excluded and the shared review dialog were inspected under tmp/sourcing-phase2. Tab order, shared controls and suppression records render correctly; photos are omitted and local asset limitations are explicit. Browser inventory remains empty, so these are test screenshots, not authenticated production UI verification. No provider search, production synthetic review, business override or historical reprocessing was run. The unrelated wholesale discovery document remains untouched.

Phase 2 is complete with the documented browser-access gap. Phase 3 matching repairs and gated bounded current-row refresh remain outstanding. Continue using the handoff; stop this session. Deployment manifest: sourcing_phase2_manifest_2026-09-12.json.
