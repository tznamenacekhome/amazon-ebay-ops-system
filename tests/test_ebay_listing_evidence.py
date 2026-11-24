import copy
import os
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations'))
import ebay_listing_evidence as evidence
import ebay_trading as trading
from ebay_browse_budget import EbayQuotaPaused,TRADING_RESOURCE,RESOURCE
from ebay_sourcing_search import EbayRateLimitedError,map_item

SETTINGS=SimpleNamespace(buyer_country='US',buyer_zip='93022')

def xml(extra='', shipping='<ShippingType>Flat</ShippingType><ShippingServiceOptions><ShippingService>USPS</ShippingService><ShippingServiceCost currencyID="USD">4.25</ShippingServiceCost></ShippingServiceOptions>'):
    return ET.fromstring(f'''<GetItemResponse xmlns="urn:ebay:apis:eBLBaseComponents"><Ack>Success</Ack><Item>
    <ItemID>123456789012</ItemID><Title>Dead or Alive 5 PS3 New</Title><Description>Factory sealed physical game</Description>
    <ConditionID>1000</ConditionID><ConditionDisplayName>New</ConditionDisplayName><Country>US</Country>
    <Quantity>3</Quantity><Seller><UserID>fixture-seller</UserID><FeedbackScore>500</FeedbackScore></Seller>
    <SellingStatus><ListingStatus>Active</ListingStatus><QuantitySold>1</QuantitySold><CurrentPrice currencyID="USD">20</CurrentPrice><BidCount>2</BidCount></SellingStatus>
    <ListingType>FixedPriceItem</ListingType><PrimaryCategory><CategoryID>139973</CategoryID><CategoryName>Video Games</CategoryName></PrimaryCategory>
    <ItemSpecifics><NameValueList><Name>Platform</Name><Value>Sony PlayStation 3</Value></NameValueList><NameValueList><Name>Game Name</Name><Value>Dead or Alive 5</Value></NameValueList></ItemSpecifics>
    <ShippingDetails>{shipping}</ShippingDetails>{extra}</Item></GetItemResponse>''')

def payload():return evidence.normalize_item(xml(),SETTINGS)

class NormalizeTests(unittest.TestCase):
    def test_fixed_price_preserves_match_and_commercial_evidence(self):
        item=payload();row=map_item({'sourcing_run_id':'run','seed_id':'seed','asin':'ASIN'},item)
        self.assertEqual(row['price'],20);self.assertEqual(row['shipping_cost'],4.25)
        self.assertEqual(row['available_quantity'],2);self.assertEqual(row['condition_id'],'1000')
        self.assertEqual(row['seller_username'],'fixture-seller')
        self.assertEqual(item['localizedAspects'][0]['value'],'Sony PlayStation 3')
        self.assertIn('physical',item['description']);self.assertEqual(item['categoryId'],'139973')
    def test_auction_and_best_offer(self):
        root=xml('<BestOfferDetails><BestOfferEnabled>true</BestOfferEnabled></BestOfferDetails>')
        root.find('e:Item/e:ListingType',trading.NS).text='Chinese'
        item=evidence.normalize_item(root,SETTINGS)
        self.assertEqual(item['buyingOptions'],['AUCTION','BEST_OFFER'])
        self.assertEqual(item['currentBidPrice']['value'],'20');self.assertEqual(item['bidCount'],2)
    def test_free_requires_explicit_zero(self):
        for cost,expected in [('0','0'),('','unknown')]:
            root=xml(shipping=f'<ShippingType>Flat</ShippingType><ShippingServiceOptions><ShippingService>USPS</ShippingService><FreeShipping>true</FreeShipping><ShippingServiceCost currencyID="USD">{cost}</ShippingServiceCost></ShippingServiceOptions>')
            options=evidence.normalize_item(root,SETTINGS)['shippingOptions']
            self.assertEqual(options[0]['shippingCost']['value'] if options else 'unknown',expected)
    def test_calculated_does_not_trust_getitem_quote(self):
        item=evidence.normalize_item(xml(shipping='<ShippingType>Calculated</ShippingType><ShippingServiceOptions><ShippingService>USPS</ShippingService><ShippingServiceCost currencyID="USD">0</ShippingServiceCost></ShippingServiceOptions>'),SETTINGS)
        self.assertEqual(item['shippingOptions'],[])
    def test_buyer_restrictions_and_pickup_cannot_be_free_shipping(self):
        for shipping in ['<ExcludeShipToLocation>US</ExcludeShipToLocation>', '<ShippingServiceOptions><ShippingService>LocalPickup</ShippingService><ShippingServiceCost currencyID="USD">0</ShippingServiceCost></ShippingServiceOptions>']:
            item=evidence.normalize_item(xml(shipping='<ShippingType>Flat</ShippingType>'+shipping),SETTINGS)
            self.assertEqual(item['shippingOptions'],[])
    def test_sold_is_positive_terminal_unknown_quantity_is_not(self):
        root=xml();root.find('e:Item/e:Quantity',trading.NS).text='1'
        self.assertTrue(evidence.ListingRouter.terminal(evidence.normalize_item(root,SETTINGS)))
        root.find('e:Item/e:Quantity',trading.NS).text=''
        item=evidence.normalize_item(root,SETTINGS)
        self.assertFalse(evidence.ListingRouter.terminal(item));self.assertIn('availability',evidence.ListingRouter.missing(item,()))
    def test_variation_and_missing_condition_are_unverified(self):
        item=evidence.normalize_item(xml('<Variations><Variation><SKU>one</SKU></Variation></Variations>'),SETTINGS)
        self.assertIn('exact_variation',evidence.ListingRouter.missing(item,()))
        item=payload();item['conditionId']=None
        self.assertIn('conditionId',evidence.ListingRouter.missing(item,()))
    def test_quantity_shipping_requires_additional_cost(self):
        settings=SimpleNamespace(buyer_country='US',buyer_zip='93022',quantity_for_shipping_estimate=2)
        self.assertEqual(evidence.normalize_item(xml(),settings)['shippingOptions'],[])

