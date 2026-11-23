"""Offline report-to-order regression checks. No credentials, network or real returns."""
import copy
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations'))
import amazon_sync_mf_returns as sync
from amazon_mf_returns import explicitly_fba_transaction

FIXTURES = Path(__file__).parent / 'fixtures' / 'mf_returns'
ACCOUNT = {'id': 'ACCOUNT', 'marketplace_id': 'ATVPDKIKX0DER', 'seller_id': 'SELLER'}
MISSING, VALID = '123-1234567-1234567', '123-7654321-7654321'


class Query:
    def __init__(self, db, table):
        self.db, self.table, self.filters = db, table, []
        self.operation, self.values, self.exclusions, self.orders, self.maximum = 'select', None, [], [], None

    def select(self, *_): return self
    def order(self, column, desc=False):
        self.orders.append((column, desc))
        return self
    def limit(self, count):
        self.maximum = count
        return self
    def single(self):
        self.one = True
        return self
    def eq(self, key, value):
        self.filters.append((key, value))
        return self
    def neq(self, column, value):
        self.exclusions.append((column, value))
        return self
    def insert(self, values):
        self.operation, self.values = 'insert', values
        return self
    def update(self, values):
        self.operation, self.values = 'update', values
        return self
    def execute(self):
        rows = self.db.tables.setdefault(self.table, [])
        if self.operation == 'insert':
            row = {'id': f'REPORT-{len(rows)}', 'requested_at': sync.now().isoformat(), **copy.deepcopy(self.values)}
            rows.append(row)
            return SimpleNamespace(data=[copy.deepcopy(row)])
        selected = [r for r in rows if all(r.get(k) == v for k, v in self.filters) and
                    all(r.get(k) != v for k, v in self.exclusions)]
        for key, desc in reversed(self.orders):
            selected.sort(key=lambda row: row.get(key) or '', reverse=desc)
        if self.maximum is not None:
            selected = selected[:self.maximum]
        if self.operation == 'update':
            for row in selected: row.update(copy.deepcopy(self.values))
        return SimpleNamespace(data=copy.deepcopy(selected[0] if getattr(self, 'one', False) else selected))


class MemoryDB:
    def __init__(self):
        self.tables, self.returns, self.observations, self.finances = {}, {}, set(), {}
    def table(self, name): return Query(self, name)
    def apply(self, db, name, **args):
        if name == 'mbop_mf_apply_order':
            item = args['p_item']
            rows = self.tables.setdefault('amazon_mf_order_items', [])
            if not any(r['amazon_order_item_id'] == item['amazon_order_item_id'] for r in rows):
                rows.append({'id': 'ORDER-ITEM', 'account_id': args['p_account'], **item})
        elif name == 'mbop_mf_return_import':
            # Model the migration's account/source_key and observation uniqueness contracts.
            line = args['p_line']
            self.returns[(args['p_account'], line['source_key'])] = copy.deepcopy(line)
            self.observations.add((args['p_account'], args['p_report'], line['source_key']))
        elif name == 'mbop_mf_return_finance_enqueue':
            data = args['p_transaction']
            rows = self.tables.setdefault('amazon_mf_return_finance_work', [])
            row = next((r for r in rows if r['account_id'] == args['p_account'] and r['transaction_id'] == data['transaction_id']), None)
            if row is None:
                row = {'account_id': args['p_account'], 'transaction_id': data['transaction_id'], 'created_at': sync.now().isoformat()}
                rows.append(row)
            if 'observed_at' not in row or args['p_observed'] > row['observed_at']:
                row.update(transaction_data=copy.deepcopy(data), observed_at=args['p_observed'], status='pending', error=None)
            return copy.deepcopy(row)
        elif name == 'mbop_mf_return_finance_complete_work':
            row = next(r for r in self.tables['amazon_mf_return_finance_work'] if
                       r['account_id'] == args['p_account'] and r['transaction_id'] == args['p_transaction_id'])
            if row['status'] != 'pending': return False
            if row['observed_at'] != args['p_observed']: raise ValueError('Work observation changed')
            if args['p_resolution'] == 'imported':
                self.finances[(row['account_id'], row['transaction_id'])] = copy.deepcopy(row['transaction_data'])
            row.update(status=args['p_resolution'], error=None)
            return True
        else:
            raise AssertionError(f'Unexpected RPC: {name}')


