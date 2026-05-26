# AGENTS.md

## Project Overview

This repository contains the Midnight Blue Operations Platform (MBOP).

Purpose:
- automate eBay purchase ingestion
- automate shipment tracking
- support Amazon resale workflows
- reduce spreadsheet maintenance
- support receiving workflows
- support future AI-assisted operations

MBOP supports Midnight Blue Enterprises, LLC. The system is evolving from a collection of automation scripts into a full operational workflow platform.

---

# Core Architecture

Python Integrations
-> Supabase PostgreSQL
-> Next.js API Routes
-> React Frontend

Supabase is the operational source of truth.

Frontend never talks directly to Supabase.

Pattern:
Frontend
-> API Routes
-> Supabase

---

# Current Frontend Structure

Purchases UI lives under:
- web/app/page.tsx
- web/app/purchases/

Dashboard UI lives under:
- web/app/dashboard/
- web/app/api/dashboard/

Current pattern:
- AppShell provides the shared left-side navigation for Dashboard, Purchases, Receiving, Amazon FBA, and Repricing
- page.tsx composes the workspace and owns UI-local query/workflow state
- usePurchases owns purchase loading, save status, errors, API mutations, and currently disabled query-aware cache support
- /api/purchases owns purchase list filtering, sorting, pagination, and summary counts
- table, filters, metrics, price cell, and drawer are separate components

Purchases table display rules:
- matched ASIN rows show the matched Amazon/RevSeller title as the primary item title when available
- matched ASIN rows show the eBay supplier title below, prefixed with "ebay: "
- unmatched rows show the eBay supplier title and a one-line Search Amazon link
- ETA shows carrier estimated delivery when available, otherwise eBay estimated delivery for undelivered items, and delivered date when delivered
- carrier ETA dates are displayed as date-only values to avoid timezone day shifts
- table headers sort through /api/purchases query parameters
- status filter uses backend-normalized purchase_items.current_status
- status filter includes Received for items warehouse-verified by the receiving workflow and Cancelled for cancelled/refunded purchase outcomes
- detail drawer saves eBay title, Amazon title, purchase price, system, ASIN, and sell price together
- detail drawer can edit system using the canonical system pick list
- detail drawer can create manual split item rows for multi-game eBay listings

Do not reintroduce large JSX blocks into page.tsx.
Do not reintroduce full-table client-side purchases filtering/sorting; add backend query behavior instead.
Do not add UI-only status derivation; backend sync/workflow code owns purchase_items.current_status.

---

# Shipment Tracking Rules

eBay import owns:
- tracking number ingestion
- carrier ingestion when eBay provides it
- seller shipped/no-tracking signal
- eBay delivery date when provided

EasyPost owns carrier tracking enrichment:
- carrier status
- normalized status
- carrier ETA
- tracking events
- public tracking URL

ETA precedence:
- delivered item: delivered date
- undelivered item with carrier ETA: EasyPost/carrier ETA
- undelivered item without carrier ETA: eBay estimated delivery date

EasyPost sync must:
- reuse existing easypost_tracker_id values
- avoid invalid placeholder tracking values
- stay at or below 5 EasyPost requests per second
- retry 429 responses with backoff
- pass known carrier when available

Long-term tracking updates should come from EasyPost webhooks once the app has a public HTTPS endpoint.

Local sync orchestration:
- `run_all_syncs.py` runs eBay buyer purchase sync, EasyPost shipment sync, supplier returns sync, and RevSeller enrichment
- `run_all_syncs.bat` is the Windows scheduler entry point and should target `C:\Dev\amazon-ebay-ops-system`
- scheduler output belongs in `logs/scheduler.log`

---

# Critical Architectural Rules

## SQL Change Workflow

When a schema or migration SQL command is required, provide the SQL as the immediate next step for the operator to apply before continuing dependent development.

After the operator confirms the SQL was applied, resume implementation and verification.

## Cost Calculation Rule

Frontend MUST NEVER recalculate landed cost.

Authoritative field:
vw_purchases_dashboard.unit_cost

Backend logic is authoritative.

---

## Workflow Separation Rule

Purchases workflow != Receiving workflow
Purchases workflow != eBay seller order workflow
Purchases workflow != Amazon FBA shipment workflow
Receiving workflow != Amazon FBA shipment workflow

Purchases workflow:
- sourcing verification
- operational review
- ASIN review
- shipment visibility

