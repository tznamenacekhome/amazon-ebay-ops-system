import json
from copy import deepcopy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations'))
from validate_sourcing_adjudicated_ground_truth import select_evidence, replay, validate
from video_game_identity import build_identity_comparison, split_game_names, source_name_relation
from sourcing_match_rules import normalize_candidate_evidence
from matching_feedback import recheck_proposed_identity

QUEUE=json.loads(Path('web/app/api/sourcing/adjudication/queue.json').read_text())
CASES=json.loads(Path('tests/fixtures/sourcing_adjudicated_identity_regressions_2026-09-13.json').read_text())['cases']


def action(row, verdict='correct', *, variation=True, attested=True, corrections=None, timestamp='2026-09-14T03:00:00+00:00', identity='test-action', relationships=None, flags=None):
    ctx={'queueId':row['queueId'],'queueSnapshotHash':row['snapshotHash'],'sourceSnapshotId':row['sourceSnapshotId'],
        'pair':{'asin':row['asin'],'ebayItemId':row['ebayItemId'],'variationId':row['variationId']},
        'source':'identity_adjudication_queue','snapshotPolicy':'frozen_historical','actor':'synthetic-test-reviewer',
        'requestHash':'test-request-hash','requestId':identity,'snapshotId':'snapshot-'+identity,'recordedAt':timestamp,
        'identityAttested':attested,'variationVerified':variation,
        'matchingFeedback':{'version':'matching_feedback_v3','evidenceProvenance':'explicit','pairVerdict':verdict,
            'corrections':corrections or [],'flaggedFields':flags or [],'fieldRelationships':relationships or []}}
    a={'action_id':identity,'asin':row['asin'],'ebay_item_id':row['ebayItemId'],'created_at':timestamp,
        'listing_snapshot_id':'snapshot-'+identity,'raw_action_context':ctx}
    s={'action_id':identity,'listing_snapshot_id':'snapshot-'+identity,'asin':row['asin'],'ebay_item_id':row['ebayItemId'],
        'raw_context_json':deepcopy(ctx),'captured_at':timestamp,'amazon_title':row['reference']['amazon_title'],
        'amazon_system':row['reference']['system'],'ebay_title':row['candidate']['ebay_title'],
        'raw_ebay_json':deepcopy(row['candidate']['raw_ebay_json'])}
    return a,s


