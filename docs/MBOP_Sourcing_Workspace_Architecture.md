# MBOP Sourcing Workspace Architecture

Status: Companion Architecture Plan

Owner: Midnight Blue Enterprises, LLC

System: Midnight Blue Operations Platform (MBOP)

Related requirements document:
- `MBOP_Sourcing_Workspace_Requirements.md`

---

# Implementation Status - 2026-07-12 PT

Implemented entry points:
- `web/app/sourcing/page.tsx`
- `web/app/sourcing/useSourcingOpportunities.ts`
- `web/app/api/sourcing/opportunities/route.ts`
- `web/app/api/sourcing/opportunities/[id]/actions/route.ts`
- `web/app/api/sourcing/settings/route.ts`
- `web/app/api/sourcing/history/route.ts`
- `web/app/api/sourcing/runs/route.ts`
- `web/app/api/sourcing/coverage-cycle/route.ts`
- `web/app/api/sourcing/coverage-cycle/items/route.ts`
- `web/app/api/sourcing/daily-runs/route.ts`
- `integrations/build_sourcing_seed_asins.py`
- `integrations/ebay_sourcing_search.py`
- `integrations/score_sourcing_opportunities.py`
- `integrations/sourcing_coverage_cycle.py`
- `integrations/run_daily_catalog_sourcing.py`
- `integrations/run_daily_sourcing_discovery.py`
- `integrations/match_sourcing_purchases.py`
- `integrations/refresh_sourcing_listing_availability.py`
- `integrations/sourcing_common.py`

Manual legacy population sequence:

```powershell
$runId = [guid]::NewGuid().ToString()
python integrations/build_sourcing_seed_asins.py --mode recent_sales --limit 30 --run-id $runId
python integrations/ebay_sourcing_search.py --run-id $runId --limit 15 --max-results-per-asin 8
python integrations/score_sourcing_opportunities.py --run-id $runId --replace-run
```

Unified daily coverage-cycle sequence:

```powershell
python integrations/run_daily_catalog_sourcing.py --plan-only
python integrations/run_daily_catalog_sourcing.py
```

Current implementation notes:
- `sourcing_runs.status` uses only live schema-supported statuses: `planned`, `running`, `completed`, and `failed`.
- `sourcing_runs.source_count`, `search_count`, `candidate_count`, and `opportunity_count` are the implemented count columns.
- Fee context used by scoring is stored under `sourcing_seed_asins.raw_context_json.estimated_fee_cost`.
- Platform inference used by eBay search is stored under
  `sourcing_seed_asins.raw_context_json.inferred_system` when the Amazon title
  does not itself include a video-game platform.
- Seed creation skips replenishment ASINs when current sellable inventory exists,
  Amazon inventory planning shows units older than 30 days, and Amazon reports
  zero shipped units in the last 30 days. Out-of-stock ASINs remain eligible
  even when the last sale is old or absent.
- eBay candidates are upserted by the table's unique `ebay_item_id`; duplicate eBay listings returned for multiple seeds are deduped per search run.
- eBay pickup-only candidates are excluded when Browse API availability exposes
  pickup delivery options such as `SELLER_ARRANGED_LOCAL_PICKUP` without
  `shippingOptions`.
- UI actions are operator-only: `watching`, `dismissed`, `roi_snoozed`, and `purchased_pending_match`.
- `/api/sourcing/runs` starts the unified daily coverage-cycle workflow. The
  UI no longer launches separate Recent Sales and Full Listings discovery jobs.
- `run_daily_sourcing_discovery.py` is a compatibility wrapper around
  `run_daily_catalog_sourcing.py` for scheduler wiring. The unified runner
  spends the usable eBay Browse quota automatically each day.
- `sourcing_coverage_cycles` and `sourcing_coverage_cycle_items` store the
  durable ASIN pass. Priority order is recently sold in the last 90 days,
  purchased Amazon-bound items not yet sent to Amazon, then the remaining
  eligible catalog.
- When a daily catalog sourcing job finishes the active coverage cycle while
  Browse quota remains, it immediately creates and starts the next coverage
  cycle. The runner carries an in-memory ASIN exclusion set for the whole daily
  job, so an ASIN searched earlier in the same job is not searched again after
  the cycle rolls over.
- The Coverage Cycle tab shows cycle progress, priority-bucket progress, queue
  rows, recent `daily_catalog_sourcing` runs, and the last three completed
  coverage cycles with the same summary stats shown for the current cycle.
