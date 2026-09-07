"""Run against an explicitly selected disposable Docker PostgreSQL container."""
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
CONTAINER = os.environ.get('MBOP_SQL_TEST_CONTAINER')


@unittest.skipUnless(CONTAINER, 'Set MBOP_SQL_TEST_CONTAINER to an isolated PostgreSQL test container')
class BuyingSqlTests(unittest.TestCase):
    @classmethod
    def sql(cls, text, database=None):
        return subprocess.run(['docker', 'exec', '-i', CONTAINER, 'psql', '-U', 'postgres',
                               '-d', database or cls.database, '-X', '-qAt', '-v', 'ON_ERROR_STOP=1'],
                              input=text, text=True, capture_output=True, check=True).stdout.strip()

    @classmethod
    def setUpClass(cls):
        info = json.loads(subprocess.check_output(['docker', 'inspect', CONTAINER], text=True))[0]
        assert info['HostConfig']['NetworkMode'] == 'none', 'Only network-isolated disposable containers are allowed'
        cls.database = 'zfi_test_' + uuid.uuid4().hex
        cls.sql('create database ' + cls.database, 'postgres')
        cls.sql((ROOT / 'tests/zfi_buying_fixture.sql').read_text())
        cls.sql((ROOT / 'supabase/migrations/20260907000000_mbop_zfi_buying_contract.sql').read_text())

    @classmethod
    def tearDownClass(cls):
        cls.sql('drop database ' + cls.database, 'postgres')

    def test_1_facts_privileges_watermark_and_reservation(self):
        self.sql((ROOT / 'tests/zfi_buying_assertions.sql').read_text())

    def test_2_parallel_reservations_have_one_owner(self):
        ids = [str(uuid.uuid4()) for _ in range(8)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            rows = list(pool.map(lambda rid: json.loads(self.sql(
                f"select mbop_claim_purchase_ingestion('{rid}')")), ids))
        self.assertEqual(sum(row['acquired'] for row in rows), 1)
        self.assertEqual(len({row['run_id'] for row in rows}), 1)
        self.sql("update mbop_purchase_ingestion_requests set status='failed',completed_at=now() where status in ('queued','running')")

    def test_3_legacy_active_scheduled_run_is_returned(self):
        old = str(uuid.uuid4())
        self.sql(f"insert into scheduler_runs(run_id,group_name,status,ecs_task_arn) values('{old}','purchase-ingestion','running','legacy-task')")
        row = json.loads(self.sql(f"select mbop_claim_purchase_ingestion('{uuid.uuid4()}')"))
        self.assertFalse(row['acquired'])
        self.assertEqual(row['run_id'], old)
        self.sql("update scheduler_runs set status='ok'; update mbop_purchase_ingestion_requests set status='succeeded' where status='running'")
        other = str(uuid.uuid4())
        self.sql(f"insert into scheduler_runs(run_id,group_name,status,ecs_task_arn) values('{other}','purchases','running','broader-worker')")
        row = json.loads(self.sql(f"select mbop_claim_purchase_ingestion('{uuid.uuid4()}')"))
        self.assertFalse(row['acquired'])
        self.assertEqual(row['run_id'], other)
