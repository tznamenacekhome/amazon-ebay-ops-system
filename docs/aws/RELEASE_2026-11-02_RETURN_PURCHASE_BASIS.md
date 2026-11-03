# Return purchase basis in Send to Amazon

Return order `111-7134497-9675438`, Nintendo Labo Vehicle Kit, was ready to
send back to Amazon with no cost because its original sale has missing COGS.
The queue previously depended exclusively on sale profitability and used the
return date as its purchase-date field.

Exact SKU `1070891208` / ASIN `B07FYN3JDL` appears on line 354 of
`data/imports/inventorylab_fba_active_inventory_2026-0.csv`: eBay, December 21,
2025, $35 per unit. Original MBOP purchase item
`befea0e0-be4e-4b4b-8587-e9be138352e5`, order `25-13983-50117`, independently
matches cost, date, and ASIN. `sql/2026-11-02_link_labo_return_purchase_basis.sql`
attaches this verified evidence to the recovery case; it does not create a
purchase, change purchase quantities, or rewrite sale profitability.

The FBA API now uses verified exact-SKU/ASIN purchase-basis metadata for the
queue's purchase date/cost and for shipment routing and legacy source fallback
costs. Existing sale COGS remains the cost fallback when verified evidence is
absent. Unknown original purchase dates remain unknown instead of displaying
the customer return date. Shipment source JSON preserves the evidence.

Validation: focused Node tests cover exact SKU/ASIN, unverified evidence,
invalid/unknown costs, valid zero cost, invalid calendar dates, and date-only
format. TypeScript passes. Production metadata read confirms $35, 2025-12-21,
and ready-to-send state, with inspection retained.

Deployment: commit `2704683d6d82` pushed to main; web task `mbop-web-task:194`,
image `sha256:fc48a5b0ef4ae7a0f6b4e1b0663e287acb749072a4b2e76ea528d57458f30348`.
Production Docker build passed; ECS services-stable wait completed and the new
load-balancer target is healthy. Browser verification could not run because CUA
failed to start its Node runtime (system path not found); this is a limitation
on direct authenticated UI verification. Database metadata and API helper tests
were verified independently. Temporary Docker credential config was removed.