- Matching intelligence refresh is advisory for the sourcing-catalog scheduler
  group. Its failure is recorded in scheduler telemetry, but it no longer marks
  the whole sourcing-catalog group failed after the quota-spending sourcing job
  and listing availability refresh have already completed. Scheduler groups
  with only nonblocking failures record `degraded` telemetry and return process
  exit code 0 so ECS/EventBridge does not classify advisory failures as failed
  tasks.
- The opportunity detail drawer was removed after operator review.
- Table actions handle watch, purchased/offer made, and dismiss directly; table dismiss uses a modal for dismiss reason and notes.
- Auction type cells link to Gixen and copy the eBay item number to the clipboard.
- Type cells show backend-suggested Best Offer and auction bid amounts in USD.
  When eBay Browse returns an original non-USD amount, the cell also displays
  the original currency equivalent, such as CAD, using the Browse converted
  item-price ratio. Fixed-price rows read original currency from `price`;
  auction rows read it from `currentBidPrice`.
- Sourcing History separates scored rows from operator-presented rows. The
  `Shown` column uses the latest completed batch count, while the message can
  say `Scored N; shown M` so rejected/non-actionable scored rows are not
  confused with buyable opportunities.
- Replenishment defaults to `All Open`, the full current actionable queue across
  runs/cycles. The newest completed batch view is preserved as `New This Run`;
  batch membership is no longer the default limiting scope.
- Coverage Cycle summaries show `Opportunities Presented`, derived from unique
  `sourcing_opportunity_batch_items.opportunity_id` values in completed batches
  for all runs in the cycle.
- Quota stops such as `ebay_out_of_quota`, `ebay_rate_limited`, and
  `quota_reserve_reached` are displayed as "Out of quota" rather than failed
  sourcing jobs.
- `match_sourcing_purchases.py` performs exact item-ID matching only. It does not yet attempt title/price/date fallback matches.
- `purchased_pending_match` also represents Best Offers made by the operator. The matcher moves rows back to `watching` when no matching eBay purchase appears within 72 hours of the purchased/offer-made action.
- When the matcher finds the imported eBay purchase, it writes sourced ASIN, Amazon title, and `purchase_items.target_price` using the highest of Last Sold, Keepa 90-day, and current Buy Box price.
- Amazon images come from `vw_latest_amazon_listing_snapshot.raw_listing_json.summaries[0].mainImage.link` when available.
- `refresh_sourcing_listing_availability.py` checks open/watch/ROI-snoozed sourcing eBay item IDs through eBay Browse once per daily scheduler run. Ended, sold-out, or missing listings are moved to `dismissed` and recorded in `sourcing_actions` with dismiss reason `no_longer_available`. Purchased-pending rows are left for `match_sourcing_purchases.py` so accepted offers can still match imported eBay orders.
- `refresh_sourcing_listing_availability.py` sends the same buyer contextual ZIP
  header used by sourcing search and preserves an existing stored shipping
  option/cost when eBay item-detail responses omit `shippingOptions`.
- `score_sourcing_opportunities.py` normalizes structured eBay raw payload
  evidence for deterministic matching diagnostics, including item-specific
  Platform, Game Name, Region Code, Country of Origin, Format, Type, Features,
  Release Year, category IDs/names, seller description text, and image URL
  availability.
- `/api/sourcing/opportunities` hydrates Last Sold from the seed row first and
  then falls back to Amazon sales history by ASIN, which keeps full-listing
  opportunities from showing an empty Last Sold column when the ASIN has recent
  Amazon sales.
- Sourcing platform scoring uses seed `system`, then
  `raw_context_json.inferred_system`, then title detection. eBay item-specific
  Platform is preferred over title-only candidate platform detection.
- Clear wrong-platform, non-game/accessory, digital/service,
  incomplete-product, non-North-American region, sequel/year, Game Name, and
  edition/version conflicts are backend hard blocks before profitability can
  surface a row as open.

---

# Purpose

This document translates the approved Sourcing Workspace requirements into an implementation architecture for Codex.

The Sourcing Workspace is a standalone MBOP subsystem for finding inventory acquisition opportunities, starting with Amazon replenishment sourcing from eBay.

The MVP must remain read-only toward external marketplaces:
- No automated eBay purchases
- No automated eBay bids
- No automated Best Offers
- No Amazon write actions
- Operator remains final decision maker

---

# Existing MBOP Architecture Context

MBOP architecture:

```text
Python integrations
→ Supabase PostgreSQL
→ Next.js API routes
→ React frontend
```

