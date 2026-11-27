"""One reviewed, manifest-bound Phase 3B text-only replay. Dry-run default; existing Flipmine lease/writers only.
No sheet read, discovery, marketplace mutation or broad historical replay.
Original source decisions are archived before a selected row can become pending.
"""
import argparse,collections,datetime as dt,hashlib,json,os,sys,time,uuid
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'integrations'))
import import_flipmine as fm
from sourcing_common import get_supabase_client
from sourcing_database_guard import wait_for_database
from sourcing_platform_policy import platform_eligibility
from sourcing_phase3_refresh import Rpc,PATCH_FIELDS,exact_json
from matching_intelligence import build_listing_snapshot
from score_sourcing_opportunities import score_candidate,score_candidate_batches,fetch_keepa_price_context_by_asin,fetch_owned_units_by_asin
from ebay_listing_evidence import ListingUnavailable
NS=uuid.UUID('0d734175-29a3-4401-a1db-4dc9cd253d9c')

def mutable_decision_patch(scored):
 """Preserve authoritative lifecycle history; never ask refresh SQL to write it."""
 patch=deepcopy({k:scored[k]for k in PATCH_FIELDS if k in scored})
 if patch['status']not in ['open','rejected']:
  lifecycle=patch['status'];patch['status']='rejected'
  diagnostics=patch['matching_diagnostics_json']
  diagnostics['normalPipelineLifecycleStatus']=lifecycle
  diagnostics['businessEligibilityChecks']=[*(diagnostics.get('businessEligibilityChecks')or[]),{'code':'operator_history_status','label':'Normal pipeline historical lifecycle','result':'fail','blocking':True,'actual':lifecycle,'explanation':'Historical lifecycle remains authoritative; refresh record cannot become actionable.'}]
  from sourcing_decision_trace import enrich_sourcing_diagnostics
  patch['matching_diagnostics_json']=enrich_sourcing_diagnostics(diagnostics,status='rejected',opportunity_type=patch.get('opportunity_type'),profit=patch.get('profit'),roi_percent=patch.get('roi_percent'))
 return patch

def unavailable_decision_patch(op, reason):
 diagnostics=deepcopy(op.get('matching_diagnostics_json')or{})
 diagnostics['businessEligibilityChecks']=[*(diagnostics.get('businessEligibilityChecks')or[]),{'code':'listing_availability','label':'Current listing availability','result':'fail','blocking':True,'explanation':reason}]
 from sourcing_decision_trace import enrich_sourcing_diagnostics
 diagnostics=enrich_sourcing_diagnostics(diagnostics,status='rejected',opportunity_type=op.get('opportunity_type'),profit=op.get('profit'),roi_percent=op.get('roi_percent'),listing_status='ended')
 return {'status':'rejected','matching_diagnostics_json':diagnostics}

