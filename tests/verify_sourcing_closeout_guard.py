"""Disposable acceptance for unreviewed classification and closeout RPCs."""
import json
from pathlib import Path

scope={}
exec(compile(Path(__file__).with_name('verify_sourcing_decision_guard.py').read_text(encoding='utf-8').split('checks = []')[0],__file__,'exec'),scope)
seed,sql,quote,capture,apply,action=(scope[k] for k in ('seed','sql','quote','capture','apply','action'))
checks=[]

for verdict in ('correct','incorrect','unsure'):
    row=seed();before=capture(row);sql(action(row,verdict=verdict));after=capture(row)
    result=apply(row,before);assert result['result']=='protected_skip',(verdict,result)
    assert capture(row)==after
    checks.append('new explicit '+verdict+' excludes write atomically')

row=seed('dismissed')
sql(f"insert into sourcing_actions(opportunity_id,asin,ebay_item_id,action_type,dismiss_reason,raw_action_context) values('{row['op']}','{row['asin']}','{row['item']}','dismissed','duplicate_open_asin_opportunity',"+quote({'cleanup_source':'cleanup_sourcing_duplicate_asin_opportunities'})+"::jsonb)")
assert apply(row,capture(row))['result']=='written'
checks.append('automated duplicate dismissal is not human review')

row=seed('dismissed');sql(action(row,'dismissed'))
assert apply(row,capture(row))['result']=='protected_skip'
checks.append('human dismissal remains protected')

row=seed();sql(action(row,verdict='unsure'))
data=json.loads(sql(f"select sourcing_closeout_capture(array['{row['op']}']::uuid[])"))[0]
assert data['protected']=='operator_reviewed' and 'candidate' not in data
checks.append('capture excludes reviewed pair before source hydration')

row=seed();data=json.loads(sql(f"select sourcing_closeout_capture(array['{row['op']}']::uuid[])"))[0]
assert data['hash']==capture(row)['hash'] and data['candidate']['candidate_id']==row['candidate']
assert 'raw_ebay_json' not in data['state']['candidate']
assert 'diagnosticsHash' in data['state']['opportunity']
checks.append('compact guard and exact source capture agree')

first=seed();second=seed();one=capture(first);two=capture(second)
rows=[{'requestId':str(scope['uuid4']()),'opportunityId':r['op'],'state':c['state'],'hash':c['hash'],'patch':scope['patch']()} for r,c in [(first,one),(second,two)]]
rows[1]['patch']['score']='invalid'
try:
    sql(f"select sourcing_closeout_write_batch({quote(rows)}::jsonb,array['{first['op']}','{second['op']}']::uuid[])")
    raise AssertionError('Batch must roll back')
except RuntimeError:pass
assert capture(first)==one and capture(second)==two
checks.append('batch failure rolls back earlier row and its audit')

for name,call in [('capture bound',"select sourcing_closeout_capture('{}'::uuid[])"),
                  ('calendar bound',"select sourcing_closeout_cohort(now()-interval '32 days',now())")]:
    try:sql(call);raise AssertionError(name)
    except RuntimeError:pass
    checks.append(name)

Path('tmp/sourcing-closeout/closeout-guard-tests.json').write_text(json.dumps({'passed':True,'checks':checks,'count':len(checks)},indent=2),encoding='utf-8')
print(f'{len(checks)} closeout guard checks passed')
