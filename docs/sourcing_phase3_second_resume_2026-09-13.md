# Phase 3: resume from the second failed gate (2026-09-13)

## Saved adjudication corpus gate - 2026-09-13

**ADJUDICATED EVIDENCE INSUFFICIENT — MORE OPERATOR REVIEW REQUIRED.** Persisted sample: 12 Confirm Match, 3 Incorrect Match, 0 Not Sure, 1 informational mixed lot. All 12 confirmations lack variation verification, so Tier A remains 0; the actual export agrees. All 17 scoped corrections apply. Unchanged shadow: negatives 2 non-match/1 incorrect Match, unqualified confirmations 10 Match/2 Review. Local shadow fixes produce negatives 2 non-match/1 Review, confirmations 11 Match/1 Review; Disney generation/package remains unresolved. Curated 15 positives/18 negatives, 197 Python tests, 195 disposable RPC calls and 1,609 unchanged production-default outputs pass. No deployment, refresh/provider search or production write. Next: append verified variation-scope confirmations, resolve Disney scope, rerun this bounded gate before the final write-guard/deployment phase. [Full report](sourcing_adjudicated_ground_truth_2026-09-13.md) and [exact manifest](sourcing_adjudicated_ground_truth_manifest_2026-09-13.json). Earlier empty-review/checkpoint counts below remain historical.

> Superseded evidence interpretation: [positive-evidence reconciliation](sourcing_positive_evidence_reconciliation_2026-09-13.md) found no qualifying Tier A historical corpus. The 417 receiving assertions are 416 ASIN/item keys, not 417 certified exact pairs. Receiving defaults and purchase labels do not establish identity. Current classification is B=391/E=26; all original measurements below remain preserved. No matcher change or deployment followed. **GROUND TRUTH INSUFFICIENT — MANUAL ADJUDICATION REQUIRED.** See the new manifest and 16-row review queue; do not treat an empty Tier A replay as a pass.

**FAILED SAFETY GATE - SHADOW ONLY.** All six targeted full-source positives now pass identity admission, the original seven positives remain eligible, and the original four bad pairs remain definite non-matches. The expanded strict receiving-assertion safety set still fails. No commit/push, runtime activation, deployment, provider search or production refresh occurred. All changes remain uncommitted on base `0ab2a01`.

## Six root causes and general fixes

The complete before traces were generated and read before changing the matcher. They retain original seed/catalog context, title, Game Name, item specifics, full description, source states, per-source values, every identity comparison, legacy rules, recommendation and scorer presentation. No v3 corrections applied to these inputs. Private files: `six-root-cause-traces-before.json`, `six-root-cause-traces-after.json`, and `root-cause-classification.json` under `tmp/sourcing-phase3-second-resume`.

| Exact positive | Root cause | General fix | Result |
|---|---|---|---|
| White Knight Chronicles II, B004WL4LOY | Post-platform genre, rating, release year, region and Online wording contaminated the core name; two numbers prevented correct base extraction. Publisher handling already worked. | Assign corroborated suffix attributes to their typed metadata roles, protecting product words and numbers before the platform. | Match / Probable Match |
| Battlefield 2042, B096HSJ6PJ | Multiplayer/Online, M, 2021 and NTSC-U/C became product-name tokens alongside the real title number 2042. | Same typed suffix rule; retain 2042 and exclude only the corroborated release-year suffix. | Match / Probable Match |
| Far Cry 4 Complete Edition, B013KZ3P2G | `Far Cry 4 -- Complete Edition, Far Cry 4` was parsed as one repeated product and created conflicting sources. | Parse comma-separated Game Name values independently. Compatible repetitions/omissions support the full title; different explicit editions still conflict. | Match / Probable Match |
| Persona 5 Royal Phantom Thieves, B081W4X9RW | The unrecognized generic trailing label Edition created a different core name on one side. | Remove only the trailing label after extracting recognized editions. Keep all actual variant words, including Royal and Phantom Thieves. No invented edition value. | Match / Probable Match |
| Metroid Dread Special Edition, B097B15RT8 | Ready To Ship was part of the core identity. The shorter Game Name Metroid was not itself contradictory. | Remove the terminal shipping phrase; preserve the full title and the separately supported Special Edition. | Match / Probable Match |
| Final Fantasy XIV Online Complete Edition, B071NFMKR2 | The post-platform Stormblood+Heavensward+Realm list became core identity, while repeated comma-separated Game Name values caused another source conflict. | Separate enumerated contents only for an explicitly inclusive edition, an agreeing structured core name, and a description inclusion statement corroborating multiple expansion names. Preserve the complete contents list as evidence. | Match / Probable Match; inventory hold remains |

