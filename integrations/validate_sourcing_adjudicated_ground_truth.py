"""Offline exact-pair adjudication gate. No database/client, writes or activation.

Verdicts label the corpus; they are NEVER supplied to the matcher as answers.
Only independently validated scoped corrections enter the replay inputs.
"""
from __future__ import annotations
import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path

from matching_feedback import apply_scoped_reviews
from sourcing_match_rules import evaluate_static_match_rules, normalize_candidate_evidence
from video_game_identity import build_identity_comparison, IDENTITY_FIELDS, evidence_hash


def instant(value):
    return datetime.fromisoformat(str(value).replace('Z', '+00:00'))


def ordered(actions):
    return sorted(actions, key=lambda a: (instant(a['created_at']), a['action_id']), reverse=True)


def action_errors(action, queue, snapshots):
    """Validate the origin pair, not the destination of a scoped ASIN correction."""
    ctx = action.get('raw_action_context') or {}
    origin = next((q for q in queue if q['queueId'] == ctx.get('queueId')), None)
    snap = snapshots.get(action.get('listing_snapshot_id'))
    errors = []
    if not origin or not snap:
        return ['missing frozen origin or linked review snapshot']
    expected_pair = (origin['asin'], origin['ebayItemId'], origin['variationId'])
    actual_pair = ctx.get('pair') or {}
    if (action.get('asin'), action.get('ebay_item_id'), actual_pair.get('variationId')) != expected_pair:
        errors.append('action exact pair/variation differs from frozen origin')
    if (actual_pair.get('asin'), actual_pair.get('ebayItemId'), actual_pair.get('variationId')) != expected_pair:
        errors.append('context exact pair/variation differs from frozen origin')
    if ctx.get('source') != 'identity_adjudication_queue' or ctx.get('snapshotPolicy') != 'frozen_historical':
        errors.append('unverified workflow/source policy')
    if ctx.get('queueSnapshotHash') != origin['snapshotHash'] or ctx.get('sourceSnapshotId') != origin['sourceSnapshotId']:
        errors.append('frozen evaluation/source snapshot mismatch')
    if not ctx.get('actor') or not ctx.get('requestHash') or ctx.get('requestId') != action.get('action_id'):
        errors.append('missing actor/request provenance')
    if (snap.get('asin'), snap.get('ebay_item_id'), snap.get('action_id')) != (action['asin'], action['ebay_item_id'], action['action_id']):
        errors.append('review snapshot is not action/exact-pair linked')
    if snap.get('raw_context_json') != ctx or ctx.get('snapshotId') != snap.get('listing_snapshot_id'):
        errors.append('action/snapshot context mismatch')
    try:
        if instant(ctx.get('recordedAt')) != instant(action['created_at']) or instant(snap.get('captured_at')) != instant(action['created_at']):
            errors.append('action/snapshot timestamp mismatch')
    except (TypeError, ValueError):
        errors.append('invalid action/snapshot timestamp')
    feedback = ctx.get('matchingFeedback') or {}
    if feedback.get('version') != 'matching_feedback_v3' or feedback.get('evidenceProvenance') != 'explicit':
        errors.append('not explicit v3 evidence')
    if (snap.get('amazon_title'), snap.get('amazon_system'), snap.get('ebay_title'), snap.get('raw_ebay_json')) != (
            origin['reference'].get('amazon_title'), origin['reference'].get('system'), origin['candidate']['ebay_title'], origin['candidate']['raw_ebay_json']):
        errors.append('reviewed material differs from frozen full source')
    return errors


