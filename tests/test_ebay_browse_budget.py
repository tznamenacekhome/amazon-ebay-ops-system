import datetime as dt
import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations'))
import requests
import ebay_browse_budget as budget
import ebay_sourcing_search as search
from ebay_api_limits import find_resource_quota

def response(status=200,body=None,headers=None):
    r=requests.Response();r.status_code=status;r._content=json.dumps(body or {}).encode();r.headers.update(headers or {});return r

class BudgetTests(unittest.TestCase):
    def setUp(self):
        p=patch.dict(os.environ,{'EBAY_CLIENT_ID':'fixture-app'});p.start();self.addCleanup(p.stop)
        self.db=Mock();self.query=self.db.table.return_value
        for key in ('select','eq','limit','update','upsert'):getattr(self.query,key).return_value=self.query
        self.gate=budget.BrowseBudget(self.db,'fixture-job')
    def test_all_windows_choose_exhausted_daily_rate(self):
        payload={'rateLimits':[{'resources':[{'name':'buy.browse','rates':[{'limit':100,'remaining':90,'timeWindow':60},{'limit':5000,'remaining':0,'timeWindow':86400}]}]}]}
        self.assertEqual(find_resource_quota(payload,'buy.browse').remaining,0)
        self.assertEqual(find_resource_quota(payload,'buy.browse').time_window_seconds,86400)
    def test_shared_pause_raises_without_http_request(self):
        self.gate.rpc=Mock(return_value={'allowed':False,'retry_at':'2099-01-01T08:00:00Z','reason':'daily_quota_exhausted'})
        with self.assertRaises(budget.EbayQuotaPaused) as caught:self.gate.reserve()
        self.assertEqual(caught.exception.retry_at,'2099-01-01T08:00:00Z')
    def test_refresh_is_once_then_reserve(self):
        self.gate.rpc=Mock(side_effect=[{'refresh':True},{'allowed':True}]);self.gate.refresh=Mock()
        self.gate.reserve();self.gate.refresh.assert_called_once()
    def test_cache_identity_includes_marketplace_and_buyer_context(self):
        a=self.gate.cache_key('https://api.ebay.com/buy/browse/v1/item/get_item_by_legacy_id',{'params':{'legacy_item_id':'123456789012'},'headers':{'X-EBAY-C-ENDUSERCTX':'zip-A'}})
        b=self.gate.cache_key('https://api.ebay.com/buy/browse/v1/item/v1|123456789012|0',{'headers':{'X-EBAY-C-ENDUSERCTX':'zip-A'}})
        c=self.gate.cache_key('https://api.ebay.com/buy/browse/v1/item/v1|123456789012|1',{'headers':{'X-EBAY-C-ENDUSERCTX':'zip-A'}})
        self.assertEqual(a,b);self.assertNotEqual(a,c)
        self.assertEqual(a['buyer_context'],'zip-A')
        self.assertIsNone(self.gate.cache_key('https://api.ebay.com/buy/browse/v1/item_summary/search',{}))
    def test_cache_expiry_and_unverified_identity_never_reused(self):
        now=budget.utcnow();key={'item_id':'v1|123|0'}
        for expiry,payload in [(now-dt.timedelta(seconds=1),{'itemId':'v1|123|0','title':'Game'}),(now+dt.timedelta(minutes=1),{'itemId':'v1|other|0','title':'Game'})]:
            self.query.execute.return_value=SimpleNamespace(data=[{'payload':payload,'expires_at':expiry.isoformat()}])
            self.assertIsNone(self.gate.cached(key))
    def test_cache_preserves_original_payload_and_short_ttl(self):
        key={'app_key':'app','marketplace':'EBAY_US','item_id':'v1|123|0','buyer_context':'zip-A'}
        payload={'itemId':'v1|123|0','title':'Game','localizedAspects':[],'shippingOptions':[]}
        self.gate.save(key,response(body=payload))
        saved=self.query.upsert.call_args.args[0]
        self.assertEqual(saved['payload'],payload)
        self.assertEqual(budget.parsed(saved['expires_at'])-budget.parsed(saved['fetched_at']),dt.timedelta(minutes=15))
    def test_429_records_retry_after_and_daily_reset(self):
        self.gate.refresh=Mock();self.query.execute.return_value=SimpleNamespace(data=[{'remaining':0,'reset_at':'2099-01-01T08:00:00Z'}])
        error=self.gate.after_429(response(429,{'errors':[{'errorId':2001,'message':'Too many requests'}]},{'Retry-After':'120'}),120)
        self.assertEqual(error.reason,'daily_quota_exhausted');self.assertEqual(error.retry_at,'2099-01-01T08:00:00+00:00')
        self.assertEqual(self.query.update.call_args.args[0]['last_retry_after'],'120')
    def test_retry_after_numeric_is_not_capped_and_http_date_supported(self):
        self.assertEqual(search.retry_after_seconds(response(headers={'Retry-After':'7200'}),1),7200)
        seconds=search.retry_after_seconds(response(headers={'Retry-After':'Thu, 01 Jan 2099 08:00:00 GMT'}),1)
        self.assertGreater(seconds,7200)
    def test_daily_429_stops_after_one_attempt(self):
        gate=Mock();gate.cache_key.return_value=None;gate.cached.return_value=None
        gate.after_429.return_value=budget.EbayQuotaPaused('daily_quota_exhausted','2099-01-01T08:00:00Z')
        with patch.object(budget,'production_budget',return_value=gate),patch.object(search.requests,'get',return_value=response(429)) as get,patch.object(search.time,'sleep') as sleep:
            with self.assertRaises(search.EbayRateLimitedError):search.get_with_retries('https://api.ebay.com/buy/browse/v1/item/v1|123|0',call_type='detail')
        self.assertEqual(get.call_count,1);sleep.assert_not_called()
    def test_cache_hit_has_zero_browse_attempts(self):
        gate=Mock();gate.cached.return_value=response(body={'itemId':'v1|123|0','title':'Game'})
        with patch.object(budget,'production_budget',return_value=gate),patch.object(search.requests,'get') as get:
            _,metrics=search.get_with_retries('https://api.ebay.com/buy/browse/v1/item/v1|123|0',call_type='detail')
        get.assert_not_called();gate.reserve.assert_not_called();self.assertEqual(metrics['detail_call_count'],0)
    def test_other_job_exhaustion_blocks_request_before_network(self):
        gate=Mock();gate.cached.return_value=None
        gate.reserve.side_effect=budget.EbayQuotaPaused('daily_quota_exhausted','2099-01-01T08:00:00Z')
        with patch.object(budget,'production_budget',return_value=gate),patch.object(search.requests,'get') as get:
            with self.assertRaises(search.EbayRateLimitedError) as caught:search.get_with_retries('https://api.ebay.com/buy/browse/v1/item/v1|123|0',call_type='detail')
        get.assert_not_called();self.assertEqual(caught.exception.metrics['detail_call_count'],0)
    def test_temporary_throttle_has_bounded_retry_and_jitter(self):
        gate=Mock();gate.cached.return_value=None
        gate.after_429.return_value=budget.EbayQuotaPaused('temporary_throttle',(budget.utcnow()+dt.timedelta(seconds=2)).isoformat())
        with patch.object(budget,'production_budget',return_value=gate),patch.object(search.requests,'get',side_effect=[response(429,headers={'Retry-After':'2'}),response(200)]) as get,patch.object(search.time,'sleep') as sleep:
            search.get_with_retries('https://api.ebay.com/buy/browse/v1/item/v1|123|0',call_type='detail')
        self.assertEqual(get.call_count,2);sleep.assert_called_once_with(2)
        with patch.object(search.random,'uniform',return_value=.5):self.assertEqual(search.retry_after_seconds(response(429),3),8.5)

if __name__=='__main__':unittest.main()
