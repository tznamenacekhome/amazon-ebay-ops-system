"""Phase 2 schema tests against disposable, network-disabled PostgreSQL."""
import os
import subprocess
import time
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = [
    ROOT / "supabase/migrations/20261003175949_mbop_wholesale_supplier_foundation.sql",
    ROOT / "supabase/migrations/20261003181641_mbop_wholesale_matching_enrichment.sql",
]


class WholesalePhase2DatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.getenv("MBOP_WHOLESALE_DB_TESTS") != "1":
            raise unittest.SkipTest("Set MBOP_WHOLESALE_DB_TESTS=1 to run disposable PostgreSQL tests")
        cls.container = "mbop-wholesale-p2-" + uuid.uuid4().hex[:10]
        subprocess.run(["docker", "run", "--rm", "-d", "--name", cls.container,
                        "--network", "none", "-e", "POSTGRES_PASSWORD=local-test-only",
                        "postgres:17-alpine"], check=True, capture_output=True)
        cls.addClassCleanup(lambda: subprocess.run(["docker", "stop", cls.container], check=True, capture_output=True))
        for _ in range(60):
            if subprocess.run(["docker", "exec", cls.container, "pg_isready", "-U", "postgres"], capture_output=True).returncode == 0:
                break
            time.sleep(0.5)
        cls.sql("create role anon; create role authenticated; create role service_role bypassrls; grant usage on schema public to service_role;")
        for migration in MIGRATIONS:
            cls.sql(migration.read_text(encoding="utf-8"))

    @classmethod
    def sql(cls, statement):
        result = subprocess.run(["docker", "exec", "-i", cls.container, "psql", "-U", "postgres", "-qAt", "-v", "ON_ERROR_STOP=1"],
                                input=statement, text=True, encoding="utf-8", capture_output=True)
        if result.returncode:
            raise RuntimeError(result.stderr.strip())
        return result.stdout.strip()

    def setUp(self):
        self.sql("truncate wholesale_enrichment_work_items, wholesale_enrichment_runs, wholesale_match_states, wholesale_amazon_candidates, amazon_listing_eligibility_evidence, wholesale_catalog_searches, wholesale_supplier_observations, wholesale_imports, wholesale_supplier_products, wholesale_suppliers cascade;"
                 "insert into wholesale_suppliers(supplier_key,name) values('royal-electronics','Royal Electronics') returning supplier_id;")
        self.product_id = self.sql("insert into wholesale_supplier_products(supplier_id,identity_key,raw_title,raw_system,raw_identifier,normalized_identifier,identifier_type,identifier_length,identifier_status) "
                                   "select supplier_id,repeat('a',64),'Metroid Prime 4 Beyond','SW2','045496906023','045496906023','UPC',12,'valid' from wholesale_suppliers returning supplier_product_id;")

    def test_schema_and_view_compile(self):
        self.assertEqual(self.sql("select count(*) from vw_wholesale_matching_products"), "1")
        self.assertEqual(self.sql("select count(*) from pg_class where relname in ('wholesale_catalog_searches','amazon_listing_eligibility_evidence','wholesale_amazon_candidates','wholesale_match_states','wholesale_enrichment_runs','wholesale_enrichment_work_items') and relrowsecurity"), "6")

    def test_manual_override_requires_compatible_fresh_eligible_candidate(self):
        candidate_id = self.sql("insert into wholesale_amazon_candidates(supplier_product_id,marketplace_id,asin,compatibility_status,eligibility_status,eligibility_expires_at) values(" +
                                f"'{self.product_id}','ATVPDKIKX0DER','B000000001','compatible','eligible',now()+interval '1 day') returning candidate_id;")
        selected = self.sql("set role service_role; select (wholesale_set_manual_candidate(" +
                            f"'{self.product_id}','ATVPDKIKX0DER','B000000001','test')).selected_candidate_id;")
        self.assertEqual(selected, candidate_id)
        self.assertEqual(self.sql("select selection_source from wholesale_match_states"), "manual")

    def test_restricted_candidate_cannot_be_selected(self):
        self.sql("insert into wholesale_amazon_candidates(supplier_product_id,marketplace_id,asin,compatibility_status,eligibility_status,eligibility_expires_at) values(" +
                 f"'{self.product_id}','ATVPDKIKX0DER','B000000001','compatible','restricted',now()+interval '1 day');")
        with self.assertRaisesRegex(RuntimeError, "candidate_not_freshly_eligible"):
            self.sql("set role service_role; select wholesale_set_manual_candidate(" +
                     f"'{self.product_id}','ATVPDKIKX0DER','B000000001','test');")

    def test_clear_without_existing_state_creates_rematch_request(self):
        value = self.sql("set role service_role; select (wholesale_set_manual_candidate(" +
                         f"'{self.product_id}','ATVPDKIKX0DER',null,'test')).rematch_requested;")
        self.assertEqual(value, "t")
        self.assertEqual(self.sql("select match_status from wholesale_match_states"), "discovery_pending")

    def test_service_only_access_and_cache_dimensions(self):
        with self.assertRaisesRegex(RuntimeError, "permission denied"):
            self.sql("set role authenticated; select * from wholesale_amazon_candidates;")
        self.sql("insert into amazon_listing_eligibility_evidence(seller_id,marketplace_id,asin,condition_type,eligibility_status,expires_at) values('seller-a','market-a','B000000001','new_new','eligible',now()+interval '1 day');")
        self.sql("insert into amazon_listing_eligibility_evidence(seller_id,marketplace_id,asin,condition_type,eligibility_status,expires_at) values('seller-b','market-a','B000000001','new_new','restricted',now()+interval '1 day');")
        self.assertEqual(self.sql("select count(*) from amazon_listing_eligibility_evidence"), "2")


if __name__ == "__main__":
    unittest.main()
