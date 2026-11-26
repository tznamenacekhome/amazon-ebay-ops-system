"""Business platform policy is shared, early and independent of match identity."""
import json
import unittest
from pathlib import Path
from unittest.mock import patch, PropertyMock
from test_sourcing_phase3 import inputs, SETTINGS, review
from test_flipmine_context import DB
from flipmine_context import SourcingContext
from sourcing_platform_policy import POLICY, platform_eligibility
from sourcing_match_rules import evaluate_static_match_rules, normalize_candidate_evidence
from video_game_identity import build_identity_comparison
from score_sourcing_opportunities import score_candidate


class PlatformPolicyTests(unittest.TestCase):
    def seed(self, system, format=None):
        return {'asin':'B000TEST00','system':system,'amazon_title':'Example Quest',
            'raw_context_json':{'amazon_catalog_identity':{'asin':'B000TEST00',
                'normalized_platform':system,'normalized_format':format}}}

    def test_all_cartridge_platforms_excluded_even_bad_disc_label(self):
        for system in POLICY['excludedCartridgePlatforms']:
            with self.subTest(system=system):
                self.assertEqual('blocked',platform_eligibility(self.seed(system,'dvd_rom'))['result'])

    def test_switch_disc_pc_and_umd_keep_existing_eligibility(self):
        for system in [*POLICY['explicitEligiblePlatforms'],*POLICY['discOrComputerPlatforms']]:
            with self.subTest(system=system):
                self.assertEqual('pass',platform_eligibility(self.seed(system,'umd' if system=='PSP' else None))['result'])

    def test_operator_overrides_and_alias_distinctions(self):
        for alias in ['Nintendo 3DS','PlayStation Vita','Sony PSP','PC','Nintendo Switch','Nintendo Switch 2']:
            self.assertEqual('pass',platform_eligibility(self.seed(alias))['result'],alias)
        for alias in ['Game Cube','Nintendo GameCube','Nintendo DS']:
            self.assertEqual('blocked',platform_eligibility(self.seed(alias))['result'],alias)

    def test_aliases_and_mixed_platforms(self):
        for alias in ['Nintendo DS','Gameboy Advance','Nintendo Game Boy Color',
                      'Super NES','SNES','Mega Drive','Sega Genesis','Sega Game Gear']:
            self.assertEqual('blocked',platform_eligibility(self.seed(alias))['result'],alias)
        for system in POLICY['mixedFormatPlatforms']:
            self.assertEqual('unresolved',platform_eligibility(self.seed(system))['result'])
            self.assertEqual('unresolved',platform_eligibility(self.seed(system,'cd_rom'))['result'])
            disc=self.seed(system,'cd_rom');disc['raw_context_json']['amazon_catalog_identity']['relevant_attributes_json']={'physical_format':'CD-ROM'}
            self.assertEqual('pass',platform_eligibility(disc)['result'])
            self.assertEqual('blocked',platform_eligibility(self.seed(system,'cartridge'))['result'])
            s=self.seed(system,'cd_rom')
            self.assertEqual('blocked',platform_eligibility(s,{'ebay_title':'Example Quest cartridge'})['result'])

    def test_unknown_platform_and_conflicting_systems_do_not_pass(self):
        self.assertEqual('unresolved',platform_eligibility(self.seed('Unknown'))['result'])
        self.assertEqual('unresolved',platform_eligibility(self.seed('Nintendo Switch / Nintendo 3DS'))['result'])
        s=self.seed('PS 3');s['raw_context_json']['amazon_catalog_identity']['relevant_attributes_json']={'platform':'PS 4'}
        self.assertEqual('unresolved',platform_eligibility(s)['result'])

    def test_actual_mario_identity_matches_but_never_opens(self):
        rows=json.loads((Path(__file__).parent/'fixtures/typed_metadata_phase1_20261125.json').read_text())
        row=next(r for r in rows if r['row']==238);s,c=row['seed'],row['candidate']
        identity=build_identity_comparison(amazon_title=s['amazon_title'],ebay_title=c['ebay_title'],seed=s,
            evidence=normalize_candidate_evidence(c),policy='phase3_shadow')
        self.assertEqual('match',identity['comparisons']['coreGame']['result'])
        result=score_candidate(c,s,SETTINGS,matching_context={'offline_identity_policy':'phase3_shadow'})
        self.assertNotEqual('open',result['status'])
        rules=result['matching_diagnostics_json']['static_rules']
        self.assertIn(POLICY['cartridgeReason'],rules['hard_blocks'])

    def test_known_ineligible_catalog_skips_every_provider(self):
        for system in ['Game Boy Advance','Gamecube']:
            db=DB();db.rows['amazon_catalog_item_identity_snapshots'][0]['normalized_platform']=system
            ctx=SourcingContext(db,SETTINGS)
            with patch.object(SourcingContext,'amazon',new_callable=PropertyMock) as provider:
                provider.side_effect=AssertionError('No providers for an explicitly ineligible platform')
                self.assertIsNone(ctx.seed('B000000001'))
            self.assertIsNone(ctx._keepa)

    def test_manual_identity_confirmation_cannot_waive_business_policy(self):
        s,c=inputs('Example Quest Gamecube','Example Quest Gamecube',game_name='Example Quest',system='Gamecube')
        rule=evaluate_static_match_rules(c,s,identity_policy='phase3_shadow',scoped_reviews=[review(s,c)],review_cutoff='2026-11-26T05:00:00+00:00')
        self.assertEqual('match',rule['identity_comparison']['comparisons']['coreGame']['result'])
        self.assertEqual('blocked',rule['sourcing_platform_policy']['result'])

    def test_wholesale_uses_same_policy_before_fees_or_inventory_reads(self):
        from wholesale_evaluate_opportunities import evaluate_product
        class Repository:
            def get_matching_detail(self,*args):return {'product':{'supplier_product_id':'product'},'match_state':{'selected_candidate_id':'candidate'},'candidates':[{'candidate_id':'candidate','asin':'B000TEST00'}]}
            def observation_history(self,*args):return [{'observation_id':'observation'}]
            def ensure_opportunity(self,*args):return {'opportunity_id':'opportunity'}
            def catalog_snapshots(self,*args):return {'B000TEST00':{'asin':'B000TEST00','normalized_platform':'Game Boy Advance'}}
            def save_evaluation(self,op,row):return row
        result=evaluate_product(Repository(),'product','US')
        self.assertFalse(result['is_financially_qualified'])
        self.assertEqual([POLICY['cartridgeReason']],result['incomplete_reasons'])


if __name__=='__main__':unittest.main()
