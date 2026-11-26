import sys
import unittest
from copy import deepcopy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from replay_flipmine_phase2 import mutable_decision_patch, unavailable_decision_patch, write_checkpoint


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

    def test_unavailable_listing_uses_guarded_rejection_and_keeps_history(self):
        op={'status':'open','opportunity_type':'buy_now','profit':10,'roi_percent':100,'matching_diagnostics_json':{'recommendation':'Probable Match'}}
        before=deepcopy(op);patch=unavailable_decision_patch(op,'Confirmed unavailable')
        self.assertEqual(before,op)
        self.assertEqual('rejected',patch['status'])
        self.assertFalse(patch['matching_diagnostics_json']['presentationDecision']['eligible'])
        self.assertTrue(any(c['code']=='listing_availability'and c['blocking']for c in patch['matching_diagnostics_json']['businessEligibilityChecks']))

    def test_unicode_checkpoint_round_trip_is_not_windows_codepage_dependent(self):
        import json
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as directory:
            path=Path(directory)/'pending.json';value={'description':'Sealed \u2713 \u65e5\u672c','request':{'status':'rejected'}}
            write_checkpoint(path,value)
            self.assertEqual(value,json.loads(path.read_text(encoding='utf-8')))


if __name__=='__main__':unittest.main()
