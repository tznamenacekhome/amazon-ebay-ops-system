# Phase 3B implementation and blocked release review

November 26, 2026. **Release gate FAIL. No push, deployment or production replay.**

## Executive result and stop reason

The scoped platform, attribution, composite-metadata and contextual-keyword changes are implemented in focused local commits. The mandatory text-only shadow review exposed a latent **shared condition-language gap** outside Phase3B's approved corrections. The operator's instruction was: “If the gate identifies a genuine systemic issue outside the approved scope, stop and report it.” Work stopped before release; no listing-specific workaround or unapproved condition-policy expansion was added.

| Original row | Product / exact pair | Retained item-specific disclosure | Proposed shadow result |
|---:|---|---|---|
|50|Star Wars Galaxies Total Experience — eBay128210994247 / ASINB0008EZDDM|“Has some tears in the cello wrap”|Open; condition Pass; no condition review|
|63|Assassin's Creed Rogue — eBay880138368350 / ASINB00N3VNF32|“Has a few holes in seal as shown.”|Open; condition Pass; no condition review|

These are product-specific **textual** disclosures, not testing language, generic advertising or photograph findings. Phase3A correctly preserves them. Existing condition grammar recognizes some singular tear/shrink-wrap and torn/broken/missing-seal expressions, but misses plural tears/cello-wrap and this holes-in-seal construction. Previously, independent name conflicts kept these pairs rejected; the valid name normalization exposes the missing condition guard. Row50 opens at the publisher stage; row63 at the composite stage. Contextual-keyword changes do not cause either promotion.

The safe requirement is at least condition review, not an unsupported automatic New recommendation. Holes must not blindly be called damage: a later fix must distinguish an unqualified seller disclosure from clearly identified normal factory vent holes, negation and conditional/boilerplate text. No photograph review is required or proposed.

Two actual captured failing release regressions now make the blocker reproducible. **437 Python tests run:435 pass, two release guards fail.** All39 disposable PostgreSQL tests and16 frontend/API files pass; TypeScript noEmit passes. Passing component tests do not override this failed end-to-end safety gate.

## Verified production and unchanged operations

Fresh AWS reads at the start and after the blocked review confirm worker183 (`8e37e5f7c68f`) and web238 (`07867ac1c8ef`) remain healthy. Frozen baseline engine/policy files were compared directly against the worker commit. No deployment or AWS schedule change occurred in this task.

The original tab remains Complete on Phase3A run `33c2d3bb-6ffc-52af-855a-36e06e0f9bb6`:558 rows,144 evaluated,409 excluded,five reused/duplicate outcomes, pending0/failed0. Its persisted presentation counts remain **Buy List33 / Closest Excluded73**. No Phase3B job, lease, replay manifest, source import, candidate rescore or opportunity write was initiated. Existing inventory, listings, purchases, orders, source provenance, manual decisions and holds are untouched.

## Unreleased platform policy

Central policy v3 adds **PS / original PlayStation / PS1 / PSX, Dreamcast and Sega CD / Mega-CD / Mega CD** to operator exclusions. Canonical aliases distinguish PS2–PS5, PSP, Vita and Saturn. CD-ROM alone is not Sega CD. Reliable catalog/seed and structured offered-platform fields drive business eligibility; historical description references do not determine the offered platform.

Python/server parity includes106 actual/synthetic cases, plus explicit historical-reference and PC CD-ROM controls. Early catalog/Flipmine exclusion tests cover the new platforms before providers. Actual stale purchasing-action POST tests reject the new ineligible platforms while allowing normal matching-review actions and leaving historical Open status untouched. Existing shared presentation and wholesale policies consume the same central JSON. Prior cartridge exclusions, mixed-media requirements and eligible platforms remain unchanged.

**These changes are local, not live.** No existing opportunity has actually been suppressed by Phase3B. A read-only policy-only model using production data projects:

| Original Flipmine presentation | Verified starting counts | Policy-only model | Actual after task |
|---|---:|---:|---:|
|Buy List|33|31|33 — not deployed|
|Closest Excluded|73|73|73 — not deployed|

Modeled suppression by newly excluded platform:

| Platform | Buy List | Closest Excluded |
|---|---:|---:|
|PS1|1|0|
|Dreamcast|1|0|
|Sega CD|0|0|

The affected modeled Buy List pairs are Gran Turismo2 (eBay168847018534 / B07FYS9TQC, PS1) and Shenmue (eBay880090923440 / B00004S99R, Dreamcast). This is an original-Flipmine presentation comparison, not a full regular-history census. Shared policy coverage is implemented/tested for regular sourcing too, but no global historical scan or reevaluation occurred.