def select_evidence(row, actions, queue, snapshots):
    actions = ordered(actions)
    exact = [a for a in actions if (a['asin'], a['ebay_item_id']) == (row['asin'], row['ebayItemId'])]
    def possibly_same_listing(action):
        other=action['ebay_item_id']; current=row['ebayItemId']
        legacy=lambda value: value.split('|')[1] if value.startswith('v1|') else value
        return action['asin']==row['asin'] and (other==current or
            legacy(other)==legacy(current) and not (other.startswith('v1|') and current.startswith('v1|')))
    candidates=[a for a in actions if possibly_same_listing(a)]
    verdict = next((a for a in candidates if a['raw_action_context'].get('matchingFeedback', {}).get('pairVerdict') in ('correct', 'incorrect', 'unsure')), None)
    corrections, flags, relationships, seen = [], [], [], set()
    flags_seen = relationships_seen = False
    problems = []
    for action in actions:
        ctx = action['raw_action_context']
        feedback = ctx.get('matchingFeedback') or {}
        is_exact = (action['asin'], action['ebay_item_id']) == (row['asin'], row['ebayItemId'])
        if action['asin'] != row['asin']:
            continue
        if is_exact:
            if not flags_seen and ctx.get("reviewKind") != "variation_scope":
                flags = [{'field':f, 'actionId':action['action_id']} for f in feedback.get('flaggedFields',[])]
                flags_seen = True
            if not relationships_seen and feedback.get('fieldRelationships'):
                for r in feedback['fieldRelationships']:
                    errs = action_errors(action,queue,snapshots)
                    if not isinstance(r,dict) or r.get('field')!='platform' or r.get('operatorRelationship') not in ('match','compatible','wrong','unknown'):
                        errs.append('invalid platform relationship')
                    relationships.append({**(r if isinstance(r,dict) else {}),'actionId':action['action_id'],
                        'actor':ctx.get('actor'),'timestamp':action['created_at'],'provenanceErrors':errs})
                    problems.extend(errs)
                relationships_seen = True
        for correction in feedback.get('corrections') or []:
            if not is_exact and not (correction.get('side') == 'amazon' and correction.get('scope') == 'asin'):
                continue
            key = (correction.get('side'), correction.get('field'))
            if key in seen:
                continue  # Never fall back to older evidence after invalid newer evidence.
            seen.add(key)
            errs = action_errors(action, queue, snapshots)
            if correction.get('scope') not in ('pair','asin') or correction.get('scope') == 'asin' and correction.get('side') != 'amazon':
                errs.append('invalid correction scope')
            if correction.get('field') not in IDENTITY_FIELDS:
                errs.append('unsupported correction field')
            corrections.append({**correction,'actionId':action['action_id'],'actor':ctx.get('actor'),
                'timestamp':action['created_at'],'snapshotId':action['listing_snapshot_id'],
                'evaluationId':ctx.get('queueSnapshotHash'),'provenanceErrors':errs})
            problems.extend(errs)
    ctx = verdict['raw_action_context'] if verdict else {}
    pair_verdict = ctx.get('matchingFeedback', {}).get('pairVerdict')
    verdict_errors = action_errors(verdict, queue, snapshots) if verdict else ['no saved pair verdict']
    if verdict and verdict['ebay_item_id']!=row['ebayItemId']:
        verdict_errors.append('newer listing-level verdict does not establish exact stored variation scope')
    newer = [a['action_id'] for a in actions if verdict and instant(a['created_at']) > instant(verdict['created_at']) and (
        any(c['actionId'] == a['action_id'] for c in corrections) or a in exact and (
            a['raw_action_context'].get('matchingFeedback', {}).get('flaggedFields') or
            a['raw_action_context'].get('matchingFeedback', {}).get('fieldRelationships')))]
    variation_action = next((a for a in candidates if a['raw_action_context'].get('reviewKind') == 'variation_scope'
        or a['raw_action_context'].get('matchingFeedback', {}).get('pairVerdict') in ('correct','incorrect','unsure')), None)
    variation_ctx = variation_action['raw_action_context'] if variation_action else {}
    variation_errors = action_errors(variation_action, queue, snapshots) if variation_action else ['no variation evidence']
    if variation_action and verdict and variation_action['action_id'] != verdict['action_id']:
        if variation_ctx.get('reviewKind') != 'variation_scope' or variation_ctx.get('variationTargetActionId') != verdict['action_id']:
            variation_errors.append('variation evidence does not reference current confirmation')
    resolution = {'operator_confirmed_not_applicable':'not_applicable','verified_stored_variation':'verified'}.get(
        variation_ctx.get('variationResolution'), variation_ctx.get('variationResolution','unknown'))
    stored = row.get('variationId')
    browse = row['ebayItemId'].split('|')[-1] if row['ebayItemId'].startswith('v1|') else None
    exact_variation = stored if stored and stored != '0' else browse if browse and browse != '0' else None
    if stored and stored != '0' and browse and browse != '0' and stored != browse:
        exact_variation = None
    qualification = list(verdict_errors)
    if pair_verdict == 'correct':
        if ctx.get('identityAttested') is not True:
            qualification.append('exact product identity was not explicitly attested')
        qualification.extend(variation_errors)
        if variation_ctx.get('variationVerified') is not True:
            qualification.append('variation scope/not-applicable verification unchecked')
        if resolution not in ('not_applicable','verified'):
            qualification.append('variation resolution is unknown or invalid')
        if resolution == 'verified' and not exact_variation:
            qualification.append('exact verified variation identity missing or inconsistent')
        if newer:
            qualification.append('newer correction/relationship evidence requires renewed pair confirmation')
        qualification.extend(problems)
    informational = row['asin'] == 'B072JZB85B' and row['ebayLegacyItemId'] == '233733278405'
    ground_class = 'informational' if informational else 'tier_a_positive' if pair_verdict == 'correct' and not qualification else 'verified_negative' if pair_verdict == 'incorrect' and not verdict_errors else 'unqualified_confirmation' if pair_verdict == 'correct' else 'unresolved'
    return {'class':ground_class,'verdict':pair_verdict,'verdictActionId':verdict['action_id'] if verdict else None,
        'verdictTimestamp':verdict['created_at'] if verdict else None,'actor':ctx.get('actor'),'notes':ctx.get('notes'),
        'snapshotId':verdict['listing_snapshot_id'] if verdict else None,'evaluationId':ctx.get('queueSnapshotHash'),
        'identityAttested':ctx.get('identityAttested'),'variationVerified':variation_ctx.get('variationVerified'),
        'variationResolution':resolution,'exactVariationId':exact_variation,
        'variationProvenance':{'actionId':variation_action['action_id'] if variation_action else None,'actor':variation_ctx.get('actor'),
            'timestamp':variation_action['created_at'] if variation_action else None,'targetActionId':variation_ctx.get('variationTargetActionId'),
            'provenanceErrors':variation_errors},'source':ctx.get('source'),
        'qualificationReasons':qualification if ground_class in ('unresolved','unqualified_confirmation') else ['intentional informational mixed-lot exclusion'] if informational else ['verified exact-pair provenance; positive identity and variation assertions present'] if ground_class == 'tier_a_positive' else ['verified exact-pair negative; positive/variation assertions not required'],
        'verdictProvenanceErrors':verdict_errors,'corrections':corrections,'flags':flags,'relationships':relationships,
        'newerEvidenceActionIds':newer,'lineage':[{'actionId':a['action_id'],'timestamp':a['created_at'],
            'verdict':a['raw_action_context'].get('matchingFeedback', {}).get('pairVerdict'),
            'snapshotId':a['listing_snapshot_id'],'hash':evidence_hash(a)} for a in exact]}


