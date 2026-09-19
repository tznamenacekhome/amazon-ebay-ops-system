alter table public.amazon_return_recovery_cases
  add column if not exists target_price numeric(14, 2);

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'amazon_return_recovery_cases_target_price_check'
      and conrelid = 'public.amazon_return_recovery_cases'::regclass
  ) then
    alter table public.amazon_return_recovery_cases
      add constraint amazon_return_recovery_cases_target_price_check
      check (target_price is null or target_price >= 0);
  end if;
end
$$;

comment on column public.amazon_return_recovery_cases.target_price is
'Operator-selected FBA list price for an Amazon Return Recovery unit before shipment creation.';
