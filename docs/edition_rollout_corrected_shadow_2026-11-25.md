# Corrected edition rollout: release gate remains FAILED

No commit, push, deployment, migration or production reevaluation was performed.
The attached task explicitly says to stop before deployment if another material
issue is discovered. Individual inspection of the remaining new Open outcomes
found an unresolved required-contents issue for Spirit Camera. The original
shadow capture and failed-gate report remain unchanged for comparison.

## Corrections made locally

The approved Standard omission, conservative re-release packaging, special-edition
corroboration, typed metadata and Browse remaining-quantity changes remain.
Thresholds, demand, fees, quotas, provider priorities, cache lifetimes and
schedules were not changed.

- The existing condition detector missed articles, modifiers and alternative word
  order. It now recognizes the captured missing-plastic-seal, seal-damage and
  cracked-case disclosures, plus punched UPC. HTML tags are removed before
  detection. Negative/conditional context is retained. Brand New classification
  cannot override contradictory disclosures.
- Existing static condition checks now retain review for plastic tears and
  stretched wrap. Specific persisted review reasons keep these out of automatic
  purchasing. Diagnostics distinguish confirmed unacceptable, requires review,
  affirmative New evidence and missing evidence.
- Wii Fit's ordinary edition clearance no longer resolves its known exact package
  ambiguity when the catalog lacks a manifest or explicit software-only
  configuration. This does not assert this ASIN necessarily includes a board.
  Known manifests remain enforced; confirmed missing required components conflict.
- Features/description adjectives such as Enhanced remake do not independently
  establish Enhanced Edition. Genuine named prose, typed Edition values and
  existing bare Enhanced product-title behavior remain supported. The existing
  Witcher outcome was preserved.
- An anaphoric description of an already named substantive edition, such as
  this special edition referring to Ultimate, no longer adds a competing SKU.
  Explicit Special Edition evidence remains active. Features/descriptions
  were not globally ignored.
- Complete Edition appearing only in Features is retained as ambiguity rather
  than confirmed retail-SKU conflict. Both Pandora's Tower rows remain review:
  matching UPC/title/platform do not resolve the exact meaning of this field.
  Explicit named Complete Edition remains substantive.
- Closest Excluded reuses the existing list pipeline. Condition reviews require
  active availability, passing recorded shipping/profit/ROI, and independent
  hold/seller/identity checks. Confirmed condition failures cannot pass this
  gate. Review results are not buying recommendations.

## Nine actual listing regressions

The fixture file tests/fixtures/edition_shadow_failures_20261124.json retains
the actual captured candidate/seed evidence and complete descriptions.

| Listing / ASIN | First patch | Corrected |
|---|---|---|
| 880128084759 / B003O6N2NY — Tiger Woods | Open | Rejected; confirmed seal damage/cracked case |
| 336887119682 / B00006JBS4 — Legends of Wrestling II | Open | Rejected; confirmed missing plastic seal |
| 287741926297 / B00DNGQTFI — Dragon Ball Z | Open | Rejected; shrink-wrap damage review |
| 840120275430 / B000MAFXTQ — Samurai Warriors | Open | Rejected; disclosed packaging flaws review |
| 147693336106 / B000VJRU44 — Wii Fit | Open | Rejected; accessory contents not corroborated |
| 407348790546 / B00B2QL2Y4 — Pandora's Tower | Non-match | Review; Features-only Complete Edition unresolved |
| 257841605061 / B00B2QL2Y4 — Pandora's Tower | Non-match | Review; Features-only Complete Edition unresolved |
| 314068158958 / B000B69E9G — Resident Evil 4 | Identity review | Identity match; dismissed lifecycle preserved |
| 168877999113 / B01KGR9QJC — The Crew Ultimate | Identity review | Identity match; dismissed lifecycle preserved |

All nine actual-pair regressions pass, with additional negation, real named
edition conflicts, bare Enhanced names and missing-condition tests. Existing
protected numeric titles, scoped manual decisions, evidence hashes and other
purchasing safeguards retain regression coverage.

## Same-input 97-opportunity shadow

The original November 24 approximately 9:59 p.m. Pacific capture was reused.
HEAD, first patch and corrected patch use the same settings, pricing, owned
units, reviews, seller context and operational history. No provider calls or
production scoring writes were used.

| All 97 distinct opportunities | HEAD | First patch | Corrected |
|---|---:|---:|---:|
| Identity matches | 16 | 53 | 54 |
| Continued identity reviews | 71 | 34 | 35 |
| Confirmed identity non-matches | 10 | 10 | 8 |
| Shadow Open | 0 | 35 | 30 |
| Rejected lifecycle | 80 | 45 | 50 |
| Dismissed lifecycle | 15 | 15 | 15 |
| Inventory snoozed | 2 | 2 | 2 |

