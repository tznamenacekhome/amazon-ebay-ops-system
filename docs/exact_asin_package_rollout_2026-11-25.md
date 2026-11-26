# Exact-ASIN package correction and controlled edition rollout

## Mechanism and evidence scope

The existing Amazon catalog relevant_attributes_json stores components,
identifiers and package evidence. Normal catalog enrichment now retains
marketplace-scoped descriptions/bullets as well. A small versioned artifact,
integrations/product_package_evidence.json, retains authoritative or unresolved
exact-ASIN observations with platform, marketplace, component quantities,
configuration, sources and verification status. It is deployed with the existing
integrations, attached to cached exact-ASIN catalog identity, and retained on
normal future catalog normalization. No migration, new service or backfill.

Only B006Y76HY6 (original AR Book requirement) and B000VJRU44 (unresolved exact
package configuration) have curated records. No requirement propagates by title
or franchise. Matching exact-ASIN/platform/catalog-title guards apply; explicit
other marketplaces do not receive US evidence. Legacy catalog seed copies lacking
marketplace retain MBOP's existing US sourcing scope. Conflicting verified
observations stay review. Actual new requirement evidence changes material
hashes for affected products; unchanged products preserve their hashes.

The shared package comparator distinguishes software-only, accessory bundle,
required-components and unresolved configurations. Ordinary software without
known ambiguity does not need a manifest. It separates package words such as
Game only from product identity, without waiving missing-case/manual or other
condition checks. Physical component evidence never assigns franchise defaults.
Controllers require compatible platform evidence, and recorded model/quantity
requirements are enforced. Incomplete inferred bundle manifests remain review.

Explicit missing components override UPC/seal claims. Replacements/reproductions
do not prove original New contents. A corroborated original factory-sealed retail
package with exact SKU identifier and compatible package configuration may
establish original contents without enumerating every item. Generic New/sealed
claims alone do not. A named bundle's identity can match while independent
physical contents remain unverified for purchasing.

All prior edition, condition, re-release, numeric identity and remaining-quantity
corrections remain. Existing Closest Excluded qualification/ranking, seller
checks, holds, manual decisions, provenance and duplicate guards remain.

## Production evidence reviewed read-only

The bounded retained review covered 11 catalog ASINs and at most two candidates
each; see exact_asin_package_retained_review_2026-11-25.json.

- B0028ZH7GU explicitly identifies Guitar Hero 5 Wii Game only. It is classified
  software-only and receives no guitar requirement. Other identity checks still
  exclude the retained candidate; this task does not waive them.
- B00VEPK9U6 identifies Guitar Hero Live Xbox 360 Guitar Bundle. Its game-only
  candidate cannot satisfy that package.
- DDR Hottest Party Bundle, Hottest Party 2 with Dance Mat and Skylanders Starter
  Packs retain bundle contents review/conflict independently from ordinary DDR.
- B000VJRU44's title Wii Fit / Standard does not establish software-only versus
  board bundle. Its exact configuration remains unresolved; no board manifest
  was invented.
- Spirit Camera's captured title is Sealed / Brand New, with no description,
  contents specifics or exact SKU identifier. Its original AR Book remains
  uncorroborated, so it is rejected from automatic purchasing and reviewable.

No stored Wii Fit Plus configuration, Rock Band/Disney Infinity catalog pair, or
software-only/bundle pair for the exact same named game was established by this
bounded catalog review. Synthetic fixtures explicitly cover those combinations;
they are not claims about real ASIN configurations. Manufacturer requirements
and references are preserved in the exact-ASIN evidence artifact.

## Four-stage same-input shadow gate: PASS

The same original 97 opportunities and captured settings/pricing/history were
used. All 29 remaining new Open rows were individually reviewed against captured
identity, descriptions, specifics and independent checks. No additional material
purchasing concern was identified. This is not fresh purchase verification.

