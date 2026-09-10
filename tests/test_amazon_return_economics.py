import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations'))
from analyze_amazon_return_economics import unique_transactions, item_components, classify_game, loss_bounds


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


if __name__=='__main__':unittest.main()
