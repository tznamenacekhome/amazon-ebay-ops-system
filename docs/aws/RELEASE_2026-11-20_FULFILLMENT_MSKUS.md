# Fulfillment-specific Amazon seller SKUs

Listing identity includes marketplace, fulfillment method, and seller SKU. FBA and MF listings of an ASIN require separate SKU resolution. Unknown or ambiguous mappings export a blank SKU so InventoryLab can create or identify the correct listing.

## Changes

- List on Amazon preparation and new exports resolve SKUs for the selected method and condition. DEFAULT normalizes to MF. Method-scoped seller catalog and configured merchant-offer records supply mappings. Separate SKUs/conditions retain separate export rows.
- New allocation snapshots include fulfillment_method and seller_sku. Saved batches reject fulfillment changes and cross-method re-export. Changing a draft's method starts a new batch identity with the current selection. Historical CSV downloads use their saved content.
- The report importer incorrectly classified DEFAULT as Amazon/FBA. The migration corrects current catalog rows whose saved report proves DEFAULT and clears their FNSKU. The bounded audit found 23 affected rows. FBA inventory sync preserves explicit listing observations when historical inventory still contains a converted SKU.
- The catalog exposes generated fulfillment_method. Merchant lots and FBA shipment items/source rows store their fixed method. Database guards reject known opposite-method SKUs and mismatched ASINs. Unverified merchant SKUs remain pending reconciliation. MF completion uses scoped validation instead of its old global SKU/ASIN lookup.
- FBA shipment fallback and historical InventoryLab backfill use FBA mappings only. Ambiguous ASIN fallback stays unresolved. MF profitability cannot consume FBA-only InventoryLab opening balances. Backfill cost lookup requires an exact SKU. Inventory projection and non-eBay FBA inventory COGS metadata lookup are method-scoped.
- AGENTS.md records the identity contract. Product title/catalog intelligence remains shared by ASIN.

The current provider seller-SKU registration keeps its existing marketplace/SKU uniqueness and IDs. Fulfillment-aware mapping uses its explicit method and separate FBA/MF workflow tables. Historical observations retain the method under which they were captured.

## Migration and verification

Migration `supabase/migrations/20261120162024_mbop_fulfillment_msku_identity.sql` belongs to MBOP public schema. The shared ledger was checked and all applied entries matched. This migration adds method fields, an index and validation functions and corrects proven DEFAULT rows. No purchase quantities or costs change.

Coverage includes TypeScript SKU resolution and CSV/API checks, Python importer/inventory/profitability tests, and real PostgreSQL guard tests in a disposable container. The web build passed. Production verification compares mappings for the same ASIN under both methods without creating listings or inventory.