class RouterTests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{'MBOP_EBAY_TRADING_ENRICHMENT':'true'});self.env.start();self.addCleanup(self.env.stop)
        self.gate=Mock();self.gate.app='fixture';self.gate.cached.return_value=None
        self.router=evidence.ListingRouter('token',SETTINGS,gate=self.gate)
        self.router.trading=Mock(return_value=payload());self.router.browse=Mock(return_value=(payload(),{'detail_call_count':1}))
    def test_prefers_trading_and_shared_cache_avoids_retrieval(self):
        first,_=self.router.get('123456789012');second,metrics=self.router.get('123456789012')
        self.assertEqual(first,second);self.router.trading.assert_called_once();self.router.browse.assert_not_called()
        self.assertEqual(metrics['duplicate_detail_calls_prevented_count'],1)
    def test_persisted_cache_is_shared_between_providers(self):
        response=Mock();response.json.return_value=payload();self.gate.cached.return_value=response
        self.router.get('123456789012');self.router.trading.assert_not_called();self.router.browse.assert_not_called()
    def test_conflicting_search_invalidates_cache(self):
        self.router.get('123456789012');self.router.get('123456789012',summary={'title':'Revised title'})
        self.assertEqual(self.router.trading.call_count,2)
    def test_browse_fallback_for_missing_condition(self):
        bad=payload();bad['conditionId']=None;self.router.trading.return_value=bad
        self.router.get('123456789012');self.router.browse.assert_called_once()
    def test_trading_works_when_browse_exhausted(self):
        def reserve(resource,**kwargs):
            if resource==RESOURCE:raise EbayQuotaPaused('exhausted','2099-01-01T08:00:00Z')
        self.gate.reserve.side_effect=reserve
        self.router.get('123456789012');self.router.browse.assert_not_called()
    def test_browse_fallback_when_trading_pool_protected(self):
        def reserve(resource,**kwargs):
            if resource==TRADING_RESOURCE:raise EbayQuotaPaused('protected','2099-01-01T08:00:00Z',TRADING_RESOURCE)
        self.gate.reserve.side_effect=reserve
        self.router.get('123456789012');self.router.browse.assert_called_once();self.router.trading.assert_not_called()
    def test_both_exhausted_preserve_retry_and_do_not_call_providers(self):
        self.gate.reserve.side_effect=EbayQuotaPaused('exhausted','2099-01-01T08:00:00Z')
        with self.assertRaises(EbayRateLimitedError):self.router.get('123456789012')
        self.router.trading.assert_not_called();self.router.browse.assert_not_called()
    def test_terminal_listing_never_falls_back(self):
        item=payload();item['mbopEvidence']['ended']=True;self.router.trading.return_value=item
        self.router.get('123456789012');self.router.browse.assert_not_called()
    def test_exact_variation_stays_on_browse(self):
        item=payload();item['itemId']='v1|123456789012|77';item['itemGroupHref']='exact-variation-group';self.router.browse.return_value=(item,{})
        self.router.get(item['itemId']);self.router.trading.assert_not_called();self.router.browse.assert_called_once()
    def test_ambiguous_parent_is_not_purchasable(self):
        item=payload();item['itemGroupHref']='group';self.router.trading.return_value=item;self.router.browse.return_value=(item,{})
        with self.assertRaises(evidence.EvidenceUnavailable):self.router.get('123456789012')
        self.assertEqual(self.router.browse.call_count,1)
    def test_calculated_shipping_only_for_viable_candidates(self):
        item=payload();item['shippingOptions']=[];item['mbopEvidence']['shippingType']='Calculated'
        self.router.trading.return_value=item;self.router.user_token='user'
        quote=ET.fromstring('<GetItemShippingResponse xmlns="urn:ebay:apis:eBLBaseComponents"><ShippingDetails><ShippingServiceOptions><ShippingService>USPS</ShippingService><ShippingServiceCost currencyID="USD">6.85</ShippingServiceCost></ShippingServiceOptions></ShippingDetails></GetItemShippingResponse>')
        with patch.object(evidence,'call',return_value=quote) as call:
            self.router.get('123456789012',viable=lambda p:False);call.assert_not_called()
            result,_=self.router.get('123456789012',viable=lambda p:True)
        self.assertEqual(result['shippingOptions'][0]['shippingCost']['value'],'6.85')
        self.assertIn('<QuantitySold>1</QuantitySold>',call.call_args.args[2])
        self.assertEqual(self.router.trading.call_count,1)
    def test_no_infinite_fallback_after_provider_errors(self):
        self.router.trading.side_effect=trading.TradingError(['17']);self.router.browse.side_effect=evidence.EvidenceUnavailable('missing')
        with self.assertRaises(evidence.EvidenceUnavailable):self.router.get('123456789012')
        self.assertEqual(self.router.trading.call_count,1);self.assertEqual(self.router.browse.call_count,1)

