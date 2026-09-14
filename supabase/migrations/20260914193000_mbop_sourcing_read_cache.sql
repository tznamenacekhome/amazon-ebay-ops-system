-- MBOP read-model performance: transactional invalidation and a compact list projection.
-- No operational rows, matching decisions, schedules, or business rules are changed.
set lock_timeout = '2s';
set statement_timeout = '30s';

-- Dirty markers are isolated by database backend, so unrelated operational
-- writers never contend on one shared revision row or acquire cross-table locks.
create table public.sourcing_cache_dirty (
  backend_pid integer primary key,
  changed_at timestamptz not null
);
create table public.sourcing_cache_state (
  singleton boolean primary key default true check(singleton),
  revision bigint not null default 0
);
insert into public.sourcing_cache_state(singleton) values(true);
alter table public.sourcing_cache_dirty enable row level security;
alter table public.sourcing_cache_state enable row level security;
revoke all on public.sourcing_cache_dirty,public.sourcing_cache_state from public,anon,authenticated;

create function public.sourcing_bump_cache_version() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  -- DO UPDATE is intentional: hold this backend's marker until commit. DO NOTHING
  -- could let a reader consume an earlier marker before this write commits.
  insert into public.sourcing_cache_dirty(backend_pid,changed_at)
  values(pg_backend_pid(),clock_timestamp())
  on conflict(backend_pid) do update set changed_at=excluded.changed_at;
  return null;
end;
$$;
revoke all on function public.sourcing_bump_cache_version() from public,anon,authenticated;

create function public.sourcing_cache_version() returns jsonb
language plpgsql security definer set search_path = '' as $$
declare current_revision bigint; consumed bigint; active_run boolean;
begin
  -- Serialize only cache readers. Never wait on an in-flight operational writer.
  select revision into current_revision from public.sourcing_cache_state
    where singleton for update;
  with ready as (
    select backend_pid from public.sourcing_cache_dirty for update skip locked
  ), consumed_rows as (
    delete from public.sourcing_cache_dirty d using ready r
    where d.backend_pid=r.backend_pid returning d.backend_pid
  ) select count(*) into consumed from consumed_rows;
  if consumed > 0 then
    update public.sourcing_cache_state set revision=revision+1 where singleton
      returning revision into current_revision;
  end if;
  select exists(select 1 from public.sourcing_runs
    where status in ('running','planned') and completed_at is null) into active_run;
  return jsonb_build_object('revision',current_revision,'running',active_run);
end;
$$;
revoke all on function public.sourcing_cache_version() from public,anon,authenticated;
grant execute on function public.sourcing_cache_version() to service_role;

