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

## Published release

- Application commit `d063348259ae` was pushed. Migration `20261120162024` was applied through the linked workflow to project `froeucjkcepuhgwisped`; the complete shared ledger matched afterward. The known local pg-delta certificate/cache warning occurred after successful application and did not prevent ledger verification.
- All 23 audited DEFAULT catalog rows read back with method MF. The two currently mapped merchant lots had no known opposite-method SKU. The four saved MF export CSVs audited had blank MSKU columns, so no historical export contents were changed.
- The new resolver, using production data, returned FBA SKU `1072485155` and MF SKU `1072518299` for Minecraft Switch ASIN `B07RCCHQLD`. Call of Duty ASIN `B0033T1UWW` resolved to FBA SKU `1072485152` and no verified MF mapping.
- 42 Python/PostgreSQL checks passed across SKU identity, shipment inventory, profitability fees, shipping reconciliation, InventoryLab return history, MF projection, and the new database guards. TypeScript identity, InventoryLab export, listing API and batch selection checks passed. Local and Docker web builds passed.
- Scheduler task `mbop-scheduler-task:167` uses digest `sha256:6a0b3a3e9c37e15b07911c7356ed824722f3c606fc5e1f4b35a5ebd0e8d3d01a`. The shared scheduler deployment updated all 21 existing schedule targets. It preserved their commands and scheduling configuration. Cloud flags were verified.
- Web task `mbop-web-task:224` uses digest `sha256:bb402e476519552a73371d50a13145589ca140804a1e29f5c0bdf407ce5ca179`, build SHA `d063348259ae`. ECS confirmed rollout COMPLETED with one desired/running task and zero pending tasks.
- Authenticated production browser verification remains pending. Browser connection discovery reported the host unavailable, with the visible Chrome window on InventoryLab. Verification completed through migration readback, method-specific resolver reads and AWS deployment checks.
