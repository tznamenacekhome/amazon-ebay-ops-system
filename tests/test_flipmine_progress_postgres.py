import json,os,unittest
from pathlib import Path
import test_flipmine_postgres as fixture
from test_mf_listing_batches import lit

@unittest.skipUnless(__name__=='__main__' or os.environ.get('MBOP_POSTGRES_TESTS')=='1','Disposable PostgreSQL only')
class ProgressTests(unittest.TestCase):
    sql=classmethod(fixture.FlipmineTransactions.sql.__func__)
    @classmethod
    def setUpClass(cls):
        fixture.FlipmineTransactions.setUpClass.__func__(cls)
        cls.sql((Path(__file__).resolve().parents[1]/'supabase/migrations/20261124055201_mbop_flipmine_progress_accuracy.sql').read_text())
    def setUp(self):
        fixture.FlipmineTransactions.setUp(self)
    begin=fixture.FlipmineTransactions.begin
    claim=fixture.FlipmineTransactions.claim
    snapshot=fixture.FlipmineTransactions.snapshot
    row=fixture.FlipmineTransactions.row
    def counts(self):return json.loads(self.sql(f"select counts from flipmine_progress_counts(array[{lit(self.tab['tab_id'])}::uuid]);"))
    def test_counts_are_persisted_outcomes_not_cached_summary(self):
        self.sql("update sourcing_flipmine_rows set status=case when row_number=2 then 'duplicate' else 'pending' end;")
        self.sql("update sourcing_flipmine_tabs set summary='{\"evaluated\":99,\"buyList\":7}';")
        c=self.counts();self.assertEqual(c['duplicates'],1);self.assertEqual(c['pending'],1);self.assertEqual(c['evaluated'],0);self.assertEqual(c['rows'],2)
        self.sql(f"select flipmine_refresh_progress({lit(self.run)},{lit(self.tab['tab_id'])});")
        result=json.loads(self.sql('select summary from sourcing_flipmine_tabs'))
        self.assertEqual(result['buyList'],7);self.assertEqual(result['pending'],1);self.assertEqual(result['evaluated'],0)
        self.assertEqual(self.sql('select status from sourcing_flipmine_tabs'),'running')
    def test_failure_and_api_wait_remain_outstanding(self):
        self.sql("update sourcing_flipmine_rows set status=case when row_number=2 then 'failed' else 'pending' end,evaluation='{\"api_wait\":{\"resource\":\"buy.browse\"}}';")
        c=self.counts();self.assertEqual(c['failed']+c['pending'],c['rows']);self.assertEqual(c['evaluated'],0)
        self.sql("update sourcing_flipmine_runs set status='failed';")
        self.assertEqual(self.counts(),c)
    def test_expired_worker_cannot_overwrite_summary_or_complete(self):
        self.sql("update sourcing_flipmine_runs set status='paused';update sourcing_flipmine_tabs set summary='{\"sentinel\":true}';")
        self.sql(f"select flipmine_refresh_progress({lit(self.run)},{lit(self.tab['tab_id'])});")
        self.assertTrue(json.loads(self.sql('select summary from sourcing_flipmine_tabs'))['sentinel'])
        self.assertEqual(self.counts()['pending'],2)
    def test_service_only(self):
        self.assertEqual(self.sql("select has_function_privilege('anon','flipmine_progress_counts(uuid[])','EXECUTE')"),'f')

if __name__=='__main__':unittest.main()