Rules to preserve:
- Supabase is operational source of truth.
- Frontend must not talk directly to Supabase.
- Frontend renders backend/API-provided business logic.
- Business logic belongs in Python integrations, SQL views, or Next.js API routes.
- Sourcing must remain separate from Purchases, Receiving, FBA, Sales Orders, Repricing, and Order Problems.
- eBay seller orders must not be written to `purchases` or `purchase_items`.
- Sourcing opportunities should link to purchases only after a buyer purchase is imported and matched.

---

# MVP Scope

Build a new top-level workspace:

```text
Sourcing
```

Initial tabs:

```text
Sourcing
├── Replenishment
├── Watchlist
├── Purchased Pending Match
├── Sourcing History
├── Settings
```

Future tabs:

```text
Sourcing
├── Replenishment
├── eBay → Amazon
├── Wholesale
├── Watchlist
├── Purchased Pending Match
├── Sourcing History
├── Settings
```

Only implement Phase 1:
- Replenishment sourcing from known Amazon ASINs
- eBay candidate discovery
- profitability scoring
- AI visual flagging
- operator actions
- purchase matching by eBay item ID

---

# Data Sources

## Amazon Sales Orders

Use existing Amazon sales/profitability data for:
- Recent sold ASINs
- Most recent sale price
- 60/90 day velocity
- profit and ROI context where available

Recent Sales mode should use:
- most recent sale price within lookback window

Do not use BSR as a primary filter.

---

## Amazon Active Listings

Use existing Amazon listing / SKU / inventory tables for:
- Full Listing mode ASIN seeds
- Amazon title
- Amazon image if available
- listing/suppression/restriction warnings
- current Amazon inventory

Full Listing mode should use:
- Keepa New Condition 90-day average price when no recent sale exists

---

## Amazon Inventory

Use current canonical inventory where available:
- current Amazon FBA sellable inventory
- current inbound/outbound inventory where MBOP has reliable state
- current MBOP-owned pre-Amazon inventory when relevant

Inventory need calculation:
```text
Months Of Supply = Current Available Inventory / Monthly Sales Velocity
```

Need levels:
- `<1` = Critical
- `1-2` = High
- `2-4` = Medium
- `>4` = Low

---

## Keepa

Use existing Keepa product snapshots when available.

For Full Listing mode:
- Use Keepa New Condition 90-day average price as target sale price.

Keepa should remain read-only catalog intelligence.

Do not call Keepa from frontend page loads.

---

## eBay Browse API

Use eBay Browse API for sourcing search.

Primary endpoint:
```text
GET /buy/browse/v1/item_summary/search
```

Use user ZIP code for buyer-contextual shipping estimates:

```text
X-EBAY-C-ENDUSERCTX: contextualLocation=country%3DUS%2Czip%3D93022
```

Make ZIP configurable in Sourcing Settings.

Default:
```text
93022
```

Expected Browse API support:
- keyword search
- item title
- item image
- item web URL
- buying options
- auction detection
- Best Offer detection
- item ID / legacy item ID
- price
- shipping options
- item location
- seller summary
- pagination

Known validation needed:
- quantity available / multi-quantity reliability
- combined shipping discount availability
- exact shipping estimate behavior per listing type

Use conservative assumptions where API data is incomplete.

Shipping estimate states:
- `known_paid`: eBay returned a positive buyer-ZIP shipping price.
- `known_free`: eBay returned a zero buyer-ZIP shipping price.
- `unknown_no_cost`: eBay returned a shipping option without a price.
- `unknown_no_options`: eBay returned no buyer-ZIP shipping option.

When `sourcing_ebay_candidates.shipping_cost` is already populated, MBOP treats
that stored value as the buyer-ZIP quote even if `raw_ebay_json.shippingOptions`
is absent from a later detail/availability refresh. This prevents display and
scoring from regressing to `unknown_no_options` after eBay omits shipping from a
detail payload.

Unknown shipping candidates must remain visible when otherwise plausible, but MBOP must not calculate profit, ROI, max offer, or max bid from an assumed $0 shipping cost.

---

# eBay Search Rules

Condition:
```text
New only
```

Use condition ID:
```text
1000
```

Include buying types:
- Fixed price
- Auction
- Best Offer

Item location:
- United States
- Canada

Candidates outside the configured item-location countries must be hard-excluded from open opportunities, even if eBay returns them in search results.

Delivery country:
- United States

Candidates outside the configured item-location countries must be hard-excluded. Candidates with unknown shipping should be flagged and shown as watch opportunities when otherwise plausible, without profitability overclaiming.

No seller exclusions.

Excluded title keywords:
```text
download
gamesharing
message delivery
nfr
no game
not a game
not for resale
steam
vpn
disc only
```

These must be configurable.

---

# API Limit Strategy

