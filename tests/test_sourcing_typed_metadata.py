"""Phase 1 metadata only: no seller/lexical/alias matching policy."""
import json
import unittest
from copy import deepcopy
from pathlib import Path
from test_sourcing_phase3 import inputs, SETTINGS
from system_detection import normalize_system
from sourcing_identity_metadata import typed_product_text
from sourcing_match_rules import normalize_candidate_evidence, evaluate_static_match_rules
from video_game_identity import build_identity_comparison, general_product_fields


class TypedMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.captures = json.loads((Path(__file__).parent/'fixtures/typed_metadata_phase1_20261125.json').read_text())

    def compare(self, a, b, names=None, system='PS 3', aspects=(), catalog=None):
        s, c = inputs(a, b, game_name=names, system=system)
        c['raw_ebay_json']['localizedAspects'] += [{'name': 'Platform', 'value': system}, *aspects]
        if catalog:
            s['raw_context_json']['amazon_catalog_identity'] = {'asin': s['asin'], **catalog}
        return build_identity_comparison(amazon_title=a, ebay_title=b, seed=s,
            evidence=normalize_candidate_evidence(c), policy='phase3_shadow')

    def test_complete_legacy_aliases(self):
        for phrase, canonical in [('Nintendo Game Boy Advance','Game Boy Advance'), ('Game Boy Advance','Game Boy Advance'),
                ('Nintendo GameCube','Gamecube'), ('Game Cube','Gamecube'), ('Super Nintendo','Super Nintendo'),
                ('SNES','Super Nintendo'), ('Sega Dreamcast','Dreamcast'), ('Sony PSP','PSP'), ('PlayStation Portable','PSP')]:
            with self.subTest(phrase=phrase):
                self.assertEqual(canonical, normalize_system(phrase))
                result = self.compare('Example Quest', 'Example Quest '+phrase, 'Example Quest', system=canonical)
                self.assertEqual('example quest', result['ebay']['coreGame'])
                self.assertTrue(any(v.get('field')=='platform' and v.get('text')==phrase for v in result['ebay']['assignedMetadata']))

    def test_actual_mario_and_independent_eligibility(self):
        row=next(r for r in self.captures if r['row']==238)
        s,c=row['seed'],row['candidate']
        result=build_identity_comparison(amazon_title=s['amazon_title'],ebay_title=c['ebay_title'],seed=s,
            evidence=normalize_candidate_evidence(c),policy='phase3_shadow')
        self.assertEqual('match',result['comparisons']['coreGame']['result'])
        self.assertEqual('super mario advance',result['ebay']['coreGame'])
        self.assertEqual('Game Boy Advance',result['amazon']['platform'])
        self.assertTrue(any(v.get('field')=='region' for v in result['ebay']['assignedMetadata']))

    def test_double_switch_keeps_name_and_catalog_conflict(self):
        row=next(r for r in self.captures if r['row']==92)
        s,c=row['seed'],row['candidate']
        result=build_identity_comparison(amazon_title=s['amazon_title'],ebay_title=c['ebay_title'],seed=s,
            evidence=normalize_candidate_evidence(c),policy='phase3_shadow')
        self.assertEqual('double switch',result['amazon']['coreGame'])
        self.assertEqual('double switch',result['ebay']['coreGame'])
        self.assertEqual('review',result['comparisons']['platform']['result'])

    def test_missing_names_never_become_products_or_create_a_match(self):
        for value in ['N/A','None','Unknown','Does not apply','Not Applicable']:
            with self.subTest(value=value):
                result=self.compare('Example Quest PS3','Different Quest PS3',value)
                self.assertNotEqual('match',result['result'])
                self.assertEqual('different quest',result['ebay']['coreGame'])
                self.assertTrue(any('missing-value' in v['reason'] for v in result['ebay']['assignedMetadata']))
        self.assertEqual('unknown',general_product_fields('Unknown')['coreGame'])
        self.assertEqual('none',general_product_fields('None')['coreGame'])

    def test_real_conflicting_names_remain_review(self):
        s,c=inputs('Example Quest PS3','Example Quest PS3',game_name='Different Quest')
        e=normalize_candidate_evidence(c);e['game_name_values']=['N/A','Different Quest','Example Quest']
        result=build_identity_comparison(amazon_title=s['amazon_title'],ebay_title=c['ebay_title'],seed=s,evidence=e,policy='phase3_shadow')
        self.assertEqual('conflicting_sources',result['ebay']['fields']['coreGame']['state'])
        self.assertNotEqual('match',result['result'])

    def test_unresolved_span_is_not_globally_erased(self):
        text, assigned, _=typed_product_text('Quest Game Boy Advance',source='title',side='ebay',evidence={},catalog={})
        self.assertIn('Game Boy Advance',text)
        self.assertEqual([],assigned)

    def test_explicit_platform_conflict_and_unsupported_ds(self):
        result=self.compare('Example Quest PS3','Example Quest Game Boy Advance','Example Quest')
        self.assertNotEqual('match',result['comparisons']['platform']['result'])
        s,c=inputs('Example Quest Nintendo DS','Example Quest Nintendo DS',system='DS',game_name='Example Quest')
        rules=evaluate_static_match_rules(c,s,excluded_keywords=[],allowed_item_location_countries=['US'],identity_policy='phase3_shadow')
        self.assertTrue(any('unsupported sourcing platform' in b for b in rules['hard_blocks']))

    def test_region_and_media_do_not_disappear_as_safeguards(self):
        result=self.compare('Example Quest PS3','Example Quest PS3 PAL','Example Quest',
            aspects=[{'name':'Region Code','value':'PAL'}],catalog={'normalized_platform':'PS 3','normalized_region':'NTSC-U/C'})
        self.assertNotEqual('match',result['result'])
        result=self.compare('Example Quest PC','Example Quest PC CD-ROM','Example Quest',system='PC',
            aspects=[{'name':'Format','value':'DVD-ROM'}],catalog={'normalized_platform':'PC','normalized_format':'dvd_rom'})
        self.assertEqual('review',result['comparisons']['mediaFormat']['result'])
        self.assertNotEqual('match',result['result'])

    def test_meaningful_names_and_distinct_numbers(self):
        for title in ['Wii Play Motion','New Super Mario Bros.','007 Legends','50 Cent: Blood on the Sand',
                      '13 Sentinels: Aegis Rim','7 Days to Die']:
            result=self.compare(title+' PS3',title+' PS3',title)
            self.assertEqual('match',result['comparisons']['coreGame']['result'])
        for a,b in [('1942','1943'),('Final Fantasy X','Final Fantasy X-2'),('FIFA 23','FIFA 24'),('Resident Evil 4','Resident Evil 5')]:
            self.assertNotEqual('match',self.compare(a+' PS3',b+' PS3',b)['result'])

    def test_uncorroborated_phase_two_wording_does_not_resolve_identity(self):
        for extra in ['NEW Example Quest','Example Quest READ DESCRIPTION','Example Quest Ubisoft']:
            self.assertNotEqual('match',self.compare('Example Quest PS3',extra+' PS3',None)['result'])


    def test_new_metadata_does_not_hide_multiple_title_platforms(self):
        result=self.compare('Example Quest SNES','Example Quest PC (Super Nintendo SNES)',
                            'Example Quest',system='Super Nintendo')
        self.assertEqual('review',result['comparisons']['platform']['result'])
        self.assertNotEqual('match',result['result'])

    def test_conflicting_sku_identifier_cannot_corroborate_special_edition(self):
        result=self.compare('Example Quest Deluxe Edition PSP','Example Quest Sony PSP',
            'Example Quest',system='PSP',aspects=[{'name':'UPC','value':'045496731397'}],
            catalog={'normalized_platform':'PSP','normalized_edition':'Deluxe',
                     'relevant_attributes_json':{'product_identifiers':[{'type':'upc','value':'045496960032'}]}})
        self.assertNotEqual('match',result['comparisons']['edition']['result'])
        self.assertNotEqual('match',result['result'])


if __name__=='__main__':
    unittest.main()
