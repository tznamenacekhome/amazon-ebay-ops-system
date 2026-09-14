"""Check legacy inventory actions against the scorer's ASIN-wide hold semantics.

Mutation fixture: only the named disposable database; never production.
"""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations'))
from score_sourcing_opportunities import is_inventory_snooze_action

# Reuse fixture helpers without executing the separate acceptance suite.
helpers = Path(__file__).with_name('verify_sourcing_decision_guard.py').read_text(encoding='utf-8')
scope = {}
exec(compile(helpers.split('checks = []')[0], str(Path(__file__)), 'exec'), scope)
seed, sql, quote, capture, apply = (scope[name] for name in ('seed', 'sql', 'quote', 'capture', 'apply'))
row = seed()
other = seed(asin=row['asin'])
context = {'actionType': 'inventory_snooze', 'currentOwnedUnits': 5}
assert is_inventory_snooze_action({'raw_action_context': context})
sql(f"insert into sourcing_actions(opportunity_id,candidate_id,asin,ebay_item_id,action_type,raw_action_context) "
    f"values('{other['op']}','{other['candidate']}','{row['asin']}','{other['item']}',"
    f"'roi_snoozed',{quote(context)}::jsonb)")
before = capture(row)
result = apply(row, before)
after = capture(row)
proof = {'expected': 'protected_skip', 'result': result, 'opportunityId': row['op'],
         'holdOpportunityId': other['op'], 'sameAsin': True, 'differentListing': True,
         'actionType': 'roi_snoozed', 'rawActionType': 'inventory_snooze',
         'stateUnchanged': before == after,
         'auditRows': int(sql(f"select count(*) from sourcing_decision_refresh_log where opportunity_id='{row['op']}'"))}
Path('tmp/sourcing-guard-canonicalization/inventory-compatibility.json').write_text(
    json.dumps(proof, indent=2), encoding='utf-8')
print(json.dumps(proof))
assert result['result'] == 'protected_skip', 'ASIN-wide legacy inventory action must protect other listings'
assert before == after