The primary prior Phase3B audit group is **48 ->46 eligible** after removing PS1 rows153 and496. The broader56 identity-audit pool becomes54 eligible. Neither count is a replay authorization or recovery target. Four newly named-compatible frozen pairs remain platform-ineligible and nonactionable. All newly excluded platforms are absent from any proposed live recovery selection; no final live manifest was created because the gate failed.

## Implemented attribution and normalization

Publisher relationships are backed by actual captured fixtures: EA Sports/Electronic Arts, Lucas Arts/LucasArts, Blue Byte/Blue Byte Software, Microsoft/Microsoft Game Studios, Accalim/Acclaim and COSMI corporate attribution. Each accepted role carries observed publisher, complete Game Name, platform and source information. Whole residual-name equality remains mandatory. Publisher relationships do not override wrong installments, conflicting publisher evidence, platform or other product evidence. Simple supported roles do not universally require a GTIN.

Amazon-side COSMI attribution is classified only against a complete offered name, matching platform and corroborating publisher. Existing accepted COSMI controls remain protected. Licensed brands/author credits are not company aliases: Disney Infinity, EA Sports FC, Tom Clancy and Microsoft Flight Simulator are protected; Nickelodeon/Tim Burton variants remain unresolved without separately supported semantics. A component regression caught invalid Publisher=New metadata; reserved-word/franchise guards were tightened, preserving New Super Mario Bros and New Carnival Games.

Composite roles extend the existing typed parser: PC CD/DVD-ROM and computer/video-game descriptors, explicit Windows compatibility wording, corroborated release year and region, bounded packaging/seller words and publisher attribution. The entire named game remains intact. Examples resolved include Extreme Assault's combined CD-ROM/Computer Game/Blue Byte wording, Hip Hop Dance's corroborated genre/track wording, Assassin's Creed Rogue's Game suffix and Suikoden's “& Y-FOLD.” Original conditions, digital/physical content, region and edition checks retain the raw evidence.

Rollercoaster/Roller Coaster is normalized narrowly within Rollercoaster Tycoon, not by general edit distance. Its explicit PC Windows compatibility bracket is a typed OS role. Row280 remains **inventory_snoozed** in the normal frozen pipeline and retains edition/source uncertainty; its historical hold is not bypassed. Myst IV Revelation4 can classify a corroborated repeated trailing installment while preserving the full title/subtitle and installment. Adjacent Suikoden V/5 remains the prior correction; the residual issue was packaging wording. Meaningful numbers, sports years, V3, X-2 and genuine sequels remain protected.

Pandora's Tower's North American wording is classified only with independent region evidence; review/financial concerns remain. Ridge Racer GH lacks sufficient independent packaging corroboration in retained evidence and remains unresolved (also newly ineligible PS1). Unverified seller codes remain unclassified. Dusk Driver/Div­er and MOLOPOLY spelling/package issues are not generally corrected. No broad subtitle/alternate-release relations, token sorting, arbitrary code stripping or Phase3C source model were added.

## Contextual keyword results and retained safeguards

| Case | Bounded correction | Independent protection |
|---|---|---|
|Rune Factory4 Special, row481|Rune inside a corroborated full named game does not imply currency; any separate runes/currency/code offer still blocks|Special/base-release identity uncertainty remains|
|Bejeweled, row438|“match gems” in corroborated puzzle gameplay does not sell gems; other gems occurrences remain blocking|Stock-code/title issues remain unresolved|
|Mario Tennis, row400|“brand we carry” is retailer stock-policy vocabulary, not a carry service|Actual “CARTIRDGE ONLY” disclosure is explicitly recognized as incomplete contents; stock-code/name issues remain|
|Frogger Helmet Chaos, row492|Helmet belongs to the corroborated named software product, not helmet-only merchandise|Full identity, platform and catalog media/edition dispute must still resolve; no game-name alias applied|
|Nintendo Labo, row546|Toy-Con is classified as a named physical kit family, not automatically accessory-only|Mandatory exact-ASIN kit contents review unless existing required-contents proof establishes the configuration; replacements/no-software remain blocked|
|Bejeweled, row504|No exception for condition damage|Written “visible cracks on case” still blocks New purchasing|

Digital currency, services, accessory-only products, demos, missing contents and independent eligibility/financial restrictions stay active. No keyword is globally disabled. Contextual keywords produce **zero additional shadow Open outcomes** beyond the normalization stage. Their diagnostics improve without pretending that incomplete release/package evidence is resolved. Broader generic prose and alternative-release uncertainty remain conservative follow-up work.

## Incremental frozen shadow

