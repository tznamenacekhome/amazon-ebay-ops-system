# InventoryLab CSV purchase dates

InventoryLab rejected exported rows with `String '--' was not recognized as a
valid DateTime`. The FBA export reused the UI date formatter, whose missing-date
placeholder is `--`. It also used a two-digit year and converted date-only
values through the browser timezone.

Per the operator's requirement, export is blocked unless every selected source
row has a valid ASIN, MSKU, title, original unit cost, list price, quantity,
purchase date, and supplier. FNSKU is optional; System is descriptive game
metadata and not applicable to shoes/pet supplies. Zero purchase cost is valid.
An error identifies each incomplete selected source row; the entire download
is blocked, rather than silently dropping units or writing incomplete rows.

Valid calendar dates use `MM/DD/YYYY` without timezone shifts. The formatter's
unknown-date result is never exported because the gate requires a valid date.
Display placeholders in the app are unchanged. Export uses one line per selected
source row, preserving original cost/date/supplier for multiple purchases under
one ASIN. The previous client-side weighted cost calculation was removed;
authoritative backend unit costs are exported directly.

The two remaining ready returns were matched by exact SKU to InventoryLab and
independently checked against consumed legacy sale COGS. Comfortiva SKU
`1059898575`: Sierra, 2023-08-14, $29. Harmony SKU `1058392679`: Petco,
2026-04-06, $5.99. Applied audit SQL:
`sql/2026-11-02_link_legacy_return_purchase_bases.sql`. Other non-eBay source
rows have differing dates/costs, so these are explicitly InventoryLab legacy
bases, not inferred matches to a particular non-eBay source-sheet row. The FBA
API now displays the verified original supplier rather than a recovery label.

Regression checks cover missing required fields even when ASIN aggregates look
complete, separate costs/dates, valid zero cost, excluded incomplete rows,
optional FNSKU, quantity validation, unknown/invalid dates, leap years, full years,
and UTC/Los Angeles/Honolulu. Node tests and TypeScript pass. Deployment receipt
follows. The earlier date-format-only build was task 195; the complete-unit gate
supersedes that approach.
