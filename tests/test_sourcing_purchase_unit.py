import json
import unittest
from copy import deepcopy
from pathlib import Path
from test_sourcing_phase3 import SETTINGS
from sourcing_match_rules import evaluate_static_match_rules
from score_sourcing_opportunities import score_candidate


class PurchaseUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.row=next(r for r in json.loads((Path(__file__).parent/'fixtures/identity_wording_phase2_20261125.json').read_text(encoding='utf-8'))if r['label']=='flipmine:43')

    def rules(self,description=None,change=None):
        s,c=deepcopy(self.row['seed']),deepcopy(self.row['candidate'])
        if description is not None:
            c['raw_ebay_json']['description']=description;c['raw_ebay_json']['shortDescription']=''
        if change:change(c)
        return evaluate_static_match_rules(c,s,identity_policy='phase3_shadow'),s,c

    def test_generic_testing_does_not_penalize_sealed_or_new_inventory(self):
        for text in ['Tested','Tested and working','All tested & working.',
                     'Brand new factory sealed. All tested and working.',
                     'We sell new and used games. This copy is factory sealed. All tested and working.',
                     'Never opened to test. Factory sealed.']:
            with self.subTest(text=text):
                rules,s,c=self.rules(text)
                self.assertEqual('pass',rules['condition_mismatch']['result'])
                self.assertEqual('pass',rules['condition_review']['result'])
                self.assertEqual('pass',rules['purchase_unit']['result'])

    def test_specific_opened_used_played_missing_seal_and_damage_remain_blocked(self):
        for text in ['This game was opened to test it.','Opened for testing.','I opened it to test.','Played once.',
                     'This copy has been played.','This game is used.',
                     'Missing the plastic seal.','Cracked case.',
                     'We sell new and used games. This game is used.']:
            with self.subTest(text=text):
                rules,_,_=self.rules(text)
                self.assertEqual('blocked',rules['condition_mismatch']['result'])
                self.assertTrue(rules['hard_blocks'])

    def test_actual_named_price_can_bind_individual_new_game(self):
        rules,s,c=self.rules()
        self.assertEqual('pass',rules['purchase_unit']['result'])
        self.assertEqual('14.0',rules['purchase_unit']['price'])
        self.assertEqual('Probable Match',rules['recommendation'])
        scored=score_candidate(c,s,SETTINGS,matching_context={'offline_identity_policy':'phase3_shadow'})
        self.assertEqual('open',scored['status'])
        self.assertEqual(self.row['candidate']['raw_ebay_json'],c['raw_ebay_json'])

    def test_unbound_lot_conflicting_price_and_variations_require_review(self):
        base='Retro video game lot of 27 games. Tier 1 (Individually Priced): Saints Row 2 ($14). All tested & working.'
        cases=[(base.replace('($14)','($15)'),None),
               ('Retro lot of 27 games. All tested and working.',None),
               (base+' Saints Row 2 ($12).',None),
               (base,lambda c:c['raw_ebay_json'].update(variationAspects=[{'name':'Game','value':'Select'}])),
               (base,lambda c:c.update(available_quantity=0)),
               (base,lambda c:c.update(ebay_title='Saints Row 2 lot of 27 games'))]
        for description,change in cases:
            with self.subTest(description=description,change=change):
                rules,s,c=self.rules(description,change)
                self.assertEqual('pass',rules['condition_mismatch']['result'])
                self.assertEqual('review',rules['purchase_unit']['result'])
                scored=score_candidate(c,s,SETTINGS,matching_context={'offline_identity_policy':'phase3_shadow'})
                self.assertNotEqual('open',scored['status'])
                self.assertTrue(any(t['reasonCode']=='purchase_unit_review'for t in scored['matching_diagnostics_json']['decisionTrace']if t.get('reasonCode')))

    def test_missing_original_contents_stays_independent(self):
        rules,_,_=self.rules('Brand New. Game only, missing manual.')
        self.assertEqual('blocked',rules['incomplete_listing']['result'])


    def test_mixed_inventory_requires_specific_game_condition(self):
        text='Mixed new and used inventory. Individually Priced: Saints Row 2 ($14). All tested and working.'
        rules,_,_=self.rules(text)
        self.assertEqual('pass',rules['condition_mismatch']['result'])
        self.assertEqual('review',rules['purchase_unit']['result'])
        rules,_,_=self.rules(text+' Saints Row 2 is factory sealed.')
        self.assertEqual('pass',rules['condition_mismatch']['result'])
        self.assertEqual('pass',rules['purchase_unit']['result'])


if __name__=='__main__':unittest.main()
