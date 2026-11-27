import copy,unittest
import test_sourcing_phase3b_publishers as pub
CASES=pub.CASES
from sourcing_match_rules import evaluate_static_match_rules
class CompositeRoles(unittest.TestCase):
 compare=pub.PublisherRoles.compare
 def test_actual_composite_roles_and_nonadjacent_installment(self):
  for n in [19,20,280,520,470]:
   with self.subTest(row=n):
    i=self.compare(copy.deepcopy(CASES[n]));self.assertEqual(i['comparisons']['coreGame']['result'],'match');self.assertTrue(i['ebay']['assignedMetadata'])
 def test_wrong_installment_and_unverified_codes_preserved(self):
  for n in [520,470]:
   r=copy.deepcopy(CASES[n]);r['candidate']['ebay_title']+=' 1943';self.assertNotEqual(self.compare(r)['comparisons']['coreGame']['result'],'match')
  r=copy.deepcopy(CASES[19]);r['candidate']['ebay_title']+=' A-3036';self.assertNotEqual(self.compare(r)['comparisons']['coreGame']['result'],'match')
 def test_cib_and_wording_never_waive_used_damage_or_contents(self):
  for text in ['Pre-owned.','Case has cracks.','Disc only.','Opened to test this game.']:
   r=copy.deepcopy(CASES[280]);r['candidate']['raw_ebay_json']['description']=text
   st=evaluate_static_match_rules(r['candidate'],r['seed'],identity_policy='phase3_shadow');self.assertTrue(st['hard_blocks'],text)
 def test_dusk_and_monopoly_are_not_fuzzily_corrected(self):
  from sourcing_identity_wording import orthographic_text
  self.assertEqual(orthographic_text('Dusk Driver MOLOPOLY')[0],'Dusk Driver MOLOPOLY')
if __name__=='__main__':unittest.main()
