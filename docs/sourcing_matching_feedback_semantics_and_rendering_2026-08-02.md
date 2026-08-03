# Sourcing Matching Feedback Semantics And Rendering

Date: 2026-08-02

## Scope

This change refines sourcing dismissal diagnostics feedback. It does not change matching rules, rescore production opportunities, call AI, call marketplaces, or perform marketplace writes.

## Feedback Model

Operator feedback now separates failed matching rule families from evidence sources.

Persisted shape:

```json
{
  "matchingFeedback": {
    "version": "matching_feedback_v2",
    "allAssumptionsCorrect": false,
    "failedRuleFamilies": ["core_game_identity"],
    "evidenceSources": ["amazon_title", "ebay_title", "ebay_game_name"],
    "legacyIncorrectRows": ["core_game_identity"],
    "note": null
  }
}
```

The legacy `diagnosticsFeedback` object is still written for compatibility and old rows remain readable.

## Rule Families

- `core_game_identity`
- `numeric_installment`
- `platform`
- `edition_version`
- `region`
- `completeness`
- `digital_physical`
- `category_product_type`
- `seller_listing_photo_consistency`
- `other`

## Evidence Sources

- `amazon_title`
- `ebay_title`
- `ebay_game_name`
- `ebay_item_specifics`
- `amazon_catalog_metadata`
- `ebay_description`
- `primary_image`
- `additional_images`
- `category`
- `platform_metadata`
- `other`

## Legacy Mapping

- Core Game Identity -> `core_game_identity`
- Platform/system -> `platform`
- Installment/sequel number -> `numeric_installment`
- Edition/version -> `edition_version`
- Full title -> `amazon_title`, `ebay_title` evidence only
- eBay Game Name -> `ebay_game_name` evidence only

Evidence-only legacy rows no longer become rule-family failures.

## UI Rendering

The dismissal diagnostics panel now has selectable `Derived Identity` rows and display-only `Evidence Used` rows. `All matching assumptions are correct` remains mutually exclusive with failed rule-family selections.

Diagnostic values are formatted before rendering. Arbitrary objects are not rendered directly in JSX, preventing `[object Object]` from appearing in the operator view.

## Rock Band Fixture

Regression example:

- Amazon: `Rock Band 3 [video game]`
- eBay: `Rock Band Track Pack: Classic Rock PS3`

Expected feedback:

- failed rule family: `core_game_identity`
- evidence sources: `amazon_title`, `ebay_title`, `ebay_game_name`
- not `numeric_installment`, `platform`, or `edition_version`

## Reporting

`integrations/analyze_matching_feedback.py` summarizes stored feedback by failed rule family, evidence source, dismissal reason, date range, and representative examples. The analyzer is read-only and does not call marketplaces, rescore rows, or write production data.

## Tests

Covered by `tests/test_matching_feedback.py`: legacy row mapping, evidence-only rows not becoming rule failures, all-correct clearing failures and evidence, the Rock Band Track Pack expected feedback shape, and analyzer aggregation counts.

## Caveats

This change improves feedback semantics and rendering only. Matching rules, opportunity scores, presentation eligibility, profitability logic, AI behavior, and marketplace behavior are unchanged.
