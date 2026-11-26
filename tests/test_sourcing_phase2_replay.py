import sys
import unittest
from copy import deepcopy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from replay_flipmine_phase2 import mutable_decision_patch


class ReplayLifecycleTests(unittest.TestCase):
    def test_refresh_cannot_reactivate_historical_lifecycles_or_change_history(self):
        for status in ['dismissed','watching','roi_snoozed','inventory_snoozed','purchased_pending_match']:
            scored={'status':status,'opportunity_type':'buy_now','profit':10,'roi_percent':100,
                    'matching_diagnostics_json':{'recommendation':'Probable Match','businessEligibilityChecks':[]}}
            before=deepcopy(scored);patch=mutable_decision_patch(scored)
            self.assertEqual(before,scored)
            self.assertEqual('rejected',patch['status'])
            self.assertEqual(status,patch['matching_diagnostics_json']['normalPipelineLifecycleStatus'])
            self.assertFalse(patch['matching_diagnostics_json']['presentationDecision']['eligible'])
            self.assertTrue(any(c['blocking']and c['result']=='fail'for c in patch['matching_diagnostics_json']['businessEligibilityChecks']))

    def test_mutable_decisions_keep_the_normal_result(self):
        for status in ['open','rejected']:
            scored={'status':status,'matching_diagnostics_json':{}}
            self.assertEqual(scored,mutable_decision_patch(scored))


if __name__=='__main__':unittest.main()
