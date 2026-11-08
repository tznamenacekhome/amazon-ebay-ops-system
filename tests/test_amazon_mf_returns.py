import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations'))
from amazon_mf_returns import parse_report, financial_transaction, windows, amount, date
from amazon_sync_mf_returns import transactions, verify_order


class ReturnSources(unittest.TestCase):
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
