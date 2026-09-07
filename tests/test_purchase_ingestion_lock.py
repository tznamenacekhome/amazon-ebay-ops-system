import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock
from integrations.purchase_ingestion_lock import claim, finish, required


class IngestionLockTests(unittest.TestCase):
    def test_all_buyer_entrypoint_groups_require_lock(self):
        from run_all_syncs import jobs_for_group
        for group in ['purchase-ingestion', 'purchases', 'dashboard', 'core', 'all']:
            self.assertTrue(required(jobs_for_group(group)), group)
        for group in ['purchase-tracking', 'sourcing-catalog', 'amazon-sales-recent']:
            self.assertFalse(required(jobs_for_group(group)), group)

    def test_claim_fails_closed_without_database(self):
        with self.assertRaises(RuntimeError): claim(None, 'run')

    def test_claim_passes_worker_identity_and_returns_existing_run(self):
        db = MagicMock()
        db.rpc.return_value.execute.return_value = SimpleNamespace(data={'acquired': False, 'run_id': 'other'})
        self.assertEqual(claim(db, 'run', 'task')['run_id'], 'other')
        db.rpc.assert_called_once_with('mbop_claim_purchase_ingestion', {'p_run_id': 'run', 'p_start': True, 'p_task_arn': 'task'})

    def test_terminal_status_is_success_only_for_ok(self):
        for status in ['ok', 'failed', 'degraded', 'blocked', 'cancelled']:
            db = MagicMock()
            finish(db, 'run', status, 'now')
            update = db.table.return_value.update.call_args.args[0]
            self.assertEqual(update['status'], 'succeeded' if status == 'ok' else 'failed')
