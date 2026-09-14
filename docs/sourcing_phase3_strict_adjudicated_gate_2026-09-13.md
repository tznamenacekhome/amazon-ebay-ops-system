# Phase 3 strict adjudicated safety gate after variation follow-up

## Completed-scope rerun: Disney is the sole observed blocker

All 12 confirmations now qualify. Strict replay: 11 Match / 1 Review (Disney); three negatives remain excluded (2 Conflict / 1 Review). No matcher change is justified by the missing reference generation/package evidence. [Focused analysis and current result](sourcing_phase3_disney_gate_rerun_2026-09-13.md). No deployment or refresh. Phase 3 remains shadow-only and incomplete. Earlier counts below are historical.

ADJUDICATED EVIDENCE STILL INSUFFICIENT — MORE OPERATOR REVIEW REQUIRED

Phase 3 remains incomplete and shadow-only. This is a fresh bounded persisted-evidence capture and offline replay, not a deployment or refresh. The supplied completion premise differs from storage: 10 of 12 variation follow-ups are saved. No state was inferred from UI labels.

## Corpus and provenance

Capture 2026-09-14T03:51:14.422503+00:00 through 2026-09-14T03:51:17.506492+00:00: 33 read-only requests, 2,011,579 bytes, 25 distinct actions and 39 linked/source snapshots. All 16 state responses were identical before/after the snapshot read. All 15 original actions match the prior capture exactly; the ten additions are variation-only events. Original verdicts, corrections, flags and notes remain intact.

16 queue rows; 15 reviewable; 10 Tier A positives; 3 verified exact-pair negatives; 0 Not Sure/unresolved verdicts; 2 unqualified confirmations; 1 informational mixed lot (B072JZB85B / 233733278405). The two unqualified confirmations are not Not Sure. Twelve original Confirm Match verdicts remain preserved.

Confirmed-row variation distribution: 10 not_applicable / 0 verified / 2 unknown. Each qualified row has identityAttested=true and variationVerified=true. Zero saved Compatible relationships. All 17 valid corrections applied: 11 eBay/pair, 5 Amazon/pair, 1 Amazon/ASIN (Andromeda edition). No verdict was supplied to the matcher as an answer; corrections alone were applied with snapshot/scope validation. No altered mixed-lot behavior.

## Every exact pair

Identity admission is eligibility for normal business evaluation, not buying approval. Static recommendation is shown separately. M=Match, C=Conflict, U=Unknown field evidence; unknown noncritical fields are not automatically exclusions.

| ASIN / exact eBay ID | Class / operator verdict | Shadow / identity admission | Core/base | Installment | Edition | Platform | Generation/theme/package | Static |
|---|---|---|---|---|---|---|---|---|
| B072JZB85B / 233733278405 | Informational / excluded | Not replayed | — | — | — | — | — | — |
| B07FF3F7F9 / v1\|267725836968\|0 | verified_negative / incorrect | non-match / Conflict | C/C | U | U | M | U/U/U | Blocked |
| B07JMHZMX1 / v1\|168621770668\|0 | tier_a_positive / correct | match / Match | M/M | U | U | M | U/U/U | Probable Match |
| B08SZ1F5FB / v1\|306964576833\|0 | tier_a_positive / correct | match / Match | M/M | U | M | M | U/U/U | Probable Match |
| B01KIH8ADS / v1\|227032903283\|0 | unqualified_confirmation / correct | match / Match | M/M | M | M | M | U/U/U | Probable Match |
| B07KTFL61P / v1\|188511505771\|0 | tier_a_positive / correct | match / Match | M/M | U | U | M | U/U/U | Probable Match |
| B01LDUYU60 / v1\|295925010221\|0 | unqualified_confirmation / correct | match / Match | M/M | U | U | M | U/U/U | Probable Match |
| B01MTQWAFN / v1\|257625187330\|0 | tier_a_positive / correct | match / Match | M/M | M | U | M | U/U/U | Probable Match |
| B07JMHZMX1 / v1\|158089049996\|0 | tier_a_positive / correct | match / Match | M/M | U | U | M | U/U/U | Blocked |
| B009E480RS / v1\|358716154387\|0 | tier_a_positive / correct | match / Match | M/M | M | U | M | U/U/U | Probable Match |
| B00I6E6SH6 / v1\|127933546536\|0 | tier_a_positive / correct | match / Match | M/M | U | U | M | U/U/U | Probable Match |
| B01N3NNPAB / v1\|318579237825\|0 | tier_a_positive / correct | match / Match | M/M | U | M | M | U/U/U | Probable Match |
| B001VLFCXW / v1\|227432986138\|0 | verified_negative / incorrect | needs_review / Review | M/M | U | U | M | U/U/U | Review |
| B07JMHZMX1 / v1\|168621774190\|0 | tier_a_positive / correct | match / Match | M/M | U | U | M | U/U/U | Probable Match |
| B00AXI9WFS / v1\|318571029833\|0 | tier_a_positive / correct | needs_review / Review | M/M | U | U | M | U/U/M | Review |
| B08HTHJ9L2 / 158136497383 | verified_negative / incorrect | non-match / Conflict | M/M | U | C | M | U/U/U | Blocked |

## Disagreements and gate decision

1. **Disney Infinity B00AXI9WFS / 318571029833:** Tier A positive, shadow Review, not eligible for normal business evaluation. This is a strict-gate failure even though no hard block occurs. Root cause classification: insufficient field/source evidence. The reference is `DISNEY INFINITY Starter Pack Xbox 360`; the full listing describes Starter Pack 1.0 plus a separate sealed 3.0 disc, power discs and guide. Amazon generation/installment is unknown; eBay is 1.0. Core/base and packageType match after the two saved eBay corrections, but those corrections do not establish the omitted independent dimensions or whole-package equivalence. Variation Not Applicable certifies listing selection scope, not those missing fields. No parser/comparator defect is proven by this capture; no whitelist, inferred generation, omission relaxation or mixed-lot change was made.

