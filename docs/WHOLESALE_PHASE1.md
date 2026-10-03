# Wholesale supplier history — Phase 1

Implemented October 3, 2026. **Locally validated; not deployed or applied to the
shared production database.** The discovery report remains historical design
context; this document describes the implementation and the newer pricing decision.

## Ownership and scope

MBOP owns this operational supplier evidence. Supabase is its persisted source
of truth; Python parses/imports it. This is quoted supplier stock and price,
not owned inventory, purchases, COGS or a financial calculation. It creates no
duplicate ownership and crosses no ZFI boundary. Existing eBay sourcing,
purchases, receiving, FBA workflows and scheduler groups are unchanged.

The entry point is `integrations/import_royal_price_list.py`. Parsing is offline
by default. `--apply` sends one bounded transaction through the server-only
`wholesale_apply_import` RPC. No upload screen, web route or scheduler is needed
for this phase. A Python repository provides bounded product/history reads;
future frontend consumers must use Next.js API routes, never browser Supabase.

## Schema

Migration: `supabase/migrations/20261003175949_mbop_wholesale_supplier_foundation.sql`.
All four new tables belong to MBOP in `public`:

| Table | Responsibility |
| --- | --- |
| `wholesale_suppliers` | UUID, stable supplier key, name, active flag, timestamps. Seeds `royal-electronics` / Royal Electronics, Inc. |
| `wholesale_imports` | Supplier, effective date/date source, filename, SHA-256 of original bytes, parser version, explicit revision/replacement, currency, completed/rejected status, counts, warnings, errors and source row evidence. |
| `wholesale_supplier_products` | Persistent UUID and supplier-scoped identity; first imported exact title/SYS/identifier plus separately normalized identifier and validation; independent active flag and timestamps. |
| `wholesale_supplier_observations` | One immutable accepted quote per product/import; exact title/SYS/identifier, validation, decimal price, currency, raw and normalized availability, source row numbers and timestamp. Effective date and revision come from the import FK. |

The imports and observations are append-only through service-role permissions.
Corrections do not update/delete them. RLS is enabled on all tables; no browser
role policies or grants are added. Tables, invoker views and the invoker RPC
are service-role only. The RPC locks the supplier row to serialize concurrent
imports. Foreign keys prevent cross-supplier product/import associations.

## Product identity

Royal has no separately demonstrated stable offer SKU. The v1 identity is SHA-256
of UTF-8 compact JSON `[normalized identifier, normalized SYS, normalized title]`,
with whitespace collapsed and case folded in each identity component. Uniqueness
is `(supplier_id, identity_key)`. ASIN does not participate. A barcode alone or
title alone cannot collapse different platform/edition/pack offers.

Raw text is never replaced by normalized text. Product columns retain first-seen
raw identity; every dated observation and import source row retain that list's
exact strings. Case/spacing and harmless barcode hyphen differences resolve to
the same product. A substantive title, platform or identifier change deliberately
creates a separate product. There is no fuzzy merge. Future identity reconciliation
must be explicit and audited; do not silently merge editions or systems.

Identical duplicate rows produce one observation with every source row number.
Different price or raw quantity for the same identity is a conflict: preserve
both rows as quarantined evidence and reject promotion of the entire list.
Different titles/platforms sharing a code remain separate products.

## Royal workbook contract

Read `COMPLETE LIST`, header row 1, A:G:
`ORDER, TITLE, SYS, UPC / SKU, PRICE, QTY, SUB`.
Only B:F are product evidence. ORDER/SUB, including their formulas, are ignored
for product identity and quotes. Whole-file hashing still identifies a distinct
source document if those worksheet cells change; same-date reapplication then
requires an explicit correction, without creating duplicate product identities.

Blank and recognized subtotal/total rows are counted and skipped. Explicit
date metadata rows are nonproducts. A standalone, case-insensitive `USED` word
in TITLE or SYS excludes the row, including surrounding spaces/tabs/punctuation.
`Unused` is not that marker. No other condition is inferred: **absence of USED
permits import but is not proof of factory-sealed/New condition**.

TITLE, SYS and identifier must be nonempty text. Numeric Excel identifiers are
not padded or reconstructed from formatting; the source representation is
preserved in rejected-row evidence and the operator must supply authoritative
text. Formulas in B:F, invalid prices or missing identity fields also reject
the list after reporting the bad rows. This prevents a partial/unreadable list
from making valid older products appear absent. The importer can persist a
dated `rejected` source with diagnostics, but creates no products/observations
and does not advance the current list. A corrected workbook is a new revision.
Unparseable files or unknown/conflicting dates fail before a dated import exists.

Prices are nonnegative decimal values with at most two fractional digits;
Royal quotes are explicitly USD. Future suppliers can use other ISO-shaped
three-letter currencies. No conversion, unit/pack assumption or profitability
calculation is performed. PRICE remains the supplier's quote; pack/MOQ semantics
must be established before purchasing decisions.

