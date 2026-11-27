import copy,json,unittest
from pathlib import Path
from integrations.sourcing_decision_trace import enrich_sourcing_diagnostics
class Phase3AReasons(unittest.TestCase):
 def test_eight_actual_compact_reasons_preserve_decisions(self):
  cases=json.loads(Path('tests/fixtures/phase3a_exclusion_reasons_20261126.json').read_text())
  self.assertEqual(len(cases),8)
  for c in cases:
   with self.subTest(row=c['row']):
    before=copy.deepcopy(c);d=enrich_sourcing_diagnostics(c['diagnostics'],status=c['status'],opportunity_type=c['opportunity_type'],profit=c['profit'],roi_percent=c['roi_percent'])
    p=d['presentationDecision'];self.assertFalse(p['eligible']);self.assertEqual(p['finalStatus'],c['status']);self.assertEqual(p['finalOpportunityType'],c['opportunity_type'])
    self.assertEqual(p['primaryReason']['code'],'duplicate_history'if c['row']==68 else'condition_unacceptable')
    self.assertNotIn('mapped rule',p['primaryReason']['summary']);self.assertEqual(c,before)
    if c['row']==68:self.assertIn('dismissed',p['primaryReason']['summary'])
    else:
     for hit in c['diagnostics']['static_rules']['condition_mismatch']['hits']:self.assertIn(hit,p['primaryReason']['summary'])
     self.assertIn('condition_mismatch',p['primaryReason']['diagnosticKeys'])
    old={r['code']for r in c['diagnostics']['presentationDecision']['secondaryReasons']};new={r['code']for r in p['secondaryReasons']};self.assertTrue(old<=new,(old,new))
if __name__=='__main__':unittest.main()
