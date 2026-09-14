"""Mutation acceptance tests. Only the named disposable database is allowed."""
import json
import os
import subprocess
from uuid import uuid4
from pathlib import Path

CONTAINER = 'mbop-phase2-review-test'
assert os.environ.get('MBOP_REVIEW_TEST_CONTAINER') == CONTAINER
COMMAND = ['docker', 'exec', '-i', CONTAINER, 'psql', '-U', 'postgres', '-At', '-v', 'ON_ERROR_STOP=1']


def sql(statement):
    result = subprocess.run(COMMAND, input=statement, text=True, capture_output=True, encoding='utf-8')
    if result.returncode:
        raise RuntimeError(result.stderr)
    return result.stdout.strip()


def quote(value):
    if value is None:
        return 'null'
    return "'" + (json.dumps(value) if isinstance(value, (dict, list)) else str(value)).replace("'", "''") + "'"


def seed(status='open', asin=None, item=None):
    op, candidate, seed_id = [str(uuid4()) for _ in range(3)]
    asin = asin or 'T' + uuid4().hex[:9]
    item = item or 'v1|' + uuid4().hex + '|0'
    existing = sql(f"select candidate_id from sourcing_ebay_candidates where ebay_item_id={quote(item)}")
    candidate = existing or candidate
    candidate_insert = '' if existing else (
        f"insert into sourcing_ebay_candidates(candidate_id,seed_id,asin,ebay_item_id) values('{candidate}','{seed_id}','{asin}','{item}');")
    sql(f"insert into sourcing_seed_asins(seed_id,asin,source_mode) values('{seed_id}','{asin}','recent_sales');"
        + candidate_insert +
        f"insert into sourcing_opportunities(opportunity_id,candidate_id,seed_id,asin,ebay_item_id,opportunity_type,status) "
        f"values('{op}','{candidate}','{seed_id}','{asin}','{item}','buy_now','{status}');")
    return dict(op=op, candidate=candidate, seed=seed_id, asin=asin, item=item)


def capture(row):
    return json.loads(sql(f"select jsonb_build_object('state',s,'hash',sourcing_guard_hash(s)) "
                          f"from (select sourcing_decision_guard_state('{row['op']}') s) t"))


def patch():
    return {'status': 'open', 'score': 75, 'matching_diagnostics_json': {
        'static_rules': {'identity_comparison': {'evidenceDecision': {'productIdentityVerdict': 'match'}}},
        'presentationDecision': {'eligible': True}}}


def apply(row, before, request=None, changes=None, allowed=True):
    request = request or str(uuid4())
    return json.loads(sql(f"select sourcing_refresh_decision_guarded('{request}','{row['op']}',"
        f"ARRAY[{quote(row['op']) if allowed else ''}]::uuid[],{quote(before['state'])}::jsonb,"
        f"{quote(before['hash'])},{quote(changes or patch())}::jsonb)"))


def action(row, kind='matching_feedback', verdict=None, asin=None):
    context = {'matchingFeedback': {'version': 'matching_feedback_v3', 'pairVerdict': verdict}}
    return (f"insert into sourcing_actions(opportunity_id,candidate_id,asin,ebay_item_id,action_type,raw_action_context) "
            f"values('{row['op']}','{row['candidate']}','{asin or row['asin']}','{row['item']}','{kind}',{quote(context)})")


checks = []


def record(name):
    checks.append(name)


row = seed(); before = capture(row); request = str(uuid4())
assert apply(row, before, request)['result'] == 'written'
after = capture(row)
assert after['state']['opportunity']['score'] == 75
assert before['state']['actions'] == after['state']['actions']
assert before['state']['candidate'] == after['state']['candidate']
record('unchanged row writes with before/after audit and no source/action changes')
assert apply(row, before, request)['replayed']
assert capture(row) == after
record('retry idempotency')

# Exercise raw JSON numeric tokens without routing them through binary floats.
for values in [('25', '25.0', '25.00', '25.000'), ('0', '0.0', '-0.00'), ('1.5', '1.50'),
               ('12345678901234567890.123456789', '12345678901234567890.1234567890')]:
    hashes = [sql(f"select sourcing_guard_hash('{{\"value\":{value}}}'::jsonb)") for value in values]
    assert len(set(hashes)) == 1, values
    record('exact numeric equivalence ' + '/'.join(values))