Bounds: 10 MiB file, 50 MiB expanded XLSX, 10,000 sheet rows, 50 sheet columns,
5,000 accepted products, 2,000 characters per imported product field, and a
10 MB database payload. Original B:F strings, cell types and identifier number
format are stored with row outcomes. The binary workbook stays with the operator;
the import retains its original filename/hash and sufficient row evidence for
audit, not a public file URL.

## Identifiers and availability

Preserve the exact raw identifier, including leading zeros and spaces. For
digit-shaped values only, trim whitespace and remove whitespace/hyphens into a
separate normalized field. Other supplier SKUs retain internal punctuation.
Never add/drop digits or alter check digits. Record length, apparent UPC-A/EAN-13
type, check-digit validity (nullable) and one of `valid`, `invalid_check_digit`,
`unexpected_length`, `non_barcode`. Questionable codes import with warnings;
11 digits are not converted into a confirmed UPC.

| Raw QTY | Minimum | Exact | Meaning |
| --- | --- | --- | --- |
| `74` | 74 | true | Exactly 74 reported |
| `144+` | 144 | false | At least 144 reported; no upper bound |
| `0` | 0 | true | Exactly zero reported |
| `CALL` or unrecognized/blank | null | null | Unknown; preserved with warning, never assumed zero |

## Business dates, revisions and current state

Prefer a `PRICE_LIST_DATE` named cell or explicit `Price list date:` / `Effective
date:` text in document properties, headers/footers or sheet cells. Recognize
YYYY-MM-DD and MM/DD/YYYY. Conflicting metadata or an explicit argument that
disagrees is an error. Excel's dynamic print date, creation/modification time,
filename and import time are not authoritative dates. If none is reliable,
`--effective-date` is required. The actual September workbook uses that parameter.

Idempotency key: `(supplier_id, effective_date, file_sha256)`. Repeated identical
imports return the original import ID/summary with `already_imported=true` and
zero **this-run** created/matched/observation counts. No write occurs. The stored
summary remains the original execution's counts. Concurrent identical requests
have the same behavior. A lost response can safely be retried. A changed parser
version for an already-imported identical file is refused pending explicit
reconciliation, rather than silently reparsing old history.

A different file for a date already completed requires
`--replaces-import-id <latest-completed-import-uuid-for-that-date>`. A stale or
wrong-supplier/date replacement is rejected. Revisions are monotonic per date.
Only a **completed** correction supersedes older completed observations for
that date. Rejected corrections do not hide earlier usable history.

`vw_wholesale_observation_history` exposes all accepted observations with dates,
revision, filename and `is_superseded`. Normal history excludes superseded
revisions, but audit history includes them. Latest is ordered by effective date
and then revision, never arrival time; out-of-order imports remain historical.

`vw_wholesale_supplier_products` exposes the product, latest effective observation,
`last_seen_date`, the supplier's latest completed list and `present_in_latest_list`.
Disappearance leaves the product, active flag and history intact; it does not mean
zero quantity or discontinuation. The last quote remains available with its old
date. If a correction withdraws the product's only observation, the latest effective
quote/date are null and the superseded evidence is still queryable. The active flag
is an independent administrative decision, not automatic absence classification.

## Running and reading

Offline preview (does not load credentials or contact Supabase):

```powershell
Set-Location C:\Dev\amazon-ebay-ops-system
.\.venv\Scripts\python.exe integrations/import_royal_price_list.py `
  'C:\Users\timz\Downloads\PRICE LISTS 9092026.xlsx' `
  --effective-date 2026-09-09 `
  --json-output tmp/wholesale-phase1/royal-preview.json
```

After the migration is approved/applied to the intended environment, configure
server-side `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` using existing secret
handling and add `--apply --expected-project-ref <verified-ref>`. `local` only
accepts localhost/127.0.0.1 URLs. Same-date corrections also add the replacement
UUID. Never put service-role keys into browser code or command arguments.

Exit 0: accepted preview/import or successful replay. Exit 2: parsed rejection
(with durable rejection evidence if `--apply`). Exit 1: input, target or storage
failure; database writes are atomic. Full errors/warnings/source rows are in the
optional JSON audit. Preview cannot know how many persistent products already
exist; created/matched counts are reported only after apply.

Server-side reads, using an existing authenticated service client:

```python
from integrations.wholesale_repository import WholesaleRepository

