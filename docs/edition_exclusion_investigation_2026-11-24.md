# Edition-related sourcing exclusions: investigation and proposed correction

Evidence reviewed Nov 24, 2026, approximately 9:05–9:20 p.m. Pacific.
No systemic policy change, deployment, broad reevaluation or source reimport was
performed. The only production candidate retried was the authorized Super Mario
Advance pair. The saved 62-row cohort was inspected, not rescored or promoted.

## Findings

The production finding is reproducible: 71 rejected, primarily Review Threshold,
linked to the original Flipmine tab; 62 have stored profit >= $5 and ROI >= 40%.
They represent **57 ASINs**, not 62 independent products. Stored profit across all
62 is **$3,367.36**. The 53 exact edition-only reason records total **$2,914.80**.

| Saved diagnostic category | Candidates | Stored estimated profit |
|---|---:|---:|
| Edition-only reason, Amazon Standard/Standard Edition and eBay omitted | 47 | $2,666.62 |
| Edition-only reason, other edition/type/reverse omission | 6 | $248.18 |
| Multiple omitted identity/contents fields | 4 | $214.17 |
| Other identity/source reviews | 5 | $238.39 |

**34 appear to identify the same named game/platform** in this conservative
text/structured-evidence triage; **28 remain unresolved**. This is an assessment,
not proof of exact physical packaging, condition or purchase eligibility. The
34 comprise 32 Standard-omission rows with matching core game (excluding the
unresolved Wii Fit contents case), plus two platform-in-edition metadata cases.
Several still have condition or packaging caveats listed in the appendix.
Images were not comprehensively inspected and no purchases are recommended here.

Of the 47 Standard-only reason records, 33 have matching coreGame. Fourteen
also have internal product/source reviews that the headline edition reason
hides. Just Sing is an additional Standard versus Standard Edition *synonym*
conflict on the Amazon side. Exactly **32 records / 30 ASINs / $1,969.19 stored
estimated profit** have no other existing comparison marked review or conflict.
That is the most useful first diagnostic cohort, not a promise of 32 Buy List
entries: condition, contents, region, actual variants, demand, current economics
and existing manual/operational decisions still apply.

## Confirmed mechanism

`integrations/video_game_identity.py:phase3_comparison` builds `unresolved_required`
for edition/packageType/generation/installment whenever one side has a value and
the other does not. It changes an otherwise matching result to needs_review.
Standard is treated exactly like a substantive special edition. The reason
string prioritizes omissions even when other source comparisons also need review.
The shared scorer then gives Review, and the normal presentation threshold rejects
it. This is provider-independent shared matching policy, not a Trading-only error.

The parser also compares Standard Edition from a title with Standard from catalog
as distinct strings; Just Sing demonstrates a false internal source conflict.
Catalog `normalized_edition` is accepted too literally: PlayStation 4 and Xbox One
are platform values; Jewel Case is packaging rather than a conventional edition.
Those cases need typed normalization and provenance, not a blanket default.

## Requested examples

| eBay ID / ASIN | Evidence and conclusion | Stored sale reference / profit |
|---|---|---:|
| 920172650408 / B000M46V20, Shining Force EXA | Title, PS2 and Game Name agree. eBay UPC agrees with exact Amazon and Keepa identifiers. Standard omission is excessive. | $583.63 / $251.29 |
| 840156143661 / B00079W8OU, Shining Tears | Same named game/platform; **description discloses a hole punch in the UPC**. Identity can agree while sell-as-new/packaging review remains necessary. | $350.00 / $180.00 |
| 128191788877 / B0009Z3K9O, Castlevania PS2 | Same game/platform. Amazon edition is **Jewel Case**, not Standard. Resolve exact packaging/identifier, not ordinary Standard omission. | $375.14 / $138.62 |
| 257841605061 / B00B2QL2Y4, Pandora's Tower | Title/platform/Game Name and UPC agree with exact Amazon/Keepa identifiers. Features says Complete Edition; distinguish generic completeness from material edition evidence. | $341.11 / $92.08 |
| 377668366261 / B000R30FJQ, Digimon World Data Squad | Title/platform/Game Name and UPC agree with exact Amazon/Keepa identifiers; excessive Standard omission. | $299.99 / $96.55 |

