import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations'))
from amazon_mf import order_items,offer,condition
class AmazonMfProjection(unittest.TestCase):
 def order(self):
  return {'orderId':'ORDER','createdTime':'2026-11-01T01:00:00Z','lastUpdatedTime':'2026-11-07T01:00:00.001Z','salesChannel':{'marketplaceId':'US'},'fulfillment':{'fulfilledBy':'MERCHANT','fulfillmentStatus':'PARTIALLY_SHIPPED'},'buyer':{'email':'never-store'},'recipient':{'address':'never-store'},'associatedOrders':[{'orderId':'ORIGINAL','associationType':'REPLACEMENT_ORIGINAL_ID'}],'orderItems':[{'orderItemId':'ITEM','quantityOrdered':3,'product':{'asin':'ASIN','sellerSku':'SKU','condition':{'conditionType':'NEW'}},'fulfillment':{'quantityFulfilled':1,'quantityUnfulfilled':2}}]}
 def test_operational_scope_no_pii_and_replacement(self):
  result=order_items(self.order(),'US')[0];self.assertEqual(result['unfulfilled'],2);self.assertEqual(result['replacement_for'][0]['order_id'],'ORIGINAL');self.assertNotIn('never-store',str(result));self.assertIn('.001',result['source_updated_at'])
  wrong=self.order();wrong['fulfillment']['fulfilledBy']='AMAZON';self.assertEqual(order_items(wrong,'US'),[])
  with self.assertRaises(ValueError):order_items(self.order(),'OTHER')
 def test_cancellation_request_alone_does_not_release_stock(self):
  o=self.order();o['orderItems'][0]['cancellation']={'cancellationRequest':{'requester':'BUYER'}}
  self.assertEqual(order_items(o,'US')[0]['unfulfilled'],2)
  o['fulfillment']['fulfillmentStatus']='CANCELLED';self.assertEqual(order_items(o,'US')[0]['unfulfilled'],0)
 def test_missing_quantities_fail_instead_of_marking_sync_success(self):
  o=self.order();del o['orderItems'][0]['fulfillment']['quantityFulfilled']
  with self.assertRaises(ValueError):order_items(o,'US')
 def test_offer_live_quantity_not_last_submitted_quantity(self):
  item={'sku':'SKU','summaries':[{'marketplaceId':'US','asin':'ASIN','conditionType':'new_new','lastUpdatedDate':'2026-11-01T00:00:00Z'}],'attributes':{'fulfillment_availability':[{'fulfillment_channel_code':'DEFAULT','quantity':999}]},'fulfillmentAvailability':[{'fulfillmentChannelCode':'DEFAULT','quantity':2}]}
  r=offer(item,'US','2026-11-07T00:00:00Z',None);self.assertEqual(r['quantity'],2);self.assertEqual(r['condition'],'new')
  item['fulfillmentAvailability']=[];self.assertIsNone(offer(item,'US','2026-11-07T00:00:00Z',None)['quantity'])
  item['attributes']={};self.assertIsNone(offer(item,'US','2026-11-07T00:00:00Z',None))
 def test_conditions_match_exactly_without_fuzzy_titles(self):
  self.assertEqual(condition('used_very_good'),condition('USED','VERY_GOOD'));self.assertEqual(condition('used_like_new'),condition('USED','MINT'))
if __name__=='__main__':unittest.main()
