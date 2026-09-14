"""Bounded stored-evidence Phase 3 refresh. No provider or marketplace clients.

Dry-run by default. Exact decimal transport, durable idempotent write batches,
and a database-side compare/write protect operator activity and lifecycle.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
import gzip
import json
import math
import os
from pathlib import Path
from types import SimpleNamespace
import uuid
from zoneinfo import ZoneInfo
import requests

PATCH_FIELDS = ('status','matching_diagnostics_json','score','score_reason','ai_flags',
    'opportunity_type','target_sale_price','target_sale_price_source','landed_cost','profit','roi_percent',
    'total_profit_opportunity','max_profitable_landed_cost','max_offer_price','required_offer_percent_of_ask',
    'max_bid','inventory_need_level','months_of_supply','monthly_velocity','warning_flags','seller_trust_status','seller_trust_score')


def exact_json(value):
    if isinstance(value, Decimal):
        if not value.is_finite(): raise ValueError('Nonfinite decimal')
        return str(value)
    if isinstance(value, dict): return '{'+','.join(json.dumps(str(k))+':'+exact_json(v) for k,v in value.items())+'}'
    if isinstance(value, (list,tuple)): return '['+','.join(exact_json(v) for v in value)+']'
    if isinstance(value,float) and not math.isfinite(value): raise ValueError('Nonfinite number')
    return json.dumps(value,ensure_ascii=False)


class Rpc:
    def __init__(self):
        from sourcing_common import load_environment
        load_environment()
        self.url=os.environ['SUPABASE_URL'].rstrip('/')
        if self.url!='https://froeucjkcepuhgwisped.supabase.co': raise ValueError('Unexpected production project')
        key=os.environ['SUPABASE_SERVICE_ROLE_KEY']
        self.session=requests.Session()
        self.session.headers.update(apikey=key,Authorization='Bearer '+key,**{'Content-Type':'application/json'})

    def __call__(self,name,body):
        allowed={'sourcing_closeout_cohort','sourcing_closeout_capture','sourcing_closeout_write_batch'}
        if name not in allowed: raise ValueError('Unsupported RPC')
        response=self.session.post(self.url+'/rest/v1/rpc/'+name,data=exact_json(body).encode('utf-8'),timeout=120)
        if not response.ok: raise RuntimeError(f'{name}: HTTP {response.status_code}: {response.text[:600]}')
        return json.loads(response.text,parse_float=Decimal)


def calendar_window(now=None):
    now=now or datetime.now(timezone.utc)
    local=now.astimezone(ZoneInfo('America/Los_Angeles'))
    start=datetime.combine(local.date()-timedelta(days=29),time(),tzinfo=local.tzinfo).astimezone(timezone.utc)
    return {'startInclusive':start.isoformat(),'endInclusive':now.isoformat(),'timezone':'America/Los_Angeles','calendarDays':30}


def evaluate_capture(capture):
    from score_sourcing_opportunities import score_candidate
    # Only the scorer uses normal Python numeric values. Guard evidence remains exact.
    c=json.loads(exact_json(capture))
    state=c['state'];op=state['opportunity'];candidate=c.get('candidate');seed=c.get('seed')
    if not candidate or not seed or not candidate.get('ebay_title') or not seed.get('amazon_title'): return None
    settings=sorted(state['settings'],key=lambda x:x.get('created_at') or '',reverse=True)
    if not settings: raise RuntimeError('Missing sourcing settings')
    candidate={**candidate,**{k:op[k] for k in ('asin','candidate_id','seed_id','sourcing_run_id')}}
    scored=score_candidate(candidate,seed,SimpleNamespace(**settings[0]),
        matching_context={'offline_identity_policy':'phase3_shadow','offline_scoped_reviews':c.get('reviews',[]),
          'offline_review_cutoff':c['capturedAt'],
          'declined_offers':{x['ebay_legacy_item_id']:x['declined_offer_amount'] for x in state['declinedOffers']}},
        owned_units_by_asin={op['asin']:c['ownedUnits']})
    if not scored:return None
    diag=scored['matching_diagnostics_json']
    diag['canonicalDecision']['policyRole']='phase3_active_stored_evidence'
    diag['phase3Refresh']={'version':'phase3_closeout_v1','sourceCandidateId':op['candidate_id'],
        'sourceSeedId':op['seed_id'],'guardHash':capture['hash'],'evaluatedAt':c['capturedAt']}
    return {k:scored[k] for k in PATCH_FIELDS}


def describe(capture,patch):
    op=capture['state']['opportunity'];diag=patch['matching_diagnostics_json']
    identity=diag['static_rules']['identity_comparison']
    verdict=identity['evidenceDecision']['productIdentityVerdict']
    business=any(x['blocking'] and x['result'] in ('fail','unknown') for x in diag.get('businessEligibilityChecks',[]))
    route='buy_list' if patch['status']=='open' else 'business_excluded' if verdict=='match' and business else 'closest_excluded'
    if route=='buy_list' and (verdict!='match' or business): raise RuntimeError('Identity/business admission invariant failed')
    return {'opportunityId':op['opportunity_id'],'asin':op['asin'],'ebayItemId':op['ebay_item_id'],
        'previousStatus':op['status'],'previousDecision':op.get('previousIdentity'),
        'previousRecommendation':op.get('previousRecommendation'),
        'previousSuccess':op['status']=='open' or op.get('previousEligible') is True,
        'newDecision':verdict,'newRecommendation':diag['recommendation'],'newStatus':patch['status'],
        'reason':identity['reason'],'route':route,
        'unchangedDecision':op.get('previousIdentity')==verdict and op.get('previousRecommendation')==diag['recommendation'] and op['status']==patch['status']}


def refresh_existing(opportunity_id):
    """Production scorer's existing-row updates use the same safe path."""
    rpc=Rpc();captured=rpc('sourcing_closeout_capture',{'p_ids':[opportunity_id]})[0]
    if captured['protected']: return {'result':'protected_skip','reason':captured['protected']}
    patch=evaluate_capture(captured)
    if patch is None:return {'result':'insufficient_evidence_skip'}
    return rpc('sourcing_closeout_write_batch',{'p_allowed_ids':[opportunity_id],
        'p_rows':[{'requestId':str(uuid.uuid4()),'opportunityId':opportunity_id,'state':captured['state'],'hash':captured['hash'],'patch':patch}]})[0]