repo = WholesaleRepository(supabase)
page = repo.list_products(supplier_id, limit=100, present_only=True)
product = repo.get_product(supplier_product_id)  # includes latest_observation
history = repo.history(supplier_product_id, limit=100)
audit_history = repo.history(supplier_product_id, include_superseded=True)
```

Pagination is mandatory/bounded (maximum 500); all historical revisions are
explicitly available. No frontend aggregation or supplier-price analytics are
implemented. Future analytics must disclose sparse observation coverage and
their time/observation weighting rather than pretending there is daily history.

## Migration and validation status

The migration was applied only to networking-disabled disposable PostgreSQL 17
containers by `tests/test_wholesale_db.py`. Those containers were removed after
testing. No linked Supabase mutation, migration ledger change, AWS deployment,
production import or external marketplace call was performed for Phase 1.

Production application is intentionally pending. Before a future authorized
`supabase db push`, verify project `froeucjkcepuhgwisped` and run `supabase migration
list`, reconciling the **complete shared MBOP/College Planner ledger**. Review all
pending migrations, then use the documented push workflow. Do not directly paste
schema SQL into the linked database or modify applied migrations. Check capacity
before a large catalog import; even this initial list adds 1,050 products and
1,050 observations plus compact source evidence. This phase does not change quotas.

Tests:

```powershell
$env:MBOP_WHOLESALE_DB_TESTS = '1'
$env:MBOP_ROYAL_WORKBOOK = 'C:\Users\timz\Downloads\PRICE LISTS 9092026.xlsx'
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_wholesale*.py' -v
```

The opt-in database suite starts its own Docker PostgreSQL with `--network none`;
it cannot use production credentials. Without the opt-in, fast parser/repository
tests run and database tests skip. The real workbook is optional; small generated
fixtures cover the whole workflow independently of external files/APIs.

Actual workbook verification (September 9 date, run October 3):

| Measure | Observed |
| --- | ---: |
| Product source rows | 1,051 |
| USED skipped | 1 (row 645, P4 Star Wars: Squadrons USED) |
| Blank/footer rows skipped | 4 |
| Accepted products / initial local observations | 1,050 / 1,050 |
| Invalid product rows / conflicting duplicate rows | 0 / 0 |
| Existing matched on empty local DB | 0 |
| Reimport additional products / observations | 0 / 0 |
| Identifier warnings | 17: seven 11-digit codes, ten failed check digits |
| Leading-zero identifiers retained | 173 |
| Exact quantities / at-least quantities | 554 / 496 |
| Availability warnings | 0 |

Pre-filter system counts match prior analysis: SW 439, PS5 331, P4 163, SW2 66,
XBOX 18, XB1 14, ACCPS5 10, ACCSW2 4, PS3 3, ACCSW 3. P4 becomes 162 after USED
filtering. All questionable identifiers remain imported and uncorrected.
The complete source/warning audit and local verification outputs are in
`tmp/wholesale-phase1/royal-preview.json` and `database-verification.json`.

Database tests also verify concurrent duplicate exactly-once application,
rollback after a late error, raw identity variants, three dated prices
18.00 -> 17.00 -> 14.00, out-of-order dates, disappearance, corrections including
withdrawn rows, quarantines, supplier isolation, USD/other-supplier currencies,
RLS/grants and append-only evidence. These are local results, not production proof.

Final checks: **23 wholesale tests passed**, including the real-workbook test;
**54 existing sourcing match-rule tests passed**. Python `py_compile` passed for
the three implementation modules and three fixture/test modules. `git diff
--check` passed. No web build was needed because no web code changed.

## File inventory

Added:

- `integrations/wholesale_royal.py`: pure Royal parser and normalization.
- `integrations/wholesale_repository.py`: transactional import and bounded reads.
- `integrations/import_royal_price_list.py`: preview/apply CLI and audit output.
- `supabase/migrations/20261003175949_mbop_wholesale_supplier_foundation.sql`:
  four tables, seed supplier, transaction RPC, two read views and permissions.
- `tests/wholesale_fixtures.py`, `tests/test_wholesale_royal.py`,
  `tests/test_wholesale_db.py`: small workbook fixtures and parser/database tests.
- `docs/WHOLESALE_PHASE1.md`: this implementation/operations record.

Updated: `CURRENT_STATE.md`, `DECISIONS.md`, `docs/database_schema.md`,
`docs/backend_architecture.md`. The discovery report remains unchanged.
Pre-existing FBA shipment fix changes in the working tree are separate work
and were not altered by this phase.

## Phase 2 handoff and future decisions

No Amazon matching/search, Keepa, eligibility, profitability, opportunity UI,
ordering, receiving or external enrichment was added. Later modules can key
multiple ASIN candidates to `supplier_product_id` and cite the exact
`observation_id` / `import_id`. Questionable barcodes still permit future
title/platform discovery. Raw SYS is supplier evidence, not a guessed canonical
platform. Map/validate it explicitly later, including accessories and pack/region
differences. Substantive supplier identity edits need an audited reconciliation
design if Royal does not provide stable offer SKUs.

**Future pricing decision, superseding the discovery's single-primary-price
recommendation:** calculate wholesale True ROI independently using **current
Buy Box price** and **Keepa 90-day average selling price**. Apply the **25% True
ROI hurdle independently to both**. If **either** qualifies, the product may
be presented for human opportunity review, subject to valid ASIN matching and
New-condition selling eligibility. Show both calculations; neither silently
replaces the other. Risk signals remain informational and change neither
calculation. This rule is recorded only, not implemented in Phase 1.

Future phases still need commercial pack/MOQ confirmation, ASIN compatibility
and eligibility evidence, ROI denominator/storage assumptions, and a defensible
quantity policy for products without MBOP sales history. None blocks preserving
supplier price evidence now.
