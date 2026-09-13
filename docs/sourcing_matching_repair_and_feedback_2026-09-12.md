# Sourcing matching repair — implementation and validation

Phases 1 and 2 are implemented and deployed, with the authenticated production UI access limitation below. Phase 3 was tested on 2026-09-13 and failed the positive-visibility safety gate; its candidate remains shadow-only. Production admission is unchanged, and Phase 3 activation and bounded refresh remain outstanding.

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


## Phase 3 — shadow candidate; safety gate failed (2026-09-13)

**Phase 3 is not complete or deployed.** Candidate commit `1b2aae1af404` is deliberately opt-in through `offline_identity_policy=phase3_shadow`; production defaults remain legacy. No runtime schedule, production row, action-time snapshot, threshold or business-hold release condition changed. The failed gate forbids deployment/refresh. This is a resumable shadow checkpoint, not an activated repair.

### Candidate implementation and boundaries

The existing identity entry point now supports a shadow evaluation with general full product-name extraction, contextual Arabic/Roman/ordinal/decimal tokens, explicit edition/package qualifiers and independently parsed eBay sources. It retains New in product names, Rare Replay, Awakening and Track Pack themes. Unknown does not default to Standard, Complete or installment 1. Exact-ASIN seed/catalog checks reject mismatched catalog and seed references. A bounded in-process reference cache keys ASIN plus actual title/system/catalog content; persistent cross-run reference/correction ingestion is not yet activated.

The candidate static scorer routes title, Game Name, numeric and edition checks through the same evaluated comparisons. Existing platform/cross-generation, location (including Canada), condition, pricing/Best Offer and lifecycle rules remain. Shadow traces now distinguish matching Review from genuine profitability failures, using recorded business checks. All three Phase 2 tabs, shared controls and query projections are unchanged. No related-ASIN, wholesale or eBay-first discovery was added.

Explicit v3 review application is tested offline: exact variation identifiers, evaluation cutoff, latest verdict including Unsure, field-only actions independent of verdict, per-field correction supersession, pair versus explicit Amazon-ASIN scope, original/source provenance, unchanged action-linked snapshots, changed images/text and newer/undated negative memory. Confirm Match cannot clear business rules or lifecycle holds. Legacy v3 snapshots do not preserve the full reviewed Amazon catalog context; catalog-bearing corrections/confirmations conservatively require re-review until that provenance can be reconciled. Live review ingestion remains disabled behind the failed gate. No explicit v3 actions existed at the initial current capture; subsequent actions in the final readback were inventory snoozes, not v3 confirmations.

### Data, coverage and correctness

Reused and hash-verified the Phase 1 1,000-dismissal cohort, newest 250, action snapshots and 5,356 positive candidates. No repeat dismissal audit or provider search. Positive source tiers remain workflow/memory candidates, not purchase-status ground truth: 2,520 distinct complete-title pairs could be replayed; 658 source records lack Amazon titles, 1,475 lack eBay titles, and 2,269 lack an exact listing ID. Those counts overlap. The title-only candidate replay is not certified positive-match accuracy. NERF ASIN B099JP9NQZ was reconciled between frozen purchase reference metadata and the same purchase item's correct-item receiving evidence. Dead Rising base reference B01JCV1QGE was verified in frozen seed/purchase metadata and was never replaced with Dead Rising 4.

The purposive reviewed set contains 12 real title pairs across supplied and held-out families, with 50 annotated field expectations. Eleven use full current/frozen listing sources; the NERF case is a bounded textual fixture with reconciled reference provenance. This is analyst textual validation, not physical/photo or operator certification, and not a population accuracy estimate.

| Measure | Before | Shadow after |
|---|---:|---:|
| Correct annotated field/state expectations | 16/50 (32%) | 43/50 (86%) |
| Amazon core-name coverage, frozen 1,000 | 133/1,000 | 1,000/1,000 |
| eBay core-name coverage without source conflict, frozen 1,000 | 106/1,000 | 363/1,000 |
| Amazon installment coverage | 57/1,000 | 347/1,000 |
| eBay installment coverage | 25/1,000 | 474/1,000 |
| Definitive non-matches among 4 reviewed wrong pairs | 0/4 | 2/4 |
| Reviewed wrong pairs excluded, including Review | — | 4/4 |

Coverage means an available non-conflicting field, not correctness. Full per-field/per-family coverage, source states and before/after decisions are in `tmp/sourcing-phase3/safety-summary.json` and `replay.json`. Generic extraction still retains seller/publisher tokens, treats abbreviations/omissions too aggressively, and leaves completeness/digital evidence extraction incomplete. Broad identity classification is therefore not validated.

Of 7 reviewed good pairs, **4 remain eligible, 0 recover and 3 are lost**. Three retained rows are current Buy List rows; NERF is a controlled profitable fixture. A separate populated synthetic fixture demonstrates recovery when credible Game Name establishes an omitted Deluxe edition; it is not counted as a recovered production opportunity. Exact known-good losses, all Review-based rather than new hard blocks:

| ASIN / opportunity | Cause |
|---|---|
| B000FQBPCQ / b40f3e0a-ae02-4b81-aa12-0200d5c86095 | Zelda: Twilight Princess title retains NWT, conflicting with Game Name. |
| B07RP42TMG / 664f232d-1cac-47b2-8d8d-f61e27785a58 | Ghost Recon Breakpoint retains publisher Ubisoft / Game wording. |
| B07Y686RM7 / da586db5-97c6-4f69-bf47-ef920ea8c1a5 | Roller Coaster Tycoon Classic versus abbreviated RollerCoaster Tycoon Game Name. |

