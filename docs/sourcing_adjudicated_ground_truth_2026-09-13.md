# Adjudicated exact-pair ground truth - 2026-09-13

## Completed-scope rerun: Disney is the sole observed blocker

All 12 confirmations now qualify. Strict replay: 11 Match / 1 Review (Disney); three negatives remain excluded (2 Conflict / 1 Review). No matcher change is justified by the missing reference generation/package evidence. [Focused analysis and current result](sourcing_phase3_disney_gate_rerun_2026-09-13.md). No deployment or refresh. Phase 3 remains shadow-only and incomplete. Earlier counts below are historical.

## Post-variation strict gate checkpoint

Fresh persisted capture: 10 Tier A positives, 3 verified negatives, 2 unqualified confirmations and 1 informational exclusion; 10 of 12 scopes saved. Tier A replay is 9 Match / 1 Review (Disney Infinity); negatives are 2 Conflict / 1 Review, none admitted. All 17 corrections apply; 15 curated positives and 18 negatives pass. No matcher change, deployment or refresh. Phase 3 remains incomplete and shadow-only. [Full strict-gate report](sourcing_phase3_strict_adjudicated_gate_2026-09-13.md). Earlier zero-Tier-A reports below are frozen history.

## Historical pre-variation report

The following evidence and instructions describe the earlier capture. Use the post-variation checkpoint and linked strict report above for current counts and next steps.

**ADJUDICATED EVIDENCE INSUFFICIENT — MORE OPERATOR REVIEW REQUIRED.** Phase 3 remains incomplete and shadow-only. No deployment or production writes occurred.

## Persisted corpus and qualification

All 15 reviewable rows have saved verdicts: **12 Confirm Match, 3 Incorrect Match, 0 Not Sure**. The original mixed/random lot **B072JZB85B / 233733278405** remains informational-only, outside the denominator. No mixed-lot matching rule changed.

**Tier A positives: 0. Verified exact-pair negatives: 3.** Every confirmation has identityAttested=true but variationVerified=false and variationResolution=unknown. A Browse suffix of 0 is not an operator assertion that variation selection is inapplicable. The existing queue/export agrees: 15 reviewed, 0 Tier A, 3 negatives, 12 unresolved. These 12 are unqualified confirmations, not Not Sure verdicts. Platform relationship entries were not saved on any row: **Compatible count 0**; none is inferred from title text or matching platform values.

Production capture: 2026-09-14T02:04:37.325428+00:00 to 2026-09-14T02:04:40.594670+00:00; 33 read-only requests, 1,430,673 bytes, 15 distinct actions and 29 linked/source snapshots. All 16 state responses were identical before and after snapshot reads. Actor, timestamp, full item/variation identity, original evaluation, source snapshot, action/snapshot links, notes, flags, scoped corrections and lineage are preserved in the manifest. Each reviewable pair has one action; no live supersession was observed. Synthetic regressions cover later verdicts, changed snapshots, conflicting newer corrections/flags/relationships and ambiguous newer listing-level identity. No historical records were rewritten.

Raw evidence and all replays are ignored under `tmp/sourcing-adjudicated-ground-truth`. The checked-in manifest records exact identities, references to the full immutable queue inputs, every scoped correction, actor/time, snapshot/evaluation IDs, source hashes, all field comparisons and reasons. The capture is historical evidence, not an atomic future rollout manifest.

## Unchanged-first replay and corrections

The current shadow matcher was replayed and frozen **before any matcher modification**. Persisted pair verdicts were used only as labels; they were removed from the copied review payload supplied to the matcher. This prevents Confirm/Incorrect feedback from turning the safety replay into an automatic answer echo. Full raw listing metadata and descriptions were retained.

**17/17 corrections applied** with action/snapshot validation: 11 ebay/pair, 5 amazon/pair, 1 amazon/asin. ASIN scope applies only to the explicit Andromeda Amazon edition correction; all other corrections are exact-pair scoped. No invalid/stale corrections or Wrong-only fields were present in this saved sample. Wrong-only input is treated as unreliable without inventing a replacement in synthetic gate tests. Compatible remains separate relationship evidence; synthetic qualification accepts it without rewriting distinct platform values.

On these 17 operator-corrected cells, 0/17 raw parser values agree with the correction labels; after scoped application, 17/17 agree. That is an override/application check, not a claim that parser accuracy became 100%. Confirm Match does not certify the unedited fields.

| Corpus | Unchanged shadow | Final local candidate |
|---|---|---|
| Tier A positives | Empty; not a pass | Empty; not a pass |
| 3 verified negatives | 2 definite non-matches; 1 incorrect Match | 2 definite non-matches; 1 Review; 0 Match |
| 12 unqualified confirmations (diagnostic only) | 10 Match; 2 Review | 11 Match; 1 Review |

Review and Unknown remain identity exclusions. The BIGS recovery from false admission is a Review, not a definite negative inference. A Review on a future qualified positive would fail the gate; zero new hard blocks would not be enough.

