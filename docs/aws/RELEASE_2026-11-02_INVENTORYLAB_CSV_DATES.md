# InventoryLab CSV purchase dates

InventoryLab rejected exported rows with `String '--' was not recognized as a
valid DateTime`. The FBA export reused the UI date formatter, whose missing-date
placeholder is `--`. It also used a two-digit year and converted date-only
values through the browser timezone.

Per the operator's requirement, export is blocked unless every selected source
row has a valid ASIN, title, original unit cost, list price, quantity,
purchase date, and supplier. MSKU and FNSKU are optional: InventoryLab creates
new listings during shipment prep, before MBOP knows the MSKU. System is descriptive game
metadata and not applicable to shoes/pet supplies. Zero purchase cost is valid.
An error identifies each incomplete selected source row; the entire download
is blocked, rather than silently dropping units or writing incomplete rows.

Valid calendar dates use `MM/DD/YYYY` without timezone shifts. The formatter's
unknown-date result is never exported because the gate requires a valid date.
Display placeholders in the app are unchanged. Export validates every selected
source row, then merges by ASIN: quantities sum, cost is the quantity-weighted
average, purchase date is the earliest selected source date, and suppliers are
deduplicated and combined. MSKU remains optional and uses the preferred ASIN
MSKU when available.

The completeness change in `c0e079a` accidentally replaced the existing ASIN
merge with per-purchase CSV rows. This regression is corrected. Export aggregation
now runs in the FBA API against authoritative database unit costs. The browser
sends only selected source IDs and quantities, not cost/date/supplier values.
Database reads are restricted to those IDs (at most 500 selected source rows),
and missing/ineligible selected items block export rather than disappearing.
The export POST performs no writes and does not create or finalize a shipment.

The two remaining ready returns were matched by exact SKU to InventoryLab and
independently checked against consumed legacy sale COGS. Comfortiva SKU
`1059898575`: Sierra, 2023-08-14, $29. Harmony SKU `1058392679`: Petco,
2026-04-06, $5.99. Applied audit SQL:
`sql/2026-11-02_link_legacy_return_purchase_bases.sql`. Other non-eBay source
rows have differing dates/costs, so these are explicitly InventoryLab legacy
bases, not inferred matches to a particular non-eBay source-sheet row. The FBA
API now displays the verified original supplier rather than a recovery label.

Regression checks cover missing required fields even when ASIN aggregates look
complete, selected weighted costs, earliest selected dates, ASIN merging,
combined suppliers, valid zero cost, excluded incomplete rows,
optional MSKU/FNSKU, quantity validation, unknown/invalid dates, leap years, full years,
and UTC/Los Angeles/Honolulu. Node tests, TypeScript, and the production Docker
build pass. Final application commit: `d1ac3ae495b7`; web task `198`, image
`sha256:16a218caa8f1e8471ce75069059d73798ccd17044c3db01316f0ec10ceaa5dad`.
Both verified source updates were read back from production. The temporary
Docker credential config was removed after deployment. Direct browser export
verification remains unavailable because the browser-control Node runtime
cannot start; tests and production-data checks do not establish an actual
InventoryLab import success.

Production verification: ECS services-stable wait completed. Revision 198 is running with a healthy ALB target;
revision 197 has zero running tasks. The ASIN-merged, MSKU-optional build is
serving traffic. No claim of a completed IL import is made.