for left, right in [('25.00', '25.01'), ('25', '26'), ('0', 'null'),
                    ('null', '""'), ('false', 'null'), ('[1,2]', '[2,1]'), ('"ID"', '"id"')]:
    assert sql(f"select sourcing_guard_hash({quote(left)}::jsonb) <> sourcing_guard_hash({quote(right)}::jsonb)") == 't'
    record('distinct JSON values ' + left + '/' + right)

for left, right in [('25', '25.0'), ('25.0', '25.00'), ('0', '-0.00'), ('1.5', '1.50')]:
    row = seed()
    sql(f"update sourcing_opportunities set max_offer_price={left} where opportunity_id='{row['op']}'")
    before = capture(row)
    # Numeric equality must work in the actual guarded transaction as well.
    before['state']['opportunity']['max_offer_price'] = float(right)
    assert apply(row, before)['result'] == 'written'
    record('numeric transaction equivalence ' + left + '/' + right)

for left, right in [('25.00', '25.01'), ('25', '26'), ('0', 'null')]:
    row = seed()
    sql(f"update sourcing_opportunities set max_offer_price={left} where opportunity_id='{row['op']}'")
    before = capture(row)
    sql(f"update sourcing_opportunities set max_offer_price={right} where opportunity_id='{row['op']}'")
    changed = capture(row)
    assert apply(row, before)['result'] == 'stale_state_skip'
    assert capture(row) == changed
    record('numeric transaction mutation ' + left + '/' + right)

row = seed()
sql(f"update sourcing_opportunities set updated_at='2026-09-13T12:00:00.120000Z' where opportunity_id='{row['op']}'")
before = capture(row)
before['state']['opportunity']['updated_at'] = '2026-09-13T05:00:00.12-07:00'
before['state']['pairHistory'][0]['updated_at'] = '2026-09-13 12:00:00.120+00'
request = str(uuid4())
assert apply(row, before, request)['result'] == 'written'
before['state']['opportunity']['updated_at'] = '2026-09-13T12:00:00.120Z'
assert apply(row, before, request)['replayed']
record('equivalent timestamp offsets and precision write and replay')

row = seed(); before = capture(row)
sql(f"update sourcing_opportunities set updated_at=updated_at+interval '1 microsecond' where opportunity_id='{row['op']}'")
assert apply(row, before)['result'] == 'stale_state_skip'
record('actual microsecond timestamp change skips')

for left, right, equal in [('{"a":25.00,"b":[false,null]}', '{"b":[false,null],"a":25}', True),
                           ('{"a":25}', '{"a":26}', False),
                           ('{"a":null}', '{"a":0}', False),
                           ('{"a":null}', '{"a":""}', False),
                           ('{"a":false}', '{"a":null}', False)]:
    row = seed()
    sql(f"update sourcing_ebay_candidates set raw_ebay_json={quote(left)}::jsonb where candidate_id='{row['candidate']}'")
    before = capture(row)
    sql(f"update sourcing_ebay_candidates set raw_ebay_json={quote(right)}::jsonb where candidate_id='{row['candidate']}'")
    assert apply(row, before)['result'] == ('written' if equal else 'stale_state_skip')
    record('nested JSON transaction ' + left + '/' + right)

mutations = {
    'updated_at': lambda r: f"update sourcing_opportunities set updated_at=clock_timestamp() where opportunity_id='{r['op']}'",
    'new action': lambda r: action(r),
    'new review': lambda r: action(r, verdict='unsure'),
    'ASIN': lambda r: f"update sourcing_opportunities set asin='CHANGED' where opportunity_id='{r['op']}'",
    'candidate': lambda r: f"update sourcing_opportunities set candidate_id=null where opportunity_id='{r['op']}'",
    'listing': lambda r: f"update sourcing_opportunities set ebay_item_id='CHANGED' where opportunity_id='{r['op']}'",
    'variation': lambda r: f"update sourcing_ebay_candidates set raw_ebay_json='{{\"variationId\":\"changed\"}}' where candidate_id='{r['candidate']}'",
    'reference metadata': lambda r: f"update sourcing_seed_asins set raw_context_json='{{\"inferred_system\":\"PS 5\"}}' where seed_id='{r['seed']}'",
    'new hold': lambda r: f"insert into sourcing_blocked_asins(asin,reason) values('{r['asin']}','test hold')",
}
for name, mutation in mutations.items():
    row = seed(); before = capture(row); sql(mutation(row)); changed = capture(row)
    assert apply(row, before)['result'] == 'stale_state_skip', name
    assert capture(row) == changed, name
    record('stale ' + name)

