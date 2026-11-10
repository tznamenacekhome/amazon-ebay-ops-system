# MF listing completion without MSKU

2026-11-10: MSKU is no longer requested by the Mark listed form. Completion
records the selected quantities and original cost/purchase lineage in
`amazon_merchant_inventory_lots` with a nullable `seller_sku`. No placeholder
SKU is generated. Existing known SKU completions continue to work.

Pending lots remain merchant-held physical inventory, are included in purchase
stock balances, and appear separately in MF Inventory under "Merchant-held stock
awaiting Amazon MSKU reconciliation", independent of the live listing stock
filter. Batch completion history identifies pending reconciliation too.

The existing successful MF synchronization calls registration after advancing
its complete-offer checkpoint. Pending lots are matched only when a complete
Amazon observation, fetched after manual completion, has exactly one retained
MF offer for the same ASIN and normalized condition. Missing, unknown-condition
or ambiguous identities stay pending; order shortages remain visible. Pending
stock cannot be reserved or shipped against a guessed SKU. An opening-balance
attempt for the same ASIN is blocked while pending stock exists, preventing a
second physical count from adding those units again.

Reconciliation sets the actual SKU and `msku_reconciled_at`, then registers the
SKU-addressable ledger lot once through its unique `listing_lot_id`. It does
not create a second physical purchase/completion or alter original costs.
Repeated completion requests retain the existing request/batch locks and
idempotency checks. Return descendant lineage and inspection holds remain in
purchase balances and opening-balance overlap checks. MSKU reconciliation is
identity evidence; manual listing completion still does not establish Amazon
acceptance or availability.

Migration: `20261110175424_mbop_deferred_mf_msku.sql`. No new infrastructure,
Amazon permissions, marketplace writes, report uploads or scheduler cadence.
Validation: `python tests/test_mf_deferred_msku.py` runs five isolated PostgreSQL
acceptance cases for no-SKU partial completion/retries/costs, complete-snapshot
reconciliation and reservations, ambiguity/condition/stale evidence, opening
overlap, and unchanged known-SKU/FBA behavior. The web build and focused lint
also pass. No operator batch is completed by deployment or verification.
