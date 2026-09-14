# Phase 3 resume ? 2026-09-13

**FAILED SAFETY GATE ? SHADOW ONLY.** The original three regressions are fixed, but a fresh populated Buy List reveals five additional valid source-text pairs that would be lost, and the full-source Final Fantasy XIV example under an inventory hold is downgraded. No commit/push, deployment, decision refresh, provider search, marketplace action, or production write was performed in this resume. Working base: `0ab2a01`; candidate changes remain uncommitted. Stop after this failed Phase 3 gate.

## Changes and boundaries

The shadow v2 parser recognizes NWT/BNIB, separates camel-case names without splitting DiRT, removes generic Game only after platform wording, and uses corroborating Publisher/Game Name evidence for edge attribution. Publisher words present in Game Name are retained. Hyphenated identifiers such as IL-2 remain part of the product, not installment 2. Generic standalone installment extraction separates the base product while retaining the full retail name. Missing installments/editions/completeness remain unknown.

Within one eBay listing, a supporting Game Name may be the same normalized name or an ordered subset of its full title. The full title is retained. Additional/different Game Name words still require review. This containment rule is never used to match a shorter Amazon product to a distinct longer eBay product. Comparison output records same, compatible omission, explicit conflict or unknown. Exact-ASIN cache isolation remains intact.

The offline scoped-feedback adapter now accepts actual UI states `value`, `unknown`, `explicitly_absent`, and `not_applicable`, retaining the submitted state and prior value. It preserves latest-verdict supersession, cutoff, exact variation/pair scope and ASIN-only Amazon scope. A newer invalid correction prevents fallback to older evidence. A correction-only action does not supersede a pair verdict; Unsure is not positive evidence. Missing reviewed catalog provenance still requires Review; this guard was not relaxed. Confirm Match still cannot bypass profitability, inventory/velocity holds, location policy or protected lifecycle rules.

`matching_correction_corpus.py` builds a reusable offline action/snapshot corpus. It retains original source, parser evidence/output, opening correction, changed value/state, scope, exact IDs, version, timestamp and verdict. It distinguishes unknown extraction, reported extraction differences, prior correction changes, and reported pair false positives/negatives. A field correction does not establish a comparison-stage error. It never creates rules or writes to a database. The current bounded v3 query returned zero actions; live correction effectiveness is therefore not measurable here. Synthetic API/PostgreSQL and Python tests provide correction validation.

Production defaults remain legacy. All 1,609 frozen default static/full-scorer results match the production baseline exactly. Shared tabs, controls, sorting, hold release conditions and runtime queries are unchanged.

## Measured results

On the original 50 annotated fields, legacy accuracy is 16/50 (32%); prior shadow was 43/50 (86%); resumed shadow is 48/50 (96%). Remaining errors are NERF's eBay platform (`PS` instead of PlayStation 5) and seller wording on the unresolved Mario Set example. This small reviewed subset is not population accuracy.

On the frozen 1,000 cohort, Amazon supported core-name coverage is 133/1,000 ? 1,000/1,000; eBay is 106/1,000 ? 887/1,000. Greater coverage is not proof of correctness: the new counterexamples contain over-specific core names.

| Cohort | Match | Non-match | Review | New hard blocks | Controlled open?excluded | Of those, Review losses | Controlled recoveries |
|---|---:|---:|---:|---:|---:|---:|---:|
| Frozen 1,000 | 164 | 724 | 112 | 607 | 634 | 90 | 5 |
| Newest 250 | 58 | 166 | 26 | 159 | 184 | 26 | 0 |
| Fresh 600 | 89 | 386 | 125 | 386 | 75 | 3 | 13 |

The frozen positive-candidate corpus contains 5,356 workflow/memory records and 2,520 deduplicated complete title pairs. Shadow results are 1,393 Match / 1,029 Non-match / 98 Review. Missing inputs include 1,475 eBay titles, 658 Amazon titles and 2,269 exact listing IDs (overlapping). There are no independent exact-pair certifications in this corpus; these counts are not positive accuracy and do not justify promoting rejected rows.

These are same-input scorer simulations, not approved view changes, verified recoveries or restored dismissals. Historical memory and current pricing/reactivation are not fully simulated. Business-check outputs are unchanged throughout replay. Full field/family coverage and per-row reasons are retained in the private safety summary/replay.

Original reviewed positives: Zelda Twilight Princess, Ghost Recon Breakpoint, RollerCoaster Tycoon Classic, Ni no Kuni, Hasbro Family Game Night 3, Atelier Ryza 2 and NERF Legends all remain eligible: **7 retained, 0 recovered relative to legacy, 0 lost**. The first three recover from the previous failed shadow result. Six reuse full stored listing evidence; NERF remains the bounded exact-ASIN purchase/receiving text fixture, not fabricated full raw sources. The Rock Band PlayStation 3/PS3 alias fixture passes. The synthetic FFXIV XIV/14 same-edition fixture passes, but does not override its failing full-source example below.

