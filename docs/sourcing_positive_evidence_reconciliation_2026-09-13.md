# Phase 3 positive-evidence reconciliation — 2026-09-13

## Saved adjudication corpus gate - 2026-09-13

**ADJUDICATED EVIDENCE INSUFFICIENT — MORE OPERATOR REVIEW REQUIRED.** Persisted sample: 12 Confirm Match, 3 Incorrect Match, 0 Not Sure, 1 informational mixed lot. All 12 confirmations lack variation verification, so Tier A remains 0; the actual export agrees. All 17 scoped corrections apply. Unchanged shadow: negatives 2 non-match/1 incorrect Match, unqualified confirmations 10 Match/2 Review. Local shadow fixes produce negatives 2 non-match/1 Review, confirmations 11 Match/1 Review; Disney generation/package remains unresolved. Curated 15 positives/18 negatives, 197 Python tests, 195 disposable RPC calls and 1,609 unchanged production-default outputs pass. No deployment, refresh/provider search or production write. Next: append verified variation-scope confirmations, resolve Disney scope, rerun this bounded gate before the final write-guard/deployment phase. [Full report](sourcing_adjudicated_ground_truth_2026-09-13.md) and [exact manifest](sourcing_adjudicated_ground_truth_manifest_2026-09-13.json). Earlier empty-review/checkpoint counts below remain historical.

## Identity adjudication workflow checkpoint - 2026-09-13

The exact 16-row workflow is implemented and offline-tested; see [workflow, evidence and deployment checkpoint](sourcing_identity_adjudication_workflow_2026-09-13.md). `/sourcing/adjudication` captures explicit v3 verdicts and scoped corrections into existing evidence tables. It does not route sourcing rows, release holds, or certify historical positives automatically. Concurrency, stale state, retries and transaction rollback pass; web Docker replay preserves 37/50/2 exact routing rows and order. Deployed web146 from a2552110df37; rollout COMPLETED and exact ALB target healthy. Scheduler92 and all 20 schedules are semantically unchanged. The new migration is applied and all 18 shared ledger entries match. Production read-only queue verification loads 16 available rows, 0 reviewed, 0 Tier A. Authenticated UI remains unverified. Phase 3 remains shadow-only, with no sourcing refresh/provider searches. Next: operator reviews the 16 rows through Sourcing > Identity Adjudication. Stop before further matcher repair; Phase 3 is not complete.


**GROUND TRUTH INSUFFICIENT — MANUAL ADJUDICATION REQUIRED.** Phase 3 remains shadow-only and incomplete. This audit changed no matcher, scorer, feedback consumer, UI, production data, schedule or deployment. No provider search, marketplace quota, refresh, commit or push was used.

Historical workflow-positive records are not automatically exact-pair ground truth.

The prior 417-row “strict receiving” test was not a verified-positive gate. It combined receipt assertions with title-only matching inputs. This report supersedes that interpretation, not the preserved historical measurements. An empty verified corpus is **not** a passing safety gate.

## Sources and actual semantics

The frozen source has 5,356 examples: 3,460 purchase items, 828 purchase matches, 632 purchased actions, 421 receiving outcomes and 15 manual memories. The old 2,105 replayable broader candidates are **all purchase_items**, despite the broader source inventory. The previous evaluator does not hydrate action/manual snapshots to replay every source. Its missing-input/deduplication behavior must not be mistaken for independent evidence coverage.

| Source / producer | ASIN / item / variation availability | What the workflow certifies | Creation, mistakes and supersession | Exact-pair ground truth |
|---|---|---|---|---|
| Receiving outcomes; receiving UI/API | ASIN and legacy item often stored; no variation certification | Quantity, marketplace and receipt outcome; not a mandatory independent identity review | UI initializes Correct Item; API defaults to correct_item without an explicit outcome. One mutable outcome per purchase item is upserted. Errors/replacements and later corrections are possible. | Conditional only with additional explicit identity provenance; none qualified here |
| purchase_items; intelligence builder | Assigned ASIN; item may be absent or embedded in item-transaction SKU; variation absent | Assignment and business status, not identity adjudication | Builder labels every nonempty ASIN as verified_purchase_item / very_high, without requiring a reviewed product identity. ASIN/title can be enriched or edited later. | No, by itself |
| sourcing_purchase_matches | Opportunity and purchase IDs; legacy eBay item join; no independent variation verification | Which imported purchase corresponds to a sourcing listing | Automatic legacy_item_id matching, not independent catalog matching. Original bad ASIN and later corrected purchase can coexist. | No, by itself |
| Purchased actions | ASIN/item/opportunity/action and snapshot references; often v1 item with zero suffix | Intent/record of buying, not an independent full product review | Manual workflow event; purchasing mistakes remain possible. Later negative/correction can contradict it. | No, by itself |
| Confirm Match / confirmed_valid_match / mark_valid_match | Exact ASIN/item/variation and reviewed snapshot required | Explicit pair identity, not every parser field or commercial eligibility | Manual; latest verdict, snapshot currentness and conflicting later evidence must be checked. Zero in the bounded action inventory. | Conditional |
| matching_feedback_v3 | Explicit pair scope, action/evaluation provenance and side-specific corrections | Pair verdict and field corrections are separate assertions | Zero in 2,313 bounded actions. Existing tests cover supersession, changed evidence, correction-only and Unsure; this audit provides no live v3 application evidence. | Current explicit correct verdict can qualify; correction-only and Unsure cannot |
| manual_item_matches | ASIN/title/system; source purchase item; no exact listing/variation in the 15 frozen memories | Reusable title/system correction | Manual UI/operator memory, then automatic reuse; mutable on normalized_title/system. It is not a listing-specific physical inspection. | No, by itself |
| RevSeller / purchase enrichment | Catalog ASIN/title/system; no exact supplier variation certification | Reference/enrichment selection | Automatic matching can reuse manual title memory and catalog data; references are not infallible. Existing ASIN retention is not proof of correctness. | No, by itself |
| Purchased/action-time snapshots | Preserve marketplace titles and sometimes specifics/description | What evidence was stored for the action | Snapshot existence does not turn Purchased into Confirm Match. Backfills must not be represented as contemporaneous observations. All 607 supplemental purchased snapshots here say sourcing_api/purchased. | Evidence carrier, not a positive label |
| Current diagnostic snapshots | Evaluated reference/listing and decision where captured | Current algorithm result | Not independent ground truth. Keep separate from action-time inputs and later labels. A bounded exact-ID read additionally preserved current diagnostics for 250/417 receiving assertions. Missing links remain explicit; no diagnostic backfill was performed. | No |
| Field correction / ASIN reassignment | Side and exact ASIN/pair scope must be preserved | A specific field/reference amendment | Correction does not certify the pair. Four current purchase ASINs differ from their receiving ASINs; these projections do not prove who changed them or when. | Correction alone: no |
| Wrong item, listing_error, seller_listing_mismatch, sourcing_false_positive, later pair rejection | Requires exact linkage; received-item error also has purchase scope | Contrary evidence of identity/physical outcome, depending on source | Seller-photo mismatch is not a broad text rule. Wrong delivery need not mean listing text was wrong. Later replacement may resolve physical outcome. Zero sourcing_false_positive and zero seller-listing/photo negatives in the selected cohorts. | Never positive ground truth |

Implementation evidence: `web/app/receiving/page.tsx` initializes and submits correct_item; `web/app/api/receiving/route.ts` normalizes the default and upserts by purchase_item_id. `integrations/build_matching_intelligence_examples.py` assigns the overly broad positive labels. `integrations/match_sourcing_purchases.py` indexes legacy item IDs. `web/app/api/purchases/route.ts` stores title/system manual memory and item splits. `integrations/sync_revseller_sheet.py` consumes that memory. Existing `matching_feedback.py`, review API and UI report define v3 scope and provenance; none was changed.

## Tier model and cohort reconciliation

- **A:** explicit, current exact-pair identity confirmation with preserved reference/listing snapshot, known relevant variation and no unresolved newer contradiction. Hard safety corpus.
- **B:** strong linked purchase/receipt candidate, missing explicit identity review or complete source provenance. Diagnostic evidence, not an unconditional veto.
- **C:** purchase/assignment/workflow-only positive without independent exact-pair certification.
- **D:** stronger contrary evidence invalidates the historical successful-workflow assertion. Wrong delivery is kept distinct from a proven wrong listing match.
- **E:** unresolved material source, reference, scope or correction conflict. No forced positive or negative.

| Cohort | A | B | C | D | E | Total |
|---|---:|---:|---:|---:|---:|---:|
| Receiving assertions | 0 | 391 | 0 | 0 | 26 | 417 |
| Broader purchase assertions | 0 | 390 | 1,685 | 3 | 27 | 2,105 |

The **417 assertions cover 416 ASIN/legacy-item keys**, not 417 distinct exact pairs. Race with Ryan / B07RXW74N5 / 391598494650 occurs twice with a harmless `[video game]` reference-title difference. The earlier 421 → 417 deduplication included title text and did not finish exact-pair deduplication. Preserve all assertions rather than arbitrarily select one as truth.

The broader cohort has 1,182 identifiable ASIN/legacy-item keys, 918 assertions without listing IDs, and five further repeated identifiable keys. Do not collapse missing-ID rows into one “pair” per ASIN. Combined grouping retains 2,104 candidate groups, including missing-ID source records; this is **not** a verified exact-variation count. Cohorts overlap and must not be summed as independent positives.

Receiving dates span June 14–September 9; broader record dates span May 19–September 12. These timestamps can be import/receipt times, not product-review times.

## Current unchanged shadow results

| Cohort / tier | Match | Conflict | Review | Unknown |
|---|---:|---:|---:|---:|
| Tier A | 0 | 0 | 0 | 0 |
| Receiving B | 186 | 200 | 5 | 0 |
| Receiving E | 3 | 23 | 0 | 0 |
| Broader B | 183 | 202 | 5 | 0 |
| Broader C | 1,024 | 573 | 88 | 0 |
| Broader D | 1 | 2 | 0 | 0 |
| Broader E | 0 | 27 | 0 | 0 |

All 2,522 assertion replays reproduce the previous unchanged matcher verdicts. Tier A has zero qualifying pairs, zero explicit confirmations, zero receiving-derived verified pairs, zero corrections, no date range and no full verified reference/listing pairs. Its empty replay was **not** counted as a pass. The tool stops for individual adjudication if new explicit Confirm Match/v3 evidence appears; it does not silently discard it.

The 607 exact-ID purchased snapshots add stored listing evidence, but not operator certification. Separate snapshot replays cover 198 receiving assertions (93 Match / 89 Conflict / 16 Review) and 288 broader assertions (134 / 136 / 18). They use their own stored reference titles/timestamps and do not overwrite the original title-only traces. Eight receiving title-only conflicts and ten broader conflicts become Match with stored snapshot inputs. These are **input/replay recoveries**, not verified good opportunities recovered or production routing changes.

For example, Madden NFL 25, Vanguard and FIFA 23 have corroborating publisher/genre/year metadata and already pass with that evidence. Control's stray Series X|S token, Bendy's XB1 token, Watch Dogs SHIPS FREE, and Andromeda Deluxe extraction still fail with stored specifics. Dance Central 3 becomes Review, which remains an exclusion, not a successful recovery. NBA 2K17 has a real stored Game Name disagreement (Early Tip-Off Weekend versus Standard title/description), independently of seller-text noise.

## What is and is not established

There are **28 reviewed receiving parser-field defects and one comparator/token-order defect**. These are observations on the frozen evidence representation, not 29 certified physical-pair false negatives. Four additional broader examples expose field-normalization problems. Broad counts reuse shared pair inspections; do not double count them.

The remaining conflicts are not automatically correct exclusions or matcher defects. The category tables below report confirmed observations plus unresolved/provenance groups, not fabricated historical explanations. Uninspected truth remains unproven. In particular, 167 receiving conflicts remain in the ambiguous-receiving group; 21 have explicitly reviewed material ambiguity, one has stale ASIN metadata, one has conflicting structured evidence, and one receipt describes a replacement. Three demonstrated conflicts arose from missing metadata in the original replay.

Three historical mistaken exact pairs are independently documented and were verified through four exact source-ID negative reads: Rock Band 3 versus base Rock Band at items 406156557010 and 117010162581; Just Dance 2014 versus 2015 at 167831909062. The fourth record is a transaction-form duplicate of the Just Dance negative. Their later receiving/purchase assertions target B000TSZADA (base Rock Band) and B00KTNSLX6 (Just Dance 2015), so the old-ASIN negatives do **not** condemn the corrected pairs. The 5,356-source inventory still contains three Just Dance old-ASIN positive records (two automatic purchase matches and one Purchased action), outside the 2,105 title-replay rows. This directly disproves unconditional Purchased/purchase-linked ground truth.

The three Tier D broader records have explicit wrong-item receipts: Battlefront II (wrong delivery/refund, with corrected order attribution), Fighters Uncaged (wrong product), and Stronghold Collection (non-North-American version). Stronghold's titles return Match, illustrating a physical-outcome failure invisible in title matching. These are three contradicted receipt outcomes, **not three proven mistaken purchasing decisions or seller-photo mismatches**. A separate Battlefront receipt has an order-problem note explaining a successful replacement; its positive outcome cannot certify the first delivery.

Confirmed seller listing/photo mismatch in the selected cohorts: **0**. Confirmed historical mistakes: **3 documented old exact pairs**, none of which is still the same erroneous ASIN pair in the 417/2,105 title cohorts. Observed receiving-versus-current ASIN discrepancies: **4**, all unresolved rather than assumed manual mistakes. No field correction, pair verdict or ASIN reassignment was applied.