def replay(row, evidence, actions, snapshots, cutoff):
    seed, candidate = deepcopy(row['reference']), deepcopy(row['candidate'])
    candidate['asin'] = row['asin']
    # All original metadata is retained. Do not supply pair truth to this test.
    reviews = []
    selected = {(c['actionId'],c['side'],c['field']) for c in evidence['corrections'] if not c['provenanceErrors']}
    for action in actions:
        applied = [c for c in action['raw_action_context'].get('matchingFeedback',{}).get('corrections',[])
            if (action['action_id'],c.get('side'),c.get('field')) in selected]
        if not applied:
            continue
        reviewed = deepcopy(action)
        reviewed['snapshot'] = snapshots[action['listing_snapshot_id']]
        reviewed['raw_action_context']['matchingFeedback']['pairVerdict'] = 'not_provided'
        reviewed['raw_action_context']['matchingFeedback']['corrections'] = applied
        reviews.append(reviewed)
    original = build_identity_comparison(amazon_title=seed['amazon_title'], ebay_title=candidate['ebay_title'],
        seed=seed, evidence=normalize_candidate_evidence(candidate), policy='phase3_shadow')
    corrected = apply_scoped_reviews(original, candidate, seed, reviews, evaluated_at=cutoff)
    admission = evaluate_static_match_rules(candidate, seed, identity_policy='phase3_shadow', scoped_reviews=reviews, review_cutoff=cutoff)
    assert admission['identity_comparison']['comparisons'] == corrected['comparisons']
    unreliable = [f['field'] for f in evidence['flags'] if not any(
        c['field']==f['field'] and c['actionId']==f['actionId'] for c in evidence['corrections'])]
    invalid = [c for c in evidence['corrections'] if c['provenanceErrors']]
    application_failed = any(c['result']!='applied' for c in corrected['correctionApplication'])
    scope_gate = not unreliable and not invalid and not application_failed
    return {'withoutCorrections':original,'withCorrections':corrected,
        'identityVerdict':corrected['evidenceDecision']['productIdentityVerdict'],
        'normalBusinessEvaluationEligible':scope_gate and corrected['result'] == 'match',
        'correctionScopeGatePassed':scope_gate,'unreliableFieldsWithoutReplacement':unreliable,
        'invalidCorrections':invalid,'admissionResult':'Match' if scope_gate and corrected['result']=='match' else 'Conflict' if corrected['result']=='conflict' else 'Review' if not scope_gate or corrected['result']=='review' else 'Unknown',
        'staticRecommendation':admission['recommendation'],'staticHardBlocks':admission['hard_blocks'],
        'staticWarnings':admission['warnings'],'fullScorerNotSimulated':'Frozen adjudication inputs do not supply current pricing/business state.',
        'sourceEvidenceHash':evidence_hash({'seed':seed,'candidate':candidate}),
        'pairVerdictUsedAsInput':False,'correctionApplication':corrected['correctionApplication']}


