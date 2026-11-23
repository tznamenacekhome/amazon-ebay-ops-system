"""Report worker acceptance tests against disposable PostgreSQL; Amazon is fixture-only.

Run explicitly: python tests/test_mf_returns_sync_postgres.py
The inherited harness uses postgres:17, no published port, and removes its container.
"""
import json
import os
import re
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parent))
from test_mf_returns import MFReturns
from test_mf_listing_batches import lit, js
from test_amazon_mf_returns_sync import FIXTURES, MISSING, VALID, order, boundary_refund
import amazon_sync_mf_returns as sync


def identifier(value):
    if not re.fullmatch(r'[a-z_][a-z_0-9]*', value):
        raise AssertionError(f'Invalid test SQL identifier: {value}')
    return value


def sql_value(value):
    if value is None: return 'null'
    if isinstance(value, (dict, list)): return js(value)
    return lit(value)


class PostgreSQLQuery:
    """Small PostgREST-shaped adapter over the isolated harness's docker/psql only."""
    def __init__(self, db, table):
        self.db, self.table = db, identifier(table)
        self.columns, self.filters, self.ordering = '*', [], []
        self.operation, self.values, self.maximum = 'select', None, None

    def select(self, columns):
        self.columns = '*' if columns == '*' else ','.join(identifier(c) for c in columns.split(','))
        return self
    def eq(self, key, value):
        self.filters.append(f'{identifier(key)}={sql_value(value)}')
        return self
    def neq(self, key, value):
        self.filters.append(f'{identifier(key)}<>{sql_value(value)}')
        return self
    def order(self, key, desc=False):
        self.ordering.append(f'{identifier(key)} {"desc" if desc else "asc"}')
        return self
    def limit(self, maximum):
        self.maximum = int(maximum)
        return self
    def insert(self, values):
        self.operation, self.values = 'insert', values
        return self
    def update(self, values):
        self.operation, self.values = 'update', values
        return self
    def execute(self):
        where = ' where ' + ' and '.join(self.filters) if self.filters else ''
        if self.operation == 'select':
            query = f'select {self.columns} from {self.table}{where}'
            if self.ordering: query += ' order by ' + ','.join(self.ordering)
            if self.maximum is not None: query += f' limit {self.maximum}'
        elif self.operation == 'insert':
            columns = ','.join(identifier(k) for k in self.values)
            values = ','.join(sql_value(v) for v in self.values.values())
            query = f'insert into {self.table}({columns}) values({values}) returning *'
        else:
            values = ','.join(f'{identifier(k)}={sql_value(v)}' for k, v in self.values.items())
            query = f'update {self.table} set {values}{where} returning *'
        result = self.db.sql(f"with rows as ({query}) select coalesce(jsonb_agg(to_jsonb(rows)), '[]'::jsonb) from rows;")
        return SimpleNamespace(data=json.loads(result))


class PostgreSQLDB:
    def __init__(self, sql): self.sql = sql
    def table(self, name): return PostgreSQLQuery(self, name)
    def rpc(self, name, args):
        arguments = ','.join(f'{identifier(k)}=>{sql_value(v)}' for k, v in args.items())
        def execute():
            result = self.sql(f"select coalesce(to_jsonb({identifier(name)}({arguments})), 'null'::jsonb);")
            return SimpleNamespace(data=json.loads(result))
        return SimpleNamespace(execute=execute)


