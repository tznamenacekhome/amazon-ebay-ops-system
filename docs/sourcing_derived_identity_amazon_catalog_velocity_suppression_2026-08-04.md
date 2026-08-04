# Derived Identity, Amazon Catalog Evidence, and Velocity Suppression

Date: 2026-08-04

## Scope

Implemented a backend-owned derived game identity representation for sourcing diagnostics, a read-only Amazon Catalog Items cache integration, and dynamic ASIN-level suppression for opportunities dismissed as `sales_velocity_too_low`.

No AI calls, image analysis, eBay Browse calls, marketplace writes, purchases, offers, bids, or historical reopening are part of this change.

## Derived Identity Parser

`integrations/sourcing_match_rules.py` now emits `derived_identity` in matching diagnostics:

- `coreGame`
- `installment`
- `installmentNormalized`
- `edition`
- `platform`
- `region`
- `packageContents`
- `completeness`
- `digitalPhysical`

The React diagnostics panel displays this backend-owned identity and no longer derives core game/installment values independently.

Roman numerals normalize to Arabic comparison values for known game families. Example: `Final Fantasy XIV` and `Final Fantasy 14` both normalize to installment `14`, while display keeps `XIV / 14` for the Roman side.

## Regression Fixture Results

- Wipeout 3 vs ABC's Wipeout 2:
  - Core Game: `Wipeout / Wipeout`
  - Installment: `3 / 2`
  - Edition: `Base / Standard`
  - Platform: `Nintendo 3DS / Nintendo 3DS`
  - Result: `installment_conflict`
- Final Fantasy XIV / 14 Complete Edition PS4:
  - Core Game: `Final Fantasy / Final Fantasy`
  - Installment normalized: `14 / 14`
  - Edition: `Complete Edition`
  - Platform: `PlayStation 4`
- Rock Band 3 vs Rock Band Track Pack Classic Rock:
  - Core products remain distinct: `Rock Band` vs `Rock Band Track Pack: Classic Rock`

## Amazon Catalog Items

Added `integrations/amazon_sync_catalog_items.py`, a read-only SP-API Catalog Items v2022-04-01 cache utility. It requests:

- `attributes`
- `summaries`
- `relationships`
- `productTypes`
- `classifications`
- `images`
- `identifiers`

Observed representative ASIN dry-run artifact:

`tmp/amazon_catalog_items_identity_dry_run_20260804150230.json`

Representative ASINs fetched:

- `B008E6ZXBI`
- `B000TSZADA`
- `B07HFMJ4R5`

Useful observed keys included:

- `attributes.item_name`
- `attributes.hardware_platform`
- `attributes.platform_for_display`
- `attributes.edition`
- `attributes.format`
- `attributes.item_package_quantity`
- `attributes.variation_theme`
- `productTypes.productType`
- top-level `relationships`, `summaries`, `classifications`, `images`, `identifiers`

No parent/child ASIN relationship values were returned for the three representative ASINs; the cache preserves raw relationship payloads and variation theme data when present.

Evidence precedence:

1. Exact ASIN Catalog Items structured attributes
2. Exact child-ASIN variation data when present in the payload
3. Existing trusted MBOP/Amazon metadata
4. Normalized Amazon title
5. Unknown

Catalog Items are cached in `amazon_catalog_item_identity_snapshots`; page rendering does not call SP-API.

## Sales Velocity Suppression

When an operator dismisses an opportunity as `sales_velocity_too_low`, MBOP creates or updates an active ASIN-level suppression in `sourcing_sales_velocity_suppressions`.

The suppression stores:

- ASIN
- source action/date
- velocity at dismissal
- metric window
- required velocity
- current velocity
- status
- last evaluated timestamp
- reactivated timestamp
- reason code

Current threshold is represented as at least one sale inside the configured sourcing lookback window, converted to monthly velocity. With a 90-day lookback, the threshold is `0.3333` sales/month.

Suppression semantics:

- Active suppressions are excluded from default Replenishment.
- The new `Sales Velocity Suppressed` view shows active suppressed ASINs with current/required velocity and release eligibility.
- Seed generation reevaluates active suppressions whenever velocity refreshes.
- Sub-threshold improvement stays suppressed.
- Crossing the threshold releases the suppression.
- Business-only velocity suppressions remain `valid_match_poor_opportunity` / `business_issue` and do not create identity-negative examples.

## Dry Runs

Current presented opportunity reevaluation:

- Command: `integrations/reprocess_current_unreviewed_sourcing.py --limit 500`
- Artifact: `tmp/sourcing_unreviewed_reprocess_dry_run_20260804150200.json`
- Rows in scope: 500
- Status transitions: `open->open`: 500
- Newly hard-blocked: 0
- Rows leaving presentation: 0

Sales velocity suppression backfill:

- Command: `integrations/backfill_sales_velocity_suppressions.py`
- Artifact: `tmp/sales_velocity_suppression_backfill_dry_run_20260804150216.json`
- Dismissal actions found: 2,110
- ASIN suppressions selected: 21

## Production Write Results

Migration:

- `supabase db push` applied `20260804000000_mbop_sourcing_catalog_velocity_suppression.sql`.
- Follow-up `supabase migration list` confirmed local and remote migration ledgers aligned through `20260804000000`.

Sales velocity suppression backfill:

- Command: `integrations/backfill_sales_velocity_suppressions.py --write`
- Artifact: `tmp/sales_velocity_suppression_backfill_write_20260804223137.json`
- Dismissal actions found: 2,110
- ASIN suppressions selected: 21
- Rows written: 21

Amazon Catalog Items cache:

- Command: `integrations/amazon_sync_catalog_items.py --current-opportunities --limit 50 --write`
- Artifact: `tmp/amazon_catalog_items_identity_write_20260804223141.json`
- ASINs fetched: 18
- Rows written: 18
- Calls were read-only Catalog Items API calls. No eBay quota-consuming search was run.

Current presented opportunity reevaluation:

- Command: `integrations/reprocess_current_unreviewed_sourcing.py --write`
- Artifact: `tmp/sourcing_unreviewed_reprocess_write_20260804223800.json`
- Rows in scope: 3,451
- Rows processed: 3,451
- Unchanged: 3,397
- Newly hard-blocked: 2
- Downgraded from open to rejected: 12
- Rows leaving presentation: 12
- Rows entering presentation: 0
- Recommendation changes: 2
- Status transitions: `open->open`: 3,439, `open->rejected`: 12
- Purchased, completed, and dismissed rows touched: 0

## Migration

Forward migration:

`supabase/migrations/20260804000000_mbop_sourcing_catalog_velocity_suppression.sql`

Adds:

- `amazon_catalog_item_identity_snapshots`
- `sourcing_sales_velocity_suppressions`

`supabase migration list` showed all earlier migrations aligned with remote. After explicit operator approval, `supabase db push` applied this migration and a follow-up ledger check confirmed remote alignment.

## Validation

Passed:

- `python -m unittest tests.test_sourcing_match_rules tests.test_amazon_catalog_items tests.test_sourcing_velocity_suppression tests.test_sourcing_progressive_batches`
- `python -m py_compile` for changed sourcing/catalog/backfill/SP-API scripts
- `npm.cmd --prefix web run build`

## Caveats

- Catalog Items evidence is cached only for ASINs fetched through the new utility; unfetched ASINs continue to fall back through existing trusted MBOP/Amazon metadata and title normalization.
- Product Type Definitions were not used for ASIN values; Catalog Items is the ASIN-level evidence source.
- Historical Sales Velocity Too Low dismissals were backfilled as active ASIN-level business suppressions without reopening historical opportunities or creating identity-negative evidence.