Receiving workflow:
- warehouse verification
- quantity verification
- split shipment handling
- exception handling
- marketplace assignment after receipt
- received-date capture for later reporting/querying

Amazon FBA workflow:
- shipment preparation after receiving
- grouping Received Amazon-bound purchase items by ASIN
- InventoryLab CSV export
- shipment ID association
- moving included quantities from Received to Listed
- leaving excluded quantities in Received

Current receiving entry points:
- web/app/AppShell.tsx
- web/app/receiving/page.tsx
- web/app/api/receiving/route.ts

Current Amazon FBA entry points:
- web/app/AppShell.tsx
- web/app/fba/page.tsx
- web/app/api/fba-shipments/route.ts

Current Aged Amazon Inventory repricing advisor entry points:
- web/app/AppShell.tsx
- web/app/repricing/page.tsx
- web/app/api/amazon/repricing-advisor/route.ts

Amazon SP-API integrations:
- must remain read-only until a specific write workflow is designed
- may use inventory, listings, and pricing read endpoints
- must not request restricted PII data or Amazon seller order/customer data
- must write normalized Amazon seller/FBA data to Amazon-specific tables, not purchases or purchase_items
- current FBA inventory sync entry point is `integrations/amazon_sync_fba_inventory.py`
- current Amazon listing status sync entry point is `integrations/amazon_sync_listing_status.py`

Keepa integrations:
- must remain read-only catalog intelligence
- must not write to purchases, purchase_items, receiving rows, FBA shipment rows, or Amazon seller workflow tables
- may store product price, sales-rank, offer, review, rating, and raw payload data in Keepa-specific tables
- must be token-aware; use plan/dry-run modes before broad syncs
- current product sync entry point is `integrations/keepa_sync_products.py`

Do not merge these workflows into one UI.

Purchases may display the workflow status Received when the receiving workflow sets purchase_items.current_status = received, but receiving verification itself belongs in the receiving workflow.
Receiving may also set Return Pending when an item is physically received but should be returned.
Receiving detail links eBay titles to the eBay listing when a listing URL or item ID is available, and links Amazon titles to Amazon using ASIN.
Amazon-bound received items must have ASIN and sell price before they can be marked Received; eBay-bound received items do not require Amazon title, ASIN, or sell price.

Cancelled is a purchase-item workflow status. It must be preserved by purchase sync and status normalization. The future return/refund workflow must include Cancelled because cancelled items still need refund confirmation.

eBay seller orders are not purchases. Seller-order functionality must use separate future tables/workflows and must not write to purchases or purchase_items.

Dashboard metrics must use backend/API aggregation and authoritative purchase item unit_cost values. The first dashboard report groups purchase units and cost by order month and excludes Return Opened rows, Cancelled rows, plus purchase_items explicitly flagged with exclude_from_purchase_reporting. Do not recalculate landed cost in frontend components.
Personal purchases and business supplies must be excluded through explicit backend flags, not title/system guesses.

---

## Matching Engine Rule

Video games are platform-specific.

Never auto-match across systems.

Examples:
- Minecraft PS4 != Minecraft Switch
- Madden Xbox != Madden PS5

Matching logic must consider:
- title
- system/platform
- ambiguity handling

System/platform must be populated by backend import/enrichment logic.
Frontend may display system, but must not infer it from titles.

System display names are canonical backend values such as Switch, PS 5, Xbox One, and PC.

Marketplace title cleaning is shared by frontend search links and backend matching preparation:
- Python: clean_marketplace_title_for_search
- TypeScript: cleanMarketplaceTitleForSearch

Use this cleaner before Amazon catalog searches or fuzzy matching against marketplace titles.

Manual corrections:
- ASIN/sell-price corrections should propagate only to matching title/system rows
- never overwrite a different existing ASIN during propagation
- manual match memory belongs in manual_item_matches after the SQL migration is applied
- Amazon title corrections belong in purchase_items.amazon_title and must remain separate from eBay supplier titles
- edited eBay titles and purchase prices are item-specific manual overrides and must not propagate by title/system
- edited system values are item-specific corrections and should use canonical system names
- eBay sync must preserve manual_title_override and manual_unit_cost_override fields
- manual split child rows must not be consumed by eBay sync fallback matching

---

# Frontend Philosophy

Optimize for:
- operational throughput
- large monitors
- dense information layouts
- minimal clicks
- keyboard efficiency

Explicitly NOT:
- consumer UX
- card-heavy layouts
- mobile-first design
