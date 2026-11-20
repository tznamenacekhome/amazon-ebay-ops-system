# MF listing recovery

The operator requested recovery of missing units in the last three MF batches, using [MF Batch Inventory Reconciliation](https://docs.google.com/spreadsheets/d/1GDAP85aYYaeopF3yhaXGaH0vU9peNChAagTp1tXGFlI/edit?gid=364361611).

The Missing from Export tab has 38 source rows, 37 ASINs and 53 units. Exact batch-reference/ASIN matching found 40 complete MBOP allocations and 40 pending merchant lots, totaling $1,166.19. The November 9, November 15 and November 19 source batches contribute 15, 20 and 18 units respectively. Minecraft Starter ASIN B07HFMJ4R5 contributes 9 plus 2 units from separate batches, correctly merged to 11 in the export. None of the selected lots was registered in amazon_mf_lots. All associated purchase items were Listed.

## Recovery behavior

Migration `20261120170048_mbop_mf_batch_recovery.sql` adds explicit transfer lineage, recovery evidence, source recovery statuses and a service-role-only transaction. Recovery creates a saved exported MF batch and transfers the existing physical merchant lots to its allocations. Lot IDs, quantities, costs, source purchase pointers and original timestamps remain intact. Source allocations retain immutable snapshots and CSVs, record transferred quantities, and exclude those quantities from active batch totals and cost. Purchase rows are unchanged.

The recovery takes full existing allocations only. It rejects already transferred, reconciled, registered, quantity-changed or opposite-method sources. Stable batch/allocation locks serialize overlapping requests, and an exact retry returns the existing batch. Mark listed confirms recovery allocations using the same lots, including any subsequently reconciled MF SKU, without inserting inventory or splitting purchases. Whole source allocations can be included or excluded during confirmation. Normal partial listing behavior remains supported.

The source sheet records New condition. Recovery snapshots and merchant lots use this evidence to correct the previous unknown condition; source historical snapshots remain unchanged. The current fulfillment-aware resolver found no verified MF SKU for the 37 output rows. An older MF offer for Gold's Gym is superseded by current FBA catalog evidence and excluded. All export MSKU cells remain blank for InventoryLab to assign appropriate MF listings. No Amazon write or InventoryLab submission is performed by this recovery.

The UI identifies moved quantities and recovery evidence, excludes moved units from original batch counts/costs, prevents completion of source recovery batches, and filters old completion displays to lots still owned by that batch. Explicit PostgREST relationship hints disambiguate source ownership from recovery-target links.

## Execution and verification

Target is the linked MBOP shared Supabase project `froeucjkcepuhgwisped`. The complete shared migration ledger must match except for this new MBOP migration before `supabase.cmd db push --linked`. Commit this exact SQL first. Use the documented AWS web deployment after migration, then verify stable ECS service state and production batch data.

`node scripts/recover-mf-listing-batch.cjs plan tmp/mf-recovery-source.json tmp/mf-recovery-final` produces a bounded source-checked manifest and CSV using the native server export and method-specific SKU resolver. `apply <manifest.json>` invokes the atomic transaction and checks physical lot IDs, quantities and costs against the saved preflight. Local artifacts in ignored tmp contain the read-only sheet evidence, manifest, CSV and result. Production recovery_evidence retains source URL/hash, original batches, allocation manifest, CSV hash and preflight lot identity/units/cost.

Prepared recovery ID: `aeec25a8-d679-46b5-94ab-30eb1f884f55`, reference `MF 2026-11-20 09:05 AM`, 40 allocations, 37 CSV rows, 53 units. The CSV uses standard weighted two-decimal unit costs; its extended sum is $1,166.15 due to four cents of rounding. MBOP retains the exact original lot cost of $1,166.19.

Nine isolated PostgreSQL checks passed, covering stock/cost/purchase conservation, retries, overlapping concurrent recoveries, atomic rollback, changed/registered sources, FBA SKU rejection, completion retries, retention of a reconciled MF SKU, and normal partial completion. Listing API checks cover cost exclusion for transferred quantities. Batch-selection checks and the local Next.js production build passed. Deployment and production readback results are recorded below after execution.
