"""Isolated PostgreSQL: completing without SKU and later reliable Amazon mapping."""
import os,sys,unittest,uuid
from datetime import timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from test_mf_inventory_orders import MFInventory
from test_mf_listing_batches import ROOT,lit,js

@unittest.skipUnless(__name__=='__main__' or os.environ.get('MBOP_POSTGRES_TESTS')=='1','Explicit isolated PostgreSQL test')
class DeferredMSKU(MFInventory):
 __unittest_skip__=False
 @classmethod
 def setUpClass(cls):
  super().setUpClass()
  cls.sql((ROOT/'supabase/migrations/20261108193013_mbop_mf_returns.sql').read_text(encoding='utf-8'))
  cls.sql((ROOT/'supabase/migrations/20261109014929_mbop_mf_listing_visibility.sql').read_text(encoding='utf-8'))
  cls.sql((ROOT/'supabase/migrations/20261110175424_mbop_deferred_mf_msku.sql').read_text(encoding='utf-8'))
 def offer(self,sku,condition='new',offset=10):
  payload={'seller_sku':sku,'asin':'B07RCCHQLD','condition':condition,'quantity':4,'observed_at':(self.t+timedelta(seconds=offset)).isoformat(),'status':[],'listing_state':'in_stock'}
  self.sql(f'select mbop_mf_apply_offer({lit(self.account)},{js(payload)})')
 def checkpoint(self):
  self.sql(f'update amazon_mf_accounts set offers_success_at={lit((self.t+timedelta(seconds=10)).isoformat())};select mbop_mf_register_lots();')
 def test_null_sku_partial_and_retry_preserve_physical_stock_cost(self):
  self.export();_,query=self.complete(2,sku=None);self.sql(query)
  self.assertEqual(self.sql('select quantity||\':\'||unit_cost from amazon_merchant_inventory_lots'),'2:12.34')
  self.assertEqual(self.sql('select sum(quantity) from vw_mf_pending_msku'),'2')
  self.assertEqual(self.sql('select count(*) from amazon_mf_lots'),'0')
  self.assertEqual(self.sql(f'select quantity from purchase_items where item_id={lit(self.item)}'),'2')
  self.assertEqual(self.sql('select sum(on_hand) from mbop_mf_purchase_balances(array(select listed_item_id from amazon_merchant_inventory_lots))'),'2')
 def test_successful_snapshot_reconciles_once_and_allocates_orders(self):
  self.export();self.complete(4,sku='');self.offer(self.sku)
  self.sql('select mbop_mf_register_lots()')
  self.assertEqual(self.sql('select count(*) from amazon_mf_lots'),'0','Incomplete snapshots must not map stock')
  run=str(uuid.uuid4());self.sql(f'insert into amazon_mf_sync_runs(id,account_id) values({lit(run)},{lit(self.account)})')
  self.sql(f"select mbop_mf_sync_finish({lit(run)},now(),null,{js({'offers_observed_at':(self.t+timedelta(seconds=10)).isoformat()})})")
  self.sql('select mbop_mf_register_lots();select mbop_mf_register_lots();')
  self.assertEqual(self.sql('select count(*),sum(quantity) from amazon_mf_lots'),'1|4')
  self.assertEqual(self.sql('select count(*) from vw_mf_pending_msku'),'0')
  self.assertEqual(self.sql('select seller_sku from amazon_merchant_inventory_lots'),self.sku)
  self.apply(self.orderrow(ordered=2));self.assertEqual(self.balance()['order_reserved'],2)
  self.assertEqual(self.sql('select sum(on_hand) from mbop_mf_purchase_balances(array(select listed_item_id from amazon_merchant_inventory_lots))'),'4')
 def test_ambiguous_wrong_condition_and_stale_offers_stay_pending(self):
  self.export();self.complete(4,sku=None);self.offer('A');self.offer('B');self.checkpoint()
  self.assertEqual(self.sql('select count(*) from vw_mf_pending_msku'),'1')
  self.sql("delete from amazon_mf_offers where seller_sku='B';update amazon_mf_offers set condition='used';select mbop_mf_register_lots()")
  self.assertEqual(self.sql('select count(*) from amazon_mf_lots'),'0')
  self.sql("update amazon_mf_offers set condition='new',observed_at=now()-interval '1 day';select mbop_mf_register_lots()")
  self.assertEqual(self.sql('select count(*) from amazon_mf_lots'),'0')
 def test_opening_cannot_double_count_pending_listing(self):
  self.export();self.complete(4,sku=None);self.offer(self.sku)
  rev=self.sql('select revision from amazon_mf_accounts')
  self.sql(f"select mbop_mf_opening({lit(self.account)},{lit(str(uuid.uuid4()))},{lit(self.sku)},'new',4,12.34,'counted',{rev})",ok=False)
 def test_known_sku_and_fba_behaviors_unchanged(self):
  other=str(uuid.uuid4());self.export(method='FBA',batch=other);self.complete(1,batch=other,sku=None,ok=False)
  self.export();self.complete(4,sku=self.sku)
  self.assertEqual(self.sql('select sum(quantity) from amazon_mf_lots'),'4')

def load_tests(loader,tests,pattern):return unittest.TestSuite(DeferredMSKU(n) for n in DeferredMSKU.__dict__ if n.startswith('test_'))
if __name__=='__main__':unittest.main()