All **19** listings in the cohort with explicit UPC specifics agree with their
Keepa UPC/EAN after zero-padding normalization. Identifiers strengthen a match;
they do not override contradictory titles/platforms, guarantee physical contents,
or establish condition. Some specifics may be catalog-derived rather than a
barcode read from the actual offered item. MPN must not be silently treated as UPC.

## Cases that prevent blanket clearing

- NHL Hitz 2003, 336902274107: title/specifics say PS2, description says original
  Xbox. Real conflicting platform evidence must remain visible.
- Final Fantasy XI, 198790647550: Amazon Vana'diel Collection 2008 versus original
  FFXI/HDD bundle specifics; different contents are plausible.
- Active Life 377666013189 and DDR 960200585507: Amazon requires a mat; eBay game/
  disc wording does not establish the mat is included. EA Sports Active 2 Game
  Only, 407372956949, likewise cannot establish accessory-package parity.
- Peppa Pig 227625724314 explicitly says No box. Tiger Woods 880128084759 discloses
  extensive seal damage and cracked case; Legends of Wrestling 336887119682 says
  plastic seal is missing. These are independent condition/completeness concerns.
- Smurftastic, Witcher Enhanced, Persona Premium, Star Wars Collector and Division
  Gold Steelbook need correct special-edition/content reconciliation, not Standard
  inference. Multi-value Game Name fields can mix base and special variants.
- Tokyo Xtreme Racer's N/A Game Name is parsed as product evidence; other cases
  involve publisher attribution, possessive/plural typos, reordered PDC words,
  leading The, US Version, CD-ROM/box metadata and Black Label packaging.
  Some are likely normalization false reviews, but they require separate bounded
  rules. Never fuzzy-collapse named subtitles, installments, years or packaging.

The [62-row appendix](edition_exclusion_review_62_2026-11-24.md) and
[machine-readable assessment](edition_exclusion_review_62_2026-11-24.json)
record each pair, category and remaining concerns.

## Regular sourcing scope

The shared rule also affects retained daily-catalog records. Read-only aggregates
found **526 rejected records across 27 ASINs** with the exact edition-only reason
and Amazon Standard/Standard Edition, across retained September–November history.
**33** also meet profit/ROI minima and are primarily Review Threshold. These are
records, not 526 unique listings or automatic purchasing opportunities.

Another 163 dismissed and 39 watching records carry that same saved diagnostic;
those states must not be reset. Across all edition-only types, 108 financially
qualifying regular-catalog review exclusions were found; only 33 are the Standard
subset. Candidates discarded before opportunity persistence are outside these
counts. No broad catalog reassessment was initiated. One of the 62 Flipmine-linked
opportunities originated in regular sourcing, so run-type counts differ from
provenance-linked cohort counts; do not add the cohorts as independent demand.

## Profit estimate audit

All 57 ASINs have persisted Keepa observations, roughly 5–24 hours old at review,
within the existing seven-day source freshness rule. Exact Amazon identity rows
exist for 56; Division Gold Steelbook has no current identity snapshot. No broad
Amazon/Keepa refresh was performed. The stored references generally track current
asking observations and 90-day averages; only four differ from today's conservative
current/average comparison by over five cents. Division's stored $80.96 reference
exceeds the current $75.29 90-day comparison and needs recalculation on reevaluation.

**None of the 62 has an observed fee sample in pricing_reference.** They use the
fallback `sale_price * 22% + $4`, not verified per-ASIN current Amazon fees. Landed
cost is listing price plus quoted shipping; acquisition sales tax, inbound/prep,
returns and holding costs are not separately established by that calculation.

