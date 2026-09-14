"""Build a read-only regression corpus from exported action/snapshot evidence.

No database or marketplace client, rule generation, or write mode. An operator
report is evidence to review, not proof of the pipeline component that failed.
"""
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path


FIELD_ROWS = {'coreGame':'core_game_identity','platform':'platform_system',
              'installment':'installment_number','edition':'edition_version',
              'packageType':'package_bundle_contents','digitalPhysical':'digital_physical'}


def build_corpus(actions):
    examples, pair_examples = [], []
    for action in actions:
        context = action.get('raw_action_context') or {}
        feedback = context.get('matchingFeedback') or {}
        if feedback.get('version') != 'matching_feedback_v3' or feedback.get('evidenceProvenance') != 'explicit':
            continue
        snapshot = action.get('snapshot') or {}
        linked = bool(action.get('action_id') and snapshot.get('action_id') == action['action_id']
                      and snapshot.get('asin') == action.get('asin')
                      and snapshot.get('ebay_item_id') == action.get('ebay_item_id'))
        comparison = context.get('diagnosticComparison') or {}
        base = dict(actionId=action.get('action_id'), asin=action.get('asin'),
                    ebayItemId=action.get('ebay_item_id'), timestamp=action.get('created_at'),
                    operatorVerdict=feedback.get('pairVerdict'), evaluation=context.get('evaluation'),
                    evaluationVersion=(context.get('evaluation') or {}).get('version'),
                    sourceSnapshot=deepcopy(snapshot), snapshotLinked=linked)
        verdict, evaluated = feedback.get('pairVerdict'), comparison.get('productIdentityVerdict')
        # Pair disagreement cannot tell us whether extraction or comparison failed.
        if verdict in {'correct','incorrect'}:
            disagreement = ('reported_false_positive' if verdict == 'incorrect' and evaluated == 'match'
                            else 'reported_false_negative' if verdict == 'correct' and evaluated == 'non-match'
                            else 'reported_review_exclusion' if verdict == 'correct' and evaluated in {'needs_review','unknown'}
                            else 'no_established_pair_disagreement')
            pair_examples.append({**base,'evaluatedVerdict':evaluated,'classification':disagreement})
        for correction in feedback.get('corrections') or []:
            field, side = correction.get('field'), correction.get('side')
            original = next((r for r in comparison.get('rows', [])
                             if r.get('key') in {field, FIELD_ROWS.get(field,field)}), {})
            parsed_evidence = original.get(str(side)+'Evidence') or {}
            prior = correction.get('before') or {}
            state = parsed_evidence.get('state')
            classification = ('unknown_extraction' if state == 'unknown'
                              else 'prior_correction_changed' if prior.get('actionId')
                              else 'reported_extraction_difference' if original and
                                   (original.get(side) != correction.get('value') or correction.get('state') != 'value')
                              else 'unclassified_correction')
            examples.append({**base,'field':field,'side':side,'scope':correction.get('scope'),
                             'originalSourceValue':snapshot.get('amazon_title' if side=='amazon' else 'ebay_title'),
                             'parserOutput':original.get(side),'parserEvidence':deepcopy(parsed_evidence),
                             'openingValue':deepcopy(prior),'correctedValue':correction.get('value'),
                             'correctedState':correction.get('state'),'classification':classification,
                             'comparisonResult':original.get('comparisonResult'),
                             'comparisonError':'not_established_by_field_correction'})
    return {'mode':'offline_read_only','examples':examples,'pairExamples':pair_examples,
            'correctionCounts':dict(Counter(x['classification'] for x in examples)),
            'reportedErrorsByField':dict(Counter(x['field'] for x in examples if x['classification']=='reported_extraction_difference')),
            'pairCounts':dict(Counter(x['classification'] for x in pair_examples)),
            'verifiedComparisonErrors':0,
            'limitation':'Reports retain operator claims; component causality and current applicability require replay and source validation.'}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    if args.input.resolve()==args.output.resolve(): parser.error('Output must not replace source evidence')
    args.output.write_text(json.dumps(build_corpus(json.loads(args.input.read_text(encoding='utf8'))),indent=2),encoding='utf8')