def scoped_reviews_for_candidates(db,candidates):
    asins=sorted({c['asin'] for c in candidates if c.get('asin')})
    if not asins:return []
    actions=db.table('sourcing_actions').select('*').in_('asin',asins).eq(
        'raw_action_context->matchingFeedback->>version','matching_feedback_v3').limit(1000).execute().data or []
    if len(actions)==1000:raise RuntimeError('Scoped review bound reached')
    ids=sorted({a['listing_snapshot_id'] for a in actions if a.get('listing_snapshot_id')})
    snapshots={}
    for offset in range(0,len(ids),100):
        rows=db.table('sourcing_listing_snapshots').select('*').in_('listing_snapshot_id',ids[offset:offset+100]).execute().data or []
        snapshots.update({r['listing_snapshot_id']:r for r in rows})
    return [{**a,'snapshot':snapshots.get(a.get('listing_snapshot_id'))} for a in actions]


def summarize(records,cohort,window):
    evaluated=[r for r in records.values() if 'newDecision' in r]
    result={'window':window,'totalFound':len(cohort),'excluded':dict(Counter(r['exclusion'] for r in cohort if r.get('exclusion'))),
      'evaluated':len(evaluated),'outcomes':dict(Counter(r['result'] for r in records.values())),
      'routes':dict(Counter(r['route'] for r in evaluated if r['result'] in ('written','dry_run'))),
      'unchangedDecisions':sum(r.get('unchangedDecision',False) for r in evaluated),'errors':0,
      'protectedRowsTouched':0,'reviewedRowsOverwritten':0,'historicalRewrites':0,'providerSearches':0,'marketplaceWrites':0}
    for label,success in [('previousSuccesses',True),('previousFailures',False)]:
        selected=[r for r in evaluated if r['previousSuccess']==success]
        result[label]={'evaluated':len(selected),'decisions':dict(Counter(r['newDecision'] for r in selected))}
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--write',action='store_true')
    parser.add_argument('--batch-size',type=int,default=10,choices=range(1,26))
    args=parser.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=True);rpc=Rpc()
    meta_path=out/'run.json'
    if meta_path.exists():
        meta=json.loads(meta_path.read_text(encoding='utf-8'))
        if meta['write']!=args.write:raise ValueError('Use a different output directory for write/dry run')
    else:
        meta={'runId':str(uuid.uuid4()),'window':calendar_window(),'write':args.write,'policy':'phase3_shadow'}
        meta_path.write_text(exact_json(meta),encoding='utf-8')
    cohort_path=out/'cohort.json'
    if cohort_path.exists():cohort=json.loads(cohort_path.read_text(encoding='utf-8'))
    else:
        cohort=[];after=None
        while True:
            page=rpc('sourcing_closeout_cohort',{'p_start':meta['window']['startInclusive'],'p_end':meta['window']['endInclusive'],'p_after':after})
            cohort.extend(page)
            if len(page)<1000:break
            after=page[-1]['opportunity_id']
        cohort_path.write_text(exact_json(cohort),encoding='utf-8')
    journal=out/'results.jsonl';records={}
    if journal.exists():
        for line in journal.read_text(encoding='utf-8').splitlines():
            r=json.loads(line);records[r['opportunityId']]=r
    pending=out/'pending.json'

    def record(r):
        if r['opportunityId'] in records:return
        with journal.open('a',encoding='utf-8') as f:f.write(exact_json(r)+'\n');f.flush();os.fsync(f.fileno())
        records[r['opportunityId']]=r

    def commit_pending():
        data=json.loads(pending.read_text(encoding='utf-8'),parse_float=Decimal)
        results=rpc('sourcing_closeout_write_batch',data['request'])
        if len(results)!=len(data['metadata']):raise RuntimeError('Incomplete batch response; durable request retained')
        for metadata,result in zip(data['metadata'],results):record({**metadata,**result,'opportunityId':metadata['opportunityId']})
        pending.unlink()

    if pending.exists():commit_pending()
    eligible=[r for r in cohort if not r.get('exclusion') and r['opportunity_id'] not in records]
    for offset in range(0,len(eligible),args.batch_size):
        batch=eligible[offset:offset+args.batch_size];ids=[r['opportunity_id'] for r in batch]
        captures=rpc('sourcing_closeout_capture',{'p_ids':ids})
        with gzip.open(out/'captures.jsonl.gz','at',encoding='utf-8') as f:
            for c in captures:f.write(exact_json(c)+'\n')
        writes=[];metadata=[]
        for capture in captures:
            key=capture['opportunityId']
            if capture['protected']:
                record({'opportunityId':key,'result':'protected_skip','reason':capture['protected']});continue
            patch=evaluate_capture(capture)
            if patch is None:
                record({'opportunityId':key,'result':'insufficient_evidence_skip'});continue
            description=describe(capture,patch)
            if not args.write:record({**description,'result':'dry_run'});continue
            writes.append({'requestId':str(uuid.uuid5(uuid.UUID(meta['runId']),key)),'opportunityId':key,
                'state':capture['state'],'hash':capture['hash'],'patch':patch});metadata.append(description)
        if writes:
            # Mandatory fresh recapture after scoring. Atomic RPC checks again at mutation.
            current={r['opportunityId']:r for r in rpc('sourcing_closeout_capture',{'p_ids':ids,'p_sources':False})}
            accepted=[];accepted_meta=[]
            for row,description in zip(writes,metadata):
                latest=current[row['opportunityId']]
                if latest['protected']:record({**description,'result':'protected_skip','reason':latest['protected']})
                elif latest['hash']!=row['hash']:record({**description,'result':'stale_state_skip','reason':'final_recapture'})
                else:accepted.append(row);accepted_meta.append(description)
            if accepted:
                temporary=pending.with_suffix('.pending')
                with temporary.open('w',encoding='utf-8') as f:
                    f.write(exact_json({'request':{'p_rows':accepted,'p_allowed_ids':ids},'metadata':accepted_meta}));f.flush();os.fsync(f.fileno())
                temporary.replace(pending)
                commit_pending()
        summary=summarize(records,cohort,meta['window'])
        (out/'summary.json').write_text(exact_json(summary),encoding='utf-8')
        print(json.dumps({'processed':len(records),'eligible':len(eligible),'outcomes':summary['outcomes']}),flush=True)
    (out/'summary.json').write_text(exact_json(summarize(records,cohort,meta['window'])),encoding='utf-8')
    return 0


if __name__=='__main__':raise SystemExit(main())
