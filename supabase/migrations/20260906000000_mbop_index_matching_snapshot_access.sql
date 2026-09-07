-- MBOP: snapshot cleanup and evidence lookup access paths.
-- Target verified during investigation: froeucjkcepuhgwisped (production).
-- Not applied by the investigation. Reconcile the shared migration ledger
-- before deployment. Run while scheduler workloads are idle: ordinary index
-- creation briefly blocks writes to these tables; abort instead of waiting.
set lock_timeout = '5s';
set statement_timeout = '120s';

-- ON DELETE SET NULL must locate examples referencing each deleted snapshot.
-- Without this index, the observed lookup scans the entire examples table.
create index if not exists matching_intelligence_examples_snapshot_idx
    on public.matching_intelligence_examples (listing_snapshot_id);

-- Supports selecting bounded cleanup batches without reading payload columns.
create index if not exists sourcing_listing_snapshots_source_idx
    on public.sourcing_listing_snapshots (snapshot_source, listing_snapshot_id);

-- Supports matching evidence reuse by action, newest snapshot first.
create index if not exists sourcing_listing_snapshots_action_idx
    on public.sourcing_listing_snapshots (action_id, captured_at desc);

analyze public.matching_intelligence_examples;
analyze public.sourcing_listing_snapshots;

reset statement_timeout;
reset lock_timeout;
