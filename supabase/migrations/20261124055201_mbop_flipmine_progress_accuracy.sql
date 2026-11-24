create function public.flipmine_progress_counts(p_tabs uuid[])
returns table(tab_id uuid,counts jsonb) language sql stable security invoker set search_path=public as $$
 select t.tab_id,jsonb_build_object('rows',count(r.row_number),
 'evaluated',count(*) filter(where r.status='evaluated'),
 'duplicates',count(*) filter(where r.status='duplicate'),
 'excluded',count(*) filter(where r.status='excluded'),
 'invalid',count(*) filter(where r.status='invalid'),
 'failed',count(*) filter(where r.status='failed'),
 'pending',count(*) filter(where r.status='pending'))
 from sourcing_flipmine_tabs t left join sourcing_flipmine_rows r using(tab_id)
 where t.tab_id=any(p_tabs) group by t.tab_id
$$;

create function public.flipmine_refresh_progress(p_run uuid,p_tab uuid)
returns void language plpgsql security invoker set search_path=public as $$
declare snapshot jsonb;
begin
 perform 1 from sourcing_flipmine_runs where run_id=p_run and status='running' for update;
 if not found then return;end if;
 select counts into snapshot from flipmine_progress_counts(array[p_tab]);
 update sourcing_flipmine_tabs set summary=summary||snapshot
 where tab_id=p_tab and run_id=p_run and status in('running','partial');
end $$;

revoke all on function public.flipmine_progress_counts(uuid[]) from public,anon,authenticated;
revoke all on function public.flipmine_refresh_progress(uuid,uuid) from public,anon,authenticated;
grant execute on function public.flipmine_progress_counts(uuid[]) to service_role;
grant execute on function public.flipmine_refresh_progress(uuid,uuid) to service_role;
