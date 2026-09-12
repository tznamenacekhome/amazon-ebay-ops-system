# Sourcing matching repair handoff

Current phase: **Phase 1 — diagnostics and frozen audit**. Implementation and focused tests are complete; deployment readbacks must be recorded before closing this phase. Stop this session after Phase 1, per the supplied work order.

Read `docs/sourcing_matching_repair_and_feedback_2026-09-12.md`, its companion manifest, and the original `MBOP_Codex_Sourcing_Matching_Repair_Buy_List_Business_Excluded.md` before continuing.

## Contract

- Canonical engine: integrations/video_game_identity.py. `identity_comparison.evidenceDecision` is diagnostic-only; existing admission `result`/`hard_block` are unchanged.
- Per-side `fields` carry value/state/sources/parserVersion/evidenceVersion/expectation/availability. States can represent supported, inferred, unknown, explicitly_absent, not_applicable, conflicting_sources; absence/not-applicable must never be inferred merely from missing evidence.
- integrations/sourcing_decision_trace.py emits canonicalDecision with evaluation ID/time/version, productIdentityVerdict, businessEligibility/businessReasons, presentationDecision and lifecycleStatus.
- API diagnosticComparison v3 exposes row comparisonResult/comparisonReason and Amazon/eBay evidence; evaluation availability is new/legacy/unavailable. Missing historical evaluation IDs/times remain null. Legacy adapter does not run a new evaluator.
- Current diagnostic panel still uses existing field-feedback semantics. Do not confuse allAssumptionsCorrect with explicit exact-pair match confirmation. Phase 2 must add the requested shared feedback without rewriting old actions.

## Preserved audit and limits

Private frozen evidence is in ignored tmp/sourcing-phase1, cutoff 2026-09-12T16:39:55.421289Z. 1,000 provenance-filtered dismissal candidates, newest 250, 1,000 action snapshots, 33 holds, 5,356 positive-label candidates. Separate historical/current/replay files; no production rows changed.

Exact API baseline: Buy List 0/0 at limit150; Closest Excluded 50/141 at limit50. Exact excluded IDs and ranking are frozen. Both ordered ID lists and summaries unchanged. 1,000 legacy scoring replays unchanged. API response capture is large (~333 MB); reuse offline fixtures instead of repeatedly reading raw production payloads.

Positive candidate source reconciliation found no explicit exact-pair confirmations in that cohort. 1,995 raw identifier pairs are available for safety review; purchase/receiving flags are not automatically certified positives. Preserve all tiers and unresolved conflicts when building Phase 3 gates.

## Validation and access gap

31 Python tests and the actual TypeScript adapter/panel-render test pass; local build passes. Four exact examples are traced through action snapshot/current stored API/read-only replay/offline rendered HTML. Authenticated production browser access is unavailable; fixture screenshots/read-only API-equivalent evidence must not be described as a production UI check.

## Next

After final Phase 1 deployment readback, next session starts **Phase 2** of the original work order: Buy List naming, Business Excluded semantics and shared single/bulk feedback. Do not change numeric/edition admission thresholds yet; do not launch sourcing searches or historical backfills. No schema migration has been created in Phase 1.
