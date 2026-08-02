# Sourcing Diagnostics, Near-Miss, And Receiving Feedback

Date: 2026-08-02

Scope: operator feedback and quality-control workflow for sourcing matching.
This change adds diagnostics review in the dismissal flow, a listing/photo
mismatch dismissal reason, a Closest Excluded sourcing tab, a receiving
`Sourcing false positive` outcome, and a scoped reprocess tool for current open
opportunities.

Out of scope: AI, image analysis, profitability/ROI changes, seller-threshold
changes, search-query changes, sourcing priority changes, Browse quota changes,
marketplace actions, historical reopening, and unrelated shipment-sync edits.

## UI/API Changes

- Sourcing dismissal dialog now has an expandable `Matching Diagnostics`
  panel.
- The panel renders backend-provided `diagnosticComparison` data and does not
  duplicate matching logic in React.
- Operators can mark individual assumptions as incorrect or select
  `All matching assumptions are correct`. Those choices are mutually exclusive.
- Dismiss action payloads persist diagnostics feedback in
  `sourcing_actions.raw_action_context` and in the listing snapshot
  `raw_context_json`.
- Sourcing has a new `Closest Excluded` tab backed by
  `GET /api/sourcing/opportunities?scope=closest_excluded&limit=50`.
- Closest Excluded rows support `Mark Valid`, `Confirm`, and
  `Open Diagnostics`; these store matching-intelligence evidence only and do
  not purchase, bid, offer, message, or reopen historical rows.
- Receiving now includes `Sourcing False Positive` as an outcome and exposes
  compact failed-element toggles.

## Diagnostic Comparison Fields

The backend comparison shape is `diagnostic_comparison_v1` and includes:

- core game identity
- full title
- platform/system
- installment/sequel number
- edition/version
- region
- eBay Game Name item specific
- category
- format/type
- release year
- package/bundle contents
- completeness
- digital versus physical
- item location
- seller listing/photo consistency indicator
- final recommendation
- hard-block reasons
- warnings
- confidence/evidence summary
- ASIN/eBay opportunity context

Missing evidence is returned as null and rendered as `Not available`.

## Storage Model

No new table is required for sourcing diagnostic feedback. The durable storage
is:

- `sourcing_actions.raw_action_context.diagnosticsFeedback`
- `sourcing_actions.raw_action_context.diagnosticComparison`
- `sourcing_listing_snapshots.raw_context_json.diagnosticsFeedback`
- `sourcing_listing_snapshots.raw_context_json.diagnosticComparison`
- immediate exact examples in `matching_intelligence_examples` for
  `seller_listing_mismatch`, `mark_valid_match`, and `confirm_exclusion`

Receiving needed one schema change because the existing outcome check
constraint did not allow `sourcing_false_positive`.

Migration:

- `supabase/migrations/20260802000000_mbop_sourcing_feedback_outcomes.sql`

## Seller Listing Mismatch

New dismissal reason:

- Display: `Seller Listing Does Not Match Photos`
- Internal value: `seller_listing_mismatch`

Semantics:

- `match_label = non_match`
- `label_type = negative_identity`
- exact eBay item ID is listing-specific negative evidence
- `raw_action_context.evidenceSource = image_conflict`
- seller intelligence receives the same product/condition style strike path as
  existing identity dismissals
- similar titles/listings are not broadly poisoned solely from this reason

## Closest Excluded Ranking

The API ranks excluded candidates on the backend using stored evidence:

- existing opportunity score
- shared title-token count from diagnostics
- platform match evidence
- category evidence
- recommendation before/after block
- hard-block severity

The result is capped at 50 rows and includes total qualifying count in the
normal opportunities summary. Obvious low-review-value rows such as exact
historical negatives and no-longer-available exclusions are filtered out.

## Receiving False Positive

New receiving outcome:

- `sourcing_false_positive`

Behavior:

- creates a receiving problem/return-pending style exception
- stores failed matching elements in
  `matching_intelligence_receiving_outcomes.raw_context_json.failedMatchingElements`
- is rebuilt as `non_match` / `negative_identity` with very-high evidence
- preserves seller listing/photo mismatch as a failed element when selected
- does not automate returns, refunds, messages, or marketplace actions

## Reprocessing

Script:

```powershell
.\.venv\Scripts\python.exe integrations\reprocess_current_unreviewed_sourcing.py
.\.venv\Scripts\python.exe integrations\reprocess_current_unreviewed_sourcing.py --write
```

Scope:

- current `open` sourcing opportunities only
- no purchased, matched, completed, dismissed, or ROI-snoozed rows
- no historical reopening
- no marketplace actions

The script writes local JSON artifacts under `tmp/` for dry-run and write mode.

## Validation

Pre-commit validation:

- Python compile check for matching-intelligence and reprocess modules: passed.
- Next.js production build: passed.

Additional test/deployment/reprocess results are recorded in the final operator
report after deployment.

## Caveats

- Existing historical positive examples are not rewritten by this change.
- Rebuilds preserve new sourcing-action evidence because the action labels are
  now mapped in `build_matching_intelligence_examples.py`.
- The UI renders diagnostics from backend JSON. Any future diagnostic rows
  should be added in `web/app/api/sourcing/diagnosticComparison.ts`.