def write_checkpoint(path,value):
 path.write_text(exact_json(value),encoding='utf-8')

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--execute',action='store_true');p.add_argument('--max-seconds',type=int,default=600)
 args=p.parse_args();os.chdir(ROOT)
 manifest=json.loads(Path('docs/phase3b_replay_manifest_2026-11-26.json').read_text(encoding='utf-8'))
 assert manifest['tabId']=='97fc964e-a4f2-43bb-a5ca-90381d1352b8' and 1<=len(manifest['rows'])<=50
 target_total=len(manifest['rows'])
 gate=json.loads(Path('docs/phase3b_seal_shadow_2026-11-26.json').read_text(encoding='utf-8'));assert gate['gate']=='PASS'
 for file,digest in gate['codeFileHashes'].items():assert hashlib.sha256(Path(file).read_bytes().replace(b'\r\n',b'\n')).hexdigest()==digest,file
 tag=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest();run_id=str(uuid.uuid5(NS,tag))
 root=Path('tmp/phase3b-replay');root.mkdir(exist_ok=True);journal=root/'results.jsonl';statefile=root/'state.json';pending=root/'pending.json'
 db=get_supabase_client();assert os.environ['SUPABASE_URL'].rstrip('/')=='https://froeucjkcepuhgwisped.supabase.co';wait_for_database(db,attempts=1)
 tab=db.table('sourcing_flipmine_tabs').select('*').eq('tab_id',manifest['tabId']).single().execute().data
 rows=db.table('sourcing_flipmine_rows').select('*').eq('tab_id',manifest['tabId']).order('row_number').execute().data
 assert len(rows)==558 and tab['source_hash']==manifest['sourceHash']
 selected={r['rowNumber']:r for r in manifest['rows']};assert len(selected)==target_total
 for row in rows:
  if row['row_number']in selected:
   allowed=selected[row['row_number']];assert row['asin']==allowed['asin']and row['ebay_legacy_item_id']==allowed['ebayItemId']
 cids=[r['candidateId']for r in manifest['rows']];candidates=db.table('sourcing_ebay_candidates').select('*').in_('candidate_id',cids).execute().data
 cs={r['candidate_id']:r for r in candidates};seeds=db.table('sourcing_seed_asins').select('*').in_('seed_id',list({r['seed_id']for r in candidates})).execute().data;ss={r['seed_id']:r for r in seeds}
 # Never silently reuse an unlinked pre-existing decision instead of the
 # authorized full fresh evaluation. Stop before any production writes.
 current_sources={r['row_number']:r for r in rows}
 unlinked=[r['candidateId'] for r in manifest['rows'] if not r['opportunityId'] and not current_sources[r['rowNumber']]['opportunity_id']]
 if unlinked:
  observed=db.table('sourcing_opportunities').select('opportunity_id').in_('candidate_id',unlinked).limit(100).execute().data
  assert {r['opportunity_id'] for r in observed}<={r['opportunityId'] for r in manifest['rows'] if r['opportunityId']},'Unexpected new decisions after manifest; review before bounded replay'
 plan=[{'row':r['rowNumber'],'item':r['ebayItemId'],'asin':r['asin'],'policy':platform_eligibility(ss[cs[r['candidateId']]['seed_id']],cs[r['candidateId']])['result']}for r in manifest['rows']]
 print(json.dumps({'mode':'execute'if args.execute else'plan','runId':run_id,'rows':target_total,'policy':dict(collections.Counter(r['policy']for r in plan))}),flush=True)
 (root/'plan.json').write_text(json.dumps(plan,indent=2))
 if not args.execute:return
 os.environ.update(MBOP_SOURCING_PHASE3='1',MBOP_EBAY_TRADING_ENRICHMENT='true',MBOP_EBAY_QUOTA_GUARD='true',MBOP_EBAY_JOB_NAME='import_flipmine.py')
 # Actual calls in this process, without credentials, payloads or query strings.
 import requests
 original_request=requests.Session.request;calls=collections.Counter()
 def tracked(session,method,url,*a,**kw):
  host=urlparse(url).hostname or '';path=urlparse(url).path;label=None
  if host.endswith('ebay.com'):
   label='eBay:'+str((kw.get('headers')or{}).get('X-EBAY-API-CALL-NAME')or('OAuth'if'identity/'in path else'Analytics'if'analytics/'in path else'Browse'))
  elif host.endswith('amazon.com'):label='Amazon:OAuth'if host=='api.amazon.com'else'Amazon:read'
  elif host.endswith('keepa.com'):label='Keepa:read'
  if label:calls[label]+=1
  try:return original_request(session,method,url,*a,**kw)
  finally:(root/'calls.json').write_text(json.dumps(calls,indent=2))
 requests.Session.request=tracked
 def usage():return db.table('ebay_api_usage').select('resource,job_name,day,attempts').in_('job_name',['import_flipmine.py','essential:import_flipmine.py']).execute().data
 if not (root/'usage-before.json').exists():(root/'usage-before.json').write_text(json.dumps(usage()))
 done={json.loads(line)['row']for line in journal.read_text(encoding='utf-8').splitlines()}if journal.exists()else set()
 if len(done)==target_total:
  print('Saved checkpoint complete; no provider calls or new jobs.');return
 rpc=Rpc();worker=fm.FlipmineImporter(db,run_id,SimpleNamespace(spreadsheet_id=tab['spreadsheet_id']))
 original_rows={r['row_number']:r for r in rows};old_ops={}
 if statefile.exists():
  state=json.loads(statefile.read_text(encoding='utf-8'));assert state['manifestHash']==tag;original_rows={r['row_number']:r for r in state['originalRows']};old_ops=state['oldOps']
 else:
  assert tab['status']=='completed'and tab['run_id']==manifest['originalRunId']
  for item in manifest['rows']:
   row=original_rows[item['rowNumber']];c=cs[row['candidate_id']];s=ss[c['seed_id']];op=None
   if item['opportunityId']:op=db.table('sourcing_opportunities').select('*').eq('opportunity_id',item['opportunityId']).single().execute().data
   if op:assert op['candidate_id']==c['candidate_id'] and op['seed_id']==s['seed_id'],'Manifest evidence links changed; stop before replay'
   old_ops[str(row['row_number'])]=op
   archive=build_listing_snapshot(opportunity=op,candidate=c,seed=s,event='backfill',source='authorized_phase3b_text_replay_original',raw_context={'original_source_row':row,'original_tab':tab,'manifestHash':tag,'original_opportunity':op})
   archive['listing_snapshot_id']=str(uuid.uuid5(NS,tag+':original:'+str(row['row_number'])))
   if not db.table('sourcing_listing_snapshots').select('listing_snapshot_id').eq('listing_snapshot_id',archive['listing_snapshot_id']).limit(1).execute().data:db.table('sourcing_listing_snapshots').insert(archive).execute()
  state={'manifestHash':tag,'runId':run_id,'originalTab':tab,'originalRows':rows,'oldOps':old_ops};statefile.write_text(json.dumps(state))
 active=db.table('sourcing_flipmine_runs').select('run_id').eq('status','running').neq('run_id',run_id).limit(1).execute().data
 assert not active,'Another Flipmine worker owns the active lease'
 existing_run=db.table('sourcing_flipmine_runs').select('status').eq('run_id',run_id).limit(1).execute().data
 if not existing_run:
  begun=fm.rpc(db,'flipmine_begin',p_run=run_id);assert begun['launch']and begun['run_id']==run_id
 else:
  assert existing_run[0]['status']in ['running','partial','failed'];db.table('sourcing_flipmine_runs').update({'status':'running','heartbeat_at':fm.now(),'error_summary':None}).eq('run_id',run_id).execute()
 if tab['run_id']!=run_id:
  changed=db.table('sourcing_flipmine_tabs').update({'run_id':run_id,'status':'running','error_summary':None,'summary':{**tab['summary'],'targetedReplay':{'manifestHash':tag,'originalRunId':manifest['originalRunId'],'rows':target_total}}}).eq('tab_id',tab['tab_id']).eq('status','completed').eq('run_id',manifest['originalRunId']).eq('source_hash',manifest['sourceHash']).execute().data
  assert len(changed)==1,'Source tab changed before bounded replay lease'
 else:db.table('sourcing_flipmine_tabs').update({'status':'running'}).eq('tab_id',tab['tab_id']).eq('run_id',run_id).execute()
 tab={**tab,'run_id':run_id,'status':'running'}
 def record(value):
  with journal.open('a')as f:f.write(json.dumps(value,default=str)+'\n');f.flush();os.fsync(f.fileno())
  done.add(value['row']);print(json.dumps(value,default=str),flush=True)
 def save_source(number,status,evaluation,error=None):
  evaluation={**(evaluation or{}),'targetedReplay':{'manifestHash':tag,'archiveId':str(uuid.uuid5(NS,tag+':original:'+str(number)))}}
  worker.row_update(tab['tab_id'],dict(original_rows[number]),status=status,evaluation=evaluation,error=error)
 def flush_pending():
  item=json.loads(pending.read_text(encoding='utf-8'));result=rpc('sourcing_closeout_write_batch',item['request'])[0]
  if result['result']in ['written','already_written','already_applied']:
   save_source(item['summary']['row'],item.get('sourceStatus','evaluated'),item['diagnostics'],item.get('sourceError'))
  else:
   old=original_rows[item['summary']['row']];save_source(old['row_number'],old['status'],old['evaluation'],old['error'])
  record({**item['summary'],'guardResult':result['result']});pending.unlink()
 if pending.exists():flush_pending()
 # Persist the bounded pending set before processing so original import progress
 # and selected replay remaining work cannot silently bypass unprocessed rows.
 current_rows={r['row_number']:r for r in db.table('sourcing_flipmine_rows').select('*').eq('tab_id',tab['tab_id']).execute().data}
 for item in manifest['rows']:
  number=item['rowNumber']
  if number in done:continue
  current=current_rows[number];marker=(current.get('evaluation')or{}).get('targetedReplay')or{}
  if current['status']in fm.TERMINAL and marker.get('manifestHash')==tag:
   record({'row':number,'item':item['ebayItemId'],'asin':item['asin'],'result':'checkpoint_recovered','opportunityId':current['opportunity_id']});continue
  if item['opportunityId']is None and original_rows[number]['opportunity_id']is None and current['opportunity_id']and current['status']in ['evaluated','duplicate']:
   save_source(number,current['status'],current['evaluation'],current['error']);record({'row':number,'result':'guarded_creation_recovered','opportunityId':current['opportunity_id']});continue
  op=old_ops[str(number)]
  if op:
   protected=rpc('sourcing_closeout_capture',{'p_ids':[op['opportunity_id']]})[0]['protected']
   if protected:
    old=original_rows[number];save_source(number,old['status'],old['evaluation'],old['error']);record({'row':number,'result':'protected_skip','reason':protected});continue
  save_source(number,'pending',original_rows[number]['evaluation'],'Authorized bounded replay pending; original snapshot preserved')
 worker.progress(tab['tab_id'],[])
 deadline=time.monotonic()+args.max_seconds
 try:
  for index,item in enumerate(manifest['rows']):
   number=item['rowNumber']
   if number in done:continue
   if time.monotonic()>deadline:raise RuntimeError('Bounded replay deadline; resume saved manifest checkpoint')
   worker.heartbeat()
   if index%20==0:wait_for_database(db,attempts=1)
   old=deepcopy(original_rows[number]);op=old_ops[str(number)];c=cs[old['candidate_id']];s=ss[c['seed_id']]
   if op:
    protected=rpc('sourcing_closeout_capture',{'p_ids':[op['opportunity_id']]})[0]['protected']
    if protected:
     save_source(number,old['status'],old['evaluation'],old['error'])
     record({'row':number,'item':item['ebayItemId'],'asin':item['asin'],'result':'protected_skip','reason':protected});continue
   save_source(number,'pending',old['evaluation'],'Authorized bounded replay in progress; original snapshot preserved')
   policy=platform_eligibility(s,c)
   if policy['result']!='pass':
    scored=score_candidate(c,s,worker.settings,matching_context={'offline_identity_policy':'phase3_shadow'})
    save_source(number,'excluded',scored['matching_diagnostics_json'],policy['reason'])
    record({'row':number,'item':item['ebayItemId'],'asin':item['asin'],'result':'policy_excluded','reason':policy['reason'],'providerCalls':0});continue
   try:
    if not op:
     result=worker.process_row(tab,old)
     latest=db.table('sourcing_flipmine_rows').select('*').eq('tab_id',tab['tab_id']).eq('row_number',number).single().execute().data
     save_source(number,latest['status'],latest['evaluation'],latest['error'])
     record({'row':number,'item':item['ebayItemId'],'asin':item['asin'],'result':result,'opportunityId':latest['opportunity_id'],'reason':latest['error']});continue
    if old['opportunity_id']!=op['opportunity_id']:
     fm.rpc(db,'flipmine_bind_candidate',p_run=run_id,p_tab=tab['tab_id'],p_row=number,p_candidate=c)
     linked=db.table('sourcing_flipmine_rows').select('opportunity_id').eq('tab_id',tab['tab_id']).eq('row_number',number).single().execute().data
     assert linked['opportunity_id']==op['opportunity_id'],'Exact-pair decision changed during bind'
     save_source(number,'pending',old['evaluation'],'Existing exact-pair decision linked; fresh full evaluation pending')
    fresh=worker.context.seed(item['asin'])
    if not fresh:
     reason=worker.context.exclusions.get(item['asin'])or'Excluded by normal catalog eligibility/inventory/demand checks'
     capture=rpc('sourcing_closeout_capture',{'p_ids':[op['opportunity_id']]})[0]
     if capture['protected']:
      save_source(number,old['status'],old['evaluation'],old['error']);record({'row':number,'result':'protected_skip','reason':capture['protected']});continue
     diagnostics=deepcopy(op.get('matching_diagnostics_json')or{})
     diagnostics['businessEligibilityChecks']=[*(diagnostics.get('businessEligibilityChecks')or[]),{'code':'catalog_seed_eligibility','label':'Current catalog eligibility / inventory / demand','result':'fail','blocking':True,'explanation':reason}]
     from sourcing_decision_trace import enrich_sourcing_diagnostics
     diagnostics=enrich_sourcing_diagnostics(diagnostics,status='rejected',opportunity_type=op.get('opportunity_type'),profit=op.get('profit'),roi_percent=op.get('roi_percent'))
     request={'p_allowed_ids':[op['opportunity_id']],'p_rows':[{'requestId':str(uuid.uuid5(NS,tag+':catalog-excluded:'+str(number))),'opportunityId':op['opportunity_id'],'state':capture['state'],'hash':capture['hash'],'patch':{'status':'rejected','matching_diagnostics_json':diagnostics}}]}
     write_checkpoint(pending,{'request':request,'diagnostics':diagnostics,'sourceStatus':'excluded','sourceError':reason,'summary':{'row':number,'item':item['ebayItemId'],'asin':item['asin'],'result':'catalog_excluded','reason':reason,'opportunityId':op['opportunity_id']}});flush_pending();continue
    fresh={**fresh,'seed_id':s['seed_id'],'sourcing_run_id':s['sourcing_run_id'],'source_mode':s.get('source_mode') or fresh.get('source_mode')}
    if worker.token is None:worker.token=fm.get_access_token()
    payload=fm.fetch_listing(worker.token,item['ebayItemId'],worker.settings)
    candidate=fm.map_item(fresh,payload);candidate.update(candidate_id=c['candidate_id'],seed_id=s['seed_id'],sourcing_run_id=c['sourcing_run_id'],source_tags=list(set(c.get('source_tags')or[])|{'flipmine'}))
    db.table('sourcing_seed_asins').upsert(fresh,on_conflict='seed_id').execute();db.table('sourcing_ebay_candidates').upsert(candidate,on_conflict='candidate_id').execute()
    capture=rpc('sourcing_closeout_capture',{'p_ids':[op['opportunity_id']]})[0]
    if capture['protected']:
     save_source(number,old['status'],old['evaluation'],old['error']);record({'row':number,'result':'protected_skip','reason':capture['protected']});continue
    worker.evaluation_context()
    scored=list(score_candidate_batches(db,[candidate],{fresh['seed_id']:fresh},worker.settings,fetch_keepa_price_context_by_asin(db,[item['asin']]),worker.history,worker.matching,fetch_owned_units_by_asin(db,[fresh])))[0];assert scored
    patch=mutable_decision_patch(scored);patch['matching_diagnostics_json']['targetedReplay']={'manifestHash':tag,'source':'authorized_fresh_phase2_text_pipeline'}
    request={'p_allowed_ids':[r['opportunityId']for r in manifest['rows']if r['opportunityId']],'p_rows':[{'requestId':str(uuid.uuid5(NS,tag+':decision:'+str(number))),'opportunityId':op['opportunity_id'],'state':capture['state'],'hash':capture['hash'],'patch':patch}]}
    write_checkpoint(pending,{'request':request,'diagnostics':patch['matching_diagnostics_json'],'summary':{'row':number,'item':item['ebayItemId'],'asin':item['asin'],'result':'fresh_evaluation','opportunityId':op['opportunity_id'],'status':patch['status'],'normalPipelineStatus':scored['status'],'profit':scored['profit'],'roi':scored['roi_percent']}});flush_pending()
   except ListingUnavailable as error:
    db.table('sourcing_ebay_candidates').update({'listing_status':'ended','available_quantity':0,'last_seen_at':fm.now()}).eq('candidate_id',c['candidate_id']).execute()
    if op:
     capture=rpc('sourcing_closeout_capture',{'p_ids':[op['opportunity_id']]})[0]
     if capture['protected']:
      save_source(number,old['status'],old['evaluation'],old['error']);record({'row':number,'result':'protected_skip','reason':capture['protected']});continue
     patch=unavailable_decision_patch(op,fm.safe_error(error))
     request={'p_allowed_ids':[op['opportunity_id']],'p_rows':[{'requestId':str(uuid.uuid5(NS,tag+':ended:'+str(number))),'opportunityId':op['opportunity_id'],'state':capture['state'],'hash':capture['hash'],'patch':patch}]}
     write_checkpoint(pending,{'request':request,'diagnostics':patch['matching_diagnostics_json'],'sourceStatus':'excluded','sourceError':fm.safe_error(error),'summary':{'row':number,'item':item['ebayItemId'],'asin':item['asin'],'result':'confirmed_unavailable','opportunityId':op['opportunity_id']}});flush_pending()
    else:
     save_source(number,'excluded',{'availability':{'result':'blocked','reason':fm.safe_error(error)}},fm.safe_error(error));record({'row':number,'item':item['ebayItemId'],'asin':item['asin'],'result':'confirmed_unavailable'})
   if index%20==0:worker.progress(tab['tab_id'],[])
  assert len(done)==target_total
  worker.progress(tab['tab_id'],[])
  summary=fm.rpc(db,'flipmine_tab_evaluated',p_run=run_id,p_tab=tab['tab_id']);assert summary['failed']==0
  db.table('sourcing_flipmine_runs').update({'status':'evaluated','completed_at':fm.now(),'summary':{'phase':'awaiting_presentation','targetedReplay':True,'manifestHash':tag,'rows':target_total}}).eq('run_id',run_id).eq('status','running').execute()
  (root/'usage-after.json').write_text(json.dumps(usage()));print('All selected source rows terminal; await duplicate/presentation closeout before Complete.',flush=True)
 except Exception as error:
  fm.rpc(db,'flipmine_refresh_progress',p_run=run_id,p_tab=tab['tab_id'])
  db.table('sourcing_flipmine_tabs').update({'status':'partial','error_summary':fm.safe_error(error)}).eq('tab_id',tab['tab_id']).eq('run_id',run_id).execute()
  db.table('sourcing_flipmine_runs').update({'status':'partial','error_summary':fm.safe_error(error),'completed_at':fm.now()}).eq('run_id',run_id).execute();raise

if __name__=='__main__':
 try:main()
 except Exception as error:
  # A failure during lease preparation must also remain visible, not wait for
  # stale-worker expiry. Scope every update to this deterministic replay run.
  state=ROOT/'tmp/phase3b-replay/state.json'
  if '--execute'in sys.argv and state.exists():
   try:
    saved=json.loads(state.read_text(encoding='utf-8'));db=get_supabase_client()
    db.table('sourcing_flipmine_tabs').update({'status':'partial','error_summary':fm.safe_error(error)}).eq('tab_id',saved['originalTab']['tab_id']).eq('run_id',saved['runId']).eq('status','running').execute()
    db.table('sourcing_flipmine_runs').update({'status':'partial','error_summary':fm.safe_error(error),'completed_at':fm.now()}).eq('run_id',saved['runId']).eq('status','running').execute()
   except Exception:pass
  print('TARGETED_REPLAY_STOPPED '+fm.safe_error(error),file=sys.stderr);raise SystemExit(1)