## Every exact reviewed pair

| ASIN / full eBay ID | Saved verdict | Initial → final shadow | Static recommendation |
|---|---|---|---|
| B07FF3F7F9 / v1\|267725836968\|0 | incorrect | non-match → non-match | Blocked |
| B07JMHZMX1 / v1\|168621770668\|0 | correct | match → match | Probable Match |
| B08SZ1F5FB / v1\|306964576833\|0 | correct | match → match | Probable Match |
| B01KIH8ADS / v1\|227032903283\|0 | correct | match → match | Probable Match |
| B07KTFL61P / v1\|188511505771\|0 | correct | match → match | Probable Match |
| B01LDUYU60 / v1\|295925010221\|0 | correct | match → match | Probable Match |
| B01MTQWAFN / v1\|257625187330\|0 | correct | match → match | Probable Match |
| B07JMHZMX1 / v1\|158089049996\|0 | correct | match → match | Blocked |
| B009E480RS / v1\|358716154387\|0 | correct | needs_review → match | Probable Match |
| B00I6E6SH6 / v1\|127933546536\|0 | correct | match → match | Probable Match |
| B01N3NNPAB / v1\|318579237825\|0 | correct | match → match | Probable Match |
| B001VLFCXW / v1\|227432986138\|0 | incorrect | match → needs_review | Review |
| B07JMHZMX1 / v1\|168621774190\|0 | correct | match → match | Probable Match |
| B00AXI9WFS / v1\|318571029833\|0 | correct | needs_review → needs_review | Review |
| B08HTHJ9L2 / 158136497383 | incorrect | non-match → non-match | Blocked |

All twelve correct rows remain outside Tier A pending persisted variation-scope verification. The full per-field base/core product, installment, edition, platform, generation/theme/package evidence is in the summary manifest, including original source fields and post-correction comparisons. Current business prices/hold/lifecycle state were not invented for these historical adjudication inputs; no full current opportunity refresh was simulated.

## Disagreements and bounded changes

1. **The BIGS 2 / The BIGS — comparator defect after scoped corrections.** The operator corrected both core names to “the bigs”; the independent Amazon installment remains 2, while the listing has no supported installment. The old comparator admitted matching core names despite that unresolved independent identity dimension. The shadow candidate now routes one-sided installment omission to Review, preserving omission versus contradiction. No ASIN/title exception or fabricated base/1 installment was added. The exact full-source pair and a held-out semantic case are regression fixtures.

2. **Dance Central 3 / Dance 3 Central — within-listing source-reconciliation defect.** Full Game Name corroborates the same ordered product words and exact standalone installment. The shadow candidate reconciles that numeric position using the supporting structured spelling. It still rejects changed words, word order, additional variant text and different numbers; without corroborating Game Name the original ambiguity remains.

3. **LEGO Star Wars Complete Saga — regression exposed by the installment guard.** A frozen Game Name `Lego Star Wars-The Complete Saga (Wii, 2007)` had been split at its internal comma, manufacturing installment 2007. The first candidate newly routed this good-looking frozen pair to Review. Source splitting now respects parentheses/brackets, leaving the year in its metadata context. The final 1,600-row replay has no verdict differences from the preceding frozen shadow baseline; this Review loss is repaired, not hidden by relaxing the installment safeguard.

4. **Disney Infinity — insufficient scope/source evidence, unchanged safeguard.** The reference omits generation; the listing explicitly describes Starter Pack 1.0 plus a 3.0 disc and accessories. Core-name corrections do not establish Amazon generation or exact package equivalence. It remains Review. Do not infer a generation or alter mixed-lot logic to pass it. The operator must clarify the exact reference/package and save any supported scoped field correction separately.

5. **Minecraft / 158089049996 — separate condition rule.** Identity matches, but the full stored description contains a used-condition disclaimer. Static sourcing remains Blocked for `not new condition signal: used`. The operator identity verdict does not waive condition or business rules; this is not a parser mismatch or an identity-positive loss.

Subnautica versus Below Zero remains a definite product mismatch; Riders Republic Standard versus Limited remains a definite edition mismatch. Both are exact-ASIN/listing negatives only and do not reject those listings for another ASIN.

## Safety, tests and boundaries

