"""Phase 2 uses captured product evidence; no fuzzy or blanket word removal."""
import json
import unittest
from pathlib import Path
from test_sourcing_phase3 import inputs
from sourcing_match_rules import normalize_candidate_evidence, evaluate_static_match_rules
from video_game_identity import build_identity_comparison


class IdentityWordingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=json.loads((Path(__file__).parent/'fixtures/identity_wording_phase2_20261125.json').read_text(encoding='utf-8'))

    def compare(self,a,b,name=None,aspects=(),description='',system='PS 3'):
        s,c=inputs(a,b,game_name=name,system=system)
        c['raw_ebay_json']['localizedAspects'] += [{'name':'Platform','value':system},*aspects]
        c['raw_ebay_json']['description']=description
        return self.captured({'seed':s,'candidate':c})

    def captured(self,row):
        s,c=row['seed'],row['candidate']
        return build_identity_comparison(amazon_title=s['amazon_title'],ebay_title=c['ebay_title'],seed=s,
            evidence=normalize_candidate_evidence(c),policy='phase3_shadow')

    def test_actual_leading_new_and_publisher_captures(self):
        for number in [110,121,275,276,513]:
            row=next(r for r in self.rows if r['label']==f'flipmine:{number}')
            with self.subTest(number=number):
                result=self.captured(row)
                self.assertEqual('match',result['comparisons']['coreGame']['result'])
                self.assertTrue(result['ebay']['assignedMetadata'])
        result=self.compare('Example Quest','Example Quest Capcom','Example Quest',aspects=[{'name':'Publisher','value':'Capcom'}])
        self.assertTrue(any(s.get('field')=='publisherAttribution'for s in result['ebay']['assignedMetadata']))

    def test_meaningful_new_and_publisher_branding_are_preserved(self):
        for a,b,name in [('Super Mario Bros','New Super Mario Bros','Super Mario Bros'),
                         ('Carnival Games','New Carnival Games','Carnival Games'),
                         ('Infinity','Disney Infinity','Infinity')]:
            self.assertNotEqual('match',self.compare(a,b,name,aspects=[{'name':'Publisher','value':b.split()[0]}])['result'])
        self.assertEqual('match',self.compare('COSMI Pool Shark','COSMI Pool Shark','Pool Shark',aspects=[{'name':'Publisher','value':'Cosmi Corporation'}])['comparisons']['coreGame']['result'])
        for title in ['New Super Mario Bros','New Carnival Games','Disney Infinity','Tom Clancy Splinter Cell']:
            self.assertEqual('match',self.compare(title,title,title)['comparisons']['coreGame']['result'])

    def test_unverified_words_codes_subtitles_and_spelling_stay_conflicting(self):
        for title in ['Example Quest Ubisoft','Example Quest A-3036','Example Quest Dark Legacy','Exampel Quest', 'Example Quest 2']:
            self.assertNotEqual('match',self.compare('Example Quest',title,'Example Quest')['result'])
        self.assertNotEqual('match',self.compare('Example Quest','New Example Quest',None)['result'])
        self.assertNotEqual('match',self.compare('Example Quest','Example Quest Capcom','Example Quest',aspects=[{'name':'Publisher','value':'Ubisoft'}])['result'])

    def test_harmless_orthography_and_corroborated_adjacent_installments(self):
        for a,b in [("Cabelas Big Game Hunter","Cabela's Big Game Hunter"),('SmackDown','Smack Down'),('Warzone','War Zone'),('Steelbook','Steel Book'),('SimCity 3000','Sim City 3000')]:
            self.assertEqual('match',self.compare(a,b,b)['comparisons']['coreGame']['result'])
        for a,b in [('Hitman 3','Hitman III 3'),('Suikoden V','Suikoden V 5')]:
            self.assertEqual('match',self.compare(a,b,a)['comparisons']['coreGame']['result'])
        for a,b in [('Final Fantasy X','Final Fantasy X-2'),('FIFA 23','FIFA 24'),('Resident Evil 4','Resident Evil 5'),('1942','1943'),('Hitman 3','Hitman II 3'),('Guitar Hero III','Guitar Hero World Tour')]:
            self.assertNotEqual('match',self.compare(a,b,b)['result'])
        for title in ['007 Legends','50 Cent Blood on the Sand','13 Sentinels Aegis Rim','7 Days to Die']:
            self.assertEqual('match',self.compare(title,title,title)['comparisons']['coreGame']['result'])

    def test_condition_contents_and_incorrect_specifics_remain_visible(self):
        s,c=inputs('Example Quest','New Example Quest READ DESCRIPTION',game_name='Example Quest')
        c['raw_ebay_json']['localizedAspects'] += [{'name':'Platform','value':'PS 3'}]
        c['raw_ebay_json']['description']='Cracked case, seal damage, game only.'
        evidence=normalize_candidate_evidence(c);original=evidence.copy()
        rules=evaluate_static_match_rules(c,s,identity_policy='phase3_shadow')
        self.assertEqual('match',rules['identity_comparison']['comparisons']['coreGame']['result'])
        self.assertTrue(rules['hard_blocks'])
        self.assertEqual(original,evidence)
        self.assertNotEqual('match',self.compare('Just Dance 2018','Just Dance 2014','Just Dance 2018')['result'])

    def test_all_actual_confirmed_mismatches_and_deficient_reference_remain_protected(self):
        negatives=[r for r in self.rows if r.get('assessment')in ['A','D']]
        self.assertEqual(22,len(negatives))
        for row in negatives:
            with self.subTest(label=row['label']):
                self.assertNotEqual('match',self.captured(row)['evidenceDecision']['productIdentityVerdict'])


if __name__=='__main__':unittest.main()
