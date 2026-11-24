"""Explicit disposable PostgreSQL acceptance tests. No production connections or published ports."""
import json
import os
import subprocess
import time
import unittest
import uuid
from pathlib import Path
from test_mf_listing_batches import DOCKER, lit, js

ROOT = Path(__file__).resolve().parents[1]

@unittest.skipUnless(__name__ == '__main__' or os.environ.get('MBOP_POSTGRES_TESTS') == '1', 'Run explicitly with Docker')
class FlipmineTransactions(unittest.TestCase):
    @classmethod
    def sql(cls, query, ok=True):
        result = subprocess.run(DOCKER + ['exec', '-i', cls.container, 'psql', '-U', 'postgres', '-At', '-v', 'ON_ERROR_STOP=1'], input=query, text=True, capture_output=True)
        if ok and result.returncode: raise AssertionError(result.stderr)
        if not ok and not result.returncode: raise AssertionError('Expected rejection: ' + query)
        return result.stdout.strip()

    @classmethod
    def setUpClass(cls):
        cls.container = 'mbop-flipmine-test-' + uuid.uuid4().hex[:10]
        subprocess.run(DOCKER + ['run', '--rm', '-d', '--name', cls.container, '-e', 'POSTGRES_PASSWORD=isolated-test', 'postgres:17'], check=True, capture_output=True)
        cls.addClassCleanup(lambda: subprocess.run(DOCKER + ['stop', cls.container], check=True, capture_output=True))
        for _ in range(120):
            if subprocess.run(DOCKER + ['exec', cls.container, 'pg_isready', '-h', '127.0.0.1', '-U', 'postgres'], capture_output=True).returncode == 0: break
            time.sleep(.25)
        cls.sql((ROOT / 'tests/fixtures/sourcing_review_schema.sql').read_text())
        cls.sql("create table sourcing_runs(sourcing_run_id uuid primary key,run_type text constraint sourcing_runs_run_type_check check(run_type in ('recent_sales','full_listings','daily_catalog_sourcing')),status text,completed_at timestamptz);")
        cls.sql((ROOT / 'supabase/migrations/20261124022809_mbop_flipmine_sourcing_import.sql').read_text())
        cls.sql((ROOT / 'supabase/migrations/20261124033839_mbop_ebay_quota_and_flipmine_recovery.sql').read_text())

    def setUp(self):
        self.sql('truncate ebay_api_resource_limits,ebay_api_usage,ebay_listing_detail_cache,sourcing_flipmine_rows,sourcing_flipmine_tabs,sourcing_flipmine_runs,sourcing_opportunities,sourcing_ebay_candidates,sourcing_seed_asins,sourcing_runs cascade;')
        self.run = str(uuid.uuid4())
        self.begin(self.run)
        self.tab = self.claim(self.run)
        self.snapshot([self.row(2), self.row(3)])

    def begin(self, run): return json.loads(self.sql(f'select flipmine_begin({lit(run)});'))
    def claim(self, run, sheet=0): return json.loads(self.sql(f"select flipmine_claim_tab({lit(run)},'fixture-sheet',{sheet},'Export');") or 'null')
    def row(self, number, asin='B000000001'): return dict(row_number=number, asin=asin, ebay_legacy_item_id='123456789012', status='pending', source_evidence={'amazon title': 'untrusted'})
    def snapshot(self, rows): self.sql(f"select flipmine_snapshot_tab({lit(self.run)},{lit(self.tab['tab_id'])},'hash',{js(rows)});")
    def bind(self, number=2, asin='B000000001'):
        seed = str(uuid.uuid4())
        self.sql(f"insert into sourcing_seed_asins(seed_id,source_mode,asin,sourcing_run_id) values({lit(seed)},'flipmine',{lit(asin)},{lit(self.tab['sourcing_run_id'])});")
        candidate = dict(candidate_id=str(uuid.uuid4()), asin=asin, ebay_item_id='v1|123456789012|0', ebay_legacy_item_id='123456789012', ebay_title='Fresh title', seed_id=seed, sourcing_run_id=self.tab['sourcing_run_id'])
        result = json.loads(self.sql(f"select flipmine_bind_candidate({lit(self.run)},{lit(self.tab['tab_id'])},{number},{js(candidate)});"))
        return result
    def write(self, candidate, number=2):
        scored = {key: candidate[key] for key in ['candidate_id','seed_id','sourcing_run_id','asin','ebay_item_id']}
        scored.update(status='open', opportunity_type='buy', matching_diagnostics_json={'hard_rule_pass': True}, score=75)
        return self.sql(f"select flipmine_write_opportunity({lit(self.run)},{lit(self.tab['tab_id'])},{number},{js(scored)});")
    def finish(self): return json.loads(self.sql(f"select flipmine_tab_evaluated({lit(self.run)},{lit(self.tab['tab_id'])});"))

    def test_duplicate_pair_replay_and_existing_status_preserved(self):
        candidate = self.bind()['candidate']; oid = self.write(candidate)
        self.sql(f"update sourcing_opportunities set status='dismissed' where opportunity_id={lit(oid)};")
        bound = self.bind(3)
        self.assertTrue(bound['duplicate'])
        self.write(candidate)
        self.assertEqual(self.sql('select count(*) from sourcing_opportunities'), '1')
        self.assertEqual(self.sql('select status from sourcing_opportunities'), 'dismissed')
        self.assertEqual(self.sql('select source_tags::text from sourcing_ebay_candidates'), '{flipmine}')

    def test_competing_asins_keep_separate_candidates(self):
        self.sql("update sourcing_flipmine_rows set asin='B000000002' where row_number=3;")
        self.write(self.bind()['candidate']); self.write(self.bind(3, 'B000000002')['candidate'], 3)
        self.assertEqual(self.sql('select count(*) from sourcing_ebay_candidates'), '2')
        self.assertEqual(self.sql('select count(*) from sourcing_opportunities'), '2')

    def test_partial_retry_stable_tab_snapshot_and_duplicate_free(self):
        self.write(self.bind()['candidate'])
        self.sql(f"select flipmine_update_row({lit(self.run)},{lit(self.tab['tab_id'])},3,'{{\"status\":\"failed\",\"error\":\"provider unavailable\"}}');")
        self.assertEqual(self.finish()['failed'], 1)
        self.sql(f"update sourcing_flipmine_runs set status='partial' where run_id={lit(self.run)};")
        self.run = str(uuid.uuid4()); self.begin(self.run)
        tab = self.claim(self.run); self.assertEqual(tab['tab_id'], self.tab['tab_id'])
        self.snapshot([])  # Original immutable snapshot survives changed source contents.
        self.assertEqual(self.sql('select count(*) from sourcing_flipmine_rows'), '2')
        self.assertTrue(self.bind(3)['duplicate'])
        self.assertEqual(self.finish()['failed'], 0)
        self.sql(f"select flipmine_complete_tab({lit(tab['tab_id'])},'{{\"buyList\":1,\"closestExcluded\":0}}');")
        self.assertEqual(self.sql('select count(*) from sourcing_opportunities'), '1')
        self.assertEqual(self.sql('select status from sourcing_flipmine_tabs'), 'completed')
        self.assertIsNone(self.claim(self.run))

    def test_pending_work_cannot_complete(self):
        self.assertEqual(self.finish()['failed'], 2)
        self.sql(f"select flipmine_complete_tab({lit(self.tab['tab_id'])},'{{}}');")
        self.assertEqual(self.sql('select status from sourcing_flipmine_tabs'), 'partial')

    def test_failed_opportunity_write_does_not_acknowledge_row(self):
        candidate=self.bind()['candidate']
        scored={key:candidate[key] for key in ['candidate_id','seed_id','sourcing_run_id','asin','ebay_item_id']}
        scored.update(status='open',opportunity_type=None,matching_diagnostics_json={'hard_rule_pass':True})
        self.sql(f"select flipmine_write_opportunity({lit(self.run)},{lit(self.tab['tab_id'])},2,{js(scored)});",ok=False)
        self.assertEqual(self.sql('select count(*) from sourcing_opportunities'),'0')
        self.assertEqual(self.sql('select status from sourcing_flipmine_rows where row_number=2'),'pending')

    def test_concurrent_launch_and_expired_worker_fencing(self):
        other = str(uuid.uuid4()); self.assertFalse(self.begin(other)['launch'])
        self.sql("update sourcing_flipmine_runs set heartbeat_at=now()-interval '91 minutes';")
        self.assertTrue(self.begin(other)['launch'])
        self.sql(f"select flipmine_update_row({lit(self.run)},{lit(self.tab['tab_id'])},2,'{{\"status\":\"excluded\"}}');", ok=False)
        self.assertEqual(self.sql('select status from sourcing_flipmine_tabs'), 'partial')

    def test_header_only_empty_tab_and_new_numeric_tab(self):
        tab = self.claim(self.run, 19)
        self.sql(f"select flipmine_snapshot_tab({lit(self.run)},{lit(tab['tab_id'])},'empty','[]');")
        summary = json.loads(self.sql(f"select flipmine_tab_evaluated({lit(self.run)},{lit(tab['tab_id'])});"))
        self.assertEqual(summary['rows'], 0)
        self.sql(f"select flipmine_complete_tab({lit(tab['tab_id'])},'{{\"buyList\":0,\"closestExcluded\":0}}');")
        self.assertIsNone(self.claim(self.run, 19))

    def test_private_audit_tables_and_service_only_functions(self):
        self.assertEqual(self.sql("select has_table_privilege('anon','sourcing_flipmine_rows','SELECT')"), 'f')
        self.assertEqual(self.sql("select has_function_privilege('authenticated','flipmine_begin(uuid)','EXECUTE')"), 'f')
        self.assertEqual(self.sql("select has_function_privilege('service_role','flipmine_begin(uuid)','EXECUTE')"), 't')
        self.assertEqual(self.sql("select has_table_privilege('anon','ebay_listing_detail_cache','SELECT')"),'f')
        self.assertEqual(self.sql("select has_function_privilege('authenticated','ebay_quota_reserve(text,text,text,boolean)','EXECUTE')"),'f')

    def test_daily_quota_atomic_reservation_and_same_window_observation(self):
        rate=dict(limit=5000,count=4999,remaining=1,reset='2099-01-01T08:00:00Z',timeWindow=86400)
        self.sql(f"select ebay_quota_observe('app','buy.browse',{js(rate)});")
        self.assertTrue(json.loads(self.sql("select ebay_quota_reserve('app','buy.browse','import_flipmine.py',true);"))['allowed'])
        self.assertEqual(self.sql('select remaining from ebay_api_resource_limits'),'1','Preflight must not spend a listing call')
        self.assertTrue(json.loads(self.sql("select ebay_quota_reserve('app','buy.browse','import_flipmine.py');"))['allowed'])
        self.assertFalse(json.loads(self.sql("select ebay_quota_reserve('app','buy.browse','job-b');"))['allowed'])
        self.sql(f"select ebay_quota_observe('app','buy.browse',{js(rate)});")
        self.assertEqual(self.sql('select remaining from ebay_api_resource_limits'),'0','Lagging analytics must not refill spent reservations')
        self.assertEqual(self.sql('select sum(attempts) from ebay_api_usage'),'1')

    def test_paused_checkpoint_no_new_job_and_due_claim_once(self):
        self.write(self.bind()['candidate'])
        self.sql(f"select flipmine_pause({lit(self.run)},now()+interval '1 hour','buy.browse','daily quota');")
        self.assertFalse(self.begin(str(uuid.uuid4()))['launch'])
        self.assertEqual(self.sql('select flipmine_claim_resume();'),'')
        self.sql("update sourcing_flipmine_runs set next_retry_at=now()-interval '1 second';")
        self.assertEqual(self.sql('select flipmine_claim_resume();'),self.run)
        self.assertEqual(self.sql('select flipmine_claim_resume();'),'')
        self.assertEqual(self.claim(self.run)['tab_id'],self.tab['tab_id'])
        self.assertTrue(self.bind(3)['duplicate'])
        self.assertEqual(self.sql('select count(*) from sourcing_opportunities'),'1')
        self.assertEqual(self.sql('select count(*) from sourcing_flipmine_rows'),'2')

    def test_expired_daily_window_requires_refresh_before_new_call(self):
        self.sql("insert into ebay_api_resource_limits(app_key,resource,remaining,reset_at,observed_at) values('app','buy.browse',0,now()-interval '1 second',now());")
        self.assertTrue(json.loads(self.sql("select ebay_quota_reserve('app','buy.browse','test');"))['refresh'])
        self.assertFalse(json.loads(self.sql("select ebay_quota_reserve('app','buy.browse','other');"))['allowed'])

    def test_normal_jobs_cannot_starve_saved_import_at_reset(self):
        rate=dict(limit=5000,count=4999,remaining=1,reset='2099-01-01T08:00:00Z',timeWindow=86400)
        self.sql(f"select ebay_quota_observe('app','buy.browse',{js(rate)});")
        state=json.loads(self.sql("select ebay_quota_reserve('app','buy.browse','ebay_sourcing_search.py');"))
        self.assertFalse(state['allowed']);self.assertEqual(state['reason'],'capacity_reserved_for_saved_import')
        self.assertTrue(json.loads(self.sql("select ebay_quota_reserve('app','buy.browse','import_flipmine.py');"))['allowed'])

    def test_two_jobs_cannot_spend_the_same_remaining_call(self):
        from concurrent.futures import ThreadPoolExecutor
        self.sql("update sourcing_flipmine_runs set status='completed';")
        rate=dict(limit=5000,count=4999,remaining=1,reset='2099-01-01T08:00:00Z',timeWindow=86400)
        self.sql(f"select ebay_quota_observe('app','buy.browse',{js(rate)});")
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda name:json.loads(self.sql(f"select ebay_quota_reserve('app','buy.browse',{lit(name)});")),['job-a','job-b']))
        self.assertEqual(sum(bool(r.get('allowed')) for r in results),1)

if __name__ == '__main__': unittest.main()
