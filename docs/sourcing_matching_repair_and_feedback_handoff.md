# Sourcing matching repair handoff

Phases 1 and 2 are complete and deployed, with the authenticated production UI access gap documented below. Stop after Phase 2 this session. Next session starts Phase 3 of the original work order in C:\Users\timz\Downloads\MBOP_Codex_Sourcing_Matching_Repair_Buy_List_Business_Excluded.md.

Read the original work order and docs/sourcing_matching_repair_and_feedback_2026-09-12.md. Do not repeat the Phase 1 audit. Phase 3 owns matching heuristics, positive safety gates and bounded reprocessing. No sourcing/provider job or production synthetic review ran in Phase 2.

## Implemented contract

- Canonical parser/evidence contract remains video_game_identity.py and sourcing_decision_trace.py. Identity admission thresholds remain unchanged.
- Buy List preserves existing scopes/order/buying controls. Closest Excluded preserves default 50, ranking and never-presented scope. Reviewed exact pairs leave its unreviewed view.
- Business Excluded requires exact-ASIN canonical positive evidence or latest explicit exact-pair confirmation, plus a real business check/active hold. Unknown identities are never treated as positive. Completed/human-dismissed rows are not new opportunities. All 33 active velocity suppression records remain separately visible even without a positive listing; synced release rules remain authoritative.
- Business qualification projects only verdicts, checks and hold inputs, then hydrates full evidence by qualifying IDs. Actual live transfer fell from 114,602,897 to 3,246,708 bytes with identical results (0 supported excluded opportunities in the bounded scope, 33 suppression records); elapsed 12.404 vs 2.253 seconds. These are observations, not billing guarantees.
- Scorer businessEligibilityChecks records existing classify/offer policy outcomes and inputs independently of identity. Existing inventory/ROI holds can be exposed without rescoring. Missing/stale legacy inputs stay explicit. An allowed profitable offer/auction does not fail solely on asking-price ROI.
- Shared dialog supports Dismiss, green Confirm Match, Not Sure via verdict selection, and collapsed Correct Details. Field feedback, pair verdict, business reason and photo evidence are separate. Cancel saves nothing; errors keep the dialog open. Block ASIN retains confirmation. Bulk dismissal uses per-row stable request IDs and snapshots.
- matching_feedback_v3 is explicit operator evidence; legacy normalization stays v2/legacy_mixed. Available evidence is not counted as explicitly used evidence. Corrections retain original values/source snapshot separately. eBay scope is pair-only; Amazon ASIN scope is explicit. Latest per-field correction history and latest exact-pair verdict load independently across views.
- Action aliases: mark_valid_match -> confirmed_valid_match; confirm_exclusion -> confirmed_exclusion; save_match_feedback -> matching_feedback. Dismiss/watch aliases remain readable. Confirm Exclusion requires a concrete reason. Empty/unsure feedback is unlabeled; low ROI/velocity is not an identity negative; seller/photo feedback stays exact-pair scoped.
- **New v3 feedback is evidence-only for admission in Phase 2.** is_explicit_pair_review excludes it from automatic scoring/title memory pending Phase 3 validation. Confirm Match does not promote, release holds, purchase or certify parser fields. No new re-entry override was added. Phase 3 must validate admission use, supersession/conflicts and reference-correction application.

## Database

Verified project: froeucjkcepuhgwisped / amazon-ebay-ops. Only MBOP public objects changed.

Migration 20260912171310_mbop_atomic_sourcing_review.sql is **applied**; the complete 17-entry shared local/remote ledger matches. Never edit this applied migration. It expands snapshot events without a historical snapshot scan, adds a partial review index and sourcing_save_review / sourcing_latest_reviews.

The save RPC atomically appends action/snapshot/intelligence evidence and applicable dismissal/block/velocity writes. Request ID/fingerprint/actor retries are idempotent; stale ASIN/candidate/item/evaluation writes fail. Purchased/completed lifecycle rows and existing hold conditions are protected. Both functions are SECURITY INVOKER, callable by service_role, not anon/authenticated; production permission readback passed.

Capacity preflight: tiny read passed; DB 6,417,230,995 bytes, sourcing_actions 11,886,592 bytes. Disk IO budget was not exposed; capacity warning was given. No broad sync/backfill or historical relabel was performed.

## Tests and evidence

- 109 sourcing Python tests + 10 feedback tests passed; relevant Python compile checks passed.
- Actual shared-dialog handlers, diagnostic adapter/panel, blocked-ASIN API, Business Excluded GET/projection/hydration/hold-source tests passed.
- Actual action API -> disposable PostgreSQL -> latest-review reload -> actual Python analyzer passed for positive/negative/unsure/corrections. Tested auth, stale pair, blocked-ASIN confirmation, explicit ASIN correction scope, idempotent retries, failed-label full rollback and protected purchase.
- Disposable schema: tests/fixtures/sourcing_review_schema.sql; load before the migration in a new local PostgreSQL container, then set MBOP_REVIEW_TEST_CONTAINER for node web/app/api/sourcing/reviewActions.test.mjs. Never use production. Test schema omits unrelated foreign-key dependencies and contains no production rows.
- Production/local Docker web builds pass. Packaged scheduler's four review/offer-policy tests pass with Docker networking disabled. Focused lint: no errors, nine existing unused helper/type warnings in page.tsx.
- Frozen API exact ordered IDs and summaries unchanged: Buy List 0/0; Closest Excluded 50/141. These are frozen baseline counts.
- Production Business Excluded GET-equivalent: actual handler + live read-only Supabase calls, HTTP 200, 0 supported excluded pairs in scope, 33 hold records. No redirect was counted as success.
- Browser inventory again returned no apps/browsers. Authenticated production UI remains unverified under the work order's explicit fallback. Actual offline dialog screenshot was visually inspected: tmp/sourcing-phase2/review.png and review.html. Original four examples remain in tmp/sourcing-phase1.

Private Phase 2 artifacts: verification.json, live-api.json, database-health.json, function-permissions.json, cli-migration-list.txt, aws-before.json, aws-after.json and aws-verification.json under tmp/sourcing-phase2. Preserve/reuse large Phase 1 fixtures. Unrelated wholesale discovery document remains untouched.

## Runtime and next step

Scheduler revision 92 is registered and mbop-sourcing-catalog now targets it. Runtime source 92674f8cb8f0, digest sha256:0545ef77294d675a7315246b8d8f3be57f94c5e369049a5439585a94fa5c1019. All 20 schedules were compared: only sourcing-catalog changed TaskDefinition 91 -> 92; other settings are preserved.

Final web source 17a49ed94cb4 includes narrow querying, correct inventory-hold evidence selection and fresh IDs for each completed review (retries retain the in-flight ID). Verified 2026-09-12T17:54:23.639224+00:00: web task 144, image sha256:3f10ad423897c16e9b22d96c92db7293cfda2eb25e4d485964745bd244a6e5e5, rollout COMPLETED, one running task, zero pending and its exact ALB target healthy. Runtime commits are pushed. See docs/sourcing_phase2_manifest_2026-09-12.json.

Continuation: complete Phase 3 only, following its full false-positive/false-negative tests, evidence tiers, exact current-row manifests and safe write gate. Do not re-run provider searches or reprocess history merely to test deployment. Matching fixes and bounded current decision refresh remain outstanding; the full work order is not complete.