class TransportTests(unittest.TestCase):
    def test_xml_518_pauses_shared_pool_without_retries(self):
        import requests
        response=requests.Response();response.status_code=200;response._content=b'<Response xmlns="urn:ebay:apis:eBLBaseComponents"><Ack>Failure</Ack><Errors><SeverityCode>Error</SeverityCode><ErrorCode>518</ErrorCode><ShortMessage>Call usage limit</ShortMessage></Errors></Response>'
        gate=Mock();gate.after_429.return_value=EbayQuotaPaused('daily_quota_exhausted','2099-01-01T08:00:00Z',TRADING_RESOURCE)
        with patch.object(trading,'production_budget',return_value=gate),patch.object(trading.requests,'post',return_value=response) as post:
            with self.assertRaises(EbayQuotaPaused):trading.post(headers={'X-EBAY-API-CALL-NAME':'GetOrders'},data='xml')
        self.assertEqual(post.call_count,1);self.assertEqual(gate.reserve.call_args.args[0],TRADING_RESOURCE)
        self.assertEqual(gate.reserve.call_args.kwargs['priority'],'essential')
        self.assertTrue(gate.after_429.call_args.kwargs['exhausted'])
    def test_mutations_are_rejected_without_request(self):
        with patch.object(trading.requests,'post') as post:
            with self.assertRaises(ValueError):trading.post(headers={'X-EBAY-API-CALL-NAME':'PlaceOffer'},data='xml')
        post.assert_not_called()

