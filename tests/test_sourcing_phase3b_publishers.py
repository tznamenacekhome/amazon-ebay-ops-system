import json,sys,copy,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations'))
from sourcing_match_rules import normalize_candidate_evidence
from video_game_identity import build_identity_comparison
CASES={r['row']:r for r in json.loads(Path('tests/fixtures/phase3b_captures_20261126.json').read_text())}
class PublisherRoles(unittest.TestCase):
 def compare(self,r):
  c,s=r['candidate'],r['seed'];return build_identity_comparison(amazon_title=s['amazon_title'],ebay_title=c['ebay_title'],seed=s,evidence=normalize_candidate_evidence(c),policy='phase3_shadow')
 def test_actual_supported_corporate_relations(self):
  for n in [50,88,173,175,425]:
   with self.subTest(row=n):
    r=copy.deepcopy(CASES[n]);before=copy.deepcopy(r);i=self.compare(r);self.assertEqual(i['comparisons']['coreGame']['result'],'match');self.assertEqual(r,before)
    self.assertTrue(any(x.get('field')=='publisherAttribution'for side in ['amazon','ebay']for x in i[side]['assignedMetadata']))
 def test_meaningful_branding_is_preserved(self):
  from sourcing_identity_wording import typed_identity_wording
  from video_game_identity import general_product_fields
  for text,publisher in [('Disney Infinity','Disney'),('EA Sports FC 26','Electronic Arts'),('Microsoft Flight Simulator','Microsoft'),("Tom Clancys Splinter Cell",'Ubisoft')]:
   evidence={'game_name_values':[text], 'platform_values':['PC'],'aspects':{'publisher':[publisher]}}
   derived,roles=typed_identity_wording(text,source='title',side='ebay',evidence=evidence,fields=general_product_fields)
   self.assertEqual(general_product_fields(derived)['coreGame'],general_product_fields(text)['coreGame'])
 def test_conflicting_publisher_does_not_supply_alias(self):
  r=copy.deepcopy(CASES[88]);
  for a in r['candidate']['raw_ebay_json']['localizedAspects']:
   if a['name']=='Publisher':a['value']='Ubisoft'
  self.assertNotEqual(self.compare(r)['comparisons']['coreGame']['result'],'match')
 def test_identifier_cannot_override_different_title(self):
  r=copy.deepcopy(CASES[88]);r['candidate']['ebay_title']=r['candidate']['ebay_title'].replace('19','20');self.assertNotEqual(self.compare(r)['comparisons']['coreGame']['result'],'match')
 def test_catalog_attribution_conflict_and_existing_cosmi_control(self):
  r=copy.deepcopy(CASES[425]);r['seed']['raw_context_json']['amazon_catalog_identity']['relevant_attributes_json']['publisher']='Ubisoft';self.assertNotEqual(self.compare(r)['comparisons']['coreGame']['result'],'match')
  r=copy.deepcopy(CASES[425]);r['candidate']['ebay_title']='COSMI Pool Shark PC';
  for a in r['candidate']['raw_ebay_json']['localizedAspects']:
   if a['name']=='Game Name':a['value']='COSMI Pool Shark'
  i=self.compare(r);self.assertEqual(i['comparisons']['coreGame']['result'],'match');self.assertTrue(i['amazon']['coreGame'].startswith('cosmi'))
if __name__=='__main__':unittest.main()
