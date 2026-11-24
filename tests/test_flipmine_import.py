import copy
import os
import sys
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations'))
import import_flipmine as fm
from test_ebay_sourcing_search import settings, seed

class Query:
    def __init__(self, db, table): self.db, self.name = db, table
    def __getattr__(self, key): return lambda *a, **kw: self
    def execute(self): return SimpleNamespace(data=self.db.existing if self.name == 'sourcing_ebay_candidates' else self.db.ops if self.name == 'sourcing_opportunities' else self.db.retained if self.name == 'sourcing_flipmine_tabs' else [])
class DB:
    def __init__(self): self.existing, self.ops, self.retained = [], [], []
    def table(self, name): return Query(self, name)

def item(title='Mario Kart 8 Deluxe Nintendo Switch', platform='Nintendo Switch', **kwargs):
    return dict(itemId='v1|123456789012|0', legacyItemId='123456789012', title=title, condition='Brand New', conditionId='1000',
                buyingOptions=['FIXED_PRICE'], price={'value':'10','currency':'USD'}, shippingOptions=[{'shippingCost':{'value':'3','currency':'USD'}}],
                itemLocation={'country':'US'}, seller={'username':'fixture','feedbackPercentage':'100','feedbackScore':1000},
                localizedAspects=[{'name':'Platform','value':platform},{'name':'Game Name','value':title}],
                categories=[{'categoryId':'139973','categoryName':'Video Games'}], **kwargs)

