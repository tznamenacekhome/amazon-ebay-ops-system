# MBOP Receiving Frontend

This folder contains the Midnight Blue Operations Platform receiving workflow UI.

## Boundaries

- Receiving is a separate operational mode from Purchases.
- `page.tsx` owns scan/search state, queue sorting, detail selection, and receiving draft state.
- `/api/receiving` owns Supabase reads/writes for the receiving workflow.
- Shared navigation is provided by `web/app/AppShell.tsx`.

## Queue Behavior

- Queue includes items with derived operational status `Delivered` or `Shipped (No Tracking)`.
- Search input autofocuses on load for barcode scanning.
- If a search has exactly one match, the detail view opens automatically.
- If a search has multiple matches, the filtered queue remains visible for manual selection.
- Queue columns are sortable by displayed values.

## Detail Behavior

- Detail view groups rows by tracking number when usable tracking exists.
- If usable tracking is unavailable, detail falls back to all items for the purchase.
- eBay title links to the eBay listing when `ebay_listing_url` can be derived.
- Amazon title links to the Amazon ASIN page when ASIN exists.
- Amazon title display may append the system label when the stored title omits the system.
- Quantity received, return flag, and marketplace are recorded per item.
- ASIN and sell price are editable per item.
- Amazon-bound received items require ASIN and sell price before save is enabled.
- eBay marketplace items do not require Amazon title, ASIN, or sell price.

## Save Behavior

- Full received quantity marks the item `Received`.
- Received rows save `marketplace` and `received_date`.
- Amazon received rows save ASIN and target sell price.
- Return checked marks the item `Return Pending` and leaves marketplace and received date unset.
- Partial received quantity splits the missing quantity into a no-tracking purchase item.

## API Notes

- `/api/receiving` hydrates dashboard rows with purchase item metadata from `purchase_items`.
- Metadata lookups are chunked to avoid large PostgREST `in (...)` request failures.
- Receiving metadata includes stored `amazon_title`, `supplier_sku`, `supplier_listing_url`, derived `ebay_listing_url`, `marketplace`, and `received_date`.
