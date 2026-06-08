# MBOP Sourcing Workspace Architecture

Status: Companion Architecture Plan

Owner: Midnight Blue Enterprises, LLC

System: Midnight Blue Operations Platform (MBOP)

Related requirements document:
- `MBOP_Sourcing_Workspace_Requirements.md`

---

# Implementation Status - 2026-06-07 PT

Implemented entry points:
- `web/app/sourcing/page.tsx`
- `web/app/sourcing/useSourcingOpportunities.ts`
- `web/app/api/sourcing/opportunities/route.ts`
- `web/app/api/sourcing/opportunities/[id]/actions/route.ts`
- `web/app/api/sourcing/settings/route.ts`
- `web/app/api/sourcing/history/route.ts`
- `web/app/api/sourcing/runs/route.ts`
- `integrations/build_sourcing_seed_asins.py`
- `integrations/ebay_sourcing_search.py`
- `integrations/score_sourcing_opportunities.py`
- `integrations/match_sourcing_purchases.py`
- `integrations/sourcing_common.py`

Manual population sequence:

```powershell
$runId = [guid]::NewGuid().ToString()
python integrations/build_sourcing_seed_asins.py --mode recent_sales --limit 30 --run-id $runId
python integrations/ebay_sourcing_search.py --run-id $runId --limit 15 --max-results-per-asin 8
python integrations/score_sourcing_opportunities.py --run-id $runId --replace-run
```

Current implementation notes:
- `sourcing_runs.status` uses only live schema-supported statuses: `planned`, `running`, `completed`, and `failed`.
- `sourcing_runs.source_count`, `search_count`, `candidate_count`, and `opportunity_count` are the implemented count columns.
- Fee context used by scoring is stored under `sourcing_seed_asins.raw_context_json.estimated_fee_cost`.
- eBay candidates are upserted by the table's unique `ebay_item_id`; duplicate eBay listings returned for multiple seeds are deduped per search run.
- UI actions are operator-only: `watching`, `dismissed`, `roi_snoozed`, and `purchased_pending_match`.
- The opportunity detail drawer was removed after operator review.
- Table actions handle watch, purchased/offer made, and dismiss directly; table dismiss uses a modal for dismiss reason and notes.
- Auction type cells link to Gixen and copy the eBay item number to the clipboard.
- `match_sourcing_purchases.py` performs exact item-ID matching only. It does not yet attempt title/price/date fallback matches.
- `purchased_pending_match` also represents Best Offers made by the operator. The matcher moves rows back to `watching` when no matching eBay purchase appears within 72 hours of the purchased/offer-made action.
- When the matcher finds the imported eBay purchase, it writes sourced ASIN, Amazon title, and `purchase_items.target_price` using the highest of Last Sold, Keepa 90-day, and current Buy Box price.
- Amazon images come from `vw_latest_amazon_listing_snapshot.raw_listing_json.summaries[0].mainImage.link` when available.

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
- Compute target sale price source.
- Compute 60/90 day velocity.
- Compute inventory need.
- Store `sourcing_seed_asins`.

---

## integrations/score_sourcing_opportunities.py

Responsibilities:
- Read seed ASINs and eBay candidates.
- Apply keyword exclusions.
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
