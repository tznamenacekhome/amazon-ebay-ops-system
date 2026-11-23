-- MBOP: durable, non-PII MF return finance work. Apply before deploying the worker.
create table public.amazon_mf_return_finance_work (
 account_id uuid not null references public.amazon_mf_accounts,
 transaction_id text not null,
 transaction_data jsonb not null,
 observed_at timestamptz not null,
 status text not null default 'pending' check(status in ('pending','imported','excluded_fba')),
 error text,
 created_at timestamptz not null default now(),
 last_attempt_at timestamptz,
 resolved_at timestamptz,
 primary key(account_id,transaction_id),
 check ((transaction_data->>'transaction_id'=transaction_id) is true)
);
create index amazon_mf_return_finance_work_pending_idx
 on public.amazon_mf_return_finance_work(account_id,created_at,transaction_id) where status='pending';
alter table public.amazon_mf_return_finance_work enable row level security;
revoke all on public.amazon_mf_return_finance_work from public,anon,authenticated;
grant all on public.amazon_mf_return_finance_work to service_role;

create function public.mbop_mf_return_finance_enqueue(p_account uuid,p_transaction jsonb,p_observed timestamptz)
returns jsonb language plpgsql security invoker set search_path=public as $$
declare work public.amazon_mf_return_finance_work; market text;
begin
 select marketplace_id into strict market from amazon_mf_accounts where id=p_account for update;
 if nullif(p_transaction->>'transaction_id','') is null or p_observed is null
    or coalesce(p_transaction->>'amazon_order_id','') !~ '^[0-9]{3}-[0-9]{7}-[0-9]{7}$' then
  raise exception 'Finance work requires transaction/order/observation identity';
 end if;
 if nullif(p_transaction->>'marketplace_id','') is not null and p_transaction->>'marketplace_id'<>market then
  raise exception 'Finance work marketplace mismatch';
 end if;
 select * into work from amazon_mf_return_finance_work
 where account_id=p_account and transaction_id=p_transaction->>'transaction_id' for update;
 if found and work.transaction_data->>'amazon_order_id'<>p_transaction->>'amazon_order_id' then
  raise exception 'Finance work transaction changed order identity';
 end if;
 insert into amazon_mf_return_finance_work(account_id,transaction_id,transaction_data,observed_at)
 values(p_account,p_transaction->>'transaction_id',p_transaction,p_observed)
 on conflict(account_id,transaction_id) do update set
 transaction_data=excluded.transaction_data,observed_at=excluded.observed_at,status='pending',error=null,resolved_at=null
 where excluded.observed_at>amazon_mf_return_finance_work.observed_at;
 select * into strict work from amazon_mf_return_finance_work
 where account_id=p_account and transaction_id=p_transaction->>'transaction_id';
 return to_jsonb(work);
end $$;

-- Import and acknowledgement share one database transaction. A crash or rejected
-- import cannot erase pending work; replay uses existing transaction uniqueness.
create function public.mbop_mf_return_finance_complete_work(p_account uuid,p_transaction_id text,p_observed timestamptz,p_resolution text)
returns boolean language plpgsql security invoker set search_path=public as $$
declare work public.amazon_mf_return_finance_work;
begin
 perform 1 from amazon_mf_accounts where id=p_account for update;
 select * into strict work from amazon_mf_return_finance_work
 where account_id=p_account and transaction_id=p_transaction_id for update;
 if p_resolution not in ('imported','excluded_fba') then raise exception 'Invalid finance work resolution';end if;
 if work.status<>'pending' then return false;end if;
 if work.observed_at<>p_observed then raise exception 'Finance work changed; retry current observation';end if;
 if p_resolution='imported' then
  perform mbop_mf_return_finance(p_account,work.transaction_data,work.observed_at);
 end if;
 update amazon_mf_return_finance_work set status=p_resolution,error=null,last_attempt_at=now(),resolved_at=now()
 where account_id=p_account and transaction_id=p_transaction_id;
 return true;
end $$;

-- Defense in depth: pending finance work must never advance the completed checkpoint.
create or replace function public.mbop_mf_return_sync_finish(p_run uuid,p_error text,p_stats jsonb)
returns void language plpgsql security invoker set search_path=public as $$
declare aid uuid;
begin
 select account_id into aid from amazon_mf_return_sync_runs where id=p_run;
 if p_error is null and exists(select 1 from amazon_mf_return_finance_work where account_id=aid and status='pending') then
  p_error:='Unresolved MF return finance work remains';
 end if;
 update amazon_mf_return_sync_runs set finished_at=now(),status=case when p_error is null then 'completed' else 'failed' end,
 error=p_error,stats=p_stats where id=p_run and status='running';
end $$;

revoke all on function public.mbop_mf_return_finance_enqueue(uuid,jsonb,timestamptz) from public,anon,authenticated;
grant execute on function public.mbop_mf_return_finance_enqueue(uuid,jsonb,timestamptz) to service_role;
revoke all on function public.mbop_mf_return_finance_complete_work(uuid,text,timestamptz,text) from public,anon,authenticated;
grant execute on function public.mbop_mf_return_finance_complete_work(uuid,text,timestamptz,text) to service_role;
