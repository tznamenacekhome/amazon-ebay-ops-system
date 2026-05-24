# MBOP Receiving Workflow Requirements

Goal: highly efficient receiving processing of delivered items.

## Workflow

1. User scans the shipping tracking barcode or types a portion of the tracking number.
2. If there is exactly one matching receiving candidate, automatically open the receiving detail window.
3. If there are multiple matches, keep the queue filtered and require the user to select the correct row.
4. If there are no matches, keep focus in the search field and show an empty queue state.
5. User verifies the received item details.
6. User records one of these outcomes for each item:
   - full quantity received and correct
   - less than full quantity received
   - item needs to be returned
7. Detail window closes after save.
8. Item status updates to `Received` or `Return Pending` depending on outcome.
9. Search box on the queue screen receives focus again.
10. User scans the next item.

## Status Ownership

Receiving-owned statuses:
- `Received`: item was physically received and verified as expected.
- `Return Pending`: item was physically received but should be returned.

Impact:
- Purchases may display and filter these statuses for operational visibility.
- Receiving workflow owns the action that sets these statuses.
- Carrier sync and eBay purchase sync must not downgrade `Received` or `Return Pending` back to shipment-derived statuses such as `Delivered`.
- `Return Pending` is separate from `Return Opened`. `Return Pending` means the operator identified a return need during receiving. `Return Opened` means an eBay return/case exists.

## Data Requirements

- Add nullable `purchase_items.marketplace`.
- Allowed marketplace values are `Amazon` and `eBay`.
- Marketplace should not be set until the item is received.
- ASIN and sell price may be missing while an item waits in the receiving queue.
- ASIN and sell price are required before an item can be marked `Received` for marketplace `Amazon`.
- ASIN and sell price are not required when marketplace is `eBay`.
- If a partial quantity is received and the item is split, copied fields should include title, ASIN, Amazon title, system, target sell price, unit cost, condition, supplier listing URL, and raw import context.
- The received portion should save the selected marketplace.
- The received portion should save `received_date` using the local receiving date.
- The missing/unreceived split row should not have marketplace set.
- The missing/unreceived split row should not have `received_date` set.

## eBay Image Options

Current stored eBay buyer purchase payloads do not appear to include listing image or gallery fields.

Options:
- Add an eBay item-detail lookup during purchase sync or a later backfill and store the primary image URL on `purchase_items`.
- Add a receiving-only lookup by eBay item/listing ID when opening the receiving detail window.
- Defer images until the receiving workflow is otherwise stable.

Decision pending.

## Queue Table View

1. Separate mode from purchases, but visually similar.
2. Table columns should be the same as purchases where useful.
3. Queue should include items with these operational statuses:
   - `Delivered`
   - `Shipped (No Tracking)`
4. `Shipped (No Tracking)` is included because a package can physically arrive even when the carrier cannot be tracked.
5. Search box should focus on load so a scan can be entered without clicking.
6. Search should cover all displayed fields.
7. Primary search target is tracking number.
8. Columns should be sortable for manual queue review.

## Receiving Detail View

1. Large and easy to see from a distance.
2. Show tracking number.
3. Show carrier.
4. Show order number.
5. A tracking number usually identifies the package, but suppliers do not always identify which items belong to each tracking number.
6. Detail screen should show all items linked to the matched shipment when that linkage exists.
7. If shipment/item linkage is missing or uncertain, fall back to all items in the order.

Item fields:
- main image from eBay listing, once image source is implemented
- eBay title linked to the eBay item listing when available
- Amazon title linked to the Amazon ASIN page when ASIN is available
- quantity expected

Input options for each item:
- Quantity received, pre-filled with quantity ordered.
- Return checkbox.
- Marketplace pick list, default `Amazon`.
- ASIN field, editable at item level.
- Sell price field, editable at item level.
- Received button saves all rows and closes the detail window.

Save behavior:
- If full quantity is received and return is not checked, mark item `Received`, save marketplace, and save received date.
- If marketplace is `Amazon`, require ASIN and sell price before enabling save.
- If marketplace is `eBay`, allow save without Amazon title, ASIN, or sell price.
- If less than full quantity is received, split the purchase item:
  - current row represents the received quantity and is marked `Received`
  - new row represents the missing quantity and has no tracking / no marketplace
- If return is checked, mark that item `Return Pending`.
