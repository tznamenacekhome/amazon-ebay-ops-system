"""End-to-end runner test with real disposable SQL and no production network."""
import json,sys
from pathlib import Path
from tempfile import TemporaryDirectory
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations'))
import sourcing_phase3_refresh as refresh
scope={};exec(compile(Path(__file__).with_name('verify_sourcing_decision_guard.py').read_text(encoding='utf-8').split('checks = []')[0],__file__,'exec'),scope)
seed,sql,quote,capture=(scope[k] for k in ('seed','sql','quote','capture'))
row=seed();reviewed=seed()
if sql('select count(*) from sourcing_settings')=='0':sql('insert into sourcing_settings default values')
sql(f"update sourcing_seed_asins set amazon_title='Crystal Harbor Nintendo Switch',target_sale_price=100 where seed_id='{row['seed']}'")
sql(f"update sourcing_ebay_candidates set ebay_title='Crystal Harbor Nintendo Switch',price=20,landed_cost=20,shipping_cost=0,condition='New',item_location_country='US',buying_options=array['FIXED_PRICE'],available_quantity=1,listing_status='active' where candidate_id='{row['candidate']}'")
sql(scope['action'](reviewed,verdict='unsure'))
review_before=capture(reviewed)

class LocalRpc:
    def __call__(self,name,body):
        if name=='sourcing_closeout_cohort':return [dict(opportunity_id=row['op'],exclusion=None),dict(opportunity_id=reviewed['op'],exclusion='operator_reviewed')]
        ids=lambda values:'array['+','.join(quote(x) for x in values)+']::uuid[]'
        if name=='sourcing_closeout_capture':
            return json.loads(sql(f"select sourcing_closeout_capture({ids(body['p_ids'])},{str(body.get('p_sources',True)).lower()})"))
        if name=='sourcing_closeout_write_batch':
            return json.loads(sql(f"select sourcing_closeout_write_batch({quote(refresh.exact_json(body['p_rows']))}::jsonb,{ids(body['p_allowed_ids'])})"))
        raise AssertionError(name)

refresh.Rpc=LocalRpc
with TemporaryDirectory(dir='tmp/sourcing-closeout') as directory:
    sys.argv=['runner','--write','--output',directory]
    assert refresh.main()==0
    summary=json.loads((Path(directory)/'summary.json').read_text(encoding='utf-8'))
    assert summary['outcomes']=={'written':1},summary
    assert summary['excluded']['operator_reviewed']==1
    assert summary['previousSuccesses']['decisions']=={'match':1},summary
    assert refresh.main()==0
    assert sql(f"select count(*) from sourcing_decision_refresh_log where opportunity_id='{row['op']}'")=='1'
    assert capture(reviewed)==review_before
    Path('tmp/sourcing-closeout/runner-test.json').write_text(json.dumps({'passed':True,'summary':summary,'idempotentRerun':True,'reviewedUnchanged':True},indent=2),encoding='utf-8')
print('End-to-end stored-evidence runner, reviewed exclusion, recapture and idempotent resume passed')