- All **15 previous curated positives** pass (7 original, 6 full-source counterexamples, 2 held-out full-source examples), with zero losses. Zelda, Ghost Recon, RollerCoaster, White Knight Chronicles II, Battlefield 2042, Far Cry 4, Persona 5, Metroid Dread, FFXIV, NERF and the other curated cases are retained.
- All **18 curated negatives** (4 original plus 14 expanded) remain definite non-matches.
- **197 Python tests** pass, including 17 new corpus/provenance/semantic tests; 195 actual API/RPC calls pass in disposable PostgreSQL. The latter initially exceeded Node’s default 1 MiB test stdout buffer after repeated append-only test runs (1,061,519 bytes); only that test harness buffer was increased. Production limits and RPC logic were unchanged.
- **150 actual Python → API → UI comparison indicators** and 15 offline panel renders pass. Existing diagnostic, adjudication editor and shared-control tests pass. The current export agrees with the independently classified persisted corpus.
- **1,609 production-default static and full scorer outputs are byte-hash equivalent** after removing transient timestamps. Both 1,000 frozen and 600 current-input shadow verdicts and business checks remain equal to the previous frozen replay. These are offline comparisons, not approved production view transitions.
- Python compile, focused lint, local scheduler Docker build and **41 networking-disabled container tests** pass. No web runtime code changed, so no new Next.js build/deployment was needed.
- Tier B/C historical diagnostics are **not rerun**: the prompt places that step after strict truth passes, and it has not. Prior B/C counts remain historical, not measured candidate results. No old workflow-positive record was required to Match.
- Production deployments, refreshes, provider searches, marketplace writes, action/history rewrites, routing changes and protected lifecycle/hold changes: **all zero**. Local test writes used only the disposable database, which is stopped afterward. Authenticated production UI verification remains a prior gap and is not claimed here.

## Next step and git state

Reopen the **12 Confirm Match rows**, verify the exact listing/variation (or genuinely verify that selection is not applicable), check the variation-scope box and save Confirm Match again. This creates append-only superseding evidence; do not edit the existing records or mass-promote unchecked confirmations. Resolve the Disney Infinity generation/package question with evidence rather than inferred defaults. Then recapture only this bounded queue and rerun the strict gate.

The final write-guard/deployment task is **not ready**. It still requires a nonempty qualified positive corpus with zero Conflict/Review/Unknown losses, the subsequent Tier B/C diagnostic rerun, atomic stale-state/operator-activity protection and fresh pre-deployment validation. No deployment or bounded refresh is authorized by this report.

Implementation base: `b2d0bac1ad732df72b0238c06a2270329dec3af6`. Repository closeout includes the shadow matcher changes, offline validator, exact fixtures, tests/test-buffer fix and this documentation. The handoff records the implementation commit in a subsequent documentation commit, avoiding a self-referential hash. Production remains the previously deployed legacy behavior (prior checkpoint web149 / scheduler92; no new AWS runtime readback claimed).

## Repository closeout validation

The resumed closeout used only frozen local evidence; no production read was repeated. All 25 artifact hashes, 8 candidate source hashes and 17 prior reconciliation artifact hashes match. A fresh in-memory offline replay exactly equals the frozen final replay. All 16 manifest rows, persisted verdicts, field comparisons, correction scopes, capture/export counts and 1,609 production-default outputs reconcile. Frozen shadow counts remain Match 187 / non-match 741 / Review 72 across 1,000 rows; current-input counts remain Match 114 / non-match 374 / Review 112 across 600 rows. The focused 17-test adjudicated suite passes again; earlier suite totals above are preserved results, not additional runs.

The disposable `mbop-phase2-review-test` PostgreSQL container was found running and stopped during closeout. No image was deployed or published. Local scheduler image: `mbop-scheduler:adjudicated-shadow-final`, digest `sha256:c5c3fdea44f1d15c9ea422be0950a7343e0a7c1af72adf90082db968e5086c99`.

Compatible-platform admission remains unproven: there are zero saved Compatible relationships. The synthetic test accepts Compatible for Tier A qualification while preserving Xbox One / Xbox Series X values, but its replay remains a platform non-match. The replay currently supplies scoped corrections, not a general relationship-based admission override. A future persisted Compatible case needs explicit end-to-end validation and any justified scoped handling before this requirement can pass. No compatibility success is claimed from this empty observed sample.

Intended file inventory: `integrations/video_game_identity.py` contains the three bounded shadow changes; `integrations/validate_sourcing_adjudicated_ground_truth.py` performs offline provenance classification and correction-only replay; `tests/test_sourcing_adjudicated_ground_truth.py` and `tests/fixtures/sourcing_adjudicated_identity_regressions_2026-09-13.json` cover exact pairs and held-out semantics; `web/app/api/sourcing/adjudication/adjudication.test.mjs` raises only the disposable-test output buffer. The handoff, second-resume report and positive-evidence reconciliation receive current checkpoint notices; this report and its JSON manifest record the complete gate evidence. Raw frozen evidence stays ignored.

Reproduce from the private frozen capture:

```powershell
.venv\Scripts\python.exe integrations/validate_sourcing_adjudicated_ground_truth.py --candidate --output tmp/sourcing-adjudicated-ground-truth/new-replay.json
.venv\Scripts\python.exe -m unittest discover -s tests -p test_sourcing_adjudicated_ground_truth.py
```

`--candidate` requires a new output filename; original captures/replays are not overwritten. The baseline matcher copy and its hashes are preserved under the same ignored directory for the unchanged-first comparison.

ADJUDICATED EVIDENCE INSUFFICIENT — MORE OPERATOR REVIEW REQUIRED
