# MF Returns synchronization and text repair

November 8, 2026. Application commit `1c3a553e76a4`.

## Problem and change

The first production MF returns report imported successfully, but a subsequent
financial adjustment carried `FBA19W1MLF5L` as its ORDER_ID reference. The worker
sent this shipment ID to the customer Orders endpoint and stopped on HTTP 404.
There were no imported MF returns or physical inventory changes.

The MF worker now requires a customer 3-7-7 order ID before Orders lookup or
financial admission. Shipment/account references stay outside this customer
return ledger and are counted in run statistics. Genuine customer-order errors
are still visible. A financial shipment reference cannot suppress later valid MF
refunds. The scope remains the configured seller, marketplace and merchant
channel; no FBA workflow or Amazon write endpoint changed.

Corrupted static punctuation in the Returns workspace and inspection/claim forms
was replaced with ASCII separators. UTF-8 source reads/writes are explicit. A
static regression prevents the corrupt text from returning.

## Validation

- Ten focused source/synchronization tests passed, including the exact failing
  shipment ID, no database/API calls for non-customer IDs, a following valid MF
  refund, and visible failure for a real customer-order read error.
- Focused TypeScript/ESLint and production Docker compilation passed.
- No SQL migration was required; the existing returns migration is unchanged.
- All returns tables retain RLS; anon cannot execute restocking. The live
  verification created no stock, receipts, inspections or claims.

## Production refresh

Scheduler task definition `mbop-scheduler-task:162`, built from `1c3a553e76a4`:

`297464765814.dkr.ecr.us-west-2.amazonaws.com/mbop-scheduler@sha256:2995f63d2b08e0bc4a341998dc1d06e682b9b50a53680da5b9c2c22be2287748`

Returns-only ECS task `922b0546741043249e64b26e6a3bc42e` ran the existing
`mf-returns` group. Run `1a5ca70c-e9f8-416c-8dd4-be172e289234` completed
successfully at **2026-11-08 5:33:49 PM Pacific** (2026-11-09 01:33:49 UTC),
after starting at 5:32:57 PM Pacific. Report `1170096020766` imported successfully.
Statistics: zero MF return items, zero admitted MF financial transactions, zero
packages to check, **22 excluded non-customer financial references**, no error.
This confirms the requested recent report/finance window, not all historical
Amazon returns. There was no missing Amazon permission in this run.

The existing Supabase capacity gate passed with PostgreSQL up, 1.54 GB available
memory, 17.88 GB filesystem headroom and 537 MB swap free. It does not measure
remaining Disk IO Budget. No full orchestration or historical backfill ran.

Only the existing `mbop-amazon-sales-recent-day` and
`mbop-amazon-sales-recent-catchup` targets changed from scheduler159 to162.
Their expressions, Pacific timezone, enabled state, roles and networking were
preserved. No new schedule or infrastructure was created.

## Web rollout

Web task definition `mbop-web-task:210`, build `1c3a553e76a4`:

`297464765814.dkr.ecr.us-west-2.amazonaws.com/mbop-web@sha256:8da87d3ae8402c78eddc1bc40242cf96637e98cc4c362e2cd4488416af34a3c6`

The normal repository Dockerfile/ECR/ECS workflow was used with the established
temporary Docker-auth workaround for the broken Windows credential helper.
Unrelated shipping reconciliation working-tree changes were preserved outside
these commits.

`scripts/aws-web-status.ps1` confirmed PRIMARY **COMPLETED**, desired/running 1,
pending 0, task210 only, at 5:36 PM Pacific. The previous task209 drained.
The returns-only ECS container exited zero and logged a successful sync group.

Authenticated Chrome verification at `/mf-returns?build=1c3a553` confirmed build
`1c3a553e76a4`, readable header/pagination punctuation, last successful sync
**11/8/2026, 5:33:49 PM**, no failure/stale warning and zero records in Open
Returns. Screenshot inspection confirmed the table and shared header fit.
