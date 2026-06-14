-- Order Problems + eBay returns/refund workflow foundation.
--
-- This starts the redesigned local MBOP workflow for order problems, returns,
-- missing items, cancellation refund follow-up, and eBay case tracking.
-- It intentionally does not write to eBay and does not downgrade existing
-- purchase_items.current_status values.

-- Reset old legacy return workflow rows. The old supplier_returns table was fed
-- by spreadsheet/API experiments and should not seed completed/refunded history
-- into the redesigned workflow. This deletes only that workflow table and does
-- not touch purchases or purchase_items.
do $$
begin
  if to_regclass('public.supplier_returns') is not null then
    delete from public.supplier_returns;
  end if;
end $$;

create table if not exists public.order_problem_cases (
  problem_case_id uuid primary key default gen_random_uuid(),

  purchase_item_id uuid not null references public.purchase_items(item_id) on delete cascade,
  purchase_id uuid references public.purchases(purchase_id) on delete set null,

  supplier text default 'eBay',
  supplier_order_id text,

  problem_source text not null,
  problem_type text not null,
  workflow_state text not null,
  priority text,

  is_open boolean not null default true,
  needs_response boolean not null default false,
  next_action text,
  next_action_due_at timestamptz,

  first_detected_at timestamptz not null default now(),
  last_detected_at timestamptz,

  return_needed_at timestamptz,
  ebay_return_opened_at timestamptz,
  seller_message_last_at timestamptz,
  operator_responded_at timestamptz,
  partial_refund_offered_at timestamptz,
  partial_refund_accepted_at timestamptz,
  label_available_at timestamptz,
  return_shipped_at timestamptz,
  seller_received_return_at timestamptz,
  refund_due_at timestamptz,
  refund_received_at timestamptz,
  replacement_promised_at timestamptz,
  replacement_shipped_at timestamptz,
  replacement_received_at timestamptz,
  escalation_available_at timestamptz,
  escalated_at timestamptz,
  closed_at timestamptz,

  ebay_return_id text,
  ebay_inquiry_id text,
  ebay_case_id text,
  ebay_return_state text,
  ebay_return_status text,
  ebay_current_type text,
  ebay_action_url text,

  expected_refund_amount numeric(12, 2),
  actual_refund_amount numeric(12, 2),
  partial_refund_amount numeric(12, 2),
  refund_currency text default 'USD',

  replacement_tracking_number text,
  notes text,
  raw_ebay_json jsonb,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  constraint order_problem_cases_problem_source_check
    check (problem_source in (
      'derived_order_problem',
      'receiving_return_pending',
      'manual',
      'ebay_return_sync',
      'ebay_inquiry_sync',
      'ebay_cancellation_sync'
    )),

  constraint order_problem_cases_problem_type_check
    check (problem_type in (
      'late_delivery_candidate',
      'stale_tracking_candidate',
      'carrier_exception_candidate',
      'return_needed',
      'not_as_listed',
      'buyer_choice',
      'missing_items',
      'cancelled_refund_followup'
    )),

  constraint order_problem_cases_workflow_state_check
    check (workflow_state in (
      'candidate',
      'return_needed',
      'return_opened',
      'seller_message_needs_response',
      'waiting_on_seller',
      'partial_refund_offered',
      'partial_refund_accepted',
      'label_pending',
      'label_received',
      'return_shipped',
      'seller_received_return',
      'refund_pending',
      'replacement_pending',
      'replacement_shipped',
      'replacement_received',
      'escalation_available',
      'escalated',
      'resolved_refunded',
      'resolved_received_item',
      'closed_no_action',
      'closed_no_refund'
    )),

  constraint order_problem_cases_priority_check
    check (priority is null or priority in ('urgent', 'high', 'normal', 'low')),

  constraint order_problem_cases_refund_amount_check
    check (expected_refund_amount is null or expected_refund_amount >= 0),

  constraint order_problem_cases_actual_refund_amount_check
    check (actual_refund_amount is null or actual_refund_amount >= 0),

  constraint order_problem_cases_partial_refund_amount_check
    check (partial_refund_amount is null or partial_refund_amount >= 0)
);

