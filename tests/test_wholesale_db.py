"""Real PostgreSQL tests, opt-in: MBOP_WHOLESALE_DB_TESTS=1. No remote database."""
import copy
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "integrations"))
from wholesale_royal import parse_workbook
from wholesale_fixtures import GAME_A, GAME_B, royal_workbook

MIGRATIONS = [
    ROOT / "supabase/migrations/20261003175949_mbop_wholesale_supplier_foundation.sql",
    ROOT / "supabase/migrations/20261004210000_mbop_wholesale_parser_replay.sql",
]


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


class WholesaleDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.getenv("MBOP_WHOLESALE_DB_TESTS") != "1":
            raise unittest.SkipTest("Set MBOP_WHOLESALE_DB_TESTS=1 to run disposable PostgreSQL tests")
        cls.container = "mbop-wholesale-test-" + uuid.uuid4().hex[:10]
        subprocess.run(["docker", "run", "--rm", "-d", "--name", cls.container,
                        "--network", "none", "-e", "POSTGRES_PASSWORD=local-test-only",
                        "postgres:17-alpine"], check=True, capture_output=True)
        cls.addClassCleanup(lambda: subprocess.run(["docker", "stop", cls.container],
                                                   check=True, capture_output=True))
        for _ in range(60):
            if subprocess.run(["docker", "exec", cls.container, "pg_isready", "-U", "postgres"],
                              capture_output=True).returncode == 0:
                break
            time.sleep(0.5)
        cls.sql("create role anon; create role authenticated; create role service_role bypassrls; "
                "grant usage on schema public to service_role;")
        for migration in MIGRATIONS:
            cls.sql(migration.read_text(encoding="utf-8"))

    @classmethod
    def sql(cls, statement):
        result = subprocess.run(["docker", "exec", "-i", cls.container, "psql", "-U", "postgres",
                                 "-qAt", "-v", "ON_ERROR_STOP=1"], input=statement, text=True,
                                encoding="utf-8", capture_output=True)
        if result.returncode:
            raise RuntimeError(result.stderr.strip())
        return result.stdout.strip()

    def setUp(self):
        # This database is created above with network=none, never a configured Supabase target.
        self.sql("truncate wholesale_supplier_observations, wholesale_imports, wholesale_supplier_products, wholesale_suppliers; "
                 "insert into wholesale_suppliers(supplier_key,name) values('royal-electronics','Royal Electronics, Inc.');")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def payload(self, rows=None, dated="2026-09-09", filename="list.xlsx"):
        path = royal_workbook(Path(self.temp.name) / filename, rows if rows is not None else [GAME_A, GAME_B])
        return parse_workbook(path, dated)

    def apply(self, payload, replaces=None):
        return json.loads(self.sql("set role service_role; select wholesale_apply_import(" +
                                  literal(json.dumps(payload)) + "::jsonb," +
                                  (literal(replaces) + "::uuid" if replaces else "null") + ");"))

    def test_repeat_import_and_persistent_supplier_product(self):
        p = self.payload()
        first = self.apply(p)
        repeated = self.apply(p)
        self.assertEqual((first["products_created"], first["observations_created"]), (2, 2))
        self.assertEqual(repeated["import_id"], first["import_id"])
        self.assertTrue(repeated["already_imported"])
        self.assertEqual((repeated["products_created"], repeated["observations_created"]), (0, 0))
        self.assertEqual(self.sql("select count(*) from wholesale_supplier_products"), "2")
        self.assertEqual(self.sql("select count(*) from wholesale_imports"), "1")
        self.assertEqual(self.sql("select raw_identifier from wholesale_supplier_products where raw_system='SW2'"), "045496906023")

    def test_three_prices_and_out_of_order_list(self):
        for dated, price, qty in (("2026-09-09", 18, "144+"), ("2026-09-23", 14, 87),
                                  ("2026-09-16", 17, "144+")):
            result = self.apply(self.payload([(*GAME_A[:3], price, qty)], dated, dated + ".xlsx"))
        self.assertEqual(result["products_matched"], 1)
        self.assertEqual(self.sql("select count(*) from wholesale_supplier_products"), "1")
        self.assertEqual(self.sql("select string_agg(supplier_price::text,',' order by effective_date) from vw_wholesale_observation_history"),
                         "18.00,17.00,14.00")
        self.assertEqual(self.sql("select latest_observation->>'supplier_price' from vw_wholesale_supplier_products"), "14.00")
        self.assertEqual(self.sql("select last_seen_date from vw_wholesale_supplier_products"), "2026-09-23")

    def test_disappearance_does_not_delete_or_deactivate(self):
        self.apply(self.payload())
        self.apply(self.payload([GAME_A], "2026-09-16", "next.xlsx"))
        self.assertEqual(self.sql("select present_in_latest_list from vw_wholesale_supplier_products where raw_system='PS5'"), "f")
        self.assertEqual(self.sql("select last_seen_date from vw_wholesale_supplier_products where raw_system='PS5'"), "2026-09-09")
        self.assertEqual(self.sql("select is_active from wholesale_supplier_products where raw_system='PS5'"), "t")
        self.assertEqual(self.sql("select count(*) from wholesale_supplier_observations"), "3")

    def test_same_date_correction_is_explicit_and_retains_history(self):
        first = self.apply(self.payload())
        changed = self.payload([(*GAME_A[:3], 16, 80)], filename="correction.xlsx")
        with self.assertRaisesRegex(RuntimeError, "correction requires"):
            self.apply(changed)
        correction = self.apply(changed, first["import_id"])
        self.assertEqual(correction["products_matched"], 1)
        self.assertEqual(self.sql("select count(*) from vw_wholesale_observation_history where is_superseded"), "2")
        self.assertEqual(self.sql("select latest_observation->>'supplier_price' from vw_wholesale_supplier_products where raw_system='SW2'"), "16.00")
        self.assertEqual(self.sql("select latest_observation is null from vw_wholesale_supplier_products where raw_system='PS5'"), "t")
        self.assertTrue(self.apply(changed, first["import_id"])["already_imported"])
        with self.assertRaisesRegex(RuntimeError, "correction requires"):
            self.apply(self.payload([GAME_B], filename="third.xlsx"), first["import_id"])

    def test_format_changes_match_and_keep_both_raw_observations(self):
        self.apply(self.payload([GAME_B]))
        variant = ("  ps5  a different game ", "ps5", "710425597527", 20, 74)
        result = self.apply(self.payload([variant], "2026-09-16", "variant.xlsx"))
        self.assertEqual(result["products_created"], 0)
        self.assertEqual(result["products_matched"], 1)
        self.assertEqual(self.sql("select raw_identifier from wholesale_supplier_products"), GAME_B[2])
        self.assertEqual(self.sql("select latest_observation->>'raw_identifier' from vw_wholesale_supplier_products"), "710425597527")

    def test_same_identity_duplicate_uses_later_price_with_audit(self):
        conflict = self.payload([GAME_A, (*GAME_A[:3], 99, 1)], "2026-09-16", "bad.xlsx")
        result = self.apply(conflict)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["observations_created"], 1)
        self.assertEqual(self.sql("select latest_observation->>'supplier_price' from vw_wholesale_supplier_products"), "99.00")
        self.assertEqual(self.sql("select source_row_numbers::text from wholesale_supplier_observations"), "{2,3}")
        self.assertEqual(self.sql("select warnings->0->>'kind' from wholesale_imports"), "duplicate_price_superseded")

    def test_same_source_can_be_replayed_once_by_new_parser_version(self):
        current = self.payload([GAME_A])
        legacy = copy.deepcopy(current)
        legacy["parser_version"] = "royal-v1"
        first = self.apply(legacy)
        replay = self.apply(current, first["import_id"])
        self.assertFalse(replay["already_imported"])
        self.assertEqual(replay["observations_created"], 1)
        self.assertEqual(self.apply(current, first["import_id"])["import_id"], replay["import_id"])

    def test_transaction_rolls_back_all_products_and_source_on_late_error(self):
        payload = self.payload()
        payload["products"][1]["supplier_price"] = "not-a-price"
        with self.assertRaises(RuntimeError):
            self.apply(payload)
        for table in ("wholesale_imports", "wholesale_supplier_products", "wholesale_supplier_observations"):
            self.assertEqual(self.sql(f"select count(*) from {table}"), "0")

    def test_concurrent_duplicate_import_is_exactly_once(self):
        payload = self.payload()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.apply(payload), range(2)))
        self.assertEqual(sum(r["observations_created"] for r in results), 2)
        self.assertEqual(sum(r["already_imported"] for r in results), 1)
        self.assertEqual(len({r["import_id"] for r in results}), 1)

    def test_service_only_permissions_and_append_only_evidence(self):
        self.apply(self.payload())
        for role in ("anon", "authenticated"):
            with self.assertRaisesRegex(RuntimeError, "permission denied"):
                self.sql(f"set role {role}; select * from vw_wholesale_supplier_products;")
            with self.assertRaisesRegex(RuntimeError, "permission denied"):
                self.sql(f"set role {role}; select wholesale_apply_import('{{}}'::jsonb);")
        for table in ("wholesale_imports", "wholesale_supplier_observations"):
            with self.assertRaisesRegex(RuntimeError, "permission denied"):
                self.sql(f"set role service_role; delete from {table};")
        self.assertEqual(self.sql("select count(*) from pg_class where relname like 'wholesale_%' and relkind='r' and relrowsecurity"), "4")

    def test_supplier_scoped_identity_and_currency(self):
        p = self.payload([GAME_A])
        self.apply(p)
        self.sql("insert into wholesale_suppliers(supplier_key,name) values('other','Other Supplier');")
        other = copy.deepcopy(p)
        other["supplier_key"] = "other"
        other["currency"] = other["products"][0]["currency"] = "CAD"
        self.apply(other)
        self.assertEqual(self.sql("select count(*) from wholesale_supplier_products"), "2")
        self.assertEqual(self.sql("select string_agg(distinct currency,',' order by currency) from wholesale_supplier_observations"), "CAD,USD")

    def test_real_workbook_when_supplied(self):
        source = os.getenv("MBOP_ROYAL_WORKBOOK")
        if not source:
            self.skipTest("Optional real workbook not supplied")
        p = parse_workbook(source, "2026-09-09")
        first, repeat = self.apply(p), self.apply(p)
        self.assertEqual(first["observations_created"], p["summary"]["products_accepted"])
        self.assertEqual(repeat["observations_created"], 0)
        self.assertEqual(self.sql("select count(*) from wholesale_supplier_products where raw_title ~* '\\mUSED\\M'"), "0")
        stats = json.loads(self.sql("select jsonb_build_object('leading_zero_identifiers',count(*) filter(where raw_identifier like '0%'),"
                                   "'at_least_quantities',count(*) filter(where availability_is_exact=false),"
                                   "'exact_quantities',count(*) filter(where availability_is_exact=true)) from wholesale_supplier_observations"))
        evidence = {"summary": p["summary"], "system_counts": p["system_counts"], "first_import": first,
                    "repeat_import": repeat, "database_checks": stats,
                    "identifier_warnings": [{"raw_identifier": x["raw_identifier"], "status": x["identifier_status"]}
                                            for x in p["products"] if x["identifier_status"] != "valid"]}
        target = ROOT / "tmp/wholesale-phase1/database-verification.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print("Real workbook local database:", json.dumps(stats))


if __name__ == "__main__":
    unittest.main()
