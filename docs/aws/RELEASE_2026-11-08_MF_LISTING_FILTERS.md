# MF listing coverage, stock filters and product search

Application commit `b41901e5e4bd`, November 8, 2026 (Pacific).

The previous Listings search reported 1,217 results but Amazon caps pagination
at 1,000. Later SKUs were missing, including the wreath and U stocking. Live
AMAZON fulfillment also exposed old submitted DEFAULT attributes on converted
listings; submitted attributes are no longer sufficient to classify those as MF.

The updated downloader partitions by source creation dates, verifies partition
counts and deduplicates inclusive boundary overlaps. It discovered all 1,217
listings in 65 requests in the bounded read-only preview. Four live MF offers
match the operator's Seller Central screenshot:

| Product | ASIN | MSKU | Amazon quantity |
| --- | --- | --- | ---: |
| Leaf wreath | B07FY34QQ2 | 8H-J67B-WBRQ | 1 |
| Y stocking | B07ZL243WN | 1045855185 | 8 |
| U stocking | B00WZTNFV0 | KB-9FAU-FEZ3 | 16 |
| Tilly Tacker | B092FLB415 | 1056546450 | 12 |

The UI defaults to In stock, with Out of stock and All options. Retained
zero-quantity MF offers remain eligible for All/Out of stock. Inactive,
listing/catalog-suppressed, FBA-only and deleted/absent listings are hidden.
SEARCH_SUPPRESSED alone does not hide the BUYABLE wreath. Title, ASIN and MSKU
search runs in the API before pagination. Stock filters use Amazon's live offer
quantity; MBOP physical counts and original cost lineage remain independent.
No stock/opening balance was created from the screenshot or the Amazon snapshot.

Migration `20261109014929_mbop_mf_listing_visibility.sql` adds listing_state and
the service-role-only invoker view. The full shared local/remote migration
ledger was reconciled before the CLI push and verified afterward. Applied
migrations were not edited. The known local pg-delta catalog-certificate warning
did not prevent applying or recording this migration.

Validation passed: four source/discovery tests (including the 1,001-item
pagination regression), five existing Amazon MF projection tests, two isolated
PostgreSQL visibility tests, stock/search escaping checks, TypeScript, focused
ESLint and the production Docker build. Database cases preserve physical lots
and operator Keep MF=false while hiding inactive records. The live preview's
capacity guard passed; no full orchestration or historical backfill was run.

Deployment uses the existing web/scheduler Dockerfiles, ECR and ECS, with the
established temporary Docker authentication workaround. Unrelated shipping
reconciliation working-tree changes remain outside these commits.

## Production evidence

The MF-only ECS task `ac54a6f16e8448e9913272c7c2e9c5fc` on scheduler163 exited
zero. Its run completed at **2026-11-08 5:56:42 PM Pacific** (Nov 9 01:56:42 UTC):
1,217 listings read, 65 listing API calls, six current MF records (four in
stock, two inactive), zero changed customer orders/items and no error. The
new current-listings view returns exactly the four screenshot offers totaling
37 Amazon-listed units. Original MBOP physical counts remain unconfirmed; no
physical lot was created.

Real PostgREST searches returned two rows for `stocking`, one wreath for
`B07FY34QQ2`, one U stocking for `KB-9FAU-FEZ3`, and the quoted U title matched
literally. The new view is not readable by anon. Only the two existing
Amazon-sales-recent schedules moved from scheduler162 to163; cadence, Pacific
timezone, enabled state and other configuration were preserved.

Images built from `b41901e5e4bd`:

- Web task211: `297464765814.dkr.ecr.us-west-2.amazonaws.com/mbop-web@sha256:0d8d83f0f9d7394bc896e225bfe02c50caf44426e49cf505aa2f5870a36017de`
- Scheduler163: `297464765814.dkr.ecr.us-west-2.amazonaws.com/mbop-scheduler@sha256:2a09f2ebf32309d2985a0fd43635bed960578334719cb558c51d35d21b6144c6`
