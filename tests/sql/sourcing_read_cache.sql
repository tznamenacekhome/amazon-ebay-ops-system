do $$
declare first_revision bigint; current_revision bigint; projected jsonb;
begin
  if (select count(*) from pg_trigger where tgname='sourcing_cache_changed') <> 27 then raise exception 'source coverage'; end if;
  first_revision := (public.sourcing_cache_version()->>'revision')::bigint;
  insert into public.sourcing_opportunities select x, '{}'::jsonb,null,null from generate_series(100,1099) x;
  if (select count(*) from public.sourcing_cache_dirty) <> 1 then raise exception 'bulk must coalesce'; end if;
  current_revision := (public.sourcing_cache_version()->>'revision')::bigint;
  if current_revision <> first_revision+1 then raise exception 'invalidation'; end if;
  if (public.sourcing_cache_version()->>'revision')::bigint <> current_revision then raise exception 'stable cache'; end if;
  begin
    update public.sourcing_opportunities set matching_diagnostics_json='{"x":1}';
    raise exception 'rollback probe';
  exception when raise_exception then null;
  end;
  if (public.sourcing_cache_version()->>'revision')::bigint <> current_revision then raise exception 'rollback invalidated'; end if;
  update public.sourcing_opportunities set matching_diagnostics_json='{"x":2}';
  delete from public.sourcing_opportunities where id=100;
  truncate public.sourcing_opportunities;
  if (public.sourcing_cache_version()->>'revision')::bigint <> current_revision+1 then raise exception 'coalesced invalidation'; end if;
  insert into public.sourcing_runs(id,status,completed_at) values(1,'running',now());
  if (public.sourcing_cache_version()->>'running')::boolean then raise exception 'historically completed running status'; end if;
  update public.sourcing_runs set completed_at=null where id=1;
  if not (public.sourcing_cache_version()->>'running')::boolean then raise exception 'active run'; end if;
  update public.sourcing_runs set completed_at=now() where id=1;
  if public.sourcing_list_diagnostics_json(null) is not null then raise exception 'null'; end if;
  if public.sourcing_list_diagnostics_json('[]') <> '[]'::jsonb then raise exception 'array'; end if;
  if public.sourcing_list_diagnostics_json('{}') <> '{}'::jsonb then raise exception 'empty'; end if;
  projected := public.sourcing_list_diagnostics_json('{"flags":[],"static_rules":{"flags":["Blocked: test"],"identity_comparison":{"evidenceDecision":{"productIdentityVerdict":"non_match"},"amazon":{"large":"discard"}}},"canonicalDecision":{"evaluationId":"exact"},"normalized_evidence":{"large":"discard"}}');
  if projected ? 'normalized_evidence' or projected #> '{static_rules,identity_comparison,amazon}' is not null then raise exception 'raw evidence leaked'; end if;
  if projected #>> '{static_rules,identity_comparison,evidenceDecision,productIdentityVerdict}' <> 'non_match' or projected #>> '{canonicalDecision,evaluationId}' <> 'exact' or projected->'flags' <> '[]'::jsonb then raise exception 'qualification changed'; end if;
  if has_table_privilege('anon','public.sourcing_cache_state','SELECT') or has_function_privilege('anon','public.sourcing_cache_version()','EXECUTE') then raise exception 'anon permissions'; end if;
  if not has_function_privilege('service_role','public.sourcing_cache_version()','EXECUTE') then raise exception 'service permission'; end if;
end;
$$;
select 'PASS: source coverage; bulk/update/delete/truncate/rollback; active/completed runs; null/array/object/projection/guard ID; grants';
