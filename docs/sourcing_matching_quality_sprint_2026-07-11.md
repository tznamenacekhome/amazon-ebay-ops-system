# Sourcing Matching Quality Sprint

Date: 2026-07-11

Scope: deterministic Amazon ASIN -> eBay listing matching quality. No AI calls,
model training, image AI, eBay-to-Amazon sourcing, purchases, bids, Best Offers,
or marketplace write actions were added.

## Implemented

- Fixed Amazon platform data flow into scoring.
  - Scoring now resolves platform from first-class seed `system`, then
    `sourcing_seed_asins.raw_context_json.inferred_system`, then Amazon title
    detection.
  - Diagnostics preserve the platform source.
- Added reusable eBay evidence normalization inside the matcher.
  - Parses localized aspects for Platform, Game Name, Region Code, Country of
    Origin, Format, Type, Features, and Release Year.
  - Normalizes category IDs/names/path, subtitle, description, primary image,
    and additional image URLs into diagnostics.
- Strengthened deterministic rules.
  - Item-specific Platform is used before eBay title platform detection.
  - Incompatible known platforms hard-block.
  - Category validation blocks clear non-game/accessory/merchandise categories
    and routes possible game+accessory bundles to Review.
  - Item-specific Game Name can block clear different-game listings.
  - Numeric sequel/year conflicts block clear mismatches.
  - Premium/base and other edition mismatches hard-block when explicit.
  - Digital/service/accessory/incomplete/region phrase coverage was expanded.
- Improved diagnostics.
  - `matching_diagnostics_json` now includes normalized evidence, platform
    source/result, category evidence/result, Game Name comparison, numeric
    identity result, edition/version signals, digital/service, not-game,
    incomplete, region, historical evidence, seller status, final
    recommendation, hard blocks, and warnings.
  - `/api/sourcing/opportunities` now returns the backend diagnostics payload as
    `matchingDiagnostics` in addition to flattened flags.
- Added automated regression tests in `tests/test_sourcing_match_rules.py`.
  - Coverage includes wrong platform, Wii vs Wii U, accessories, cake toppers,
    puzzles, plush/merchandise, power discs, strategy guides, digital service,
    Just Dance year mismatch, Premium Edition vs base, microfiber cleaners,
    cable/pedal/drum sticks, disc-only, foreign region, a valid match, loose
    disc inside complete case, ambiguous bundle review, and kids-meal backpack
    merchandise.
- Updated `integrations/analyze_sourcing_match_quality.py`.
  - Reports structured metadata availability, structured rule hits,
    platform-source coverage, category-source coverage, before/after review
    counts, newly blocked rows, potential false positives, and manual-review
    examples.

## Before / After Dry Run

Command:

```powershell
.\.venv\Scripts\python.exe integrations\analyze_sourcing_match_quality.py --limit 500 --since-days 365
```

Before applying the live rescore, the updated rules found:

- Rows evaluated: 500
- Current statuses: `rejected` 469, `open` 27, `dismissed` 4
- Rule recommendations: `Blocked` 143, `Probable Match` 346,
  `Probable Non-Match` 11
- Newly blocked reviewable rows: 16
- Representative newly blocked rows:
  - `Wii Music` -> `Rock Band Cake Topper And Rings Music Celebration Wii Xbox
    PS4`
  - `YO-KAI WATCH - 3DS` -> `Yo-Kai Watch Microfiber Cleaner Yokai cloth`
  - `Just Dance 2018 - Nintendo Switch` -> multiple `Just Dance 2020/2021`
    listings

After adding two additional merchandise/service phrases and rescoring the latest
`recent_sales` and `full_listings` runs:

- Rows evaluated: 500
- Current statuses: `rejected` 487, `open` 9, `dismissed` 4
- Rule recommendations: `Blocked` 145, `Probable Match` 346,
  `Probable Non-Match` 9
- Newly blocked reviewable rows: 0
- Potential false positive examples among positive/reviewable statuses: 0

Structured metadata coverage in the final 500-row sample:

- Category: 500
- Primary image: 500
- Additional images: 477
- Localized aspects: 105
- Item-specific Platform: 97
- Item-specific Game Name: 97
- Description: 96
- Item-specific Region: 64
- Release Year: 55
- Features: 38

Structured rule hits in the final sample:

- Category blocks: 56
- Accessory/not-game blocks: 41
- Numeric identity blocks: 28
- Edition/version blocks: 23
- Digital/service blocks: 17
- Incomplete listing blocks: 10
- Region blocks: 6
- Game Name blocks: 2

## Live Rescore Applied

The existing safe rescore path was used:

```powershell
.\.venv\Scripts\python.exe integrations\refresh_matching_intelligence.py --runs-per-mode 1 --skip-rebuild
```

Runs updated:

- `recent_sales` run `54060af1-873a-4375-91d1-129e84365dcd`: 14 candidates
  updated, 0 inserted.
- `full_listings` run `19dd4246-2d41-4aee-90d2-0b0a59d55313`: 6,231
  candidates updated, 0 inserted.

No sourcing history was deleted. Operator terminal statuses such as dismissed,
purchased pending match, and matched to purchase remain preserved by the
existing scorer merge path.

## Last Sold Display Follow-Up

The Opportunities API now hydrates Last Sold from the seed row first and falls
back to Amazon sales history by ASIN when a full-listing seed has no
`last_sold_at`. This fixed current opportunities whose ASIN had recent Amazon
sales but displayed an empty Last Sold column.

## Remaining Work

- Add a UI diagnostic drawer that renders the now-exposed
  `matchingDiagnostics` payload.
- Continue converting real dismissals into tests as new false-positive patterns
  appear.
- Consider a dedicated Review status/workflow if the operator wants uncertain
  but plausible candidates separated from normal open opportunities.
- Image analysis remains future work after deterministic metadata quality is
  stable.
