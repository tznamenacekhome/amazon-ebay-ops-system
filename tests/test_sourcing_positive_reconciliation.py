"""Provenance decisions must be independent of matcher success and workflow labels."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations'))
from reconcile_sourcing_positive_evidence import classify, listing_scope


class ReconciliationTests(unittest.TestCase):
    def classify(self, **overrides):
        arguments = dict(row={'asin':'A','ebayItemId':'123456789012'},
                         purchase={'asin':'A'}, receiving=None,
                         negative=None, adjudication={})
        arguments.update(overrides)
        return classify(**arguments)[0]

    def test_successful_receipt_is_candidate_not_certification(self):
        receipt={'asin':'A','ebay_item_id':'123456789012','outcome':'correct_item'}
        self.assertEqual('B', self.classify(receiving=receipt))
        self.assertEqual('C', self.classify())

    def test_other_asin_receipt_never_certifies_current_pair(self):
        receipt={'asin':'B','ebay_item_id':'123456789012','outcome':'correct_item'}
        self.assertEqual('C', self.classify(receiving=receipt))

    def test_changed_asin_is_unresolved_not_an_invented_mistake(self):
        self.assertEqual('E', self.classify(purchase={'asin':'B'}))

    def test_material_evidence_not_erased_by_receipt(self):
        receipt={'asin':'A','ebay_item_id':'123456789012','outcome':'correct_item'}
        self.assertEqual('E',self.classify(receiving=receipt,adjudication={'materialUnresolved':True}))

    def test_documented_wrong_delivery_is_not_good_workflow_evidence(self):
        self.assertEqual('D', self.classify(negative={'outcome':'wrong_item'}))

    def test_transaction_is_not_variation(self):
        self.assertEqual(('123456789012',None),listing_scope('123456789012-10080059012115'))
        self.assertEqual(('123456789012','7'),listing_scope('v1|123456789012|7'))
        self.assertNotEqual(listing_scope('v1|123456789012|0'),listing_scope('v1|123456789012|7'))
        self.assertEqual((None,None),listing_scope(None))


if __name__ == '__main__':
    unittest.main()
