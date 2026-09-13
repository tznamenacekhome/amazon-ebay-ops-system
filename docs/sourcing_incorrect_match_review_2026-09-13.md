# Incorrect Match and inline row corrections — 2026-09-13

The shared single-record review dialog now supports checking a field, editing either marketplace value, and saving **Incorrect Match** in one action. This is a UI/feedback-capture change. **Phase 3 remains shadow-only and its safety gate is still failed.** The Zelda, Ghost Recon, and Roller Coaster Tycoon counterexamples and stale 609-row manifest remain untouched.

## Behavior and implementation

- `web/app/sourcing/page.tsx`: Buy List, Closest Excluded, Business Excluded, and exactly-one-selected-row all open the same dialog. Single-row Wrong Platform and Wrong Edition / Version buttons are removed; historical/bulk reasons stay readable. Selecting a reason writes nothing. Incorrect Match uses the existing `dismiss` transaction. Confirm Match explicitly supplies `correct`; Save feedback defaults to `not_provided` (leave prior verdict unchanged), while deliberate Not Sure is `unsure`. Errors preserve the dialog and edits. Existing retry IDs and bulk behavior are retained.
- `MatchingReviewControls.tsx` and `reviewFields.ts`: one Field / Amazon / eBay / Wrong table, read-only until checked; per-side edits, explicit Unknown/known absent/not applicable, per-row undo, confirmation before discarding checked-row edits, saved operator overlays, and original parser/source details. Amazon ASIN scope requires explicit selection for each new correction; eBay remains exact pair/variation. No parser runs or comparison admission recalculation occur in React. Recorded evaluation and corrections are clearly separated.
- Original titles remain copyable, source specifics/descriptions are collapsible, and the dialog has no photos, image counts, second correction form, or duplicate matching-summary grid. Existing photo/seller reason and evidence controls remain. Recorded numeric tokens assigned to platform/year/quantity are labeled separately from ignored/unclassified wording; missing token records say unavailable.
- Canonical editable fields are coreGame, installment, generation, theme, platform, edition, region, packageType, completeness and digitalPhysical. These are the existing correction/identity contract. Condition, identifier and year have no separate typed correction fields in this contract; source specifics remain available rather than inventing new identity defaults/schema.
- `matchingFeedback.ts` and `reviewActions.ts`: v3 keeps the verdict, flagged canonical fields, all flagged rule families, actual per-side changes, previous effective values/states/action provenance, optional selected reason context, and original evaluation/source snapshot separately. No truncation of corrected product names. A one-pair latest-review read resolves previous operator overlays before save and detects changed opening corrections. The existing atomic RPC still owns action/snapshot/example and dismissal writes. No migration was necessary.

Legacy negative reason mapping: platform-only -> `wrong_platform`; edition-only -> `wrong_edition_version`; core, multiple, or unspecified components -> `wrong_product`. The explicit negative action supplies the pair judgment; a checkbox alone does not. `failureClassification` records operator-reported field errors separately from `pair_non_match_without_component`, with pipeline stage `unspecified`. Optional selected business/condition/seller reason is retained separately from the negative identity reason. No v3 admission ingestion or generalized exclusions are activated.

## Saved example and verification

The actual Prey component test checks Core Game, pastes Amazon `Prey` and eBay `IL-2 Sturmovik Birds of Prey`, then clicks Incorrect Match. Its emitted payload passes through the actual action route, disposable PostgreSQL transaction, latest-review lookup, and Python analyzer. The original eBay source title and parsed `Prey` remain in the snapshot; the correction's previous state is `inferred`. The saved verdict is `incorrect`, reason `wrong_product`, flagged field `coreGame`, family `core_game_identity`. The ASIN in the synthetic fixture is a test placeholder and was never written to production.

Validation:

- 156 Python tests (125 sourcing, 21 identity-engine, 10 feedback).
- Actual dialog/row handlers: side-specific paste, unchanged fields, checked-without-replacement feedback, undo/discard confirmation, explicit states, negative with/without edits, positive with corrections, correction-only/unsure, saved overlays, stale/error retention, legacy reasons, single-row entry paths, and actual bulk callbacks.
- Actual API -> disposable PostgreSQL -> reload -> Python analyzer: combined negative/corrections, positive/corrections, original source/evaluation, verdict preservation on field-only save, correction supersession isolation, exact variation vs explicit Amazon ASIN scope, request retries/fingerprint conflict, auth/stale pair/evaluation, failed-label rollback, protected purchase and unchanged active velocity/ASIN holds. A confirmation does not reopen a dismissed opportunity.
- Existing Business Excluded qualification/hydration, blocked-ASIN buying guards, retry IDs, diagnostic adapter, and 120 Python/API/UI comparison checks pass.
- Frozen full static/scorer comparison against production scheduler source `92674f8cb8f0`: **1,609 inputs, zero static or scoring differences**, excluding only generated evaluation IDs/timestamps and creation/update timestamps.
- Frozen actual API and compiled production-route replay: **37 Buy List, 50 Closest Excluded, 2 Business Excluded**; exact order, routing/scoring/presentation fields and summaries unchanged. The 33 velocity holds remain separate. This is a populated frozen cohort, not a new live eligibility audit. No provider/network requests during replay.
- Next.js production build/type check passes. Focused ESLint: zero errors, 10 unused-helper/type warnings (nine pre-existing plus the retained old diagnostic panel used by diagnostic regression tests).