Reused the immutable **395 Phase3A captures**. All18 directly relevant actual Phase3B snapshots were identical to existing snapshots after material/economic comparison and were deduplicated. Added13 distinct synthetic platform controls: **408 distinct cases** total. Both materially different historical captures remain retained; no live marketplace enrichment was used.

| Stage | Match / Review / Non-match | Open / Rejected |
|---|---|---|
|Deployed baseline|120 /43 /245|58 /321|
|Platform only|120 /43 /245|49 /330|
|Publisher attribution|125 /43 /240|54 /325|
|Composite metadata / narrow normalization|140 /45 /223|62 /317|
|Contextual keywords|140 /45 /223|62 /317|
|Combined final|140 /45 /223|62 /317|

Every stage also retains24 Dismissed, four Inventory Snoozed and one Watching. The9 baseline Open reductions are intentional platform suppression, including synthetic controls. On the original395 alone, Open47 ->43 (policy) ->56 (combined); these are historical shadow statuses, not live Buy List counts.

All408 original material hashes remain unchanged. Platform-only identity verdicts are unchanged. All21 independently supported mismatches remain Non-match. Previously Open **eligible** controls and protected lifecycles remain protected; ineligible platforms cannot become Open. Twenty core identity verdicts improve to Match (16 eligible, four ineligible), plus two Review outcomes. Thirteen eligible historical shadow Open promotions were reviewed from text/structured evidence; the two unsafe condition outcomes above make the **final gate FAIL**. The other11 are not live purchasing recommendations or approved recovery counts.

Detailed changed-candidate audit (exact IDs, historical landed cost/profit/ROI, independent blocks and unsafe flags): `phase3b_candidate_review_2026-11-26.csv`. Machine-readable six-stage results, assertions, policy model, code/input hashes and blockers: `phase3b_shadow_2026-11-26.json`.

## Tests, commits and release status

- Python:435 passing tests; two newly captured required release regressions failing;437 total. The failing tests remain visible and are not marked expected-failure or weakened to pass.
- Disposable PostgreSQL17:39 passing tests, covering Flipmine persistence/replay/progress and quota/concurrency protection; no production DB or published ports.
- Frontend/API:16 passing files, including106 Python/server policy-parity cases, stale-action suppression and prior compact-reason/UI behavior.
- TypeScript noEmit and whitespace checks passed. No production image build, deployment smoke or authenticated browser verification of Phase3B was attempted after the failed gate.

Focused local implementation commits: platform `950daeb`; publisher `046f747`; composite/narrow normalization `97d3a57`; meaningful-New protection `a023564`; contextual keywords `0683cf8`. Additional gate fixtures/report and stale-action tests are separate review artifacts. **No commits from this task were pushed.** Unrelated uncommitted reports and the MF oversale document remain preserved.

API consumption in this task: eBay0, Amazon0, Keepa0, photograph0. Only bounded operational-data/AWS reads and local tests/shadows ran. No production candidate/evaluation writes, provider enrichment, schedule changes, source reimport, fresh export import, inventory/listing changes, purchase, bid or offer. There are **zero newly actionable production opportunities**. Replay manifest/outcomes and post-replay counts: not applicable; release stopped.

## Required follow-up and fresh-export validation

Separately scope a reusable **condition-disclosure grammar correction**, not two listing exceptions. Cover actual plural tears/cello-cellophane-wrap wording and puncture/holes-in-seal disclosures with product scope, negation, conditional/other-merchandise safeguards and explicit normal factory-vent controls. Preserve generic testing neutrality, written cracks/opening/use/missing-seal/contents safeguards, operator decisions and Phase3A text extraction. Establish at least review when seal condition cannot be safely established; do not label all holes as confirmed damage.

Then rerun all437 regressions plus the same408 frozen shadow with the additional condition controls. Reinspect every newly Match/Open text outcome. Recheck the baseline, platform eligibility and current holds, exclude unavailable/independently blocked pairs, and prepare a deterministic manifest only after the gate passes. No automatic replay of46/48/54/56/265/558 rows or regular historical sourcing.

After a separately cleared release, validate a **small manually initiated fresh export** through the existing import/checkpoint workflow. Plan quota first; deduplicate listing/ASIN pairs and details, reuse only sufficiently fresh evidence, include positive and negative attribution/composite/keyword/platform examples, verify pre-provider exclusions and full normal purchasing safeguards, then compare persistence/progress/duplicates and Buy List/Closest Excluded outcomes. Do not reimport the original558-row tab, discover new tabs automatically, manufacture live marketplace listings, or submit purchases/offers to test the feature. Historical shadow margins are not current resale clearance.
