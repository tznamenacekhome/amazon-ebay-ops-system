-- Manual Informed Repricer rule-name mapping.
--
-- Informed listing reports currently expose strategy/rule IDs such as 24206,
-- but not the operator-friendly rule names shown in the Informed UI. This
-- table stores a small read-only advisory mapping for MBOP display purposes.
-- It must not write back to Informed, Amazon, purchases, purchase_items, or
-- workflow tables.

create table if not exists public.informed_rule_name_overrides (
  informed_rule_name_override_id uuid primary key default gen_random_uuid(),
  informed_rule_id text not null unique,
  friendly_name text not null,
  active boolean not null default true,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table public.informed_rule_name_overrides is
'Manual display-name mapping for Informed Repricer strategy/rule IDs when report exports only provide numeric IDs.';

create index if not exists informed_rule_name_overrides_active_idx
  on public.informed_rule_name_overrides (active, informed_rule_id);

insert into public.informed_rule_name_overrides (informed_rule_id, friendly_name)
values
  ('24206', '40% Video Games'),
  ('31970', 'Break Even'),
  ('33389', '30% Strategy Buy Box'),
  ('32840', 'Dollar '),
  ('33653', 'WinAtAllCost'),
  ('33719', '200% High Margin'),
  ('33811', '$2 NoBuyBox'),
  ('34059', 'MF'),
  ('34504', '50% Buy Box'),
  ('36575', '100%'),
  ('39410', '75%'),
  ('44502', '10% Buy Box')
on conflict (informed_rule_id) do update
set
  friendly_name = excluded.friendly_name,
  active = true,
  updated_at = now();

grant all on table public.informed_rule_name_overrides to service_role;
