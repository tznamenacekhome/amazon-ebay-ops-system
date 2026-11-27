"""Known failing release guards. Phase 3B must not deploy until these pass.
Actual retained product-specific prose; no photograph inspection or live requests.
"""
import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations'))
from sourcing_match_rules import evaluate_static_match_rules
CASES={r['row']:r for r in json.loads(Path('tests/fixtures/phase3b_condition_gate_failures_20261126.json').read_text())}
class Phase3BConditionReleaseGate(unittest.TestCase):
 def require_review(self,number):
  r=CASES[number];s=evaluate_static_match_rules(r['candidate'],r['seed'],identity_policy='phase3_shadow')
  self.assertEqual(s['condition_review']['result'],'review')
  self.assertNotEqual(s['condition_mismatch']['result'],'blocked')
  self.assertEqual(s['identity_comparison']['evidenceDecision']['productIdentityVerdict'],'match')
  self.assertTrue(s['condition_review']['evidence'])
 def test_actual_plural_tears_in_cello_wrap_cannot_auto_pass_new(self):self.require_review(50)
 def test_actual_holes_in_seal_cannot_auto_pass_without_scope_review(self):self.require_review(63)
if __name__=='__main__':unittest.main()
