import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations'))
import score_sourcing_opportunities as scoring
import run_daily_catalog_sourcing as catalog
import sourcing_database_guard as guard


class IncrementalTests(unittest.TestCase):
    def test_candidate_query_restricts_seed_scope_on_every_page(self):
        db = MagicMock()
        q = db.table.return_value
        for method in ('select', 'eq', 'in_', 'order', 'range'):
            getattr(q, method).return_value = q
        q.execute.side_effect = [SimpleNamespace(data=[{'candidate_id': n} for n in range(100)]), SimpleNamespace(data=[])]
        self.assertEqual(len(list(scoring.fetch_candidates(db, 'run', ['new-seed']))), 100)
        self.assertEqual(q.in_.call_count, 2)
        q.in_.assert_called_with('seed_id', ['new-seed'])
        self.assertEqual(list(scoring.fetch_candidates(db, 'run', [])), [])

    def test_retry_after_committed_insert_does_not_insert_again(self):
        db = MagicMock()
        q = db.table.return_value
        q.insert.return_value = q
        q.upsert.return_value = q
        q.execute.side_effect = [RuntimeError('lost response'), SimpleNamespace(data=[])]
        rows = [{'candidate_id': 'candidate', 'status': 'open'}]
        with patch.object(scoring, 'guard_if_enabled'), patch.object(scoring, 'fetch_existing_opportunities', side_effect=[[], [{'candidate_id': 'candidate', 'opportunity_id': 'saved', 'status': 'dismissed'}]]):
            with self.assertRaises(RuntimeError):
                scoring.upsert_opportunities(db, 'run', rows)
            self.assertEqual(scoring.upsert_opportunities(db, 'run', rows), (1, 0))
        self.assertEqual(q.insert.call_count, 1)
        self.assertEqual(q.upsert.call_args.args[0][0]['status'], 'dismissed')

    def test_recovery_retries_saved_scoring_scope_without_search(self):
        with patch.object(catalog, 'wait_for_database') as ready, patch.object(catalog.time, 'sleep'), patch.object(catalog, 'run_python', side_effect=[subprocess.CalledProcessError(1, 'score'), None]) as run:
            catalog.score_chunk(object(), 'run', ['seed1', 'seed2'])
        self.assertEqual(ready.call_count, 2)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args_list[0], run.call_args_list[1])
        self.assertEqual(run.call_args.args[0][-2:], ['--seed-ids', 'seed1,seed2'])

    def test_active_other_scheduler_prevents_abandoned_work_recovery(self):
        db = MagicMock()
        q = db.table.return_value
        q.select.return_value = q
        q.eq.return_value = q
        q.execute.return_value = SimpleNamespace(data=[{'run_id': 'other'}])
        with self.assertRaises(RuntimeError):
            catalog.recover_abandoned_searches(db, 'cycle')
        q.update.assert_not_called()


class GuardTests(unittest.TestCase):
    def healthy(self):
        return {'pg_up': 1, 'node_memory_MemAvailable_bytes': 1024**3, 'node_memory_MemTotal_bytes': 2*1024**3,
                'node_memory_SwapFree_bytes': 1024**3, 'node_memory_SwapTotal_bytes': 1024**3,
                'node_filesystem_avail_bytes': 2*1024**3, 'node_filesystem_size_bytes': 8*1024**3}

    def test_low_swap_or_memory_or_disk_blocks(self):
        self.assertIsNone(guard.pressure_reason(self.healthy()))
        for key in ('node_memory_SwapFree_bytes', 'node_memory_MemAvailable_bytes', 'node_filesystem_avail_bytes', 'pg_up'):
            values = self.healthy(); values[key] = 0
            self.assertIsNotNone(guard.pressure_reason(values))
        self.assertEqual(guard.pressure_reason({}), 'missing_metrics')

    def test_pressure_waits_then_tiny_read_and_timeout_never_reads(self):
        db = MagicMock()
        with patch.dict(os.environ, {'SUPABASE_URL': 'https://froeucjkcepuhgwisped.supabase.co', 'SUPABASE_SERVICE_ROLE_KEY': 'test'}), patch.object(guard.requests, 'get'), patch.object(guard, 'emit'), patch.object(guard.time, 'sleep') as sleep:
            with patch.object(guard, 'parse_pressure', side_effect=[{}, self.healthy()]):
                guard.wait_for_database(db, attempts=2)
            self.assertEqual(sleep.call_count, 1)
            db.table.assert_called_once_with('sourcing_runs')
            db.reset_mock()
            with patch.object(guard, 'parse_pressure', return_value={}):
                with self.assertRaises(guard.DatabasePressureError):
                    guard.wait_for_database(db, attempts=2)
            db.table.assert_not_called()
