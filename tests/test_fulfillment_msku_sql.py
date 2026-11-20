"""Real fulfillment guards in disposable PostgreSQL. No production access."""
import os
import subprocess
import time
import unittest
import uuid
from pathlib import Path

from test_mf_listing_batches import DOCKER

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(__name__ == "__main__" or os.environ.get("MBOP_POSTGRES_TESTS") == "1", "Explicit isolated PostgreSQL test")
class FulfillmentGuards(unittest.TestCase):
    @classmethod
    def sql(cls, query, ok=True):
        result = subprocess.run(DOCKER + ["exec", "-i", cls.container, "psql", "-U", "postgres", "-At", "-v", "ON_ERROR_STOP=1"],
                                input=query, text=True, capture_output=True)
        if ok and result.returncode:
            raise AssertionError(result.stderr)
        if not ok and result.returncode == 0:
            raise AssertionError("Expected fulfillment guard rejection")
        return result.stdout.strip()

    @classmethod
    def setUpClass(cls):
        cls.container = "mbop-sku-guard-" + uuid.uuid4().hex[:10]
        subprocess.run(DOCKER + ["run", "--rm", "-d", "--name", cls.container, "-e", "POSTGRES_PASSWORD=isolated-local-test", "postgres:17"], check=True, capture_output=True)
        cls.addClassCleanup(lambda: subprocess.run(DOCKER + ["stop", cls.container], check=True, capture_output=True))
        for _ in range(60):
            result = subprocess.run(DOCKER + ["exec", cls.container, "psql", "-U", "postgres", "-Atc", "select 1"], capture_output=True)
            if result.returncode == 0:
                time.sleep(2)
                if subprocess.run(DOCKER + ["exec", cls.container, "psql", "-U", "postgres", "-Atc", "select 1"], capture_output=True).returncode == 0:
                    break
            time.sleep(0.5)
        cls.sql("""
          create role anon; create role authenticated; create role service_role;
          create table amazon_skus(seller_sku text,marketplace_id text,asin text,fulfillment_channel text,fnsku text,raw_listing_json jsonb,updated_at timestamptz);
          create table amazon_listing_snapshots(fulfillment_channel text);
          create table amazon_listing_batches(id uuid,fulfillment_method text);
          create table amazon_listing_allocations(id uuid,batch_id uuid,snapshot jsonb);
          create table amazon_listing_completions(request_id uuid);
          create table purchase_items(item_id uuid);
          create table amazon_mf_accounts(id uuid,marketplace_id text,configured boolean);
          create table amazon_mf_offers(account_id uuid,seller_sku text,asin text,listing_state text);
          create table amazon_merchant_inventory_lots(id integer,seller_sku text,asin text);
          create table fba_shipment_items(id integer,seller_sku text,asin text);
          create table fba_shipment_source_items(id integer,seller_sku text,asin text);
          insert into amazon_skus values('MF-REPAIR','US','ASIN','Amazon','WRONG',
            '{"source":"amazon_report_ALL","row":{"fulfillment-channel":"DEFAULT"}}',now());
        """)
        cls.sql((ROOT / "supabase/migrations/20261120162024_mbop_fulfillment_msku_identity.sql").read_text())

    def setUp(self):
        self.sql("""
          truncate amazon_mf_accounts,amazon_mf_offers,amazon_merchant_inventory_lots,fba_shipment_items,fba_shipment_source_items;
          delete from amazon_skus where seller_sku<>'MF-REPAIR';
          insert into amazon_mf_accounts values('00000000-0000-0000-0000-000000000001','US',true);
          insert into amazon_skus(seller_sku,marketplace_id,asin,fulfillment_channel) values('FBA-SKU','US','ASIN','AMAZON_NA'),('MF-SKU','US','ASIN','DEFAULT');
        """)

    def test_known_opposite_methods_rejected_and_unknown_mf_deferred(self):
        self.sql("insert into amazon_merchant_inventory_lots(id,seller_sku,asin) values(1,'FBA-SKU','ASIN')", ok=False)
        self.sql("insert into fba_shipment_items(id,seller_sku,asin) values(1,'MF-SKU','ASIN')", ok=False)
        self.sql("insert into fba_shipment_source_items(id,seller_sku,asin) values(1,'MF-SKU','ASIN')", ok=False)
        self.sql("insert into amazon_merchant_inventory_lots(id,seller_sku,asin) values(1,'UNVERIFIED','ASIN')", ok=False)
        self.sql("insert into amazon_merchant_inventory_lots(id,seller_sku,asin) values(1,null,'ASIN'),(2,'MF-SKU','ASIN')")
        self.sql("insert into fba_shipment_items(id,seller_sku,asin) values(1,'FBA-SKU','ASIN')")
        self.assertEqual(self.sql("select fulfillment_method from amazon_merchant_inventory_lots where id=2"), "MF")
        self.assertEqual(self.sql("select fulfillment_method from fba_shipment_items"), "FBA")

    def test_default_repair_and_historical_context(self):
        self.assertEqual(self.sql("select fulfillment_method||':'||coalesce(fnsku,'NULL') from amazon_skus where seller_sku='MF-REPAIR'"), "MF:NULL")
        self.sql("insert into fba_shipment_items(id,seller_sku,asin) values(1,'FBA-SKU','ASIN');update amazon_skus set fulfillment_channel='DEFAULT' where seller_sku='FBA-SKU';update fba_shipment_items set seller_sku=seller_sku where id=1")
        self.assertEqual(self.sql("select fulfillment_method from fba_shipment_items"), "FBA")

    def test_export_allocations_cannot_cross_methods(self):
        self.sql("insert into amazon_listing_batches values('00000000-0000-0000-0000-000000000002','MF')")
        self.sql("insert into amazon_listing_allocations(batch_id,snapshot) values('00000000-0000-0000-0000-000000000002','{\"asin\":\"ASIN\",\"seller_sku\":\"FBA-SKU\"}')", ok=False)
        self.sql("insert into amazon_listing_allocations(batch_id,snapshot) values('00000000-0000-0000-0000-000000000002','{\"asin\":\"ASIN\",\"seller_sku\":\"MF-SKU\"}')")
        self.assertEqual(self.sql("select snapshot->>'fulfillment_method' from amazon_listing_allocations"), "MF")
        self.sql("update amazon_listing_batches set fulfillment_method='FBA'", ok=False)


if __name__ == "__main__":
    unittest.main()