def order(oid=VALID, marketplace=ACCOUNT['marketplace_id']):
    return {'orderId': oid, 'salesChannel': {'marketplaceId': marketplace},
            'fulfillment': {'fulfilledBy': 'MERCHANT', 'fulfillmentStatus': 'SHIPPED'},
            'createdTime': '2026-10-01T00:00:00Z', 'lastUpdatedTime': '2026-10-02T00:00:00Z',
            'orderItems': [{'orderItemId': 'ITEM-VALID' if oid == VALID else 'ITEM-MISSING', 'quantityOrdered': 1,
                            'fulfillment': {'quantityFulfilled': 1},
                            'product': {'sellerSku': 'MF-VALID', 'asin': 'B000000001'}}]}


def boundary_refund(marketplace=ACCOUNT['marketplace_id']):
    return {'transactionId': 'MF-BOUNDARY-REFUND', 'transactionType': 'Refund', 'transactionStatus': 'RELEASED',
            'postedDate': '2026-09-26T12:00:00Z', 'marketplaceDetails': {'marketplaceId': marketplace},
            'relatedIdentifiers': [{'relatedIdentifierName': 'ORDER_ID', 'relatedIdentifierValue': VALID}],
            'totalAmount': {'currencyAmount': -20, 'currencyCode': 'USD'},
            'items': [{'contexts': [{'contextType': 'ProductContext', 'fulfillmentNetwork': 'MFN'}]}]}