The broader 804 conflicts are provisionally partitioned into 32 field-parser observations, one comparator observation, three replay-input omissions, two wrong-item outcomes, one replacement-scope issue, one structured disagreement, 21 reviewed material ambiguities, six ambiguous receiving-linked assertions and 737 workflow-only assertions. This is a lower-bound evidence assessment, **not a statistical estimate that the 737 are correct or incorrect matches**. A defensible genuine-match-error percentage cannot be inferred from these workflow labels.

## Safety, preservation and next step

Replayed curated fixtures retain all seven original positives and all six later full-source positives; both held-out full-source positives also pass. All four original negatives and 14 expanded negative cases remain non-matches in the focused Phase 3 suite, alongside other existing negative guards. No known curated good pair was downgraded or lost. These curated analyst regressions remain mandatory but do not silently become operator-certified historical Tier A pairs.

Annotated accuracy remains **16/50 legacy → 49/50 shadow (98%)**. Frozen 1,000-row core-name coverage remains **Amazon 13.3% → 100%; eBay 10.6% → 92.9%**. There was no additional parser change in this audit and no population-wide field accuracy claim.

Validation: six new audit tests, 24 existing Phase 3 tests, two prior positive-tier tests, Python compile, all 2,522 unchanged assertion comparisons, separate stored-snapshot comparisons and the frozen 1,600-row curated/scorer replay. Sampling quotas pass for every populated category. Forty prior artifact hashes match all three preserved Phase 3 manifests. No runtime changes required another Docker build, web build or deployment. Prior runtime/UI/container evidence is carried forward as prior evidence, not rerun evidence.

Bounded production reads were exact purchase/item/snapshot/source keys after a tiny verified-project read: 211 requests, 21,158,611 response bytes, 20:35:30–20:46:23 UTC, project froeucjkcepuhgwisped. Selections and hashes are in the manifest. The requests returned 2,107 purchase rows, 435 receipt rows, 805 purchase matches, 165 problem records, 2,313 actions, 607 purchased snapshots, 824 receiving-linked current opportunity diagnostics and four documented negatives. This is a non-atomic historical audit, not a rollout manifest. No broad provider/catalog refresh or raw-history backfill ran.

Production writes, refresh rows examined/written/stale-skipped, protected lifecycle edits, history rewrites, view entries/leaves and hold changes: **all zero**. Buy List sorting and Phase 2 controls/hold-release rules were untouched. The previously verified runtime remains web145 / scheduler92; no new AWS readback or deployment was needed or claimed. Authenticated production UI remains unverified; prior offline UI and read-only API evidence remain the documented fallback, not authentication-redirect proof.

All pre-existing Phase 3 runtime changes remain uncommitted on 0ab2a01. Existing review UI work was already committed; no dirty web file was introduced. The unrelated wholesale discovery document is unchanged. New work consists of an offline reconciliation tool, tests, adjudication fixture, report/manifest and handoff/state updates. No commit or push was created.

Next: review the bounded queue below to establish exact reference/product/variation and receiving-versus-original-listing truth. Prioritize full-source Control, Bendy, Watch Dogs, Dance Central and Andromeda; then the package/edition conflicts and four ASIN discrepancies. Record explicit scoped pair verdicts with the actual reviewed source snapshot and any field corrections separately. Do not promote uncertain, rejected or held rows. Further general matcher work can use the demonstrated field defects, but a deployment claim still needs a non-vacuous verified corpus. Atomic stale-state refresh protection, fresh rollout manifest, final deployment and bounded refresh belong to the later task.

Reproduce offline after retaining the private inputs:

```powershell
.venv\Scripts\python.exe integrations/reconcile_sourcing_positive_evidence.py --annotations tests/fixtures/sourcing_positive_evidence_adjudications_2026-09-13.json
.venv\Scripts\python.exe -m unittest discover -s tests -p test_sourcing_positive_reconciliation.py
```

The manifest and appendix below preserve exact selections, per-category counts, sample IDs and case-specific reasoning. Raw purchases, notes, source snapshots and full traces remain ignored under `tmp/sourcing-positive-evidence-reconciliation`.


## Complete conflict counts

Counts are exclusive primary classifications. Zero means no confirmed assignment in this bounded audit, not proof that the cause never occurs. Missing snapshots, no explicit review and unknown variation are also cross-cutting limitations, not repeatedly added to this table.

| Category | Receiving conflicts | Broader conflicts |
|---|---:|---:|
| genuine parser extraction error | 28 | 32 |
| genuine comparator error | 1 | 1 |
| wrong historical asin linkage | 0 | 0 |
| mistaken purchase | 0 | 0 |
| wrong edition version purchase | 0 | 0 |
| wrong platform linkage | 0 | 0 |
| seller listing mismatch | 0 | 0 |
| seller listing error received item differs | 0 | 2 |
| ambiguous receiving semantics | 167 | 6 |
| physical receipt not exact listing identity | 1 | 1 |
| exact listing id unavailable | 0 | 0 |
| source snapshot unavailable | 3 | 3 |
| later operator correction | 0 | 0 |
| stale metadata | 1 | 0 |
| conflicting amazon reference evidence | 0 | 0 |
| conflicting ebay structured evidence | 1 | 1 |
| workflow only no identity verification | 0 | 737 |
| unresolved | 21 | 21 |

Identity-field counts overlap when a row conflicts on more than one field. Core pollution can mask a latent edition/package/region issue; zero field conflicts is not verified field agreement.

| Field | Receiving conflicts | Broader conflicts |
|---|---:|---:|
| base/core product | 223 | 804 |
| installment/version | 1 | 4 |
| edition | 1 | 1 |
| generation | 0 | 0 |
| theme/content variant | 0 | 0 |
| package type | 0 | 0 |
| included contents | 0 | 0 |
| platform | 0 | 0 |
| region | 0 | 0 |
| completeness | 0 | 0 |
| digital/physical | 0 | 0 |
| other | 0 | 0 |

## Inspection coverage and bounded review queue

66 receiving assertions were individually inspected. The broader corpus has 79 inspected assertions, including 61 shared exact-pair/title inspections and 18 additional cases. All per-category minimums pass; both older and newer observations and obvious/borderline cases are included. Inspection is analyst interpretation of stored evidence, not a new operator confirmation. The reproducible annotation fixture retains the original reasoning and the subsequent richer-snapshot findings separately.

The next review queue contains 16 exact assertions. Missing evidence must be supplied or explicitly recorded as unavailable; no count target justifies an invented match.

| ASIN / eBay item | Tier | Missing evidence / decision |
|---|---|---|
| B072JZB85B / 233733278405 | E | Independent exact-ASIN catalog/UPC or package evidence, exact listing/variation confirmation and explicit current operator pair verdict; receipt allocation/replacement history where relevant |
| B07FF3F7F9 / 267725836968 | E | Independent exact-ASIN catalog/UPC or package evidence, exact listing/variation confirmation and explicit current operator pair verdict; receipt allocation/replacement history where relevant |
| B07JMHZMX1 / 168621770668 | E | Actor/time and exact old/new ASIN reference justification |
| B08SZ1F5FB / 306964576833 | B | Independent exact-ASIN catalog/UPC or package evidence, exact listing/variation confirmation and explicit current operator pair verdict; receipt allocation/replacement history where relevant |
| B01KIH8ADS / 227032903283 | E | Independent exact-ASIN catalog/UPC or package evidence, exact listing/variation confirmation and explicit current operator pair verdict; receipt allocation/replacement history where relevant |
| B07KTFL61P / 188511505771 | B | Independent exact-ASIN catalog/UPC or package evidence, exact listing/variation confirmation and explicit current operator pair verdict; receipt allocation/replacement history where relevant |
| B01LDUYU60 / 295925010221 | E | Independent exact-ASIN catalog/UPC or package evidence, exact listing/variation confirmation and explicit current operator pair verdict; receipt allocation/replacement history where relevant |
| B01MTQWAFN / 257625187330 | B | Independent exact-ASIN catalog/UPC or package evidence, exact listing/variation confirmation and explicit current operator pair verdict; receipt allocation/replacement history where relevant |
| B07JMHZMX1 / 158089049996 | E | Actor/time and exact old/new ASIN reference justification |
| B009E480RS / 358716154387 | B | Independent exact-ASIN catalog/UPC or package evidence, exact listing/variation confirmation and explicit current operator pair verdict; receipt allocation/replacement history where relevant |
| B00I6E6SH6 / 127933546536 | E | Actor/time and exact old/new ASIN reference justification |
| B01N3NNPAB / 318579237825 | B | Independent exact-ASIN catalog/UPC or package evidence, exact listing/variation confirmation and explicit current operator pair verdict; receipt allocation/replacement history where relevant |
| B001VLFCXW / 227432986138 | E | Independent exact-ASIN catalog/UPC or package evidence, exact listing/variation confirmation and explicit current operator pair verdict; receipt allocation/replacement history where relevant |
| B07JMHZMX1 / 168621774190 | E | Actor/time and exact old/new ASIN reference justification |
| B00AXI9WFS / 318571029833 | E | Independent exact-ASIN catalog/UPC or package evidence, exact listing/variation confirmation and explicit current operator pair verdict; receipt allocation/replacement history where relevant |
| B08HTHJ9L2 / 158136497383 | E | Independent exact-ASIN catalog/UPC or package evidence, exact listing/variation confirmation and explicit current operator pair verdict; receipt allocation/replacement history where relevant |

## Individual stored-evidence inspections

Every receiving case below records a correct_item workflow outcome unless stated otherwise. That outcome can be a default and does not attest an independent comparison of the exact listing/variation to the Amazon retail reference. Full original receipts/order and transaction links, current purchase metadata, action lists, snapshots, diagnostics and parser/comparator traces are retained in the private reconciliation artifact. No v3 correction or explicit Confirm Match was found for these pairs. The following case-specific findings explain why the shadow result is right, wrong at a field level, or unresolved.

### B00DC7G1WE / 266027835351

Source `matching_intelligence_receiving_outcomes` / `42705eac-7481-41e3-b20b-1d020f6ac956`; 2026-06-26 19:38:55.958151+00; Tier B; title replay **non-match**.

Amazon: Bayonetta 2 wii u

eBay: Bayonetta 2 Nintendo Wii U 2014 sealed

2014 follows Wii U and reads like release metadata for Bayonetta 2. No structured release-year or original listing snapshot is in this purchase payload. Likely extraction issue, not certified false negative.

Parsed comparison: coreProduct conflict: Amazon bayonetta, eBay bayonetta 2 2014; coreGame conflict: Amazon bayonetta 2, eBay bayonetta 2 2014

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.

### B001989B4S / 318364800720

Source `matching_intelligence_receiving_outcomes` / `d32bf391-a72f-4bfc-833d-e49a62338b9d`; 2026-06-14 23:26:20.93724+00; Tier B; title replay **non-match**.

Amazon: Fight Night Round 4 - Xbox 360

eBay: 8 pcs SEALED Fight Night Round 4 • XBOX 360 • WATA VGA CGC

8 pcs and WATA/VGA/CGC surround Fight Night Round 4. Quantity/grading terms contaminate core, but exact single-unit versus lot packaging and grader claims require the listing.

Parsed comparison: coreProduct conflict: Amazon fight night round, eBay 8 pcs fight night round 4 wata vga cgc; coreGame conflict: Amazon fight night round 4, eBay 8 pcs fight night round 4 wata vga cgc

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.

### B0032FCM6U / 137487065723

Source `matching_intelligence_receiving_outcomes` / `6ee59e0f-a553-4e27-99e9-b42b003c866e`; 2026-07-16 01:06:48.703009+00; Tier B; title replay **non-match**.

Amazon: MLB 2K10 - PC

eBay: Major League Baseball 2K10 PC Brand NEW Factory SEALED

MLB versus Major League Baseball 2K10 is a plausible abbreviation equivalence. No independent catalog/identifier evidence proves this ASIN beyond the linked purchase title.

Parsed comparison: coreProduct conflict: Amazon mlb, eBay major league baseball; coreGame conflict: Amazon mlb 2k10, eBay major league baseball 2k10

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.

### B072JZB85B / 233733278405

Source `matching_intelligence_receiving_outcomes` / `7f08f8ed-86a8-453a-aaf2-762c51acb069`; 2026-07-23 02:23:24.166027+00; Tier E; title replay **non-match**.

Amazon: FIFA 18 (PS4) [video game]

eBay: FIFA 18 , Tom Clancy’s The Division & Destiny 2 , Lot Of 3 , PS4 Free Shipping

FIFA 18 is one of three different games in the listing. Receiving quantity one does not establish whether a split child or whole lot was certified. Preserve package mismatch until allocation/source evidence is reviewed.

Parsed comparison: coreProduct conflict: Amazon fifa, eBay fifa 18 tom clancy s the division and destiny 2; coreGame conflict: Amazon fifa 18, eBay fifa 18 tom clancy s the division and destiny 2

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Stored titles expose a material ambiguity; receipt does not resolve exact retail package/reference truth.

### B07FF3F7F9 / 267725836968

Source `matching_intelligence_receiving_outcomes` / `d7eb4172-eb08-4197-8c4b-360983272928`; 2026-08-01 00:55:58.606417+00; Tier E; title replay **non-match**.

Amazon: Subnautica - Xbox One [Xbox One]

