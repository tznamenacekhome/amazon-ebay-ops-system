-- Retire MBOP-owned legacy finance/reporting objects after ZFI replacement.
-- This migration is intentionally not applied by Codex.
-- Apply only after confirming MBOP no longer needs local historical copies for
-- audit/retention beyond the completed ZFI backfill.

drop view if exists public.vw_latest_ynab_category_balance_snapshot;

drop table if exists public.ynab_business_transactions;
drop table if exists public.ynab_category_balance_snapshots;
drop table if exists public.business_value_snapshots;
