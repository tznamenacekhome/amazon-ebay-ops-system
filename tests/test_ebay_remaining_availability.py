import unittest,sys
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations'))
from ebay_availability import quantity_evidence
from ebay_listing_evidence import ListingRouter,EvidenceUnavailable
from ebay_sourcing_search import first_quantity
from refresh_sourcing_listing_availability import listing_is_available
import test_ebay_listing_evidence as fixtures
payload=fixtures.payload

class QuantityTests(unittest.TestCase):
 def item(self,**availability):
  p=payload();p.pop('mbopEvidence',None);p['estimatedAvailabilities']=[availability];return p
 def test_remaining_stock_is_not_fabricated(self):
  p=self.item(estimatedAvailabilityStatus='IN_STOCK',estimatedRemainingQuantity=20)
  self.assertEqual(quantity_evidence(p),(20,'available'));self.assertEqual(first_quantity(p),20)
  self.assertNotIn('availability',ListingRouter.missing(p,()));self.assertTrue(listing_is_available(p)[0]);self.assertNotIn('estimatedAvailableQuantity',p['estimatedAvailabilities'][0])
 def test_unknown_invalid_and_conflicting_quantities_stay_unknown(self):
  for a in ({'estimatedAvailabilityStatus':'UNKNOWN','estimatedRemainingQuantity':20},{'estimatedRemainingQuantity':20},{'estimatedAvailabilityStatus':'IN_STOCK'},{'estimatedAvailabilityStatus':'IN_STOCK','estimatedRemainingQuantity':20,'estimatedAvailableQuantity':0},{'estimatedAvailabilityStatus':'IN_STOCK','estimatedRemainingQuantity':True},{'estimatedAvailabilityStatus':'IN_STOCK','estimatedRemainingQuantity':-1},{'estimatedAvailabilityStatus':'IN_STOCK','estimatedRemainingQuantity':'NaN'},{'estimatedAvailabilityStatus':'IN_STOCK','estimatedRemainingQuantity':1.5}):
   p=self.item(**a);self.assertIsNone(quantity_evidence(p)[0]);self.assertIn('availability',ListingRouter.missing(p,()))
 def test_zero_sold_out_and_ended_remain_unavailable(self):
  for a in ({'estimatedAvailabilityStatus':'IN_STOCK','estimatedRemainingQuantity':0},{'estimatedAvailabilityStatus':'OUT_OF_STOCK','estimatedRemainingQuantity':20}):self.assertFalse(listing_is_available(self.item(**a))[0])
  p=self.item(estimatedAvailabilityStatus='IN_STOCK',estimatedRemainingQuantity=20);p['itemEndDate']='2020-01-01T00:00:00Z';self.assertFalse(listing_is_available(p)[0])
 def test_conflicting_availability_rows(self):
  p=self.item(estimatedAvailableQuantity=2);p['estimatedAvailabilities'].append({'estimatedAvailableQuantity':3});self.assertIsNone(quantity_evidence(p)[0])

class BrowseRecoveryTests(unittest.TestCase):
 setUp=fixtures.RouterTests.setUp
 def browse_payload(self):
  p=payload();p.pop('mbopEvidence',None);p['estimatedAvailabilities']=[{'estimatedAvailabilityStatus':'IN_STOCK','estimatedRemainingQuantity':20}]
  self.router.trading.return_value={**payload(),'shippingOptions':[]};self.router.trading.return_value['mbopEvidence']['shippingType']='Flat'
  self.router.browse.return_value=(p,{'detail_call_count':1});return p
 def test_production_failure_recovers_with_normal_fallback(self):
  p=self.browse_payload();result,_=self.router.get('123456789012');self.assertEqual(first_quantity(result),20);self.router.browse.assert_called_once()
 def test_unknown_shipping_and_wrong_buyer_not_accepted(self):
  for which in ('missing','wrong_buyer'):
   self.router.cache.clear();p=self.browse_payload()
   if which=='missing':p['shippingOptions']=[]
   else:p['shippingOptions'][0]['shipToLocationUsedForEstimate']={'country':'CA','postalCode':'other'}
   with self.assertRaises(EvidenceUnavailable):self.router.get('123456789012')
 def test_unknown_availability_and_parent_variation_not_accepted(self):
  for which in ('availability','variation'):
   self.router.cache.clear();p=self.browse_payload()
   if which=='availability':p['estimatedAvailabilities'][0]['estimatedAvailabilityStatus']='UNKNOWN'
   else:p['itemGroupHref']='parent'
   with self.assertRaises(EvidenceUnavailable):self.router.get('123456789012')
 def test_bad_shipping_cost_is_not_fabricated_as_free(self):
  for cost in ({'value':'unknown','currency':'USD'},{'value':'NaN','currency':'USD'},{'value':'0','currency':'CAD'},{'value':'-1','currency':'USD'}):
   self.router.cache.clear();p=self.browse_payload();p['shippingOptions'][0]['shippingCost']=cost
   with self.assertRaises(EvidenceUnavailable):self.router.get('123456789012')

if __name__=='__main__':unittest.main()

