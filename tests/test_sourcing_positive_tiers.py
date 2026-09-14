import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations'))
from validate_sourcing_positive_tiers import evaluate


class PositiveTierTests(unittest.TestCase):
    def test_receiving_label_never_overrides_product_conflict(self):
        source={'asin':'A','ebay_item_id':'v1|123|1','amazon_title':'Prey PS3','ebay_title':'IL-2 Sturmovik Birds of Prey PS3','outcome':'correct_item'}
        row={'source_table':'matching_intelligence_receiving_outcomes','source_id':'r','asin':'A','ebay_item_id':'v1|123|1','raw_context_json':{'receiving_outcome':source}}
        result=evaluate([row])
        self.assertEqual(1,result['strict']['rows'])
        self.assertEqual(1,result['strict']['matchingExclusions'])
        self.assertEqual('non-match',result['strictRows'][0]['afterVerdict'])
        source['ebay_item_id']='v1|123|2'
        result=evaluate([row])
        self.assertEqual(0,result['strict']['rows'])
        self.assertEqual(1,len(result['unresolvedSources']))

    def test_unrelated_asin_reference_is_not_used(self):
        source={'asin':'A','ebay_item_id':'123','ebay_title':'Game PS3','outcome':'correct_item'}
        row={'source_table':'matching_intelligence_receiving_outcomes','source_id':'r','purchase_item_id':'p','asin':'A','ebay_item_id':'123','raw_context_json':{'receiving_outcome':source}}
        purchase={'source_table':'purchase_items','source_id':'p','purchase_item_id':'p','asin':'B','ebay_item_id':'123','raw_context_json':{'purchase_item':{'amazon_title':'Other Game PS3'}}}
        result=evaluate([row,purchase])
        self.assertEqual(0,result['strict']['rows'])
        self.assertFalse(result['unresolvedSources'][0]['referenceLinkedByPurchaseIdAndAsin'])


if __name__=='__main__':unittest.main()
