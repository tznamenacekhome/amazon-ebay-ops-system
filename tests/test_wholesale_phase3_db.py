"""Phase 3 lifecycle tests against disposable network-disabled PostgreSQL."""
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
    ROOT / "supabase/migrations/20261003183342_mbop_wholesale_opportunity_evaluation.sql",
    ROOT / "supabase/migrations/20261003213000_mbop_wholesale_phase3b_refinement.sql",
]


class WholesalePhase3DatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.getenv("MBOP_WHOLESALE_DB_TESTS") != "1":
            raise unittest.SkipTest("Set MBOP_WHOLESALE_DB_TESTS=1 to run disposable PostgreSQL tests")
        cls.container = "mbop-wholesale-p3-" + uuid.uuid4().hex[:10]
        subprocess.run(["docker", "run", "--rm", "-d", "--name", cls.container,
                        "--network", "none", "-e", "POSTGRES_PASSWORD=local-test-only", "postgres:17-alpine"],
                       check=True, capture_output=True)
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
        self.sql("truncate wholesale_product_classifications,wholesale_order_candidate_requests,wholesale_order_candidates,wholesale_decisions,wholesale_evaluations,wholesale_opportunities,wholesale_match_states,wholesale_amazon_candidates,wholesale_supplier_observations,wholesale_imports,wholesale_supplier_products,wholesale_suppliers cascade;")
        self.supplier_id = self.sql("insert into wholesale_suppliers(supplier_key,name) values('royal','Royal') returning supplier_id")
        self.import_id = self.sql("insert into wholesale_imports(supplier_id,effective_date,date_source,original_filename,file_sha256,parser_version,revision,currency,status,summary,source_rows) values(" +
                                  f"'{self.supplier_id}','2026-10-01','operator_parameter','x.xlsx',repeat('a',64),'test',1,'USD','completed','{{}}','[]') returning import_id")
        self.product_id = self.sql("insert into wholesale_supplier_products(supplier_id,identity_key,raw_title,raw_system,raw_identifier,normalized_identifier,identifier_type,identifier_length,identifier_status) values(" +
                                   f"'{self.supplier_id}',repeat('b',64),'Game','SW','012345678905','012345678905','upc_a',12,'valid') returning supplier_product_id")
        self.observation_id = self.sql("insert into wholesale_supplier_observations(supplier_product_id,supplier_id,import_id,raw_title,raw_system,raw_identifier,normalized_identifier,identifier_type,identifier_length,identifier_status,supplier_price,currency,availability_raw,availability_min,availability_is_exact,source_row_numbers) values(" +
                                       f"'{self.product_id}','{self.supplier_id}','{self.import_id}','Game','SW','012345678905','012345678905','upc_a',12,'valid',15,'USD','144+',144,false,'{{1}}') returning observation_id")
        self.candidate_id = self.sql("insert into wholesale_amazon_candidates(supplier_product_id,marketplace_id,asin,compatibility_status,eligibility_status,eligibility_expires_at) values(" +
                                     f"'{self.product_id}','US','B000000001','compatible','eligible',now()+interval '1 day') returning candidate_id")
        self.sql("insert into wholesale_match_states(supplier_product_id,marketplace_id,match_status,selected_candidate_id,selection_source) values(" +
                 f"'{self.product_id}','US','matched','{self.candidate_id}','automatic')")
        self.opportunity_id = self.sql("insert into wholesale_opportunities(supplier_product_id,marketplace_id,current_candidate_id,current_observation_id) values(" +
                                       f"'{self.product_id}','US','{self.candidate_id}','{self.observation_id}') returning opportunity_id")
        self.evaluation_id = self.sql("insert into wholesale_evaluations(opportunity_id,supplier_product_id,candidate_id,observation_id,marketplace_id,asin,evaluator_version,assumption_version,input_fingerprint,evaluation_status,eligibility_status,supplier_unit_cost,allowance_status,qualification_basis,is_financially_qualified,supplier_availability_raw,supplier_availability_min,supplier_availability_is_exact) values(" +
                                      f"'{self.opportunity_id}','{self.product_id}','{self.candidate_id}','{self.observation_id}','US','B000000001','v1','a1',repeat('c',64),'complete','eligible',15,'complete','current_only',true,'144+',144,false) returning evaluation_id")
        self.sql(f"update wholesale_opportunities set current_evaluation_id='{self.evaluation_id}',opportunity_status='ready_for_review',evaluation_requested=false where opportunity_id='{self.opportunity_id}'")

    def test_temporary_pass_and_manual_reversal(self):
        self.sql("set role service_role; select wholesale_apply_decision(" +
                 f"'{self.opportunity_id}','{self.evaluation_id}','temporary_pass','price_risk','note','tester')")
        self.assertEqual(self.sql("select opportunity_status||':'||active_decision_scope from wholesale_opportunities"), "temporarily_passed:temporary")
        self.assertEqual(self.sql("select decision_context->'list_context'->>'effective_date' from wholesale_decisions"), "2026-10-01")
        self.assertEqual(self.sql("select decision_context->'condition_snapshot'->>'supplier_price' from wholesale_decisions"), "15.0000")
        self.sql("set role service_role; select wholesale_apply_decision(" +
                 f"'{self.opportunity_id}','{self.evaluation_id}','reverse_pass',null,null,'tester')")
        self.assertEqual(self.sql("select opportunity_status from wholesale_opportunities"), "ready_for_review")
        self.assertEqual(self.sql("select count(*) from wholesale_decisions"), "2")

    def test_listing_hard_pass_is_reversible(self):
        self.sql("set role service_role; select wholesale_apply_decision(" +
                 f"'{self.opportunity_id}','{self.evaluation_id}','hard_pass','listing_asin_issue',null,'tester')")
        self.assertEqual(self.sql("select opportunity_status from wholesale_opportunities"), "hard_passed")
        self.sql("set role service_role; select wholesale_apply_decision(" +
                 f"'{self.opportunity_id}','{self.evaluation_id}','reverse_pass',null,null,'tester')")
        self.assertEqual(self.sql("select opportunity_status from wholesale_opportunities"), "ready_for_review")

    def test_restricted_is_system_state_not_manual_pass_reason(self):
        with self.assertRaisesRegex(RuntimeError, "invalid_hard_pass_reason"):
            self.sql("set role service_role; select wholesale_apply_decision(" +
                     f"'{self.opportunity_id}','{self.evaluation_id}','hard_pass','restricted_cant_sell',null,'tester')")

    def test_non_na_classification_persists_and_can_be_reversed(self):
        self.sql("set role service_role; select wholesale_set_product_classification(" +
                 f"'{self.product_id}','non_na_version',true,'{{\"region\":\"eu\"}}','tester')")
        self.assertEqual(self.sql("select classification_status from wholesale_product_classifications"), "active")
        self.sql("set role service_role; select wholesale_set_product_classification(" +
                 f"'{self.product_id}','non_na_version',false,'{{}}','tester')")
        self.assertEqual(self.sql("select classification_status from wholesale_product_classifications"), "reversed")

    def test_draft_commitment_idempotency_and_update(self):
        first = self.sql("set role service_role; select (wholesale_upsert_draft_commitment(" +
                         f"'{self.opportunity_id}','{self.evaluation_id}',7,'request-1','tester')).order_candidate_id")
        repeated = self.sql("set role service_role; select (wholesale_upsert_draft_commitment(" +
                            f"'{self.opportunity_id}','{self.evaluation_id}',7,'request-1','tester')).order_candidate_id")
        self.assertEqual(first, repeated)
        self.assertEqual(self.sql("select quantity||':'||revision from wholesale_order_candidates"), "7:1")
        self.sql("set role service_role; select wholesale_upsert_draft_commitment(" +
                 f"'{self.opportunity_id}','{self.evaluation_id}',9,'request-2','tester')")
        self.assertEqual(self.sql("select quantity||':'||revision from wholesale_order_candidates"), "9:2")
        self.assertEqual(self.sql("select count(*) from wholesale_order_candidate_requests"), "2")

    def test_144_plus_is_not_an_exact_upper_bound(self):
        self.sql("set role service_role; select wholesale_upsert_draft_commitment(" +
                 f"'{self.opportunity_id}','{self.evaluation_id}',200,'request-1','tester')")
        self.assertEqual(self.sql("select quantity from wholesale_order_candidates"), "200")

    def test_exact_availability_is_enforced(self):
        self.sql(f"update wholesale_evaluations set supplier_availability_is_exact=true,supplier_availability_min=10 where evaluation_id='{self.evaluation_id}'")
        with self.assertRaisesRegex(RuntimeError, "quantity_exceeds_exact_supplier_availability"):
            self.sql("set role service_role; select wholesale_upsert_draft_commitment(" +
                     f"'{self.opportunity_id}','{self.evaluation_id}',11,'request-1','tester')")

    def test_release_draft_restores_review_state(self):
        candidate = self.sql("set role service_role; select (wholesale_upsert_draft_commitment(" +
                             f"'{self.opportunity_id}','{self.evaluation_id}',7,'request-1','tester')).order_candidate_id")
        self.sql(f"set role service_role; select wholesale_release_draft_commitment('{candidate}','tester')")
        self.assertEqual(self.sql("select commitment_status from wholesale_order_candidates"), "released")
        self.assertEqual(self.sql("select opportunity_status from wholesale_opportunities"), "ready_for_review")

    def test_service_only_permissions(self):
        with self.assertRaisesRegex(RuntimeError, "permission denied"):
            self.sql("set role authenticated; select * from wholesale_opportunities")

    def test_manual_asin_change_requests_evaluation(self):
        other = self.sql("insert into wholesale_amazon_candidates(supplier_product_id,marketplace_id,asin,compatibility_status,eligibility_status,eligibility_expires_at) values(" +
                         f"'{self.product_id}','US','B000000002','compatible','eligible',now()+interval '1 day') returning candidate_id")
        self.sql(f"update wholesale_match_states set selected_candidate_id='{other}',selection_source='manual' where supplier_product_id='{self.product_id}'")
        self.assertEqual(self.sql("select evaluation_requested from wholesale_opportunities"), "t")


if __name__ == "__main__":
    unittest.main()
