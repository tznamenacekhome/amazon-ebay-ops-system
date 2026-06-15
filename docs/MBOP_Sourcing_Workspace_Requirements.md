# MBOP Sourcing Workspace - Implementation Specification

Status: Approved For Development

Owner: Midnight Blue Enterprises, LLC

System: Midnight Blue Operations Platform (MBOP)

This document contains the canonical requirements, business rules, architecture decisions, workflow definitions, AI-learning strategy, eBay API findings, and implementation guidance for the MBOP Sourcing Workspace MVP.

## Implementation Status - 2026-06-13 PT

Phase 1 is implemented as an initial usable workspace:
- Top-level `/sourcing` workspace added to MBOP navigation.
- Replenishment, Watchlist, Purchased Pending Match, Sourcing History, and Settings tabs are present.
- Recent Sales seed generation writes `sourcing_seed_asins`.
- eBay Browse API candidate search writes/upserts `sourcing_ebay_candidates`.
- Basic opportunity scoring writes `sourcing_opportunities`.
- Operator actions record rows in `sourcing_actions` and update opportunity workflow status.
- Settings are editable through `/api/sourcing/settings`.
- Amazon images are populated from latest Amazon listing snapshots when available.
- The opportunity detail drawer was removed after operator review; sourcing actions are handled directly from the table and lightweight dismiss modal.
- Table dismiss opens a lightweight modal for dismiss reason and notes, avoiding the slower drawer path for common triage.
- Auction opportunity type links to Gixen and copies the eBay item number for paste-in bidding setup.
- `Digital Item` is available as a dismiss reason.
- `No Longer Available` is available as a dismiss reason.
- A daily sourcing listing availability job refreshes open/watch/ROI-snoozed opportunity eBay listings and automatically dismisses ended, sold-out, or missing listings with `no_longer_available`.
- Sourcing search and scoring hard-exclude items not located in the US or Canada.
- eBay Browse calls use an encoded buyer contextual location header so calculated shipping is returned more reliably.
- Unknown-shipping candidates are retained as visible watch opportunities when otherwise plausible; MBOP must not treat unknown shipping as free shipping.
- If a later availability/detail refresh omits `shippingOptions` but MBOP already
  has `sourcing_ebay_candidates.shipping_cost`, the stored shipping cost remains
  the authoritative buyer-ZIP quote for display and scoring. This avoids false
  `No ZIP quote` labels after eBay returns an item-detail payload without
  shipping options.
- Purchase matching script exists for exact eBay item ID / legacy item ID matches against imported eBay purchases.
- The Sourcing page `Run Sourcing` button can execute the sourcing workflow for Recent Sales, Full Listings, or both depending on the selected source mode.
- Full Listings seed generation has been dry-run validated against active listing and Keepa snapshot data.

Initial data population was run against recent-sales mode with 30 seed ASINs, 15 seed searches, and 47 scored eBay candidates/opportunities. This remains an advisory sourcing queue only; no external marketplace write actions are performed.

Not yet implemented:
- Scheduled/automatic execution of purchased pending match after eBay buyer purchase sync.
- AI image/title observations.
- Restricted ASIN and return-heavy detection beyond warning placeholders.
- Full Listings production sourcing run beyond seed dry-run validation.
- Automatic ROI snooze reactivation.
- Mature API quota/cache cadence for dismissed and snoozed listings.

## Purpose

The Sourcing Workspace is MBOP's inventory acquisition engine.

Primary goal:
- Identify profitable inventory purchasing opportunities for Amazon resale.

Data sources:
- Amazon sales history
- Amazon inventory
- Amazon profitability
- Keepa
- eBay Browse API
- Operator sourcing history
- AI visual analysis

Operator remains the final decision maker.

No automated purchasing, bidding, or offer submission.

## Workspace Structure

Phase 1:

- Replenishment
- Watchlist
- Purchased Pending Match
- Sourcing History
- Settings

Future:
- eBay → Amazon sourcing
- Wholesale sourcing

## Replenishment Modes

### Recent Sales Mode

Source:
- Amazon sales in last 90 days

Pricing:
- Use most recent sale price

Purpose:
- Restock proven sellers

### Full Listings Mode

Source:
- All active Amazon listings

Pricing:
- Use Keepa New Condition 90-day average price

Purpose:
- Find sourcing opportunities even without recent sales

## Product Eligibility Rules

Exclude:
- Restricted ASINs

Warn only:
- Suppressed listings
- Return-heavy listings

Minimum Amazon sale price:
- $20.99

## Inventory Need

Months of Supply =
Current Available Inventory / Monthly Velocity