Exact IDs remain in `tests/fixtures/sourcing_phase3_resume_counterexamples.json` and the manifest. No simplified versions replaced these six sources. The two held-out full-source checks, Skyrim Special Edition (B01GW8XJVU) and New Super Mario Bros. 2 (B0088MVPFQ), also pass. Additional held-out rule tests cover metadata-free suffixes, conflicting repeated editions, unfamiliar different variant names, shipping phrases and missing/contradictory contents corroboration.

The candidate policy is `video_game_identity_phase3_shadow_v3`. It does not compare titles by unrestricted containment. Game Name omission is reconciled only within the same listing; different full core names, installments, editions, generations and themes remain comparisons of independent evidence. Metadata removal is limited to a post-platform suffix and corroborating typed specifics, and words present in Game Name are protected. Contents separation is conditional, not a blanket rule allowing arbitrary additional titles. Unknown fields remain unknown, including exact contents parity, unsupported editions, completeness and physical format.

NERF's `Playstation PS5` wording now parses as PlayStation 5 rather than generic PS. The legacy production parser is unchanged.

## Corrections and deterministic recheck

The pure backend `recheck_proposed_identity` returns stored and proposed identities separately using the same `phase3_comparison` engine used by sourcing. It does not call marketplaces, save data, create a pair verdict or authorize admission. UI code still has no independent comparator. No new UI endpoint or automatic recheck button was added.

Scoped application and previews share one wire-state adapter. A core-name correction also refreshes its dependent base-name diagnostic, so an invisible stale derived field cannot veto the correction. Edition, platform and other independent facts are not certified by that correction. Original values and provenance remain retained. A provided evaluation timestamp newer than the review action is rejected as unverifiable evidence. Exact-ASIN, listing/variation, scope, cutoff, latest-verdict supersession, invalid newer correction, changed source and conflicting catalog tests remain enforced. A negative pair verdict for one ASIN does not apply to a different ASIN for the same listing. Correction-only and Unsure do not become positive pair evidence.

Confirm Match remains independent of business/lifecycle rules. Reviewed snapshots without the current catalog provenance remain Review rather than overriding catalog data. Current explicit v3 review rows: **0**. Applicability is tested offline and in the disposable API transaction workflow; no live correction was fabricated to demonstrate success.

## Reviewed fixtures and accuracy

Original positives, each eligible: Zelda Twilight Princess; Ghost Recon Breakpoint; RollerCoaster Tycoon Classic; Ni no Kuni; Hasbro Family Game Night 3; Atelier Ryza 2; NERF Legends. **7 retained, 0 lost, 0 newly recovered versus legacy.** All six additional reviewed positives pass identity admission, including the held FFXIV pair. The five previously lost Buy List examples recover relative to shadow v2; FFXIV recovers its positive identity while retaining its hold. Rock Band PS3/platform-alias and FFXIV XIV/14 same-edition fixtures also pass.

Original reviewed negatives, each deterministic non-match: DiRT versus DiRT 3; Gears Ultimate versus Rare Replay package; Origins versus Awakening; Castlevania base versus 2. All 14 expanded negative cases remain non-matches: Rock Band 3 versus Beatles/Country Track Pack/Metal Track Pack; Wipeout 3/2; Dead Rising 4/3; Nickelodeon Dance/base versus 2; Shrek 2/Third and Racing; Disney Infinity/base versus 2.0 Marvel and 3.0 Star Wars; Wii Play Motion/Tiger Woods; New Carnival/Cookie's Counting Carnival and Shrek's Carnival Craze; Prey/IL-2. Expanded textual fixtures do not constitute fresh physical verification. The original Mario Set dismissal remains unresolved, not an approved recovery.