| Corrected sample (samples overlap) | Matches | Reviews | Non-matches | Open |
|---|---:|---:|---:|---:|
| Flipmine 62 | 31 | 31 | 0 | 25 |
| Initial 32 | 28 | 4 | 0 | 23 |
| Regular catalog 6 | 5 | 1 | 0 | 5 |
| Re-release sample 8 | 3 | 2 | 3 | 0 |
| Omitted substantive edition sample 2 | 0 | 1 | 1 | 0 |
| Previously accepted sample 20 | 15 | 1 | 4 | 0 |

The accepted sample regains its HEAD identity distribution and retains its
same-input lifecycle distribution. Both identified regressions are resolved.
No new non-match relative to the first patch remains.

The 62-pair cohort has 26 specific review reasons passing the scoped near-miss
business gate on captured data: 24 edition/contents and 2 condition. These
are not 26 verified presented Closest Excluded rows. Fresh evidence and the full
normal manual/history/deduplication/ranking/presentation gates still apply.

Each of the 30 newly Open opportunities was individually inspected using captured
identity comparisons, title, specifics, description, business checks and history.
[The per-opportunity comparison](edition_rollout_corrected_shadow_2026-11-25.json)
preserves inspection dispositions. Images/current live availability were not verified.

## Additional material blocker: Spirit Camera

307276397847 / B006Y76HY6 — Spirit Camera: The Cursed Memoir remains identity
Match / shadow Open. The captured title says Sealed and condition is Brand New,
but description is empty, specifics do not identify contents, and the catalog
has no required-contents manifest.

Nintendo's [official manual](https://csassets.nintendo.com/noaext/image/private/t_KA_PDF/manual-3DS-spirit-camera-the-cursed-memoir-en?_a=DATAg1AAZAA0)
confirms progression requires the AR Book. Nintendo also describes the
[book packaged with the game](https://www.nintendo.com/en-gb/Games/Nintendo-3DS-games/Spirit-Camera-The-Cursed-Memoir-274842.html).
This establishes a material contents requirement, not proof this seller's copy
is missing it. The saved sealed title does not resolve the contents uncertainty
under the requested gate.

Required-package protection is still incomplete when catalog manifests are
absent. The narrow Wii Fit correction does not cover all physical accessories.
Do not deploy/replay. Recommended next step: preserve an authoritative exact-ASIN
contents requirement, verify original AR Book/package evidence, and retain
review while unresolved. Add the captured fixture and rerun the gate. A printable
functional replacement does not establish original New retail contents.

## Validation

- 331 Python tests passed: all sourcing suites plus identity, captured-description,
  remaining availability, listing evidence/search and Flipmine import/context/sheet.
- 24 disposable PostgreSQL 17 acceptance tests passed: 13 persistence/concurrency,
  4 progress, 7 shared quota. No production database was used. Direct script
  invocations initially failed startup; unchanged classes passed through an
  explicit unittest runner.
- 15 frontend/API test files passed, including actual Closest Excluded GET
  condition review/confirmed defect cases and 120 Python-to-API/UI comparisons.
  Scoped ESLint and Next production build/type check passed.
- Historical reviewRouting.test.mjs still fails because its frozen capture lacks
  the current opportunities query. The preceding implementation report
  established the same failure with unchanged HEAD. That capture was not altered.
  The separate adjudication database harness was not configured and is not
  claimed as executed.
- Local build success is not authenticated production verification. No new
  release exists to verify.

## Production and controlled replay

A tiny read succeeded. A bounded production read at approximately 9:39 a.m.
Pacific November 25 confirms the original tab remains Partial, with the same
source hash and all 558 pairs: 433 excluded, 118 evaluated, 6 reused (persisted
duplicate state), 1 failed, 0 pending.

Because the gate remains failed:

- No release commit or new worker/web revision exists.
- Super Mario Advance row 238 was not retried.
- Neither the initial 32 nor additional affected cohort was replayed.
- No before/after replay Buy List or Closest Excluded counts exist. Shadow counts
  above must not substitute for live presentation counts.
- Newly actionable production opportunities from this task: 0.
- Production replay eBay/Amazon/Keepa calls: 0.
- Production candidate/evaluation/history writes and marketplace actions: 0.
- Decisions, holds, provenance, source rows and checkpoints were preserved.
- Unrelated MF oversale documentation and prior working-tree changes remain.

Once the additional contents issue is resolved and the gate passes, follow the
authorized order: commit/deploy worker and web together, verify health/revisions,
retry only row 238, reconcile completion guards, then perform only the authorized
targeted replay through fresh protected normal evaluation.
