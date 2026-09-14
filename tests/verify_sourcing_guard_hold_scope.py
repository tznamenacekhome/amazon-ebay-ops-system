"""Disposable PostgreSQL hold-scope and release acceptance tests."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations'))
from score_sourcing_opportunities import should_reactivate_inventory_snoozed

scope = {}
helpers = Path(__file__).with_name('verify_sourcing_decision_guard.py').read_text(encoding='utf-8')
exec(compile(helpers.split('checks = []')[0], __file__, 'exec'), scope)
seed, sql, quote, capture, apply = (scope[k] for k in ('seed', 'sql', 'quote', 'capture', 'apply'))
checks = []


def hold(row, kind='inventory_snoozed', context=None, cost=None):
    context = context or {'inventorySnooze': {'baselineUnits': 10, 'representAtUnits': 9}}
    sql(f"insert into sourcing_actions(opportunity_id,candidate_id,asin,ebay_item_id,action_type,raw_action_context,expected_purchase_cost) "
        f"values('{row['op']}','{row['candidate']}','{row['asin']}','{row['item']}',{quote(kind)},{quote(context)}::jsonb,{cost or 'null'})")


def inventory(row, units):
    sql(f"update sourcing_seed_asins set current_inventory_units={units} where seed_id='{row['seed']}'")


def verify(name, row, expected, before=None):
    before = before or capture(row)
    actual_before = capture(row)
    result = apply(row, before)
    assert result['result'] == expected, (name, result)
    if expected != 'written':
        assert capture(row) == actual_before, name
        assert sql(f"select count(*) from sourcing_decision_refresh_log where opportunity_id='{row['op']}'") == '0', name
    checks.append(name)


for kind, context in [('inventory_snoozed', None), ('roi_snoozed', {'actionType': 'inventory_snooze', 'inventorySnooze': {'representAtUnits': 9}})]:
    row = seed(); other = seed(asin=row['asin']); inventory(row, 10); hold(other, kind, context)
    verify(kind + ' same ASIN different listing', row, 'protected_skip')
    verify(kind + ' repeat protected attempt', row, 'protected_skip')
    unrelated = seed()
    verify(kind + ' different ASIN', unrelated, 'written')

row = seed(); inventory(row, 10); before = capture(row); other = seed(asin=row['asin']); hold(other)
verify('inventory hold inserted after manifest capture', row, 'protected_skip', before)

for context in [{'inventorySnooze': {'representAtUnits': 9}}, {'inventorySnooze': {'baselineUnits': 10}}]:
    row = seed(); other = seed(asin=row['asin']); hold(other, context=context); inventory(row, 9)
    assert should_reactivate_inventory_snoozed({'raw_action_context': context}, 'open', 9)
    verify('existing sell-through release ' + str(context), row, 'written')

row = seed(); other = seed(asin=row['asin']); hold(other, context={'inventorySnooze': {}}); inventory(row, 0)
verify('missing threshold cannot invent release', row, 'protected_skip')

row = seed(); other = seed(asin=row['asin']); inventory(row, 8)
hold(other, context={'inventorySnooze': {'representAtUnits': 1}})
hold(other, context={'inventorySnooze': {'representAtUnits': 9}})
verify('latest inventory threshold supersedes earlier hold', row, 'written')

row = seed(); other = seed(asin=row['asin']); inventory(row, 8); hold(other)
sql(f"insert into purchase_items(asin,quantity,current_status,marketplace) values('{row['asin']}',2,'received','amazon')")
verify('purchase pipeline prevents premature release', row, 'protected_skip')

row = seed(); other = seed(asin=row['asin']); inventory(row, 8); hold(other)
for status, market in [('cancelled', 'amazon'), ('received', 'ebay')]:
    sql(f"insert into purchase_items(asin,quantity,current_status,marketplace) values('{row['asin']}',20,'{status}','{market}')")
verify('cancelled and eBay pipeline excluded from owned units', row, 'written')

row = seed(); other = seed(asin=row['asin']); inventory(row, 8); hold(other)
item = sql(f"insert into purchase_items(asin,quantity,current_status,marketplace) values('{row['asin']}',2,'listed','amazon') returning item_id").splitlines()[0]
shipment = sql("insert into fba_shipments(shipment_code,workflow_status) values('TEST','finalized') returning fba_shipment_id").splitlines()[0]
sql(f"insert into fba_shipment_items(item_id,fba_shipment_id,quantity,included,outbound_remaining_quantity) values('{item}','{shipment}',2,true,2)")
verify('active outbound FBA pipeline prevents release', row, 'protected_skip')
sql(f"update fba_shipments set workflow_status='closed' where fba_shipment_id='{shipment}'")
verify('closed outbound FBA shipment no longer blocks release', row, 'written')

row = seed(); hold(row, 'roi_snoozed', {'actionType': 'snooze_roi'}, 25)
sql(f"update sourcing_opportunities set landed_cost=25 where opportunity_id='{row['op']}'")
verify('ROI same pair protected', row, 'protected_skip')
other = seed(asin=row['asin']); verify('ROI different listing not overblocked', other, 'written')
sql(f"update sourcing_opportunities set landed_cost=24 where opportunity_id='{row['op']}'")
verify('ROI existing price-improvement release', row, 'written')

row = seed(); hold(row, 'roi_snoozed', {'actionType': 'snooze_roi'}, 25)
sql(f"update sourcing_ebay_candidates set price=24 where candidate_id='{row['candidate']}'")
verify('ROI candidate price fallback release', row, 'written')

row = seed(); hold(row, 'roi_snoozed', {'actionType': 'snooze_roi'}, 25)
sql(f"update sourcing_ebay_candidates set price=0 where candidate_id='{row['candidate']}'")
verify('ROI unknown zero price cannot release hold', row, 'protected_skip')

for action, expected in [({'action_type':'inventory_snooze'},'inventory_snooze'),
                         ({'action_type':'roi_snooze'},'roi_snooze'),
                         ({'action_type':'snooze_roi'},'roi_snooze'),
                         ({'action_type':'dismissed','dismiss_reason':'inventory_snooze'},'other')]:
    assert sql(f"select sourcing_guard_hold_type({quote(action)}::jsonb)") == expected
    checks.append('normalize ' + str(action))

Path('tmp/sourcing-hold-scope/hold-tests.json').write_text(json.dumps({'passed':True,'count':len(checks),'checks':checks},indent=2),encoding='utf-8')
print(f'{len(checks)} hold-scope checks passed')