Full-source Gears/Rare Replay and Castlevania/sequel are definitive non-matches. DiRT/DiRT 3 and Origins/Awakening are excluded through Review because source normalization still disagrees; they are not counted as definitive catches. Mario Kart Live Mario Set remains an unresolved operator label, not a newly explained textual mismatch or an approved recovery. Title-only test successes must not replace these full-source results.

Across the frozen 1,000, shadow verdicts are 151 match / 237 non-match / 612 needs-review versus 26 / 38 / 7 plus 929 unknown before. The newest 250 become 52 match / 46 non-match / 152 needs-review versus 4 match / 246 unknown. Controlled scorer replay shows 646 departures (460 without new hard blocks) and 5 entries on the historical dismissal inputs; these are hypothetical current evaluations, not historical rewrites or verified recoveries. The 609 current rows show 81 controlled departures (74 without new hard blocks) and 14 entries. These counts do not include fully reconciled current history/price/hold reactivation, so they cannot authorize writes.

### Current manifest and write gate

Initial API-equivalent capture: 2026-09-13T16:26:30.714Z to 2026-09-13T16:27:17.175Z, verified project `froeucjkcepuhgwisped`. Actual GET handlers used read-only Supabase requests; this is not Cognito/browser verification. Views: Buy List 37 (2 Buy Now, 30 Best Offer, 4 auction, 1 multi-unit), Closest Excluded 50 of scoped total 131, Business Excluded 2, plus 33 active suppression records. Existing bounded run/presentation windows apply.

Union contribution order: 108 open rows + 50 exact Closest Excluded + 2 Business Excluded + 449 additional rows from the latest 500 status-rejected candidates = **609 distinct rows**. Reused 245 hydrated API rows; fetched only 364 missing rows. The rejected cohort is provisional until final operator-history/eligibility screening; no rejected promotion is authorized. All before images, raw identifiers, hashes, timestamps and exact ordered view IDs are private in `row-manifest.json`, `current.json` and `current-evidence.json`. The API response capture transferred 321,195,889 bytes, primarily the existing Closest Excluded path; it was reused offline. No broad sync/backfill was run; disk I/O budget remains unavailable.

The proposed identity filter would remove 24 of the captured 37 Buy List rows, retain 13 in the existing order, and flag 49/50 Closest Excluded and 1/2 Business Excluded rows as not positively admitted. This is not a recomputed approved API membership/ranking: every affected row's reason/comparison is retained for reconciliation. No candidate was silently promoted.

At 2026-09-13T16:38:55.528555+00:00, a metadata-only readback checked all 609 rows: **11 changed since capture**, with **9 subsequent inventory-snooze actions**. The one initially protected inventory-snoozed row remained unchanged. Zero write attempts, zero refresh writes, zero actual write-skips (nothing was attempted), zero historical/action snapshot mutations. The manifest is stale for future writes. A later refresh must recapture/reconcile operator activity and use an atomic stale-state check; the legacy reprocess scripts are not approved to apply this candidate directly. Full current routing reconciliation and the guarded write path remain outstanding because the identity safety gate failed first.

### Verification and runtime

156 Python tests passed (125 sourcing, 21 identity, 10 feedback); 16 Phase 3 tests also passed in the locally built scheduler image with Docker networking disabled. Python compile checks, focused lint and Next.js production build/type checks passed. Actual API/Business Excluded/dialog/retry regression tests passed. 120 Python → actual API adapter → actual UI indicator checks passed, with real panel rendering. The existing production-default static output is exactly unchanged on all 1,000 frozen replays. Passing unit tests is not a passing safety gate.

Offline screenshots `tmp/sourcing-phase3/B000QL0T36.png` and `B000FQBPCQ.png` were inspected; they show honest unknowns/Review and source evidence. Photos are omitted. Browser inventory returned no apps/browsers; authenticated production UI remains unverified. No redirect is treated as feature proof.

AWS readback: web task 144, source 17a49ed94cb4, digest sha256:3f10ad423897c16e9b22d96c92db7293cfda2eb25e4d485964745bd244a6e5e5, rollout COMPLETED, one running task. Sourcing schedule still targets scheduler 92, source 92674f8cb8f0, digest sha256:0545ef77294d675a7315246b8d8f3be57f94c5e369049a5439585a94fa5c1019. All 20 schedule configurations are unchanged from the Phase 2 readback. Phase 3 was not deployed; the local test image is not a production revision. No schema/migration changes or provider/marketplace calls/writes were made.

Resume **Phase 3 only** from the handoff. Fix source reconciliation/general extraction, retain these positive counterexamples, validate the complete current routing and feedback provenance, and rerun the full safety gate before activation or an idempotent bounded refresh. Do not weaken guards or replace held-out examples to pass. Manifest: `docs/sourcing_phase3_manifest_2026-09-13.json`.


## Subsequent UI-only work order (2026-09-13)

The inline field-correction / Incorrect Match refinement is deployed as web145, source ac617406851d. Scheduler92, schedules, production matching/scoring and the failed Phase 3 gate remain unchanged. No bounded refresh or provider run occurred. See [the UI task report](sourcing_incorrect_match_review_2026-09-13.md) for transaction tests, frozen populated routing/scoring preservation, actual component screenshots, deployment isolation and the continuing authenticated UI verification gap. Phase 3 remains shadow-only and its safety gate is still failed.
