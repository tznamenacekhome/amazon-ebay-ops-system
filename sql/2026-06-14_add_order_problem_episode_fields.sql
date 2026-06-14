-- Order Problems episode tracking.
--
-- Additive only. This lets one purchase item move through multiple separate
-- order-problem episodes over time while preserving one open episode per item.

alter table public.order_problem_cases
  add column if not exists episode_kind text,
  add column if not exists episode_sequence integer,
  add column if not exists opened_reason text,
  add column if not exists resolved_reason text,
  add column if not exists superseded_by_case_id uuid references public.order_problem_cases(problem_case_id) on delete set null,
  add column if not exists source_artifact_type text;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'order_problem_cases_episode_kind_check'
      and conrelid = 'public.order_problem_cases'::regclass
  ) then
    alter table public.order_problem_cases
      add constraint order_problem_cases_episode_kind_check
      check (
        episode_kind is null
        or episode_kind in (
          'delivery_delay',
          'carrier_stall',
          'carrier_exception',
          'item_not_received',
          'replacement_tracking',
          'damaged_item',
          'incomplete_item',
          'cancelled_refund',
          'return_request',
          'refund_followup'
        )
      );
  end if;

  if not exists (
    select 1
    from pg_constraint
    where conname = 'order_problem_cases_opened_reason_check'
      and conrelid = 'public.order_problem_cases'::regclass
  ) then
    alter table public.order_problem_cases
      add constraint order_problem_cases_opened_reason_check
      check (
        opened_reason is null
        or opened_reason in (
          'system_candidate',
          'carrier_stale',
          'carrier_exception',
          'ebay_inquiry',
          'ebay_return',
          'ebay_case',
          'receiving_exception',
          'manual',
          'cancellation'
        )
      );
  end if;

  if not exists (
    select 1
    from pg_constraint
    where conname = 'order_problem_cases_resolved_reason_check'
      and conrelid = 'public.order_problem_cases'::regclass
  ) then
    alter table public.order_problem_cases
      add constraint order_problem_cases_resolved_reason_check
      check (
        resolved_reason is null
        or resolved_reason in (
          'tracking_resumed',
          'delivered',
          'received_ok',
          'replacement_received',
          'refund_received',
          'seller_cancelled_refunded',
          'operator_closed',
          'superseded',
          'no_refund',
          'no_action'
        )
      );
  end if;

  if not exists (
    select 1
    from pg_constraint
    where conname = 'order_problem_cases_source_artifact_type_check'
      and conrelid = 'public.order_problem_cases'::regclass
  ) then
    alter table public.order_problem_cases
      add constraint order_problem_cases_source_artifact_type_check
      check (
        source_artifact_type is null
        or source_artifact_type in (
          'derived_candidate',
          'ebay_inquiry',
          'ebay_return',
          'ebay_case',
          'receiving_exception',
          'manual'
        )
      );
  end if;

  if not exists (
    select 1
    from pg_constraint
    where conname = 'order_problem_cases_episode_sequence_check'
      and conrelid = 'public.order_problem_cases'::regclass
  ) then
    alter table public.order_problem_cases
      add constraint order_problem_cases_episode_sequence_check
      check (episode_sequence is null or episode_sequence > 0);
  end if;
end $$;

with numbered as (
  select
    problem_case_id,
    row_number() over (
      partition by purchase_item_id
      order by first_detected_at nulls last, created_at, problem_case_id
    ) as sequence_number,
    case
      when problem_type = 'late_delivery_candidate' then 'delivery_delay'
      when problem_type = 'stale_tracking_candidate' then 'carrier_stall'
      when problem_type = 'carrier_exception_candidate' then 'carrier_exception'
      when problem_type = 'missing_items' and ebay_current_type = 'ITEM_NOT_RECEIVED_INQUIRY' then 'item_not_received'
      when problem_type = 'missing_items' then 'incomplete_item'
      when problem_type = 'cancelled_refund_followup' then 'cancelled_refund'
      when problem_type = 'not_as_listed' then 'damaged_item'
      when problem_type = 'return_needed' then 'return_request'
      else 'return_request'
    end as inferred_episode_kind,
    case
      when problem_source = 'derived_order_problem' then 'system_candidate'
      when problem_source = 'ebay_inquiry_sync' then 'ebay_inquiry'
      when problem_source = 'ebay_return_sync' then 'ebay_return'
      when problem_source = 'receiving_return_pending' then 'receiving_exception'
      when problem_source = 'ebay_cancellation_sync' then 'cancellation'
      else 'manual'
    end as inferred_opened_reason,
    case
      when problem_source = 'derived_order_problem' then 'derived_candidate'
      when problem_source = 'ebay_inquiry_sync' then 'ebay_inquiry'
      when problem_source = 'ebay_return_sync' then 'ebay_return'
      when problem_source = 'receiving_return_pending' then 'receiving_exception'
      else 'manual'
    end as inferred_source_artifact_type,
    case
      when is_open = true then null
      when workflow_state = 'resolved_refunded' then 'refund_received'
      when workflow_state = 'resolved_received_item' then 'replacement_received'
      when workflow_state = 'closed_no_refund' then 'no_refund'
      when workflow_state = 'closed_no_action' then 'no_action'
      else null
    end as inferred_resolved_reason
  from public.order_problem_cases
)
update public.order_problem_cases c
set
  episode_sequence = coalesce(c.episode_sequence, numbered.sequence_number),
  episode_kind = coalesce(c.episode_kind, numbered.inferred_episode_kind),
  opened_reason = coalesce(c.opened_reason, numbered.inferred_opened_reason),
  source_artifact_type = coalesce(c.source_artifact_type, numbered.inferred_source_artifact_type),
  resolved_reason = coalesce(c.resolved_reason, numbered.inferred_resolved_reason)
from numbered
where c.problem_case_id = numbered.problem_case_id;

create index if not exists order_problem_cases_episode_idx
  on public.order_problem_cases (purchase_item_id, episode_sequence);

create index if not exists order_problem_cases_episode_kind_idx
  on public.order_problem_cases (episode_kind, is_open);

create index if not exists order_problem_cases_source_artifact_idx
  on public.order_problem_cases (source_artifact_type, ebay_return_id, ebay_inquiry_id, ebay_case_id);