def validate(capture):
    snapshots = {s['listing_snapshot_id']:s for s in capture['snapshots']}
    rows = []
    for row in capture['queue']:
        actions = capture['states'][row['queueId']]['actions']
        evidence = select_evidence(row, actions, capture['queue'], snapshots)
        result = {'queueId':row['queueId'],'asin':row['asin'],'ebayItemId':row['ebayItemId'],
            'variationId':row['variationId'],'sourceSnapshotId':row['sourceSnapshotId'],
            'frozenEvaluationId':row['snapshotHash'],'evidence':evidence}
        if evidence['class'] != 'informational':
            result['replay'] = replay(row,evidence,actions,snapshots,capture['finishedAt'])
        rows.append(result)
    positives = [r for r in rows if r['evidence']['class'] == 'tier_a_positive']
    negatives = [r for r in rows if r['evidence']['class'] == 'verified_negative']
    confirmed = [r for r in rows if r['evidence']['verdict'] == 'correct']
    counts = lambda group: dict(Counter(r['replay']['identityVerdict'] for r in group))
    insufficient = not positives or any(r['evidence']['class']=='unqualified_confirmation' or r['evidence']['class']=='unresolved' and r['evidence']['verdict']!='unsure' for r in rows)
    failed = any(not r['replay']['normalBusinessEvaluationEligible'] for r in positives) or any(r['replay']['normalBusinessEvaluationEligible'] for r in negatives)
    changed = any(hashlib.sha256(Path(f).read_bytes()).hexdigest()!=h for f,h in capture.get('baselineCodeHashes',{}).items())
    return {'mode':'offline_shadow_only','matcherChanged':changed,'deploymentAllowed':False,'refreshAllowed':False,
        'classificationCounts':dict(Counter(r['evidence']['class'] for r in rows)),
        'verdictCounts':dict(Counter(r['evidence']['verdict'] for r in rows if r['evidence']['class'] != 'informational')),
        'positiveResults':counts(positives),'negativeResults':counts(negatives),'unqualifiedConfirmDiagnostics':counts([r for r in confirmed if r not in positives]),
        'platformCompatibleCount':sum(any(x.get('operatorRelationship') == 'compatible' for x in r['evidence']['relationships']) for r in rows),
        'correctionCount':sum(len(r['evidence']['corrections']) for r in rows),
        'correctionsApplied':sum(sum(c['result'] == 'applied' for c in r.get('replay',{}).get('correctionApplication',[])) for r in rows),
        'status':'ADJUDICATED EVIDENCE INSUFFICIENT' if insufficient else 'STRICT GATE FAILED' if failed else 'CORPUS PASSES; CURATED GATE REQUIRED',
        'rows':rows}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',type=Path,default=Path('tmp/sourcing-adjudicated-ground-truth/capture.json'))
    parser.add_argument('--output',type=Path,default=Path('tmp/sourcing-adjudicated-ground-truth/unchanged-replay.json'))
    parser.add_argument('--candidate',action='store_true',help='Replay a changed shadow candidate after preserving the unchanged-first result')
    args=parser.parse_args()
    assert not args.output.exists(),'Use a new output path; frozen replays are immutable'
    capture=json.loads(args.capture.read_text(encoding='utf8'))
    for f,h in capture['baselineCodeHashes'].items():
        if not args.candidate or f.endswith('queue.json'):
            assert hashlib.sha256(Path(f).read_bytes()).hexdigest()==h,'Unchanged-first replay requires baseline source: '+f
    result=validate(capture)
    args.output.write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2))
    for r in result['rows']:
        if 'replay' in r:print(r['asin'],r['ebayItemId'],r['evidence']['class'],r['replay']['identityVerdict'],r['replay']['staticRecommendation'],r['replay']['withCorrections']['reason'])
