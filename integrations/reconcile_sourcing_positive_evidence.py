"""Offline provenance reconciliation. Never imports a database/provider client.

Historical workflow-positive records are not automatically exact-pair ground truth.
The frozen title-assertion cohort is retained separately from exact-pair groups.
Analyst parser observations do not certify physical products or authorize admission.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

from video_game_identity import build_identity_comparison
from sourcing_match_rules import normalize_candidate_evidence

TIERS = {
    'A': 'Current explicit exact-pair identity review, preserved snapshot and scope, no unresolved newer evidence.',
    'B': 'Strong linked purchase/receipt candidate; explicit exact-pair review or full source provenance missing.',
    'C': 'Workflow/ASIN assignment only; no independent exact-pair certification.',
    'D': 'Positive workflow assertion contradicted by documented exact-pair negative or wrong-item receipt; not a global negative rule.',
    'E': 'Unresolved material evidence, scope or reference contradiction; no automatic truth assignment.',
}
CATEGORIES = ['genuine_parser_extraction_error', 'genuine_comparator_error',
    'wrong_historical_asin_linkage', 'mistaken_purchase', 'wrong_edition_version_purchase',
    'wrong_platform_linkage', 'seller_listing_mismatch', 'seller_listing_error_received_item_differs',
    'ambiguous_receiving_semantics', 'physical_receipt_not_exact_listing_identity',
    'exact_listing_id_unavailable', 'source_snapshot_unavailable', 'later_operator_correction',
    'stale_metadata', 'conflicting_amazon_reference_evidence', 'conflicting_ebay_structured_evidence',
    'workflow_only_no_identity_verification', 'unresolved']
IDENTITY_FIELDS = {'coreProduct':'base/core product', 'coreGame':'base/core product',
    'installment':'installment/version', 'edition':'edition', 'generation':'generation',
    'theme':'theme/content variant', 'packageType':'package type', 'includedContents':'included contents',
    'platform':'platform', 'region':'region', 'completeness':'completeness', 'digitalPhysical':'digital/physical'}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf8'))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def listing_scope(value):
    """Return listing + known variation, never interpret a transaction as variation."""
    text = str(value or '')
    match = re.fullmatch(r'v1\|(\d+)\|([^|]+)', text)
    if match:
        return match[1], match[2]
    match = re.fullmatch(r'(\d{12})(?:-\d+)?', text)
    return (match[1], None) if match else (None, None)


def pair(row):
    return row.get('asin'), listing_scope(row.get('ebayItemId') or row.get('ebay_item_id'))[0]


def classify(*, row, purchase, receiving, negative, adjudication):
    # Missing provenance never becomes positive through a matching verdict.
    if purchase and purchase.get('asin') != row.get('asin'):
        return 'E', 'Current purchase ASIN differs; attribution/timing of reassignment is not recorded here.'
    if negative:
        return 'D', 'Documented same-ASIN/listing contradictory evidence; physical receipt errors do not prove the listing text was wrong.'
    if adjudication.get('materialUnresolved'):
        return 'E', 'Stored titles expose a material ambiguity; receipt does not resolve exact retail package/reference truth.'
    if receiving and receiving.get('outcome') == 'correct_item' and pair(receiving) == pair(row):
        return 'B', 'Linked purchase and correct_item receipt, but default outcome and no explicit identity-review provenance.'
    return 'C', 'Purchase ASIN/workflow linkage does not establish an independently reviewed exact pair.'


def summarize(rows):
    return {tier: {'rows':len(items := [r for r in rows if r['tier']==tier]),
                   'verdicts':dict(Counter(r['shadowVerdict'] for r in items)),
                   'sources':dict(Counter(r['sourceTable'] for r in items))} for tier in TIERS}


def reconcile(directory, annotations):
    directory = Path(directory)
    frozen_path = Path('tmp/sourcing-phase1/positive-candidates.json')
    previous_path = Path('tmp/sourcing-phase3-second-resume/positive-tiers.json')
    frozen, previous = read(frozen_path), read(previous_path)
    sources = {(r['source_table'],r['source_id']):r for r in frozen}
    purchases = {r['item_id']:r for r in read(directory/'purchase_items.json')}
    receipts = {r['purchase_item_id']:r for r in read(directory/'matching_intelligence_receiving_outcomes.json')}
    matches, problems, actions = (read(directory/(name+'.json')) for name in
                                ('sourcing_purchase_matches','order_problem_cases','sourcing_actions'))
    action_index, match_index, problem_index = defaultdict(list), defaultdict(list), defaultdict(list)
    for a in actions: action_index[pair(a)].append(a)
    for a in matches: match_index[a['purchase_item_id']].append(a)
    for a in problems: problem_index[a['purchase_item_id']].append(a)
    snapshots = read('tmp/sourcing-phase1/action-snapshots.json') + read(directory/'purchased-snapshots.json')
    snapshot_index = {r['listing_snapshot_id']:r for r in snapshots}
    current_index = defaultdict(list)
    for path in ['tmp/sourcing-phase1/current-evidence.json',
                 'tmp/sourcing-phase3-second-resume/current-evidence.json',
                 str(directory/'current-receiving-opportunity-diagnostics.json')]:
        for r in read(path): current_index[pair(r)].append({'file':path,'opportunityId':r['opportunity_id'],
            'latestSnapshotId':r.get('latest_listing_snapshot_id'),'diagnostics':r.get('matching_diagnostics_json')})
    reviewed = {r['sourceId']:r for r in annotations}
    assert not any(a['action_type'] in ('confirmed_valid_match','mark_valid_match') or
                   'matching_feedback_v3' in json.dumps(a) for a in actions), \
        'New explicit review requires individual snapshot/supersession adjudication before this audit can report Tier A.'
    results = {}
    negative_reasons = {'wrong_product','wrong_platform','wrong_edition_version','seller_listing_mismatch','listing_error'}
    for name in ('strictRows','broaderRows'):
        records=[]
        for old in previous[name]:
            raw=sources[(old['sourceTable'],old['sourceId'])]
            context=raw.get('raw_context_json') or {}
            stored=context.get('receiving_outcome') or context.get('purchase_item') or {}
            purchase=purchases.get(old['purchaseItemId'])
            receipt=receipts.get(old['purchaseItemId'])
            pair_actions=sorted(action_index[pair(old)],key=lambda r:(r['created_at'],r['action_id']))
            negatives=[a for a in pair_actions if a.get('dismiss_reason') in negative_reasons and
                       listing_scope(a.get('ebay_item_id')) == listing_scope(old['ebayItemId'])]
            # Never call a non-identity commercial/condition reason a pair rejection.
            wrong_receipt=receipt if receipt and pair(receipt)==pair(old) and receipt.get('outcome') in ('wrong_item','sourcing_false_positive') else None
            annotation=reviewed.get(old['sourceId'],{})
            tier,reason=classify(row=old,purchase=purchase,receiving=receipt,
                                 negative=negatives or wrong_receipt,adjudication=annotation)
            source_system=stored.get('system')
            trace=build_identity_comparison(amazon_title=old['amazonTitle'],ebay_title=old['ebayTitle'],
                seed={'asin':old['asin'],'system':source_system},policy='phase3_shadow')
            verdict=trace['evidenceDecision']['productIdentityVerdict']
            assert verdict==old['afterVerdict'], 'Current matcher unexpectedly differs from frozen replay'
            conflicts=set(re.findall(r'(\w+) conflict:',trace['reason']))
            category=annotation.get('category','ambiguous_receiving_semantics' if name=='strictRows' else 'workflow_only_no_identity_verification')
            if purchase and purchase.get('asin')!=old['asin']:category='stale_metadata'
            if negatives:category='unresolved'  # explicit pair negative != proof of a purchased mistake
            if wrong_receipt:category='seller_listing_error_received_item_differs'
            record={**old,'cohort':name,'tier':tier,'tierReason':reason,'variationId':listing_scope(old['ebayItemId'])[1],
                'exactListingKey':listing_scope(old['ebayItemId'])[0],
                'sourceRecord':raw,'currentPurchase':purchase,'currentReceipt':receipt,
                'purchaseMatches':match_index[old['purchaseItemId']], 'orderProblems':problem_index[old['purchaseItemId']],
                'actions':pair_actions,'latestExplicitPairVerdict':negatives[-1] if negatives else None,
                'latestV3Corrections':[], 'v3Available':False,
                'actionTimeSnapshots':[snapshot_index[a['listing_snapshot_id']] for a in pair_actions if a.get('listing_snapshot_id') in snapshot_index],
                'currentStoredDiagnostics':current_index[pair(old)],
                'historicalDecisionAvailable':bool(current_index[pair(old)]),
                'originalReplayGameName':None,'originalReplayItemSpecifics':None,'originalReplayDescription':None,
                'missingSourceExplanation':'Purchase/receiving projection lacks Browse specifics and description; other available snapshots remain separate, not silently joined into the replay.',
                'shadowVerdict':verdict,'shadowTrace':trace,
                'conflictFields':sorted(conflicts),'conflictCategory':category,
                'analystInspection':annotation or None,
                'explicitIdentityReviewProven':False,'tierAEligible':False,
                'evidenceCurrentness':'Bounded non-atomic source read; historical snapshots and mutable current records kept separate.'}
            stored_replays=[]
            for snap in record['actionTimeSnapshots']:
                if snap.get('asin') != old['asin'] or pair(snap) != pair(old):
                    continue
                if not snap.get('ebay_item_specifics_json') and not snap.get('ebay_description'):
                    continue
                candidate={'ebay_title':snap['ebay_title'],'raw_ebay_json':{
                    'localizedAspects':snap.get('ebay_item_specifics_json') or [],
                    'description':snap.get('ebay_description')}}
                result=build_identity_comparison(amazon_title=snap['amazon_title'],ebay_title=snap['ebay_title'],
                    seed={'asin':snap['asin'],'system':snap.get('amazon_system')},
                    evidence=normalize_candidate_evidence(candidate),policy='phase3_shadow')
                stored_replays.append({'snapshotId':snap['listing_snapshot_id'],
                    'capturedAt':snap['captured_at'],'source':snap['snapshot_source'],
                    'referenceTitleChanged':snap['amazon_title']!=old['amazonTitle'],
                    'trace':result,'verdict':result['evidenceDecision']['productIdentityVerdict'],
                    'note':'Separate stored-snapshot replay, not a replacement for the frozen assertion or verified truth.'})
            record['storedSnapshotReplays']=stored_replays
            records.append(record)
        results[name]=records
    # Candidate grouping is not variation certification. Unknown variation stays unknown.
    groups=defaultdict(list)
    for r in results['strictRows']+results['broaderRows']:
        key=(r['asin'],r['exactListingKey'],r['variationId']) if r['exactListingKey'] else ('unresolved-source',r['sourceTable'],r['sourceId'])
        groups[key].append({'sourceId':r['sourceId'],'cohort':r['cohort'],'tier':r['tier']})
    results['pairGroups']=[{'key':k,'assertions':v} for k,v in groups.items()]
    results['tierA']=[]
    results['summary']={'sourceRows':len(frozen),'sourceCounts':dict(Counter(r['source_table'] for r in frozen)),
        'receiving':summarize(results['strictRows']),'broader':summarize(results['broaderRows']),
        'tiers':TIERS,'receivingAssertions':417,'receivingListingKeys':416,
        'candidateGroupCount':len(groups),'variationScopeUnverified':True,
        'tierACount':0,'tierAResults':{'match':0,'non-match':0,'needs_review':0,'unknown':0},
        'emptyCorpusIsNotPass':True,'deploymentAllowed':False,'matcherChanged':False,
        'explicitConfirmMatchCount':sum(a['action_type'] in ('confirmed_valid_match','mark_valid_match') for a in actions),
        'v3ActionCount':sum('matching_feedback_v3' in json.dumps(a) for a in actions),
        'readActions':len(actions),'inputHashes':{str(p):digest(p) for p in [frozen_path,previous_path,Path('integrations/video_game_identity.py')]}}
    for name in ('strictRows','broaderRows'):
        conflicts=[r for r in results[name] if r['shadowVerdict']=='non-match']
        counts=Counter(r['conflictCategory'] for r in conflicts)
        fields=Counter()
        for row in conflicts:fields.update(set(IDENTITY_FIELDS.get(f,'other') for f in row['conflictFields']))
        results['summary'][name+'ConflictCategories']={k:counts[k] for k in CATEGORIES}
        results['summary'][name+'ConflictFields']={f:fields[f] for f in dict.fromkeys([*IDENTITY_FIELDS.values(),'other'])}
        results['summary'][name+'Missing']={'listingId':sum(not r['exactListingKey'] for r in results[name]),
            'browseInput':len(results[name]),'explicitReview':len(results[name])}
    return results


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',default='tmp/sourcing-positive-evidence-reconciliation')
    parser.add_argument('--annotations',required=True)
    args=parser.parse_args()
    output=reconcile(args.directory,read(args.annotations))
    Path(args.directory,'reconciliation.json').write_text(json.dumps(output,indent=2),encoding='utf8')
    print(json.dumps(output['summary'],indent=2))
