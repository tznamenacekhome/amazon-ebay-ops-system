# Matching Intelligence Layer

Status: Foundation implemented; deterministic live scoring diagnostics are
implemented; AI-assisted opportunity review is intentionally deferred.

The Matching Intelligence Layer preserves reviewed sourcing evidence so MBOP can
improve Amazon-to-eBay replenishment matching before any future eBay-to-Amazon
sourcing work.

## Boundaries

- Sourcing remains advisory.
- MBOP does not purchase, bid, submit offers, or write marketplace data.
- Frontend displays backend/API diagnostics only.
- Video game system/platform remains a hard boundary.
- Business-only dismissals must not poison ASIN identity matching.
- eBay-to-Amazon sourcing is still future work.

## Dismissal Taxonomy

Operator dismiss reasons:

- Identity / Match: `wrong_product`, `wrong_platform`,
  `wrong_edition_version`, `non_north_american_version`, `digital_item`
- Completeness: `incomplete_product`
- Packaging / Condition: `missing_shrink_wrap`, `suspected_reseal`,
  `packaging_damage`
- Business / Sourcing: `roi_too_low`, `sales_velocity_too_low`,
  `too_much_competition`, `capital_better_used_elsewhere`,
  `valid_product_poor_opportunity`
- System: `no_longer_available`, `other`

Notes are stored for every dismissal reason when entered. MBOP does not require
or strongly prompt for notes by dismissal reason; note capture remains optional.

`no_longer_available` is an availability/system label, not a non-match.
`digital_item` maps to a non-match because it is not a valid physical resale
match.

## Labels

`matching_intelligence_examples` uses:

- `match`
- `non_match`
- `condition_problem`
- `valid_match_poor_opportunity`
- `availability_system`
- `needs_review`

Label types separate positive identity, negative identity, condition issue,
business issue, availability/system, and unknown evidence.

## Storage

- `sourcing_listing_snapshots` stores point-in-time eBay/Amazon evidence when a
  candidate becomes an opportunity, when an operator/system action occurs, and
  when historical/manual purchase evidence is backfilled for training.
- `matching_intelligence_examples` stores rebuildable labeled examples from
  sourcing actions, manual match memory, purchase history, receiving outcomes,
  sourcing purchase matches, and order problem return outcomes.
- `matching_intelligence_receiving_outcomes` stores receiving-owned item
  verification outcomes such as correct item, wrong item, wrong condition,
  packaging issue, incomplete item, and listed successfully.
- `sourcing_seller_intelligence` stores derived seller metrics and advisory
  seller status.

Seller `avoid` is advisory only for now. It should warn/penalize, not hide by
default, until diagnostics are proven.

Historical purchase rows with verified ASINs are treated as manually verified
positive match evidence because the purchases predate MBOP and were operator
verified before purchase.

## Rebuild

Dry run:

```powershell
.\.venv\Scripts\python.exe integrations\build_matching_intelligence_examples.py --source all
```

Write:

```powershell
.\.venv\Scripts\python.exe integrations\build_matching_intelligence_examples.py --source all --write
```

The script prints counts by source, label, dismiss reason, and missing notes.

## Orchestration

`run_all_syncs.py` includes a `Matching intelligence refresh` job in the
`core`, `purchases`, `daily`, and `catalog` groups. The job:

1. rebuilds examples from purchases, sourcing actions, manual matches, sourcing
   purchase matches, and order-problem cases
2. rebuilds seller intelligence
3. rescores the latest completed sourcing run for each source mode so live
   opportunity diagnostics use the latest evidence

Manual run:

```powershell
.\.venv\Scripts\python.exe integrations\refresh_matching_intelligence.py --runs-per-mode 1
```

Dry run:

```powershell
.\.venv\Scripts\python.exe integrations\refresh_matching_intelligence.py --dry-run
```

## UI/API

- API: `GET /api/sourcing/matching-intelligence`
- UI: Sourcing workspace, `Matching Intelligence` tab

## Live Sourcing Use

Amazon-to-eBay sourcing now consumes Matching Intelligence during scoring:

- deterministic static rules produce row-level diagnostics for platform
  boundaries, title overlap, excluded keywords, digital/download listings,
  edition/version signals, region signals, incomplete/not-game listings,
  category/location signals, historical dismissal similarity, seller trust, and
  the final recommendation
- static rules normalize eBay raw payload evidence into diagnostics, including
  localized aspects for Platform, Game Name, Region Code, Country of Origin,
  Format, Type, Features, and Release Year, plus category names/IDs, seller
  description text, and image URL availability
- Amazon seed platform resolution now uses first-class seed `system`,
  `raw_context_json.inferred_system`, and title detection in that order; eBay
  item-specific Platform is used before title platform detection
- clear non-game categories, accessory/merchandise phrases, digital/service
  phrases, incomplete-product phrases, non-North-American region signals,
  numeric sequel/year mismatches, item-specific Game Name conflicts, and
  edition/version conflicts can hard-block profitable-looking rows
- recommendations use `Blocked`, `Probable Non-Match`, `Review`,
  `Probable Match`, and `Strong Match`
- exact historical positive examples boost candidate score
- exact historical `non_match` and `condition_problem` examples hard-block the
  candidate
- historical business-only examples apply a small score penalty but do not
  poison identity matching
- seller `watch` and `avoid` statuses add warnings and score penalties, but do
  not hide opportunities yet
- eBay listings with known category evidence outside Video Games are hard-blocked
  or routed to Review for ambiguous game-plus-accessory bundles
- `/api/sourcing/opportunities` returns full backend `matchingDiagnostics` for
  each row in addition to flattened flags
- the Matching Intelligence UI includes image clue counts and a near-miss
  review queue for title-similar dismissed/condition examples

Rule quality can be reviewed with:

```powershell
.\.venv\Scripts\python.exe integrations\analyze_sourcing_match_quality.py --limit 5000 --since-days 365
```

The analyzer defaults to dry-run mode. `--write` stores diagnostics only and
does not update opportunity status, auto-dismiss listings, bid, purchase,
submit offers, call AI, train a model, or build eBay-to-Amazon sourcing.

The latest deterministic rule reviews are documented in
`docs/sourcing_match_quality_report.md` and
`docs/sourcing_matching_quality_sprint_2026-07-11.md`.

AI review against opportunities should wait until the labeled sample set is
larger and more balanced. Current target: at least 5,000 labeled examples with a
stronger mix of negative identity, condition, and near-miss examples before AI
observations influence opportunity review.

## Current Gaps

The remaining requirement work is tracked in `ROADMAP.md`. The important open
items are:

- a dedicated uncertain-match review workflow
- a full per-opportunity diagnostics drawer that renders backend-provided
  `matchingDiagnostics`
- sample-driven fuzzy matching after the evidence set is large enough
- AI title/image/item-specific review against live opportunities
- scoring that directly uses structured image/listing clues
- fuller seller ROI, offer, conversion, and expansion-search intelligence
- fuller return intelligence reporting and outcome analysis
- configurable matching weights by source, outcome, confidence, and recency

Strong or required note prompts are intentionally out of scope. Notes remain
optional and are stored whenever entered.
