"""Exact saved production wording from the failed November 24 release gate."""
import json
import unittest
from copy import deepcopy
from pathlib import Path
import test_sourcing_edition_policy as policy_tests
from sourcing_match_rules import used_condition_hits, condition_review_hits


class CapturedShadowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = {r['item']: r for r in json.loads(
            (Path(__file__).parent/'fixtures/edition_shadow_failures_20261124.json').read_text())}

    def evaluate(self, item):
        row = self.rows[item]
        return policy_tests.EditionPolicyTests().score(deepcopy(row['seed']), deepcopy(row['candidate']))

    def test_actual_confirmed_defects(self):
        for item in ('880128084759', '336887119682'):
            with self.subTest(item=item):
                result = self.evaluate(item)
                self.assertEqual(result['status'], 'rejected')
                self.assertTrue(result['matching_diagnostics_json']['static_rules']['condition_mismatch']['hits'])
                self.assertEqual(result['matching_diagnostics_json']['static_rules']['condition_mismatch']['evidenceState'], 'confirmed_unacceptable')
                self.assertEqual(result['matching_diagnostics_json']['presentationDecision']['primaryReason']['code'], 'condition_unacceptable')

    def test_actual_condition_reviews(self):
        for item in ('287741926297', '840120275430'):
            with self.subTest(item=item):
                result = self.evaluate(item)
                self.assertEqual(result['status'], 'rejected')
                d = result['matching_diagnostics_json']
                self.assertFalse(d['static_rules']['condition_mismatch']['hits'])
                self.assertEqual(d['static_rules']['condition_mismatch']['evidenceState'], 'requires_review')
                self.assertEqual(d['presentationDecision']['primaryReason']['code'], 'condition_review')

    def test_actual_wii_fit_contents_uncertainty_survives_edition(self):
        result = self.evaluate('147693336106')
        self.assertEqual(result['status'], 'rejected')
        self.assertEqual(result['matching_diagnostics_json']['presentationDecision']['primaryReason']['code'], 'contents_not_corroborated')

    def test_actual_features_complete_remain_review_not_conflict(self):
        for item in ('407348790546', '257841605061'):
            result = self.evaluate(item)
            identity = result['matching_diagnostics_json']['static_rules']['identity_comparison']
            self.assertEqual(identity['result'], 'review')
            self.assertFalse(identity['hard_block'])
            self.assertEqual(result['status'], 'rejected')

    def test_actual_accepted_identity_regressions_resolved(self):
        for item in ('314068158958', '168877999113'):
            d = self.evaluate(item)['matching_diagnostics_json']
            self.assertEqual(d['static_rules']['identity_comparison']['result'], 'match')

    def test_negated_and_conditional_damage_not_affirmative(self):
        for text in ('No seal damage.', 'No visible seal damage.', 'No cracks.',
                     'The case is not cracked.', 'There is no small tear in the plastic.',
                     'If the case is cracked, contact us.', 'Without a cracked case.'):
            self.assertFalse(used_condition_hits('',text), text)
            self.assertFalse(condition_review_hits('',text), text)

    def test_genuine_named_editions_still_conflict(self):
        helper = policy_tests.EditionPolicyTests()
        for label in ('Enhanced Edition','Special Edition','Complete Edition','Deluxe Edition'):
            s,c = helper.pair(b=label)
            self.assertEqual(helper.compare(s,c)['result'], 'conflict', label)

    def test_description_named_edition_not_ignored(self):
        helper = policy_tests.EditionPolicyTests()
        s,c = helper.pair(description='This is the Special Edition.')
        self.assertEqual(helper.compare(s,c)['result'],'conflict')

    def test_bare_enhanced_in_product_title_remains_named(self):
        helper = policy_tests.EditionPolicyTests()
        s,c = helper.pair(a='Enhanced Edition', b='Enhanced', game='Dead or Alive 5 Enhanced')
        self.assertEqual(helper.compare(s,c)['result'], 'match')

    def test_missing_condition_is_distinct_from_affirmative_new(self):
        from sourcing_match_rules import evaluate_static_match_rules
        helper = policy_tests.EditionPolicyTests()
        s,c = helper.pair()
        self.assertEqual(evaluate_static_match_rules(c,s,identity_policy='phase3_shadow')['condition_mismatch']['evidenceState'], 'affirmatively_new')
        c['ebay_title']='Dead or Alive 5 PS3'
        c['condition']=None
        c['condition_id']=None
        c['raw_ebay_json'].pop('conditionId',None)
        self.assertEqual(evaluate_static_match_rules(c,s,identity_policy='phase3_shadow')['condition_mismatch']['evidenceState'], 'missing')


if __name__ == '__main__':
    unittest.main()
