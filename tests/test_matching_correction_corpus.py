import sys
import unittest
from copy import deepcopy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations'))
from matching_correction_corpus import build_corpus


class CorrectionCorpusTests(unittest.TestCase):
    def test_sources_and_causal_uncertainty_are_preserved(self):
        row={'action_id':'a','asin':'ASIN','ebay_item_id':'v1|123|variation','created_at':'2026-09-13T12:00:00Z',
             'snapshot':{'action_id':'a','asin':'ASIN','ebay_item_id':'v1|123|variation','ebay_title':'Full original title'},
             'raw_action_context':{'evaluation':{'version':'original-parser'},
                 'matchingFeedback':{'version':'matching_feedback_v3','evidenceProvenance':'explicit','pairVerdict':'incorrect',
                                     'corrections':[{'field':'coreGame','side':'ebay','scope':'pair','state':'value','value':'Correct product','before':{'value':'Wrong product'}}]},
                 'diagnosticComparison':{'productIdentityVerdict':'match','rows':[{'key':'core_game_identity','ebay':'Wrong product','ebayEvidence':{'state':'supported'},'comparisonResult':'match'}]}}}
        before=deepcopy(row);result=build_corpus([row]);example=result['examples'][0]
        self.assertEqual(before,row)
        self.assertEqual('Full original title',example['originalSourceValue'])
        self.assertEqual('Wrong product',example['parserOutput'])
        self.assertEqual('original-parser',example['evaluationVersion'])
        self.assertTrue(example['snapshotLinked'])
        self.assertEqual({'reported_false_positive':1},result['pairCounts'])
        self.assertEqual('not_established_by_field_correction',example['comparisonError'])
        row['raw_action_context']['matchingFeedback']['pairVerdict']='not_provided'
        row['raw_action_context']['diagnosticComparison']['rows'][0]['ebayEvidence']['state']='unknown'
        result=build_corpus([row])
        self.assertEqual([],result['pairExamples'])
        self.assertEqual({'unknown_extraction':1},result['correctionCounts'])

    def test_legacy_inference_is_not_an_operator_correction(self):
        self.assertEqual([],build_corpus([{'raw_action_context':{'matchingFeedback':{'version':'matching_feedback_v2','corrections':[{}]}}}])['examples'])


if __name__=='__main__':unittest.main()
