# MBOP Matching Intelligence Layer Requirements v2

Status: Partially implemented as of 2026-06-14. The data model, listing
snapshots, return/receiving evidence capture, notes for all dismissal reasons,
seller intelligence foundation, opportunity conversion backfill foundation, and
Amazon-to-eBay live scoring hooks are in place. Remaining work is tracked in
`ROADMAP.md`.

This version supersedes the prior download and adds:

- Seller Intelligence
- Seller Expansion Search
- Listing Snapshot Preservation
- Return Outcome Learning
- Opportunity Conversion Intelligence
- Notes stored for ALL dismissal reasons
- Matching-weight guidance
- Updated Codex instructions

## Seller Intelligence

Track:
- purchase_count
- unit_count
- return_count
- condition_return_count
- wrong_product_return_count
- average_roi
- median_roi
- offers_made
- offers_accepted
- offer_acceptance_rate
- average_offer_discount
- total_profit
- opportunity_count
- purchase_conversion_count
- purchase_conversion_rate
- seller_trust_score
- seller_status

Seller statuses:
- trusted
- normal
- watch
- avoid

Suggested rule:
2+ returns for wrong product/platform/edition or condition issues => avoid.

Hide by default but allow override.

Implementation note:
Seller `avoid` is advisory only for now. MBOP warns and penalizes but does not
hide avoid sellers by default until diagnostics are proven.

## Seller Expansion Search

Future capability:

When a purchase or offer is made:
- View Other Listings From Seller

Purpose:
- bundle opportunities
- combined shipping opportunities
- additional profitable inventory

Use Matching Intelligence to evaluate the seller's other inventory.

## Listing Snapshot Preservation

Capture snapshots when:
- opportunity created
- opportunity dismissed
- opportunity watched
- opportunity purchased
- offer made

Store:
- title
- subtitle
- description
- item specifics
- condition
- category
- price
- shipping
- quantity available
- seller data
- primary image
- all images
- raw payload
- timestamp

Reason:
Listings disappear. Training data should not.

## Return Outcome Learning

Returns are stronger training signals than dismissals.

Capture:
- return_reason
- operator_notes
- listing_snapshot_id
- seller_id
- ebay_item_id
- purchase_item_id

Examples:
- Wrong Edition
- Packaging / Condition Issue
- Non-North-American Version

Return outcomes should become matching-intelligence examples and receive higher future weighting than dismissals.

## Opportunity Conversion Intelligence

Track:
- opportunity_shown
- opportunity_watched
- opportunity_purchased
- purchase_matched
- received
- listed
- sold
- profitable

Purpose:
Learn which opportunities actually worked.

## Notes Requirement

Store notes for EVERY dismissal reason.

Examples:
- PEGI logo visible on back cover image
- Greatest Hits copy
- Missing shrink wrap
- Seller says resealed

Notes are training data and future-reason discovery data.

Implementation note:
Notes are saved for every dismissal reason when entered. Strong or required
note prompts are intentionally out of scope.

## Matching Weight Guidance (Future)

Suggested future weights:

- Manual ASIN correction = 10
- Purchased + sold profitably = 10
- Purchased + received = 8
- Purchased opportunity = 7
- Permanent dismissal = 5
- Watch = 2
- AI-only observation = 1

No ML implementation required now.

## Additional Codex Instruction

Implement:
1. Seller Intelligence data model.
2. Listing Snapshot Preservation.
3. Return Outcome Learning capture.
4. Opportunity Conversion Intelligence tracking.
5. Notes for all dismissal reasons.
6. Seller and return signals in future diagnostics.

Do NOT implement eBay -> Amazon sourcing yet.

Apply Matching Intelligence improvements to Amazon -> eBay sourcing first and iterate.