On the original 50 annotated fields, accuracy is **16/50 legacy (32%) -> 49/50 shadow (98%)**, versus 48/50 at the preceding checkpoint. The remaining annotation error is seller wording on the unresolved Mario Set source. On the frozen 1,000, supported Amazon core-name coverage is **13.3% -> 100%**, and eBay **10.6% -> 92.9%**. These limited annotations are not population accuracy.

| Replay | Match | Conflict | Review | Unknown | New hard blocks | Controlled open-to-excluded | Review-origin exclusions | Controlled recoveries |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Frozen 1,000 | 187 | 741 | 72 | 0 | 622 | 613 | 57 | 6 |
| Newest 250 | 62 | 172 | 16 | 0 | 165 | 180 | 16 | 0 |
| Fresh 600 | 114 | 374 | 112 | 0 | 374 | 64 | 1 | 13 |

These same-input scorer results are not approved view transitions or verified recoveries. Business-check outputs remain equal across all 1,600 replay rows. The full field/family breakdown is retained in `safety-summary.json`.

## Strict receiving assertions versus broader candidates

The frozen source contains **421 explicit receiving correct_item records**, resolving to **417 distinct exact pairs** after four duplicate assertions. All 421 have usable pair/reference inputs after same-purchase-ID and same-ASIN reference reconciliation. A fresh bounded read of their exact purchase-item IDs found **421 unchanged correct_item records**. There are no fresh Confirm Match v3 actions. Available purchase-import payloads contain no Game Name/item-specific/description/variation evidence; those fields were not synthesized. Raw original payloads remain in the frozen source.

The source-tiered evaluator never feeds a receiving label to the matching engine. Results:

| Evidence tier | Distinct pairs | Match | Conflict | Review | Unknown | Matching exclusions |
|---|---:|---:|---:|---:|---:|---:|
| Strict receiving assertions | 417 | 189 | 223 | 5 | 0 | 228 |
| Broader purchase/manual/workflow candidates | 2,105 | 1,208 | 804 | 93 | 0 | 897 |

These tiers are separately deduplicated and must not be summed into an independent-certification headline. Missing weaker-source inputs remain explicit in the report. Purchase status does not certify identity. Conversely, a `correct_item` assertion must not be silently discarded merely because the parser conflicts with it.

The strict failures contain both real parser regressions and unresolved source truth. Examples:

- B00DC7G1WE / eBay 266027835351: Bayonetta 2 versus `Bayonetta 2 Nintendo Wii U 2014 sealed` is blocked by a bare release year without structured metadata. This is a clear title-normalization counterexample.
- B0032FCM6U / eBay 137487065723: MLB 2K10 versus Major League Baseball 2K10 exposes an abbreviation issue. No per-title whitelist was introduced.
- B001989B4S / eBay 318364800720: Fight Night Round 4 has quantity/grading wording (`8 pcs`, WATA/VGA/CGC) in the supplier title; those are still unresolved by this parser.
- B072JZB85B / eBay 233733278405: a FIFA 18 receiving assertion refers to a listing containing FIFA 18, The Division and Destiny 2. Correct receipt of one purchase item is not automatically proof that the whole retail listing matches one ASIN/package.
- B07FF3F7F9 / eBay 267725836968: the receiving assertion says correct_item, but the reference says Subnautica and the listing says Below Zero. The conflicting product evidence is retained for reconciliation; it is not overridden or relabeled automatically.

Thus **228 matching exclusions are unresolved receiving-assertion failures, not 228 certified parser false negatives**. The strict gate still fails, independently of the successful six fixes. The earlier commentary suggesting four missing strict references was corrected: those four are duplicates, not missing inputs.

## Fresh routing and protected state

Capture began 2026-09-13 19:49:17 UTC. Fresh views are **28 Buy List / 50 Closest Excluded / 2 Business Excluded**, with 99 open records, 500 recent rejected diagnostic inputs and 33 active holds. Deduplicated union: 600. Latest-action/metadata readback at 19:53:03 UTC found 0 changed rows, 0 new operator actions and 1 protected inventory-snoozed row. The exact manifest includes IDs, timestamps, stored identity/business evidence, routes, hashes and ordered views. SHA-256: `e81ef1a66916b277d889fd15a596a20f4f122c90564d0ccaa9624ac80aa0a43f`.

