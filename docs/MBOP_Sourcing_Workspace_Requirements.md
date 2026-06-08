# MBOP Sourcing Workspace - Implementation Specification

Status: Approved For Development

Owner: Midnight Blue Enterprises, LLC

System: Midnight Blue Operations Platform (MBOP)

This document contains the canonical requirements, business rules, architecture decisions, workflow definitions, AI-learning strategy, eBay API findings, and implementation guidance for the MBOP Sourcing Workspace MVP.

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
- Use contextualLocation with ZIP 93022 (configurable)

Condition:
- New only
- Condition ID 1000

Include:
- Buy It Now
- Best Offer
- Auctions

Item location:
- US and Canada

Delivery country:
- US

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
- Required max cost

Automatically reactivate when profitability meets criteria.

### Watch

Manual monitoring.

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

## Purchased Workflow

Operator can mark:
- Purchased

Store:
- opportunity_id
- ebay_item_id
- asin
- expected cost

Status:
- Purchased Pending Match

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
