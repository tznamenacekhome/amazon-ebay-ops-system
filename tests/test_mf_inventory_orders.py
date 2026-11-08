import json,os,sys,unittest,uuid
from datetime import datetime,timedelta,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent));sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations'))
from test_mf_listing_batches import ListingTransactions,lit,js,ROOT
from amazon_mf import order_items,offer,condition

@unittest.skipUnless(__name__=='__main__' or os.environ.get('MBOP_POSTGRES_TESTS')=='1','Explicit Docker transaction test')
class MFInventory(ListingTransactions):
    __unittest_skip__=False
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sql((ROOT/'supabase/migrations/20261108042001_mbop_mf_inventory_orders.sql').read_text(encoding='utf-8-sig'))
        cls.sql((ROOT/'supabase/migrations/20261108044257_mbop_mf_historical_order_baseline.sql').read_text(encoding='utf-8'))
    def setUp(self):
        super().setUp()
        self.sql('truncate amazon_mf_accounts cascade;truncate amazon_merchant_inventory_lots cascade;')
        self.account=str(uuid.uuid4());self.t=datetime.now(timezone.utc);self.sku='ACTUAL-MF-SKU'
        self.sql(f"insert into amazon_mf_accounts(id,seller_id,marketplace_id,tracking_started_at) values({lit(self.account)},'SELLER','US',{lit((self.t-timedelta(days=2)).isoformat())});")
    def stock(self,q=4):
        self.export(quantity=q);self.complete(q)
    def orderrow(self,shipped=0,ordered=3,status='Unshipped',second=1,oid='customer-order',sku=None):
        return {'marketplace_id':'US','fulfillment_channel':'MFN','amazon_order_id':oid,'amazon_order_item_id':'amazon-item','seller_sku':sku or self.sku,'asin':'B07RCCHQLD','condition':'new','title':'Game','ordered':ordered,'shipped':shipped,'unfulfilled':max(ordered-shipped,0),'status':status,'source_updated_at':(self.t+timedelta(seconds=second)).isoformat(),'purchased_at':self.t.isoformat(),'replacement_for':[]}
    def apply(self,item):self.sql(f'select mbop_mf_apply_order({lit(self.account)},{js(item)});')
    def balance(self):return json.loads(self.sql(f"select row_to_json(x) from (select on_hand,order_reserved,available from vw_mf_inventory where account_id={lit(self.account)} and seller_sku={lit(self.sku)})x"))
    def test_reserve_partial_ship_cancel_retry_refund_no_restock(self):
        self.stock();self.apply(self.orderrow());self.assertEqual(self.balance(),{'on_hand':4,'order_reserved':3,'available':1})
        partial=self.orderrow(shipped=1,status='PartiallyShipped',second=2);self.apply(partial);self.apply(partial)
        self.assertEqual(self.balance(),{'on_hand':3,'order_reserved':2,'available':1})
        self.apply(self.orderrow(shipped=1,status='Canceled',second=3));self.assertEqual(self.balance(),{'on_hand':3,'order_reserved':0,'available':3})
        # A newer Amazon regression/refund observation is not physical return receiving.
        self.apply(self.orderrow(shipped=0,status='Canceled',second=4));self.assertEqual(self.balance()['on_hand'],3)
        self.apply(self.orderrow(second=1));self.assertEqual(self.balance()['order_reserved'],0)
    def test_replacement_independent_item_and_shortages_visible(self):
        self.stock();self.apply(self.orderrow(ordered=4));self.apply(self.orderrow(ordered=2,oid='replacement-order'))
        self.assertEqual(self.balance()['available'],-2)
        self.assertEqual(self.sql(f'select sum(reservation_shortage) from vw_mf_orders where account_id={lit(self.account)}'),'2')
        self.apply(self.orderrow(shipped=4,ordered=4,status='Shipped',second=4));self.apply(self.orderrow(shipped=2,ordered=2,status='Shipped',second=5,oid='replacement-order'))
        self.assertEqual(self.balance()['on_hand'],0)
        self.assertEqual(self.sql(f'select sum(shipment_shortage) from vw_mf_orders where account_id={lit(self.account)}'),'2')
    def test_opening_overlap_idempotence_unknown_cost(self):
        self.stock();self.sql(f"select mbop_mf_apply_offer({lit(self.account)},{js({'seller_sku':self.sku,'asin':'B07RCCHQLD','condition':'new','quantity':9,'observed_at':self.t.isoformat(),'status':[]})});")
        rev=self.sql(f'select revision from amazon_mf_accounts where id={lit(self.account)}');req=str(uuid.uuid4())
        query=f"select mbop_mf_opening({lit(self.account)},{lit(req)},{lit(self.sku)},'new',6,null,'Physically counted total including MBOP lots',{rev});"
        self.sql(query);self.sql(query);self.assertEqual(self.balance()['on_hand'],6)
        self.assertEqual(self.sql(f'select quantity||\':\'||coalesce(unit_cost::text,\'unknown\') from amazon_mf_lots where opening_id={lit(req)}'),'2:unknown')
        self.sql(query.replace(lit(req),lit(str(uuid.uuid4()))),ok=False)
    def test_unmatched_and_old_shipments_do_not_consume_later_opening(self):
        self.apply(self.orderrow(shipped=2,ordered=2,status='Shipped',second=-1,sku='NO-STOCK'))
        self.sql(f"select mbop_mf_apply_offer({lit(self.account)},{js({'seller_sku':'NO-STOCK','asin':'B07RCCHQLD','condition':'new','quantity':2,'observed_at':self.t.isoformat(),'status':[]})});")
        rev=self.sql(f'select revision from amazon_mf_accounts where id={lit(self.account)}')
        self.sql(f"select mbop_mf_opening({lit(self.account)},{lit(str(uuid.uuid4()))},'NO-STOCK','new',2,null,'Counted after historical shipment',{rev});")
        self.assertEqual(self.sql("select on_hand from vw_mf_inventory where seller_sku='NO-STOCK'"),'2')
        self.assertEqual(self.sql("select shipment_shortage from vw_mf_orders where seller_sku='NO-STOCK'"),'2')
    def test_keep_mf_user_false_survives_default_and_old_offers(self):
        payload={'seller_sku':self.sku,'asin':'B092FLB415','condition':'new','quantity':8,'observed_at':self.t.isoformat(),'status':[]}
        self.sql(f'select mbop_mf_apply_offer({lit(self.account)},{js(payload)});')
        self.sql(f"update amazon_mf_preferences set keep_mf=false,source='operator' where account_id={lit(self.account)};")
        payload['observed_at']=(self.t-timedelta(seconds=1)).isoformat();payload['quantity']=99
        self.sql(f'select mbop_mf_apply_offer({lit(self.account)},{js(payload)});')
        self.assertEqual(self.sql('select keep_mf from amazon_mf_preferences'),'f');self.assertEqual(self.sql('select amazon_quantity from amazon_mf_offers'),'8')

    def test_fifo_cost_lineage_across_two_lots_and_concurrent_retries(self):
        from concurrent.futures import ThreadPoolExecutor
        self.stock();self.sql(f"select mbop_mf_apply_offer({lit(self.account)},{js({'seller_sku':self.sku,'asin':'B07RCCHQLD','condition':'new','quantity':9,'observed_at':self.t.isoformat(),'status':[]})});")
        rev=self.sql(f'select revision from amazon_mf_accounts where id={lit(self.account)}')
        self.sql(f"select mbop_mf_opening({lit(self.account)},{lit(str(uuid.uuid4()))},{lit(self.sku)},'new',6,40,'Two extra counted units',{rev});")
        item=self.orderrow(shipped=5,ordered=5,status='Shipped',second=60)
        with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(self.apply,[item,item]))
        self.assertEqual(self.sql("select string_agg(unit_cost::text||':'||shipped,',' order by acquired_at,id) from vw_mf_lot_balances"),'12.34:4,40:1')
        self.assertEqual(self.balance()['on_hand'],1)
    def test_wrong_scope_rejected_and_equal_timestamp_conflicts_visible(self):
        row=self.orderrow();row['marketplace_id']='OTHER'
        self.sql(f'select mbop_mf_apply_order({lit(self.account)},{js(row)});',ok=False)
        row['marketplace_id']='US';self.apply(row);row['ordered']=99;self.apply(row)
        self.assertEqual(self.sql('select ordered from amazon_mf_order_items'),'3')
        self.assertIn('Conflicting',self.sql('select anomaly from amazon_mf_order_items'))
        self.assertEqual(self.sql("select count(*) from amazon_mf_order_observations where outcome='timestamp_conflict'"),'1')
    def test_failed_sync_never_advances_success_watermark(self):
        run=str(uuid.uuid4());self.sql(f"insert into amazon_mf_sync_runs(id,account_id) values({lit(run)},{lit(self.account)});update amazon_mf_accounts set last_attempt_at=(select started_at from amazon_mf_sync_runs where id={lit(run)}) where id={lit(self.account)};")
        self.sql(f"select mbop_mf_sync_finish({lit(run)},now(),'Orders permission HTTP 403','{{}}');")
        self.assertEqual(self.sql('select last_success_at is null and orders_through is null from amazon_mf_accounts'),'t')
        self.assertIn('403',self.sql('select last_error from amazon_mf_accounts'))

    def test_historical_refund_update_cannot_consume_newly_counted_stock(self):
        self.stock();row=self.orderrow(shipped=2,ordered=2,status='Shipped')
        row['purchased_at']=(self.t-timedelta(days=3)).isoformat()
        self.apply(row)
        self.assertEqual(self.balance()['on_hand'],4)
        self.assertEqual(self.sql('select baseline_shipped from amazon_mf_order_items'),'2')
        self.assertIn('timing requires reconciliation',self.sql('select anomaly from amazon_mf_order_items'))
        self.assertEqual(self.sql('select count(*) from amazon_mf_shipment_events'),'0')

if __name__=='__main__':unittest.main()