| Outcome across 97 | HEAD | First edition patch | Previous corrected | Final |
|---|---:|---:|---:|---:|
| Identity match | 16 | 53 | 54 | 53 |
| Identity review | 71 | 34 | 35 | 36 |
| Identity non-match | 10 | 10 | 8 | 8 |
| Shadow Open | 0 | 35 | 30 | 29 |
| Rejected lifecycle | 80 | 45 | 50 | 51 |
| Dismissed lifecycle | 15 | 15 | 15 | 15 |
| Inventory snoozed | 2 | 2 | 2 | 2 |

Only Spirit Camera changes identity/lifecycle relative to the previous corrected
shadow: Match/Open becomes Review/Rejected. All nine prior listing regressions
remain corrected. Accepted sample remains 15 matches, 1 review, 4 non-matches,
with unchanged protected lifecycle. Final Flipmine 62: 30 identity matches,
32 reviews, 24 shadow Open. Initial 32: 27 matches, 5 reviews, 22 shadow Open.
The complete comparison is exact_asin_package_shadow_2026-11-25.json.

## Validation and deployment plan

- 342 Python matching/sourcing/Flipmine/enrichment regression tests passed.
- 24 PostgreSQL 17 disposable acceptance tests passed: 13 persistence/concurrency,
  4 progress and 7 quota. No production database used.
- 15 frontend/API files passed, including 120 Python-to-API/UI comparisons.
- Scoped lint and Next production build/type check passed.
- Known old frozen reviewRouting capture remains incomplete as documented in
  the preceding report; it was not rewritten. Authenticated production UI
  verification is separate from local tests.

Pre-release AWS: account 297464765814, web231 healthy/stable, catalog sourcing
and Keepa-priority recovery use worker177. No active sourcing/Flipmine task was
interrupted. Only those two necessary schedule image revisions will change;
commands, timing, permissions and other schedules are preserved.

Before-replay normal HEAD list-builder counts: Buy List 0, Closest Excluded 115.
These are backend presentation counts, not authenticated UI verification.
Capacity gate passed before these reads.

The authorized cohort is the initial 32 plus 26 directly affected additional
opportunities within the captured 62. Additional rows are selected by changed
edition comparison/normalization or an explicit corrected edition/contents
review reason; four unrelated pairs are not selected. Fresh normal evaluation,
protected-row checks and atomic guarded persistence are required, not shadow
identity promotion. Original evaluations must be archived, holds/manual decisions
skipped, and source rows/provenance retained. No reimport or marketplace actions.

Release and replay results will be recorded after production verification.

Catalog-refresh regression follow-up: a changed catalog title/platform now
retains known exact-ASIN package evidence as unresolved contradiction instead of
silently dropping it. A properly verified software-only observation may still
supersede an older unresolved record. The expanded 344-test Python suite passes;
all 97 captured identity/lifecycle results remain identical to the final gate.

Final presentation verification exposed a compact-projection defect: the
database's existing sourcing_list_diagnostics helper deliberately drops detailed
identity comparisons and condition checks. The first API mocks retained full
diagnostics and missed this path. Closest Excluded therefore lacked the policy
marker even though stored purchasing decisions correctly blocked the defects.
The list query now requests only a scalar policy-version projection; qualification
uses retained compact hard blocks, identity verdict, review reasons and business
checks. No schema change or full identity-payload expansion is needed. Tests now
emulate the production projection. All 15 API/frontend files, lint and build pass.
Read-only backend verification yields Buy List 24 / Closest Excluded 87, with
the four confirmed condition failures absent. Worker matching decisions are
unchanged; this follow-up is web-only.

## Final production receipt ? November 25, Pacific

Feature commit 35ee6847148c; package persistence follow-up f82933aad115; compact-list fixes d6afcd9e7f11 and b5aa9cd545cf. Final runtime: worker179 / web235. ECS service completed with 1 running, 0 pending and a healthy ALB target. Worker179 source-hash/evidence import smoke exited 0. All 21 schedules were compared: only catalog sourcing and Keepa-priority recovery image revisions changed (177 ? 179). Timing, commands, permissions, quotas and cache settings are unchanged.

