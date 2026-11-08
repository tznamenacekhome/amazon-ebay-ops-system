"""Real PostgreSQL transaction tests in an isolated, disposable Docker container.
Run: python tests/test_mf_listing_batches.py (Docker Desktop, postgres:17).
Never connects to production or publishes a database port.
"""
import json
import subprocess
import time
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKER = ['docker', '-H', 'npipe:////./pipe/dockerDesktopLinuxEngine']

def lit(value):
    return "'" + str(value).replace("'", "''") + "'"

def js(value):
    return lit(json.dumps(value)) + '::jsonb'

class ListingTransactions(unittest.TestCase):
    @classmethod
    def sql(cls, query, ok=True):
        r = subprocess.run(DOCKER + ['exec', '-i', cls.container, 'psql', '-U', 'postgres', '-At', '-v', 'ON_ERROR_STOP=1'], input=query, text=True, capture_output=True)
        if ok and r.returncode: raise AssertionError(r.stderr)
        if not ok and not r.returncode: raise AssertionError('Expected transaction rejection: ' + query)
        return r.stdout.strip()

    @classmethod
    def setUpClass(cls):
        cls.container = 'mbop-listing-test-' + uuid.uuid4().hex[:10]
        subprocess.run(DOCKER + ['run','--rm','-d','--name',cls.container,'-e','POSTGRES_PASSWORD=isolated-local-test','postgres:17'], check=True, capture_output=True)
        cls.addClassCleanup(lambda: subprocess.run(DOCKER+['stop',cls.container],check=True,capture_output=True))
        for _ in range(120):
            r=subprocess.run(DOCKER+['exec',cls.container,'psql','-U','postgres','-Atc','select 1'],capture_output=True)
            if r.returncode==0:
                time.sleep(2)
                if subprocess.run(DOCKER+['exec',cls.container,'psql','-U','postgres','-Atc','select 1'],capture_output=True).returncode==0: break
            time.sleep(0.5)
        cls.sql('''create role anon; create role authenticated; create role service_role bypassrls;
        create table purchases(purchase_id uuid primary key);
        create table purchase_items(item_id uuid primary key default gen_random_uuid(),purchase_id uuid references purchases,
          title text not null,quantity integer,unit_cost numeric,asin text,current_status text,marketplace text,
          exclude_from_purchase_reporting boolean default false,condition text,received_date date,verified_date date,
          raw_import_json jsonb,manual_split_child boolean default false,manual_split_parent_item_id uuid,
          notes text,manual_unit_cost_override boolean default false);
        create table amazon_skus(seller_sku text,asin text);
        create table fba_shipments(fba_shipment_id uuid primary key,shipment_code text);
        create table fba_shipment_source_items(fba_shipment_id uuid,source_row_id uuid,quantity integer,included boolean);
        create table fba_shipment_items(fba_shipment_id uuid,item_id uuid,quantity integer,included boolean);
        ''')
        cls.sql((ROOT/'supabase/migrations/20261108035549_mbop_amazon_listing_batches.sql').read_text())

    def setUp(self):
        self.batch=str(uuid.uuid4()); self.item=str(uuid.uuid4()); self.purchase=str(uuid.uuid4())
        self.sql(f"insert into purchases values({lit(self.purchase)}); insert into purchase_items(item_id,purchase_id,title,quantity,unit_cost,asin,current_status,marketplace,condition,received_date,verified_date,notes,raw_import_json) values({lit(self.item)},{lit(self.purchase)},'Game',4,12.34,'B07RCCHQLD','received','Amazon','new','2026-11-01','2026-11-02','original receipt note','{{\"receipt_evidence\":\"preserved\"}}');")

    def export(self, method='MF', batch=None, quantity=4):
        batch=batch or self.batch
        a={'item_id':self.item,'source_type':'purchase_item','purchase_id':self.purchase,'asin':'B07RCCHQLD','condition':'new','unit_cost':12.34,'quantity':quantity,'received_date':'2026-11-01'}
        return self.sql(f"select mbop_save_listing_batch({lit(batch)},{lit(method)},'2026-01-17 17:42','MF 2026-01-17 05:42 PM',{js({self.item:str(quantity)})},'EXACT CSV',{js([a])});")

    def complete(self, quantity=1, request=None, batch=None, sku='ACTUAL-MF-SKU', ok=True):
        payload=[{'allocation_id':self.sql(f'select id from amazon_listing_allocations where batch_id={lit(batch or self.batch)}'), 'quantity':quantity,'seller_sku':sku}]
        request=request or str(uuid.uuid4())
        query=f"select mbop_complete_mf_listing({lit(batch or self.batch)},{lit(request)},{js(payload)},'2026-01-17 17:42');"
        return self.sql(query,ok=ok),query

    def test_partial_completion_preserves_cost_and_receipts(self):
        self.export(); self.complete(2)
        self.assertEqual(self.sql(f'select quantity||\':\'||current_status from purchase_items where item_id={lit(self.item)}'),'2:received')
        self.assertEqual(self.sql(f"select quantity||':'||unit_cost||':'||confirmation_source||':'||physical_location from amazon_merchant_inventory_lots where source_item_id={lit(self.item)}"),'2:12.34:manual:merchant')
        self.assertEqual(self.sql(f"select p.notes||':'||p.received_date||':'||p.verified_date||':'||(p.raw_import_json->>'receipt_evidence') from purchase_items p join amazon_merchant_inventory_lots l on l.listed_item_id=p.item_id where l.source_item_id={lit(self.item)}"),'original receipt note:2026-11-01:2026-11-02:preserved')
        self.assertEqual(self.sql(f'select status from amazon_listing_batches where id={lit(self.batch)}'),'partially_listed')
        self.complete(2)
        self.assertEqual(self.sql(f'select sum(quantity) from amazon_merchant_inventory_lots where source_item_id={lit(self.item)}'),'4')

    def test_retry_and_completed_batch_cannot_duplicate_stock(self):
        self.export(); _,query=self.complete(4)
        self.sql(query)
        self.complete(1,ok=False)
        self.assertEqual(self.sql(f'select sum(quantity) from amazon_merchant_inventory_lots where source_item_id={lit(self.item)}'),'4')

    def test_reexport_is_immutable_and_never_creates_stock(self):
        self.export(); self.sql(f"select mbop_save_listing_batch({lit(self.batch)},'FBA','2026-02-01','changed','{{}}','CHANGED','[]');")
        self.assertEqual(self.sql(f'select export_csv from amazon_listing_batches where id={lit(self.batch)}'),'EXACT CSV')
        self.assertEqual(self.sql(f'select count(*) from amazon_merchant_inventory_lots where source_item_id={lit(self.item)}'),'0')
        self.sql(f"select mbop_save_listing_batch({lit(self.batch)},'MF','2026-02-01','changed','{{}}');",ok=False)

    def test_overcompletion_and_unknown_msku_roll_back(self):
        self.export(); self.complete(5,ok=False); self.complete(1,sku='',ok=False)
        self.assertEqual(self.sql(f'select count(*) from amazon_listing_completions where batch_id={lit(self.batch)}'),'0')
        self.assertEqual(self.sql(f'select quantity from purchase_items where item_id={lit(self.item)}'),'4')

    def test_other_batch_cannot_consume_same_units(self):
        self.export(); other=str(uuid.uuid4());self.export(batch=other);self.complete(4)
        self.complete(1,batch=other,ok=False)
        self.assertEqual(self.sql(f'select count(*) from amazon_listing_completions where batch_id={lit(other)}'),'0')

    def test_draft_restores_zeroes_and_fba_rejects_mf_completion(self):
        selection={self.item:'0',str(uuid.uuid4()):'2'}
        self.sql(f"select mbop_save_listing_batch({lit(self.batch)},'FBA','2026-01-17 17:42','FBA draft',{js(selection)});")
        self.assertEqual(json.loads(self.sql(f'select selection from amazon_listing_batches where id={lit(self.batch)}')),selection)
        self.export(method='FBA'); self.complete(1,ok=False)
        shipment=str(uuid.uuid4());self.sql(f"insert into fba_shipments values({lit(shipment)},'FBA-TEST');insert into fba_shipment_items values({lit(shipment)},{lit(self.item)},4,true);select mbop_finish_fba_listing_batch({lit(self.batch)},'FBA-TEST');")
        self.assertEqual(self.sql(f'select status from amazon_listing_batches where id={lit(self.batch)}'),'completed')
        self.assertEqual(self.sql(f'select count(*) from amazon_merchant_inventory_lots where source_item_id={lit(self.item)}'),'0')

    def test_concurrent_retries_create_one_lot(self):
        from concurrent.futures import ThreadPoolExecutor
        self.export()
        allocation=self.sql(f'select id from amazon_listing_allocations where batch_id={lit(self.batch)}')
        payload=[{'allocation_id':allocation,'quantity':4,'seller_sku':'ACTUAL-MF-SKU'}]
        query=f"select mbop_complete_mf_listing({lit(self.batch)},{lit(str(uuid.uuid4()))},{js(payload)},'2026-01-17 17:42');"
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(self.sql,[query,query]))
        self.assertEqual(self.sql(f'select count(*) from amazon_merchant_inventory_lots where source_item_id={lit(self.item)}'),'1')

    def test_multiple_allocations_roll_back_together(self):
        self.export()
        allocation=self.sql(f'select id from amazon_listing_allocations where batch_id={lit(self.batch)}')
        second=str(uuid.uuid4())
        self.sql(f"insert into amazon_listing_allocations(id,batch_id,source_key,source_item_id,purchase_id,snapshot,quantity) select {lit(second)},batch_id,'second',source_item_id,purchase_id,snapshot,quantity from amazon_listing_allocations where id={lit(allocation)};")
        ids=sorted([allocation,second])
        payload=[{'allocation_id':ids[0],'quantity':1,'seller_sku':'REAL'},{'allocation_id':ids[1],'quantity':5,'seller_sku':'REAL'}]
        self.sql(f"select mbop_complete_mf_listing({lit(self.batch)},{lit(str(uuid.uuid4()))},{js(payload)},'2026-01-17 17:42');",ok=False)
        self.assertEqual(self.sql(f'select quantity from purchase_items where item_id={lit(self.item)}'),'4')
        self.assertEqual(self.sql(f'select count(*) from amazon_merchant_inventory_lots where source_item_id={lit(self.item)}'),'0')
        self.assertEqual(self.sql(f'select sum(listed_quantity) from amazon_listing_allocations where batch_id={lit(self.batch)}'),'0')

if __name__=='__main__': unittest.main()