create unique index if not exists order_problem_cases_one_open_per_item_idx
  on public.order_problem_cases (purchase_item_id)
  where is_open = true;

create index if not exists order_problem_cases_purchase_item_idx
  on public.order_problem_cases (purchase_item_id);

create index if not exists order_problem_cases_workflow_state_idx
  on public.order_problem_cases (workflow_state);

create index if not exists order_problem_cases_open_due_idx
  on public.order_problem_cases (is_open, next_action_due_at);

create index if not exists order_problem_cases_needs_response_due_idx
  on public.order_problem_cases (needs_response, next_action_due_at);

create index if not exists order_problem_cases_ebay_return_idx
  on public.order_problem_cases (ebay_return_id)
  where ebay_return_id is not null;

create index if not exists order_problem_cases_ebay_inquiry_idx
  on public.order_problem_cases (ebay_inquiry_id)
  where ebay_inquiry_id is not null;

create index if not exists order_problem_cases_ebay_case_idx
  on public.order_problem_cases (ebay_case_id)
  where ebay_case_id is not null;

create table if not exists public.order_problem_events (
  problem_event_id uuid primary key default gen_random_uuid(),
  problem_case_id uuid not null references public.order_problem_cases(problem_case_id) on delete cascade,

  event_type text not null,
  event_source text not null,
  event_at timestamptz not null default now(),

  message text,
  amount numeric(12, 2),
  currency text,
  tracking_number text,
  raw_json jsonb,

  created_at timestamptz not null default now(),

  constraint order_problem_events_source_check
    check (event_source in ('system', 'operator', 'ebay_api', 'tracking')),

  constraint order_problem_events_amount_check
    check (amount is null or amount >= 0)
);

create index if not exists order_problem_events_case_event_at_idx
  on public.order_problem_events (problem_case_id, event_at desc);

grant all on table public.order_problem_cases to service_role;
grant all on table public.order_problem_events to service_role;

-- Seed the new workflow from existing workflow-locked statuses. This preserves
-- purchase_items state and only creates local problem cases where no open case
-- already exists.
with seeded_cases as (
  insert into public.order_problem_cases (
    purchase_item_id,
    purchase_id,
    supplier,
    supplier_order_id,
    problem_source,
    problem_type,
    workflow_state,
    priority,
    is_open,
    needs_response,
    next_action,
    first_detected_at,
    last_detected_at,
    return_needed_at,
    ebay_return_opened_at
  )
  select
    pi.item_id,
    pi.purchase_id,
    coalesce(p.supplier, 'eBay'),
    p.supplier_order_id,
    case
      when pi.current_status = 'return_pending' then 'receiving_return_pending'
      else 'manual'
    end,
    case
      when pi.current_status = 'cancelled' then 'cancelled_refund_followup'
      else 'return_needed'
    end,
    case
      when pi.current_status = 'return_pending' then 'return_needed'
      when pi.current_status = 'return_opened' then 'return_opened'
      when pi.current_status = 'cancelled' then 'refund_pending'
      else 'candidate'
    end,
    'normal',
    true,
    false,
    case
      when pi.current_status = 'cancelled' then 'Confirm refund received.'
      when pi.current_status = 'return_opened' then 'Review eBay return/case status.'
      else 'Open or continue return/refund follow-up.'
    end,
    now(),
    now(),
    case when pi.current_status = 'return_pending' then now() else null end,
    case when pi.current_status = 'return_opened' then now() else null end
  from public.purchase_items pi
  left join public.purchases p
    on p.purchase_id = pi.purchase_id
  where pi.current_status in ('return_pending', 'return_opened', 'cancelled')
    and not exists (
      select 1
      from public.order_problem_cases existing
      where existing.purchase_item_id = pi.item_id
        and existing.is_open = true
    )
  returning problem_case_id, workflow_state, problem_type
)
insert into public.order_problem_events (
  problem_case_id,
  event_type,
  event_source,
  message
)
select
  problem_case_id,
  'seeded_from_purchase_item_status',
  'system',
  'Seeded from existing purchase item workflow status: ' || workflow_state || ' / ' || problem_type
from seeded_cases;