class ImportTests(unittest.TestCase):
    def setUp(self):
        self.db = DB(); self.calls = []
        self.tab = dict(tab_id=str(uuid.uuid4()), sourcing_run_id=str(uuid.uuid4()))
        self.row = dict(row_number=2, asin='B000000001', ebay_legacy_item_id='123456789012', source_evidence={'amazon title':'FALSE', 'ebay price':.01})
        self.seed = seed('Mario Kart 8 Deluxe Nintendo Switch', 'Switch'); self.seed['asin'] = self.row['asin']
        self.context = Mock(); self.context.seed.return_value = self.seed
        patches = [patch.object(fm,'fetch_settings',return_value=settings()), patch.object(fm,'fetch_matching_context',return_value={}),
                   patch.object(fm,'fetch_historical_status_by_key',return_value={}), patch.object(fm,'get_access_token',return_value='test-token'),
                   patch.object(fm,'fetch_keepa_price_context_by_asin',return_value={}),patch.object(fm,'fetch_owned_units_by_asin',return_value={}),
                   patch.object(fm,'rpc',side_effect=self.rpc),patch('score_sourcing_opportunities.fetch_declines',return_value=[])]
        for p in patches: p.start(); self.addCleanup(p.stop)
        self.fetch = Mock(return_value=item())
        self.worker = fm.FlipmineImporter(self.db,str(uuid.uuid4()),Mock(),context=self.context,listing_fetch=self.fetch)
    def rpc(self, db, name, **args):
        self.calls.append((name, copy.deepcopy(args)))
        if name == 'flipmine_bind_candidate': return dict(duplicate=bool(self.db.ops), candidate=args['p_candidate'])
    def result(self): return next((args['p_scored'] for name,args in self.calls if name=='flipmine_write_opportunity'),None)
    def test_normal_match_uses_current_data_and_shared_scorer(self):
        self.worker.process_row(self.tab,self.row)
        result=self.result(); self.assertIsNotNone(result)
        candidate=next(args['p_candidate'] for name,args in self.calls if name=='flipmine_bind_candidate')
        self.assertEqual(candidate['price'],10); self.assertEqual(candidate['landed_cost'],13)
        self.assertEqual(candidate['ebay_title'],self.fetch.return_value['title'])
        self.assertTrue(result['matching_diagnostics_json']['hard_rule_pass'])
        self.context.seed.assert_called_once_with('B000000001')
    def test_hard_mismatch_never_becomes_closest_opportunity(self):
        self.fetch.return_value=item('Mario Kart 8 Deluxe PlayStation 5','Sony PlayStation 5')
        self.worker.process_row(self.tab,self.row)
        self.assertIsNone(self.result())
        self.assertEqual(self.calls[-1][1]['p_values']['status'],'excluded')
        self.assertFalse(self.calls[-1][1]['p_values']['evaluation']['hard_rule_pass'])
    def test_missing_shipping_remains_unknown(self):
        del self.fetch.return_value['shippingOptions']
        self.worker.process_row(self.tab,self.row)
        bound=next(args['p_candidate'] for name,args in self.calls if name=='flipmine_bind_candidate')
        self.assertIsNone(bound['landed_cost']); self.assertIsNone(bound['shipping_cost'])
        self.assertIsNone(self.result()['profit'])
    def test_pickup_only_listing_uses_normal_discovery_exclusion(self):
        del self.fetch.return_value['shippingOptions']
        self.fetch.return_value['pickupOptions']=[{'pickupAtLocationAvailability':'IN_STOCK'}]
        self.worker.process_row(self.tab,self.row)
        self.assertIsNone(self.result());self.assertEqual(self.row['status'],'excluded')
    def test_existing_pair_preserves_evaluation_and_workflow_status(self):
        self.db.existing=[dict(candidate_id='existing',asin=self.row['asin'],ebay_item_id='v1|123456789012|0',ebay_legacy_item_id='123456789012')]
        self.db.ops=[dict(opportunity_id='held',matching_diagnostics_json={'hard_rule_pass':True})]
        self.worker.process_row(self.tab,self.row)
        self.fetch.assert_not_called(); self.context.seed.assert_not_called(); self.assertIsNone(self.result())
        self.assertEqual(self.calls[0][0],'flipmine_bind_candidate')
    def test_catalog_exclusion_never_trusts_export(self):
        self.context.seed.return_value=None
        self.worker.process_row(self.tab,self.row)
        self.fetch.assert_not_called(); self.assertEqual(self.calls[-1][1]['p_values']['status'],'excluded')
    def test_provider_failure_is_retryable_not_empty_success(self):
        self.fetch.side_effect=RuntimeError('HTTP 503')
        with self.assertRaisesRegex(RuntimeError,'503'): self.worker.process_row(self.tab,self.row)
        self.assertIsNone(self.result())
    def test_same_unavailable_listing_is_not_requested_twice_for_competing_asins(self):
        self.fetch.side_effect=fm.ListingUnavailable('ended')
        for asin in ('B000000001','B000000002'):
            self.context.seed.return_value={**self.seed,'asin':asin}
            with self.assertRaises(fm.ListingUnavailable):self.worker.process_row(self.tab,{**self.row,'asin':asin})
        self.assertEqual(self.fetch.call_count,1)
    def test_same_listing_different_asins_get_different_identity(self):
        self.worker.process_row(self.tab,self.row)
        other={**self.row,'row_number':3,'asin':'B000000002'}
        self.context.seed.return_value={**self.seed,'asin':other['asin']}
        self.worker.process_row(self.tab,other)
        candidates=[args['p_candidate'] for name,args in self.calls if name=='flipmine_bind_candidate']
        self.assertNotEqual(candidates[0]['candidate_id'],candidates[1]['candidate_id']); self.assertEqual(self.fetch.call_count,1)
    def test_secret_redaction(self):
        with patch.dict(os.environ,{'GOOGLE_APPLICATION_CREDENTIALS':'/private/test-credentials-file.json','FLIPMINE_GOOGLE_SHEET_ID':'private-sheet-id'}):
            message=fm.safe_error(RuntimeError('/private/test-credentials-file.json private-sheet-id token=abc'))
        self.assertNotIn('private',message); self.assertNotIn('abc',message)

class ListingTests(unittest.TestCase):
    def response(self, status=200, payload=None): return SimpleNamespace(status_code=status,ok=status==200,json=lambda:payload or item())
    def fetch(self,response):
        with patch.object(fm,'get_with_retries',return_value=(response,{})) as get:
            result=fm.fetch_listing('token','123456789012',settings())
            self.assertTrue(get.call_args.args[0].endswith('/item/get_item_by_legacy_id'))
            self.assertEqual(get.call_args.kwargs['params']['legacy_item_id'],'123456789012')
            return result
    def test_correct_endpoint_and_identity(self): self.assertEqual(self.fetch(self.response())['legacyItemId'],'123456789012')
    def test_404_is_unavailable(self):
        with self.assertRaises(fm.ListingUnavailable): self.fetch(self.response(404))
    def test_503_is_failure(self):
        with self.assertRaises(RuntimeError): self.fetch(self.response(503))
    def test_wrong_identity_retained_for_review(self):
        payload=item(); payload['legacyItemId']='999999999999'
        with self.assertRaises(ValueError): self.fetch(self.response(payload=payload))
    def test_ended_and_out_of_stock_excluded(self):
        for payload in [item(itemEndDate='2020-01-01T00:00:00Z'),item(estimatedAvailabilities=[{'estimatedAvailableQuantity':0}])]:
            with self.subTest(payload=payload), self.assertRaises(fm.ListingUnavailable): self.fetch(self.response(payload=payload))
    def test_variation_is_not_selected_by_title(self):
        with self.assertRaisesRegex(ValueError,'Variation'): self.fetch(self.response(payload=item(itemGroupHref='https://example.test/group')))

