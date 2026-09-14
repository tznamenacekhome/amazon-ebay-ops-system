# Guarded state field audit — 2026-09-13

Audited the eight tables present in the disposable database used by the migration acceptance tests. This is a local schema audit, not a fresh production schema claim. The state reader includes every column of these tables plus the explicit `pairHistory` projection. Any later schema expansion needs a renewed timestamp-path audit.

Previously every value contributed to the raw `jsonb::text` SHA-256 fingerprint. Numeric scale and native timestamp timezone formatting could change that text without changing business state. Objects already had PostgreSQL JSONB key ordering; arrays retained their SQL aggregation or source order. Null, boolean, identifiers, status and text must remain distinct. JSON numbers now normalize recursively; timestamp-looking strings inside raw payloads remain exact.

| Guard path | SQL type | Nullable | Semantic category |
| --- | --- | --- | --- |
| `actions.*.action_id` | uuid | NO | UUID identifier |
| `actions.*.opportunity_id` | uuid | YES | UUID identifier |
| `actions.*.candidate_id` | uuid | YES | UUID identifier |
| `actions.*.asin` | text | YES | text identifier |
| `actions.*.ebay_item_id` | text | YES | text identifier |
| `actions.*.action_type` | text | NO | text enum/status |
| `actions.*.dismiss_reason` | text | YES | nullable text |
| `actions.*.notes` | text | YES | nullable text |
| `actions.*.required_max_landed_cost` | numeric | YES | decimal monetary amount |
| `actions.*.required_roi_percent` | numeric | YES | decimal percentage/rate |
| `actions.*.expected_purchase_cost` | numeric | YES | decimal monetary amount |
| `actions.*.created_at` | timestamp with time zone | NO | timestamp |
| `actions.*.raw_action_context` | jsonb | YES | JSON (recursive objects/arrays/scalars) |
| `actions.*.listing_snapshot_id` | uuid | YES | UUID identifier |
| `blockedAsin.asin` | text | NO | text identifier |
| `blockedAsin.reason` | text | YES | nullable text |
| `blockedAsin.notes` | text | YES | nullable text |
| `blockedAsin.source_opportunity_id` | uuid | YES | UUID identifier |
| `blockedAsin.source_action_id` | uuid | YES | UUID identifier |
| `blockedAsin.blocked_by` | text | YES | nullable text |
| `blockedAsin.blocked_at` | timestamp with time zone | NO | timestamp |
| `blockedAsin.updated_at` | timestamp with time zone | NO | timestamp |
| `declinedOffers.*.ebay_legacy_item_id` | text | NO | text identifier |
| `declinedOffers.*.declined_offer_amount` | numeric | NO | decimal monetary amount |
| `declinedOffers.*.currency` | text | NO | text |
| `declinedOffers.*.first_seen_at` | timestamp with time zone | NO | timestamp |
| `declinedOffers.*.last_seen_at` | timestamp with time zone | NO | timestamp |
| `candidate.candidate_id` | uuid | NO | UUID identifier |
| `candidate.sourcing_run_id` | uuid | YES | UUID identifier |
| `candidate.seed_id` | uuid | YES | UUID identifier |
| `candidate.asin` | text | YES | text identifier |
| `candidate.ebay_item_id` | text | NO | text identifier |
| `candidate.ebay_legacy_item_id` | text | YES | text identifier |
| `candidate.ebay_title` | text | YES | nullable text |
| `candidate.ebay_image_url` | text | YES | nullable text |
| `candidate.ebay_item_web_url` | text | YES | nullable text |
| `candidate.seller_username` | text | YES | nullable text |
| `candidate.item_location_country` | text | YES | nullable text |
| `candidate.buying_options` | ARRAY | NO | ordered array |
| `candidate.condition_id` | text | YES | text identifier |
| `candidate.condition` | text | YES | nullable text |
| `candidate.price` | numeric | YES | decimal monetary amount |
| `candidate.shipping_cost` | numeric | YES | decimal monetary amount |
| `candidate.landed_cost` | numeric | YES | decimal monetary amount |
| `candidate.shipping_is_separate` | boolean | NO | boolean |
| `candidate.available_quantity` | integer | YES | integer |
| `candidate.is_multi_quantity` | boolean | NO | boolean |
| `candidate.auction_end_time` | timestamp with time zone | YES | timestamp |
| `candidate.current_bid` | numeric | YES | decimal numeric |
| `candidate.bid_count` | integer | YES | integer |
| `candidate.best_offer_enabled` | boolean | NO | boolean |
| `candidate.raw_ebay_json` | jsonb | NO | JSON (recursive objects/arrays/scalars) |
| `candidate.first_seen_at` | timestamp with time zone | NO | timestamp |
| `candidate.last_seen_at` | timestamp with time zone | NO | timestamp |
| `candidate.listing_status` | text | NO | text |
| `opportunity.opportunity_id` | uuid | NO | UUID identifier |
| `opportunity.sourcing_run_id` | uuid | YES | UUID identifier |
| `opportunity.seed_id` | uuid | YES | UUID identifier |
| `opportunity.candidate_id` | uuid | YES | UUID identifier |
| `opportunity.asin` | text | NO | text identifier |
| `opportunity.ebay_item_id` | text | YES | text identifier |
| `opportunity.opportunity_type` | text | NO | text enum/status |
| `opportunity.target_sale_price` | numeric | YES | decimal monetary amount |
| `opportunity.target_sale_price_source` | text | YES | nullable text |
| `opportunity.landed_cost` | numeric | YES | decimal monetary amount |
| `opportunity.profit` | numeric | YES | decimal monetary amount |
| `opportunity.roi_percent` | numeric | YES | decimal percentage/rate |
| `opportunity.total_profit_opportunity` | numeric | YES | decimal monetary amount |
| `opportunity.max_profitable_landed_cost` | numeric | YES | decimal monetary amount |
| `opportunity.max_offer_price` | numeric | YES | decimal monetary amount |
| `opportunity.required_offer_percent_of_ask` | numeric | YES | decimal percentage/rate |
| `opportunity.max_bid` | numeric | YES | decimal numeric |
| `opportunity.inventory_need_level` | text | YES | text enum/status |
| `opportunity.months_of_supply` | numeric | YES | decimal numeric |
| `opportunity.monthly_velocity` | numeric | YES | decimal numeric |
| `opportunity.score` | numeric | YES | decimal numeric |
| `opportunity.score_reason` | text | YES | nullable text |
| `opportunity.warning_flags` | ARRAY | NO | ordered array |
| `opportunity.ai_flags` | ARRAY | NO | ordered array |
| `opportunity.status` | text | NO | text enum/status |
| `opportunity.created_at` | timestamp with time zone | NO | timestamp |
| `opportunity.updated_at` | timestamp with time zone | NO | timestamp |
| `opportunity.initial_listing_snapshot_id` | uuid | YES | UUID identifier |
| `opportunity.latest_listing_snapshot_id` | uuid | YES | UUID identifier |
| `opportunity.seller_trust_status` | text | YES | nullable text |
| `opportunity.seller_trust_score` | numeric | YES | decimal numeric |
| `opportunity.matching_diagnostics_json` | jsonb | YES | JSON (recursive objects/arrays/scalars) |
| `velocityHolds.*.suppression_id` | uuid | NO | UUID identifier |
| `velocityHolds.*.asin` | text | NO | text identifier |
| `velocityHolds.*.source_action_id` | uuid | YES | UUID identifier |
| `velocityHolds.*.dismissed_at` | timestamp with time zone | NO | timestamp |
| `velocityHolds.*.velocity_at_dismissal` | numeric | YES | decimal numeric |
| `velocityHolds.*.metric_window_days` | integer | NO | integer |
| `velocityHolds.*.required_velocity` | numeric | NO | decimal numeric |
| `velocityHolds.*.current_velocity` | numeric | YES | decimal numeric |
| `velocityHolds.*.status` | text | NO | text enum/status |
| `velocityHolds.*.last_evaluated_at` | timestamp with time zone | YES | timestamp |
| `velocityHolds.*.reactivated_at` | timestamp with time zone | YES | timestamp |
| `velocityHolds.*.reason_code` | text | NO | text |
| `velocityHolds.*.raw_context_json` | jsonb | NO | JSON (recursive objects/arrays/scalars) |
| `velocityHolds.*.created_at` | timestamp with time zone | NO | timestamp |
| `velocityHolds.*.updated_at` | timestamp with time zone | NO | timestamp |
| `seed.seed_id` | uuid | NO | UUID identifier |
| `seed.sourcing_run_id` | uuid | YES | UUID identifier |
| `seed.asin` | text | NO | text identifier |
| `seed.seller_sku` | text | YES | nullable text |
| `seed.amazon_title` | text | YES | nullable text |
| `seed.amazon_image_url` | text | YES | nullable text |
| `seed.source_mode` | text | NO | text enum/status |
| `seed.target_sale_price` | numeric | YES | decimal monetary amount |
| `seed.target_sale_price_source` | text | YES | nullable text |
| `seed.last_sold_at` | timestamp with time zone | YES | timestamp |
| `seed.units_sold_60d` | integer | NO | integer |
| `seed.units_sold_90d` | integer | NO | integer |
| `seed.monthly_velocity` | numeric | YES | decimal numeric |
| `seed.current_inventory_units` | numeric | YES | decimal numeric |
| `seed.months_of_supply` | numeric | YES | decimal numeric |
| `seed.inventory_need_level` | text | YES | text enum/status |
| `seed.is_restricted` | boolean | NO | boolean |
| `seed.is_suppressed` | boolean | NO | boolean |
| `seed.is_return_heavy` | boolean | NO | boolean |
| `seed.warning_flags` | ARRAY | NO | ordered array |
| `seed.raw_context_json` | jsonb | NO | JSON (recursive objects/arrays/scalars) |
| `seed.created_at` | timestamp with time zone | NO | timestamp |
| `seed.coverage_cycle_id` | uuid | YES | UUID identifier |
| `seed.coverage_cycle_item_id` | uuid | YES | UUID identifier |
| `seed.queue_position` | integer | YES | integer |
| `seed.priority_bucket` | text | YES | text enum/status |
| `settings.*.setting_id` | uuid | NO | UUID identifier |
| `settings.*.min_amazon_price` | numeric | NO | decimal monetary amount |
| `settings.*.min_roi_percent` | numeric | NO | decimal percentage/rate |
| `settings.*.min_profit_dollars` | numeric | NO | decimal monetary amount |
| `settings.*.sales_lookback_days` | integer | NO | integer |
| `settings.*.inventory_need_months_threshold` | numeric | NO | decimal numeric |
| `settings.*.buyer_zip` | text | NO | text |
| `settings.*.buyer_country` | text | NO | text |
| `settings.*.item_location_countries` | ARRAY | NO | ordered array |
| `settings.*.delivery_country` | text | NO | text |
| `settings.*.best_offer_min_ask_percent` | numeric | NO | decimal percentage/rate |
| `settings.*.excluded_keywords` | ARRAY | NO | ordered array |
| `settings.*.created_at` | timestamp with time zone | NO | timestamp |
| `settings.*.updated_at` | timestamp with time zone | NO | timestamp |
| `pairHistory.*.id` | uuid | NO | UUID identifier |
| `pairHistory.*.status` | text | NO | text enum/status |
| `pairHistory.*.updated_at` | timestamp with time zone | NO | timestamp |