class AdjudicatedTruthTests(unittest.TestCase):
    def setUp(self):self.row=deepcopy(QUEUE[2])
    def select(self, actions, snapshots, row=None, queue=None):
        return select_evidence(row or self.row,actions,queue or [self.row],{s['listing_snapshot_id']:s for s in snapshots})
    def test_missing_variation_is_not_tier_a(self):
        a,s=action(self.row,variation=False);v=self.select([a],[s]);self.assertEqual('unresolved',v['class']);self.assertIn('verification unchecked',v['qualificationReasons'][0])
    def test_positive_with_exact_scope_is_tier_a(self):
        a,s=action(self.row);self.assertEqual('tier_a_positive',self.select([a],[s])['class'])
    def test_negative_requires_no_positive_assertions(self):
        a,s=action(self.row,'incorrect',variation=False,attested=False);self.assertEqual('verified_negative',self.select([a],[s])['class'])
    def test_unsure_supersedes_positive_and_retains_history(self):
        a,s=action(self.row);b,t=action(self.row,'unsure',timestamp='2026-09-14T03:01:00+00:00',identity='newer');v=self.select([a,b],[s,t]);self.assertEqual('unsure',v['verdict']);self.assertEqual('unresolved',v['class']);self.assertEqual(2,len(v['lineage']))
    def test_invalid_newer_verdict_does_not_fall_back(self):
        a,s=action(self.row);b,t=action(self.row,timestamp='2026-09-14T03:01:00+00:00',identity='newer');b['raw_action_context']['snapshotId']='wrong';v=self.select([a,b],[s,t]);self.assertEqual('newer',v['verdictActionId']);self.assertEqual('unresolved',v['class'])
    def test_newer_legacy_id_cannot_silently_leave_old_positive_current(self):
        a,s=action(self.row);b,t=action(self.row,'incorrect',timestamp='2026-09-14T03:01:00+00:00',identity='newer');b['ebay_item_id']=self.row['ebayLegacyItemId'];v=self.select([a,b],[s,t]);self.assertEqual('newer',v['verdictActionId']);self.assertEqual('unresolved',v['class'])
    def test_compatible_qualifies_without_rewriting_values(self):
        row=deepcopy(QUEUE[1]);a,s=action(row,relationships=[{'field':'platform','operatorRelationship':'compatible'}]);v=self.select([a],[s],row,[row]);self.assertEqual('tier_a_positive',v['class']);r=replay(row,v,[a],{s['listing_snapshot_id']:s},'2026-09-14T04:00:00+00:00');self.assertEqual('Xbox One',r['withCorrections']['amazon']['platform']);self.assertEqual('Xbox Series X',r['withCorrections']['ebay']['platform']);self.assertFalse(r['pairVerdictUsedAsInput']);self.assertEqual('non-match',r['identityVerdict'])
    def test_invalid_relationship_cannot_qualify(self):
        a,s=action(self.row,relationships=[None]);self.assertEqual('unresolved',self.select([a],[s])['class'])
    def test_newer_wrong_flag_without_replacement(self):
        a,s=action(self.row);b,t=action(self.row,'not_provided',timestamp='2026-09-14T03:01:00+00:00',identity='newer',flags=['coreGame']);v=self.select([a,b],[s,t]);self.assertEqual('unresolved',v['class']);r=replay(self.row,v,[a,b],{x['listing_snapshot_id']:x for x in [s,t]},'2026-09-14T04:00:00+00:00');self.assertFalse(r['normalBusinessEvaluationEligible']);self.assertEqual(['coreGame'],r['unreliableFieldsWithoutReplacement']);self.assertEqual([],r['correctionApplication'])
    def test_newer_empty_flags_supersede_old_flags(self):
        a,s=action(self.row,flags=['edition']);b,t=action(self.row,timestamp='2026-09-14T03:01:00+00:00',identity='newer');self.assertEqual([],self.select([a,b],[s,t])['flags'])
    def test_explicit_asin_scope_does_not_propagate_pair_correction(self):
        corr=[{'side':'amazon','field':'edition','scope':'asin','state':'value','value':'Deluxe Edition'}, {'side':'ebay','field':'coreGame','scope':'pair','state':'value','value':'Different game'}]
        a,s=action(self.row,corrections=corr);sibling=deepcopy(self.row);sibling.update(queueId='sibling',ebayItemId='v1|999999999999|0');sibling['candidate']['ebay_item_id']=sibling['ebayItemId'];v=self.select([a],[s],sibling,[self.row,sibling]);self.assertIsNone(v['verdict']);self.assertEqual(1,len(v['corrections']));r=replay(sibling,v,[a],{s['listing_snapshot_id']:s},'2026-09-14T04:00:00+00:00');self.assertEqual('Deluxe Edition',r['withCorrections']['amazon']['edition']);self.assertNotEqual('Different game',r['withCorrections']['ebay']['coreGame'])
    def test_different_asin_does_not_inherit_negative(self):
        a,s=action(self.row,'incorrect');other=deepcopy(self.row);other['asin']='B000OTHER0';v=self.select([a],[s],other,[self.row,other]);self.assertIsNone(v['verdict']);self.assertEqual([],v['corrections'])
    def test_changed_snapshot_correction_cannot_apply(self):
        a,s=action(self.row,corrections=[{'side':'ebay','field':'coreGame','scope':'pair','state':'value','value':'Wrong injected product'}]);s['ebay_title']='Changed snapshot';v=self.select([a],[s]);r=replay(self.row,v,[a],{s['listing_snapshot_id']:s},'2026-09-14T04:00:00+00:00');self.assertFalse(r['correctionScopeGatePassed']);self.assertNotEqual('Wrong injected product',r['withCorrections']['ebay']['coreGame'])
    def test_observed_exact_pairs_are_regressions_without_verdict_override(self):
        for c in CASES:
            with self.subTest(asin=c['asin']):
                comparison=build_identity_comparison(amazon_title=c['reference']['amazon_title'],ebay_title=c['candidate']['ebay_title'],seed=c['reference'],evidence=normalize_candidate_evidence(c['candidate']),policy='phase3_shadow')
                result=recheck_proposed_identity(comparison,c['corrections'])['proposed']
                self.assertEqual(c['expectedShadowVerdict'],result['evidenceDecision']['productIdentityVerdict'])
    def test_held_out_numeric_position_requires_corroboration(self):
        def compare(game_name):
            return build_identity_comparison(amazon_title='Crystal Harbor 7 PS4',ebay_title='Crystal 7 Harbor PS4',seed={'asin':'B000TEST00'},evidence={'game_names':[game_name]} if game_name else {},policy='phase3_shadow')
        # normalize_candidate_evidence uses game_name_values, not a made-up metadata field.
        evidence=normalize_candidate_evidence({'raw_ebay_json':{'localizedAspects':[{'name':'Game Name','value':'Crystal Harbor 7'}]}})
        yes=build_identity_comparison(amazon_title='Crystal Harbor 7 PS4',ebay_title='Crystal 7 Harbor PS4',seed={'asin':'B000TEST00'},evidence=evidence,policy='phase3_shadow');self.assertEqual('match',yes['result']);self.assertNotEqual('match',compare(None)['result'])
        self.assertNotEqual('same_typed_installment',source_name_relation('crystal 7 harbor','harbor crystal 7'));self.assertNotEqual('same_typed_installment',source_name_relation('crystal 7 harbor','crystal harbor 8'));self.assertNotEqual('same_typed_installment',source_name_relation('crystal 7 harbor','crystal harbor 7 deluxe'))
    def test_parenthesized_comma_is_not_an_installment(self):
        self.assertEqual(['Crystal Harbor (Wii, 2010)','Crystal Harbor'],split_game_names('Crystal Harbor (Wii, 2010), Crystal Harbor'))
        evidence=normalize_candidate_evidence({'raw_ebay_json':{'localizedAspects':[{'name':'Game Name','value':'Crystal Harbor (Wii, 2010)'}]}})
        result=build_identity_comparison(amazon_title='Crystal Harbor Wii',ebay_title='Crystal Harbor (Wii, 2010)',seed={'asin':'B000TEST00'},evidence=evidence,policy='phase3_shadow');self.assertEqual('match',result['result']);self.assertIsNone(result['ebay']['installment'])
    def test_core_correction_does_not_certify_omitted_installment(self):
        original=build_identity_comparison(amazon_title='Crystal Harbor 7 PS4',ebay_title='Crystal Harbor PS4',seed={'asin':'B000TEST00'},policy='phase3_shadow')
        corrected=recheck_proposed_identity(original,[{'side':'amazon','field':'coreGame','scope':'pair','state':'value','value':'crystal harbor'}])['proposed'];self.assertEqual('review',corrected['result']);self.assertEqual('7',corrected['amazon']['installment']);self.assertIsNone(corrected['ebay']['installment']);self.assertIn('installment',corrected['reason'])


if __name__=='__main__':unittest.main()