Actual-component screenshots, inspected offline: `tmp/sourcing-review-ui/original.png` (pre-change dialog from commit 88adc93), `prey.png` (negative fixture with pending edits), and `valid.png` (valid pair with only Amazon corrected). Original source, unknown rows, enabled cells, provenance and actions are visible. A contrast issue found in screenshot review was fixed with explicit dialog text colors.

Private artifacts: `tmp/sourcing-review-ui/` contains screenshots/HTML, actual UI payload, full routing IDs, default-output hashes, exact-row readback, and AWS manifests. No frozen Phase 1/2/3 artifact was overwritten. The unrelated wholesale discovery document is preserved.

## Deployment isolation and limitations

Before deployment AWS reads confirmed web144 and both scheduled/on-demand sourcing target92, all 20 schedules captured. A tiny verified-project Supabase read and four exact-row/latest-review reads passed; no database writes or synthetic production feedback. Current authenticated browser inventory is empty. Offline UI and read-only Supabase/compiled API evidence are not authenticated production feature verification; no authentication redirect is counted.

The web Docker build context is `web/` and the runtime copies only the built Next.js output, public assets, startup scripts and production Node dependencies. It does not include Python integrations. Compiled server-route inspection found neither `phase3_shadow` nor `offline_identity_policy`. Web launch configuration retains CLOUD_DEPLOYMENT=true / LOCAL_SYNC_ENABLED=false; normal launch functions accept no identity-policy argument. Existing on-demand scheduler family resolves to unchanged revision92. Packaged-image checks and final deployment evidence follow below.

No scoring refresh, historical backfill, provider search, marketplace write, hold release, migration, or synthetic production review is part of this task. The stale Phase 3 manifest is not used for writes. Next matching work remains general seller-noise/source-omission reconciliation with all three good-match counterexamples and fresh stale-state validation, not a whitelist or broad relaxation.
## Reproducing the bounded tests

From the repository root, run `node web/app/sourcing/MatchingReviewControls.test.mjs`, then set `MBOP_REVIEW_TEST_CONTAINER` to a disposable PostgreSQL container loaded with `tests/fixtures/sourcing_review_schema.sql` and the applied review migration, and run `node web/app/api/sourcing/reviewActions.test.mjs`. Never point that fixture at production. The test creates only synthetic rows in that disposable container.

With the frozen private fixtures present, run `node web/app/api/sourcing/reviewRouting.test.mjs`. `tests/verify_sourcing_review_runtime.cjs` exercises the compiled production route directly; set `REVIEW_APP` to the built app directory and `REVIEW_FIXTURES` to the frozen Phase 3 directory. In Docker, mount the script and fixtures read-only and use `--network none`. `tests/verify_sourcing_review_defaults.py <integrations-directory> <output-json>` compares deterministic default static/scorer output using the frozen 1,000 + 609 inputs; run against the archived production source and current source, then compare output hashes. These commands cannot authorize Phase 3 activation.

Screenshots: [original dialog](../tmp/sourcing-review-ui/original.png), [Prey corrections](../tmp/sourcing-review-ui/prey.png), [valid-pair correction](../tmp/sourcing-review-ui/valid.png). These are actual React component renderings, with test-driven pending state, not a live authenticated browser session.

The existing production dependency install reported five audit findings (one moderate, three high, one critical); package manifests and lockfiles were unchanged by this bounded task. Dependency remediation was not folded into the UI change.


## Final deployment evidence

Completed at 2026-09-13T17:32:04Z. Runtime commits `e8a74957c18a` and `ac617406851d` are pushed. Deployed from a clean detached worktree using the normal `scripts/deploy-web.ps1` workflow; ECS/ALB readback and `scripts/aws-web-status.ps1` verify web **145**, source **ac617406851d**, one running task, zero pending, rollout **COMPLETED**, exact target **172.31.39.177 healthy**.

Pinned ECR image: `sha256:ced396963d4da7d939e659100b4e673ce98bb390b1a66304b5dc02f25856ad51`. Its runtime layers and configuration exactly match the locally tested Docker image (attestation/manifest-list identifiers differ). The actual compiled API inside that image passed the populated 37/50/2 routing replay with Docker networking disabled. No Python integrations or Phase 3 activation keys are present in the compiled web server. All web task configuration is unchanged except image/build IDs. Scheduler/on-demand target **92** and **all 20 schedules** are unchanged.

An initial deployment wrapper stopped on PowerShell's handling of Docker stderr before service changes. Capturing the unchanged deployment script's native output resolved this; only web145 was registered/rolled out for this task. No provider job was launched.

The disposable PostgreSQL container is stopped. Zero production synthetic feedback, scoring refresh, protected-row edits, history rewrites, provider calls, or marketplace mutations. All nine frozen failed-Phase-3 artifact hashes remain unchanged. Authenticated production UI is still unverified; the browser inventory returned no surfaces. See `docs/sourcing_review_ui_manifest_2026-09-13.json` for validation/deployment metadata and private artifact hashes.

This UI/feedback task is complete with the documented authentication gap. **Phase 3 remains shadow-only and its safety gate is still failed.** Stop here; do not run sourcing or refresh scores as part of this task.
