import copy,unittest
import test_sourcing_phase3b_publishers as pub
from sourcing_match_rules import evaluate_static_match_rules
class ContextualKeywords(unittest.TestCase):
 def evaluate(self,n,extra='',title=None):
  r=copy.deepcopy(pub.CASES[n]);c,s=r['candidate'],r['seed']
  if title is not None:c['ebay_title']=title
  c['raw_ebay_json']['description']=(c['raw_ebay_json'].get('description')or'')+extra
  return evaluate_static_match_rules(c,s,identity_policy='phase3_shadow')
 def test_actual_named_and_scoped_words(self):
  for n,term in [(481,'rune'),(438,'gems'),(400,'carry')]:
   with self.subTest(row=n):self.assertNotIn(term,self.evaluate(n)['digital_download']['hits'])
  self.assertNotIn('helmet',self.evaluate(492)['not_game']['hits'])
  r=self.evaluate(546);self.assertNotIn('toy',r['not_game']['hits']);self.assertEqual(r['contents_review']['result'],'review')
 def test_real_digital_currency_and_service_hits_remain(self):
  for n,text,term in [(481,' Buy 1000 runes delivered to your account.','runes'),(438,' Buy gems:10000 gems only.','gems'),(400,' We offer a carry service through the game.','carry')]:
   with self.subTest(term=term):self.assertIn(term,self.evaluate(n,text)['digital_download']['hits'])
 def test_actual_independent_blocks_remain(self):
  self.assertEqual(self.evaluate(504)['condition_mismatch']['result'],'blocked')
  self.assertEqual(self.evaluate(400)['incomplete_listing']['result'],'blocked')
  self.assertNotEqual(self.evaluate(481)['identity_comparison']['evidenceDecision']['productIdentityVerdict'],'match')
  self.assertNotEqual(self.evaluate(492)['identity_comparison']['evidenceDecision']['productIdentityVerdict'],'match')
 def test_real_accessories_and_missing_kit_software_remain(self):
  self.assertIn('helmet',self.evaluate(492,title='Frogger helmet replacement accessory only')['not_game']['hits'])
  r=self.evaluate(546,' Replacement cardboard only. No game or software included.');self.assertIn('toy',r['not_game']['hits'])
 def test_style_cleanup_and_testing_remain_unchanged(self):
  r=self.evaluate(504);self.assertIn('visible cracks on case',r['condition_mismatch']['hits'])
if __name__=='__main__':unittest.main()