Assume default eBay Browse API quota around:
```text
5,000 calls/day
```

Measured production audit:
- `docs/ebay_browse_call_efficiency_audit_2026-07-12.md` records the
  2026-07-12 eBay Browse call-efficiency audit. The monitored daily catalog
  sourcing run searched 248 ASINs and used 1,498 counted Browse calls, or 6.04
  calls per searched ASIN.
- The measured split was 666 search-query calls, averaging 2.69 searches per
  ASIN, plus 832 inferred item-detail shipping-enrichment calls, averaging 3.35
  detail calls per ASIN.
- Duplicate candidate hits across aliases were small in that run. The primary
  quota sink was eager detail enrichment for search results whose summaries did
  not include buyer-ZIP shipping.
- Priority optimization sequence: add search/detail/retry diagnostics, make
  detail enrichment lazy and bounded, add adaptive alias stopping, then revisit
  the eBay quota increase case with before/after evidence.

Implementation update:
- `docs/ebay_browse_call_optimization_implementation_2026-07-13.md` documents
  the first optimization pass. eBay search now uses one approved platform-aware
  query per ASIN, `category_ids=139973` for EBAY_US Video Games software, and a
  first-page `limit=200` without pagination. DS, original Xbox, and GameCube
  seeds are not searched.
- `ebay_sourcing_search.py` maps and filters summary rows before any detail
  call. Item detail is called only for plausible candidates with missing data
  needed for final matching or scoring, and in-run detail calls are cached by
  eBay item ID plus buyer context.
- Exact search/detail/retry counters and compact detail-call records are stored
  under `sourcing_runs.raw_summary_json.ebay_search`; the Coverage Cycle Daily
  Runs table displays the backend-owned metrics.

MBOP treats `buy.browse` as a shared daily budget, not as a fixed opportunity
count. Before quota-based sourcing discovery, `run_sourcing_workflow.py` calls
eBay Developer Analytics `GET /developer/analytics/v1_beta/rate_limit/` and
reads the `buy.browse` resource. The workflow then searches seed chunks until
the usable remaining quota is exhausted, all seeds are searched, or eBay returns
a persistent 429. Quota exhaustion is a normal stop condition:

```text
stop_reason = ebay_out_of_quota
display = Out of quota
```

The same `buy.browse` quota is also used by:
- `ebay_sourcing_search.py` item summary search
- `ebay_sourcing_search.py` item-detail shipping enrichment
- `refresh_sourcing_listing_availability.py` active listing availability checks
- `ebay_sync_buyer_purchases.py` legacy-item detail enrichment for missing
  platform/system values

When sourcing consumes the remaining daily quota, those other Browse-backed
enrichments may skip or report errors until the eBay reset time. Buyer purchase
ingestion itself still uses the legacy Trading API for orders and does not
depend on Browse for the core order import.

Implementation guardrails:
- Cache search results by ASIN/query/filter set.
- Store eBay item IDs and last seen payload.
- Do not re-fetch permanently dismissed listings.
- Do not frequently re-fetch ROI-snoozed listings unless price/recheck cadence requires it.
- Enrich only candidates that pass first-pass filters.
- Prefer one search call per seed ASIN/query.
- Use low result limits first, then expand if needed.
- Track daily call counts locally.
- Add a dry-run or plan mode for broad scans.

---

# Proposed Database Schema

Use UUID primary keys unless project conventions differ.

## sourcing_settings

Stores operator-configurable defaults.

Suggested columns:
- `setting_id`
- `min_amazon_price numeric default 20.99`
- `min_roi_percent numeric default 40`
- `min_profit_dollars numeric`
- `sales_lookback_days integer default 90`
- `inventory_need_months_threshold numeric default 2`
- `buyer_zip text default '93022'`
- `buyer_country text default 'US'`
- `item_location_countries text[] default ['US','CA']`
- `delivery_country text default 'US'`
- `best_offer_min_ask_percent numeric default 60`
- `excluded_keywords text[]`
- `created_at`
- `updated_at`

---

## sourcing_runs

One row per sourcing scan.

Suggested columns:
- `sourcing_run_id`
- `run_type text`
  Allowed: `recent_sales`, `full_listings`
- `status text`
  Allowed: `planned`, `running`, `completed`, `failed`
- `started_at`
- `completed_at`
- `settings_snapshot jsonb`
- `source_count integer`
- `search_count integer`
- `candidate_count integer`
- `opportunity_count integer`
- `api_call_count integer`
- `error_message text`
- `raw_summary_json jsonb`

---

## sourcing_seed_asins

ASINs selected for a sourcing run.

