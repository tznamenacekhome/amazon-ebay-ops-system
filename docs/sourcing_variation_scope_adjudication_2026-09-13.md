# Explicit variation-scope adjudication — 2026-09-13

## Scope

Continuation from implementation/evidence `62908e7` and handoff `fa6a8fa`. The frozen persisted corpus remains 16 rows: 15 reviewable, 12 Confirm Match, 3 Incorrect Match, 0 Not Sure and 1 informational mixed lot. This refinement does not invent operator decisions or promote the twelve unqualified confirmations. Phase 3 remains incomplete and shadow-only.

## Operator workflow

Open Sourcing > Identity Adjudication, then **Review confirmation variation scope**. The view includes only current eligible Confirm Match rows that are not Tier A. Progress is computed from current persisted confirmations: initially **0 of 12 variation scope reviewed**. Negative and informational rows are excluded. Saved Unknown or identifier-missing Verified decisions count as reviewed but remain visibly unqualified; a qualified row leaves the follow-up list. Reload recomputes both counts, including operator actions made during this task.

Open a row and select exactly one state at the top of the editor:

- **Not applicable — single-product listing:** the operator verifies that the exact listing has no relevant product variation ambiguity. Saves `variationResolution=not_applicable`, `variationVerified=true`; no artificial variation ID is required.
- **Exact variation verified:** the operator verified the selectable variation. Saves `variationResolution=verified`, `variationVerified=true`; Tier A additionally requires a nonzero exact stored variation identity. The editor displays it or explains why qualification is blocked. It never creates an identifier.
- **Unknown:** saves `variationResolution=unknown`, `variationVerified=false`. The pair stays Confirm Match evidence but does not qualify for Tier A.

Click **Save variation scope**. Do not re-enter verdict, Wrong flags, notes, either-side corrections or platform relationships. These load from saved evidence and are disabled in the follow-up editor. Unknown is an acceptable honest answer; do not select Not Applicable merely to increase Tier A counts. Other adjudication verdicts remain available in the full queue.

## Persistence, provenance and qualification

No SQL migration or RPC definition changes. The existing `sourcing_save_adjudication` transaction appends a new action, source snapshot and evidence row under its request/ASIN advisory locks, expected-revision check and idempotent request fingerprint. Variation-only context contains `reviewKind=variation_scope`, `variationTargetActionId` pointing to the current confirmation, and the explicit variation fields. Its `matching_feedback_v3.pairVerdict` is `not_provided`, with no copied corrections or relationships. The original pair verdict, identity attestation, notes, correction scopes, actors and timestamps remain on their original events. Variation provenance exposes its own action, actor, time and snapshot; lineage retains both events.

The API accepts follow-up only for a current confirmed pair without intervening correction/relationship evidence requiring renewed review. A changed confirmation, stale revision or invalid target rejects inline; unsaved selection remains visible. Retrying an uncertain write uses the original request ID. A committed save followed by readback failure is reported as saved, avoiding duplicate writes. Concurrent operator changes are also checked inside the existing transaction, not only in a preflight read.

Both API and offline validator require current exact-pair provenance, Confirm Match, explicit identity attestation and qualified variation scope. Verified requires the exact stored identifier; zero is not one. Historical explicit resolution names are normalized on read; a bare boolean or pair verdict cannot manufacture a positive variation assertion. Newer invalid scope does not fall back to an older qualified decision. Newer pair verdicts supersede earlier variation follow-up. Compatible relationships are allowed for qualification without rewriting platform values; unedited fields are not certified. Relationship-based matcher admission remains a separate unproven requirement with zero saved Compatible examples in the frozen operator sample.

`GET /api/sourcing/adjudication?followup=variation` returns the filtered rows and dynamic progress. `?report=1` separates `positives`, `unqualifiedConfirmations`, `negatives`, `unresolved` (Not Sure), `unreviewed`, and `excluded`; it includes pair and variation identity, original verdict/attestation, variation provenance, corrections, platform evidence, snapshot/evaluation references and lineage. The offline validator reads the separate event without changing its correction-only full-source matcher inputs.

## Validation

75 focused Python tests pass: 20 adjudicated provenance/variation, 24 Phase 3, 10 feedback and 21 identity-engine tests. API/RPC tests pass 257 calls against the named disposable PostgreSQL container, including all three scope states, preserved original records, retry, stale revision, supersession, negative protection, exact-variation qualification and filtered export. Existing review transaction tests pass through the actual Python analyzer, including rollback and protected purchase behavior. UI contracts, shared controls and diagnostic panel tests pass. Python compile, TypeScript, focused lint, local Next.js build and Docker/web build pass.

The actual packaged browser/API/RPC harness `tests/verify_variation_scope_browser.mjs` tests all three states, preserved notes/corrections/relationship/verdict, inline stale errors with retained selection, qualification, removal from follow-up and reload. Its setup and writes are local disposable test data only. No production credentials enter this test. The image's frozen routing replay retains exact 37 Buy List / 50 Closest Excluded / 2 Business Excluded rows, summaries, fields and order with networking disabled (110 frozen reads). The executable web bundle contains no Phase 3 activation or Python integrations. Frozen export independently reproduces 12 unqualified confirmations, 3 negatives, zero Not Sure and one informational exclusion.

## Gate and deployment boundary

The strict operator gate is pending real follow-up. No new operator-positive gate or Tier B/C diagnostic pass is claimed. The BIGS remains Review rather than definite nonmatch; Dance Central reconciliation and the repaired intermediate LEGO Star Wars regression remain preserved; Disney Infinity generation/package evidence is unresolved; Minecraft's used-condition block remains an independent business rule. Matcher runtime files, sourcing routing, holds, lifecycle, frozen queue and applied SQL are unchanged. The only Python change is the offline validator and its tests, so scheduler deployment is unnecessary and prohibited for this refinement.

Web-only deployment is authorized after validation. Before-state AWS capture shows web149, scheduler92 and 20 schedules. Final deployed revision and schedule comparison will be recorded below. Browser inventory returned no enabled surface; authenticated production click verification cannot be claimed. Exact-image browser testing plus bounded read-only production API-equivalent checks are separate evidence, not proof of the ALB/Cognito browser path.

After the operator finishes: capture only this bounded queue and linked provenance, rebuild a new corpus without overwriting the previous frozen artifacts, then rerun qualified positives, verified negatives and all curated fixtures through the current shadow matcher. Review/Unknown losses of Tier A positives or any admitted negative fail the gate. Activation, fresh write manifests, atomic refresh protection and bounded refresh remain a later task.
