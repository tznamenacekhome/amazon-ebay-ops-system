import os,sys,unittest
from pathlib import Path
from datetime import timedelta
sys.path.insert(0,str(Path(__file__).parent))
from test_mf_inventory_orders import MFInventory
from test_mf_listing_batches import lit,js,ROOT

@unittest.skipUnless(__name__=='__main__' or os.environ.get('MBOP_POSTGRES_TESTS')=='1','Explicit isolated PostgreSQL test')
class ListingVisibility(MFInventory):
 __unittest_skip__=False
 @classmethod
 def setUpClass(cls):
  super().setUpClass()
  cls.sql((ROOT/'supabase/migrations/20261109014929_mbop_mf_listing_visibility.sql').read_text(encoding='utf-8'))
 def test_current_live_in_stock_zero_stock_and_inactive_separation(self):
  for sku,q,state,observed in [('live',4,'in_stock',self.t),('zero',0,'out_of_stock',self.t),('suppressed',5,'inactive',self.t),('deleted',3,'in_stock',self.t-timedelta(days=1))]:
   self.sql(f"select mbop_mf_apply_offer({lit(self.account)},{js({'seller_sku':sku,'asin':'ASIN','condition':'new','title':'Stocking '+sku,'quantity':q,'listing_state':state,'observed_at':observed.isoformat(),'status':[]})})")
  self.sql(f'update amazon_mf_accounts set offers_success_at={lit(self.t.isoformat())} where id={lit(self.account)}')
  self.assertEqual(self.sql("select string_agg(seller_sku,',' order by seller_sku) from vw_mf_inventory_listings"),'live,zero')
  self.assertEqual(self.sql("select seller_sku from vw_mf_inventory_listings where listing_state='in_stock'"),'live')
  self.assertEqual(self.sql("select seller_sku from vw_mf_inventory_listings where listing_state='out_of_stock'"),'zero')
  self.assertEqual(self.sql('select count(*) from amazon_mf_offers'),'4')
 def test_hide_inactive_listing_without_removing_physical_lot_or_operator_preference(self):
  self.stock()
  payload={'seller_sku':self.sku,'asin':'B07RCCHQLD','condition':'new','title':'Tilly','brand':'Tilly Tackers','quantity':4,'listing_state':'inactive','observed_at':self.t.isoformat(),'status':[]}
  self.sql(f'select mbop_mf_apply_offer({lit(self.account)},{js(payload)})')
  self.sql("update amazon_mf_preferences set keep_mf=false")
  payload['observed_at']=(self.t+timedelta(seconds=1)).isoformat()
  self.sql(f'select mbop_mf_apply_offer({lit(self.account)},{js(payload)})')
  self.sql(f'update amazon_mf_accounts set offers_success_at={lit(self.t.isoformat())} where id={lit(self.account)}')
  self.assertEqual(self.sql('select count(*) from vw_mf_inventory_listings'),'0')
  self.assertEqual(self.sql('select sum(on_hand) from vw_mf_lot_balances'),'4')
  self.assertEqual(self.sql('select keep_mf from amazon_mf_preferences'),'f')

def load_tests(loader,tests,pattern):return unittest.TestSuite(ListingVisibility(n) for n in ListingVisibility.__dict__ if n.startswith('test_'))
if __name__=='__main__':unittest.main()