Suggested columns:
- `seed_id`
- `sourcing_run_id`
- `asin text`
- `seller_sku text`
- `amazon_title text`
- `amazon_image_url text`
- `source_mode text`
  Allowed: `recent_sales`, `full_listings`
- `target_sale_price numeric`
- `target_sale_price_source text`
  Allowed: `most_recent_sale`, `keepa_new_90d_avg`
- `last_sold_at timestamptz`
- `units_sold_60d integer`
- `units_sold_90d integer`
- `monthly_velocity numeric`
- `current_inventory_units numeric`
- `months_of_supply numeric`
- `inventory_need_level text`
  Allowed: `critical`, `high`, `medium`, `low`, `unknown`
- `is_restricted boolean`
- `is_suppressed boolean`
- `is_return_heavy boolean`
- `warning_flags text[]`
- `raw_context_json jsonb`
- `created_at`

---

## sourcing_ebay_candidates

Raw or lightly normalized eBay listing candidates.

Suggested columns:
- `candidate_id`
- `sourcing_run_id`
- `seed_id`
- `asin text`
- `ebay_item_id text`
- `ebay_legacy_item_id text`
- `ebay_title text`
- `ebay_image_url text`
- `ebay_item_web_url text`
- `seller_username text`
- `item_location_country text`
- `buying_options text[]`
- `condition_id text`
- `condition text`
- `price numeric`
- `shipping_cost numeric`
- `landed_cost numeric`
- `shipping_is_separate boolean`
- `available_quantity integer`
- `is_multi_quantity boolean`
- `auction_end_time timestamptz`
- `current_bid numeric`
- `bid_count integer`
- `best_offer_enabled boolean`
- `raw_ebay_json jsonb`
- `first_seen_at`
- `last_seen_at`
- `listing_status text`
  Allowed: `active`, `ended`, `unknown`

Indexes:
- unique on `ebay_item_id`
- index on `asin`
- index on `sourcing_run_id`
- index on `seed_id`

---

## sourcing_opportunities

Scored opportunities shown to the operator.

Suggested columns:
- `opportunity_id`
- `sourcing_run_id`
- `seed_id`
- `candidate_id`
- `asin text`
- `ebay_item_id text`
- `opportunity_type text`
  Allowed:
  - `buy_now`
  - `multi_unit`
  - `best_offer`
  - `auction`
  - `watch`
  - `no_profitable_source_found`
- `target_sale_price numeric`
- `target_sale_price_source text`
- `landed_cost numeric`
- `profit numeric`
- `roi_percent numeric`
- `total_profit_opportunity numeric`
- `max_profitable_landed_cost numeric`
- `max_offer_price numeric`
- `required_offer_percent_of_ask numeric`
- `max_bid numeric`
- `inventory_need_level text`
- `months_of_supply numeric`
- `monthly_velocity numeric`
- `score numeric`
- `score_reason text`
- `warning_flags text[]`
- `ai_flags text[]`
- `status text`
  Allowed:
  - `open`
  - `watching`
  - `roi_snoozed`
  - `dismissed`
  - `purchased_pending_match`
  - `matched_to_purchase`
  - `expired`
- `created_at`
- `updated_at`

Indexes:
- index on `status`
- index on `asin`
- index on `ebay_item_id`
- unique on active `ebay_item_id + asin` where appropriate

---

## sourcing_ai_observations

AI visual/title review outputs.

Suggested columns:
- `observation_id`
- `opportunity_id`
- `candidate_id`
- `asin text`
- `ebay_item_id text`
- `flag_type text`
- `flag_category text`
  Examples:
  - `region`
  - `packaging`
  - `product`
  - `listing_quality`
- `confidence numeric`
- `severity text`
  Allowed: `low`, `medium`, `high`
- `observation_text text`
- `model_name text`
- `input_snapshot_json jsonb`
- `raw_ai_json jsonb`
- `created_at`

Initial AI flags should be advisory only.

No auto-exclusion in MVP.

---

## sourcing_actions

Operator actions for training and workflow.

ASIN blocking is a product-level sourcing control, not a listing-level match
failure. The Sourcing UI exposes it inside the bulk `Dismiss selected` modal
for selected opportunities and the single-row dismiss modal for one-off triage.
The API records a dismissed action with `dismiss_reason = asin_blocked`, writes
the ASIN to `sourcing_blocked_asins`, and dismisses existing active
opportunities for that ASIN. Future sourcing seed generation excludes rows in
`sourcing_blocked_asins`.

