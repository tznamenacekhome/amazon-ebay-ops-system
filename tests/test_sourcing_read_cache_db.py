"""Run explicitly: python tests/test_sourcing_read_cache_db.py (Docker required)."""
import json
import re
import subprocess
import time
from pathlib import Path


def main():
    name = "mbop-read-cache-regression"
    migration = Path("supabase/migrations/20260914193000_mbop_sourcing_read_cache.sql").read_text(encoding="utf-8")
    subprocess.run(["docker", "run", "--rm", "-d", "--name", name, "--network", "none", "-e", "POSTGRES_PASSWORD=local-test-only", "postgres:17-alpine"], check=True, capture_output=True)
    command = ["docker", "exec", "-i", name, "psql", "-U", "postgres", "-qAt", "-v", "ON_ERROR_STOP=1"]
    def sql(value):
        return subprocess.run(command, input=value, text=True, encoding="utf-8", capture_output=True, check=True).stdout.strip()
    try:
        for _ in range(40):
            if subprocess.run(["docker", "exec", name, "pg_isready", "-U", "postgres"], capture_output=True).returncode == 0:
                break
            time.sleep(0.25)
        tables = re.findall(r"after insert or update or delete or truncate on public\.(\w+)", migration)
        sql("create role anon; create role authenticated; create role service_role;" + "".join(f"create table public.{table}(id integer primary key, matching_diagnostics_json jsonb,status text,completed_at timestamptz);" for table in tables))
        sql(migration)
        sql("create view public.vw_latest_keepa_product_snapshot as select id,matching_diagnostics_json as raw_keepa_json from public.keepa_product_snapshots;")
        sql(Path("supabase/migrations/20260914193100_mbop_sourcing_keepa_offer_presence.sql").read_text(encoding="utf-8"))
        assert sql("select public.sourcing_keepa_has_offers(row(1,'{\"offers\":[null]}'::jsonb)::public.vw_latest_keepa_product_snapshot);") == "t"
        assert sql("select public.sourcing_keepa_has_offers(row(1,'{\"offers\":[]}'::jsonb)::public.vw_latest_keepa_product_snapshot);") == "f"
        assert sql("select public.sourcing_keepa_has_offers(row(1,'{}'::jsonb)::public.vw_latest_keepa_product_snapshot);") == "f"
        print(sql(Path("tests/sql/sourcing_read_cache.sql").read_text(encoding="utf-8")))
        before = json.loads(sql("select public.sourcing_cache_version();"))["revision"]
        # Opposite source-table order must not introduce a shared-counter deadlock.
        processes = []
        for first, second, item in [("sourcing_opportunities", "sourcing_actions", 10), ("sourcing_actions", "sourcing_opportunities", 20)]:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
            process.stdin.write(f"begin; insert into public.{first}(id) values({item}); select pg_sleep(1); insert into public.{second}(id) values({item}); select pg_sleep(1); commit;")
            process.stdin.close()
            processes.append(process)
        time.sleep(0.4)
        start = time.monotonic()
        during = json.loads(sql("select public.sourcing_cache_version();"))["revision"]
        assert time.monotonic() - start < 1, "Freshness read blocked on an operational writer"
        assert during == before, "Uncommitted source write became visible"
        for process in processes:
            process.wait(timeout=10)
            assert process.returncode == 0, process.stderr.read()
        after = json.loads(sql("select public.sourcing_cache_version();"))["revision"]
        assert after > before
        assert json.loads(sql("select public.sourcing_cache_version();"))["revision"] == after
        print("PASS: concurrent inverse-order writers; nonblocking reader; commit visibility; stable version")
    finally:
        subprocess.run(["docker", "stop", name], check=True, capture_output=True)


if __name__ == "__main__":
    main()
