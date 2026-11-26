"""Synthetic configurations except the explicitly captured Spirit Camera fixture.

TEST ASINs are not assertions about real Amazon retail configurations.
"""
import json
import unittest
from copy import deepcopy
from pathlib import Path
from test_sourcing_phase3 import inputs, SETTINGS
from sourcing_match_rules import normalize_candidate_evidence, evaluate_static_match_rules
from video_game_identity import build_identity_comparison
from score_sourcing_opportunities import score_candidate
from sourcing_package_contents import attach_verified_package, US


class ExactPackageTests(unittest.TestCase):
    def pair(self, game='Guitar Hero', config='software_only', parts=(), description='', asin='B000TEST00'):
        system='Wii' if game.startswith('Wii') else 'PS 3'
        label='Wii' if system=='Wii' else 'PS3'
        s,c=inputs(game+' '+label,game+' '+label+' Brand New Factory Sealed',asin=asin,game_name=game,system=system)
        parts=[dict(name=x,quantity=1) if isinstance(x,str) else x for x in parts]
        attrs={'title':game,'package_configuration':config,'verified_package_evidence':{
            'asin':asin,'marketplace_id':US,'platform':system,'configuration':config,
            'verification_status':'verified','required_contents':parts,
            'sources':[{'kind':'synthetic_test','reference':'NOT PRODUCTION CONFIGURATION'}]}}
        s['raw_context_json']['amazon_catalog_identity']={'asin':asin,'marketplace_id':US,
            'normalized_platform':system,'normalized_edition':'Standard','relevant_attributes_json':attrs}
        c['raw_ebay_json']['description']=description
        return s,c

    def compare(self,s,c):
        return build_identity_comparison(amazon_title=s['amazon_title'],ebay_title=c['ebay_title'],
            seed=s,evidence=normalize_candidate_evidence(c),policy='phase3_shadow')

    def test_separate_asins_and_component_vocabulary_not_franchise_rules(self):
        for game,part in [('Wii Fit','balance board'),('Wii Fit Plus','balance board'),
                ('Guitar Hero','guitar controller'),('Rock Band','guitar controller'),
                ('Dance Dance Revolution','dance mat'),('Skylanders','portal'),
                ('Disney Infinity','base'),('Fitness Game','sensor')]:
            with self.subTest(game=game):
                s,c=self.pair(game)
                self.assertEqual(self.compare(s,c)['result'],'match')
                s2,c2=self.pair(game,'bundle',[part],asin='B000TEST01')
                self.assertEqual(self.compare(s2,c2)['result'],'review')
                c2['raw_ebay_json']['description']='Game only.'
                self.assertEqual(self.compare(s2,c2)['result'],'conflict')
                c2['raw_ebay_json']['description']='Includes original '+part+' for '+('Wii' if game.startswith('Wii') else 'PlayStation 3')+'.'
                self.assertEqual(self.compare(s2,c2)['result'],'match')
                c['raw_ebay_json']['description']=c2['raw_ebay_json']['description']
                self.assertEqual(self.compare(s,c)['result'],'conflict')

    def test_software_only_full_normal_pipeline(self):
        s,c=self.pair('Wii Fit Plus')
        c['ebay_title']='Wii Fit Plus Wii Game Only Brand New Factory Sealed'
        r=score_candidate(c,s,SETTINGS,matching_context={'offline_identity_policy':'phase3_shadow'})
        self.assertEqual(r['status'],'open',r['matching_diagnostics_json']['static_rules']['hard_blocks'])

    def test_hardware_only_and_incompatible_platform(self):
        s,c=self.pair(config='bundle',parts=['guitar controller'],description='Controller only.')
        self.assertEqual(self.compare(s,c)['result'],'conflict')
        c['raw_ebay_json']['description']='Includes original guitar controller for Xbox 360.'
        self.assertEqual(self.compare(s,c)['result'],'conflict')
        c['raw_ebay_json']['description']='Includes guitar controller.'
        self.assertEqual(self.compare(s,c)['result'],'review')

    def test_original_factory_sealed_requires_exact_package_identity(self):
        s,c=self.pair(config='bundle',parts=['guitar controller'],description='Original factory-sealed retail box.')
        c['ebay_title']+=' Bundle'
        # Test package policy directly: unknown exact identifier cannot infer contents.
        self.assertEqual(self.compare(s,c)['comparisons']['edition']['policy']['packagePolicy']['result'],'review')
        attrs=s['raw_context_json']['amazon_catalog_identity']['relevant_attributes_json']
        attrs['product_identifiers']=[{'type':'upc','value':'010086631128'}]
        c['raw_ebay_json']['localizedAspects'].append({'name':'UPC','value':'010086631128'})
        # No broad core-name shortening: put package configuration in a typed
        # listing field instead of inventing a different core product.
        c['ebay_title']=c['ebay_title'].replace(' Bundle','')
        c['raw_ebay_json']['description']='Original factory-sealed retail box. Guitar bundle.'
        result=self.compare(s,c)
        self.assertEqual(result['comparisons']['edition']['policy']['packagePolicy']['result'],'match')
        c['raw_ebay_json']['description']+=' Missing guitar controller.'
        self.assertEqual(self.compare(s,c)['result'],'conflict')

    def test_required_quantity_and_replacement(self):
        s,c=self.pair('Collector Game','required_components',[{'name':'figures','quantity':2}],description='Includes figures.')
        self.assertEqual(self.compare(s,c)['result'],'review')
        c['raw_ebay_json']['description']='Includes 2 figures.'
        self.assertEqual(self.compare(s,c)['result'],'match')
        s,c=self.pair(config='bundle',parts=[{'name':'guitar controller','quantity':1,'model':'model-alfa'}],
                      description='Includes guitar controller for PlayStation 3.')
        self.assertEqual(self.compare(s,c)['result'],'review')
        c['raw_ebay_json']['description']+=' Controller model-alfa.'
        self.assertEqual(self.compare(s,c)['result'],'match')

    def test_identifier_cannot_override_physical_missing(self):
        s,c=self.pair(config='bundle',parts=['guitar controller'],description='No guitar controller included.')
        s['raw_context_json']['amazon_catalog_identity']['relevant_attributes_json']['product_identifiers']=[{'type':'upc','value':'010086631128'}]
        c['raw_ebay_json']['localizedAspects'].append({'name':'UPC','value':'010086631128'})
        self.assertEqual(self.compare(s,c)['result'],'conflict')

    def test_actual_spirit_and_positive_negative_variants(self):
        row=json.loads((Path(__file__).parent/'fixtures/spirit_camera_captured_20261124.json').read_text())
        s,c=deepcopy(row['seed']),deepcopy(row['candidate'])
        result=self.compare(s,c)
        self.assertEqual(result['result'],'review')
        self.assertIn('AR book',result['comparisons']['edition']['reason'])
        for description,outcome in [('Includes original AR book.','match'),
                ('Original AR book not included.','conflict'),
                ('Includes printable AR book.','review'),
                ('Includes replacement AR book.','review'),
                ('Includes AR book. AR book is a reproduction.','review'),
                ('Original factory-sealed retail package.','review')]:
            with self.subTest(description=description):
                c['raw_ebay_json']['description']=description
                self.assertEqual(self.compare(s,c)['result'],outcome)
        # Synthetic identifier: not a claimed real Spirit Camera UPC.
        s['raw_context_json']['amazon_catalog_identity']['relevant_attributes_json']['product_identifiers']=[{'type':'upc','value':'010086631128'}]
        c['raw_ebay_json']['localizedAspects'].append({'name':'UPC','value':'010086631128'})
        c['raw_ebay_json']['description']='Original factory-sealed retail package.'
        self.assertEqual(self.compare(s,c)['result'],'match')
        c['raw_ebay_json']['description']='Includes original AR book. No AR book damage.'
        self.assertEqual(self.compare(s,c)['result'],'match')

    def test_cross_asin_marketplace_platform_and_conflicting_catalog(self):
        s,c=self.pair(config='software_only')
        attrs=s['raw_context_json']['amazon_catalog_identity']['relevant_attributes_json']
        attrs['verified_package_evidence']['required_contents']=[{'name':'balance board'}]
        self.assertEqual(self.compare(s,c)['result'],'review')
        for change in ('asin','marketplace_id','normalized_platform'):
            catalog={'asin':'B006Y76HY6','marketplace_id':US,'normalized_platform':'3DS',
                     'relevant_attributes_json':{'title':'Spirit Camera: The Cursed Memoir'}}
            catalog[change]={'asin':'OTHER','marketplace_id':'UK','normalized_platform':'PS 3'}[change]
            self.assertNotIn('verified_package_evidence',attach_verified_package(catalog,catalog['asin'])['relevant_attributes_json'])

    def test_ordinary_no_manifest_stays_ordinary(self):
        s,c=inputs('Ordinary Game PS3','Ordinary Game PS3 Brand New',game_name='Ordinary Game')
        self.assertEqual(self.compare(s,c)['result'],'match')
        c['raw_ebay_json']['description']='Check out our other listings & BUNDLE!'
        self.assertEqual(self.compare(s,c)['result'],'match')

    def test_conflicting_verified_exact_asin_sources_remain_review(self):
        row=json.loads((Path(__file__).parent/'fixtures/spirit_camera_captured_20261124.json').read_text())
        s,c=deepcopy(row['seed']),deepcopy(row['candidate'])
        attrs=s['raw_context_json']['amazon_catalog_identity']['relevant_attributes_json']
        attrs['verified_package_evidence']={'asin':s['asin'],'marketplace_id':US,
            'verification_status':'verified','configuration':'software_only',
            'required_contents':[],'sources':[{'kind':'synthetic_conflicting_source'}]}
        self.assertEqual(self.compare(s,c)['result'],'review')

    def test_unverified_inferred_bundle_manifest_cannot_clear_hardware(self):
        s,c=self.pair(config='bundle',description='Includes guitar controller for PlayStation 3.')
        attrs=s['raw_context_json']['amazon_catalog_identity']['relevant_attributes_json']
        attrs.pop('verified_package_evidence')
        s['raw_context_json']['amazon_catalog_identity']['normalized_edition']='Guitar Bundle'
        result=self.compare(s,c)
        self.assertEqual(result['comparisons']['edition']['policy']['packagePolicy']['result'],'review')


if __name__=='__main__':
    unittest.main()