Need levels:
- <1 month = Critical
- 1-2 months = High
- 2-4 months = Medium
- >4 months = Low

Velocity source:
- 90-day Amazon sales history

## eBay Search Rules

API:
- eBay Browse API
- GET /buy/browse/v1/item_summary/search

Buyer location:
- Use encoded contextualLocation with ZIP 93022 (configurable)
- Header format: `X-EBAY-C-ENDUSERCTX: contextualLocation=country%3DUS%2Czip%3D93022`

Condition:
- New only
- Condition ID 1000

Include:
- Buy It Now
- Best Offer
- Auctions

Item location:
- US and Canada
- Items outside US/Canada must never be shown as open opportunities.

Delivery country:
- US
- If eBay returns a buyer ZIP shipping price, use it in landed cost.
- If eBay returns free shipping, display free shipping and use $0 shipping in landed cost.
- If eBay does not return a buyer ZIP shipping price, keep the candidate visible as a watch opportunity when otherwise plausible, flag it as unknown shipping, and do not compute profit/ROI or offer/bid guidance from a fake $0 shipping assumption.

No seller exclusions.

## Excluded Keywords

- download
- gamesharing
- message delivery
- nfr
- no game
- not a game
- not for resale
- steam
- vpn
- disc only

User-configurable.

## Opportunity Types

- Buy Now
- Multi-Unit Opportunity
- Best Offer Opportunity
- Auction Opportunity
- Watch
- No Profitable Source Found

## Best Offer Rules

Best Offer profitability uses the lower of:
- Keepa 90-day average price
- current Amazon market price

The suggested offer is:
- Best Offer landed cap minus eBay shipping cost

The 60% test compares the suggested item offer against the eBay asking price before shipping.

Only show Best Offer opportunities if profitability can be achieved with an offer >= 60% of asking price.

Exclude if required offer is below 60% of asking price.

## Auction Rules

Calculate:
- Maximum Bid
- Expected Profit
- Expected ROI

Store:
- ebay_item_id
- auction_end_time
- max_bid

Initial integration:
- Copy For Gixen (item ID + max bid)
- No automated bidding

## Ranking

Sort priority:

1. Multi-unit opportunities
2. Total profit opportunity
3. Inventory need
4. ROI

ROI is configurable but not primary sort order.

After priority sorting, the Replenishment list groups rows by ASIN while
preserving the highest-priority row's ASIN group position. This lets the
operator review all opportunities for the same product together.

## Title Match Guardrails

eBay may return unrelated games when the platform matches. MBOP must hard-block
an opportunity when the Amazon title and eBay result title have no meaningful
title-token overlap after removing platform and generic tokens such as Nintendo,
Wii, Xbox, PlayStation, Switch, game, games, edition, new, and sealed.

Example:
- Amazon title: Carnival Games - Nintendo Wii
- eBay result title: Go Play Circus Star (Nintendo Wii, 2009)
- Result: blocked because only the platform overlaps.

## eBay Search Platform Aliases

Sourcing search must account for common seller platform abbreviations in eBay
titles. In addition to the system text in the Amazon title, MBOP searches title
variants with these platform aliases:

- Xbox One: xb1
- PlayStation 2: ps2
- PlayStation 3: ps3
- PlayStation 4: ps4
- PlayStation 5: ps5
- Nintendo Switch: Switch
- Nintendo Wii: Wii
- Nintendo Wii U: Wii U, wiiu

Wii and Wii U must remain distinct. When the seed ASIN is a Wii game, eBay
results detected as Wii U games must be excluded even when eBay's search result
ranking returns them.

## Opportunity Grid

Columns:

- eBay Image
- Amazon Image
- eBay Title
- Amazon Title
- Landed Cost
- Profit
- ROI
- Velocity
- Inventory Need
- Opportunity Type
- AI Flags

Landed Cost format:
- $20.00 ($5 ship)
- $20.00 if free shipping
- Needs quote / item price shown separately when eBay does not return a shipping estimate
- When eBay returns converted pricing, the grid shows MBOP's USD landed-cost
  values and a secondary original-currency line, such as CAD item and shipping
  amounts, so Seller Central/eBay page comparisons are understandable.

Row action behavior:
- Single-row actions such as Dismiss, Watch, and Purchased/Offer Made update the
  current grid locally and remove the acted-on row without reloading or
  resorting the remaining rows.
- Bulk actions also remove affected rows locally without re-sorting.
- The Replenishment list may re-sort only after explicit Refresh, tab changes,
  search/filter changes, settings re-apply, or a new sourcing run.

## AI Visual Analysis

Inputs:
- eBay image
- eBay title
- Amazon image
- Amazon title

AI generates observations only.
AI does not decide whether to buy.