Identity-only filtering would exclude 10/28 Buy List, 48/50 Closest Excluded and 0/2 Business Excluded rows. This is not a full proposed refreshed API membership: history, rejected eligibility and current pricing still require reconciliation. Actual task-caused entries/leaves in all views are **0**. Existing ranking and sorting are preserved by the actual handler and compiled-container exact-row comparisons.

Match proceeds to normal business evaluation; Conflict excludes; Unknown is not positive evidence. Review remains excluded from normal Buy List admission and is not guaranteed a place in the top-50 Closest Excluded view. It therefore counts as a safety failure for a good pair. None of the six targeted fixtures remains Review; five strict assertions do. No threshold was relaxed to admit uncertain matches.

Refresh rows examined for write/written/stale-write-skipped: **0/0/0**. Protected lifecycle rows touched and historical records changed: **0**. This is not evidence of a working atomic refresh guard: that path remains unimplemented/unvalidated and was not reached after the identity gate failed. Recent rejected rows remain diagnostic inputs, not approved promotions. The current manifest is a multi-read capture and must be recaptured before any later write.

## Tests and runtime

- 174 focused Python tests passed: 135 sourcing, 21 identity, 18 matching/feedback/corpus. Relevant py_compile passed.
- 24 packaged Phase 3 tests passed with Docker networking disabled.
- 180 actual canonical API/UI indicator comparisons passed: 120 original fixture checks and 60 full-source checks for the six counterexamples. Actual panels rendered offline; shared editable-dialog tests passed.
- Fresh actual GET and compiled web-container tests reproduce exact 28/50/2 IDs, summaries, routing fields and sorting with network disabled.
- Actual review API -> disposable PostgreSQL -> reload -> analyzer tests passed, including stale pair, idempotency, correction-only, original evidence preservation, negative rollback and protected purchase checks. The disposable container is stopped. These are review stale-state tests, not atomic decision-refresh tests.
- Next.js production build and both Docker builds passed. Focused lint: 0 errors, 10 existing unused-code warnings.
- All 1,609 production-default static/full-scorer outputs remain equal to the preserved production baseline.
- Authenticated production UI remains unverified. Offline render/read-only API evidence is documented; no redirect is treated as feature verification.

AWS remains **web145 / scheduler92**. Web source `ac617406851d`, image `sha256:ced396963d4da7d939e659100b4e673ce98bb390b1a66304b5dc02f25856ad51`; scheduler source `92674f8cb8f0`, image `sha256:0545ef77294d675a7315246b8d8f3be57f94c5e369049a5439585a94fa5c1019`. Web has one running task and a completed rollout. All 20 schedules compare unchanged, including their complete saved configuration. No runtime consumer was deployed.

Local-only validation manifests: scheduler `sha256:430b5aefcd70b424d3e07fe8da769104b58da43e455d404ce093dd78ed8cd5fa`; web `sha256:a7d309a78abbc5e3b3b41bf0da29c342877007c9c1c3485c81b94e44c5b7994d`. No image was published. No schema/migration change, marketplace write or quota-consuming provider search occurred. The unrelated wholesale document remains untouched.

## Resume boundary

Preserved: all 9 first-gate artifacts and all 13 preceding-checkpoint artifacts listed by their manifests remain hash-identical. The new [manifest](sourcing_phase3_second_resume_manifest_2026-09-13.json) records current source hashes, exact routing proposals, tests, runtime evidence and artifact hashes. Do not overwrite this checkpoint's files on another replay; use a separate output directory.

The offline tools are `validate_sourcing_matching_phase3.py` (with pinned reviewed sources), `validate_sourcing_positive_tiers.py`, and `validate_sourcing_phase3_resume_gate.py --directory tmp/sourcing-phase3-second-resume`. The final gate exits 1 because the strict receiving assertions do not pass; it does not authorize writes even when a subset passes. `recheck_proposed_identity` is proposal-only. The next work must address general remaining normalization/aliases and explicitly reconcile contradictory receipt-item versus whole-listing/ASIN evidence, then complete full routing and atomic write protection. Do not hide conflicts by treating receiving labels or proposed corrections as unconditional admission overrides.

Phase 3 remains incomplete. Stop at the failed gate.
