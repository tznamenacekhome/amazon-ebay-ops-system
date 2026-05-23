# Purchases Frontend

This folder contains the purchases workflow UI.

## Boundaries

- `page.tsx` composes the workspace and owns UI-local workflow state.
- `usePurchases` owns purchase loading, save status, errors, and API mutations.
- `usePurchaseFilters` owns filter state and filtered row derivation.
- Table, filter, metric, price-cell, and drawer components stay presentation-focused.

## Table Display

- Matched ASIN rows use `amazon_title` as the primary item title when available.
- Matched ASIN rows show the eBay supplier title below, prefixed with `ebay: `.
- Unmatched rows use the eBay supplier title as the primary item title.
- Unmatched rows show a one-line `Search Amazon` link in the ASIN column.
- ETA displays carrier estimated delivery when available, falls back to eBay estimated delivery for undelivered items without a carrier ETA, and displays delivered date for delivered items.
- Shipment dates are formatted as date-only values to avoid UTC/local timezone day shifts.
- Status displays derived operational status, not raw carrier text.
- Table headers sort the filtered row set by the displayed column values.

## Detail Drawer Display

- `Status` uses the same derived operational status as the table.
- `Carrier Status` shows only carrier/shipment status fields, never item `current_status`.
- `ETA` appears next to `Order Date` and uses the same display-date logic as the table.
- When ASIN is missing, `Amazon Title` displays `--`; the eBay supplier title remains visible separately.
- ASIN and sell price are edited together with one drawer save action.

## Title Cleaning

- Amazon search links use `cleanMarketplaceTitleForSearch`.
- The Python integration mirror is `clean_marketplace_title_for_search`.
- Matching-key helpers live in `matchingKeys.ts`.
- Keep frontend search-link cleaning aligned with backend matching/search automation cleaning.
- Title-cleaning spreadsheet notes can define broad cleanup rules even when repeated rows are not manually corrected one by one.

## Manual Match Propagation

- Manual ASIN and sell-price saves go through `/api/purchases`.
- The API propagates corrections to other rows with the same normalized title and system.
- Existing different ASINs are not overwritten.
- Manual match memory is written to `manual_item_matches` when the database migration has been applied.

## Operational Rules

- The frontend must never recalculate landed cost.
- Display `unit_cost` from `vw_purchases_dashboard`; backend logic is authoritative.
- Purchases and receiving are separate workflows. Do not merge receiving verification into this UI.
- ASIN/manual review can live here, but matching confidence and ambiguity status must come from backend data.
- Video-game matching is platform-specific. Do not introduce frontend matching shortcuts across systems.
- Frontend displays `system`, but backend import/enrichment owns system detection and canonical display names.