class BusinessParityTests(unittest.TestCase):
    def test_legacy_availability_fallback_does_not_duplicate_shared_refresh(self):
        import refresh_sourcing_listing_availability_trading_fallback as fallback
        with patch.dict(os.environ,{'MBOP_EBAY_TRADING_ENRICHMENT':'true'}),patch.object(fallback,'parse_args'),patch.object(fallback,'load_environment'),patch.object(fallback,'get_supabase_client') as db,patch.object(fallback,'get_getitem_quota') as quota:
            self.assertEqual(fallback.main(),0)
        db.assert_not_called();quota.assert_not_called()
    def test_browse_only_pending_row_does_not_block_other_trading_rows(self):
        import import_flipmine as fm
        worker=Mock();worker.settings=SETTINGS;worker.sheet.spreadsheet_id='fixture';worker.run_id='run';worker.deadline=None
        rows=[{'status':'pending','row_number':2},{'status':'pending','row_number':3}]
        error=EbayRateLimitedError('Browse exhausted',retry_at='2099-01-01T08:00:00Z',resource=RESOURCE)
        worker.process_row.side_effect=[error,'evaluated']
        worker.row_update.side_effect=lambda tab,row,**values:row.update(values)
        with patch.dict(os.environ,{'MBOP_EBAY_TRADING_ENRICHMENT':'true'}),patch.object(fm,'rpc',return_value={'tab_id':'tab','source_hash':'saved','sourcing_run_id':'sourcing'}),patch.object(fm,'read_rows',return_value=rows),patch.object(fm,'router_for'),patch.object(fm,'production_budget',return_value=Mock()),patch.object(fm,'wait_for_database'),patch.object(fm,'enforce_one_open_opportunity_per_asin'),patch.object(fm,'snapshot_new_opportunities') as snapshot:
            with self.assertRaises(EbayRateLimitedError):fm.FlipmineImporter.process_tab(worker,{'sheet_id':0,'tab_name':'saved'})
        self.assertEqual(worker.process_row.call_count,2);self.assertEqual(rows[0]['status'],'pending');self.assertEqual(rows[1]['status'],'evaluated')
        snapshot.assert_called_once()
        # A later checkpoint must not spend Trading or catalog resources again
        # on the saved Browse-only row before its known reset.
        worker.process_row.reset_mock();worker.evaluation_context.reset_mock()
        with patch.object(fm,'rpc',return_value={'tab_id':'tab','source_hash':'saved','sourcing_run_id':'sourcing'}),patch.object(fm,'read_rows',return_value=rows),patch.object(fm,'router_for') as router,patch.object(fm,'enforce_one_open_opportunity_per_asin'),patch.object(fm,'snapshot_new_opportunities'):
            with self.assertRaises(EbayRateLimitedError):fm.FlipmineImporter.process_tab(worker,{'sheet_id':0,'tab_name':'saved'})
        worker.process_row.assert_not_called();worker.evaluation_context.assert_not_called();router.assert_not_called()
    def test_equivalent_evidence_preserves_existing_match_and_economics(self):
        from test_ebay_sourcing_search import seed,settings
        from ebay_sourcing_search import candidate_decision
        product=seed('Dead or Alive 5 PlayStation 3','PS 3');config=settings()
        trading_payload=payload();browse_payload=copy.deepcopy(trading_payload);browse_payload.pop('mbopEvidence')
        decisions=[candidate_decision(map_item(product,p),product,config,{}, {}) for p in (trading_payload,browse_payload)]
        for field in ('hard_blocks','recommendation','matching_reject','economic_reject','economic_reason','pricing','landed_cost','opportunity_shape'):
            self.assertEqual(decisions[0][field],decisions[1][field],field)
    def test_shipping_uncertainty_stays_watch_and_cannot_suggest_offer(self):
        from score_sourcing_opportunities import classify,suggested_offer
        from test_ebay_sourcing_search import settings
        candidate={'price':10,'shipping_cost':None,'best_offer_enabled':True,'available_quantity':1}
        self.assertEqual(classify(candidate,['FIXED_PRICE','BEST_OFFER'],None,30,True,settings(),shipping_unknown=True),'watch')
        self.assertIsNone(suggested_offer(candidate,30,settings()))

if __name__=='__main__':unittest.main()
