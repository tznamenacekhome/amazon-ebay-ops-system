"""Disposable PostgreSQL transaction acceptance checks; no production writes."""
import json,os,sys,unittest,uuid
from datetime import timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from test_mf_inventory_orders import MFInventory
from test_mf_listing_batches import lit,js,ROOT

@unittest.skipUnless(__name__=='__main__' or os.environ.get('MBOP_POSTGRES_TESTS')=='1','Explicit Docker transaction tests')
class MFReturns(MFInventory):
    __unittest_skip__=False
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sql((ROOT/'supabase/migrations/20261108193013_mbop_mf_returns.sql').read_text(encoding='utf-8'))
    def setUp(self):
        super().setUp()
        self.stock();self.apply(self.orderrow(shipped=3,status='Shipped',second=2))
        self.report=str(uuid.uuid4());self.tracking='1Z1234567890123456'
        self.sql(f"insert into amazon_mf_return_reports(id,account_id,window_start,window_end) values({lit(self.report)},{lit(self.account)},now()-interval '59 days',now());")
    def import_return(self,item='amazon-item',sku=None,qty=3,rma='RMA',tracking=None):
        row={'source_key':rma+':'+item,'amazon_order_id':'customer-order','amazon_order_item_id':item,'seller_sku':sku or self.sku,'asin':'B07RCCHQLD','title':'Game','rma':rma,'quantity':qty,'packages':[{'tracking_number':tracking or self.tracking,'delivery_at':self.t.isoformat()}]}
        rid=self.sql(f'select mbop_mf_return_import({lit(self.account)},{lit(self.report)},{js(row)});')
        return rid,row
    def receive(self,rid=None,tracking=None):
        pid=self.sql(f"select id from amazon_mf_return_packages where account_id={lit(self.account)} and tracking_number={lit(tracking or self.tracking)}")
        request=str(uuid.uuid4());received=(self.t-timedelta(seconds=1)).isoformat()
        query=f"select mbop_mf_return_receive({lit(self.account)},{lit(request)},{lit(pid)},null,'RAW SCAN',{lit(received)},'Package only',{lit(rid) if rid else 'null'});"
        self.sql(query);self.sql(query)
        return pid
    def inspect(self,rid,pid,q=1,disposition='saleable',req=None,**extra):
        data={'return_id':rid,'package_id':pid,'quantity':q,'condition':'new','disposition':disposition,'product_scan':'B07RCCHQLD','notes':'Contents counted and tested','identity_confirmed':True,'inspected_at':self.t.isoformat(),**extra}
        query=f'select mbop_mf_return_inspect({lit(self.account)},{lit(req or str(uuid.uuid4()))},{js(data)});'
        return query
    def test_return_import_no_stock_and_partial_saleable_once_with_cost(self):
        rid,row=self.import_return();self.import_return()
        self.assertEqual(self.balance()['on_hand'],1)
        self.assertEqual(self.sql('select count(*) from amazon_mf_returns'),'1')
        pid=self.receive();self.assertEqual(self.balance()['on_hand'],1)
        query=self.inspect(rid,pid);self.sql(query);self.sql(query)
        self.assertEqual(self.balance()['on_hand'],2)
        self.assertEqual(self.sql('select physical_status from vw_mf_open_returns'),'partially_received')
        self.assertEqual(self.sql('select unit_cost from amazon_mf_lots where return_inspection_id is not null'),'12.34')
        self.assertEqual(self.sql('select count(*) from amazon_mf_lots where parent_lot_id is not null'),'1')
        self.sql(self.inspect(rid,pid,q=3),ok=False)
    def test_package_not_product_and_missing_or_wrong_never_restock(self):
        rid,_=self.import_return();pid=self.receive()
        self.assertEqual(self.sql('select physical_status from vw_mf_open_returns'),'received_awaiting_inspection')
        self.sql(self.inspect(rid,pid,disposition='wrong_item'))
        self.sql(self.inspect(rid,pid,disposition='missing'))
        self.assertEqual(self.balance()['on_hand'],1)
        self.assertEqual(self.sql('select contents_exception from vw_mf_open_returns'),'t')
    def test_multiple_packages_items_and_missing_identity(self):
        rid,_=self.import_return(qty=2);second,_=self.import_return(item='unmatched-item',sku='OTHER',qty=1)
        self.assertEqual(self.sql('select count(*) from amazon_mf_return_packages'),'1')
        self.assertEqual(self.sql('select count(*) from amazon_mf_return_package_items'),'2')
        self.receive();self.import_return(qty=2,tracking='9400000000000000000000')
        self.assertEqual(self.sql('select count(*) from amazon_mf_return_packages'),'2')
        pid=self.receive(tracking='9400000000000000000000')
        self.sql(self.inspect(rid,pid))
        self.sql(self.inspect(second,pid),ok=False)
    def test_hold_resolution_restores_stock_only_after_saleable(self):
        rid,_=self.import_return();pid=self.receive();request=str(uuid.uuid4())
        self.sql(self.inspect(rid,pid,disposition='inspection_hold',req=request))
        self.assertEqual(self.balance()['available'],1)
        self.assertEqual(self.sql('select inspection_held from vw_mf_inventory'),'1')
        self.sql(self.inspect(rid,pid,release_inspection=request))
        self.assertEqual(self.balance()['available'],2)
        self.assertEqual(self.sql('select inspection_held from vw_mf_inventory'),'0')
        self.sql(self.inspect(rid,pid,release_inspection=request),ok=False)
    def test_posted_refund_before_receipt_returnless_and_duplicate(self):
        rid,_=self.import_return()
        txn={'transaction_id':'REFUND1','amazon_order_id':'customer-order','marketplace_id':'US','kind':'Refund','status':'RELEASED','posted_at':self.t.isoformat(),'amount':'-20.00','currency':'USD','items':[],'components':[]}
        query=f'select mbop_mf_return_finance({lit(self.account)},{js(txn)},{lit(self.t.isoformat())});'
        self.sql(query);self.sql(query)
        self.assertEqual(self.sql('select count(*) from amazon_mf_return_finances'),'1')
        self.assertEqual(self.sql('select refunded_unreceived from vw_mf_open_returns'),'t')
        self.assertEqual(self.balance()['on_hand'],1)
        self.sql(f"update amazon_mf_returns set manual_returnless=true where id={lit(rid)}")
        self.assertEqual(self.sql('select refunded_unreceived from vw_mf_open_returns'),'f')
        self.sql(f'delete from amazon_mf_return_observations;delete from amazon_mf_return_package_items;delete from amazon_mf_returns where id={lit(rid)}')
        self.assertEqual(self.sql('select financial_status from vw_mf_open_returns'),'order_refund_needs_item_review')
    def test_inspection_without_receipt_and_concurrent_restock(self):
        rid,_=self.import_return();pid=self.sql('select id from amazon_mf_return_packages')
        self.sql(self.inspect(rid,pid),ok=False);self.receive()
        import concurrent.futures
        queries=[self.inspect(rid,pid,q=2),self.inspect(rid,pid,q=2)]
        def execute(query):
            try:self.sql(query);return True
            except AssertionError:return False
        with concurrent.futures.ThreadPoolExecutor() as pool: results=list(pool.map(execute,queries))
        self.assertEqual(sorted(results),[False,True]);self.assertEqual(self.balance()['on_hand'],3)
    def test_old_reports_do_not_rollback_quantities(self):
        rid,row=self.import_return(qty=2)
        self.sql(f"update amazon_mf_return_reports set source_created_at=now()-interval '2 days' where id={lit(self.report)}")
        row['quantity']=1
        self.sql(f'select mbop_mf_return_import({lit(self.account)},{lit(self.report)},{js(row)})')
        self.assertEqual(self.sql(f'select expected_quantity from amazon_mf_returns where id={lit(rid)}'),'2')
    def test_financial_release_lifecycle_is_one_posted_debit(self):
        self.import_return()
        txn={'transaction_id':'DEFERRED','release_transaction_id':'RELEASED','amazon_order_id':'customer-order','marketplace_id':'US','kind':'Refund','status':'DEFERRED_RELEASED','posted_at':self.t.isoformat(),'amount':'-20','currency':'USD','items':[],'components':[]}
        def ingest(t):self.sql(f'select mbop_mf_return_finance({lit(self.account)},{js(t)},{lit(self.t.isoformat())});')
        ingest(txn);released={**txn,'transaction_id':'RELEASED','release_transaction_id':None,'deferred_transaction_id':'DEFERRED','status':'RELEASED'};ingest(released);ingest(txn)
        self.assertEqual(self.sql('select count(*) from vw_mf_return_finances'),'1')
        self.assertEqual(self.sql('select posted_refund_net from vw_mf_open_returns'),'-20')
    def test_ambiguous_order_item_does_not_choose_a_lot(self):
        other=self.orderrow(shipped=1,status='Shipped',second=3);other['amazon_order_item_id']='ANOTHER-ITEM';self.apply(other)
        rid,row=self.import_return(item='',qty=1)
        self.assertEqual(self.sql(f'select order_item_id is null from amazon_mf_returns where id={lit(rid)}'),'t')
        pid=self.receive();self.sql(self.inspect(rid,pid),ok=False)
        exact=self.sql("select id from amazon_mf_order_items where amazon_order_item_id='amazon-item'")
        self.sql(f"select mbop_mf_return_match({lit(self.account)},{lit(rid)},{lit(exact)},1,'Reviewed RMA and actual order item')")
        self.sql(self.inspect(rid,pid));self.assertEqual(self.balance()['on_hand'],1)
    def test_counted_opening_excludes_received_inspection_hold(self):
        rid,_=self.import_return();pid=self.receive();self.sql(self.inspect(rid,pid,disposition='inspection_hold'))
        self.sql(f"select mbop_mf_apply_offer({lit(self.account)},{js({'seller_sku':self.sku,'asin':'B07RCCHQLD','condition':'new','quantity':2,'observed_at':self.t.isoformat(),'status':[]})});")
        revision=self.sql(f'select revision from amazon_mf_accounts where id={lit(self.account)}')
        self.sql(f"select mbop_mf_opening({lit(self.account)},{lit(str(uuid.uuid4()))},{lit(self.sku)},'new',2,null,'Physical total includes held return',{revision})")
        self.assertEqual(self.sql('select added_quantity from amazon_mf_openings'),'0')

def load_tests(loader, tests, pattern):
    return unittest.TestSuite(MFReturns(name) for name in MFReturns.__dict__ if name.startswith('test_'))

if __name__=='__main__':unittest.main()