@unittest.skipUnless(__name__ == '__main__' or os.environ.get('MBOP_POSTGRES_TESTS') == '1', 'Explicit disposable PostgreSQL tests')
class MFReturnSyncTransactions(MFReturns):
    __unittest_skip__ = False

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sql('create table amazon_sales_orders(amazon_order_id text,fulfillment_channel text,marketplace_id text);')
        cls.sql((Path(__file__).resolve().parents[1] / 'supabase/migrations/20261123213947_mbop_mf_return_finance_work.sql').read_text())

    def setUp(self):
        super().setUp()
        self.sql('truncate amazon_sales_orders;')
        self.db = PostgreSQLDB(self.sql)
        self.scope = {'id': self.account, 'seller_id': 'SELLER', 'marketplace_id': 'US'}
        self.client = Mock()
        self.client.create_report.side_effect = lambda *_a, **_k: {'reportId': f'REPORT-{self.report_number()}'}
        self.client.get_report.side_effect = lambda rid: {'processingStatus': 'DONE', 'reportDocumentId': rid,
                                                         'createdTime': '2026-11-23T23:50:00Z'}
        self.client.get_report_document.side_effect = lambda doc: {'url': f'https://fixture.invalid/{doc}'}
        self.client.get_order.side_effect = lambda oid: order(oid, marketplace='US')
        self.sequence = 0

    def report_number(self):
        self.sequence += 1
        return self.sequence

    def response(self, content):
        return SimpleNamespace(content=content.encode(), status_code=200, ok=True)

    def test_confirmed_fba_report_skips_without_failure_or_mf_writes(self):
        lines = (FIXTURES / 'mixed.tsv').read_text().splitlines(True)
        content = lines[0] + lines[1]
        self.sql(f"insert into amazon_sales_orders values({lit(MISSING)},'AFN','US');")
        with patch.object(sync.requests, 'get', return_value=self.response(content)), patch.object(sync.time, 'sleep'):
            imported = sync.report(self.db, self.client, self.scope, '2026-09-26T00:00:00Z', '2026-11-23T23:55:00Z')
        self.assertEqual(imported, 0)
        self.client.get_order.assert_not_called()
        self.assertEqual(self.sql("select status from amazon_mf_return_reports where report_id='REPORT-1'"), 'IMPORTED')
        self.assertEqual(self.sql('select count(*) from amazon_mf_returns'), '0')
        self.assertEqual(self.balance()['on_hand'], 1)

    def test_partial_with_no_normalized_return_is_retried_after_rollover_and_replay_is_unique(self):
        lines = (FIXTURES / 'mixed.tsv').read_text().splitlines(True)
        content = lines[0] + lines[1]
        self.client.get_order.side_effect = RuntimeError('Orders HTTP 404 NotFound')
        with patch.object(sync.requests, 'get', return_value=self.response(content)), patch.object(sync.time, 'sleep'), \
             patch.object(sync, 'now', return_value=datetime(2026, 11, 23, 23, 59, tzinfo=timezone.utc)):
            with self.assertRaisesRegex(sync.IncompleteReturnsSync, 'HTTP 404'):
                sync.report(self.db, self.client, self.scope, '2026-09-26T00:00:00Z', '2026-11-23T23:55:00Z')
        self.assertEqual(self.sql('select count(*) from amazon_mf_returns'), '0')
        partial_id = self.sql("select id from amazon_mf_return_reports where report_id='REPORT-1'")
        empty = (FIXTURES / 'empty.tsv').read_text()
        def download(url, **_): return self.response(content if url.endswith('/REPORT-1') else empty)
        with patch.object(sync.requests, 'get', side_effect=download), patch.object(sync.time, 'sleep'), \
             patch.object(sync, 'now', return_value=datetime(2026, 11, 24, 0, 5, tzinfo=timezone.utc)), \
             patch.object(sync, 'transactions', side_effect=lambda *_: iter([])), \
             patch.object(sync, 'sync_carriers', return_value=0):
            run = sync.rpc(self.db, 'mbop_mf_return_sync_begin', p_account=self.account)
            with self.assertRaisesRegex(sync.IncompleteReturnsSync, 'HTTP 404') as error:
                sync.synchronize(self.db, self.client, self.scope)
            self.assertEqual(error.exception.stats['partial_reports_retried'], 1)
            sync.rpc(self.db, 'mbop_mf_return_sync_finish', p_run=run, p_error=str(error.exception), p_stats=error.exception.stats)
            self.assertEqual(self.sql(f'select status from amazon_mf_return_sync_runs where id={lit(run)}'), 'failed')
            self.assertEqual(self.sql("select count(*) from amazon_mf_return_sync_runs where status='completed'"), '0')
            self.assertEqual(self.sql(f'select status from amazon_mf_return_reports where id={lit(partial_id)}'), 'PARTIAL')
            self.client.get_order.side_effect = lambda oid: order(oid, marketplace='US')
            successful_run = sync.rpc(self.db, 'mbop_mf_return_sync_begin', p_account=self.account)
            stats = sync.synchronize(self.db, self.client, self.scope)
            sync.rpc(self.db, 'mbop_mf_return_sync_finish', p_run=successful_run, p_error=None, p_stats=stats)
            self.assertEqual(stats['partial_reports_retried'], 1)
            self.assertEqual(self.sql(f'select status from amazon_mf_return_sync_runs where id={lit(successful_run)}'), 'completed')
            self.assertEqual(self.sql(f'select status from amazon_mf_return_reports where id={lit(partial_id)}'), 'IMPORTED')
            # Explicit replay of the same document exercises real import RPC uniqueness.
            pending = self.db.table('amazon_mf_return_reports').select('*').eq('id', partial_id).execute().data[0]
            sync.report(self.db, self.client, self.scope, pending['window_start'], pending['window_end'], pending_report=pending)
        self.assertEqual(self.sql('select count(*) from amazon_mf_returns'), '1')
        self.assertEqual(self.sql('select count(*) from amazon_mf_return_observations'), '1')
        self.assertEqual(self.sql(f'select count(*) from amazon_mf_order_items where amazon_order_id={lit(MISSING)}'), '1')
        self.assertEqual(self.balance()['on_hand'], 1)

    def finance_boundary_case(self, failure):
        source, failing = boundary_refund('US'), {'active': True}
        def request(_method, _path, params):
            return {'transactions': [source] if params['postedAfter'] <= source['postedDate'] else []}
        self.client.request.side_effect = request
        def lookup(oid):
            if failure == 'verification' and failing['active']: raise RuntimeError('Orders HTTP 404')
            return order(oid, marketplace='US')
        self.client.get_order.side_effect = lookup
        # A real SQL rejection inside the completion RPC proves the transaction
        # cannot acknowledge work when the underlying finance insert rolls back.
        if failure == 'import':
            self.sql("""create function reject_fixture_refund() returns trigger language plpgsql as $$
              begin if new.transaction_id='MF-BOUNDARY-REFUND' then raise exception 'Fixture refund import rejected';end if;return new;end $$;
              create trigger reject_fixture_refund before insert on amazon_mf_return_finances
              for each row execute function reject_fixture_refund();""")
            self.addCleanup(lambda: self.sql('drop trigger if exists reject_fixture_refund on amazon_mf_return_finances;drop function if exists reject_fixture_refund();'))
        def run_sync():
            run = sync.rpc(self.db, 'mbop_mf_return_sync_begin', p_account=self.account)
            try:
                stats = sync.synchronize(self.db, self.client, self.scope)
            except sync.IncompleteReturnsSync as error:
                sync.rpc(self.db, 'mbop_mf_return_sync_finish', p_run=run, p_error=str(error), p_stats=error.stats)
                raise
            sync.rpc(self.db, 'mbop_mf_return_sync_finish', p_run=run, p_error=None, p_stats=stats)
            return stats
        with patch.object(sync, 'report', return_value=0), patch.object(sync.time, 'sleep'), \
             patch.object(sync, 'sync_carriers', return_value=0):
            with patch.object(sync, 'now', return_value=datetime(2026, 11, 23, 23, 59, tzinfo=timezone.utc)):
                with self.assertRaises(sync.IncompleteReturnsSync): run_sync()
            self.assertEqual(self.sql('select count(*) from amazon_mf_return_finances'), '0')
            self.assertEqual(self.sql("select status from amazon_mf_return_finance_work where transaction_id='MF-BOUNDARY-REFUND'"), 'pending')
            with patch.object(sync, 'now', return_value=datetime(2026, 11, 24, 0, 5, tzinfo=timezone.utc)):
                with self.assertRaises(sync.IncompleteReturnsSync) as error: run_sync()
                self.assertEqual(error.exception.stats['finance_work_retried'], 1)
                self.assertGreater(self.client.request.call_args.kwargs['params']['postedAfter'], source['postedDate'])
                self.assertEqual(self.sql("select count(*) from amazon_mf_return_sync_runs where status='completed'"), '0')
                # Even a caller incorrectly requesting success cannot bypass pending work.
                guard_run = sync.rpc(self.db, 'mbop_mf_return_sync_begin', p_account=self.account)
                sync.rpc(self.db, 'mbop_mf_return_sync_finish', p_run=guard_run, p_error=None, p_stats={})
                self.assertEqual(self.sql(f'select status from amazon_mf_return_sync_runs where id={lit(guard_run)}'), 'failed')
                failing['active'] = False
                if failure == 'import': self.sql('drop trigger reject_fixture_refund on amazon_mf_return_finances;')
                stats = run_sync()
                self.assertEqual(stats['financial_transactions'], 1)
                self.assertEqual(self.sql("select count(*) from amazon_mf_return_sync_runs where status='completed'"), '1')
                work = self.db.table('amazon_mf_return_finance_work').select('*').eq('account_id', self.account).execute().data[0]
                self.assertEqual(work['status'], 'imported')
                # Re-enqueue/replay with a new observation simulates a repeated posting.
                sync.rpc(self.db, 'mbop_mf_return_finance_enqueue', p_account=self.account,
                         p_transaction=work['transaction_data'], p_observed=sync.now().isoformat())
                run_sync()
        self.assertEqual(self.sql('select count(*) from amazon_mf_return_finances'), '1')
        self.assertEqual(self.sql('select count(*) from vw_mf_return_finances'), '1')
        self.assertEqual(self.sql("select amount from amazon_mf_return_finances where transaction_id='MF-BOUNDARY-REFUND'"), '-20')
        self.assertEqual(self.sql('select count(*) from amazon_mf_return_finance_work'), '1')
        self.assertEqual(self.sql('select count(*) from amazon_mf_returns'), '1')
        self.assertEqual(self.balance()['on_hand'], 1)

    def test_refund_order_404_survives_lookback_boundary_and_recovers_once(self):
        self.finance_boundary_case('verification')

    def test_rejected_refund_import_survives_lookback_boundary_and_recovers_once(self):
        self.finance_boundary_case('import')


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(MFReturnSyncTransactions(name) for name in MFReturnSyncTransactions.__dict__ if name.startswith('test_'))


if __name__ == '__main__':
    unittest.main()
