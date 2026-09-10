import sys
import unittest
from pathlib import Path
from decimal import Decimal as D
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations'))
from analyze_amazon_inbound_storage import fee_rows,summarize_shipments,seasonal_holding,next_month,percentile
from amazon_spapi_client import AmazonSPAPIClient,AmazonSPAPIError

class InboundStorageTests(unittest.TestCase):
    def test_only_documented_storage_reports_added(self):
        client=AmazonSPAPIClient.__new__(AmazonSPAPIClient)
        client.config=SimpleNamespace(marketplace_id='ATVPDKIKX0DER')
        for typ in ('GET_FBA_STORAGE_FEE_CHARGES_DATA','GET_FBA_FULFILLMENT_LONGTERM_STORAGE_FEE_CHARGES_DATA'):
            self.assertEqual(client.create_report_payload(typ)['reportType'],typ)
        with self.assertRaises(AmazonSPAPIError):client.create_report_payload('UNKNOWN_UNAUTHORIZED_REPORT')

    def transaction(self,ident='a',amount=-10,kind='ServiceFee',date='2026-02-01'):
        return {'transactionId':ident,'transactionStatus':'RELEASED','description':'FBAStorageBilling',
                'transactionType':kind,'postedDate':date,'totalAmount':{'currencyCode':'USD','currencyAmount':amount}}

    def test_parent_and_nested_amount_counted_once(self):
        t=self.transaction();t['items']=[{'totalAmount':{'currencyAmount':-10}}]
        self.assertEqual(fee_rows([t,t],'2025-09-01','2026-09-01')[0]['cost_usd'],D(10))

    def test_reversal_and_correction_keep_signs(self):
        rows=fee_rows([self.transaction(),self.transaction('b',10,'ServiceFee - Reversal'),
                       self.transaction('c',-9,'ServiceFee - Correction')],'2025-09-01','2026-09-01')
        self.assertEqual(sum(r['cost_usd'] for r in rows),D(9))

    def test_boundary_and_deferred(self):
        t=self.transaction('d');t['transactionStatus']='DEFERRED'
        rows=fee_rows([t,self.transaction(date='2026-09-01')],'2025-09-01','2026-09-01')
        self.assertEqual(rows,[])

    def test_conflicting_versions_rejected(self):
        with self.assertRaises(ValueError):fee_rows([self.transaction(),self.transaction(amount=-11)],'2025-09-01','2026-09-01')

    def test_currency_not_silently_mixed(self):
        t=self.transaction();t['totalAmount']['currencyCode']='CAD'
        with self.assertRaises(ValueError):fee_rows([t],'2025-09-01','2026-09-01')

    def test_weighted_denominator_and_mixed_game_allocation(self):
        rows=[{'units':100,'game_units':20,'carrier':D(10)},
              {'units':10,'game_units':10,'carrier':D(10)},
              {'units':1000,'game_units':1000,'carrier':None}]
        result=summarize_shipments(rows,'carrier')
        self.assertEqual(result['weighted_per_unit'],D(20)/110)
        self.assertEqual(result['allocated_game_cost'],D(12))
        self.assertEqual(result['allocated_per_game'],D('0.4'))
        self.assertEqual(result['shipments'],2)

    def test_zero_fee_is_distinct_from_missing(self):
        result=summarize_shipments([{'units':10,'game_units':10,'carrier':D(0)}],'carrier')
        self.assertEqual(result['weighted_per_unit'],0)
        self.assertIsNone(summarize_shipments([],'carrier')['weighted_per_unit'])

    def test_annual_seasons_and_missing_input(self):
        low,high=seasonal_holding(D('.01'),D('.03'),365)
        self.assertEqual(low,high)
        self.assertLess(high,D('.03')*12)
        self.assertEqual(seasonal_holding(None,D('.03'),90),(None,None))

    def test_month_rollover_and_percentiles(self):
        self.assertEqual(next_month('2025-12'),'2026-01')
        self.assertEqual(percentile([D(1),D(3)],.25),D('1.5'))

if __name__=='__main__':unittest.main()