Suggested columns:
- `action_id`
- `opportunity_id`
- `candidate_id`
- `asin text`
- `ebay_item_id text`
- `action_type text`
  Allowed:
  - `dismissed`
  - `roi_snoozed`
  - `watching`
  - `purchased`
  - `unwatch`
  - `restore`
- `dismiss_reason text`
  Required when `action_type = dismissed`
- `notes text`
- `required_max_landed_cost numeric`
- `required_roi_percent numeric`
- `expected_purchase_cost numeric`
- `created_at`

Dismiss reasons:
- `wrong_product`
- `wrong_platform`
- `wrong_edition_version`
- `non_north_american_version`
- `packaging_condition_issue`
- `incomplete_product`
- `not_worth_selling`
- `other`

---

## sourcing_purchase_matches

Links sourcing opportunities to imported eBay purchases.

Suggested columns:
- `match_id`
- `opportunity_id`
- `ebay_item_id text`
- `purchase_id`
- `purchase_item_id`
- `match_method text`
  Allowed:
  - `ebay_item_id`
  - `legacy_item_id`
  - `manual`
  - `title_price_date_fallback`
- `match_confidence numeric`
- `matched_at`
- `review_required boolean default false`
- `review_status text`
  Allowed: `pending`, `approved`, `rejected`, `not_required`

Primary matching key:
```text
ebay_item_id
```

Do not require operator to enter eBay order ID.

---

# Backend Integration Scripts

## integrations/ebay_sourcing_search.py

Responsibilities:
- Accept a list of seed ASINs or run ID.
- Build eBay search queries from Amazon title.
- Apply Browse API filters.
- Send contextual location header.
- Store candidates.
- Track API call counts.
- Preserve raw payloads.

Required modes:
- dry-run
- write
- limit
- run-type recent_sales/full_listings
- max-results-per-asin

---

## integrations/build_sourcing_seed_asins.py

Responsibilities:
- Build seed ASIN list for recent sales mode.
- Build seed ASIN list for full listings mode.
- Exclude stale in-stock/no-30-day-sale ASINs from replenishment seed creation.
- Store inferred platform/system context from Amazon listing and Keepa/catalog
  snapshots for video-game titles that do not include a platform.
- Compute target sale price source.
- Compute 60/90 day velocity.
- Compute inventory need.
- Store `sourcing_seed_asins`.

---

## integrations/ebay_sourcing_search.py

Responsibilities:
- Search eBay Browse for seed ASINs.
- Include video-game platform/system terms in eBay search queries.
- If the Amazon title lacks a platform but seed context inferred one from
  Amazon/Keepa/catalog data, search with platform-qualified queries instead of
  the generic title-only query.
- Preserve raw eBay payloads and buyer-ZIP shipping context.

---

## integrations/score_sourcing_opportunities.py

Responsibilities:
- Read seed ASINs and eBay candidates.
- Apply deterministic match diagnostics for platform boundaries, title overlap,
  excluded keywords, digital/download listings, region/version signals,
  incomplete/not-game listings, pickup-only delivery, edition/version warnings,
  historical dismissal memory, and seller trust.
- Apply profitability formulas.
- Classify opportunity type.
- Compute score.
- Create/update `sourcing_opportunities`.

Best Offer:
- compute max offer price
- compute required offer percent of asking price
- exclude if required offer percent < 60%
- use the lower of stored Keepa 90-day average price and current Amazon market price for Best Offer profitability caps

Auction:
- compute max bid

Multi-unit:
- mark as multi-unit when quantity data is available
- if combined shipping cannot be calculated, flag as possible opportunity rather than overclaiming ROI

---

## integrations/ai_review_sourcing_candidates.py

Responsibilities:
- Send eBay image/title and Amazon image/title to AI.
- Store observations.
- Do not auto-dismiss.
- Skip opportunities already dismissed permanently.
- Support limit/batch mode.

Initial recommended flags:
- non-ESRB / foreign region signals
- missing shrink wrap
- possible reseal
- disc only
- case only
- wrong edition
- wrong platform
- damaged packaging

---

## integrations/match_sourcing_purchases.py

Responsibilities:
- Match `purchased_pending_match` opportunities to imported eBay buyer purchases.
- Enrich matched purchase item rows with ASIN, Amazon title, and target sell price from sourcing context.
- Move unmatched rows back to `watching` after 72 hours when no eBay purchase is imported.
- Primary match by eBay item ID / legacy item ID.
- Create `sourcing_purchase_matches`.
- Update opportunity status to `matched_to_purchase`.
- If ambiguous, create review-required match row.

This script should run after eBay buyer purchase sync.

---

# API Routes

Use Next.js API routes.