The four original reviewed bad pairs are now deterministic non-matches: DiRT/DiRT 3, Gears Ultimate/Rare Replay, Origins/Awakening and Castlevania/base versus 2. All 14 supplemental distinct-product cases pass: Rock Band 3/Beatles and Country/Metal Track Packs; Wipeout 3/2; Dead Rising 4/3; Nickelodeon Dance/base versus 2; Shrek 2/Third and Racing; Disney Infinity/base versus 2.0 Marvel and 3.0 Star Wars; Wii Play Motion/Tiger Woods; New Carnival/Cookie's Counting Carnival and Shrek's Carnival Craze; Prey/IL-2. These supplemental cases are textual regression tests, not fresh marketplace verification. Mario Set remains unresolved and is not counted as a caught bad pair or approved recovery.

## Failed fresh safety examples

Exact full source inputs are frozen in `tmp/sourcing-phase3-resume/current-evidence.json`, with durable fixture IDs in `tests/fixtures/sourcing_phase3_resume_counterexamples.json`.

| ASIN / exact opportunity | Good product | Shadow failure |
|---|---|---|
| B004WL4LOY / 76c40cca-b987-4aa1-a55e-ca1458c30e41 | White Knight Chronicles II | Hard exclusion: Action RPG, T, 2011, NTSC-U/C and Online contaminate the core name. |
| B096HSJ6PJ / 2620cd16-b78b-468e-a3ba-1486f52be8fc | Battlefield 2042 | Hard exclusion: multiplayer/online, M, 2021 and region contaminate the core name. |
| B013KZ3P2G / 2242e14b-764d-48bd-9435-64c763a3d796 | Far Cry 4 Complete Edition | Identity Review from repeated comma-separated Game Name. Scoring labels the result Probable Non-Match; this is still counted as a Review-origin loss. |
| B081W4X9RW / cf461d09-70b6-4d0b-9321-f8f07f0f7b36 | Persona 5 Royal Phantom Thieves | Hard exclusion: trailing Edition remains in only one core name. |
| B097B15RT8 / d3c3c263-66b8-4686-af12-ff70d1781e4d | Metroid Dread Special Edition | Hard exclusion: Ready To Ship remains in the core name. |
| B071NFMKR2 / 18a42399-3b36-4bda-a962-5c25f22c5482 | Final Fantasy XIV Online Complete Edition | Held positive downgraded: enumerated Stormblood/Heavensward/Realm contents become a different core product. Inventory hold remains protected. |

These are source-text reviewed positives, not physical/photo certifications. Five current Buy List positives would be lost: four new hard exclusions and one Review-origin exclusion. The held FFXIV pair would also lose positive identity. Passing the original seven alone is insufficient. No title-specific whitelist or broad mismatch relaxation was added to mask these failures.

Review semantics remain: Review is excluded from normal Buy List admission and is not a deterministic identity conflict. Closest Excluded offers only the ranked top 50 never-presented/unreviewed candidates; it is not a guaranteed Review queue. The gate counts hidden Review positives as losses. The remaining scalar recommendation/identity distinction and complete post-refresh routing still need validation before activation.

## Fresh manifest, routing and protection

Fresh read window: 2026-09-13 17:40:39?17:40:58 UTC. Captured 28 Buy List, 50 Closest Excluded (129 qualifying), 2 Business Excluded, 99 open, latest 500 rejected diagnostic inputs, and 33 active velocity holds. Deduplicated opportunity union: 600. Latest-action/metadata readback at 17:44:17 UTC found 0 changed rows and 0 new actions; one inventory-snoozed protected opportunity is in the union. Latest reviews: zero. The rejected sample is diagnostic input, not an approved 500-row reactivation scope; final eligibility screening was not completed after gate failure.

`exact-current-manifest.json` records exact ordered views/cohorts, ASIN/listing/candidate IDs, status, updated_at, action/review timestamps, stored identity/business evidence and hashes. SHA-256: `40c32c33e6fe24cb78f2f40254c5110fd7e2cfa9412d83d2828e29bc44e9adf3`. This multi-read capture is not a transactional snapshot and is not reusable for future writes without recapture.

The read-only API harness projects only identifiers in its historical presented-listing lookup; those are the only fields that function consumes. Capture transfer was 82,039,432 bytes before exact missing-row hydration, avoiding repeat transfer of the old large historical payload. The actual GET handler and compiled container were replayed offline against the captured responses; exact IDs, summaries, routing fields and existing order match 28/50/2. Production query code was not changed. Existing bounded API lookup limits remain a limitation of this evidence.

