"""Actual PostgreSQL tests, isolated Docker only; no production connection."""
import json
import os
import subprocess
import sys
import time
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from test_mf_listing_batches import DOCKER, ROOT, js, lit

MIGRATION = ROOT / 'supabase/migrations/20261109030118_mbop_non_ebay_purchase_intake.sql'


@unittest.skipUnless(__name__ == '__main__' or os.environ.get('MBOP_POSTGRES_TESTS') == '1', 'Explicit isolated PostgreSQL test')
class ReceiptTransactions(unittest.TestCase):
    @classmethod
    def sql(cls, query, ok=True):
        result = subprocess.run(DOCKER + ['exec', '-i', cls.container, 'psql', '-U', 'postgres', '-At', '-v', 'ON_ERROR_STOP=1'], input=query.encode('utf-8'), capture_output=True)
        if ok and result.returncode: raise AssertionError(result.stderr.decode())
        if not ok and not result.returncode: raise AssertionError('Expected transaction rejection')
        return result.stdout.decode().strip()

    @classmethod
    def setUpClass(cls):
        cls.container = 'mbop-receipt-test-' + uuid.uuid4().hex[:10]
        subprocess.run(DOCKER + ['run', '--rm', '-d', '--name', cls.container, '-e', 'POSTGRES_PASSWORD=isolated-local-test', 'postgres:17'], check=True, capture_output=True)
        cls.addClassCleanup(lambda: subprocess.run(DOCKER + ['stop', cls.container], check=True, capture_output=True))
        for _ in range(80):
            if subprocess.run(DOCKER + ['exec', cls.container, 'psql', '-U', 'postgres', '-Atc', 'select 1'], capture_output=True).returncode == 0:
                time.sleep(2)
                if subprocess.run(DOCKER + ['exec', cls.container, 'psql', '-U', 'postgres', '-Atc', 'select 1'], capture_output=True).returncode == 0: break
            time.sleep(.5)
        cls.sql('''create role anon; create role authenticated; create role service_role bypassrls;
        create schema storage;
        create table storage.buckets(id text primary key,name text,public boolean,file_size_limit bigint,allowed_mime_types text[]);
        create table purchases(purchase_id uuid primary key default gen_random_uuid(),supplier text not null,supplier_order_id text,order_date date,total_order_cost numeric(12,2),shipping_cost numeric(12,2),tax_amount numeric(12,2),order_status text,raw_import_json jsonb,notes text);
        create table purchase_items(item_id uuid primary key default gen_random_uuid(),purchase_id uuid references purchases,title text not null,supplier_sku text,system text,quantity integer,unit_cost numeric(12,2),current_status text,condition text,asin text,amazon_title text,target_price numeric(12,2),manual_unit_cost_override boolean,exclude_from_purchase_reporting boolean,exclusion_reason text,raw_import_json jsonb);
        create view vw_purchases_dashboard as select pi.*,p.order_date,p.supplier from purchase_items pi join purchases p using(purchase_id);
        ''')
        cls.sql(MIGRATION.read_text(encoding='utf-8-sig'))
        cls.sql((ROOT / 'supabase/migrations/20261110040733_mbop_receipt_review_costs_and_matching.sql').read_text(encoding='utf-8-sig'))

    def setUp(self):
        self.sql('truncate purchase_intake_drafts,purchase_items,purchases;')
        self.id = str(uuid.uuid4())
        self.data = {'supplier': 'Eastern Leaf', 'order_id': '823933', 'order_date': '2026-05-11', 'currency': 'USD', 'shipping': 0, 'tax': 0, 'discount': 0, 'order_total': 172.91, 'notes': '', 'items': [self.item('Tilly Tacker', 20, 172.91)]}
        self.draft(self.id)

    def item(self, title, quantity, amount):
        return {'title': title, 'supplier_sku': '', 'quantity': quantity, 'line_total': amount, 'condition': 'new', 'system': '', 'exclude_from_purchase_reporting': False}

    def draft(self, id, status='review'):
        self.sql(f"insert into purchase_intake_drafts(id,document_sha256,original_filename,mime_type,storage_path,status) values({lit(id)},{lit(uuid.uuid4().hex * 2)},'receipt.pdf','application/pdf',{lit(id)},{lit(status)});")

    def preview(self): return json.loads(self.sql(f'select mbop_purchase_intake_costs({js(self.data)})'))
    def save(self, id=None, ok=True): return self.sql(f'select mbop_save_purchase_intake({lit(id or self.id)},{js(self.data)})', ok=ok)

    def test_exact_order_cost_and_original_lineage_with_uneven_unit_cents(self):
        costs = self.preview()
        self.assertAlmostEqual(costs['items'][0]['average_unit_cost'], 8.6455)
        self.save()
        self.assertEqual(self.sql('select sum(quantity),sum(quantity*unit_cost) from purchase_items'), '20|172.91')
        self.assertEqual(self.sql("select string_agg(quantity||'@'||unit_cost,',' order by unit_cost) from purchase_items"), '9@8.64,11@8.65')
        self.assertEqual(self.sql("select count(*) from purchase_items where current_status='ordered' and raw_import_json->>'intake_draft_id'="+lit(self.id)), '2')
        self.assertEqual(self.sql("select supplier||'|'||order_date::text from purchases"), 'Eastern Leaf|2026-05-11')
        self.assertEqual(self.sql("select cost_snapshot->>'order_total' from purchase_intake_drafts"), '172.91')
        self.assertEqual(self.sql('select sum(quantity) from vw_purchase_intake_receiving'), '20')

    def test_shipping_tax_discount_allocate_by_merchandise_value(self):
        self.data.update(items=[self.item('A', 2, 20), self.item('B', 1, 30)], discount=5, shipping=4, tax=1, order_total=50)
        self.assertEqual([v['landed_total'] for v in self.preview()['items']], [20, 30])
        self.save(); self.assertEqual(self.sql('select sum(unit_cost*quantity) from purchase_items'), '50.00')

    def test_packing_fee_is_landed_cost_not_stock_and_asin_price_survive(self):
        self.data.update(supplier='Rainforest Flora Inc',order_id='INV/2026/00714',shipping=23,other_charges=10,order_total=333,items=[self.item('Tilly Tacker 3.7 oz',50,300)])
        self.data['items'][0].update(asin='B092FLB415',amazon_title='Tilly Tacker, 3.7 oz',sell_price='31.99')
        costs=self.preview()
        self.assertEqual(costs['other_charges'],10)
        self.assertAlmostEqual(costs['items'][0]['average_unit_cost'],6.66)
        self.save()
        self.assertEqual(self.sql('select sum(quantity),sum(quantity*unit_cost) from purchase_items'),'50|333.00')
        self.assertEqual(self.sql("select asin||'|'||target_price||'|'||amazon_title from purchase_items"),'B092FLB415|31.99|Tilly Tacker, 3.7 oz')

    def test_invalid_asin_and_sell_price_rejected_atomically(self):
        self.data['items'][0]['asin']='BAD';self.save(ok=False)
        self.data['items'][0]['asin']='B092FLB415';self.data['items'][0]['sell_price']='-1';self.save(ok=False)
        self.assertEqual(self.sql('select count(*) from purchases'),'0')

    def test_single_product_grand_total_preserves_unknown_charge_breakdown(self):
        self.data.update(cost_basis='total_only',shipping=None,tax=None,discount=None)
        self.data['items'][0]['line_total']=None
        costs=self.preview()
        self.assertIsNone(costs['shipping']); self.assertIsNone(costs['subtotal'])
        self.assertAlmostEqual(costs['items'][0]['average_unit_cost'],8.6455)
        self.save()
        self.assertEqual(self.sql('select sum(quantity*unit_cost) from purchase_items'),'172.91')
        self.assertEqual(self.sql('select shipping_cost is null and tax_amount is null from purchases'),'t')
        second=str(uuid.uuid4());self.draft(second)
        self.data['items'].append(self.item('Second product',1,10));self.save(second,ok=False)

    def test_largest_remainder_and_zero_merchandise_are_deterministic(self):
        self.data.update(items=[self.item('A', 1, 0), self.item('B', 2, 0)], shipping=.01, order_total=.01)
        self.assertEqual([v['landed_total'] for v in self.preview()['items']], [0, .01])
        self.save(); self.assertEqual(self.sql('select sum(quantity*unit_cost) from purchase_items'), '0.01')

    def test_repeat_and_concurrent_save_create_one_purchase(self):
        query = f'select mbop_save_purchase_intake({lit(self.id)},{js(self.data)})'
        jobs = [subprocess.Popen(DOCKER + ['exec', '-i', self.container, 'psql', '-U', 'postgres', '-At', '-v', 'ON_ERROR_STOP=1'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(2)]
        for job in jobs: job.stdin.write(query.encode()); job.stdin.close(); job.stdin = None
        for job in jobs:
            out, err = job.communicate(timeout=30); self.assertEqual(job.returncode, 0, err.decode())
        self.save()
        self.assertEqual(self.sql('select count(*) from purchases'), '1')
        self.assertEqual(self.sql('select sum(quantity) from purchase_items'), '20')

    def test_different_scan_of_same_supplier_invoice_is_blocked(self):
        self.save(); second = str(uuid.uuid4()); self.draft(second); self.save(second, ok=False)
        self.assertEqual(self.sql('select count(*) from purchases'), '1')

    def test_invalid_totals_missing_fields_and_ebay_are_rejected_atomically(self):
        original = json.loads(json.dumps(self.data))
        for field, value in [('order_total', 172.90), ('shipping', None), ('currency', 'CAD'), ('supplier', 'eBay'), ('order_date', '')]:
            self.data = dict(original); self.data[field] = value; self.save(ok=False)
        self.data = original; self.data['items'][0]['quantity'] = 0; self.save(ok=False)
        self.assertEqual(self.sql('select count(*) from purchases'), '0')
        self.assertEqual(self.sql('select count(*) from purchase_items'), '0')

    def test_extraction_claim_retry_lease_and_saved_protection(self):
        self.sql(f"update purchase_intake_drafts set status='uploaded' where id={lit(self.id)}")
        first = str(uuid.uuid4()); second = str(uuid.uuid4())
        self.assertEqual(self.sql(f'select mbop_dispatch_purchase_intake({lit(self.id)},{lit(first)})'), 't')
        self.assertEqual(self.sql(f'select mbop_dispatch_purchase_intake({lit(self.id)},{lit(second)})'), 'f')
        def claim(token): return self.sql(f'select count(*) from mbop_claim_purchase_intake({lit(self.id)},{lit(token)})')
        self.assertEqual(claim(first), '1'); self.assertEqual(claim(second), '0')
        self.sql("update purchase_intake_drafts set extraction_started_at=now()-interval '16 minutes'")
        self.assertEqual(claim(second), '1')
        self.sql(f"update purchase_intake_drafts set status='review' where extraction_token={lit(first)}")
        self.assertEqual(self.sql('select status from purchase_intake_drafts'), 'extracting')
        self.sql("update purchase_intake_drafts set status='review'"); self.save()
        self.assertEqual(claim(str(uuid.uuid4())), '0')

    def test_non_resale_flag_preserved_and_public_rpc_access_denied(self):
        self.data['items'][0]['exclude_from_purchase_reporting'] = True; self.save()
        self.assertEqual(self.sql('select bool_and(exclude_from_purchase_reporting) from purchase_items'), 't')
        self.assertEqual(self.sql('select count(*) from vw_purchase_intake_receiving'), '0')
        self.sql(f'set role anon; select mbop_purchase_intake_costs({js(self.data)})', ok=False)
        self.sql('set role anon; select * from purchase_intake_drafts', ok=False)


if __name__ == '__main__': unittest.main()
