import sys,unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations'))
from amazon_mf_listings import discover_listings
from amazon_mf import offer

class ListingDiscovery(unittest.TestCase):
 def test_partition_recovers_late_skus_past_amazon_cap(self):
  start=datetime(2025,1,1,tzinfo=timezone.utc)
  items=[{'sku':f'SKU-{i:04}','summaries':[{'marketplaceId':'US','createdDate':(start+timedelta(days=i)).isoformat()}]} for i in range(1001)]
  class Client:
   def request(self,method,path,params):
    low=datetime.fromisoformat(params['createdAfter']) if params.get('createdAfter') else start
    high=datetime.fromisoformat(params['createdBefore'])
    rows=[x for x in items if low<=datetime.fromisoformat(x['summaries'][0]['createdDate'])<=high]
    offset=int(params.get('pageToken',0));next_offset=offset+20
    result={'numberOfResults':len(rows),'items':rows[offset:next_offset]}
    if next_offset<min(1000,len(rows)):result['pagination']={'nextToken':str(next_offset)}
    return result
  with patch('amazon_mf_listings.time.sleep'):
   result,calls=discover_listings(Client(),'SELLER','US',(start+timedelta(days=1100)).isoformat())
  self.assertEqual(len(result),1001);self.assertIn('SKU-1000',{x['sku'] for x in result});self.assertLess(calls,100)
 def test_truncated_or_repeated_tokens_and_budget_never_report_full_coverage(self):
  class Client:
   def request(self,*args,**kwargs):return {'numberOfResults':2,'items':[{'sku':'ONE'}]}
  with self.assertRaisesRegex(ValueError,'before reported'):discover_listings(Client(),'S','US','2026-11-09T00:00:00Z')
  with self.assertRaisesRegex(ValueError,'budget'):discover_listings(Client(),'S','US','2026-11-09T00:00:00Z',max_calls=0)
 def item(self,q,status,actions=()):
  return {'sku':'SKU','summaries':[{'marketplaceId':'US','conditionType':'new_new','status':status}],
   'fulfillmentAvailability':[{'fulfillmentChannelCode':'DEFAULT','quantity':q}],
   'attributes':{'fulfillment_availability':[{'fulfillment_channel_code':'DEFAULT','quantity':999}]},
   'issues':[{'enforcements':{'actions':[{'action':x} for x in actions]}}]}
 def test_buyable_search_suppressed_wreath_remains_in_stock(self):
  self.assertEqual(offer(self.item(1,['BUYABLE'],['SEARCH_SUPPRESSED']),'US','NOW',None)['listing_state'],'in_stock')
 def test_zero_retained_listing_included_but_suppressed_and_fba_excluded(self):
  self.assertEqual(offer(self.item(0,['DISCOVERABLE']),'US','NOW',None)['listing_state'],'out_of_stock')
  self.assertEqual(offer(self.item(0,['DISCOVERABLE'],['LISTING_SUPPRESSED']),'US','NOW',None)['listing_state'],'inactive')
  self.assertEqual(offer(self.item(2,['DISCOVERABLE']),'US','NOW',None)['listing_state'],'inactive')
  item=self.item(0,['BUYABLE']);item['fulfillmentAvailability']=[{'fulfillmentChannelCode':'AMAZON_NA'}]
  self.assertIsNone(offer(item,'US','NOW',None))

if __name__=='__main__':unittest.main()