class RunTests(unittest.TestCase):
    def test_rate_limit_pauses_entire_run_without_advancing_other_rows(self):
        worker=self.worker([{'sheet_id':0},{'sheet_id':42}])
        worker.process_tab.side_effect=fm.EbayRateLimitedError('exhausted',retry_at='2099-01-01T08:00:00Z')
        with patch.object(fm,'rpc') as rpc:self.assertEqual(worker.run(),0)
        self.assertEqual(worker.process_tab.call_count,1)
        self.assertEqual(rpc.call_args.args[1],'flipmine_pause')
        self.assertEqual(rpc.call_args.kwargs['p_until'],'2099-01-01T08:00:00Z')
    def test_due_resume_never_opens_google_or_discovers_tabs(self):
        db=Mock();q=db.table.return_value
        for key in ('select','eq','neq'):getattr(q,key).return_value=q
        tabs=[{'sheet_id':0,'tab_name':'Saved','spreadsheet_id':'fixture','source_hash':'immutable'}]
        q.execute.return_value=SimpleNamespace(data=tabs)
        worker=Mock();worker.run.return_value=0
        with patch.object(sys,'argv',['import_flipmine.py','--resume-due']),patch('sourcing_common.load_environment'),patch.object(fm,'get_supabase_client',return_value=db),patch.object(fm,'rpc',return_value=str(uuid.uuid4())),patch.object(fm,'wait_for_database'),patch.object(fm,'FlipmineSheet') as google,patch.object(fm,'refresh_buyer_offer_history'),patch.object(fm,'FlipmineImporter',return_value=worker) as construct:
            self.assertEqual(fm.main(),0)
        google.assert_not_called();self.assertEqual(construct.call_args.args[2].tabs(),tabs)
        self.assertTrue(worker.resume_only)
    def test_source_auth_failure_marks_launched_run_failed_immediately(self):
        db=Mock();query=db.table.return_value;query.update.return_value=query;query.eq.return_value=query
        with patch.object(sys,'argv',['import_flipmine.py','--run-id',str(uuid.uuid4())]),patch('sourcing_common.load_environment'),patch.object(fm,'get_supabase_client',return_value=db),patch.object(fm,'wait_for_database'),patch.object(fm,'FlipmineSheet',side_effect=PermissionError('Viewer access required')):
            self.assertEqual(fm.main(),1)
        self.assertEqual(query.update.call_args.args[0]['status'],'failed')
    def worker(self, sources):
        worker = object.__new__(fm.FlipmineImporter)
        worker.db=DB();worker.run_id=str(uuid.uuid4());worker.sheet=Mock(spreadsheet_id='fixture');worker.sheet.tabs.return_value=sources
        worker.heartbeat=Mock();worker.process_tab=Mock()
        return worker
    def test_multiple_tabs_one_manual_run(self):
        worker=self.worker([{'sheet_id':0},{'sheet_id':42}]);worker.process_tab.return_value={'failed':0}
        self.assertEqual(worker.run(),0);self.assertEqual(worker.process_tab.call_count,2)
    def test_nothing_new_is_success(self):
        worker=self.worker([{'sheet_id':0}]);worker.process_tab.return_value=None
        self.assertEqual(worker.run(),0)
    def test_row_failure_does_not_stop_other_tabs_or_report_success(self):
        worker=self.worker([{'sheet_id':0},{'sheet_id':42}]);worker.process_tab.side_effect=[{'failed':1},{'failed':0}]
        self.assertEqual(worker.run(),1);self.assertEqual(worker.process_tab.call_count,2)
    def test_tab_exception_does_not_stop_other_tabs(self):
        worker=self.worker([{'sheet_id':0},{'sheet_id':42}]);worker.process_tab.side_effect=[ValueError('headers'),{'failed':0}]
        self.assertEqual(worker.run(),1);self.assertEqual(worker.process_tab.call_count,2)
    def test_incomplete_snapshot_is_retried_after_source_tab_removed(self):
        worker=self.worker([]);retained={'sheet_id':42,'tab_name':'Removed export','source_hash':'saved'}
        worker.db.retained=[retained];worker.process_tab.return_value={'failed':0}
        self.assertEqual(worker.run(),0);worker.process_tab.assert_called_once_with(retained)

if __name__=='__main__': unittest.main()
