-- Operator maintenance only, not a schema migration; target froeucjkcepuhgwisped.
-- Run only AFTER verified archive cleanup, with adequate free disk space.
-- Preserves all live rows/columns. SKIP_LOCKED avoids waiting for an initial lock.
-- A table rewrite briefly locks finance snapshot reads; do not run during a sync.
-- Submit as one standalone command, outside a transaction.
VACUUM (FULL, ANALYZE, SKIP_LOCKED) public.amazon_finance_balance_snapshots;
