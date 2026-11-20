"""Isolated PostgreSQL recovery conservation, rollback and retry checks."""
import json
import os
import unittest
import uuid
import subprocess
from concurrent.futures import ThreadPoolExecutor
from test_mf_listing_batches import ListingTransactions, ROOT, DOCKER, lit, js


@unittest.skipUnless(__name__ == '__main__' or os.environ.get('MBOP_POSTGRES_TESTS') == '1', 'Explicit isolated PostgreSQL test')
class Recovery(ListingTransactions):
    __unittest_skip__ = False

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sql('''
          alter table amazon_merchant_inventory_lots alter column seller_sku drop not null;
          alter table amazon_skus add column marketplace_id text,add column condition text,add column fulfillment_channel text,
           add column fnsku text,add column raw_listing_json jsonb,add column updated_at timestamptz;
          create table amazon_listing_snapshots(fulfillment_channel text);
          create table amazon_mf_accounts(id uuid,marketplace_id text,configured boolean);
          create table amazon_mf_offers(account_id uuid,seller_sku text,asin text,listing_state text);
          create table amazon_mf_lots(id uuid,listing_lot_id uuid);
          alter table fba_shipment_items add column seller_sku text,add column asin text;
          alter table fba_shipment_source_items add column seller_sku text,add column asin text;
        ''')
        cls.sql((ROOT/'supabase/migrations/20261120162024_mbop_fulfillment_msku_identity.sql').read_text())
        cls.sql((ROOT/'supabase/migrations/20261120170048_mbop_mf_batch_recovery.sql').read_text())

    def setUp(self):
        super().setUp()
        self.export()
        self.complete(4, sku=None)
        self.source = self.sql(f'select id from amazon_listing_allocations where batch_id={lit(self.batch)}')
        self.target = str(uuid.uuid4())
        self.payload = [{'source_allocation_id': self.source, 'quantity': 4, 'seller_sku': None, 'condition': 'new'}]
        self.evidence = {'source_url': 'https://example.com/reconciliation', 'allocations': self.payload}
        self.before = self.inventory()

    def inventory(self):
        return self.sql(f"select jsonb_agg(jsonb_build_array(id,quantity,unit_cost,source_item_id,listed_item_id,listed_at)) from amazon_merchant_inventory_lots where source_item_id={lit(self.item)}")

    def recover(self, ok=True):
        return self.sql(f"select mbop_recover_mf_listing({lit(self.target)},'2026-11-20 09:00',{js(self.payload)},'SAVED CSV',{js(self.evidence)})", ok=ok)

    def confirm(self, quantity=4, request=None, ok=True):
        allocation = self.sql(f'select id from amazon_listing_allocations where batch_id={lit(self.target)}')
        return self.sql(f"select mbop_complete_mf_listing({lit(self.target)},{lit(request or str(uuid.uuid4()))},{js([{'allocation_id': allocation, 'quantity': quantity, 'seller_sku': None}])},'2026-11-20 09:00')", ok=ok)

    def test_recovery_and_confirmation_conserve_stock_cost_and_purchase_rows(self):
        self.recover()
        self.assertEqual(self.inventory(), self.before)
        self.assertEqual(self.sql(f"select listed_quantity||':'||transferred_quantity from amazon_listing_allocations where id={lit(self.source)}"), '0:4')
        self.assertEqual(self.sql(f'select status from amazon_listing_batches where id={lit(self.batch)}'), 'recovered')
        self.assertEqual(self.sql(f'select status from amazon_listing_batches where id={lit(self.target)}'), 'exported')
        self.assertEqual(self.sql(f"select sum(quantity-transferred_quantity) from amazon_listing_allocations where batch_id in ({lit(self.batch)},{lit(self.target)})"), '4')
        request = str(uuid.uuid4())
        self.confirm(request=request)
        self.confirm(request=request)
        self.assertEqual(self.inventory(), self.before)
        self.assertEqual(self.sql(f'select quantity from purchase_items where item_id={lit(self.item)}'), '4')

    def test_idempotent_and_overlapping_recovery_rejected(self):
        self.recover()
        self.recover()
        self.target = str(uuid.uuid4())
        self.recover(ok=False)
        self.assertEqual(self.inventory(), self.before)
        self.assertEqual(self.sql(f'select count(*) from amazon_listing_batches where id={lit(self.target)}'), '0')

    def test_atomic_rollback_on_bad_second_source(self):
        self.payload.append({**self.payload[0], 'source_allocation_id': str(uuid.uuid4())})
        self.recover(ok=False)
        self.assertEqual(self.inventory(), self.before)
        self.assertEqual(self.sql(f'select transferred_quantity from amazon_listing_allocations where id={lit(self.source)}'), '0')

    def test_changed_quantity_and_registered_stock_blocked(self):
        self.payload[0]['quantity'] = 3
        self.recover(ok=False)
        self.payload[0]['quantity'] = 4
        self.sql(f"insert into amazon_mf_lots select gen_random_uuid(),id from amazon_merchant_inventory_lots where allocation_id={lit(self.source)}")
        self.recover(ok=False)
        self.assertEqual(self.inventory(), self.before)

    def test_partial_recovery_confirmation_and_original_completion_blocked(self):
        self.recover()
        self.confirm(2, ok=False)
        self.complete(1, sku=None, ok=False)
        self.assertEqual(self.inventory(), self.before)

    def test_known_fba_sku_cannot_enter_recovery(self):
        self.sql("insert into amazon_skus(seller_sku,asin,marketplace_id,fulfillment_channel) values('FBA-BAD','B07RCCHQLD','ATVPDKIKX0DER','AMAZON_NA')")
        self.payload[0]['seller_sku'] = 'FBA-BAD'
        self.recover(ok=False)
        self.assertEqual(self.inventory(), self.before)

    def test_reconciled_sku_retained_when_confirming(self):
        self.recover()
        self.sql("insert into amazon_skus(seller_sku,asin,marketplace_id,fulfillment_channel) values('MF-RECOVERED','B07RCCHQLD','ATVPDKIKX0DER','DEFAULT')")
        self.sql(f"update amazon_merchant_inventory_lots set seller_sku='MF-RECOVERED' where source_item_id={lit(self.item)}")
        self.confirm()
        self.assertEqual(self.sql(f'select seller_sku from amazon_merchant_inventory_lots where source_item_id={lit(self.item)}'), 'MF-RECOVERED')
        self.assertEqual(self.inventory(), self.before)

    def test_concurrent_recoveries_only_one_owns_stock(self):
        def attempt(target):
            sql = f"select mbop_recover_mf_listing({lit(target)},'2026-11-20 09:00',{js(self.payload)},'SAVED CSV',{js(self.evidence)})"
            return subprocess.run(DOCKER+['exec','-i',self.container,'psql','-U','postgres','-At','-v','ON_ERROR_STOP=1'], input=sql, text=True, capture_output=True).returncode
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(attempt, [self.target, str(uuid.uuid4())]))
        self.assertEqual(sorted(results), [0, 3])
        self.assertEqual(self.inventory(), self.before)

    def test_normal_partial_completion_still_splits_received_balance(self):
        self.item = str(uuid.uuid4())
        self.batch = str(uuid.uuid4())
        self.sql(f"insert into purchase_items(item_id,purchase_id,title,quantity,unit_cost,asin,current_status,marketplace,condition) values({lit(self.item)},{lit(self.purchase)},'Normal stock',4,12.34,'B07RCCHQLD','received','Amazon','new')")
        self.export()
        self.complete(2, sku=None)
        self.assertEqual(self.sql(f"select quantity||':'||current_status from purchase_items where item_id={lit(self.item)}"), '2:received')
        self.complete(2, sku=None)
        self.assertEqual(self.sql(f'select sum(quantity) from amazon_merchant_inventory_lots where source_item_id={lit(self.item)}'), '4')


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(Recovery(n) for n in Recovery.__dict__ if n.startswith('test_'))


if __name__ == '__main__':
    unittest.main()