## GET /api/sourcing/opportunities

Query params:
- mode
- status
- scope
- opportunityType
- search
- asin
- flags
- minProfit
- minRoi
- needLevel
- page
- pageSize
- sort

Returns:
- paginated opportunity rows
- summary counts
- current settings snapshot

Default scope is `all_open`, which returns still-open actionable rows from
current and prior sourcing runs before applying the established exact eBay
listing dedupe and score/recency/ASIN grouping order. `scope=new_this_run`
returns the newest completed batch only, and `scope=prior_unreviewed` returns
open rows not included in the newest completed batch.

---

## POST /api/sourcing/runs

Creates a sourcing run.

Body:
- runType: `recent_sales` or `full_listings`
- options: optional override settings

MVP can create run records and require scripts to execute separately if background execution is not yet available.

---

## POST /api/sourcing/opportunities/[id]/actions

Actions:
- dismiss
- roi_snooze
- watch
- purchased
- restore

Validation:
- permanent dismiss requires dismiss reason
- purchased stores expected cost and eBay item ID
- ROI snooze stores action context; MBOP calculates required landed cost from current Amazon pricing and profitability settings

---

## GET /api/sourcing/history

Returns historical opportunities and actions.

---

## GET /api/sourcing/settings

Returns current settings.

---

## PATCH /api/sourcing/settings

Updates settings:
- min Amazon price
- min ROI
- min profit
- buyer ZIP
- excluded keywords
- best offer minimum accepted ask percent
- lookback days
- inventory thresholds

---

# Frontend Structure

Suggested files:

```text
web/app/sourcing/page.tsx
web/app/sourcing/SourcingTabs.tsx
web/app/sourcing/ReplenishmentTable.tsx
web/app/sourcing/OpportunityDetailDrawer.tsx
web/app/sourcing/SourcingFilters.tsx
web/app/sourcing/SourcingSettings.tsx
web/app/sourcing/WatchlistTable.tsx
web/app/sourcing/PurchasedPendingMatchTable.tsx
web/app/sourcing/SourcingHistoryTable.tsx
web/app/sourcing/useSourcingOpportunities.ts
web/app/api/sourcing/...
```

Add `Sourcing` to `web/app/AppShell.tsx`.

Keep UI dense and table-focused.

---

# Replenishment Table Columns

Required:
- eBay image
- Amazon image
- eBay title
- Amazon title
- landed cost
- profit
- ROI
- velocity
- inventory need
- opportunity type
- AI flags
- action buttons

Actions:
- Open eBay
- Watch
- ROI Snooze
- Dismiss
- Purchased / Offer Made
- Copy For Gixen when auction

---

# Detail Drawer

Show:
- larger eBay image
- larger Amazon image
- full eBay title
- full Amazon title
- pricing breakdown
- target sale price and source
- velocity and inventory need
- AI observations
- raw eBay listing link
- dismiss action with required reason
- ROI snooze action
- purchased action
- auction max bid / Gixen copy fields

---

# Business Logic Details

## Profitability

Use existing MBOP profitability conventions where possible.

ROI target is configurable.

Profit must account for:
- target sale price
- estimated Amazon fees
- fulfillment cost
- landed eBay cost

If exact fees are unavailable in MVP:
- use existing Amazon Sales Orders/profitability data where available
- otherwise mark as missing fee context and be conservative

---

## No-Profit Clarification

Do not exclude an ASIN merely because the last sale had low/no profit.

Only exclude a candidate when:
- no eBay source meets profitability requirements
- no viable Best Offer path exists
- no viable auction bid path exists
- no multi-unit opportunity remains plausible

---

## Multi-Unit Logic

Prioritize multi-unit listings.

Do not exclude when single-unit ROI fails if:
- multiple units are available
- separate shipping may combine
- combined shipping savings could make ROI viable

If exact combined shipping is unavailable:
- display as multi-unit opportunity
- do not overstate profit
- show conservative one-unit ROI and flag possible combined-shipping upside

---

## Best Offer Logic

Calculate required offer.

Best Offer reference price:
- Use the lower of stored Keepa 90-day average price and current Amazon market price.
- If Keepa values are unavailable, fall back to the seed target sale price.
- Keepa remains a stored backend snapshot lookup; do not call Keepa from frontend page loads.

Suggested item offer:
```text
Best Offer landed cap - eBay shipping cost
```

60% rule:
```text
suggested item offer / eBay asking price before shipping
```

Display if:
- Best Offer enabled
- required offer >= 60% of item ask price
- profitability would meet threshold at required offer

Exclude if:
- required offer < 60% of item ask price

---

