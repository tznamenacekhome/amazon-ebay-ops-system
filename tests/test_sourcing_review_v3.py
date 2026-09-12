import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations'))
from matching_feedback import normalize_matching_feedback
from analyze_matching_feedback import summarize_feedback_rows
from score_sourcing_opportunities import is_explicit_pair_review, classify
from types import SimpleNamespace

class ReviewV3Tests(unittest.TestCase):
    def test_pair_fields_evidence_are_independent(self):
        data={'version':'matching_feedback_v3','pairVerdict':'correct','failedRuleFamilies':['edition_version'],'evidenceSources':['ebay_game_name'],'corrections':[{'field':'edition','side':'amazon','scope':'asin','state':'unknown','value':None,'before':'Standard'}]}
        result=normalize_matching_feedback(data)
        self.assertEqual(result['pairVerdict'],'correct')
        self.assertEqual(result['evidenceSources'],['ebay_game_name'])
        self.assertEqual(result['corrections'],data['corrections'])
        self.assertEqual(normalize_matching_feedback(result),result)
        self.assertEqual(normalize_matching_feedback({'version':'matching_feedback_v3','allAssumptionsCorrect':True})['pairVerdict'],'not_provided')

    def test_analyzer_separates_automation_empty_uncertain_and_correction(self):
        def row(feedback,**other):return dict(raw_action_context={'matchingFeedback':feedback},**other)
        summary=summarize_feedback_rows([
            row({'version':'matching_feedback_v3','pairVerdict':'unsure'}),
            row({'version':'matching_feedback_v3','corrections':[{'state':'unknown'}]}),row({}),
            {'dismiss_reason':'duplicate_open_asin_opportunity','raw_action_context':{'cleanup_source':'cleanup'}},
        ])
        self.assertEqual(summary['automation_actions'],1)
        self.assertEqual(summary['empty_feedback_unlabeled'],1)
        self.assertEqual(summary['pair_verdict_counts']['unsure'],1)
        self.assertEqual(summary['correction_count'],1)

    def test_feedback_does_not_promote_or_change_legacy_admission(self):
        self.assertTrue(is_explicit_pair_review({'review_feedback':{'version':'matching_feedback_v3'}}))
        self.assertFalse(is_explicit_pair_review({'review_feedback':{'version':'matching_feedback_v2'}}))
        self.assertFalse(is_explicit_pair_review({}))

    def test_offer_policy_uses_allowed_offer_not_asking_roi(self):
        settings=SimpleNamespace(best_offer_min_ask_percent=70)
        candidate={'price':100,'shipping_cost':0,'best_offer_enabled':True,'raw_ebay_json':{'shippingOptions':[{'shippingCost':{'value':'0'}}]}}
        self.assertEqual(classify(candidate,['FIXED_PRICE'],100,80,False,settings),'best_offer')
        self.assertEqual(classify(candidate,['FIXED_PRICE'],100,60,False,settings),'no_profitable_source_found')
        self.assertEqual(classify(candidate,['AUCTION'],50,80,False,settings),'auction')

if __name__=='__main__':unittest.main()
