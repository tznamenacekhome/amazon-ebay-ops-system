# Sourcing Match Quality Report

Last reviewed: 2026-06-22

Scope: Amazon ASIN -> eBay sourcing listing matching. This review covers
deterministic rules, diagnostics, and historical dismissal data only. No AI
calls, model training, marketplace write actions, or eBay -> Amazon sourcing
were added.

## Current Dataset Summary

Live sourcing dataset reviewed:

- Opportunities: 3,330
- Operator/system actions: 340
- Matching intelligence examples: 3,568

Opportunity statuses:

- `rejected`: 2,744
- `dismissed`: 468
- `watching`: 56
- `matched_to_purchase`: 32
- `purchased_pending_match`: 19
- `open`: 11

Opportunity types:

- `no_profitable_source_found`: 2,856
- `best_offer`: 225
- `buy_now`: 176
- `watch`: 52
- `auction`: 17
- `multi_unit`: 4

Dismiss reasons:

- `wrong_product`: 86
- `wrong_edition_version`: 53
- `no_longer_available`: 45
- `digital_item`: 20
- `wrong_platform`: 20
- `packaging_condition_issue`: 9
- `missing_shrink_wrap`: 8
- `other`: 6
- `packaging_damage`: 3
- `non_north_american_version`: 1

Dismissals with notes: 116.

## Repeated Bad-Match Patterns

Identity problems:

- Wrong platform/system, especially PS4 vs PS5, Xbox One vs Xbox Series/Xbox
  360, Wii vs Wii U, Switch vs DS/3DS, and cross-console results.
- No meaningful title overlap after platform and generic terms are removed.
- Accessory or non-game listings such as keychains, posters, patches,
  stickers, trading cards, magazines, strategy guides, and amiibo.
- Digital/download/code/DLC listings.
- Incomplete listings such as disc only, case only, manual only, cover art, or
  no-game listings.
- Non-North-American packaging/version signals such as PAL, PEGI, CERO, USK,
  UK import, Japanese, German, Italian, Spanish, or other foreign-version
  terms.
- Edition/version mismatches such as Deluxe, Gold, Collector, Limited,
  Steelbook, Greatest Hits, Platinum Hits, and Player's Choice.

Business problems:

- ROI too low, not profitable, low velocity, high competition, or capital
  better used elsewhere.
- Availability/system outcomes such as `no_longer_available`.

Business-only outcomes are intentionally not used as identity-blocking match
memory.

## Platform Mismatch Analysis

Among the historical opportunities, 3,060 rows had detectable platform signals
on both the Amazon and eBay side. 377 had different detected systems.

Top mismatch pairs included:

- PS5 seed -> PS4 candidate: 52
- PS4 seed -> Xbox One candidate: 47
- Xbox One seed -> Xbox Series X candidate: 36
- Wii U seed -> Switch candidate: 29
- Switch seed -> Xbox One candidate: 26
- PS3 seed -> Xbox 360 candidate: 24
- Wii seed -> Wii U candidate: 16
- PS4 seed -> PS5 candidate: 13

Most mismatches were already rejected or dismissed, but the pattern is common
enough to deserve first-class deterministic diagnostics.

## Proposed Rule Decisions

| Rule | Historical signal | Action | False-negative risk |
| --- | ---: | --- | --- |
| Hard platform boundary when Amazon and eBay both name incompatible systems | 377 detectable system mismatches | Hard block | Low. Video games are platform-specific. Multiple-platform listing titles are review, not block, if the Amazon system is included. |
| No meaningful title-token overlap | 201 historical rows in full dry-run | Hard block | Low. Generic/platform words are removed first. |
| Digital/download/code/DLC/account delivery terms | 55 pattern hits observed, 20 `digital_item` dismissals | Hard block | Low for physical resale sourcing. |
| Accessory/not-game terms and known non-game categories | 121 category blocks plus repeated keychain/poster/amiibo/patch examples | Hard block | Medium if broad terms are used. Rules now avoid blocking on generic raw aspect words like `controller`. |
| Incomplete listing terms | Repeated manual-only, disc-only, case-only, no-game notes | Hard block | Low/medium. `loose disc` is not blocked by this rule; exact incomplete phrases are. |
| Explicit non-North-American version signals | PEGI/PAL/CERO/USK/import-region examples | Hard block | Medium. Generic `import` alone is not blocked after dry-run tuning. |
| Edition/version mismatch signals | 201 full dry-run warnings, 53 `wrong_edition_version` dismissals | Probable Non-Match / score penalty | Medium/high. Some editions are sellable and price-dependent, so this warns instead of hiding. |
| Multiple platform terms that include the Amazon platform | 288 full dry-run warnings across platform families | Probable Non-Match / review | Medium. Cross-gen listing titles need human review. |
| Historical exact/title-memory non-match | Existing matching intelligence examples | Hard block | Low when ASIN + eBay identity or title/system memory matches. |
| Seller watch/avoid intelligence | Existing seller intelligence | Warn / score penalty | Medium. Seller status is advisory until more outcomes accumulate. |

## Dry-Run Result After Rule Tuning

Command:

```powershell
.\.venv\Scripts\python.exe integrations\analyze_sourcing_match_quality.py --limit 5000 --since-days 365
```

Result:

- Rows evaluated: 3,330
- Current reviewable rows: 86
- Rule recommendations:
  - `Probable Match`: 2,160
  - `Blocked`: 819
  - `Probable Non-Match`: 350
  - `Review`: 1
- Newly blocked current reviewable rows: 0
- Potential false positives among `watching`, `purchased_pending_match`, and
  `matched_to_purchase`: 0

Top block reasons:

- 201: no meaningful title token overlap
- 121: eBay category is not Video Games software
- 58: accessory/not game: amiibo
- 57: accessory/not game: keychain
- 55: excluded keyword: promo
- 49: accessory/not game: poster
- 44: excluded keyword: no game
- 37: accessory/not game: poster, print ad
- 35: excluded keyword: promotional
- 32: platform mismatch: Amazon PS 4, eBay Xbox One

Top review/warning reasons:

- 201: edition/version mismatch signal
- 68: candidate listing has no detectable platform
- 62: candidate lists multiple platforms including PS 5
- 59: candidate lists multiple platforms including Xbox 360
- 59: candidate lists multiple platforms including Xbox Series X
- 53: candidate lists multiple platforms including Xbox One
- 38: candidate lists multiple platforms including PS 4
- 32: candidate lists multiple platforms including Wii U
- 30: weak meaningful title overlap
- 30: candidate lists multiple platforms including PS 3

## Implementation Notes

The deterministic evaluator stores diagnostics for:

- platform rule result
- title overlap result
- excluded keyword result
- digital/download signals
- edition/version signals
- region signals
- incomplete/not-game signals
- category/location signals
- historical matching intelligence
- seller trust status
- final recommendation

Recommendations use:

- `Blocked`
- `Probable Non-Match`
- `Review`
- `Probable Match`
- `Strong Match`

The analyzer can write diagnostics only:

```powershell
.\.venv\Scripts\python.exe integrations\analyze_sourcing_match_quality.py --limit 5000 --since-days 365 --write
```

`--write` does not update opportunity status, dismiss listings, bid, purchase,
submit offers, or call any AI/model.

This diagnostics-only write was applied to the 3,330 current opportunities
during this review so existing rows have the same static-rule diagnostic shape
that future scoring runs will write automatically.
