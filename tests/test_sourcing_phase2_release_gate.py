"""Release gates from individual review under the clarified operator policy.

Actual condition failures remain blocked. Generic testing does not establish
use: Saints Row is assessed independently for individual unit/price evidence.
"""
import json
import unittest
from pathlib import Path
from test_sourcing_phase3 import inputs  # Establish the integration module path.
from sourcing_match_rules import evaluate_static_match_rules


class Phase2ReleaseGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=json.loads((Path(__file__).parent/'fixtures/identity_wording_phase2_20261125.json').read_text(encoding='utf-8'))

    def assert_condition_block(self,number):
        row=next(r for r in self.rows if r['label']==f'flipmine:{number}')
        result=evaluate_static_match_rules(row['candidate'],row['seed'],identity_policy='phase3_shadow')
        self.assertEqual('blocked',result['condition_mismatch']['result'],
                         f"Unsafe New-condition admission for actual source row {number}; release remains blocked")

    def test_visible_case_cracks_must_block_new_bejeweled(self):
        self.assert_condition_block(504)

    def test_saints_row_individual_price_binding_and_generic_testing(self):
        row=next(r for r in self.rows if r['label']=='flipmine:43')
        result=evaluate_static_match_rules(row['candidate'],row['seed'],identity_policy='phase3_shadow')
        self.assertEqual('pass',result['condition_mismatch']['result'])
        self.assertEqual('pass',result['condition_review']['result'])
        self.assertEqual('pass',result['purchase_unit']['result'])
        self.assertEqual('individual_with_seller_inventory_description',result['purchase_unit']['kind'])
        self.assertEqual('14.0',result['purchase_unit']['price'])

    def test_required_wheel_text_and_approved_greatest_hits_policy(self):
        for number in [136,151]:
            row=next(r for r in self.rows if r['label']==f'flipmine:{number}')
            result=evaluate_static_match_rules(row['candidate'],row['seed'],identity_policy='phase3_shadow')
            self.assertEqual('match',result['identity_comparison']['comparisons']['coreGame']['result'])
            self.assertEqual('pass',result['condition_mismatch']['result'])
            self.assertEqual('pass',result['contents_review']['result'])
            if number==151:
                self.assertEqual('match',result['identity_comparison']['comparisons']['edition']['result'])

    def test_image_fields_do_not_add_an_automated_gate(self):
        from copy import deepcopy
        row=next(r for r in self.rows if r['label']=='flipmine:43')
        before=evaluate_static_match_rules(row['candidate'],row['seed'],identity_policy='phase3_shadow')
        candidate=deepcopy(row['candidate']);candidate['raw_ebay_json']['image']={'imageUrl':'https://example.invalid/operator-review-only.jpg'}
        after=evaluate_static_match_rules(candidate,row['seed'],identity_policy='phase3_shadow')
        for key in ['recommendation','condition_mismatch','condition_review','purchase_unit','contents_review']:
            self.assertEqual(before[key],after[key])

    def test_case_damage_variants_negation_and_unrelated_context(self):
        from sourcing_match_rules import used_condition_hits
        for text in ['Visible cracks on case.','Cracks in the case.','Case has cracks.','Case is cracked.','Cracked jewel case.','Cracked corner of case.']:
            with self.subTest(text=text):self.assertTrue(used_condition_hits('',text))
        for text in ['No cracks.','Case has no cracks.','No cracks in the case.','Free from cracks in the case.','Case is not cracked.',
                     'Other games have cracked cases.','The phone case is cracked.','Cracked case on another game.','If the case is cracked, contact us.',
                     'Factory sealed. All tested and working.']:
            with self.subTest(text=text):self.assertFalse(used_condition_hits('',text))

if __name__=='__main__':unittest.main()