eBay: Subnautica: Below Zero -- Standard Edition (Microsoft Xbox One/Xbox Series X/S,

Amazon says Subnautica; listing explicitly says Below Zero. correct_item cannot choose between wrong ASIN, mistaken purchase or seller-delivered substitution. The matcher is right to expose distinct title content, but cause is unproven.

Parsed comparison: coreProduct conflict: Amazon subnautica, eBay subnautica below zero s; coreGame conflict: Amazon subnautica, eBay subnautica below zero s

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

Stored snapshot `a5aebdc6-4d24-4f6d-b80e-2eb7fe69065e` (2026-07-26T15:53:49.943889+00:00): Game Name ['Subnautica: below Zero']; description unavailable; separate richer-input replay **non-match**. coreProduct conflict: Amazon subnautica, eBay subnautica below zero s; coreGame conflict: Amazon subnautica, eBay subnautica below zero s

Exact-pair certification: **not established**. Stored titles expose a material ambiguity; receipt does not resolve exact retail package/reference truth.

### B01LDUYU60 / 124396275005

Source `matching_intelligence_receiving_outcomes` / `2a8c2d5a-1a7f-4cc2-a446-38be2612aa8c`; 2026-07-21 02:12:08.650726+00; Tier B; title replay **non-match**.

Amazon: Super Mario Maker for Nintendo 3DS - Nintendo 3DS

eBay: Super Mario Maker (Nintendo 3DS) NEW SEALED Y-FOLD NEAR-MINT!

Y-FOLD NEAR-MINT describes packaging, but the original listing/description is absent. Separate condition parsing from exact retail identity; do not certify from receipt alone.

Parsed comparison: coreProduct conflict: Amazon super mario maker, eBay super mario maker y fold near mint; coreGame conflict: Amazon super mario maker, eBay super mario maker y fold near mint

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.

### B00DC7G0GG / 166921418480

Source `matching_intelligence_receiving_outcomes` / `c40c8f47-9200-4967-8b1d-92b987c2f8b4`; 2026-06-26 19:34:24.533506+00; Tier B; title replay **non-match**.

Amazon: Super Mario 3D World wii u

eBay: New, Sealed - Super Mario 3D World (Nintendo Wii U)

New, Sealed is condition boilerplate before Super Mario 3D World. The parser removes Sealed but preserves New as a product word; this is a field extraction defect, not proof of packaging identity.

Parsed comparison: coreProduct conflict: Amazon super mario 3d world, eBay new super mario 3d world; coreGame conflict: Amazon super mario 3d world, eBay new super mario 3d world

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.

### B00CX7FOVS / 137273228365

Source `matching_intelligence_receiving_outcomes` / `da77db71-457b-43c0-8ed2-fd32d6012258`; 2026-08-08 01:10:22.172609+00; Tier B; title replay **non-match**.

Amazon: Madden NFL 25 - Xbox One

eBay: EA Sports Madden NFL 25 Xbox One Multiplayer Online American Football Game

Publisher/genre/online wording surrounds Madden NFL 25. Title strongly suggests metadata pollution; missing structured publisher/genre evidence prevents robust general-rule adjudication here. Follow-up: purchased snapshot supplies the missing metadata and the unchanged current matcher returns Match. This is confirmed loss of input coverage in the old title-only replay, not a currently demonstrated full-source matcher defect. The category denotes unavailable-to-original-replay evidence, not missing database storage.

Parsed comparison: coreProduct conflict: Amazon madden nfl, eBay ea sports madden nfl multiplayer online american football game; coreGame conflict: Amazon madden nfl 25, eBay ea sports madden nfl 25 multiplayer online american football game

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

Stored snapshot `bc0cb285-388d-46ea-8f39-89989eb09fa6` (2026-08-01T14:17:13.165821+00:00): Game Name ['Madden NFL 25']; description retained; separate richer-input replay **match**. Identity matched or unknown; unknown fields are not positive evidence.

Exact-pair certification: **not established**. Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.

### B003TK1HSM / 134665183162

Source `matching_intelligence_receiving_outcomes` / `c00c8565-936f-4727-94f0-51f207a74333`; 2026-07-16 01:52:49.631044+00; Tier B; title replay **non-match**.

Amazon: Nickelodeon Fit [video game]

eBay: NEW Nickelodeon Fit Nintendo Wii Factory Sealed

Leading NEW is a condition adjective before Nickelodeon Fit. Its retention creates an artificial different core name. Wii comes only from the eBay title; reference system provenance still needs review.

Parsed comparison: coreProduct conflict: Amazon nickelodeon fit, eBay new nickelodeon fit; coreGame conflict: Amazon nickelodeon fit, eBay new nickelodeon fit

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.

### B096WZFCHR / 398061858531

Source `matching_intelligence_receiving_outcomes` / `6a6a4bb1-a29b-473e-b15e-f2974115e297`; 2026-06-26 18:51:32.992494+00; Tier B; title replay **non-match**.

Amazon: Marvel's Guardians of the Galaxy - PlayStation 5 [PlayStation 5]

eBay: New Marvel's Guardians of the Galaxy (Sony PlayStation 5 PS5, 2021)

Leading New contaminates Guardians of the Galaxy; both titles explicitly say PlayStation 5. Parenthesized 2021 is removed correctly. No physical receipt identity review is recorded.

Parsed comparison: coreProduct conflict: Amazon marvel s guardians of the galaxy, eBay new marvel s guardians of the galaxy; coreGame conflict: Amazon marvel s guardians of the galaxy, eBay new marvel s guardians of the galaxy

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.

### B01AC3ZD06 / 389976431971

Source `matching_intelligence_receiving_outcomes` / `9ba32dc5-99ea-4bd9-9c4f-e998621659e8`; 2026-06-14 20:13:50.01561+00; Tier E; title replay **non-match**.

Amazon: Nintendo Selects: Super Mario 3D World - Wii U Standard Edition

eBay: Super Mario 3D World (Nintendo Wii U, 2013)

Amazon explicitly says Nintendo Selects and Standard Edition; listing omits Selects. Omission is not proof of a different print, nor proof of equality. Exact cover/retail reference is missing.

Parsed comparison: coreProduct conflict: Amazon selects super mario 3d world, eBay super mario 3d world; coreGame conflict: Amazon selects super mario 3d world, eBay super mario 3d world

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Stored titles expose a material ambiguity; receipt does not resolve exact retail package/reference truth.

### B01BXAFRU8 / 387437718912

Source `matching_intelligence_receiving_outcomes` / `ef18e27d-8eeb-4688-a4b5-fd8983363fe5`; 2026-07-23 02:19:41.800462+00; Tier B; title replay **non-match**.

Amazon: Tales from the Borderlands - Xbox One [video game]

eBay: Tales From the Borderlands - Xbox One X-Box 1 - New Sealed

The listing repeats Xbox One as X-Box 1; parser leaves box 1 in the product. This is platform-alias token leakage, not an installment contradiction.

Parsed comparison: coreProduct conflict: Amazon tales from the borderlands, eBay tales from the borderlands box; coreGame conflict: Amazon tales from the borderlands, eBay tales from the borderlands box 1

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.

### B00IQCRKP2 / 198491292589

Source `matching_intelligence_receiving_outcomes` / `053c1006-a575-4cad-b068-b3b3dd029396`; 2026-07-25 17:23:26.080211+00; Tier B; title replay **non-match**.

Amazon: Kinect Sports Rivals - XBOX One [video game]

eBay: Kinect Sports Rivals (Xbox One, 2014) Brand New Factory Sealed Rare Microsoft

Rare Microsoft trails Kinect Sports Rivals. Likely seller wording, but no full snapshot exists in the replay and correction provenance is absent.

Parsed comparison: coreProduct conflict: Amazon kinect sports rivals, eBay kinect sports rivals rare microsoft; coreGame conflict: Amazon kinect sports rivals, eBay kinect sports rivals rare microsoft

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

Stored snapshot `5094711d-e9e7-45b7-ba15-ef6065cb2eee` (2026-07-17T01:47:31.100955+00:00): Game Name ['Sports Rivals']; description retained; separate richer-input replay **non-match**. coreProduct conflict: Amazon kinect sports rivals, eBay kinect sports rivals rare microsoft; coreGame conflict: Amazon kinect sports rivals, eBay kinect sports rivals rare microsoft

Exact-pair certification: **not established**. Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.

### B003M986Z2 / 168521387402

Source `matching_intelligence_receiving_outcomes` / `0dd855de-8332-4577-85e3-271e95582236`; 2026-07-23 02:45:15.672185+00; Tier B; title replay **non-match**.

Amazon: Hasbro Family Game Night 3 - Nintendo Wii [video game]

eBay: Hasbro Family Game Night 3 - Wii #ABXU

Hasbro Family Game Night 3 Wii is followed by #ABXU, which becomes core text. Likely seller stock identifier, but no typed stock-code/source evidence certifies a general removal rule or retail identity.

Parsed comparison: coreProduct conflict: Amazon hasbro family game night, eBay hasbro family game night abxu; coreGame conflict: Amazon hasbro family game night 3, eBay hasbro family game night 3 abxu

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.

### B07HFMJ4R5 / 377344978601

Source `matching_intelligence_receiving_outcomes` / `d819b785-133e-418d-ab49-4e97ad36b6da`; 2026-07-23 03:12:35.033163+00; Tier E; title replay **non-match**.

Amazon: Minecraft: Starter Collection - Xbox One

eBay: Minecraft Starter Pack + 700 Minecoins Xbox One/Xbox Series X E10+ (2022) NEW

Starter Collection versus Starter Pack plus 700 Minecoins requires retail contents/reference verification. The parser also retains rating/year metadata, but fixing noise cannot certify package parity.

Parsed comparison: coreProduct conflict: Amazon minecraft starter collection, eBay minecraft starter pack minecoins e10; coreGame conflict: Amazon minecraft starter collection, eBay minecraft starter pack 700 minecoins e10

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Stored titles expose a material ambiguity; receipt does not resolve exact retail package/reference truth.

### B00KTNSLX6 / 167831909062

Source `matching_intelligence_receiving_outcomes` / `ed4d4fd3-d3d7-4743-aec6-223ca0f263c1`; 2026-08-08 01:07:47.284509+00; Tier B; title replay **non-match**.

Amazon: Just Dance 2015 - PlayStation 4 [video game]

eBay: NEW Just Dance 2015 ( Sony Playstation 4, PS4, 2014 )

The historical mistake targeted Just Dance 2014, but this assertion targets Just Dance 2015. Both source titles say 2015; leading NEW creates the current conflict. The old ASIN negative cannot transfer.

Parsed comparison: coreProduct conflict: Amazon just dance, eBay new just dance; coreGame conflict: Amazon just dance 2015, eBay new just dance 2015

Receipt evidence: correct_item / unavailable. A linked order-problem record exists; review the retained exact record.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.

### B09D643D8F / 147452442020

Source `matching_intelligence_receiving_outcomes` / `e3bc2065-7c15-4423-bd94-537222d8f73e`; 2026-08-08 01:31:01.610515+00; Tier B; title replay **non-match**.

Amazon: Call of Duty: Vanguard

eBay: Activision Call of Duty: Vanguard PS5 M 2021 NTSC-U/C Shooter Online Multiplayer

Activision, rating/year/region, Shooter and Online surround Vanguard. This resembles an already fixed full-source class, but this title-only record lacks the corroborating specifics. Follow-up: purchased snapshot supplies the missing metadata and the unchanged current matcher returns Match. This is confirmed loss of input coverage in the old title-only replay, not a currently demonstrated full-source matcher defect. The category denotes unavailable-to-original-replay evidence, not missing database storage.

Parsed comparison: coreProduct conflict: Amazon call of duty vanguard, eBay activision call of duty vanguard m ntsc u c shooter online multiplayer; coreGame conflict: Amazon call of duty vanguard, eBay activision call of duty vanguard m 2021 ntsc u c shooter online multiplayer

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

Stored snapshot `16751abb-a712-4ae0-beb2-c4991b66316d` (2026-07-26T01:23:02.890267+00:00): Game Name ['Call of Duty: Vanguard']; description retained; separate richer-input replay **match**. Identity matched or unknown; unknown fields are not positive evidence.

Exact-pair certification: **not established**. Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.

### B08SZ1F5FB / 306964576833

Source `matching_intelligence_receiving_outcomes` / `b06ded4b-90cb-48c4-a670-d30a17dc90c0`; 2026-07-16 01:33:50.823335+00; Tier B; title replay **non-match**.

Amazon: Control Ultimate Edition - Xbox Series X [video game]

eBay: Control Ultimate Edition - Microsoft Xbox Series X / S - Brand New Factory Sealed

Xbox Series X|S leaves a stray s in the core. Both sides explicitly support Control Ultimate Edition. This identifies a core-field defect without deciding physical Series S compatibility.

Parsed comparison: coreProduct conflict: Amazon control, eBay control s; coreGame conflict: Amazon control, eBay control s

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

Stored snapshot `894821b7-8fc3-400c-97cd-490b36f41915` (2026-07-03T23:29:42.076991+00:00): Game Name ['Control Ultimate Edition']; description retained; separate richer-input replay **non-match**. coreProduct conflict: Amazon control, eBay control s; coreGame conflict: Amazon control, eBay control s

Exact-pair certification: **not established**. Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.

### B00ZPT59YS / 287385002117

Source `matching_intelligence_receiving_outcomes` / `9e7895de-855d-4967-8472-86cb1f73d56d`; 2026-06-14 20:14:11.831713+00; Tier B; title replay **non-match**.

Amazon: Sea of Thieves: Standard Edition – Xbox One

eBay: Sea of Theives - Microsoft Xbox One

Sea of Theives is a likely seller misspelling of Sea of Thieves, not an edition. Standard Edition is omitted on eBay, and exact retail verification is missing. A spelling similarity alone cannot authorize a match.

Parsed comparison: coreProduct conflict: Amazon sea of thieves, eBay sea of theives; coreGame conflict: Amazon sea of thieves, eBay sea of theives

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.

### B00DC7G1WE / 318540386966

Source `matching_intelligence_receiving_outcomes` / `f057a1a8-4faa-44bf-82b7-9fd30c0969b3`; 2026-07-16 01:56:01.804887+00; Tier E; title replay **non-match**.

Amazon: Bayonetta 2 wii u

eBay: Bayonetta 2 Bonus Disc Variant (Nintendo Wii U) NEW SEALED

Bonus Disc Variant is explicit additional package content for Bayonetta 2. Bare Amazon title does not settle whether that ASIN includes the bonus disc.

Parsed comparison: coreProduct conflict: Amazon bayonetta, eBay bayonetta bonus disc variant; coreGame conflict: Amazon bayonetta 2, eBay bayonetta 2 bonus disc variant

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Stored titles expose a material ambiguity; receipt does not resolve exact retail package/reference truth.

### B072JY7NX5 / 127895893853

Source `matching_intelligence_receiving_outcomes` / `597885b3-adb1-4ea4-8913-dd4f03f39929`; 2026-06-14 20:15:01.892673+00; Tier B; title replay **non-match**.

Amazon: Wolfenstein II: The New Colossus - PlayStation 4

eBay: Wolfenstein II The New Colossus PlayStation 4 - Brand New and Sealed

Brand New and Sealed leaves and after an otherwise equal Wolfenstein II title. Both sides preserve The New Colossus and normalize II to 2.

Parsed comparison: coreProduct conflict: Amazon wolfenstein the new colossus, eBay wolfenstein the new colossus and; coreGame conflict: Amazon wolfenstein 2 the new colossus, eBay wolfenstein 2 the new colossus and

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.

### B00DWXV1DM / 116824180918

Source `matching_intelligence_receiving_outcomes` / `3d01d336-3996-4179-990c-c5c05c1d152f`; 2026-09-09 01:10:12.092557+00; Tier B; title replay **non-match**.

Amazon: Teenage Mutant Ninja Turtles

eBay: Xbox 360 Nickelodeon TMNT Teenage Mutant Ninja Turtles Video Game NEW Sealed S38

TMNT and Teenage Mutant Ninja Turtles repeat a name alongside Nickelodeon and S38. The stock-code/brand interpretation needs the source listing rather than a broad token deletion.

Parsed comparison: coreProduct conflict: Amazon teenage mutant ninja turtles, eBay nickelodeon tmnt teenage mutant ninja turtles s38; coreGame conflict: Amazon teenage mutant ninja turtles, eBay nickelodeon tmnt teenage mutant ninja turtles s38

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

Stored snapshot `7ffe4a6d-6aa5-489c-8332-622418111352` (2026-08-30T19:55:18.658898+00:00): Game Name ['Teenage Mutant Ninja Turtles']; description retained; separate richer-input replay **non-match**. coreProduct conflict: Amazon teenage mutant ninja turtles, eBay nickelodeon tmnt teenage mutant ninja turtles s38; coreGame conflict: Amazon teenage mutant ninja turtles, eBay nickelodeon tmnt teenage mutant ninja turtles s38

Exact-pair certification: **not established**. Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.

### B002SRNFX2 / 306741007237

Source `matching_intelligence_receiving_outcomes` / `add3738c-ae34-4793-8691-9ed627549d16`; 2026-08-01 00:54:01.993704+00; Tier B; title replay **non-match**.

Amazon: Jumpstart Escape Adventure island - Nintendo Wii

eBay: JumpStart Escape from Adventure Island Video Game Nintendo Wii w/ Manual, Code

Jumpstart Escape Adventure island versus JumpStart Escape from Adventure Island also includes w/ Manual, Code. Missing from and camel-tokenization likely explain part of the conflict, but package/code contents and exact catalog title are not independently verified.

Parsed comparison: coreProduct conflict: Amazon jumpstart escape adventure island, eBay jump start escape from adventure island w manual code; coreGame conflict: Amazon jumpstart escape adventure island, eBay jump start escape from adventure island w manual code

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

Stored snapshot `4ba8fd25-9718-4caf-8d1a-37853ab3bf94` (2026-07-23T01:55:39.349134+00:00): Game Name ['JumpStart: Escape from Adventure Island']; description retained; separate richer-input replay **non-match**. coreProduct conflict: Amazon jumpstart escape adventure island, eBay jump start escape from adventure island w manual code; coreGame conflict: Amazon jumpstart escape adventure island, eBay jump start escape from adventure island w manual code

Exact-pair certification: **not established**. Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.

### B01KIH8ADS / 227032903283

Source `matching_intelligence_receiving_outcomes` / `33751f5c-b525-4991-8dad-30d3d949b729`; 2026-08-10 15:03:49.143934+00; Tier E; title replay **non-match**.

Amazon: NBA 2K17 Standard Edition - PlayStation 3 [video game]

eBay: NBA 2K17 Standard Edition - PlayStation 3, New PlayStation 3,PlayStation 3 Video

Repeated platform and seller catalog suffix New ... Video remain in NBA 2K17 core. Both titles explicitly state Standard Edition; suffix text is not a different game. Stored purchased snapshot further names Early Tip-Off Weekend in Game Name while its title/description say Standard Edition. Original title noise diagnosis does not resolve that structured disagreement. Full stored-snapshot replay is Review; it remains excluded and is not counted as a recovery.

Parsed comparison: coreProduct conflict: Amazon nba, eBay nba new video; coreGame conflict: Amazon nba 2k17, eBay nba 2k17 new video

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

Stored snapshot `e32ae720-02b5-4297-9099-f81e19159cfa` (2026-08-04T02:04:47.158984+00:00): Game Name ['NBA 2K17 [Early Tip-Off!!!! Weekend]']; description retained; separate richer-input replay **needs_review**. coreProduct review: Amazon nba, eBay nba new video; coreGame review: Amazon nba 2k17, eBay nba 2k17 new video

Exact-pair certification: **not established**. Stored titles expose a material ambiguity; receipt does not resolve exact retail package/reference truth.

### B07KTFL61P / 187615175841

Source `matching_intelligence_receiving_outcomes` / `a1c34650-da99-417c-b3e1-b1f53988ee0b`; 2026-06-28 19:19:07.302711+00; Tier B; title replay **non-match**.

Amazon: Bendy and the Ink Machine (XB1) - Xbox One [Xbox One]

eBay: Brand New Bendy and The Ink Machine Microsoft Xbox One Xbox Series X

Amazon parenthetical XB1 survives alongside explicit Xbox One and becomes a game token. The independent eBay title names Bendy and the Ink Machine; cross-generation packaging is still not certified.

Parsed comparison: coreProduct conflict: Amazon bendy and the ink machine xb1, eBay bendy and the ink machine; coreGame conflict: Amazon bendy and the ink machine xb1, eBay bendy and the ink machine

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.

### B002I0JFCO / 257558396715

Source `matching_intelligence_receiving_outcomes` / `d9875b3e-55be-49e6-9b36-cd35029b5920`; 2026-06-26 19:05:52.315222+00; Tier E; title replay **non-match**.

Amazon: EA Sports Active 2 - Xbox 360

eBay: EA Sports Active 2 Xbox 360 Kinect Bundle - Heart Rate Monitor & Band SEALED NEW

EA Sports Active 2 listing explicitly includes Kinect bundle, heart monitor and band. Bare target title cannot independently certify identical retail contents.

Parsed comparison: coreProduct conflict: Amazon ea sports active, eBay ea sports active kinect bundle heart rate monitor and band; coreGame conflict: Amazon ea sports active 2, eBay ea sports active 2 kinect bundle heart rate monitor and band

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Stored titles expose a material ambiguity; receipt does not resolve exact retail package/reference truth.

### B00I6E6SH6 / 227447137918

Source `matching_intelligence_receiving_outcomes` / `11bb943f-639a-4567-a6fd-72cedef2af80`; 2026-08-08 01:28:55.207832+00; Tier E; title replay **non-match**.

Amazon: Minecraft – Xbox One [video game]

eBay: Minecraft Starter Collection - Xbox One, New Xbox One,Xbox One Video Games

Amazon Minecraft versus Starter Collection is potentially a retail-version difference. Receipt alone cannot certify a base ASIN and expanded package as identical.

Parsed comparison: coreProduct conflict: Amazon minecraft, eBay minecraft starter collection new video games; coreGame conflict: Amazon minecraft, eBay minecraft starter collection new video games

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

Stored snapshot `d2439b64-147d-472e-932c-5d30fb894876` (2026-07-28T18:29:19.748611+00:00): Game Name ['Minecraft Starter Collection - Xbox One']; description retained; separate richer-input replay **non-match**. coreProduct conflict: Amazon minecraft, eBay minecraft starter collection new video games; coreGame conflict: Amazon minecraft, eBay minecraft starter collection new video games

Exact-pair certification: **not established**. Stored titles expose a material ambiguity; receipt does not resolve exact retail package/reference truth.

### B07BHHDTL4 / 127755669265

Source `matching_intelligence_receiving_outcomes` / `725558c4-c018-493b-8c76-bad7c9e3c1c8`; 2026-07-17 00:51:36.243285+00; Tier E; title replay **non-match**.

Amazon: Sonic Mania Plus - PlayStation 4 [video game]

eBay: Sonic Mania (Sony PlayStation 4, 2018) *NEW LOOSE DISC*

Sonic Mania Plus target versus Sonic Mania NEW LOOSE DISC is both product and completeness ambiguity. Do not strip Plus or assume receipt proves the original listing was equivalent.

Parsed comparison: coreProduct conflict: Amazon sonic mania plus, eBay sonic mania new loose disc; coreGame conflict: Amazon sonic mania plus, eBay sonic mania new loose disc

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Stored titles expose a material ambiguity; receipt does not resolve exact retail package/reference truth.

### B07KTFL61P / 188511505771

Source `matching_intelligence_receiving_outcomes` / `063032b6-eeba-4661-99c5-b4581eeae259`; 2026-09-07 01:04:03.529686+00; Tier B; title replay **non-match**.

Amazon: Bendy and the Ink Machine (XB1) - Xbox One

eBay: Bendy and the Ink Machine - Microsoft Xbox One

Amazon XB1 duplicate platform shorthand produces the entire difference for Bendy and the Ink Machine. Current purchase linkage is not independent exact-ASIN catalog verification.

Parsed comparison: coreProduct conflict: Amazon bendy and the ink machine xb1, eBay bendy and the ink machine; coreGame conflict: Amazon bendy and the ink machine xb1, eBay bendy and the ink machine

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

Stored snapshot `d68e8e60-b264-419c-a624-fbac7c662437` (2026-08-30T21:14:40.97424+00:00): Game Name ['Bendy And The Ink Machine']; description retained; separate richer-input replay **non-match**. coreProduct conflict: Amazon bendy and the ink machine xb1, eBay bendy and the ink machine; coreGame conflict: Amazon bendy and the ink machine xb1, eBay bendy and the ink machine

Exact-pair certification: **not established**. Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.

### B01AC3ZD06 / 267261817198

Source `matching_intelligence_receiving_outcomes` / `7ec61d72-fc61-4838-92f0-074fd16d6f2f`; 2026-08-12 14:26:40.500487+00; Tier B; title replay **non-match**.

Amazon: Nintendo Selects: Super Mario 3D World - Wii U Standard Edition

eBay: Super Mario 3D World - Nintendo Selects Edition - Nintendo Wii U

Both titles explicitly say Nintendo Selects and Super Mario 3D World. Parser strips Nintendo first and leaves Selects in different positions. This is misplaced edition/line metadata.

Parsed comparison: coreProduct conflict: Amazon selects super mario 3d world, eBay super mario 3d world selects; coreGame conflict: Amazon selects super mario 3d world, eBay super mario 3d world selects

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.

### B003S2JI82 / 267716959948

Source `matching_intelligence_receiving_outcomes` / `749e8c39-3f41-4532-8702-b5ba0976d23e`; 2026-07-16 01:39:07.012345+00; Tier B; title replay **non-match**.

Amazon: Jeopardy - Nintendo Wii

eBay: Jeopardy for Nintendo Wii 2010 Edition, Sealed

Jeopardy for Nintendo Wii 2010 Edition leaves for and 2010. The year plausibly denotes release metadata, but could describe a version. No full source metadata establishes a safe generic deletion here.

Parsed comparison: coreProduct conflict: Amazon jeopardy, eBay jeopardy for; coreGame conflict: Amazon jeopardy, eBay jeopardy for 2010

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.

### B0B6JMXKKR / 137611067988

Source `matching_intelligence_receiving_outcomes` / `e4fe3144-670d-4264-af5a-541d566c41a8`; 2026-09-07 01:39:15.684038+00; Tier B; title replay **non-match**.

Amazon: FIFA 23 Legacy Edition - Nintendo Switch

eBay: EA Sports FIFA 23 Legacy Edition Nintendo Switch NTSC-U/C E 2022

FIFA 23 Legacy Edition includes publisher, NTSC-U/C, E and 2022. The legacy title already has annual identity; year/edition omissions must remain distinct from contradictions. Follow-up: purchased snapshot supplies the missing metadata and the unchanged current matcher returns Match. This is confirmed loss of input coverage in the old title-only replay, not a currently demonstrated full-source matcher defect. The category denotes unavailable-to-original-replay evidence, not missing database storage.

Parsed comparison: coreProduct conflict: Amazon fifa legacy, eBay ea sports fifa 23 legacy edition ntsc u c e 2022; coreGame conflict: Amazon fifa 23 legacy, eBay ea sports fifa 23 legacy edition ntsc u c e 2022

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

Stored snapshot `3a060df7-b0a4-4117-ba9c-cf9e8dbf1e5e` (2026-08-30T19:01:44.486344+00:00): Game Name ['FIFA 23']; description retained; separate richer-input replay **match**. Identity matched or unknown; unknown fields are not positive evidence.

Exact-pair certification: **not established**. Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.

### B0053BG122 / 227355763159

Source `matching_intelligence_receiving_outcomes` / `2bbe8eb2-909b-4254-bdb3-d7c19ec7f5a3`; 2026-06-15 00:03:26.946269+00; Tier B; title replay **non-match**.

Amazon: Just Dance 3 Xbox 360

eBay: Just Dance 3 Xbox 360 - Brand new and Sealed

Brand new and Sealed leaves only a stray and after Just Dance 3; Xbox 360 agrees. No installment weakening is needed to explain the false core conflict.

Parsed comparison: coreProduct conflict: Amazon just dance, eBay just dance and; coreGame conflict: Amazon just dance 3, eBay just dance 3 and

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.

### B00YX0Z3XW / 336652064451

Source `matching_intelligence_receiving_outcomes` / `4f32ac44-7d85-4f79-96f7-945b7e384a76`; 2026-07-16 01:35:28.186076+00; Tier E; title replay **non-match**.

Amazon: Call of Duty: Black Ops III - Multiplayer Edition - PlayStation 3

eBay: Call of Duty: Black Ops III (Sony PlayStation 3, 2015 PS3) **BRAND NEW SEALED**

Amazon Multiplayer Edition is explicit; eBay Black Ops III omits it. Stored titles alone cannot distinguish omitted catalog wording from material edition mismatch.

Parsed comparison: coreProduct conflict: Amazon call of duty black ops multiplayer, eBay call of duty black ops; coreGame conflict: Amazon call of duty black ops 3 multiplayer, eBay call of duty black ops 3

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Stored titles expose a material ambiguity; receipt does not resolve exact retail package/reference truth.

### B09D6QWQHD / 236240985333

Source `matching_intelligence_receiving_outcomes` / `7d2e106c-51b8-4303-a5ea-4c6f47618883`; 2026-06-26 19:37:58.664182+00; Tier B; title replay **non-match**.

Amazon: Call of Duty: Vanguard Xbox Series X

eBay: Call of Duty: Vanguard - Microsoft Xbox Series X / S

Series X|S suffix becomes the core token s for Vanguard. Edition and physical-media coverage cannot be inferred from that diagnosis.

Parsed comparison: coreProduct conflict: Amazon call of duty vanguard, eBay call of duty vanguard s; coreGame conflict: Amazon call of duty vanguard, eBay call of duty vanguard s

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.

### B01AC3ZD06 / 168527755981

Source `matching_intelligence_receiving_outcomes` / `58b25ca9-7d96-42e6-a9b5-528bfa4dccd4`; 2026-08-10 14:29:44.012642+00; Tier B; title replay **non-match**.

Amazon: Nintendo Selects: Super Mario 3D World - Wii U Standard Edition

eBay: Super Mario 3D World - Nintendo Selects Edition - Nintendo Wii U

Same explicit Nintendo Selects retail line appears before versus after Super Mario 3D World. Remaining selects token order causes the core conflict; no omitted edition is being asserted here.

Parsed comparison: coreProduct conflict: Amazon selects super mario 3d world, eBay super mario 3d world selects; coreGame conflict: Amazon selects super mario 3d world, eBay super mario 3d world selects

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.

### B07BHHJR4K / 117290505164

Source `matching_intelligence_receiving_outcomes` / `c8958051-6942-4b5e-964e-ed9cff4c1d55`; 2026-07-23 02:48:38.351166+00; Tier B; title replay **non-match**.

Amazon: Yakuza Kiwami 2: SteelBook Edition - PlayStation 4 [video game]

eBay: Yakuza Kiwami 2 - Steelbook Edition - Brand New  /  Playstation 4 PS4

SteelBook is split to steel book on Amazon while eBay lowercase steelbook stays joined. Both source titles explicitly identify Yakuza Kiwami 2 Steelbook Edition.

Parsed comparison: coreProduct conflict: Amazon yakuza kiwami steel book, eBay yakuza kiwami steelbook; coreGame conflict: Amazon yakuza kiwami 2 steel book, eBay yakuza kiwami 2 steelbook

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.

### B0054U4A4I / 157750447912

Source `matching_intelligence_receiving_outcomes` / `b91fb37e-c00e-4d81-9b70-27521b245f10`; 2026-09-07 01:14:48.988501+00; Tier E; title replay **non-match**.

Amazon: STAR WARS: THE FORCE UNLEASHED II XBOX (XBOX 360)

eBay: New Sealed Star Wars: The Force Unleashed II Platinum edition - Xbox 360

Platinum edition is explicit only on eBay for Force Unleashed II. Missing reference edition is not Standard, and does not certify equality.

Parsed comparison: coreProduct conflict: Amazon star wars the force unleashed, eBay star wars the force unleashed platinum; coreGame conflict: Amazon star wars the force unleashed 2, eBay star wars the force unleashed 2 platinum

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

Stored snapshot `addb9d1f-156c-42b5-9caf-5c7621c2822a` (2026-08-30T20:07:56.96922+00:00): Game Name ['Star Wars: The Force Unleashed II Platinum edition - Xbox 360']; description retained; separate richer-input replay **non-match**. coreProduct conflict: Amazon star wars the force unleashed, eBay star wars the force unleashed platinum; coreGame conflict: Amazon star wars the force unleashed 2, eBay star wars the force unleashed 2 platinum

Exact-pair certification: **not established**. Stored titles expose a material ambiguity; receipt does not resolve exact retail package/reference truth.

### B01LDUYU60 / 295925010221

Source `matching_intelligence_receiving_outcomes` / `4ec62dd8-def1-49a2-b51a-ec1b8e9857b2`; 2026-08-12 14:20:34.33536+00; Tier E; title replay **non-match**.

Amazon: Super Mario Maker for Nintendo 3DS - Nintendo 3DS

eBay: Super Mario Maker for 3DS Nintendo Selects Edition (Nintendo 3DS, 2019) Sealed

eBay Super Mario Maker states Nintendo Selects; reference omits it. The explicit retail-line difference remains unresolved even if selects extraction is improved.

Parsed comparison: coreProduct conflict: Amazon super mario maker, eBay super mario maker for selects; coreGame conflict: Amazon super mario maker, eBay super mario maker for selects

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

Stored snapshot `5b1d653c-6f96-41f4-8643-9a8c61f482f8` (2026-08-03T04:32:06.419109+00:00): Game Name ['Super Mario Maker for 3DS-Nintendo Selects Edition']; description retained; separate richer-input replay **non-match**. coreProduct conflict: Amazon super mario maker, eBay super mario maker for selects; coreGame conflict: Amazon super mario maker, eBay super mario maker for selects

Exact-pair certification: **not established**. Stored titles expose a material ambiguity; receipt does not resolve exact retail package/reference truth.

### B00498PSZQ / 255505144814

Source `matching_intelligence_receiving_outcomes` / `252cf129-3087-494b-a8da-47bc71f0d735`; 2026-07-16 02:10:12.798331+00; Tier B; title replay **non-match**.

Amazon: You Don't Know Jack - Xbox 360

eBay: You Don't Know Jack (Microsoft Xbox 360, 2011) BRAND NEW & FACTORY SEALED

Brand New & Factory Sealed leaves and as product text for You Don't Know Jack. The punctuation is seller condition syntax.

Parsed comparison: coreProduct conflict: Amazon you don t know jack, eBay you don t know jack and; coreGame conflict: Amazon you don t know jack, eBay you don t know jack and

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.

### B01MTQWAFN / 257625187330

Source `matching_intelligence_receiving_outcomes` / `ccaffed2-c7bb-48f7-987d-da39289ce622`; 2026-08-01 00:55:14.991058+00; Tier B; title replay **non-match**.

Amazon: Watch Dogs 2 Xbox One

eBay: Watch Dogs 2 - Microsoft Xbox One BRAND NEW FACTORY SEALED SHIPS FREE!

SHIPS FREE survives as ships free in Watch Dogs 2 core. Both titles say Xbox One; shipping words should not assert a different game.

Parsed comparison: coreProduct conflict: Amazon watch dogs, eBay watch dogs ships free; coreGame conflict: Amazon watch dogs 2, eBay watch dogs 2 ships free

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

Stored snapshot `700d85d1-90e0-4e9e-a4b6-f16bfcc96ed5` (2026-07-26T15:44:52.635774+00:00): Game Name ['Watch Dogs 2']; description retained; separate richer-input replay **non-match**. coreProduct conflict: Amazon watch dogs, eBay watch dogs ships free; coreGame conflict: Amazon watch dogs 2, eBay watch dogs 2 ships free

Exact-pair certification: **not established**. Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.

### B08MG4PK68 / 287384998062

Source `matching_intelligence_receiving_outcomes` / `9c2dba19-9ce6-4761-a886-be07c2df1ddd`; 2026-06-26 19:14:52.615233+00; Tier B; title replay **non-match**.

Amazon: Hitman 3 for Xbox One & Xbox Series X

eBay: Hitman 3 -- Standard Edition (Microsoft Xbox One/Series S/X, 2021)

Amazon for ... & Xbox Series X leaves for and, while eBay Series S/X produces series s 10. Platform wording leaks into game/installment parsing; platform policy itself is not adjudicated.

Parsed comparison: coreProduct conflict: Amazon hitman for and, eBay hitman 3 series s 10; coreGame conflict: Amazon hitman 3 for and, eBay hitman 3 series s 10

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.

### B004NRN5DU / 117331433107

Source `matching_intelligence_receiving_outcomes` / `8059a8b6-de53-486a-967c-f778fd60c0f2`; 2026-08-30 22:36:00.750471+00; Tier E; title replay **non-match**.

Amazon: Dark Souls - Xbox 360

eBay: Bandai Namco Dark Souls II Xbox 360 Game Online Multiplayer Action T 2014

Amazon Dark Souls and eBay Dark Souls II are different explicit installment claims. Receiving can reflect an ASIN mistake or different delivered item; neither cause is documented.

Parsed comparison: coreProduct conflict: Amazon dark souls, eBay bandai namco dark souls 2 online multiplayer action t 2014; coreGame conflict: Amazon dark souls, eBay bandai namco dark souls 2 online multiplayer action t 2014

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Stored titles expose a material ambiguity; receipt does not resolve exact retail package/reference truth.

### B00ZGPJ30M / 406943394327

Source `matching_intelligence_receiving_outcomes` / `acc6c1c2-2729-4303-b779-319a8a904b90`; 2026-06-14 22:27:45.1102+00; Tier B; title replay **non-match**.

Amazon: Plants vs. Zombies Garden Warfare 2 - PlayStation 4

eBay: Plants vs Zombies Garden Warfare 2  PS4 Video Game (Sealed) - Sony PlayStation 4

vs. versus vs is the only remaining core difference for Plants vs Zombies Garden Warfare 2. This is punctuation normalization, with installment 2 preserved.

Parsed comparison: coreProduct conflict: Amazon plants vs. zombies garden warfare, eBay plants vs zombies garden warfare; coreGame conflict: Amazon plants vs. zombies garden warfare 2, eBay plants vs zombies garden warfare 2

Receipt evidence: correct_item / unavailable. A linked order-problem record exists; review the retained exact record.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.

### B00RUZPKYY / 377371682218

Source `matching_intelligence_receiving_outcomes` / `223c6033-2225-40f1-9aa7-b54dac75cf17`; 2026-08-08 01:31:35.175596+00; Tier E; title replay **non-match**.

Amazon: Disgaea 5: Alliance of Vengeance - PlayStation 4

eBay: Disgaea 5: Alliance of Vengeance Bundle (Sony PlayStation 4, 2015)

Disgaea 5 listing says Bundle; reference only names Alliance of Vengeance. Contents and ASIN edition proof are missing.

Parsed comparison: coreProduct conflict: Amazon disgaea alliance of vengeance, eBay disgaea alliance of vengeance bundle; coreGame conflict: Amazon disgaea 5 alliance of vengeance, eBay disgaea 5 alliance of vengeance bundle

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

Stored snapshot `387ffdc0-1db8-4e3b-ba50-50f45fd1d2ea` (2026-07-29T01:16:09.29359+00:00): Game Name ['Disgaea 5: Alliance of Vengeance [Bundle]']; description retained; separate richer-input replay **non-match**. coreProduct conflict: Amazon disgaea alliance of vengeance, eBay disgaea alliance of vengeance bundle; coreGame conflict: Amazon disgaea 5 alliance of vengeance, eBay disgaea 5 alliance of vengeance bundle

Exact-pair certification: **not established**. Stored titles expose a material ambiguity; receipt does not resolve exact retail package/reference truth.

### B00CPKUV7K / 227088858339

Source `matching_intelligence_receiving_outcomes` / `19827957-20fd-4b24-b724-269759518f9c`; 2026-06-14 20:14:44.698378+00; Tier B; title replay **non-match**.

Amazon: Wolfenstein: The New Order - Xbox 360

eBay: Wolfenstein: The New Order - Xbox 360, New xbox_360, Xbox 360 Video Games

New xbox_360, Xbox 360 Video Games is seller catalog boilerplate after Wolfenstein The New Order. The normalized new video games suffix causes the conflict.

Parsed comparison: coreProduct conflict: Amazon wolfenstein the new order, eBay wolfenstein the new order new video games; coreGame conflict: Amazon wolfenstein the new order, eBay wolfenstein the new order new video games

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.

### B01LDUYU60 / 236444483931

Source `matching_intelligence_receiving_outcomes` / `ab52bbc6-5e41-4e04-956d-fcc9a9e43765`; 2026-08-10 15:10:32.052182+00; Tier E; title replay **non-match**.

Amazon: Super Mario Maker for Nintendo 3DS - Nintendo 3DS

eBay: Super Mario Maker for 3DS - Nintendo Selects Edition - Nintendo 3DS - Sealed

Super Mario Maker Nintendo Selects is stated only on eBay. Receipt cannot independently resolve the target ASIN print/edition.

Parsed comparison: coreProduct conflict: Amazon super mario maker, eBay super mario maker for selects; coreGame conflict: Amazon super mario maker, eBay super mario maker for selects

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

Stored snapshot `e2c0067f-f145-47a3-be89-467755b9b418` (2026-08-01T14:09:50.271535+00:00): Game Name ['Super Mario Maker for 3DS-Nintendo Selects Edition']; description retained; separate richer-input replay **non-match**. coreProduct conflict: Amazon super mario maker, eBay super mario maker for selects; coreGame conflict: Amazon super mario maker, eBay super mario maker for selects

Exact-pair certification: **not established**. Stored titles expose a material ambiguity; receipt does not resolve exact retail package/reference truth.

### B009E480RS / 358716154387

Source `matching_intelligence_receiving_outcomes` / `b32a22e5-e28e-4ea7-9811-b7fb5fa2baf3`; 2026-07-23 02:43:34.417799+00; Tier B; title replay **non-match**.

Amazon: Dance Central 3 - Xbox 360

eBay: Dance 3 Central Xbox 360 Game New Factory Sealed

Dance 3 Central and Dance Central 3 yield equal base words and installment but unequal full core order. This is an observed comparator/token-placement issue; do not authorize arbitrary bag-of-words matching. Stored Game Name explicitly says Dance Central 3, while full-source replay remains Review. Review still excludes the candidate; no arbitrary word-order relaxation is authorized.

Parsed comparison: coreGame conflict: Amazon dance central 3, eBay dance 3 central

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

Stored snapshot `571d0cd4-ea08-40a4-a9bb-02999c5d898f` (2026-07-16T19:42:02.376539+00:00): Game Name ['Dance Central 3']; description retained; separate richer-input replay **needs_review**. coreGame review: Amazon dance central 3, eBay dance 3 central

Exact-pair certification: **not established**. Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.

### B00I6E6SH6 / 127933546536

Source `matching_intelligence_receiving_outcomes` / `1efb864b-a705-475e-a843-832ddf5713b6`; 2026-08-01 00:56:22.02631+00; Tier E; title replay **non-match**.

Amazon: Minecraft – Xbox One [video game]

eBay: Microsoft Studios Minecraft Xbox One Multiplayer Online Play E10+

Current purchase ASIN differs from the receiving ASIN for this Minecraft listing. Publisher/online terms also pollute core, but provenance of the reassignment takes precedence over calling this a false negative.

Parsed comparison: coreProduct conflict: Amazon minecraft, eBay microsoft studios minecraft multiplayer online play e10; coreGame conflict: Amazon minecraft, eBay microsoft studios minecraft multiplayer online play e10

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

Current purchase reference differs: B07HBWXFNC; reassignment provenance is unresolved.

Stored snapshot `19d4490f-214b-40ec-9eb2-61c64a835dfd` (2026-07-24T15:21:37.419718+00:00): Game Name ['Minecraft']; description retained; separate richer-input replay **non-match**. coreProduct conflict: Amazon minecraft, eBay minecraft play e10; coreGame conflict: Amazon minecraft, eBay minecraft play e10

Exact-pair certification: **not established**. Current purchase ASIN differs; attribution/timing of reassignment is not recorded here.

### B072JY7NX5 / 257579386928

Source `matching_intelligence_receiving_outcomes` / `d85b4b1e-d480-4c14-8f04-ab0cec08a665`; 2026-06-28 19:19:42.135901+00; Tier B; title replay **non-match**.

Amazon: Wolfenstein II: The New Colossus - PlayStation 4

eBay: Wolfenstein 2 II The New Colossus PlayStation 4 PS4 Sealed

The eBay title states Wolfenstein 2 II, repeating the same installment in Arabic and Roman numerals. Parsing creates 2 2 and a spurious core conflict.

Parsed comparison: coreProduct conflict: Amazon wolfenstein the new colossus, eBay wolfenstein 2 2 the new colossus; coreGame conflict: Amazon wolfenstein 2 the new colossus, eBay wolfenstein 2 2 the new colossus

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.

### B01N3NNPAB / 318579237825

Source `matching_intelligence_receiving_outcomes` / `52261d35-1318-431e-bbc2-7ab6b8816fc0`; 2026-08-01 00:57:15.046434+00; Tier B; title replay **non-match**.

Amazon: Mass Effect Andromeda Deluxe - Xbox One

eBay: Mass Effect: Andromeda -- Deluxe Edition (Microsoft Xbox One, 2017)

Amazon Deluxe without trailing Edition stays in core, while eBay Deluxe Edition is extracted away. Both independently state Deluxe; policy/extraction is inconsistent.

Parsed comparison: coreProduct conflict: Amazon mass effect andromeda deluxe, eBay mass effect andromeda; coreGame conflict: Amazon mass effect andromeda deluxe, eBay mass effect andromeda

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

Stored snapshot `76439b06-358d-4056-a7e8-23acb46e5b34` (2026-07-15T04:49:41.875238+00:00): Game Name ['Mass Effect: Andromeda -- Deluxe Edition, Mass Effect: Andromeda']; description retained; separate richer-input replay **non-match**. coreProduct conflict: Amazon mass effect andromeda deluxe, eBay mass effect andromeda; coreGame conflict: Amazon mass effect andromeda deluxe, eBay mass effect andromeda

Exact-pair certification: **not established**. Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.

### B00B67ZTUW / 287548153629

Source `matching_intelligence_receiving_outcomes` / `b2e22178-1fc0-4d59-a2a1-796282e40d76`; 2026-09-07 01:15:24.176146+00; Tier E; title replay **non-match**.

Amazon: Tales of Xillia - Playstation 3

eBay: Tales of Xillia PS3 * Cover in Spanish and Portuguese * Brand New *

Spanish and Portuguese cover is explicit listing evidence. Reference region is absent; do not infer North America or dismiss the language evidence as noise.

Parsed comparison: coreProduct conflict: Amazon tales of xillia, eBay tales of xillia cover in spanish and portuguese; coreGame conflict: Amazon tales of xillia, eBay tales of xillia cover in spanish and portuguese

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

Stored snapshot `65f11cbc-4bae-48d0-86cd-2ca3a5fd3d91` (2026-08-29T19:28:24.201916+00:00): Game Name ['Tales of Xillia']; description retained; separate richer-input replay **non-match**. coreProduct conflict: Amazon tales of xillia, eBay tales of xillia cover in spanish and portuguese; coreGame conflict: Amazon tales of xillia, eBay tales of xillia cover in spanish and portuguese

Exact-pair certification: **not established**. Stored titles expose a material ambiguity; receipt does not resolve exact retail package/reference truth.

### B0058LTE5S / 137077343022

Source `matching_intelligence_receiving_outcomes` / `758b81cf-b5dc-45d8-b393-e153250c02d7`; 2026-06-26 19:23:53.662753+00; Tier E; title replay **non-match**.

Amazon: The Black Eyed Peas Experience - Nintendo Wii

eBay: The Black Eyed Peas Experience [ Limited Edition W/ Bonus Track ] (Wii) NEW

Black Eyed Peas listing states Limited Edition with Bonus Track, absent from reference title. Require exact edition/content evidence; receipt alone is insufficient.

Parsed comparison: coreProduct conflict: Amazon the black eyed peas experience, eBay the black eyed peas experience w bonus track; coreGame conflict: Amazon the black eyed peas experience, eBay the black eyed peas experience w bonus track

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Stored titles expose a material ambiguity; receipt does not resolve exact retail package/reference truth.

### B004NB1BV4 / 298107925330

Source `matching_intelligence_receiving_outcomes` / `abce63f8-1896-4d15-a41b-336eeb49267a`; 2026-06-26 19:38:19.074635+00; Tier B; title replay **non-match**.

Amazon: Rio - Nintendo Wii

eBay: Rio Brand New & Factory Sealed!

Brand New & Factory Sealed leaves and after Rio. Amazon names Wii; eBay platform is omitted, so this field defect alone does not verify platform.

Parsed comparison: coreProduct conflict: Amazon rio, eBay rio and; coreGame conflict: Amazon rio, eBay rio and

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.

### B08D7DX16N / 257642438760

Source `matching_intelligence_receiving_outcomes` / `a621a8e9-0dac-4113-b55e-3d4a798dc1fc`; 2026-08-08 00:18:41.41121+00; Tier B; title replay **non-match**.

Amazon: NBA 2K21 Mamba Forever Edition - PlayStation 5 Mamba Forever Edition [video game]

eBay: NBA 2K21 Mamba Forever Edition - Sony PlayStation 5 Brand New And Sealed

Amazon repeats Mamba Forever Edition; eBay states it once followed by condition wording. Duplicate qualifier handling and leftover and contaminate core; edition agreement is explicit.

Parsed comparison: coreProduct conflict: Amazon nba mamba forever edition mamba forever, eBay nba mamba forever edition and; coreGame conflict: Amazon nba 2k21 mamba forever edition mamba forever, eBay nba 2k21 mamba forever edition and

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

Stored snapshot `4bc1e7a7-7dab-4c39-929e-77e0f9d37492` (2026-07-28T03:06:28.232718+00:00): Game Name ['Nba 2k21 Mamba Forever Edition']; description retained; separate richer-input replay **non-match**. coreProduct conflict: Amazon nba mamba forever edition mamba forever, eBay nba mamba forever edition and; coreGame conflict: Amazon nba 2k21 mamba forever edition mamba forever, eBay nba 2k21 mamba forever edition and

Exact-pair certification: **not established**. Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.

### B099JL5K7P / 257662179064

Source `matching_intelligence_receiving_outcomes` / `8b10fb04-0442-421f-ac85-4b83c2237609`; 2026-09-09 01:16:56.790496+00; Tier B; title replay **non-match**.

Amazon: Nerf Legends - Nintendo Switch

eBay: New Nerf Legends (Nintendo Switch)

Leading New is retained before Nerf Legends. Both titles name Nintendo Switch; this is condition-token extraction, not the previously reviewed PS5 pair.

Parsed comparison: coreProduct conflict: Amazon nerf legends, eBay new nerf legends; coreGame conflict: Amazon nerf legends, eBay new nerf legends

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

Stored snapshot `8a66517c-455d-4688-a28a-7bd83e21979a` (2026-08-30T14:59:00.69352+00:00): Game Name ['Nerf Legends']; description retained; separate richer-input replay **non-match**. coreProduct conflict: Amazon nerf legends, eBay new nerf legends; coreGame conflict: Amazon nerf legends, eBay new nerf legends

Exact-pair certification: **not established**. Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.

### B001VLFCXW / 227432986138

Source `matching_intelligence_receiving_outcomes` / `ec59476c-8dbb-4040-85b1-37fe658e98a3`; 2026-08-12 14:24:53.264872+00; Tier E; title replay **non-match**.

Amazon: The Bigs 2 - Nintendo Wii

eBay: The BIGS - Albert Pujols 2K Sports Nintendo Wii 2007 - New & Sealed

The Bigs 2 target versus The BIGS, Albert Pujols, 2007 listing is an apparent different installment. Parser also mistakes a year for installment, but physical/reference truth is not established.

Parsed comparison: coreProduct conflict: Amazon the bigs, eBay the bigs albert pujols 2k sports; coreGame conflict: Amazon the bigs 2, eBay the bigs albert pujols 2k sports 2007; installment conflict: Amazon 2, eBay 2007

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

Stored snapshot `8c7b4823-bf16-4f49-ba3c-c863105ebd7f` (2026-08-05T02:42:03.297878+00:00): Game Name ['Bigs']; description retained; separate richer-input replay **non-match**. coreProduct conflict: Amazon the bigs, eBay the bigs albert pujols 2k sports; coreGame conflict: Amazon the bigs 2, eBay the bigs albert pujols 2k sports

Exact-pair certification: **not established**. Stored titles expose a material ambiguity; receipt does not resolve exact retail package/reference truth.

### B0C5RZRG44 / 227237575535

Source `matching_intelligence_receiving_outcomes` / `0676ee57-56c0-4995-b2f5-93cef13745f7`; 2026-08-10 15:03:49.4408+00; Tier B; title replay **non-match**.

Amazon: Mortal Kombat 1 Premium Edition - Xbox Series X [video game]

eBay: Mortal Kombat 1 Premium Edition - Xbox Series X, New Xbox Series X Video Games

New Xbox Series X Video Games remains after Mortal Kombat 1 Premium Edition. Edition and installment agree; seller suffix contaminates core.

Parsed comparison: coreProduct conflict: Amazon mortal kombat, eBay mortal kombat new video games; coreGame conflict: Amazon mortal kombat 1, eBay mortal kombat 1 new video games

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

Stored snapshot `0eb42164-96b7-4349-906c-2cffc783f092` (2026-08-04T04:33:31.848153+00:00): Game Name ['Mortal Kombat 1 Premium Edition - Xbox Series X']; description retained; separate richer-input replay **non-match**. coreProduct conflict: Amazon mortal kombat, eBay mortal kombat new video games; coreGame conflict: Amazon mortal kombat 1, eBay mortal kombat 1 new video games

Exact-pair certification: **not established**. Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.

### B09C1167RV / 146683357870

Source `matching_intelligence_receiving_outcomes` / `11bd6808-87e8-48e6-97ed-e3b86c642839`; 2026-07-25 17:22:55.750072+00; Tier B; title replay **non-match**.

Amazon: Street Outlaws 2: Winner Takes All (Xbox Series X/) [Video Game] Xbox One / Xbox Series X

eBay: Street Outlaws 2: Winner Takes All for Xbox One and Xbox Series X Brand New

for Xbox One and Xbox Series X leaves for and in Street Outlaws 2. Both full titles supply the same subtitle and platforms; platform conjunction is not identity.

Parsed comparison: coreProduct conflict: Amazon street outlaws winner takes all, eBay street outlaws winner takes all for and; coreGame conflict: Amazon street outlaws 2 winner takes all, eBay street outlaws 2 winner takes all for and

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

Stored snapshot `fdf92865-f78f-49c6-af4b-d268a2f0ee33` (2026-07-19T15:00:57.271772+00:00): Game Name unavailable; description retained; separate richer-input replay **non-match**. coreProduct conflict: Amazon street outlaws winner takes all, eBay street outlaws winner takes all for and; coreGame conflict: Amazon street outlaws 2 winner takes all, eBay street outlaws 2 winner takes all for and

Exact-pair certification: **not established**. Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.

### B09GJP8BPZ / 168541241306

Source `matching_intelligence_receiving_outcomes` / `ff742667-021e-4396-b628-e50b1dff1bc8`; 2026-08-01 00:50:52.430436+00; Tier E; title replay **non-match**.

Amazon: Fortnite Minty Legends Pack(code in Box)

eBay: Fortnite Minty Legends Pack (Nintendo Switch) NEW Sealed Physical

Reference explicitly says code in Box, while listing says Physical. Physical packaging can contain a download code, so this is unresolved wording, not verified media contradiction.

Parsed comparison: coreProduct conflict: Amazon fortnite minty legends pack code in box, eBay fortnite minty legends pack physical; coreGame conflict: Amazon fortnite minty legends pack code in box, eBay fortnite minty legends pack physical

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Stored titles expose a material ambiguity; receipt does not resolve exact retail package/reference truth.

### B07J32LSJ5 / 227426884063

Source `matching_intelligence_receiving_outcomes` / `df416b4e-33f2-4793-8e8a-70312fa3e2e7`; 2026-08-12 14:21:49.520992+00; Tier B; title replay **non-match**.

Amazon: Hello Neighbor: Hide & Seek - Nintendo Switch

eBay: Hello Neighbor: Hide & Seek - Nintendo Switch, New Nintendo Switch Video Games

New Nintendo Switch Video Games remains after Hello Neighbor Hide & Seek. Product subtitle agrees; repeated platform/catalog wording causes the conflict.

Parsed comparison: coreProduct conflict: Amazon hello neighbor hide and seek, eBay hello neighbor hide and seek new video games; coreGame conflict: Amazon hello neighbor hide and seek, eBay hello neighbor hide and seek new video games

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.

### B071Y1RXHG / 318413208917

Source `matching_intelligence_receiving_outcomes` / `2e58df3c-1992-4e03-852b-c790bc03a799`; 2026-06-14 22:35:26.342567+00; Tier B; title replay **non-match**.

Amazon: Star Wars Battlefront II - Xbox One

eBay: Star Wars Battlefront II (Xbox One) – Sealed – EA / DICE

EA / DICE follows matching Battlefront II titles. This is likely publisher metadata, but a different transaction under the same game has a documented wrong-item receipt; title agreement alone is not physical truth. Exact order-problem note documents seller replacement resolving an earlier wrong-product exception; current correct_item records the replacement, not proof of the original delivered listing identity.

Parsed comparison: coreProduct conflict: Amazon star wars battlefront, eBay star wars battlefront ea dice; coreGame conflict: Amazon star wars battlefront 2, eBay star wars battlefront 2 ea dice

Receipt evidence: correct_item / unavailable. A linked order-problem record exists; review the retained exact record.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.

### B00AXI9WFS / 318571029833

Source `matching_intelligence_receiving_outcomes` / `74c55b1b-2c50-4637-86e8-7c2199049be1`; 2026-08-08 01:33:14.584219+00; Tier E; title replay **non-match**.

Amazon: DISNEY INFINITY Starter Pack Xbox 360

eBay: Xbox 360 Disney Infinity Starter Pack 1.0 & Accessories Lot New/Sealed

Disney Infinity Starter Pack with 1.0 and Accessories Lot adds generation/contents absent from target. Receipt cannot establish whole-lot retail parity.

Parsed comparison: coreProduct conflict: Amazon disney infinity starter pack, eBay disney infinity starter pack and accessories lot; coreGame conflict: Amazon disney infinity starter pack, eBay disney infinity starter pack 1.0 and accessories lot

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

Stored snapshot `a00d3f46-2b59-4218-b7cd-82bb807925c5` (2026-07-21T19:31:29.879526+00:00): Game Name ['Disney Infinity']; description retained; separate richer-input replay **non-match**. coreProduct conflict: Amazon disney infinity starter pack, eBay disney infinity starter pack and accessories lot; coreGame conflict: Amazon disney infinity starter pack, eBay disney infinity starter pack 1.0 and accessories lot

Exact-pair certification: **not established**. Stored titles expose a material ambiguity; receipt does not resolve exact retail package/reference truth.

### B00I6E6SH6 / 278220244277

Source `matching_intelligence_receiving_outcomes` / `0bd5d72a-f5d7-434f-bfe6-c47fe7273f89`; 2026-08-08 01:17:16.447028+00; Tier E; title replay **non-match**.

Amazon: Minecraft – Xbox One [video game]

eBay: NEW Minecraft Starter Collection Xbox One Game 700 Minecoins Included. Sealed.

Minecraft versus Starter Collection plus 700 Minecoins leaves expanded-package identity unverified. Do not invent Base or assume codes/contents are equal.

Parsed comparison: coreProduct conflict: Amazon minecraft, eBay new minecraft starter collection minecoins included; coreGame conflict: Amazon minecraft, eBay new minecraft starter collection 700 minecoins included

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

Stored snapshot `d9d38a7d-4171-4587-b6c3-d5a8c07e2717` (2026-07-28T18:28:51.623771+00:00): Game Name ['Minecraft']; description retained; separate richer-input replay **non-match**. coreProduct conflict: Amazon minecraft, eBay new minecraft starter collection minecoins included; coreGame conflict: Amazon minecraft, eBay new minecraft starter collection 700 minecoins included

Exact-pair certification: **not established**. Stored titles expose a material ambiguity; receipt does not resolve exact retail package/reference truth.

### B08HTHJ9L2 / 158136497383

Source `matching_intelligence_receiving_outcomes` / `8f04afc0-f67d-4ddf-9708-88c9ae9cdd31`; 2026-08-12 14:13:01.07701+00; Tier E; title replay **non-match**.

Amazon: Riders Republic PlayStation 4 Standard Edition with free upgrade to the digital PS5 version

eBay: Riders Republic Limited Edition - Sony PlayStation 4

Reference Standard Edition versus listing Limited Edition is an explicit edition contradiction. The conflict is warranted on stored text; wrong linkage versus seller error is unknown.

Parsed comparison: coreProduct conflict: Amazon riders republic with free upgrade to the digital version, eBay riders republic; coreGame conflict: Amazon riders republic with free upgrade to the digital version, eBay riders republic; edition conflict: Amazon Standard Edition, eBay Limited Edition

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Stored titles expose a material ambiguity; receipt does not resolve exact retail package/reference truth.

### B00ZE360GG / 236860486717

Source `matching_intelligence_receiving_outcomes` / `dda46c41-2878-49e7-b67a-dcab8ee61121`; 2026-06-14 22:59:30.294662+00; Tier B; title replay **non-match**.

Amazon: Just Dance 2016 - Wii

eBay: Just Dance 2016 -Nintendo Wii Brand New NIB Factory Sealed

NIB remains in Just Dance 2016 core despite Brand New and Factory Sealed context. A condition abbreviation is being treated as a product qualifier.

Parsed comparison: coreProduct conflict: Amazon just dance, eBay just dance nib; coreGame conflict: Amazon just dance 2016, eBay just dance 2016 nib

Receipt evidence: correct_item / unavailable. No linked order-problem record returned in the bounded read.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.

### B003OZZJGS / listing ID unavailable

Source `purchase_items` / `c37228b5-0e2d-49f3-97ea-256a1489aba9`; 2026-05-19 06:47:56.04207+00; Tier C; title replay **non-match**.

Amazon: Gold's Gym Dance Workout - Nintendo Wii

eBay: Gold's Gym Dance WorkOut

Gold's Gym Dance WorkOut is camel-split to work out, unlike Workout on the reference. This is a text normalization defect. Exact listing ID and original snapshot are absent.

Parsed comparison: coreProduct conflict: Amazon gold s gym dance workout, eBay gold s gym dance work out; coreGame conflict: Amazon gold s gym dance workout, eBay gold s gym dance work out

No linked current receiving outcome was returned. Purchase workflow status alone is the positive source.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Purchase ASIN/workflow linkage does not establish an independently reviewed exact pair.

### B0794QSXP5 / 177913803344-10080059012115

Source `purchase_items` / `ad93a9dc-396e-4112-8320-cf302b2e57f3`; 2026-05-22 01:49:29.766565+00; Tier C; title replay **non-match**.

Amazon: Dragon Ball Fighterz - Xbox One

eBay: New Dragon Ball FighterZ (Microsoft Xbox One, 2018)

Dragon Ball FighterZ has a leading New condition token left in core. The product/platform text agrees, but no receipt or explicit pair review verifies identity.

Parsed comparison: coreProduct conflict: Amazon dragon ball fighterz, eBay new dragon ball fighterz; coreGame conflict: Amazon dragon ball fighterz, eBay new dragon ball fighterz

No linked current receiving outcome was returned. Purchase workflow status alone is the positive source.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Purchase ASIN/workflow linkage does not establish an independently reviewed exact pair.

### B07L73DW8M / 306820109491-10084336797204

Source `purchase_items` / `7a9769e0-016a-47f4-b84e-9e1a03756c91`; 2026-09-08 22:38:41.580427+00; Tier C; title replay **non-match**.

Amazon: Mortal Kombat 11 (Nintendo Switch) [video game]

eBay: Mortal Kombat 11 Nintendo Switch Brand New Sealed Fighting Game MK11 2019 WB

Mortal Kombat 11 has MK11, Fighting Game, year and WB suffixes. Metadata pollution is plausible; exact edition and full listing evidence remain incomplete.

Parsed comparison: coreProduct conflict: Amazon mortal kombat, eBay mortal kombat 11 fighting game mk11 2019 wb; coreGame conflict: Amazon mortal kombat 11, eBay mortal kombat 11 fighting game mk11 2019 wb

No linked current receiving outcome was returned. Purchase workflow status alone is the positive source.

Stored snapshot `717640a4-c45b-4649-be33-b9ce01ccfa26` (2026-09-08T19:34:11.246092+00:00): Game Name ['Mortal Kombat 11']; description retained; separate richer-input replay **non-match**. coreProduct conflict: Amazon mortal kombat, eBay mortal kombat game mk11 wb; coreGame conflict: Amazon mortal kombat 11, eBay mortal kombat 11 game mk11 wb

Exact-pair certification: **not established**. Purchase ASIN/workflow linkage does not establish an independently reviewed exact pair.

### B01JCV5Q9C / 168550477139-10083883957722

Source `purchase_items` / `79612149-b2e7-4178-9434-29b071d73581`; 2026-09-06 00:00:59.389656+00; Tier C; title replay **non-match**.

Amazon: Warhammer: End Times - Vermintide - PlayStation 4

eBay: THQ Nordic Warhammer: The End Times - Vermintide PS4 M NTSC-U/C 2016

THQ Nordic and rating/region/year surround Warhammer Vermintide; The End Times also differs from reference End Times. Missing authoritative source context prevents blanket removal.

Parsed comparison: coreProduct conflict: Amazon warhammer end times vermintide, eBay thq nordic warhammer the end times vermintide m ntsc u c; coreGame conflict: Amazon warhammer end times vermintide, eBay thq nordic warhammer the end times vermintide m ntsc u c 2016

No linked current receiving outcome was returned. Purchase workflow status alone is the positive source.

Stored snapshot `941de9a4-47fa-456f-b5ee-e3f8b778b3fe` (2026-09-05T23:42:23.996399+00:00): Game Name ['Warhammer: The End Times - Vermintide']; description retained; separate richer-input replay **non-match**. coreProduct conflict: Amazon warhammer end times vermintide, eBay warhammer the end times vermintide; coreGame conflict: Amazon warhammer end times vermintide, eBay warhammer the end times vermintide

Exact-pair certification: **not established**. Purchase ASIN/workflow linkage does not establish an independently reviewed exact pair.

### B00FM5IY4W / listing ID unavailable

Source `purchase_items` / `3c9baa50-9bf2-4d6b-87e8-3127de2a45a2`; 2026-05-19 06:47:46.2362+00; Tier E; title replay **non-match**.

Amazon: Forza Motorsport 5

eBay: Forza Motorsport 5 Day One Edition

Forza Motorsport 5 target omits Day One Edition which is explicit on eBay. Missing exact listing ID prevents edition adjudication; do not invent Standard.

Parsed comparison: coreProduct conflict: Amazon forza motorsport, eBay forza motorsport day one; coreGame conflict: Amazon forza motorsport 5, eBay forza motorsport 5 day one

No linked current receiving outcome was returned. Purchase workflow status alone is the positive source.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Stored titles expose a material ambiguity; receipt does not resolve exact retail package/reference truth.

### B071G8WL76 / 397601134474-10080519399012

Source `purchase_items` / `1fde8f15-ba71-4f7e-b6ae-d54a4aad5991`; 2026-05-22 01:52:00.046035+00; Tier E; title replay **non-match**.

Amazon: Marvel Super Heroes 2: Deluxe Edition

eBay: Marvel Super Heroes 2: Deluxe Edition Giant Man LEGO Inside Xbox One Video Game

Marvel Super Heroes 2 Deluxe includes Giant Man LEGO in the listing. Bare reference title does not prove identical included contents.

Parsed comparison: coreProduct conflict: Amazon marvel super heroes, eBay marvel super heroes giant man lego inside; coreGame conflict: Amazon marvel super heroes 2, eBay marvel super heroes 2 giant man lego inside

No linked current receiving outcome was returned. Purchase workflow status alone is the positive source.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Stored titles expose a material ambiguity; receipt does not resolve exact retail package/reference truth.

### B01AC3ZD06 / listing ID unavailable

Source `purchase_items` / `75d686a7-dbe1-43b8-8fb6-77098bef98f2`; 2026-05-19 06:49:56.82134+00; Tier E; title replay **non-match**.

Amazon: Nintendo Selects: Super Mario 3D World - Wii U Standard Edition

eBay: Super Mario 3D World

Nintendo Selects is explicit on reference and absent in supplier name; no exact item ID. Neither same-game wording nor purchase status certifies retail print.

Parsed comparison: coreProduct conflict: Amazon selects super mario 3d world, eBay super mario 3d world; coreGame conflict: Amazon selects super mario 3d world, eBay super mario 3d world

No linked current receiving outcome was returned. Purchase workflow status alone is the positive source.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Stored titles expose a material ambiguity; receipt does not resolve exact retail package/reference truth.

### B09W39YNQV / 115528942546-10080657862212

Source `purchase_items` / `df8dbf13-4bd9-4b87-a871-b7d33fb20b10`; 2026-05-22 01:52:55.97488+00; Tier C; title replay **non-match**.

Amazon: Teenage Mutant Ninja Turtles Cowabunga Collection NSW

eBay: Konami Teenage Mutant Ninja Turtles Cowabunga (NSW)

Cowabunga Collection NSW versus shortened Cowabunga NSW lacks full retail title and platform normalization. Purchase linkage is not independent evidence that the collection matches.

Parsed comparison: coreProduct conflict: Amazon teenage mutant ninja turtles cowabunga collection nsw, eBay konami teenage mutant ninja turtles cowabunga nsw; coreGame conflict: Amazon teenage mutant ninja turtles cowabunga collection nsw, eBay konami teenage mutant ninja turtles cowabunga nsw

No linked current receiving outcome was returned. Purchase workflow status alone is the positive source.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Purchase ASIN/workflow linkage does not establish an independently reviewed exact pair.

### B0C9VW1KGR / listing ID unavailable

Source `purchase_items` / `3494d8cb-140b-4bda-aefe-7fb2168019b5`; 2026-05-19 06:50:09.299911+00; Tier C; title replay **non-match**.

Amazon: EA SPORTS FC 24 - Nintendo Switch

eBay: FC 24

EA SPORTS FC 24 versus FC 24 is plausibly brand omission, but no exact listing/platform information on eBay side. Remains workflow evidence.

Parsed comparison: coreProduct conflict: Amazon ea sports fc, eBay fc; coreGame conflict: Amazon ea sports fc 24, eBay fc 24

No linked current receiving outcome was returned. Purchase workflow status alone is the positive source.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Purchase ASIN/workflow linkage does not establish an independently reviewed exact pair.

### B0060ZN5T2 / 256885967289-10080182715420

Source `purchase_items` / `87e3c727-5ede-46d4-83c9-3038e95fe257`; 2026-05-19 06:56:10.531307+00; Tier C; title replay **non-match**.

Amazon: NEW Just Dance 3 Wii (Videogame Software)

eBay: NEW Just Dance 3 ( Nintendo Wii, 2011 )

Amazon NEW and Videogame Software contaminate the target core for Just Dance 3. The condition/category wording is not an installment; exact physical match remains unverified.

Parsed comparison: coreProduct conflict: Amazon new just dance videogame software, eBay new just dance; coreGame conflict: Amazon new just dance 3 videogame software, eBay new just dance 3

No linked current receiving outcome was returned. Purchase workflow status alone is the positive source.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Purchase ASIN/workflow linkage does not establish an independently reviewed exact pair.

### B071Y1RXHG / 318227533133-10081584746819

Source `purchase_items` / `708e5bdf-3b38-459e-8f04-8c79488fca0e`; 2026-05-19 06:56:34.30321+00; Tier D; title replay **non-match**.

Amazon: Star Wars Battlefront II - Xbox One

eBay: Star Wars Battlefront II (Xbox One) – Sealed – EA / DICE

Current receipt explicitly records wrong_item/wrong_product. Supplier title still names the target product. The receipt contradicts a successful purchase assertion, not necessarily the advertised listing identity. Seller substitution versus mistaken order cannot be inferred without notes; Battlefront notes explicitly document wrong delivery/refund.

Parsed comparison: coreProduct conflict: Amazon star wars battlefront, eBay star wars battlefront ea dice; coreGame conflict: Amazon star wars battlefront 2, eBay star wars battlefront 2 ea dice

Receipt evidence: wrong_item / wrong_product. A linked order-problem record exists; review the retained exact record.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Documented same-ASIN/listing contradictory evidence; physical receipt errors do not prove the listing text was wrong.

### B0043B5SKE / 188586734114-10083715805019

Source `purchase_items` / `fbe69061-f499-4ea2-9c10-be5065e11067`; 2026-08-01 11:01:21.121494+00; Tier D; title replay **non-match**.

Amazon: Fighters Uncaged - Xbox 360

eBay: Fighters Uncaged Kinect XBOX 360 Factory Sealed Brand New Video Game

Current receipt explicitly records wrong_item/wrong_product. Supplier title still names the target product. The receipt contradicts a successful purchase assertion, not necessarily the advertised listing identity. Seller substitution versus mistaken order cannot be inferred without notes; Battlefront notes explicitly document wrong delivery/refund.

Parsed comparison: coreProduct conflict: Amazon fighters uncaged, eBay fighters uncaged kinect; coreGame conflict: Amazon fighters uncaged, eBay fighters uncaged kinect

Receipt evidence: wrong_item / wrong_product. A linked order-problem record exists; review the retained exact record.

Stored snapshot `d1632267-3901-48e9-a613-7ef3e2d09800` (2026-08-01T04:27:30.631603+00:00): Game Name ['Fighters Uncaged']; description retained; separate richer-input replay **non-match**. coreProduct conflict: Amazon fighters uncaged, eBay fighters uncaged kinect; coreGame conflict: Amazon fighters uncaged, eBay fighters uncaged kinect

Exact-pair certification: **not established**. Documented same-ASIN/listing contradictory evidence; physical receipt errors do not prove the listing text was wrong.

### B002SKDIKE / 800354779127-10086617767027

Source `purchase_items` / `be6c1094-4927-4258-b5fd-2c3872ab5edf`; 2026-07-20 04:00:56.308576+00; Tier D; title replay **match**.

Amazon: The Stronghold Collection - PC

eBay: The Stronghold Collection (PC, 2009) BRAND NEW SEALED

Current receipt explicitly records wrong_item/non_north_american_version. Supplier title still names the target product. The receipt contradicts a successful purchase assertion, not necessarily the advertised listing identity. Seller substitution versus mistaken order cannot be inferred without notes; Battlefront notes explicitly document wrong delivery/refund.

Parsed comparison: Identity matched or unknown; unknown fields are not positive evidence.

Receipt evidence: wrong_item / non_north_american_version. A linked order-problem record exists; review the retained exact record.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Documented same-ASIN/listing contradictory evidence; physical receipt errors do not prove the listing text was wrong.

### B0060ZN5T2 / 287293393612-10080515189720

Source `purchase_items` / `29b79864-0616-439a-b5c6-c4d1f4f9ccba`; 2026-05-19 06:56:29.790466+00; Tier C; title replay **non-match**.

Amazon: NEW Just Dance 3 Wii (Videogame Software)

eBay: Just Dance 3 - Nintendo Wii

Same Just Dance 3 reference has NEW/Videogame Software noise, while this supplier names Just Dance 3 Wii plainly. Reference extraction defect, not verified pair certification.

Parsed comparison: coreProduct conflict: Amazon new just dance videogame software, eBay just dance; coreGame conflict: Amazon new just dance 3 videogame software, eBay just dance 3

No linked current receiving outcome was returned. Purchase workflow status alone is the positive source.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Purchase ASIN/workflow linkage does not establish an independently reviewed exact pair.

### B0B359B45Q / 188900025021-10087855786827

Source `purchase_items` / `445a3ae8-35c6-4dce-a192-3a429cc6dd4e`; 2026-09-08 04:00:57.753383+00; Tier E; title replay **non-match**.

Amazon: Little League World Series PS4

eBay: Little League World Series Baseball 2022 PS4 Multiplayer Manual Included

Little League reference omits Baseball 2022; supplier annual identity must not be erased merely to agree. Stored exact catalog version missing.

Parsed comparison: coreProduct conflict: Amazon little league world series, eBay little league world series baseball multiplayer manual included; coreGame conflict: Amazon little league world series, eBay little league world series baseball 2022 multiplayer manual included

No linked current receiving outcome was returned. Purchase workflow status alone is the positive source.

Stored snapshot `4ef7c987-8441-4133-9ea6-fcd60b8bb77c` (2026-09-08T03:07:42.576242+00:00): Game Name ['Little League World Series Baseball 2022']; description retained; separate richer-input replay **non-match**. coreProduct conflict: Amazon little league world series, eBay little league world series baseball manual included; coreGame conflict: Amazon little league world series, eBay little league world series baseball 2022 manual included

Exact-pair certification: **not established**. Stored titles expose a material ambiguity; receipt does not resolve exact retail package/reference truth.

### B0B6JMXKKR / 298629862125-10084785225117

Source `purchase_items` / `b9d4758b-3706-4709-813e-9b46933ea779`; 2026-09-11 04:01:03.643569+00; Tier C; title replay **non-match**.

Amazon: FIFA 23 Legacy Edition - Nintendo Switch

eBay: EA Sports FIFA 23 Legacy Edition - Nintendo Switch - Soccer Sports E

FIFA 23 Legacy title agrees but publisher/sports/rating syntax remains in core. Full metadata/correction evidence is missing.

Parsed comparison: coreProduct conflict: Amazon fifa legacy, eBay ea sports fifa legacy edition soccer sports e; coreGame conflict: Amazon fifa 23 legacy, eBay ea sports fifa 23 legacy edition soccer sports e

No linked current receiving outcome was returned. Purchase workflow status alone is the positive source.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Purchase ASIN/workflow linkage does not establish an independently reviewed exact pair.

### B00104KJ4M / listing ID unavailable

Source `purchase_items` / `d298f2a4-d182-4e4c-a1a7-d544ab58ab4a`; 2026-05-19 06:51:17.429233+00; Tier E; title replay **non-match**.

Amazon: Lego Indiana Jones

eBay: Lego Indiana Jones: The Original Adventures

Lego Indiana Jones reference omits The Original Adventures. No exact item ID or authoritative catalog detail settles which game; do not treat substring agreement as identity.

Parsed comparison: coreProduct conflict: Amazon lego indiana jones, eBay lego indiana jones the original adventures; coreGame conflict: Amazon lego indiana jones, eBay lego indiana jones the original adventures

No linked current receiving outcome was returned. Purchase workflow status alone is the positive source.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Stored titles expose a material ambiguity; receipt does not resolve exact retail package/reference truth.

### B0C7K581PT / listing ID unavailable

Source `purchase_items` / `5216c3d6-eaee-4f52-a097-c56001825489`; 2026-05-19 06:50:41.835877+00; Tier C; title replay **non-match**.

Amazon: Fae Farm - Nintendo Switch (US Version)

eBay: Fae Farm

US Version sits in Fae Farm reference core. eBay omits both platform and region and has no exact ID, so even correcting reference noise cannot certify the pair.

Parsed comparison: coreProduct conflict: Amazon fae farm us version, eBay fae farm; coreGame conflict: Amazon fae farm us version, eBay fae farm

No linked current receiving outcome was returned. Purchase workflow status alone is the positive source.

No linked richer listing snapshot was available for a separate metadata replay; original reference/listing omissions remain unresolved.

Exact-pair certification: **not established**. Purchase ASIN/workflow linkage does not establish an independently reviewed exact pair.

GROUND TRUTH INSUFFICIENT — MANUAL ADJUDICATION REQUIRED
