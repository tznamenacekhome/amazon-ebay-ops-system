import unittest
from copy import deepcopy
from test_sourcing_phase3 import inputs
from sourcing_match_rules import normalize_candidate_evidence,evaluate_static_match_rules
from video_game_identity import build_identity_comparison,reconcile_seller_stock_prefix

class StockPrefixTests(unittest.TestCase):
    def pair(self,code='724b',amazon='Dead or Alive 5',game='Dead or Alive 5',seller='junk-b-gone',platform='Sony PlayStation 3'):
        s,c=inputs(amazon,f'{code}: Dead or Alive 5 for Sony PlayStation 3 PS3 Brand New Factory Sealed',game_name=game)
        c['seller_username']=seller;c['raw_ebay_json']['localizedAspects'].append({'name':'Platform','value':platform})
        return s,c
    def compare(self,s,c):return build_identity_comparison(amazon_title=s['amazon_title'],ebay_title=c['ebay_title'],seed=s,evidence=normalize_candidate_evidence(c),policy='phase3_shadow')
    def test_audited_prefixes_and_provider_parity(self):
        for code in ('724b','835'):
            s,c=self.pair(code)
            for provider in ('browse','trading'):
                c['raw_ebay_json']['mbopEvidence']={'provider':provider}
                r=self.compare(s,c);self.assertNotEqual(r['result'],'conflict');self.assertEqual(r['comparisons']['coreGame']['result'],'match')
                self.assertTrue(r['ebay']['assignedMetadata'])
                self.assertTrue(r['ebay']['fields']['coreGame']['sources'][0]['span'].startswith(code+':'))
    def test_no_general_prefix_stripping(self):
        for kwargs in ({'seller':'different'},{'code':'836'},{'game':'Dead or Alive 4'},{'game':None},{'platform':'Sony PlayStation 4'}):
            s,c=self.pair(**kwargs);self.assertEqual(reconcile_seller_stock_prefix(c['ebay_title'],normalize_candidate_evidence(c))[0],c['ebay_title'])
    def test_unaffected_review_hash_does_not_change_with_seller_attribution(self):
        s,c=self.pair(code='836');first=self.compare(s,c)['materialEvidenceHash']
        c.pop('seller_username');self.assertEqual(first,self.compare(s,c)['materialEvidenceHash'])
    def test_numeric_products_preserved(self):
        for title in ('007 Legends','50 Cent: Blood on the Sand','13 Sentinels: Aegis Rim','7 Days to Die','1942','NBA 2K26','300: March to Glory'):
            s,c=self.pair();c['ebay_title']=title+' PS3';c['raw_ebay_json']['localizedAspects'][0]['value']=title
            self.assertEqual(reconcile_seller_stock_prefix(c['ebay_title'],normalize_candidate_evidence(c))[0],c['ebay_title'])
    def test_wrong_product_and_other_safeguards_remain(self):
        s,c=self.pair(amazon='Dead or Alive 4');self.assertEqual(self.compare(s,c)['result'],'conflict')
        for change in ('condition','region','edition','platform'):
            s,c=self.pair()
            if change=='condition':c['condition']='Pre-owned';c['condition_id']='3000'
            if change=='region':c['ebay_title']+=' PAL'
            if change=='edition':s['amazon_title']='Dead or Alive 5 Ultimate Edition';c['ebay_title']+=' Deluxe Edition'
            if change=='platform':s['system']='Xbox 360';s['amazon_title']='Dead or Alive 5 Xbox 360'
            rules=evaluate_static_match_rules(c,s,identity_policy='phase3_shadow')
            self.assertTrue(rules['hard_blocks'],change)

if __name__=='__main__':unittest.main()
