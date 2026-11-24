"""Real concurrent admission tests in a disposable PostgreSQL container."""
import json
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from test_flipmine_postgres import FlipmineTransactions
from test_mf_listing_batches import lit,js

@unittest.skipUnless(__name__=='__main__' or os.environ.get('MBOP_POSTGRES_TESTS')=='1','Run explicitly with Docker')
class SharedQuotaTests(unittest.TestCase):
    sql=classmethod(FlipmineTransactions.sql.__func__)
    @classmethod
    def setUpClass(cls):
        FlipmineTransactions.setUpClass.__func__(cls)
        cls.sql((Path(__file__).resolve().parents[1]/'supabase/migrations/20261124043618_mbop_shared_ebay_trading_enrichment.sql').read_text())
    def setUp(self):
        self.sql('truncate ebay_api_resource_limits,ebay_api_usage,ebay_api_events,sourcing_flipmine_runs cascade;')
        self.sql('update ebay_api_quota_policy set essential_percent=10,discovery_percent=case when resource=\'buy.browse\' then 20 else 0 end,sourcing_share_percent=50;')
    def observe(self,resource='trading',remaining=5000):
        rate={'limit':5000,'count':5000-remaining,'remaining':remaining,'reset':'2099-01-01T08:00:00Z','timeWindow':86400}
        self.sql(f"select ebay_quota_observe('app',{lit(resource)},{js(rate)});")
    def admit(self,job='catalog',method='GetItem',priority='catalog',resource='trading',peek=False):
        return json.loads(self.sql(f"select ebay_quota_admit('app',{lit(resource)},{lit(job)},{lit(method)},{lit(priority)},{str(peek).lower()});"))
    def test_methods_and_jobs_share_one_atomic_pool(self):
        self.observe(remaining=502)
        self.assertTrue(self.admit()['allowed']);self.assertTrue(self.admit(method='GetItemShipping')['allowed'])
        self.assertFalse(self.admit()['allowed'])
        self.assertTrue(self.admit('essential:purchase','GetOrders','essential')['allowed'])
        self.assertEqual(self.sql("select remaining from ebay_api_resource_limits where resource='trading'"),'499')
        self.assertEqual(self.sql('select sum(total) from ebay_api_events'),'3')
    def test_analytics_delay_never_restores_reserved_calls(self):
        self.observe();self.admit();self.observe()
        self.assertEqual(self.sql('select remaining from ebay_api_resource_limits'),'4999')
        self.assertEqual(self.sql('select calls_used from ebay_api_resource_limits'),'1')
    def test_concurrent_workers_cannot_spend_last_essential_call_twice(self):
        self.observe(remaining=1)
        with ThreadPoolExecutor(max_workers=6) as pool:
            result=list(pool.map(lambda i:self.admit(f'essential:job{i}','GetOrders','essential'),range(6)))
        self.assertEqual(sum(bool(r.get('allowed')) for r in result),1)
        self.assertEqual(self.sql('select sum(attempts) from ebay_api_usage'),'1')
    def test_search_headroom_and_configured_operational_reserve(self):
        self.observe('buy.browse',remaining=1000)
        self.assertFalse(self.admit(resource='buy.browse',method='detail')['allowed'])
        self.assertTrue(self.admit(resource='buy.browse',method='search')['allowed'])
        self.assertTrue(self.admit(resource='buy.browse',method='detail',priority='essential')['allowed'])
    def test_manual_and_catalog_shares_prevent_mutual_starvation(self):
        self.observe();self.sql("select flipmine_begin('00000000-0000-0000-0000-000000000001');")
        self.sql("insert into ebay_api_usage values('app','trading','import_flipmine.py',(now() at time zone 'America/Los_Angeles')::date,2250);")
        self.assertFalse(self.admit('import_flipmine.py',priority='manual')['allowed'])
        self.assertTrue(self.admit()['allowed'])
        self.sql("update sourcing_flipmine_runs set status='completed';")
        self.assertTrue(self.admit('import_flipmine.py',priority='manual')['allowed'])
    def test_peek_does_not_spend_and_reset_requires_refresh(self):
        self.observe();self.assertTrue(self.admit(peek=True)['allowed'])
        self.assertEqual(self.sql('select calls_used from ebay_api_resource_limits'),'0')
        self.sql("update ebay_api_resource_limits set reset_at=now()-interval '1 second';")
        self.assertTrue(self.admit()['refresh']);self.assertFalse(self.admit()['allowed'])
    def test_service_only_access(self):
        self.assertEqual(self.sql("select has_function_privilege('anon','ebay_quota_admit(text,text,text,text,text,boolean)','EXECUTE')"),'f')
        self.assertEqual(self.sql("select has_table_privilege('authenticated','ebay_api_quota_policy','UPDATE')"),'f')

if __name__=='__main__':unittest.main()