Original import is Complete: **558 rows = 434 excluded + 118 evaluated + 6 reused; 0 failed, 0 pending**. Source hash is unchanged. Super Mario Advance row238 now passes availability verification but is independently excluded for a title identity conflict (residual Game Boy Advance/USA title wording). That guard was preserved.

Targeted replay: **58 checked, 57 guarded updates, 1 confirmed unavailable**. Final decisions: **24 Open, 33 rejected/review, 1 unavailable dismissal**. The ended Pandora's Tower listing257841605061 received the existing unavailable-listing disposition. No other candidates were reevaluated. All58 original snapshots and57 guarded audit logs were verified. A repeated saved checkpoint performed zero provider calls and no new evaluation/opportunity writes.

Normal source-filtered presentation counts: **Buy List 0 ? 24; Closest Excluded 115 ? 86**. All presented rows retain FM provenance. Buy List has24 unique listings/ASINs; normal scoped duplicate planning found zero duplicates and required no dismissals. The four confirmed unacceptable-condition rows are absent from Closest Excluded, while Spirit Camera, Wii Fit and the two condition concerns remain review-only. Counts were reconciled into the completed tab summary after persistence finished.

Final testing: **344 Python tests; 24 disposable PostgreSQL acceptance tests; 15 frontend/API files; lint and production build/type check passed**. The later compact-list regression includes retained seller-avoid trace, seller-watch behavior, economics and confirmed condition rejection. No additional matcher-policy change was needed for that read-path repair.

API usage for failed-row retry plus targeted replay: **59 Trading GetItem,27 GetItemShipping,6 GetMyeBayBuying,13 Browse detail,4 Developer Analytics** (109 eBay quota calls). Direct HTTP instrumentation and the shared Trading/Browse counters agree. There were also54 Amazon listing-restriction reads,8 eBay OAuth requests and2 Amazon OAuth requests. Keepa and source-sheet requests:0; valid existing evidence was reused. Marketplace writes/purchases/bids/offers:0.

Raw exact-ASIN review: B000VJRU44 has no included-components manifest, an empty product description, non-package-specific bullets and multiple UPC/EAN observations. Those fields do not establish a board-bundle versus standalone package with sufficient confidence. The ASIN remains unresolved rather than inheriting a franchise accessory requirement. B006Y76HY6's raw Amazon bullet independently describes its included diary; this corroborates Nintendo's AR Book requirement. The captured seller evidence still does not establish original contents.

Authenticated UI verification could not finish. After explicit operator approval, Computer Use stopped because it could not confidently determine Chrome's current URL; further UI input was stopped. AWS and backend verification above are not presented as authenticated browser verification. The pre-existing frozen routing fixture limitation remains documented. No migration, paid service, infrastructure addition, broad catalog replay, reimport or unrelated MF change was made. Temporary Docker ECR auth files were removed; persistent credential settings were unchanged.

### Newly actionable Buy List entries

Values below are the normal backend estimates at verification time. Cost is the recorded ask landed cost. Type and existing offer suggestion are retained; no offers were submitted.

