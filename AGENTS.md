# AGENTS.md

## Project Overview

This repository contains the Amazon/eBay Operations System.

Purpose:
- automate eBay purchase ingestion
- automate shipment tracking
- support Amazon resale workflows
- reduce spreadsheet maintenance
- support receiving workflows
- support future AI-assisted operations

The system is evolving from a collection of automation scripts into a full operational workflow platform.

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

Current pattern:
- page.tsx composes the workspace and owns UI-local workflow state
- usePurchases owns purchase loading, save status, errors, and API mutations
- usePurchaseFilters owns filter state and filtered row derivation
- purchaseStats owns dashboard metric calculation
- table, filters, metrics, price cell, and drawer are separate components

Purchases table display rules:
- matched ASIN rows show the matched Amazon/RevSeller title as the primary item title when available
- matched ASIN rows show the eBay supplier title below, prefixed with "ebay: "
- unmatched rows show the eBay supplier title and a one-line Search Amazon link
- ETA shows carrier estimated delivery when available, otherwise eBay estimated delivery for undelivered items, and delivered date when delivered
- carrier ETA dates are displayed as date-only values to avoid timezone day shifts

Do not reintroduce large JSX blocks into page.tsx.

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

---

# Critical Architectural Rules

## Cost Calculation Rule

Frontend MUST NEVER recalculate landed cost.

Authoritative field:
vw_purchases_dashboard.unit_cost

Backend logic is authoritative.

---

## Workflow Separation Rule

Purchases workflow != Receiving workflow
Purchases workflow != eBay seller order workflow

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

Do not merge these workflows into one UI.

eBay seller orders are not purchases. Seller-order functionality must use separate future tables/workflows and must not write to purchases or purchase_items.

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