2. **NBA 2K17 B01KIH8ADS / 227032903283** and **Super Mario Maker 3DS B01LDUYU60 / 295925010221:** latest variation is unknown/false, with no variation follow-up event. These are operator/provenance gaps. Both shadow Match, but neither can be counted as Tier A. The operator was notified during the task.

3. **The BIGS 2 B001VLFCXW / 227432986138:** verified negative remains Review due to unresolved one-sided installment 2 after core corrections. It is excluded, so it passes the requested negative-admission check. Subnautica/Below Zero and Riders Republic Standard/Limited remain definite conflicts. None of the three negatives is admitted as Match.

4. **Minecraft B07JMHZMX1 / 158089049996:** Tier A identity Match, separately static Blocked for `not new condition signal: used`. Full description is retained. This is the normal condition rule, not an identity-positive loss or permission to buy.

Known-qualified positives: 9 Match / 0 Conflict / 1 Review / 0 Unknown admission. Negatives: 0 Match / 2 Conflict / 1 Review / 0 Unknown admission. All seven strict requirements cannot be declared satisfied: positive preservation fails; two confirmations remain unqualified; Compatible admission has zero observed examples and remains unproven beyond synthetic qualification. No matcher changes were made.

## Preserved regression coverage

All 15 curated positives remain eligible: NERF Legends PS5, Zelda Twilight Princess, Ni no Kuni, Hasbro Family Game Night 3, Ghost Recon Breakpoint, Atelier Ryza 2, RollerCoaster Tycoon Classic, White Knight Chronicles II, Battlefield 2042, Far Cry 4, Persona 5 Royal, Metroid Dread, Final Fantasy XIV, Skyrim Special Edition and New Super Mario Bros. 2. All 4 original plus 14 expanded curated negatives remain definite non-matches. Exact stored full-source fixtures were reused wherever available; original bounded text-only fixtures retain that limitation.

All 1,609 production-default static/full scorer outputs match the frozen prior hashes. All 1,600 shadow verdicts and business-check comparisons remain unchanged: frozen 1,000 = Match 187 / Conflict 741 / Review 72; current-input 600 = Match 114 / Conflict 374 / Review 112. These are offline historical inputs, not current production view transitions.

## Tier B/C diagnostics

Run after evaluating the strict gate, as this prompt requests; unlike the prior work order this does not require a strict pass. No new broad production audit was run. Cohorts overlap and are not independent positive certifications.

| Frozen reconciled cohort | Tier | Match | Conflict | Review |
|---|---|---:|---:|---:|
| Receiving assertions | B | 186 | 200 | 5 |
| Receiving assertions | C | 0 | 0 | 0 |
| Broader purchase assertions | B | 183 | 202 | 5 |
| Broader purchase assertions | C | 1024 | 573 | 88 |

## Validation and boundaries

160 Python tests passed (152 identity/matching/scorer/evidence/adjudication tests plus 8 correction/snapshot tests); 257 actual API/RPC calls passed against the disposable local database; component, shared-control and diagnostic tests passed; 150 Python-to-API-to-UI indicators and 15 panel renders passed. The actual current export agrees with independent classification using 32 frozen RPC responses and zero network calls. Twenty adjudication tests passed in the existing scheduler image with current source mounted read-only and networking disabled. py_compile and focused lint passed. No Python runtime or web code changed, so no scheduler/Next.js build was required. The disposable database was stopped. Expected injected rollback/errors in transaction logs and mocked retries in unit tests are test scenarios, not production failures.

Production deployments, refreshes, provider searches, marketplace writes, review writes, routing changes, business-hold/lifecycle mutations and scheduler changes: all zero. Prior deployed checkpoint web151 / scheduler92 was not changed or freshly audited. Authenticated production UI verification is not claimed or needed to substitute for persisted evidence.

## Reproducibility and handoff

The [current manifest](sourcing_adjudicated_ground_truth_manifest_2026-09-13.json) records every pair, qualification, corrections, action/variation actors and timestamps, snapshot/evaluation IDs, lineage, all field comparisons and artifact hashes. The [prior manifest](sourcing_adjudicated_ground_truth_manifest_before_variation_2026-09-13.json) is preserved byte-for-byte; original private artifacts were not rewritten. Fresh raw evidence and all replay/test artifacts are ignored under `tmp/sourcing-phase3-strict-gate`.

Source baseline: `64851ae2cc2380b69a9a6789d344791d0a191d0f`. Documentation/evidence-only changes; no matcher candidate change. Commit identity is recorded by Git history, avoiding self-referential metadata.

Reproduce with a new output filename:

```powershell
.venv\Scripts\python.exe integrations/validate_sourcing_adjudicated_ground_truth.py --capture tmp/sourcing-phase3-strict-gate/capture.json --output tmp/sourcing-phase3-strict-gate/reproduced-replay.json
node tmp/sourcing-phase3-strict-gate/verify-export.mjs
```

Not ready for final write-guard/deployment. Complete the two missing variation follow-ups; resolve Disney generation/package identity using supported scoped evidence without guessing. Rebuild only the changed bounded evidence, retain historical captures, and rerun the strict gate. Compatible handling still needs demonstrable admission validation when applicable. The later task owns atomic stale-state/operator-activity protection, a fresh production manifest, final predeployment validation and any separately authorized activation/refresh. This frozen capture is not a future write manifest.

ADJUDICATED EVIDENCE STILL INSUFFICIENT — MORE OPERATOR REVIEW REQUIRED