### AI Observation Categories

Region:
- PEGI
- CERO
- USK
- Foreign language packaging
- Non-ESRB ratings

Packaging:
- Missing shrink wrap
- Possible reseal
- Minor shrink-wrap damage
- Major shrink-wrap damage
- Crushed packaging
- Water damage
- Sticker damage

Product:
- Disc only
- Case only
- Missing manual
- Wrong edition
- Collector edition
- Steelbook

Listing quality:
- Stock photo
- Low resolution image

## Important Business Rules

### Non-North-American Versions

Do not buy.

Examples:
- PEGI
- PAL
- Japanese versions
- Foreign packaging

These all map to one business rule:
- Non-North-American Version

### Disc Only

Do not buy.

Disc only means:
- No complete retail package

### Loose Disc

Allowed.

A loose disc inside a sealed game case is acceptable and should not trigger exclusion.

### Packaging Damage

Minor shrink-wrap damage:
- Warning only

Missing shrink wrap or likely reseal:
- High severity warning
- Operator decides

## Dismiss Workflow

### Permanent Dismiss

Never show again.

Requires reason.

### ROI Snooze

Valid product.
Price too high.

Store:
- ROI threshold
- MBOP-calculated required/current cost context

Automatically reactivate when profitability meets criteria.

### Watch

Watch replaces ROI Snoozed in the current operator workflow.

When an operator marks a row Watch, MBOP stores the current purchase-cost
baseline and current profitable landed-cost cap. A watched opportunity should
return to the open Replenishment list when all normal opportunity tests pass and
either:
- the eBay purchase-cost reference falls below the watched baseline
- the Amazon sale-price/profitability context raises the profitable landed-cost cap

For Buy It Now and auction rows, the purchase-cost reference is landed cost when
known, otherwise item price. For Best Offer rows, the purchase-cost reference is
the suggested item offer before shipping.

Watched rows with no stored baseline remain in the Watchlist until acted on
again or otherwise refreshed into a row with baseline context.

## Dismiss Reasons

Product Identity:
- Wrong Product
- Wrong Platform
- Wrong Edition / Version

Regional:
- Non-North-American Version

Packaging / Condition:
- Packaging / Condition Issue

Incomplete Product:
- Disc only
- Case only
- Missing manual
- Missing components

Business:
- Not Worth Selling
- Other

## Purchased / Offer Made Workflow

Operator can mark:
- Purchased / Offer Made

Store:
- opportunity_id
- ebay_item_id
- asin
- expected cost

Status:
- Purchased Pending Match

This status is used for both completed eBay purchases and Best Offers that the operator made and expects may become an order.

Monitoring rule:
- After eBay buyer purchase sync, MBOP attempts to match Purchased Pending Match opportunities by eBay item ID.
- If a matching eBay purchase is imported, MBOP links the opportunity to the purchase.
- When a match is found, MBOP writes the sourced ASIN, Amazon title, and target sell price to the matched purchase item.
- The matched purchase target sell price uses the highest available value from Last Sold, Keepa 90-day, and current Buy Box price.
- If no matching purchase is found within 72 hours of the Purchased / Offer Made action, MBOP moves the opportunity back to Watchlist and records an action note.

## Purchase Matching

Primary matching key:
- ebay_item_id

When eBay purchase sync imports purchases:
- Automatically match opportunity to purchase

No manual order ID entry required.

## Data Model

Suggested tables:

- sourcing_runs
- sourcing_seed_asins
- sourcing_opportunities
- sourcing_ai_observations
- sourcing_actions
- sourcing_history

## Training Data

Store:

AI observations:
- What AI detected

Operator outcomes:
- Purchased
- Dismissed
- ROI Snoozed
- Watching

Dismiss reasons:
- Non-North-American Version
- Packaging / Condition Issue
- Incomplete Product
- etc.

Future:
- AI may recommend auto-hide rules after sufficient accuracy and operator trust.
- No automatic exclusions in MVP.

## eBay API Notes

Browse API appears sufficient for:
- Search
- Images
- Titles
- Best Offer detection
- Auction detection
- Listing URLs
- Item IDs
- Shipping estimates

Use buyer ZIP code for shipping estimates.

Current default Browse API limits are approximately 5,000 calls/day.

Implementation should:
- Cache aggressively
- Avoid re-querying dismissed listings
- Avoid frequent refresh of ROI snoozed listings
- Enrich only top candidates
- Persist results for reuse

## Out of Scope for MVP

- Automated purchases
- Automated bidding
- Automated offer submission
- eBay → Amazon sourcing workflow
- Wholesale sourcing workflow
- Automatic AI exclusions
