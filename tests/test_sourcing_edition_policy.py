import unittest
from copy import deepcopy
from test_sourcing_phase3 import inputs,SETTINGS
from video_game_identity import build_identity_comparison,evidence_hash
from sourcing_match_rules import normalize_candidate_evidence,evaluate_static_match_rules
from score_sourcing_opportunities import score_candidate
from amazon_sync_catalog_items import edition_catalog_evidence

class EditionPolicyTests(unittest.TestCase):
 def pair(self,a='Standard',b='',game='Dead or Alive 5',description='',features=None,metadata=None):
  s,c=inputs('Dead or Alive 5 '+('' if a=='Standard' else a)+' PS3',f'Dead or Alive 5 {b} PS3 Brand New Factory Sealed',game_name=game)
  s['raw_context_json']['amazon_catalog_identity']={'asin':s['asin'],'normalized_edition':a,'normalized_platform':'PS 3','relevant_attributes_json':metadata or {}}
  c['raw_ebay_json']['localizedAspects'].append({'name':'Platform','value':'Sony PlayStation 3'})
  c['raw_ebay_json']['description']=description
  if features:c['raw_ebay_json']['localizedAspects'].append({'name':'Features','value':features})
  return s,c
 def compare(self,s,c):return build_identity_comparison(amazon_title=s['amazon_title'],ebay_title=c['ebay_title'],seed=s,evidence=normalize_candidate_evidence(c),policy='phase3_shadow')
 def score(self,s,c):return score_candidate(c,s,SETTINGS,matching_context={'offline_identity_policy':'phase3_shadow'})
 def test_standard_synonyms(self):
  s,c=self.pair('Standard Edition','Standard Edition');r=self.compare(s,c)
  self.assertEqual(r['result'],'match');self.assertEqual(r['amazon']['fields']['edition']['state'],'supported')
 def test_omission_is_not_an_observation(self):
  s,c=self.pair();r=self.compare(s,c)
  self.assertEqual(r['result'],'match');self.assertIsNone(r['ebay']['edition']);self.assertTrue(r['comparisons']['edition']['policy']['compatibleOmission'])
  self.assertEqual(self.score(s,c)['status'],'open')
 def test_insufficient_corroboration(self):
  s,c=self.pair(game=None);self.assertEqual(self.compare(s,c)['result'],'review')
 def test_all_rerelease_labels_and_sources(self):
  for label in ('Greatest Hits','Platinum Hits',"Player's Choice",'Nintendo Selects','PlayStation Essentials','PlayStation Hits'):
   for source in ('title','features','description'):
    with self.subTest(label=label,source=source):
     s,c=self.pair(b=label if source=='title' else '',features=label if source=='features' else None,description=f'This is the {label} release.' if source=='description' else '')
     self.assertEqual(self.compare(s,c)['result'],'match')
 def test_rerelease_content_and_packaging_requirements(self):
  for kwargs in ({'description':'Includes additional discs and bonus content.'},{'metadata':{'packaging_requirement':'Black Label'}}):
   s,c=self.pair(b='Greatest Hits',**kwargs);self.assertEqual(self.compare(s,c)['result'],'review')
 def test_explicit_special_conflicts(self):
  for a,b in [('Standard','Deluxe Edition'),('Deluxe Edition','Ultimate Edition'),("Collector's Edition",'Standard Edition')]:
   s,c=self.pair(a,b);self.assertEqual(self.compare(s,c)['result'],'conflict');self.assertTrue(evaluate_static_match_rules(c,s,identity_policy='phase3_shadow')['hard_blocks'])
  s,c=self.pair('Deluxe Edition','Standard Edition',description='This is not the Deluxe Edition.')
  self.assertEqual(self.compare(s,c)['result'],'conflict')
 def test_unresolved_special_is_explained_not_a_hard_mismatch(self):
  for a in ('Deluxe Edition',"Collector's Edition",'Limited Edition','Premium Edition','Gold Edition','Ultimate Edition','Enhanced Edition',"Director's Cut",'Special Edition'):
   with self.subTest(edition=a):
    s,c=self.pair(a);r=self.score(s,c);d=r['matching_diagnostics_json'];self.assertEqual(r['status'],'rejected');self.assertFalse(d['static_rules']['hard_blocks'])
    self.assertEqual(d['presentationDecision']['primaryReason']['code'],'edition_not_corroborated');self.assertIn('not corroborated',d['presentationDecision']['primaryReason']['summary'])
 def test_deluxe_positive_sources(self):
  for source in ('description','specifics','game_name'):
   s,c=self.pair('Deluxe Edition',description='This is the Deluxe Edition.' if source=='description' else '',game='Dead or Alive 5 Deluxe Edition' if source=='game_name' else 'Dead or Alive 5')
   if source=='specifics':c['raw_ebay_json']['localizedAspects'].append({'name':'Edition','value':'Deluxe Edition'})
   self.assertEqual(self.compare(s,c)['result'],'match')
 def test_exact_gtin_not_mpn_corroborates_without_overriding_identity(self):
  s,c=self.pair('Deluxe Edition',metadata={'product_identifiers':[{'type':'upc','value':'010086631128'}]})
  c['raw_ebay_json']['localizedAspects'].append({'name':'UPC','value':'0010086631128'});self.assertEqual(self.compare(s,c)['result'],'match')
  s['raw_context_json']['amazon_catalog_identity']['variation_child_asins']=['OTHER'];self.assertEqual(self.compare(s,c)['result'],'review')
  c['ebay_title']='Dead or Alive 4 PS3';self.assertNotEqual(self.compare(s,c)['result'],'match')
  s,c=self.pair('Deluxe Edition',metadata={'product_identifiers':[{'type':'mpn','value':'010086631128'}]})
  c['raw_ebay_json']['localizedAspects'].append({'name':'MPN','value':'010086631128'});self.assertEqual(self.compare(s,c)['result'],'review')
 def test_collector_manifest_and_contents(self):
  s,c=self.pair("Collector's Edition",description="This is the Collector's Edition. Includes art book and soundtrack.",metadata={'required_contents':['art book','soundtrack']})
  self.assertEqual(self.compare(s,c)['result'],'match')
  c['raw_ebay_json']['description']="Collector's Edition. Soundtrack missing.";self.assertEqual(self.compare(s,c)['result'],'conflict')
  c['raw_ebay_json']['description']="Collector's Edition normally has art book and soundtrack.";self.assertEqual(self.compare(s,c)['result'],'review')
  s,c=self.pair("Collector's Edition",b="Collector's Edition");self.assertEqual(self.compare(s,c)['result'],'review')
 def test_negative_or_multiple_editions(self):
  s,c=self.pair('Deluxe Edition',description='This is not the Deluxe Edition.');self.assertEqual(self.compare(s,c)['result'],'conflict')
  for description in ('Not the Deluxe Edition.','Missing the Collector Edition contents.'):
   s,c=self.pair('Deluxe Edition',description=description);self.assertNotEqual(self.compare(s,c)['result'],'match')
  s,c=self.pair('Deluxe Edition',game='Dead or Alive 5 Deluxe Edition; Dead or Alive 5 Ultimate Edition');self.assertEqual(self.compare(s,c)['result'],'review')
 def test_typed_platform_and_jewel_case(self):
  s,c=self.pair();s['raw_context_json']['amazon_catalog_identity']['normalized_edition']='PlayStation 3';r=self.compare(s,c)
  self.assertIsNone(r['amazon']['edition']);self.assertEqual(r['result'],'match')
  s['raw_context_json']['amazon_catalog_identity']['normalized_edition']='Jewel Case';self.assertEqual(self.compare(s,c)['result'],'review')
  c['raw_ebay_json']['description']='Includes the original jewel case.';self.assertEqual(self.compare(s,c)['result'],'match')
  c['raw_ebay_json']['description']='Jewel case not included.';self.assertEqual(self.compare(s,c)['result'],'review')
 def test_independent_safeguards(self):
  for change in ('platform','region','condition','digital','contents','damage'):
   s,c=self.pair(b='Greatest Hits')
   if change=='platform':s['system']='Xbox 360';s['amazon_title']='Dead or Alive 5 Xbox 360';s['raw_context_json']['amazon_catalog_identity']['normalized_platform']='Xbox 360'
   if change=='region':c['ebay_title']+=' PAL'
   if change=='condition':c['condition_id']='3000';c['condition']='Pre-owned'
   if change=='digital':c['ebay_title']+=' Digital Download Code Only'
   if change=='contents':c['ebay_title']+=' Disc Only'
   if change=='damage':c['raw_ebay_json']['description']='The seal is torn and case is cracked.'
   self.assertTrue(evaluate_static_match_rules(c,s,identity_policy='phase3_shadow')['hard_blocks'],change)
 def test_hash_and_provider_parity(self):
  s,c=self.pair();r=self.compare(s,c);e=normalize_candidate_evidence(c);e.pop('seller_username',None)
  m={'system':s['system'],'raw_context_json':deepcopy(s['raw_context_json']),'catalog':s['raw_context_json']['amazon_catalog_identity']}
  self.assertEqual(r['materialEvidenceHash'],evidence_hash({'asin':s['asin'],'amazonTitle':s['amazon_title'],'catalog':m['catalog'],'referenceMetadata':m,'ebayTitle':c['ebay_title'],'evidence':e}))
  for provider in ('browse','trading'):
   c['raw_ebay_json']['mbopEvidence']={'provider':provider};self.assertEqual(self.compare(s,c)['result'],'match')
 def test_economics_and_dismissal(self):
  s,c=self.pair();c['price']=c['landed_cost']=200;self.assertEqual(self.score(s,c)['status'],'rejected');c['price']=c['landed_cost']=10
  h={(s['asin'],c['ebay_item_id']):{'action_type':'dismissed','status':'dismissed'}}
  r=score_candidate(c,s,SETTINGS,matching_context={'offline_identity_policy':'phase3_shadow'},historical_status_by_key=h);self.assertNotEqual(r['status'],'open')
 def test_catalog_evidence_is_typed_and_market_scoped(self):
  a={'externally_assigned_product_identifier':[{'type':'upc','value':'010086631128','marketplace_id':'US'},{'type':'mpn','value':'fake'}],'included_components':[{'value':'art book','marketplace_id':'US'},{'value':'other','marketplace_id':'UK'}]}
  self.assertEqual(edition_catalog_evidence(a,'US'),{'product_identifiers':[{'type':'upc','value':'010086631128'}],'required_contents':['art book']})
 def test_required_accessory_is_not_satisfied_by_edition_compatibility(self):
  s,c=self.pair();s['amazon_title']='Dead or Alive 5 Bundle with Mat PS3';c['ebay_title']='Dead or Alive 5 Game Only PS3'
  self.assertNotEqual(self.compare(s,c)['result'],'match');self.assertNotEqual(self.score(s,c)['status'],'open')
 def test_named_enhanced_edition_is_not_base_game(self):
  s,c=self.pair('Enhanced Edition',b='Enhanced Edition',game='Dead or Alive 5 Enhanced Edition')
  self.assertEqual(self.compare(s,c)['result'],'match')
  c['ebay_title']='Dead or Alive 5 Standard Edition PS3';c['raw_ebay_json']['localizedAspects'][0]['value']='Dead or Alive 5'
  self.assertEqual(self.compare(s,c)['result'],'conflict')
 def test_affirmed_condition_defects_stay_blocked(self):
  for text in ('Seal is torn.','Cracked case.','Hole punch in the UPC.','The UPC is punched.','Missing plastic seal.'):
   s,c=self.pair(description=text);self.assertTrue(evaluate_static_match_rules(c,s,identity_policy='phase3_shadow')['hard_blocks'],text)
 def test_complete_features_are_not_assumed_standard(self):
  s,c=self.pair(features='Complete Edition');self.assertEqual(self.compare(s,c)['result'],'review')
 def test_numeric_game_identities_remain_intact(self):
  for title in ('007 Legends','50 Cent: Blood on the Sand','13 Sentinels: Aegis Rim','7 Days to Die','1942','NBA 2K26'):
   s,c=inputs(title+' PS3',title+' PS3',game_name=title)
   r=self.compare(s,c)
   if title=='1942':
    self.assertEqual(r['amazon']['installment'],'1942');self.assertEqual(r['ebay']['installment'],'1942')
   else:self.assertEqual(r['comparisons']['coreGame']['result'],'match',title)
 def test_all_twenty_proposed_fixtures_have_executable_coverage(self):
  import json
  from pathlib import Path
  import test_ebay_remaining_availability as availability
  data=json.loads((Path(__file__).resolve().parents[1]/'docs/edition_policy_proposed_fixtures_2026-11-24.json').read_text())
  self.assertEqual(len(data['fixtures']),20)
  for row in data['fixtures']:
   self.assertTrue(hasattr(type(self),row['regression_test']) or hasattr(availability.QuantityTests,row['regression_test']),row['name'])

if __name__=='__main__':unittest.main()