for status in ['purchased', 'purchased_pending_match', 'matched_to_purchase', 'completed', 'dismissed', 'watching', 'inventory_snoozed', 'roi_snoozed']:
    row = seed(status); before = capture(row)
    result = apply(row, before)
    assert result['result'] == 'protected_skip', (status, row, result)
    assert capture(row) == before
    record('protected ' + status)

for kind in ['dismissed', 'confirmed_valid_match', 'confirmed_exclusion']:
    row = seed(); sql(action(row, kind)); before = capture(row)
    assert apply(row, before)['result'] == 'protected_skip'
    record('protected action ' + kind)

row = seed(); before = capture(row); before['hash'] = 'bad'
assert apply(row, before)['result'] == 'stale_state_skip'
record('before hash mismatch')

for name, changes, allowed in [('partial failure', {**patch(), 'score': 'not numeric'}, True),
                               ('bounded IDs', patch(), False),
                               ('cannot write hold fields', {**patch(), 'business_hold': None}, True)]:
    row = seed(); before = capture(row)
    try:
        apply(row, before, changes=changes, allowed=allowed)
        raise AssertionError('Expected SQL rejection: ' + name)
    except RuntimeError:
        pass
    assert capture(row) == before
    assert sql(f"select count(*) from sourcing_decision_refresh_log where opportunity_id='{row['op']}'") == '0'
    record(name)

row = seed(); sql(f"insert into sourcing_blocked_asins(asin,reason) values('{row['asin']}','business hold')")
before = capture(row)
try:
    apply(row, before)
    raise AssertionError('Business hold bypassed')
except RuntimeError:
    pass
assert capture(row) == before
record('business hold cannot be cleared by route recomputation')
sql(action(row, 'confirmed_valid_match', 'correct')); before = capture(row)
assert apply(row, before)['result'] == 'protected_skip'
record('Confirm Match cannot bypass business hold')

row = seed(); sql(action(row, verdict='incorrect')); before = capture(row)
assert apply(row, before)['result'] == 'protected_skip'
other = seed(item=row['item']); before = capture(other)
assert apply(other, before)['result'] == 'written'
record('Incorrect Match exact-pair scope does not blacklist listing')

row = seed(); history = seed(asin=row['asin'], item=row['item'], status='dismissed'); before = capture(row)
assert apply(row, before)['result'] == 'protected_skip'
record('historical dismissal cannot reopen')

row = seed(); other = seed(asin=row['asin']); sql(action(other, 'inventory_snoozed')); before = capture(row)
assert apply(row, before)['result'] == 'protected_skip'
record('ASIN-wide inventory hold protects another listing')

row = seed(item='v1|' + str(uuid4().int)[:15] + '|0'); before = capture(row)
sql(f"insert into sourcing_declined_ebay_offers(ebay_legacy_item_id,declined_offer_amount) values('{row['item'].split('|')[1]}',25)")
assert apply(row, before)['result'] == 'stale_state_skip'
record('new declined offer changes guarded state')
sql(f"update sourcing_opportunities set opportunity_type='best_offer',max_offer_price=20 where opportunity_id='{row['op']}'")
before = capture(row)
try:
    result = apply(row, before)
    assert result['result'] != 'stale_state_skip', 'Unchanged numeric state falsely skipped before business hold validation'
    raise AssertionError('Existing declined offer bypassed')
except RuntimeError:
    pass
assert capture(row) == before
record('existing declined offer cannot be bypassed')

row = seed(); before = capture(row)
writer = subprocess.Popen(COMMAND, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
writer.stdin.write('begin;' + action(row) + ";select 'locked';select pg_sleep(2);commit;\n")
writer.stdin.flush()
assert writer.stdout.readline().strip() == 'BEGIN'
assert writer.stdout.readline().strip() == 'INSERT 0 1'
assert writer.stdout.readline().strip() == 'locked'
assert apply(row, before)['result'] == 'stale_state_skip'
writer.stdin.close(); writer.wait(timeout=10)
assert writer.returncode == 0
assert capture(row)['state']['opportunity']['score'] is None
record('concurrent operator insert skips without overwriting')

Path(os.environ.get('MBOP_GUARD_TEST_OUTPUT', 'tmp/sourcing-guard-canonicalization/guard-tests.json')).write_text(json.dumps({'passed': True, 'checks': checks, 'count': len(checks)}, indent=2), encoding='utf-8')
print(f'{len(checks)} disposable database guard checks passed')