## Auction Logic

Calculate max bid from target profitability.

Show auction opportunities where:
- current bid is below max bid
- auction has not ended

Provide Gixen copy support:
- eBay item ID
- max bid

---

# Status Semantics

Opportunity statuses:
- `open`
- `watching`
- `roi_snoozed`
- `dismissed`
- `purchased_pending_match`
- `matched_to_purchase`
- `expired`

Permanent dismissed:
- never show in open opportunities again

ROI snoozed:
- hidden until ROI/profitability criteria are met

Watching:
- visible in Watchlist
- Watch is the current replacement for ROI Snoozed. Watch actions store the
  current purchase-cost reference and profitable landed-cost cap.
- A watched opportunity can return to open Replenishment when normal scoring
  says it is open and either the eBay purchase-cost reference improves or the
  Amazon sale-price/profitability context raises the profitable landed-cost cap.
- Best Offer watch baselines use the suggested item offer before shipping as
  the purchase-cost reference.

Purchased pending match:
- visible until eBay buyer purchase sync imports and match script links purchase
- may also mean a Best Offer was made and the expected order has not appeared yet
- moves back to Watchlist after 72 hours without a matching eBay purchase

Matched:
- preserved in history

Expired:
- listing ended before purchase

---

# AI Learning Path

MVP:
- AI flags only
- operator decides
- store actions and reasons

Future:
- compute AI precision per flag
- suggest auto-hide rules
- operator approves auto-hide
- never silently auto-hide in MVP

Training pairs:
- AI observations
- operator action
- dismiss reason
- eventual purchase/sale/profit outcome

---

# Implementation Phases

## Phase 1A: Schema and Settings

- Add sourcing schema.
- Add settings table.
- Add Sourcing nav placeholder.
- Add settings API.

## Phase 1B: Seed ASIN Generation

- Build recent sales seed ASIN job.
- Build full listings seed ASIN job.
- Store velocity and inventory need.

## Phase 1C: eBay Search

- Implement Browse API client/search script.
- Use buyer ZIP contextual location.
- Store candidates.

## Phase 1D: Scoring

- Apply exclusions.
- Compute landed cost, profit, ROI.
- Classify opportunity types.
- Create opportunities.

## Phase 1E: UI

- Build Replenishment table.
- Handle high-frequency actions directly in the table.
- Use lightweight modal only for dismiss reason and notes.
- Add actions.

## Phase 1F: Operator Actions and History

- Implement dismiss, snooze, watch, purchased.
- Store actions.
- Add history.

## Phase 1G: Purchase Matching

- Match purchased opportunities to eBay purchases by item ID.
- Add Purchased Pending Match tab.

## Phase 1H: AI Flags

- Add AI visual review.
- Store observations.
- Display flags.

---

# Testing Plan

## Unit/Logic Tests

Test:
- ROI calculation
- Best Offer 60% rule
- auction max bid
- excluded keyword filtering
- inventory need calculation
- status transitions
- dismiss reason required
- purchased pending match behavior

## Integration Tests

Test:
- eBay Browse search with contextual ZIP
- condition filter new only
- auction result parsing
- Best Offer parsing
- shipping estimate parsing
- image/title extraction
- item ID matching to buyer purchase payloads

## Manual Validation

Use a small ASIN set first:
- 5 recent sellers
- 5 active listings with no recent sales

Verify:
- search quality
- landed cost accuracy
- image display
- AI flags
- dismiss workflow
- purchased matching

---

# Safety and Boundaries

Do not:
- purchase on eBay
- bid on eBay
- submit Best Offers
- modify Amazon listings
- modify Informed
- write sourcing candidates into purchases
- write sourcing candidates into purchase_items

Only link sourcing opportunity to purchase after the eBay purchase exists in MBOP.

---

# Future Features

## eBay → Amazon Sourcing

Search eBay broadly, find matching Amazon ASIN, then score if criteria are met.

This is the future Flipmine replacement.

## Wholesale Sourcing

Import wholesale price lists, match to Amazon ASINs, evaluate profitability.

## AI Auto-Hide

Only after sufficient training data and operator approval.

## Better Auction Workflow

Potential future:
- Gixen link/copy enhancement
- Review other sniping services only if they offer a safe/public API

---

# Final Codex Instruction

Build this iteratively.

Do not attempt to implement every phase at once.

Start with:
1. Schema
2. Settings
3. Seed ASIN generation
4. eBay Browse API search with ZIP-based shipping
5. Candidate storage
6. Basic opportunity scoring
7. Replenishment UI table

Then add:
- operator actions
- purchase matching
- AI visual flags
