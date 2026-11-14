import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations'))
from amazon_mf_returns import parse_report, financial_transaction, windows, amount, date, is_customer_order_id
from amazon_sync_mf_returns import transactions, verify_order


class ReturnSources(unittest.TestCase):
    def test_order_failures_allow_following_transactions_and_carrier_sync(self):
        from unittest.mock import Mock, patch
        from amazon_sync_mf_returns import synchronize
        db, client = Mock(), Mock()
        db.table.return_value.select.return_value.eq.return_value.neq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
        account = {'id': 'ACCOUNT', 'marketplace_id': 'US'}
        missing = '114-8866055-7493009'
        broken = '123-1234567-1234567'
        valid = '123-7654321-7654321'
        feed = [
            {'transactionId': str(index), 'transactionType': 'Refund',
             'relatedIdentifiers': [{'relatedIdentifierName': 'ORDER_ID', 'relatedIdentifierValue': oid}]}
            for index, oid in enumerate([missing, missing, broken, valid])
        ]
        with patch('amazon_sync_mf_returns.report', return_value=0), \
             patch('amazon_sync_mf_returns.transactions', return_value=iter(feed)), \
             patch('amazon_sync_mf_returns.verify_order', side_effect=[RuntimeError('HTTP 404'), True, True]) as verify, \
             patch('amazon_sync_mf_returns.rpc', side_effect=[RuntimeError('Import rejected'), None]) as apply, \
             patch('amazon_sync_mf_returns.sync_carriers', return_value=2) as carriers, \
             patch('amazon_sync_mf_returns.time.sleep'):
            with self.assertRaisesRegex(ValueError, 'HTTP 404.*Import rejected'):
                synchronize(db, client, account)
        self.assertEqual(verify.call_count, 3)
        self.assertEqual(apply.call_count, 2)
        self.assertEqual(apply.call_args.kwargs['p_transaction']['amazon_order_id'], valid)
        carriers.assert_called_once_with(db, account)

    def test_shipment_finance_reference_never_calls_customer_orders_or_database(self):
        from unittest.mock import Mock
        db, client = Mock(), Mock()
        for invalid in ('FBA19W1MLF5L', 'FBA123456789', '', None, 'ORDER', '123-1234567-1234567/other'):
            self.assertFalse(verify_order(db, client, {'id':'ACCOUNT'}, invalid))
        db.table.assert_not_called()
        client.get_order.assert_not_called()
        self.assertTrue(is_customer_order_id('123-1234567-1234567'))

    def test_real_customer_order_lookup_errors_remain_visible(self):
        from unittest.mock import Mock
        db, client = Mock(), Mock()
        db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data=[]
        db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data=[]
        client.get_order.side_effect=RuntimeError('Real customer order read failed')
        with self.assertRaisesRegex(RuntimeError,'Real customer order read failed'):
            verify_order(db, client, {'id':'ACCOUNT','marketplace_id':'US'}, '123-1234567-1234567')
        client.get_order.assert_called_once_with('123-1234567-1234567')

    def test_returns_ui_static_text_has_no_corrupt_encoding(self):
        root=Path(__file__).resolve().parents[1]/'web/app/mf-returns'
        for name in ('ReturnsWorkspace.tsx','ReturnForms.tsx'):
            self.assertTrue((root/name).read_text(encoding='utf-8').isascii(), name)

    def test_shipment_adjustment_does_not_stop_following_mf_refund(self):
        from unittest.mock import Mock, patch
        from amazon_sync_mf_returns import synchronize
        db, client = Mock(), Mock()
        db.table.return_value.select.return_value.eq.return_value.neq.return_value.order.return_value.limit.return_value.execute.return_value.data=[]
        account={'id':'ACCOUNT','marketplace_id':'US'}
        def source(oid,kind,tid):
            return {'transactionId':tid,'transactionType':kind,'transactionStatus':'RELEASED','postedDate':'2026-11-08T10:00:00Z',
                    'relatedIdentifiers':[{'relatedIdentifierName':'ORDER_ID','relatedIdentifierValue':oid}],
                    'totalAmount':{'currencyAmount':-5,'currencyCode':'USD'}}
        feed=[source('FBA19W1MLF5L','Adjustment','POSTAGE'),source('123-1234567-1234567','Refund','REFUND')]
        with patch('amazon_sync_mf_returns.report',return_value=0),patch('amazon_sync_mf_returns.transactions',return_value=iter(feed)),patch('amazon_sync_mf_returns.verify_order',return_value=True) as verify,patch('amazon_sync_mf_returns.rpc') as apply,patch('amazon_sync_mf_returns.sync_carriers',return_value=0),patch('amazon_sync_mf_returns.time.sleep'):
            stats=synchronize(db,client,account)
        self.assertEqual(stats['non_customer_financial_references'],1)
        self.assertEqual(stats['financial_transactions'],1)
        verify.assert_called_once_with(db,client,account,'123-1234567-1234567')
        self.assertEqual(apply.call_args.kwargs['p_transaction']['transaction_id'],'REFUND')

    def test_zero_is_known_and_unavailable_dates_are_unknown(self):
        self.assertEqual(amount(0),'0')
        self.assertIsNone(date('N/A'))
    def test_report_multiple_items_packages_duplicate_and_unknown_dates(self):
        header='Order ID\tAmazon RMA ID\tOrder Item ID\tMerchant SKU\tReturn quantity\tTracking ID\tReturn request date\tRefunded Amount\n'
        lines=parse_report(header+'ORDER\tRMA\tITEM1\tSKU1\t2\t1Z123\t2026-11-01\t10.20\n'+
                           'ORDER\tRMA\tITEM1\tSKU1\t2\t1Z456\t2026-11-01\t10.20\n'+
                           'ORDER\tRMA\tITEM2\tSKU2\t1\t1Z123\t\t\n')
        self.assertEqual(len(lines),2)
        self.assertEqual(lines[0]['quantity'],2)
        self.assertEqual(len(lines[0]['packages']),2)
        self.assertIsNone(lines[1]['requested_at'])
        self.assertNotIn('refund_posted_at',lines[0])

    def test_invalid_identity_and_dates_fail_instead_of_inventing(self):
        with self.assertRaises(ValueError): parse_report('Order ID\tAmazon RMA ID\tMerchant SKU\tReturn quantity\nORDER\t\tSKU\t1\n')

    def test_split_windows_at_most_sixty_days_and_overlap(self):
        start=datetime(2026,1,1,tzinfo=timezone.utc)
        result=list(windows(start,start+timedelta(days=150)))
        self.assertEqual(len(result),3)
        self.assertTrue(all(datetime.fromisoformat(b)-datetime.fromisoformat(a)<=timedelta(days=60) for a,b in result))
        self.assertLess(datetime.fromisoformat(result[1][0]),datetime.fromisoformat(result[0][1]))

    def test_refund_transaction_identity_not_adjustment_identity(self):
        t={'transactionId':'TX','transactionType':'Refund','transactionStatus':'RELEASED','postedDate':'2026-11-01T10:00:00Z',
           'relatedIdentifiers':[{'relatedIdentifierName':'ORDER_ID','relatedIdentifierValue':'ORDER'}],
           'totalAmount':{'currencyAmount':-9.5,'currencyCode':'USD'},'items':[{'relatedIdentifiers':[{'itemRelatedIdentifierName':'ORDER_ADJUSTMENT_ITEM_ID','itemRelatedIdentifierValue':'ADJUST'}]}]}
        row=financial_transaction(t)
        self.assertEqual(row['transaction_id'],'TX');self.assertEqual(row['amount'],'-9.5')
        self.assertIsNone(row['items'][0]['amazon_order_item_id']);self.assertEqual(row['items'][0]['adjustment_item_id'],'ADJUST')
        self.assertNotIn('buyer',row)

    def test_finance_pagination_keeps_filters_and_empty_pages(self):
        class Client:
            calls=[]
            def request(self,method,path,params):
                self.calls.append(params)
                return {'transactions':[],'nextToken':'NEXT'} if len(self.calls)==1 else {'transactions':[{'id':1}]}
        client=Client()
        import unittest.mock as mock
        with mock.patch('amazon_sync_mf_returns.time.sleep'):
            self.assertEqual(list(transactions(client,'START','END')),[{'id':1}])
        self.assertEqual(client.calls[1],{'postedAfter':'START','postedBefore':'END','nextToken':'NEXT'})
        self.assertNotIn('marketplaceId',client.calls[0])

if __name__=='__main__':unittest.main()
