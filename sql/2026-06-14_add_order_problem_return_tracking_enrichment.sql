-- Order Problems return tracking enrichment.
--
-- Additive only. These fields let EasyPost monitor buyer return labels to the
-- seller without mixing outbound return shipments into inbound supplier
-- shipment tables.

alter table public.order_problem_cases
  add column if not exists return_easypost_tracker_id text,
  add column if not exists return_tracking_url text,
  add column if not exists return_tracking_delivered_at timestamptz,
  add column if not exists return_tracking_last_sync_at timestamptz,
  add column if not exists return_tracking_events_json jsonb;

create index if not exists order_problem_cases_return_easypost_tracker_idx
  on public.order_problem_cases (return_easypost_tracker_id)
  where return_easypost_tracker_id is not null;

create index if not exists order_problem_cases_return_tracking_open_idx
  on public.order_problem_cases (workflow_state, return_tracking_number)
  where is_open = true and return_tracking_number is not null;
