import sys,json,hashlib
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,sys.argv[1])
from sourcing_match_rules import evaluate_static_match_rules
from score_sourcing_opportunities import score_candidate
raw=json.loads(Path('tmp/sourcing-phase1/settings.json').read_text())[0]
settings=SimpleNamespace(**{k:float(v) if k in ('min_roi_percent','min_profit_dollars','best_offer_min_ask_percent') else v for k,v in raw.items()})
def clean(v):
 if isinstance(v,dict):return {k:clean(x) for k,x in v.items() if k not in ('evaluatedAt','evaluationId','evaluated_at','created_at','updated_at')}
 if isinstance(v,list):return [clean(x) for x in v]
 return v
def digest(v):return hashlib.sha256(json.dumps(clean(v),sort_keys=True).encode()).hexdigest()
result={}
for cohort in ('sourcing-phase1','sourcing-phase3'):
 for row in json.loads(Path('tmp',cohort,'current-evidence.json').read_text(encoding='utf8')):
  c=dict(row.get('candidate') or {});c.update({k:row.get(k,c.get(k)) for k in ('asin','candidate_id','seed_id','sourcing_run_id')});s=row.get('seed') or {}
  result[cohort+row['opportunity_id']]={'static':digest(evaluate_static_match_rules(c,s,excluded_keywords=settings.excluded_keywords,allowed_item_location_countries=settings.item_location_countries)),'score':digest(score_candidate(c,s,settings))}
Path(sys.argv[2]).write_text(json.dumps(result))
print('Default static and full scorer output: '+str(len(result)))
