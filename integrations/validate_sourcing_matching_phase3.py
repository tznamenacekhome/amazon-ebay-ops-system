"""Offline, read-only-input Phase 3 safety replay. Never imports a live client.

This intentionally has no --write mode. A failing report is not a refresh
authorization. Raw rows, before images, and labels stay in ignored tmp/.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from sourcing_match_rules import evaluate_static_match_rules
from score_sourcing_opportunities import score_candidate


def load(path):
    return json.loads(Path(path).read_text(encoding='utf8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def summarize(results):
    return {
        'rows':len(results),
        'beforeVerdicts':dict(collections.Counter(r['beforeVerdict'] for r in results)),
        'afterVerdicts':dict(collections.Counter(r['afterVerdict'] for r in results)),
        'newHardBlocks':sum(r['newHardBlock'] for r in results),
        'oldHardBlocksRemoved':sum(r['oldHardBlockRemoved'] for r in results),
        'controlledReplayLeaves':sum(r['leaves'] for r in results),
        'controlledReplayEnters':sum(r['enters'] for r in results),
        'reviewBasedLosses':sum(r['leaves'] and not r['newHardBlock'] for r in results),
        'fieldCoverage':{side:{key:{phase:sum(r[phase+'Fields'][side][key]['state'] not in ('unknown','conflicting_sources') for r in results)
                                  for phase in ('before','after')} for key in results[0]['afterFields'][side]} for side in ('amazon','ebay')} if results else {},
        'routingReasons':dict(collections.Counter(reason for r in results if r['leaves'] or r['enters'] for reason in r['newReasons'])),
    }


def replay(row, settings):
    seed,candidate=row.get('seed') or {},row.get('candidate') or {}
    candidate=dict(candidate)
    candidate.update({k:row.get(k,candidate.get(k)) for k in ('asin','candidate_id','seed_id','sourcing_run_id')})
    opts=dict(excluded_keywords=settings.excluded_keywords,allowed_item_location_countries=settings.item_location_countries)
    before=evaluate_static_match_rules(candidate,seed,**opts)
    after=evaluate_static_match_rules(candidate,seed,identity_policy='phase3_shadow',**opts)
    old=score_candidate(candidate,seed,settings)
    new=score_candidate(candidate,seed,settings,matching_context={'offline_identity_policy':'phase3_shadow'})
    old_identity,new_identity=before['identity_comparison'],after['identity_comparison']
    return dict(opportunityId=row.get('opportunity_id'),asin=row.get('asin'),ebayItemId=row.get('ebay_item_id'),
        amazonTitle=seed.get('amazon_title'),ebayTitle=candidate.get('ebay_title'),storedStatus=row.get('status'),
        beforeVerdict=old_identity['evidenceDecision']['productIdentityVerdict'],afterVerdict=new_identity['evidenceDecision']['productIdentityVerdict'],
        beforeRecommendation=before['recommendation'],afterRecommendation=after['recommendation'],
        beforeFields={s:old_identity[s]['fields'] for s in ('amazon','ebay')},afterFields={s:new_identity[s]['fields'] for s in ('amazon','ebay')},
        beforeStatus=old['status'],afterStatus=new['status'],
        beforeEligible=old['matching_diagnostics_json']['presentationDecision']['eligible'],
        afterEligible=new['matching_diagnostics_json']['presentationDecision']['eligible'],
        leaves=old['status']=='open' and new['status']!='open',enters=old['status']!='open' and new['status']=='open',
        newHardBlock=not before['hard_blocks'] and bool(after['hard_blocks']),
        oldHardBlockRemoved=bool(before['hard_blocks']) and not after['hard_blocks'],
        oldReasons=before['hard_blocks']+before['warnings'],newReasons=after['hard_blocks']+after['warnings'],
        canonicalReason=new_identity['reason'],ruleComparisons=new_identity['comparisons'],
        beforeStaticHash=hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest(),
        businessChecksEqual=strip_time(old['matching_diagnostics_json']['businessEligibilityChecks'])==strip_time(new['matching_diagnostics_json']['businessEligibilityChecks']),
        scoringInputs='same frozen seed/candidate/settings; historical memory, live pricing and operator-state reactivation not simulated',
        afterScored=new)


def strip_time(value):
    if isinstance(value,dict):return {k:strip_time(v) for k,v in value.items() if k not in ('evaluatedAt','evaluationId')}
    if isinstance(value,list):return [strip_time(v) for v in value]
    return value


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frozen',default='tmp/sourcing-phase1')
    parser.add_argument('--current',default='tmp/sourcing-phase3')
    parser.add_argument('--reviewed-current',type=Path,help='Frozen full-source reviewed cohort; never substitute sanitized titles when a current row leaves a view')
    parser.add_argument('--output',type=Path,help='Separate output directory so prior failed-gate artifacts remain immutable')
    args=parser.parse_args();f=Path(args.frozen);p=Path(args.current)
    output=args.output or p;output.mkdir(exist_ok=True,parents=True)
    manifest=load(f/'manifest.json')
    for name in ('actions','newest250','currentStoredEvidence','actionSnapshots','positiveCandidates'):
        assert sha(manifest[name]['file'])==manifest[name]['sha256'],name+' frozen hash changed'
    raw=load(f/'settings.json')[0]
    settings=SimpleNamespace(**{k:float(v) if k in ('min_roi_percent','min_profit_dollars','best_offer_min_ask_percent') else v for k,v in raw.items()})
    frozen=[replay(r,settings) for r in load(f/'current-evidence.json')]
    current=[replay(r,settings) for r in load(p/'current-evidence.json')]
    latest_ids={r['opportunity_id'] for r in load(f/'newest250.json')}
    current_manifest=load(p/'row-manifest.json');views=load(p/'current.json')['views']
    by_id={r['opportunityId']:r for r in current}
    proposed={k:{'beforeOrderedIds':[r['opportunityId'] for r in v['opportunities']],
                    'identityExclusionIds':[r['opportunityId'] for r in v['opportunities'] if by_id[r['opportunityId']]['afterRecommendation'] not in ('Strong Match','Probable Match')],
                    'retainedOrder':[r['opportunityId'] for r in v['opportunities'] if by_id[r['opportunityId']]['afterRecommendation'] in ('Strong Match','Probable Match')],
                    'actualWrites':0} for k,v in views.items()}
    report={'mode':'shadow_only','frozen':summarize(frozen),'newest250':summarize([r for r in frozen if r['opportunityId'] in latest_ids]),
            'current':summarize(current),'cohorts':{k:summarize([by_id[x] for x in ids]) for k,ids in current_manifest['cohorts'].items()},
            'views':proposed,'protectedIds':current_manifest['protectedIds'],'sourceHashes':{'frozen':sha(f/'current-evidence.json'),'current':sha(p/'current-evidence.json')},
            'limitations':['Controlled replay is not full current operator-history/pricing reactivation; use actual-view membership for visibility safety.',
                          'Dismissal labels alone do not prove which text field is wrong. Purchase status alone is not positive identity truth.'],
            'refresh':{'written':0,'historicalSnapshotsChanged':0,'protectedLifecycleChanges':0}}
    labels=load('tests/fixtures/sourcing_phase3_reviewed.json')
    reviewed=[]
    current_inputs=load(p/'current-evidence.json')
    reviewed_inputs=load(args.reviewed_current) if args.reviewed_current else current_inputs
    frozen_inputs=load(f/'current-evidence.json')
    exact_examples={'B000QL0T36':'919606c5-9527-45a6-93aa-c4cf49ec4b0d',
                    'B00ZMBLKPG':'c3f0249f-8e52-45bd-81aa-005a5d56fafd',
                    'B001IK1BJ0':'7078668d-09aa-4b83-9302-69ad454200f5',
                    'B08H9KGMWK':'c2a7158e-30fa-40f7-acdb-c25a210edafa'}
    for label in labels['cases']:
        # Validate against real current evidence when the exact title pair is
        # available; otherwise use the explicitly bounded textual fixture.
        actual=next((r for r in frozen_inputs if r['opportunity_id']==exact_examples.get(label['asin'])),None)
        basis='exact supplied frozen opportunity with full stored sources'
        if actual is None:
            actual=next((r for r in reviewed_inputs if r['asin']==label['asin'] and
                         ' '.join(str((r.get('candidate') or {}).get('ebay_title')).split())==' '.join(label['ebay'].split())),None)
            basis='exact pinned reviewed title pair with full stored sources'
        if actual is None:
            basis='bounded textual fixture; not full listing sources'
            actual={'asin':label['asin'],'seed':{'asin':label['asin'],'amazon_title':label['amazon'],'target_sale_price':100},
                    'candidate':{'ebay_title':label['ebay'],'condition':'Brand New','condition_id':'1000','item_location_country':'US',
                                 'price':10,'shipping_cost':0,'landed_cost':10,'buying_options':['FIXED_PRICE'],
                                 'raw_ebay_json':{'categories':[{'categoryId':'139973','categoryName':'Video Games'}]}}}
        result=replay(actual,settings)
        accuracy={}
        for phase in ('before','after'):
            checks=[]
            for side in ('amazon','ebay'):
                for key,expected in label.get(side+'Fields',{}).items():
                    field=result[phase+'Fields'][side][key]
                    value=field['value']
                    # Unknown is correct only for an explicitly annotated unknown.
                    correct=(value is None and field['state']=='unknown') if expected is None else (str(value).casefold()==str(expected).casefold() and field['state'] not in ('unknown','conflicting_sources'))
                    checks.append({'side':side,'field':key,'expected':expected,'actual':value,'state':field['state'],'correct':correct})
            accuracy[phase]={'correct':sum(x['correct'] for x in checks),'total':len(checks),'checks':checks}
        reviewed.append({'asin':label['asin'],'opportunityId':result['opportunityId'],'split':label['split'],'expected':label['expected'],
                         'evidenceBasis':basis,
                         'beforeVerdict':result['beforeVerdict'],'afterVerdict':result['afterVerdict'],
                         'beforeRecommendation':result['beforeRecommendation'],'afterRecommendation':result['afterRecommendation'],
                         'wasVisible':result['opportunityId'] in proposed['buy_list']['beforeOrderedIds'] or result['beforeEligible'],
                         'afterEligible':result['afterEligible'],'accuracy':accuracy,'reason':result['canonicalReason']})
    positives=[r for r in reviewed if r['expected']=='match'];negatives=[r for r in reviewed if r['expected']=='non-match']
    loss=[r for r in positives if r['wasVisible'] and not r['afterEligible']]
    report['reviewed']={'annotationBasis':labels['annotationBasis'],'cases':reviewed,
        'accuracy':{phase:{'correct':sum(r['accuracy'][phase]['correct'] for r in reviewed),'total':sum(r['accuracy'][phase]['total'] for r in reviewed)} for phase in ('before','after')},
        'positives':{'total':len(positives),'retained':sum(r['wasVisible'] and r['afterEligible'] for r in positives),'recovered':sum(not r['wasVisible'] and r['afterEligible'] for r in positives),
                     'lost':len(loss),'lossAsins':[r['asin'] for r in loss],'stillExcluded':sum(not r['wasVisible'] and not r['afterEligible'] for r in positives)},
        'negatives':{'total':len(negatives),'caughtBefore':sum(r['beforeVerdict']=='non-match' for r in negatives),'caughtAfter':sum(r['afterVerdict']=='non-match' for r in negatives),
                     'missedAfter':sum(r['afterVerdict']!='non-match' for r in negatives),
                     'excludedAfterIncludingReview':sum(not r['afterEligible'] for r in negatives)},
        'unresolved':[r['asin'] for r in reviewed if r['expected']=='unresolved']}
    checks={'noKnownPositiveVisibilityLoss':not loss,'fullCurrentRoutingReconciled':False,'sourceConflictPolicyValidated':False}
    report['gate']={'passed':all(checks.values()),'checks':checks,'blockers':[
        {'code':'known_positive_visibility_loss','asins':[r['asin'] for r in loss],'reasons':[r['reason'] for r in loss]},
        {'code':'full_current_routing_reconciliation_not_approved','detail':'Controlled scorer replay does not yet reconcile all current operator memory, price references and exact API routing.'},
        {'code':'source_conflict_policy_not_validated','detail':'Meaningful source disagreement and harmless seller/catalog wording are not reliably separated across the frozen cohort.'}],
        'deploymentAllowed':False,'refreshAllowed':False}
    families=collections.defaultdict(list)
    for row in frozen:
        family=row['beforeFields']['amazon']['franchise']['value'] or 'unrecognized_by_legacy'
        families[family].append(row)
    report['familyCoverage']={k:summarize(v) for k,v in sorted(families.items())}
    # Compare labels as labels, without treating business/condition feedback as
    # identity negatives or using any later feedback as a replay feature.
    actions={r['opportunity_id']:r for r in load(f/'actions.json')}
    report['dismissalReasonBreakdown']={reason:summarize([r for r in frozen if (actions.get(r['opportunityId']) or {}).get('dismiss_reason')==reason]) for reason in sorted({r['dismiss_reason'] for r in actions.values()})}
    (output/'replay.json').write_text(json.dumps({'frozen':frozen,'current':current},ensure_ascii=True),encoding='utf8')
    (output/'safety-summary.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps({k: {x:v for x,v in report[k].items() if x not in ('fieldCoverage','routingReasons')} for k in ('frozen','newest250','current')},indent=2))


if __name__=='__main__': main()
