# Best Offer item-only threshold verification — 2026-09-07

Requested rule: minimum acceptable offer is 60% of the eBay ITEM asking price,
with shipping payable in full and included in profitability. A $100 listing
with $10 shipping requires at least a $70 profitable landed-cost budget to
qualify at a $60 item offer. The threshold is not $66.

Inspection found the final scorer already enforced this rule in
`score_sourcing_opportunities.suggested_offer`: subtract shipping from the
landed budget, then compare the item offer against the item-price percentage.
The earlier conversational description of that scorer was inaccurate.

The search prefilter in `ebay_sourcing_search.candidate_decision` checked the
item-price floor against the landed cap without reserving known shipping.
The local change now compares item price times the configured percentage PLUS
full known shipping with the landed cap. Unknown shipping remains eligible
for detail lookup when the item price alone is plausible; it does not become
an actionable offer without a known shipping quote.

Validation against production's currently open Best Offer rows:

- Current configured minimum item-ask percentage: 60%.
- Open Best Offer opportunities evaluated: 109.
- No longer eligible: 0.
- Stored offer amounts requiring correction: 0.
- No opportunity rows were changed or removed; all already satisfy the rule.
- Watched, dismissed, purchased and other operator workflow states were not
  altered. Existing matching, ROI and profit settings were not changed.
- Evidence: `logs/diagnostics/offer-item-only-20260907/` (Git-ignored), including
  normalized source records and per-opportunity results.

Tests: 17 search tests and 15 progressive/scoring tests passed. New regression
cases cover $100/free shipping at a $60 landed cap; $100 + $10 shipping failing
at a $60 cap; and that same paid-shipping listing passing at a $70 cap with a
$60 item offer. Unknown-shipping detail eligibility is preserved.

Deployment status: activated September 8, 2026 in scheduler revision 86,
source commit `11dfabd0a41c`. The operator authorized the complete pending
release. The sourcing schedule cadence and all non-task fields were preserved.
The item-only rule itself needs no schema migration; it shipped alongside the
declined-offer integration's additive migration and web release.
See `RELEASE_2026-09-08_SOURCING_OFFERS.md` for activation and rollback evidence.
