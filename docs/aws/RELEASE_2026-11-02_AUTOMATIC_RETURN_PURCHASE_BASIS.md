# Automatic original purchase lookup for Amazon returns

The previous change read operator-verified `purchase_basis` metadata attached to
individual cases. It did not implement automatic source lookup for every return.
Minecraft order `112-9295910-5519431` exposed the gap: its sale had no COGS
allocation and the InventoryLab importer had skipped its zero-on-hand SKU.

The shared server resolver now resolves purchase cost/date/supplier for return
review (including uninspected returns), Send to Amazon, CSV export, shipment
routing, and legacy routed-source fallback. It preserves verified operator basis,
then checks the original sale's exact order/ASIN/SKU cost-consumption references
to MBOP purchases or non-eBay source records. Legacy/no-allocation cases can use
an exact-SKU-and-ASIN InventoryLab record, constrained by original sale date and
known sale cost. Conflicting source lots, future dates, broken allocation links,
and absent source details remain unresolved; the UI flags source review and CSV
export still blocks incomplete units. No ASIN-only or cross-platform guesses.

Lookups use deduplicated batches of at most 100 IDs and bounded result paging,
not full-table scans or one query per return. Automatic metadata is computed on
read from source-of-truth tables, without creating purchases, changing historical
sale profitability, or writing on GET. Normal inspection actions persist resolved
case evidence, and routing preserves it in the shipment's source snapshot.
Original purchase fields are shown separately
from original sale financial figures in the return detail drawer.

Historical import preview: 951 CSV metadata rows, all exact-SKU matches, no
ambiguities; the importer flagged 11 rows for missing/non-positive cost or missing
date. A successful tiny read and database
size check (13 GB, previously provisioned disk 32 GB) preceded the bounded import.
The existing metadata-only importer was run with `--include-inactive --apply`;
it does not modify purchase rows or operational inventory quantities. Future
imports include inactive metadata by default; `--active-only` is an explicit
opt-out. No full orchestration or inventory sync ran.

Live read-only verification with the actual resolver:
`web/scripts/verify-return-purchase-basis.mjs 112-9295910-5519431` returned
$24.84 / 2025-04-28 / eBay for SKU `1063375674`, sourced automatically from
InventoryLab. This agrees with MBOP eBay purchase `09-13014-50926`; no manual
case attachment was used. The verifier accepts one explicit order ID and checks
the target project before reading.

Tests cover automatic exact-SKU fallback, original purchase/non-eBay allocation
precedence, conflicting lots, chronology, mismatched SKU/known costs, broken
allocation, preserved operator overrides, and lookup failures. The original
purchase-basis, merged CSV export, and TypeScript checks pass. Importer defaults
have regression tests. Deployment receipt follows.

FBA display also preserves date-only values without converting through UTC into
the browser timezone, preventing purchase dates from appearing one day early.
The actual page formatter has timezone regression coverage.

Deployment: source resolver commit `608eb9109ba2`; final date-correct build
`e1ec530549b6`, ECS web task `200`, image
`sha256:44f96b4959632407a6cab5f5562d8687c3d4daa336c4e987828fee512bd3e92e`.
Both production Docker builds passed. The actual resolver was verified against
live production records, and the new web task is running with the prior revision
at zero running tasks. ECS services-stable wait completed. Temporary Docker
credential files were removed. Direct
authenticated browser verification remains unavailable because the browser
control runtime cannot start; no browser/InventoryLab import success is claimed.