Identity-only proposed filtering would exclude 18/28 Buy List, 49/50 Closest Excluded and 1/2 Business Excluded rows. Exact IDs and reasons, including the failed positives above, are in `resume-gate.json` and the manifest. These are **not** complete predicted final view memberships. Actual task-caused entries/exits in every view: **0**. No dry-run was represented as write approval. Refresh rows examined for write/written/stale-write-skipped: **0/0/0**. Metadata drift checks examined 600 rows; they are not proof of an atomic compare-and-swap write guard. Protected lifecycle touches and historical action/snapshot changes: **0**. All nine prior Phase 3 artifact hashes are unchanged.

## Verification and runtime

- 168 focused Python tests passed: 129 sourcing, 21 identity, 18 matching/feedback/corpus; compile checks passed.
- 20 packaged Phase 3 tests passed with Docker networking disabled.
- 120 actual Python?API?UI canonical indicator checks passed, with offline panel rendering. Current shared-dialog handlers, side/state/undo/correction tests passed.
- Actual API?disposable PostgreSQL?reload?Python analyzer tests passed, including negative rollback tests, v3 corrections, supersession, stale pair, idempotency and protected purchases. The disposable container is stopped.
- API Business Excluded, blocked-ASIN, declined-offer, request-ID and fresh exact routing tests passed. Compiled web container reproduced 28/50/2 and all routing fields with networking disabled.
- Next.js production build and both Docker builds passed. Focused lint: 0 errors, 10 existing unused-code warnings. Docker dependency installation reported existing audit findings; dependency remediation was outside this matching-only change.
- Authenticated production UI remains unverified. Offline render/API evidence is not a substitute for authenticated visual verification, and no authentication redirect is counted as feature proof.

AWS readback: web145, source `ac617406851d`, image `sha256:ced396963d4da7d939e659100b4e673ce98bb390b1a66304b5dc02f25856ad51`; one running task, rollout COMPLETED. Scheduler92, source `92674f8cb8f0`, image `sha256:0545ef77294d675a7315246b8d8f3be57f94c5e369049a5439585a94fa5c1019`. All 20 schedule configurations equal the prior readback. No runtime revision changed.

Local-only validation image manifests: scheduler `sha256:dea623a31334245709f158b442617574cfbe981db71eb0d84ee91399b99d9e76`; web `sha256:bcffbc3cca8c7f53dab272fa77fa19e37ed0095225a8d7bc42114fbf80797161`. Neither was pushed or deployed. The scheduler build contains the tested matcher; the later offline gate-report helper is not a production consumer.

## Reproduction and continuation

Run the main replay with pinned reviewed full sources, then the additional gate (expected exit 1 while these counterexamples fail):

```powershell
.venv\Scripts\python.exe integrations/validate_sourcing_matching_phase3.py --current tmp/sourcing-phase3-resume --reviewed-current tmp/sourcing-phase3/current-evidence.json
.venv\Scripts\python.exe integrations/validate_sourcing_phase3_resume_gate.py
.venv\Scripts\python.exe integrations/matching_correction_corpus.py tmp/sourcing-phase3-resume/reviews.json tmp/sourcing-phase3-resume/correction-corpus.json
```

Preserve this checkpoint's artifacts before rerunning; the main replay supports `--output` for a separate output directory. Next work must handle metadata suffixes, repeated structured names, edition descriptors and included-content evidence generally, while retaining meaningful title words and all the negative fixtures. It must also finish full current routing/history/pricing reconciliation and the atomic operator-activity write guard. Revalidate NERF platform/source availability and the full FFXIV fixture. Do not activate or refresh from this manifest. No related-ASIN, wholesale or eBay-first discovery was added. The unrelated wholesale document is untouched.

Manifest: [sourcing_phase3_resume_manifest_2026-09-13.json](sourcing_phase3_resume_manifest_2026-09-13.json). Phase 3 remains incomplete.


## Resume from the second failed gate - 2026-09-13 (latest)

All six full-source blockers now pass identity admission; all original seven positives and four negatives remain correct. Annotated field accuracy is 49/50 (98%). The separate strict receiving-assertion replay still fails: 421 unchanged records deduplicate to 417 exact pairs, with 189 Match / 223 Conflict / 5 Review. The four-record difference is duplicates, not missing references. Some failures are parser errors (year/quantity/abbreviation); others are contradictory receipt-item versus whole-listing/ASIN evidence and cannot be automatically relabeled.

**FAILED SAFETY GATE - SHADOW ONLY.** No new commit/push, deploy, provider search, refresh or production write. Fresh capture remains 28/50/2 with 33 holds and 600 deduplicated rows. Six targeted losses are fixed, but the strict failures and unfinished full routing/atomic refresh guard prevent activation. Production remains web145 / scheduler92; all 20 schedules unchanged. Changes remain uncommitted on 0ab2a01. Authenticated production UI remains unverified.

See [the latest report](sourcing_phase3_second_resume_2026-09-13.md) and [manifest](sourcing_phase3_second_resume_manifest_2026-09-13.json). Prior 9 + 13 frozen artifacts are preserved. Continue Phase 3 only from the strict source-tier evidence, not from a passing six-case subset; recapture mutable state before any future write.
