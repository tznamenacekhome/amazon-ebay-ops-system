import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations'))
from analyze_amazon_return_economics import (
    unique_transactions, item_components, classify_game, loss_bounds,
    economic_bucket, missing_basis_sensitivity, shipping_concession,
    analyze_refund_only,
)


class ReturnEconomicsTests(unittest.TestCase):
    def test_deferred_and_release_are_one_economic_transaction(self):
        deferred={'transactionId':'d','transactionStatus':'DEFERRED_RELEASED','relatedIdentifiers':[{'relatedIdentifierName':'RELEASE_TRANSACTION_ID','relatedIdentifierValue':'r'}]}
        released={'transactionId':'r','transactionStatus':'RELEASED','relatedIdentifiers':[{'relatedIdentifierName':'DEFERRED_TRANSACTION_ID','relatedIdentifierValue':'d'}]}
        self.assertEqual(unique_transactions([], [deferred,released]),[released])

    def test_deferred_release_kept_if_release_not_available(self):
        deferred={'transactionId':'d','transactionStatus':'DEFERRED_RELEASED','relatedIdentifiers':[{'relatedIdentifierName':'RELEASE_TRANSACTION_ID','relatedIdentifierValue':'absent'}]}
        self.assertEqual(unique_transactions([], [deferred]),[deferred])

    def test_fresh_status_supersedes_cached_status(self):
        stored={'transactionId':'x','transactionStatus':'DEFERRED'}
        fresh={'transactionId':'x','transactionStatus':'RELEASED'}
        self.assertEqual(unique_transactions([{'raw_transaction_json':stored}],[fresh]),[fresh])

    def test_fee_parent_and_base_not_double_counted(self):
        item={'breakdowns':[{'breakdownType':'AmazonFees','breakdownAmount':{'currencyAmount':-4},'breakdowns':[{'breakdownType':'FBAPerUnitFulfillmentFee','breakdownAmount':{'currencyAmount':-4},'breakdowns':[{'breakdownType':'Base','breakdownAmount':{'currencyAmount':-4}}]}]}]}
        self.assertEqual(item_components(item),([('FBAPerUnitFulfillmentFee',Decimal('-4'))],Decimal('0')))

    def test_refund_revenue_not_an_expense(self):
        item={'breakdowns':[{'breakdownType':'ProductCharges','breakdowns':[{'breakdownType':'OurPricePrincipal','breakdownAmount':{'currencyAmount':-50}}]},{'breakdownType':'AmazonFees','breakdowns':[{'breakdownType':'Commission','breakdownAmount':{'currencyAmount':7.5}},{'breakdownType':'RefundCommission','breakdownAmount':{'currencyAmount':-1.5}}]}]}
        fees,principal=item_components(item)
        self.assertEqual(principal,Decimal('-50'))
        self.assertEqual(sum(v for k,v in fees),Decimal('6'))

    def test_accessory_not_classified_as_game(self):
        self.assertFalse(classify_game('X','Xbox One controller',{})[0])
        self.assertTrue(classify_game('Y','Minecraft - Xbox One',{})[0])

    def test_sellable_inventory_basis_not_lost(self):
        self.assertEqual(loss_bounds(Decimal(5),Decimal(20),Decimal(0),Decimal(0)),(Decimal(5),Decimal(5)))

    def test_unknown_recovery_has_separate_scenarios(self):
        self.assertEqual(loss_bounds(Decimal(5),Decimal(20),None,Decimal(3)),(Decimal(2),Decimal(22)))

    def test_missing_basis_cannot_produce_maximum(self):
        self.assertEqual(loss_bounds(Decimal(5),None,None,Decimal(0)),(Decimal(5),None))

    def test_known_impairment_is_already_net_of_recovery(self):
        self.assertEqual(loss_bounds(Decimal(5),Decimal(20),Decimal(12),Decimal(3)),(Decimal(14),Decimal(14)))

    def test_inspection_changes_economic_bucket_without_erasing_raw_damage(self):
        row = {'economic_outcome': 'inspected_sellable', 'raw_disposition': 'CUSTOMER_DAMAGED'}
        self.assertEqual(economic_bucket(row), 'A. Sellable')
        self.assertEqual(row['raw_disposition'], 'CUSTOMER_DAMAGED')

    def test_reimbursed_sellable_unit_has_one_exclusive_bucket(self):
        self.assertEqual(economic_bucket({'economic_outcome': 'amazon_reimbursed', 'raw_disposition': 'SELLABLE'}), 'C. Amazon reimbursed')

    def test_unrecognized_disposition_is_not_forced_to_unsellable(self):
        self.assertEqual(economic_bucket({'economic_outcome': 'unknown', 'raw_disposition': 'NEW_UNKNOWN_CODE'}), 'E. Unknown')

    def test_missing_basis_sensitivity_is_separate_estimate(self):
        average, exposure, expected = missing_basis_sensitivity(Decimal('312.24'), 17, 14, Decimal('404.79'), 2244)
        self.assertEqual(round(average, 2), Decimal('18.37'))
        self.assertEqual(round(exposure, 2), Decimal('257.14'))
        self.assertEqual(round(expected, 4), Decimal('0.4341'))

    def test_no_comparable_basis_does_not_manufacture_estimate(self):
        self.assertEqual(missing_basis_sensitivity(Decimal(0), 0, 14, Decimal(10), 100), (None, None, None))

    @staticmethod
    def ledger_item(principal=0, fee=0, cash=0, shipping=None):
        breakdowns = [
            {'breakdownType': 'ProductCharges', 'breakdowns': [{'breakdownType': 'OurPricePrincipal', 'breakdownAmount': {'currencyAmount': principal}}]},
            {'breakdownType': 'AmazonFees', 'breakdowns': [{'breakdownType': 'Commission', 'breakdownAmount': {'currencyAmount': fee}}]},
        ]
        if shipping is not None:
            breakdowns.append({'breakdownType': 'Shipping', 'breakdownAmount': {'currencyAmount': shipping}})
        return {'contexts': [{'contextType': 'ProductContext', 'sku': 'sku'}], 'breakdowns': breakdowns, 'totalAmount': {'currencyAmount': cash, 'currencyCode': 'USD'}}

    @staticmethod
    def transaction(kind, item):
        return {'transactionType': kind, 'transactionStatus': 'RELEASED', 'postedDate': '2026-01-02T00:00:00Z', 'relatedIdentifiers': [{'relatedIdentifierName': 'ORDER_ID', 'relatedIdentifierValue': 'order'}], 'items': [item]}

    @staticmethod
    def sale():
        return {'amazon_order_id': 'order', 'seller_sku': 'sku', 'asin': 'asin', 'title': 'Game', 'is_game': True, 'sold_units': 1, 'purchase_date': '2026-01-01', 'order_status': 'Shipped', 'cogs': '20', 'cogs_source': 'mbop_fifo'}

    def test_shipping_concession_does_not_charge_original_sale_fees(self):
        sale = self.transaction('Shipment', self.ledger_item(50, -10, 40))
        refund = self.transaction('Refund', self.ledger_item(0, 5, 0, -5))
        self.assertTrue(shipping_concession([(refund, refund['items'][0])]))
        rows = analyze_refund_only([], [self.sale()], [sale, refund], lambda name: [])
        self.assertEqual(rows[0]['net_transaction_cost'], Decimal(0))
        self.assertIsNone(rows[0]['known_basis_at_risk_zero_recovery_only'])

    def test_shipping_plus_product_refund_is_not_shipping_only(self):
        refund = self.transaction('Refund', self.ledger_item(-50, 5, -50, -5))
        self.assertFalse(shipping_concession([(refund, refund['items'][0])]))

    def test_report_reversal_is_signed_and_finance_credit_not_counted_again(self):
        reports = [
            {'reimbursement-id': 'original', 'amazon-order-id': 'order', 'sku': 'sku', 'currency-unit': 'USD', 'amount-total': '10'},
            {'reimbursement-id': 'reversal', 'original-reimbursement-id': 'original', 'amazon-order-id': '', 'sku': 'sku', 'currency-unit': 'USD', 'amount-total': '-3'},
        ]
        transactions = [self.transaction('Shipment', self.ledger_item(50, -10, 40)), self.transaction('Refund', self.ledger_item(-50, 7, -43)), self.transaction('FBAInventoryReimbursement', self.ledger_item(0, 0, 10))]
        row = analyze_refund_only([], [self.sale()], transactions, lambda name: reports)[0]
        self.assertEqual(row['known_reimbursements'], Decimal(7))
        self.assertEqual(row['net_transaction_cost'], Decimal(3))
        self.assertEqual(row['fees_less_cash_reimbursement_partial_components'], Decimal(-4))
        self.assertIsNone(row['known_inventory_impairment'])

    def test_empty_zero_amount_record_does_not_imply_lost_inventory(self):
        item = self.ledger_item()
        item['breakdowns'] = []
        row = analyze_refund_only([], [self.sale()], [self.transaction('Refund', item)], lambda name: [])[0]
        self.assertEqual(row['classification'], 'Zero-amount refund record; no product refund evidenced')
        self.assertEqual(row['net_transaction_cost'], Decimal(0))
        self.assertIsNone(row['known_basis_at_risk_zero_recovery_only'])


if __name__=='__main__':unittest.main()
