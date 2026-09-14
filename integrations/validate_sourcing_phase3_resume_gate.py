"""Read-only supplement to the Phase 3 replay; fail on full-source counterexamples.

Run after validate_sourcing_matching_phase3.py. This report cannot authorize a
rollout: passing known examples still requires complete routing/write checks.
"""
import argparse
import hashlib
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def validate(directory):
    replay=read(directory/'replay.json')
    report=read(directory/'safety-summary.json')
    current=read(directory/'current.json')
    rows={r['opportunityId']:r for r in replay['current']}
    labels=read(Path('tests/fixtures/sourcing_phase3_resume_counterexamples.json'))
    cases=[]
    buy_ids={r['opportunityId'] for r in current['views']['buy_list']['opportunities']}
    for label in labels['cases']:
        row=rows.get(label['opportunityId'])
        if row is None or row['asin']!=label['asin']:
            cases.append({**label,'passed':False,'failure':'Exact full-source fixture missing; do not replace with title-only input'})
            continue
        cases.append({**label,'passed':row['afterVerdict']=='match',
                      'beforeVerdict':row['beforeVerdict'],'afterVerdict':row['afterVerdict'],
                      'beforeRecommendation':row['beforeRecommendation'],'afterRecommendation':row['afterRecommendation'],
                      'newHardBlock':row['newHardBlock'],
                      'inBuyList':label['opportunityId'] in buy_ids,'storedStatus':row['storedStatus'],
                      'reason':row['canonicalReason'],'comparisons':row['ruleComparisons']})
    failures=[r for r in cases if not r['passed']]
    tier_path=directory/'positive-tiers.json'
    tiers=read(tier_path) if tier_path.exists() else None
    strict_failures=[r for r in (tiers or {}).get('strictRows',[]) if r['afterVerdict']!='match']
    strict_missing=[r for r in (tiers or {}).get('unresolvedSources',[]) if r.get('sourceTable')=='matching_intelligence_receiving_outcomes']
    gate_failed=bool(failures or strict_failures or strict_missing or tiers is None)
    decisions={name:[{'opportunityId':item['opportunityId'],
                      'afterIdentityVerdict':rows[item['opportunityId']]['afterVerdict'],
                      'afterRecommendation':rows[item['opportunityId']]['afterRecommendation'],
                      'identityExclusion':rows[item['opportunityId']]['afterRecommendation'] not in ('Strong Match','Probable Match'),
                      'reason':rows[item['opportunityId']]['canonicalReason']}
                     for item in view['opportunities']] for name,view in current['views'].items()}
    return {'status':'FAILED SAFETY GATE — SHADOW ONLY' if gate_failed else 'ADDITIONAL EXAMPLES PASS; FULL GATE STILL REQUIRED',
            'deploymentAllowed':False,'refreshAllowed':False,
            'originalReviewed':report['reviewed'],'additionalReviewed':cases,
            'strictPositiveSafety':(tiers or {}).get('strict'),
            'strictFailureExamples':[{k:r[k] for k in ('sourceId','asin','ebayItemId','amazonTitle','ebayTitle','afterVerdict','reason')} for r in strict_failures],
            'strictUnresolvedSourceCount':len(strict_missing),
            'knownGoodLosses':{'buyListHardExclusions':sum(r.get('inBuyList',False) and r.get('newHardBlock',False) for r in failures),
                              'buyListReviewExclusions':sum(r.get('inBuyList',False) and r.get('afterVerdict') in ('needs_review','unknown') for r in failures),
                              'heldGoodPairsDowngraded':sum(not r.get('inBuyList',False) and r.get('storedStatus') in ('inventory_snoozed','roi_snoozed','watching') for r in failures)},
            'exactShadowViewDecisions':decisions,
            'businessChecksEqual':all(r['businessChecksEqual'] for r in replay['frozen']+replay['current']),
            'actualRefresh':{'rowsExaminedForWrite':0,'written':0,'staleWriteSkips':0,'protectedRowsTouched':0,'historicalRecordsChanged':0},
            'sourceHashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
                            [directory/'current-evidence.json',directory/'row-manifest.json',directory/'replay.json']},
            'limitations':['Identity-only proposed exclusions are not a complete simulated post-refresh API membership.',
                           'No rollout or stale-state write guard is exercised after a failed positive safety gate.',
                           'Text-reviewed positives do not certify physical contents or photos.']}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,default=Path('tmp/sourcing-phase3-resume'))
    args=parser.parse_args();result=validate(args.directory)
    (args.directory/'resume-gate.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print(result['status'])
    print(json.dumps(result['knownGoodLosses']))
    raise SystemExit(1 if result['status'].startswith('FAILED') else 0)
