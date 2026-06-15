-- Order Problems return-label tracking.
--
-- Additive only. These fields capture buyer return shipment labels/tracking
-- returned by eBay Post-Order detail endpoints after a return/case is approved.

alter table public.order_problem_cases
  add column if not exists return_tracking_number text,
  add column if not exists return_tracking_carrier text,
  add column if not exists return_tracking_status text,
  add column if not exists return_label_printed_at timestamptz;

create index if not exists order_problem_cases_return_tracking_idx
  on public.order_problem_cases (return_tracking_number)
  where return_tracking_number is not null;