31 candidates have zero 30-day Keepa rank drops; 19 have zero 90-day drops. Rank
drops are only a demand proxy, not confirmed new-condition sales at the asking
price. Shining Force EXA has only 1 drop in 90 days at a $583.63 reference; Shining
Tears and Pandora's Tower have zero at $350/$341.11. These observations support
the presence of high asks, **not realizability of the profit estimates**. Duplicate
ASIN candidates cannot be summed as independent inventory demand. The $2,914.80
is not verified foregone profit or a recommended spend opportunity.

## Proposed correction — approval required before implementation

1. Canonicalize Standard and Standard Edition while retaining original evidence.
   Type platform/format/package data separately, accepting reclassification only
   when corroborated; do not erase Jewel Case or assume it is immaterial.
2. Resolve an omitted *ordinary Standard designation* as compatible omission only
   when core game, platform, installment and available reliable sources agree,
   no materially competing edition/package/region evidence exists, and any known
   alternate-SKU ambiguity is resolved. Do not fabricate an explicit Standard
   observation on eBay. Explain the inference and retain source spans.
3. Keep omitted special editions unresolved without positive edition/contents
   evidence. Explicit incompatible editions remain conflicts. Greatest Hits,
   Black Label, Limited, Collector, Deluxe, bundles, region and packaging variants
   retain independent safeguards. UPC consistency is corroboration, never a veto
   override. Unknown evidence and source contradictions remain reviewable.
4. Preserve material-evidence/manual-review scope and holds. Test the shared
   Browse/Trading paths with the [20 proposed fixtures](edition_policy_proposed_fixtures_2026-11-24.json),
   including negative variants, wrong platform/region, missing contents, ambiguous
   editions, damaged goods and protected numeric titles. Fixtures are design data;
   the new behavior is not implemented and has not passed a changed-engine suite.
5. After approval and tests, run a read-only shadow comparison on the saved cohort
   and a bounded regular-catalog sample. Review deltas before any targeted replay.
   Start with the 32 no-other-comparison-review cases; do not bulk-promote them.
   Refresh expired evidence through existing protections and run the full normal
   eligibility/economics/demand/seller-history/holds pipeline before persistence.

Keep source reconciliation/description-condition gaps separate from the Standard
omission change so its impact remains auditable. No quota, provider-priority,
cache-TTL or schedule changes are proposed.

## Super Mario Advance retry

920153081093 / B00005B8FZ, row 238, was retried once through the unchanged shared
enrichment and evaluation path with production quota guards and normal buyer-offer
history refresh. Original failed-row evidence was archived in the existing
append-only listing-snapshot mechanism. No other candidate was reevaluated.

It **still fails**: Trading cannot complete buyer-specific shipping; Browse
fallback supplies $0 fixed shipping to the configured US buyer location and
`IN_STOCK`, `estimatedRemainingQuantity: 20`, but omits estimatedAvailableQuantity.
`ListingRouter.missing` insists on the latter and reports availability unknown.
This is a confirmed adapter/schema-coverage defect, not evidence of a stockout.
eBay's [official release notes](https://developer.ebay.com/develop/api/browse-api/release-notes)
document the remaining-quantity field (1.19.9); its
[Browse guide](https://developer.ebay.com/api-docs/buy/static/api-browse.html)
also directs availability checks to status and end date.

Recommend a separate narrow adapter fix accepting documented positive remaining
quantity/status with exact-item and buyer-shipping checks, preserving UNKNOWN,
zero-quantity, ended and sold-out failures, then retry this row. No field was
invented, no availability/shipping requirement bypassed, and no policy/adapter
code changed in this investigation.

Final import state remains **Partial: 433 excluded, 118 evaluated, 6 reused,
1 failed, 0 pending = 558**. It is not marked Complete. Original provenance,
manual decisions, holds and snapshot remain intact. No deployment, purchases,
bids or offers were made. Report/fixture files are left uncommitted for review.