class SyncRegression(unittest.TestCase):
    def setUp(self):
        self.db, self.client = MemoryDB(), Mock()
        self.client.create_report.return_value = {'reportId': 'AMAZON-REPORT'}
        self.client.get_report.return_value = {'processingStatus': 'DONE', 'reportDocumentId': 'DOC'}
        self.client.get_report_document.return_value = {'url': 'https://fixture.invalid/report'}
        self.client.get_order.return_value = order()

    def run_report(self, content):
        response = SimpleNamespace(content=content.encode(), ok=True, status_code=200)
        with patch.object(sync.requests, 'get', return_value=response), \
             patch.object(sync, 'rpc', side_effect=self.db.apply), patch.object(sync.time, 'sleep'):
            pending = next((r for r in self.db.tables.get('amazon_mf_return_reports', []) if r['status'] == 'PARTIAL'), None)
            return sync.report(self.db, self.client, ACCOUNT, '2026-10-01T00:00:00Z', '2026-11-23T00:00:00Z', pending_report=pending)

    def test_valid_empty_report_does_not_lookup_orders(self):
        with self.assertLogs(sync.LOG, level='INFO') as logs:
            self.assertEqual(self.run_report((FIXTURES / 'empty.tsv').read_text()), 0)
        self.client.get_order.assert_not_called()
        self.assertEqual(self.db.tables['amazon_mf_return_reports'][0]['status'], 'IMPORTED')
        self.assertIn('full returns sync not yet complete', ' '.join(logs.output))
        self.assertFalse(self.db.returns)

    def test_blank_document_is_not_a_valid_empty_report(self):
        with self.assertRaisesRegex(ValueError, 'headers missing'):
            self.run_report('')
        self.assertNotEqual(self.db.tables['amazon_mf_return_reports'][0]['status'], 'IMPORTED')

    def test_normal_mf_return_verifies_order_and_imports(self):
        lines = (FIXTURES / 'mixed.tsv').read_text().splitlines(True)
        self.assertEqual(self.run_report(lines[0] + lines[2]), 1)
        self.client.get_order.assert_called_once_with(VALID)
        self.assertEqual(len(self.db.returns), 1)
        self.assertEqual(next(iter(self.db.returns.values()))['seller_sku'], 'MF-VALID')

    def test_mixed_404_retains_original_report_processes_other_rows_and_retries_without_duplicates(self):
        content = (FIXTURES / 'mixed.tsv').read_text()
        def lookup(oid):
            if oid == MISSING: raise RuntimeError('Orders single-order HTTP 404 NotFound')
            return order(oid)
        self.client.get_order.side_effect = lookup
        for _ in range(2):
            with self.assertRaisesRegex(sync.IncompleteReturnsSync, 'HTTP 404') as raised:
                self.run_report(content)
            self.assertEqual(raised.exception.stats['returns'], 1)
            row = self.db.tables['amazon_mf_return_reports'][0]
            self.assertEqual(row['status'], 'PARTIAL')
            self.assertIsNone(row['imported_at'])
            self.assertIn(MISSING, row['error'])
        self.assertEqual(len(self.db.returns), 1)
        self.assertEqual(len(self.db.observations), 1)
        self.client.create_report.assert_called_once()
        self.client.get_order.side_effect = lambda oid: order(oid)
        self.assertEqual(self.run_report(content), 2)
        self.assertEqual(len(self.db.returns), 2)
        self.assertEqual(self.db.tables['amazon_mf_return_reports'][0]['status'], 'IMPORTED')

    def test_unknown_or_wrong_marketplace_is_not_imported(self):
        lines = (FIXTURES / 'mixed.tsv').read_text().splitlines(True)
        self.client.get_order.return_value = order(marketplace='OTHER')
        with self.assertRaisesRegex(sync.IncompleteReturnsSync, 'marketplace mismatch'):
            self.run_report(lines[0] + lines[2])
        self.assertFalse(self.db.returns)

    def test_missing_fulfillment_or_merchant_items_is_not_successful_empty(self):
        for field, replacement in (('fulfillment', {}), ('orderItems', [])):
            with self.subTest(field=field):
                self.client.get_order.return_value = {**order(), field: replacement}
                with self.assertRaisesRegex(ValueError, 'scope|no verified MF items'):
                    sync.verify_order(self.db, self.client, ACCOUNT, VALID)

    def test_explicit_fba_refund_is_excluded_before_orders_lookup(self):
        # Shape of the recurring Nov 9 refund, with synthetic financial identities.
        transaction = {'transactionId': 'FBA-REFUND', 'transactionType': 'Refund',
                       'marketplaceDetails': {'marketplaceId': ACCOUNT['marketplace_id']},
                       'relatedIdentifiers': [{'relatedIdentifierName': 'ORDER_ID', 'relatedIdentifierValue': MISSING}],
                       'items': [{'contexts': [{'contextType': 'ProductContext', 'fulfillmentNetwork': 'AFN'}]}]}
        with patch.object(sync, 'report', return_value=0), \
             patch.object(sync, 'transactions', return_value=iter([transaction])), \
             patch.object(sync, 'sync_carriers', return_value=0), patch.object(sync, 'rpc') as rpc:
            stats = sync.synchronize(self.db, self.client, ACCOUNT)
        self.assertEqual(stats['fba_financial_transactions_skipped'], 1)
        self.assertEqual(stats['financial_transactions'], 0)
        self.client.get_order.assert_not_called()
        rpc.assert_not_called()
        self.assertTrue(explicitly_fba_transaction(transaction))
        for context in ([], [{'contextType': 'ProductContext', 'fulfillmentNetwork': 'UNKNOWN'}],
                        [{'contextType': 'ProductContext', 'fulfillmentNetwork': 'MFN'}]):
            changed = copy.deepcopy(transaction)
            changed['items'].append({'contexts': context})
            self.assertFalse(explicitly_fba_transaction(changed))

    def test_systemic_api_failure_cannot_be_successful_empty(self):
        stats = {}
        def broken(*_):
            raise RuntimeError('HTTP 403 AccessDenied')
            yield  # generator failure occurs during iteration
        with patch.object(sync, 'report', return_value=0), patch.object(sync, 'transactions', side_effect=broken):
            with self.assertRaisesRegex(RuntimeError, 'HTTP 403'):
                sync.synchronize(self.db, self.client, ACCOUNT, stats=stats)
        self.assertEqual(stats['reports_imported'], 1)
        self.assertFalse(self.db.returns)

    def run_main(self, content, finance_error=None):
        self.db.tables['amazon_mf_accounts'] = [{**ACCOUNT, 'configured': True}]
        self.client.config = SimpleNamespace(seller_id=ACCOUNT['seller_id'], marketplace_id=ACCOUNT['marketplace_id'])
        finished = []
        def apply(db, name, **args):
            if name == 'mbop_mf_return_sync_begin': return 'RUN'
            if name == 'mbop_mf_return_sync_finish':
                finished.append(copy.deepcopy(args))
                return
            return self.db.apply(db, name, **args)
        def finance(*_):
            if finance_error: raise RuntimeError(finance_error)
            yield from []
        with patch.object(sync, 'load_dotenv'), \
             patch.dict(sync.os.environ, SUPABASE_URL='https://fixture.invalid', SUPABASE_SERVICE_ROLE_KEY='fixture'), \
             patch.object(sync, 'create_client', return_value=self.db), \
             patch.object(sync, 'wait_for_database'), \
             patch.object(sync.AmazonSPAPIClient, 'from_env', return_value=self.client), \
             patch.object(sync.requests, 'get', return_value=SimpleNamespace(content=content.encode(), ok=True, status_code=200)), \
             patch.object(sync, 'rpc', side_effect=apply), patch.object(sync, 'transactions', side_effect=finance), \
             patch.object(sync, 'sync_carriers', return_value=0), patch.object(sync.time, 'sleep'):
            code = sync.main()
        return code, finished[0]

    def test_valid_empty_report_completes_full_run(self):
        code, finished = self.run_main((FIXTURES / 'empty.tsv').read_text())
        self.assertEqual(code, 0)
        self.assertIsNone(finished['p_error'])
        self.assertEqual(finished['p_stats']['reports_imported'], 1)
        self.assertEqual(finished['p_stats']['returns'], 0)

    def test_partial_report_does_not_advance_successful_checkpoint(self):
        def lookup(oid):
            if oid == MISSING: raise RuntimeError('HTTP 404')
            return order(oid)
        self.client.get_order.side_effect = lookup
        code, finished = self.run_main((FIXTURES / 'mixed.tsv').read_text())
        self.assertEqual(code, 1)
        self.assertIn('HTTP 404', finished['p_error'])
        self.assertEqual(finished['p_stats']['returns'], 1)
        self.assertEqual(finished['p_stats']['reports_imported'], 0)
        # Existing finish RPC marks p_error != null as failed; last-success query selects completed only.

    def test_systemic_finance_failure_preserves_report_stats_and_failed_status(self):
        code, finished = self.run_main((FIXTURES / 'empty.tsv').read_text(), 'HTTP 503')
        self.assertEqual(code, 1)
        self.assertIn('HTTP 503', finished['p_error'])
        self.assertEqual(finished['p_stats']['reports_imported'], 1)

    def test_normal_mf_return_completes_full_run(self):
        lines = (FIXTURES / 'mixed.tsv').read_text().splitlines(True)
        code, finished = self.run_main(lines[0] + lines[2])
        self.assertEqual(code, 0)
        self.assertIsNone(finished['p_error'])
        self.assertEqual(finished['p_stats']['returns'], 1)

    def test_confirmed_fba_report_row_is_skipped_not_partial(self):
        lines = (FIXTURES / 'mixed.tsv').read_text().splitlines(True)
        for saved in (False, True):
            with self.subTest(cached=saved):
                self.setUp()
                if saved:
                    self.db.tables['amazon_sales_orders'] = [{'amazon_order_id': VALID,
                        'marketplace_id': ACCOUNT['marketplace_id'], 'fulfillment_channel': 'AFN'}]
                else:
                    self.client.get_order.return_value = {**order(), 'fulfillment': {'fulfilledBy': 'AMAZON'}}
                self.assertEqual(self.run_report(lines[0] + lines[2]), 0)
                self.assertEqual(self.db.tables['amazon_mf_return_reports'][0]['status'], 'IMPORTED')
                self.assertFalse(self.db.returns)
                if saved: self.client.get_order.assert_not_called()

    def test_invalid_order_in_report_is_partial_not_fba_skip(self):
        content = (FIXTURES / 'mixed.tsv').read_text().replace(MISSING, 'NOT-AN-ORDER')
        with self.assertRaisesRegex(sync.IncompleteReturnsSync, 'UNVERIFIED'):
            self.run_report(content)
        self.assertEqual(len(self.db.returns), 1)
        self.assertEqual(self.db.tables['amazon_mf_return_reports'][0]['status'], 'PARTIAL')

    def test_partial_discovery_after_utc_rollover_replays_original_without_duplicates(self):
        content = (FIXTURES / 'mixed.tsv').read_text()
        def lookup(oid):
            if oid == MISSING: raise RuntimeError('HTTP 404')
            return order(oid)
        self.client.get_order.side_effect = lookup
        with patch.object(sync, 'now', return_value=datetime(2026, 11, 23, 23, 59, tzinfo=timezone.utc)):
            with self.assertRaises(sync.IncompleteReturnsSync): self.run_report(content)
        partial = self.db.tables['amazon_mf_return_reports'][0]
        partial.update(window_start='2026-09-26T00:00:00Z', window_end='2026-11-23T23:55:00Z')
        self.client.create_report.side_effect = lambda *_a, **_k: {'reportId': f'CURRENT-{len(self.db.tables["amazon_mf_return_reports"])}'}
        self.client.get_report.side_effect = lambda rid: {'processingStatus': 'DONE', 'reportDocumentId': rid}
        self.client.get_report_document.side_effect = lambda doc: {'url': f'https://fixture.invalid/{doc}'}
        def download(url, **_):
            text = content if url.endswith('AMAZON-REPORT') else (FIXTURES / 'empty.tsv').read_text()
            return SimpleNamespace(content=text.encode(), ok=True, status_code=200)
        with patch.object(sync, 'now', return_value=datetime(2026, 11, 24, 0, 5, tzinfo=timezone.utc)), \
             patch.object(sync.requests, 'get', side_effect=download), patch.object(sync.time, 'sleep'), \
             patch.object(sync, 'rpc', side_effect=self.db.apply), \
             patch.object(sync, 'transactions', side_effect=lambda *_: iter([])), \
             patch.object(sync, 'sync_carriers', return_value=0):
            for _ in range(2):
                with self.assertRaisesRegex(sync.IncompleteReturnsSync, 'HTTP 404') as error:
                    sync.synchronize(self.db, self.client, ACCOUNT)
                self.assertEqual(error.exception.stats['partial_reports_retried'], 1)
                self.assertEqual(partial['status'], 'PARTIAL')
                self.assertEqual(len(self.db.returns), 1)
                self.assertEqual(len(self.db.observations), 1)
            self.client.get_order.side_effect = lambda oid: order(oid)
            stats = sync.synchronize(self.db, self.client, ACCOUNT)
        self.assertEqual(stats['partial_reports_retried'], 1)
        self.assertEqual(partial['status'], 'IMPORTED')
        self.assertEqual(len(self.db.returns), 2)
        self.assertEqual(len(self.db.observations), 2)
        # There is no normalized-return discovery in the double; persisted reports drove replay.
        self.assertFalse(self.db.tables['vw_mf_open_returns'])

    def test_partial_status_survives_retry_download_failure(self):
        partial = {'id': 'OLD', 'account_id': ACCOUNT['id'], 'report_id': 'OLD-AMAZON',
                   'status': 'PARTIAL', 'window_start': '2026-01-01', 'window_end': '2026-01-02'}
        self.db.tables['amazon_mf_return_reports'] = [partial]
        with patch.object(sync.requests, 'get', side_effect=sync.requests.ConnectionError('offline')), \
             patch.object(sync.time, 'sleep'):
            with self.assertRaisesRegex(ValueError, 'transport failed'):
                sync.report(self.db, self.client, ACCOUNT, partial['window_start'], partial['window_end'], pending_report=partial)
        self.assertEqual(partial['status'], 'PARTIAL')

    def test_finance_verification_and_import_failures_survive_lookback_rollover(self):
        for failure in ('verification', 'import'):
            with self.subTest(failure=failure):
                self.setUp()
                source, failing = boundary_refund(), {'active': True}
                def request(_method, _path, params):
                    return {'transactions': [source] if params['postedAfter'] <= source['postedDate'] else []}
                self.client.request.side_effect = request
                def lookup(oid):
                    if failure == 'verification' and failing['active']: raise RuntimeError('Orders HTTP 404')
                    return order(oid)
                self.client.get_order.side_effect = lookup
                def apply(db, name, **args):
                    if name == 'mbop_mf_return_finance_complete_work' and failure == 'import' and failing['active']:
                        raise RuntimeError('Refund import rejected')
                    return self.db.apply(db, name, **args)
                with patch.object(sync, 'report', return_value=0), patch.object(sync.time, 'sleep'), \
                     patch.object(sync, 'rpc', side_effect=apply), patch.object(sync, 'sync_carriers', return_value=0):
                    with patch.object(sync, 'now', return_value=datetime(2026, 11, 23, 23, 59, tzinfo=timezone.utc)):
                        with self.assertRaises(sync.IncompleteReturnsSync):
                            sync.synchronize(self.db, self.client, ACCOUNT)
                    work = self.db.tables['amazon_mf_return_finance_work'][0]
                    self.assertEqual(work['status'], 'pending')
                    self.assertFalse(self.db.finances)
                    with patch.object(sync, 'now', return_value=datetime(2026, 11, 24, 0, 5, tzinfo=timezone.utc)):
                        with self.assertRaises(sync.IncompleteReturnsSync) as error:
                            sync.synchronize(self.db, self.client, ACCOUNT)
                        self.assertEqual(error.exception.stats['finance_work_retried'], 1)
                        self.assertGreater(self.client.request.call_args.kwargs['params']['postedAfter'], source['postedDate'])
                        failing['active'] = False
                        stats = sync.synchronize(self.db, self.client, ACCOUNT)
                        self.assertEqual(stats['financial_transactions'], 1)
                        self.assertEqual(work['status'], 'imported')
                        # Replay an observed refund after recovery; transaction identity stays unique.
                        self.db.apply(self.db, 'mbop_mf_return_finance_enqueue', p_account=ACCOUNT['id'],
                                      p_transaction=work['transaction_data'], p_observed=sync.now().isoformat())
                        sync.synchronize(self.db, self.client, ACCOUNT)
                self.assertEqual(len(self.db.finances), 1)
                self.assertEqual(len(self.db.tables['amazon_mf_return_finance_work']), 1)


if __name__ == '__main__':
    unittest.main()
