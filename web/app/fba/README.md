# MBOP Amazon FBA Workflow

The Amazon FBA workspace prepares Received Amazon-bound purchase items for InventoryLab shipment creation.

## Scope

- Source rows are `purchase_items.current_status = received`.
- eBay marketplace items are excluded.
- Rows without ASIN are excluded because the shipment list is grouped by ASIN.
- The frontend reads through `/api/fba-shipments`; it does not talk directly to Supabase.
- Cost values use backend-provided `vw_purchases_dashboard.unit_cost`.
- Prep pricing compares the stored sell price with latest Amazon sales, Keepa buy box intelligence, and cached Amazon Product Fees estimates before shipment creation.
- Pricing refresh is explicit. The Prep Queue `Update Pricing` button runs the small `fba-pricing` sync group instead of refreshing prices on page load.
- The Prep Queue shows the oldest pricing cache timestamp across the visible received FBA prep rows.
- Top metrics show ASIN count, unit count, total cost, total sell value, total
  profit, and total ROI. The shipment-entry row still shows selected units/cost
  for the quantities currently included.

## Grouping Rules

- Display one row per ASIN.
- Title is the stored Amazon title only.
- Quantity is summed across received purchase items.
- Cost per unit is weighted by quantity.
- Purchase date is the oldest purchase date in the grouped row.
- Supplier is the distinct supplier list for the grouped row.
- Sell price uses the highest non-null target sell price in the group.
- Sell price is editable from the grouped table. Saving updates the grouped received `purchase_items.target_price` rows before shipment creation.
- Pricing columns show Buy Price, editable Sell Price, Last Sold Price/date, current Keepa Buy Box, Keepa 90-day Buy Box average, Amazon estimated fees, and net Profit/ROI against Buy Price.
- Profit/ROI deducts cached Amazon estimated fees. After a sell price edit, MBOP reuses the cached non-referral fee components and recalculates the referral fee from the cached referral percentage, so Profit/ROI updates immediately after save without another Amazon call.
- Sell Price is visually flagged when it is below Last Sold, current Buy Box,
  and Keepa 90-day Buy Box average.
- ASIN values link to the Amazon detail page.
- Clicking an ASIN marks the row with a session-persistent highlight so the
  operator can return from Amazon and quickly find the last-opened row.
- Default sort is system, then Amazon title.

## Export

The CSV export mirrors the current shipment quantities.

If a detail row quantity is reduced before export, the exported quantity and weighted cost reflect that exclusion.

The export column for the target selling price is labeled `List Price` for InventoryLab workflow clarity.

## Save Behavior

The operator enters the Amazon Shipment ID, for example `FBA19F8YW7CV`, and saves the included quantities.

Included quantities:
- get linked to `fba_shipments` / `fba_shipment_items`
- move from `received` to `listed`
- are projected as outbound-to-Amazon inventory value while the shipment link is current and non-historical

Excluded quantities:
- remain `received`
- are not linked to the FBA shipment

If only part of a purchase item row is included, the API splits the row:
- the original row keeps the included quantity and moves to `listed`
- a new split child row keeps the remaining quantity in `received`

## Historical Marker

Historical listed items that predate MBOP shipment tracking should be linked to:

`legacy_listed_no_shipment_id`

This is not a real Amazon shipment ID. It means the item was already listed before MBOP started tracking FBA shipment IDs.

Historical marker links are not counted as current outbound-to-Amazon inventory value.
