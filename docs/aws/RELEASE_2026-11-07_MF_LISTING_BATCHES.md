# MF listing batches production release — November 7, 2026

Implementation commits: `6653694e9684` and `acb2f94bf40d`.

## Applied database change

- Verified production project: `amazon-ebay-ops` / `froeucjkcepuhgwisped`, ACTIVE_HEALTHY, PostgreSQL 17.
- Reconciled the complete shared migration ledger. Dry run showed only `20261108035549_mbop_amazon_listing_batches.sql` pending. Applied it with the documented linked CLI workflow; confirmed the remote ledger version/name afterward.
- The CLI reported a local pg-delta catalog-cache certificate-file warning after applying SQL. The migration completed; remote ledger, all four new tables, RLS, service-role reads and revoked anonymous completion access were independently verified. No ledger repair or direct schema application was used.
- New objects are MBOP-owned; College Planner objects and prior migrations are unchanged.
- Security advisor's new-table notices are the expected RLS-without-client-policy notices for server-only tables. `anon`/`authenticated` have no table grants; functions use invoker security and service-role-only execution. No public policies were added. See [Supabase function permissions](https://supabase.com/docs/guides/database/functions#function-privileges).

## AWS deployment

- Web task: `mbop-web-task:204`; build `acb2f94bf40d`.
- Web digest: `sha256:741490ac1b52f7c11b121d6414b40e9a6c42c8e673fde2fdd092e3a248c21600`.
- Scheduler task: `mbop-scheduler-task:158`.
- Scheduler digest: `sha256:cdd594c4dbdd5d3075363c4f2f2dc1ee10c866200bd70e05361427e8cb296700`.
- Only the existing `mbop-reconciliation` schedule target was changed (141 → 158); its command and timing were preserved. No broad sync or reconciliation run was launched.
- Used the repository Dockerfiles and ECR → ECS task registration/service-update workflow, preserving current task roles, secrets and configuration. Temporary ECR auth configuration avoided the existing Windows Docker credential-helper failure; its token file was removed after each build/push.
- Existing deployed shipping reconciliation work was preserved in the source/build and left outside this phase's implementation commits.

## Validation

- Eight real PostgreSQL 17 transaction tests passed in a disposable local Docker container: partial/full completion, cost and receipt retention, concurrent idempotent retries, completed-batch rejection, cross-batch stock contention, multi-allocation rollback, missing/invalid MSKUs/quantities, immutable re-export, draft exclusions and FBA history.
- Selection/date tests passed: parent/child mixed selections, blocked children, partial quantities, restored zeroes, MF reference formatting, Pacific standard/daylight time.
- API fixture tests passed: selected source snapshots and purchase IDs, exact persisted CSV, MF reference, exclusion of FBA-only SKU mappings, draft zeroes, stale/invalid selection rejection, re-export without rereading preparation data.
- Existing InventoryLab export regression checks passed, including weighted costs and calendar-date preservation.
- Two existing FBA inventory tests and two MF/FBA projection tests passed.
- Focused ESLint, TypeScript, local production build and final Docker production build passed. The initial font-fetch failure was resolved by rerunning with access to the existing external font dependency.
- Authenticated browser verification at `https://mbop.midnightblueenterprises.com/fba` showed build `acb2f94`, List on Amazon navigation/heading, FBA/MF method controls, IL date/time/timezone and correctly formatted MF preview. The preceding release of the same controls also verified parent and allocation checkbox interaction: unchecking the allocation cleared its ASIN and set its quantity to zero; rechecking the ASIN restored the allocation and quantity.
- No production draft, export, listing completion or stock lot was created during verification. Tiny production reads confirmed zero new batches/completions/lots. The two previously excluded purchase items remain in the preparation queue.

## Operational limits

Listing confirmation is manual. Amazon acceptance/availability, customer-order stock drawdown, returns and transfers remain outside this phase. Operators must capture the actual MSKU when a unique condition-matched MF mapping is unavailable. Saved drafts require explicit Save draft; exported snapshots are immutable and a new selection starts another batch. History displays the latest 100 new listing batches; historical FBA shipments remain in FBA Shipments.