All arrays preserve order. SQL-created action/history/hold/settings arrays retain their explicit ordering. No array has been declared order-insensitive. Native UUIDs are serialized by PostgreSQL; input text is not trimmed or case-folded.

Native timestamp paths normalize to UTC with six microsecond digits (PostgreSQL stored precision). Actual microsecond changes still differ. Other strings, including embedded payload timestamps, retain exact text. The allowlist is:

- `actions.*.created_at`
- `blockedAsin.blocked_at`
- `blockedAsin.updated_at`
- `declinedOffers.*.first_seen_at`
- `declinedOffers.*.last_seen_at`
- `candidate.auction_end_time`
- `candidate.first_seen_at`
- `candidate.last_seen_at`
- `opportunity.created_at`
- `opportunity.updated_at`
- `velocityHolds.*.dismissed_at`
- `velocityHolds.*.last_evaluated_at`
- `velocityHolds.*.reactivated_at`
- `velocityHolds.*.created_at`
- `velocityHolds.*.updated_at`
- `seed.last_sold_at`
- `seed.created_at`
- `settings.*.created_at`
- `settings.*.updated_at`
- `pairHistory.*.updated_at`

Audit totals: 142 full-row columns across eight tables, plus three projected history fields. Type counts: `{"_text": 6, "bool": 6, "int4": 7, "jsonb": 5, "numeric": 33, "text": 44, "timestamptz": 19, "uuid": 22}`.

Exact numeric canonicalization uses PostgreSQL [`trim_scale(numeric)`](https://www.postgresql.org/docs/current/functions-math.html). Native [`jsonb` equality](https://www.postgresql.org/docs/current/datatype-json.html) compares the complete canonical state inside the locked transaction. The hash verifies the supplied capture and identifies idempotent requests; it does not authorize a write by itself.

The critical opportunity UPDATE additionally checks native UUID, text, timestamp and numeric fields against the captured database row. These predicates are redundant defense within the same transaction; the full canonical JSONB comparison is the complete expected-state check. No separate application precheck substitutes for it.

No production refresh client or deployment was completed. Exact Decimal token equivalence is covered directly in SQL without binary float conversion. A future production capture/refresh client must preserve decimal precision through transport rather than round arbitrary precision values to Python or JavaScript floats.
