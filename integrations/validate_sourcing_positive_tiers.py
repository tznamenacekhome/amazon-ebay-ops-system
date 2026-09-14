"""Offline source-tiered positive identity safety replay; no live clients.

An explicit receiving correct_item assertion is kept distinct from purchases
and manual workflow memory. Missing/contradictory identity links stay visible.
The label is never passed as a feature to the matcher.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
from video_game_identity import build_identity_comparison


def evaluate(rows):
    purchases={r.get('purchase_item_id'):r for r in rows if r['source_table']=='purchase_items'}
    strict, unresolved, broad = [], [], []
    seen=set()
    for row in rows:
        context=row.get('raw_context_json') or {}
        source=context.get('receiving_outcome') or context.get('purchase_item') or context.get('manual_match') or {}
        reference=purchases.get(row.get('purchase_item_id')) or {}
        purchase=(reference.get('raw_context_json') or {}).get('purchase_item') or {}
        amazon=source.get('amazon_title')
        linked_reference=bool(reference and reference.get('asin')==row.get('asin') and
                              reference.get('purchase_item_id')==row.get('purchase_item_id'))
        if not amazon and linked_reference: amazon=purchase.get('amazon_title')
        ebay=source.get('ebay_title') or source.get('title')
        receiving=row['source_table']=='matching_intelligence_receiving_outcomes' and source.get('outcome')=='correct_item'
        exact=bool(row.get('asin') and row.get('ebay_item_id') and source.get('asin')==row['asin'] and
                   str(source.get('ebay_item_id') or '')==str(row['ebay_item_id']))
        key=(row.get('asin'),row.get('ebay_item_id'),amazon,ebay,receiving)
        if key in seen: continue
        seen.add(key)
        item={'sourceId':row.get('source_id'),'sourceTable':row['source_table'],
              'asin':row.get('asin'),'ebayItemId':row.get('ebay_item_id'),
              'purchaseItemId':row.get('purchase_item_id'),'reviewedAt':row.get('reviewed_at'),
              'amazonTitle':amazon,'ebayTitle':ebay,'referenceLinkedByPurchaseIdAndAsin':linked_reference,
              'exactSourceIdentity':exact,'sourceTier':'strict_receiving_assertion' if receiving and exact else 'workflow_candidate',
              'rawSourceRetainedInInput':True}
        if not amazon or not ebay or receiving and not exact:
            unresolved.append({**item,'reason':'Missing full pair titles or exact receiving identity; not silently counted as a pass'})
            continue
        # System belongs to the stored source; no platform is assigned from a
        # label or from the other side of the comparison.
        seed={'asin':row['asin'],'system':source.get('system')}
        before=build_identity_comparison(amazon_title=amazon,ebay_title=ebay,seed=seed)
        after=build_identity_comparison(amazon_title=amazon,ebay_title=ebay,seed=seed,policy='phase3_shadow')
        item.update(beforeVerdict=before['evidenceDecision']['productIdentityVerdict'],
                    afterVerdict=after['evidenceDecision']['productIdentityVerdict'],
                    reason=after['reason'], fields={s:after[s]['fields'] for s in ('amazon','ebay')})
        (strict if receiving and exact else broad).append(item)
    def summary(items):
        return {'rows':len(items),'before':dict(Counter(r['beforeVerdict'] for r in items)),
                'after':dict(Counter(r['afterVerdict'] for r in items)),
                'matchingExclusions':sum(r['afterVerdict']!='match' for r in items)}
    return {'strict':summary(strict),'broader':summary(broad),'strictRows':strict,'broaderRows':broad,
            'unresolvedSources':unresolved,'strictLabelsUsedAsFeatures':False,
            'limitations':['Frozen receiving assertions are as-of evidence; later conflicting outcomes must be reconciled before any rollout.',
                           'Purchase-import payloads often lack Browse Game Name/aspects. These missing fields are not synthesized.',
                           'Identity replay does not promote rows or override commercial/lifecycle rules.']}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    if args.input.resolve()==args.output.resolve():parser.error('Never overwrite frozen source')
    result=evaluate(json.loads(args.input.read_text(encoding='utf8')))
    args.output.write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps({k:result[k] for k in ('strict','broader')}))