create trigger sourcing_cache_changed after insert or update or delete or truncate on public.amazon_fba_inventory_snapshots
for each statement execute function public.sourcing_bump_cache_version();
create trigger sourcing_cache_changed after insert or update or delete or truncate on public.amazon_listing_snapshots
for each statement execute function public.sourcing_bump_cache_version();
create trigger sourcing_cache_changed after insert or update or delete or truncate on public.amazon_sales_order_items
for each statement execute function public.sourcing_bump_cache_version();
create trigger sourcing_cache_changed after insert or update or delete or truncate on public.amazon_sales_orders
for each statement execute function public.sourcing_bump_cache_version();
create trigger sourcing_cache_changed after insert or update or delete or truncate on public.amazon_sales_profitability
for each statement execute function public.sourcing_bump_cache_version();
create trigger sourcing_cache_changed after insert or update or delete or truncate on public.amazon_skus
for each statement execute function public.sourcing_bump_cache_version();
create trigger sourcing_cache_changed after insert or update or delete or truncate on public.fba_shipment_items
for each statement execute function public.sourcing_bump_cache_version();
create trigger sourcing_cache_changed after insert or update or delete or truncate on public.fba_shipments
for each statement execute function public.sourcing_bump_cache_version();
create trigger sourcing_cache_changed after insert or update or delete or truncate on public.keepa_product_snapshots
for each statement execute function public.sourcing_bump_cache_version();
create trigger sourcing_cache_changed after insert or update or delete or truncate on public.matching_intelligence_examples
for each statement execute function public.sourcing_bump_cache_version();
create trigger sourcing_cache_changed after insert or update or delete or truncate on public.purchase_items
for each statement execute function public.sourcing_bump_cache_version();
create trigger sourcing_cache_changed after insert or update or delete or truncate on public.sourcing_actions
for each statement execute function public.sourcing_bump_cache_version();
create trigger sourcing_cache_changed after insert or update or delete or truncate on public.sourcing_blocked_asins
for each statement execute function public.sourcing_bump_cache_version();
create trigger sourcing_cache_changed after insert or update or delete or truncate on public.sourcing_coverage_cycle_items
for each statement execute function public.sourcing_bump_cache_version();
create trigger sourcing_cache_changed after insert or update or delete or truncate on public.sourcing_coverage_cycles
for each statement execute function public.sourcing_bump_cache_version();
create trigger sourcing_cache_changed after insert or update or delete or truncate on public.sourcing_declined_ebay_offers
for each statement execute function public.sourcing_bump_cache_version();
create trigger sourcing_cache_changed after insert or update or delete or truncate on public.sourcing_ebay_candidates
for each statement execute function public.sourcing_bump_cache_version();
create trigger sourcing_cache_changed after insert or update or delete or truncate on public.sourcing_listing_snapshots
for each statement execute function public.sourcing_bump_cache_version();
create trigger sourcing_cache_changed after insert or update or delete or truncate on public.sourcing_opportunities
for each statement execute function public.sourcing_bump_cache_version();
create trigger sourcing_cache_changed after insert or update or delete or truncate on public.sourcing_opportunity_batch_items
for each statement execute function public.sourcing_bump_cache_version();
create trigger sourcing_cache_changed after insert or update or delete or truncate on public.sourcing_opportunity_batches
for each statement execute function public.sourcing_bump_cache_version();
create trigger sourcing_cache_changed after insert or update or delete or truncate on public.sourcing_purchase_matches
for each statement execute function public.sourcing_bump_cache_version();
create trigger sourcing_cache_changed after insert or update or delete or truncate on public.sourcing_runs
for each statement execute function public.sourcing_bump_cache_version();
create trigger sourcing_cache_changed after insert or update or delete or truncate on public.sourcing_sales_velocity_suppressions
for each statement execute function public.sourcing_bump_cache_version();
create trigger sourcing_cache_changed after insert or update or delete or truncate on public.sourcing_seed_asins
for each statement execute function public.sourcing_bump_cache_version();
create trigger sourcing_cache_changed after insert or update or delete or truncate on public.sourcing_seller_intelligence
for each statement execute function public.sourcing_bump_cache_version();
create trigger sourcing_cache_changed after insert or update or delete or truncate on public.sourcing_settings
for each statement execute function public.sourcing_bump_cache_version();

create function public.sourcing_list_diagnostics_json(d jsonb) returns jsonb
language plpgsql immutable parallel safe set search_path = '' as $$
declare result jsonb; rules jsonb; identity jsonb; path text[];
begin
  if d is null or jsonb_typeof(d) <> 'object' then return d; end if;
  select coalesce(jsonb_object_agg(key,value),'{}'::jsonb) into result from jsonb_each(d)
    where key = any(array['recommendation','hard_blocks','flags','warnings','static_rules','title_overlap','platform_rule','category','businessEligibilityChecks','presentationDecision','decisionTrace','canonicalDecision','identity_comparison']);
  if jsonb_typeof(d->'static_rules') = 'object' then
    select coalesce(jsonb_object_agg(key,value),'{}'::jsonb) into rules from jsonb_each(d->'static_rules')
      where key = any(array['recommendation','hard_blocks','flags','warnings','title_overlap','platform_rule','category','identity_comparison']);
    result := jsonb_set(result,'{static_rules}',rules);
  end if;
  foreach path slice 1 in array array[['identity_comparison',null],['static_rules','identity_comparison']] loop
    path := array_remove(path,null);
    identity := result #> path;
    if jsonb_typeof(identity) = 'object' then
      -- Only business qualification consumes the identity verdict in list mode.
      result := jsonb_set(result,path,jsonb_build_object('evidenceDecision',
        jsonb_build_object('productIdentityVerdict',identity #> '{evidenceDecision,productIdentityVerdict}')));
    end if;
  end loop;
  return result;
end;
$$;
create function public.sourcing_list_diagnostics(public.sourcing_opportunities) returns jsonb
language sql stable parallel safe set search_path = '' as $$
  select public.sourcing_list_diagnostics_json($1.matching_diagnostics_json);
$$;
revoke all on function public.sourcing_list_diagnostics_json(jsonb) from public, anon, authenticated;
revoke all on function public.sourcing_list_diagnostics(public.sourcing_opportunities) from public, anon, authenticated;
grant execute on function public.sourcing_list_diagnostics_json(jsonb) to service_role;
grant execute on function public.sourcing_list_diagnostics(public.sourcing_opportunities) to service_role;
notify pgrst, 'reload schema';

reset lock_timeout;
reset statement_timeout;
