# MBOP Amazon FBA Workflow

The Amazon FBA workspace prepares Received Amazon-bound purchase items for InventoryLab shipment creation.

## Scope

- Source rows are `purchase_items.current_status = received`.
- eBay marketplace items are excluded.
- Rows without ASIN are excluded because the shipment list is grouped by ASIN.
- The frontend reads through `/api/fba-shipments`; it does not talk directly to Supabase.
- Cost values use backend-provided `vw_purchases_dashboard.unit_cost`.

## Grouping Rules

- Display one row per ASIN.
- Title is the stored Amazon title only.
- Quantity is summed across received purchase items.
- Cost per unit is weighted by quantity.
- Purchase date is the oldest purchase date in the grouped row.
- Supplier is the distinct supplier list for the grouped row.
- Sell price uses the highest non-null target sell price in the group.
- Default sort is system, then Amazon title.

## Export

The CSV export mirrors the current shipment quantities.

If a detail row quantity is reduced before export, the exported quantity and weighted cost reflect that exclusion.

The export column for the target selling price is labeled `List Price` for InventoryLab workflow clarity.

## Save Behavior

The operator enters an InventoryLab/Amazon shipment ID and saves the included quantities.

Included quantities:
- get linked to `fba_shipments` / `fba_shipment_items`
- move from `received` to `listed`

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
