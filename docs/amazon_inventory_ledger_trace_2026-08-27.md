# Amazon Inventory Ledger Trace

Date: 2026-08-27

## Purpose

MBOP had Amazon FBA inventory snapshots showing ASIN `B004L4AZ3I` / SKU
`YM-A3JU-Q1OQ` moving from one total reserved unit to zero total units without
a matching MBOP sales, return, removal, reimbursement, or finance row.

To trace Amazon-native movement evidence, MBOP now allows read-only Reports API
requests for:

- `GET_LEDGER_DETAIL_VIEW_DATA`
- `GET_LEDGER_SUMMARY_VIEW_DATA`

The diagnostic entry point is:

```powershell
.\.venv\Scripts\python.exe integrations\amazon_trace_inventory_ledger.py `
  --asin B004L4AZ3I `
  --seller-sku YM-A3JU-Q1OQ `
  --fnsku X001XC53V1 `
  --start 2026-08-01T00:00:00Z `
  --end 2026-08-27T23:59:59Z
```

The script downloads and filters Amazon's detailed inventory ledger report. It
does not write to Supabase or operational workflow tables.

## Observed Ledger Rows

For FNSKU `X001XC53V1`, Amazon returned:

| Date | Event Type | FC | Quantity | Disposition | Reference |
| --- | --- | --- | ---: | --- | --- |
| 2026-08-07 | Receipts | ABQ2 | 1 | SELLABLE | FBA19KM982VB |
| 2026-08-10 | WhseTransfers | ABQ2 | -1 | SELLABLE | |
| 2026-08-11 | WhseTransfers | GYR2 | 1 | SELLABLE | |
| 2026-08-12 | WhseTransfers | GYR2 | -1 | SELLABLE | |

A broader ledger request for 2026-08-10 through 2026-08-27 without the FNSKU
report option returned 1,131 account rows and only three matching rows for this
ASIN/SKU: the 2026-08-10, 2026-08-11, and 2026-08-12 warehouse-transfer rows.
No later matching row reintroduced the unit under the same ASIN/SKU.

## Interpretation

Amazon received the unit into ABQ2, transferred it to GYR2, then transferred it
out of GYR2. MBOP still found no matching sale, removal, reimbursement, customer
return, or finance transaction. The most specific Amazon evidence currently
available is the 2026-08-12 `WhseTransfers` `-1` row from GYR2.

Operationally, treat the unit as Amazon-held/lost-in-transfer until Seller
Central gives a replacement destination row, reimbursement, or case outcome.