| Product | ASIN | eBay item | Type | Cost | Est. profit | ROI | Suggested offer |
|---|---|---|---|---:|---:|---:|---:|
| Castlevania Curse of Darkness - Xbox | B0009Z3KAI | 920160850722 | buy_now | $130.44 | $99.56 | 76.3% | - |
| Shining Force EXA - PlayStation 2 | B000M46V20 | 920172650408 | buy_now | $199.94 | $251.29 | 125.7% | - |
| Digimon World Data Squad - PlayStation 2 | B000R30FJQ | 377668366261 | buy_now | $133.44 | $96.55 | 72.4% | - |
| Hasbro Family Game Night - PlayStation 2 | B0019R4VF8 | 377668366221 | buy_now | $35.44 | $22.95 | 64.8% | - |
| Qix Neo | B0000A1HVX | 820316741656 | buy_now | $25.99 | $18.36 | 70.6% | - |
| NASCAR Dirt to Daytona - PlayStation 2 | B00006ZCCV | 336887154067 | buy_now | $19.86 | $39.94 | 201.1% | - |
| Just Sing - PlayStation 4 Standard Edition | B01J6FPZZY | 840112509185 | buy_now | $20.85 | $17.26 | 82.8% | - |
| Turok 2: Seeds of Evil - PC | B00002SFL4 | 168860841661 | best_offer | $68.04 | $83.70 | 123% | $58.90 |
| Hidden Object Adventure MEGA Collection - PC | B0032JCKYU | 117520198668 | best_offer | $11.98 | $26.09 | 217.8% | $4.74 |
| Bogey: Dead 6 | B00002STIC | 840131195824 | best_offer | $56.84 | $67.54 | 118.8% | $47.49 |
| Junior Classic Games 3D - Nintendo 3DS | B0069EB9DI | 880124306447 | best_offer | $33.00 | $33.18 | 100.5% | $31.35 |
| COSMI Pool Shark ( Windows ) | B000196EN2 | 940098783744 | best_offer | $15.66 | $38.65 | 246.8% | $8.54 |
| Shining Tears - PlayStation 2 | B00079W8OU | 257859060301 | buy_now | $97.99 | $171.01 | 174.5% | - |
| Ratatouille - PC/Mac | B000OZIAMG | 227623586139 | buy_now | $14.39 | $19.19 | 133.4% | - |
| Pac Man Fever - PlayStation 2 | B00005YJPF | 820382941556 | buy_now | $21.84 | $12.37 | 56.6% | - |
| Constantine - PlayStation 2 | B000784XF8 | 137895810464 | best_offer | $57.80 | $43.41 | 75.1% | $47.45 |
| Air Conflicts: Vietnam - PlayStation 3 | B00G9DFMDW | 377640141530 | buy_now | $27.99 | $13.54 | 48.4% | - |
| Romance of the Three Kingdoms X - PlayStation 2 | B00082ZQWW | 377668366312 | buy_now | $196.94 | $92.32 | 46.9% | - |
| Battlestar Galactica - Xbox | B00008KTMX | 377659302368 | buy_now | $54.44 | $22.66 | 41.6% | - |
| Snk Heroines: Tag Team Frenzy - Nintendo Switch | B078YN79KH | 327437457493 | buy_now | $30.00 | $12.70 | 42.3% | - |
| The Town of Light - Xbox One | B06XTT5CKM | 840094365516 | buy_now | $59.99 | $25.66 | 42.8% | - |
| Phix: The Adventure | B0000AUFQ3 | 366801881758 | best_offer | $46.06 | $27.94 | 60.7% | $38.00 |
| Call of Juarez: Bound In Blood - Playstation 3 | B001RTCOWA | 860135189241 | buy_now | $23.84 | $10.37 | 43.5% | - |
| Mighty No. 9 - PlayStation 4 | B00VZAQ2X8 | 900099910655 | best_offer | $16.00 | $6.61 | 41.3% | $9.50 |

### Remaining replay exclusions

| Reason | Count |
|---|---:|
| edition_not_corroborated | 18 |
| condition_review | 2 |
| contents_not_corroborated | 6 |
| condition_unacceptable | 4 |
| review_threshold | 3 |
| Confirmed unavailable | 1 |

Next review actions: verify the exact Wii Fit package and Spirit Camera original AR Book evidence; inspect the two condition-review listings before considering them. Remaining special-edition/source identity uncertainty remains explicit. No broad historical reevaluation is initiated.

Full per-pair outcomes, presentation records and provider counts: [production results](exact_asin_package_production_results_2026-11-25.json).
