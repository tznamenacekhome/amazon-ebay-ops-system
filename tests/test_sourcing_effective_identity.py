"""Scoped identity corrections must reach static rules and full admission."""
import unittest
from copy import deepcopy

from test_sourcing_phase3 import inputs, review, SETTINGS
from sourcing_match_rules import evaluate_static_match_rules
from score_sourcing_opportunities import score_candidate

CUTOFF = '2026-09-14T10:00:00+00:00'


def correction(field='platform', value='PS 5', **kwargs):
    return dict(side='ebay', field=field, scope='pair', state='value', value=value, **kwargs)


class EffectiveIdentityTests(unittest.TestCase):
    def setUp(self):
        self.seed, self.candidate = inputs('Crystal Harbor PlayStation 5', 'Crystal Harbor PlayStation 4', system='PS 5')

    def action(self, corrections=None, **kwargs):
        return review(self.seed, self.candidate, verdict='not_provided',
                      corrections=corrections or [correction()], **kwargs)

    def evaluate(self, actions=()):
        static = evaluate_static_match_rules(self.candidate, self.seed, identity_policy='phase3_shadow',
                                            scoped_reviews=list(actions), review_cutoff=CUTOFF)
        score = score_candidate(self.candidate, self.seed, SETTINGS, matching_context={
            'offline_identity_policy': 'phase3_shadow', 'offline_scoped_reviews': list(actions),
            'offline_review_cutoff': CUTOFF})
        return static, score

    def assert_platform_blocked(self, actions=()):
        static, score = self.evaluate(actions)
        self.assertEqual('conflict', static['identity_comparison']['comparisons']['platform']['result'])
        self.assertEqual('blocked', static['platform_rule']['result'])
        self.assertEqual('Blocked', static['recommendation'])
        self.assertEqual('rejected', score['status'])

    def test_raw_conflict(self):
        self.assert_platform_blocked()

    def test_exact_correction_reaches_full_score_and_preserves_provenance(self):
        action = self.action()
        action['actor'] = 'test-operator'
        original = deepcopy(self.candidate)
        static, score = self.evaluate([action])
        self.assertEqual('match', static['identity_comparison']['comparisons']['platform']['result'])
        self.assertEqual('pass', static['platform_rule']['result'])
        self.assertEqual([], static['hard_blocks'])
        self.assertEqual('Probable Match', static['recommendation'])
        self.assertEqual('open', score['status'])
        field = static['identity_comparison']['ebay']['fields']['platform']
        self.assertEqual('PlayStation 4', field['before']['value'])
        self.assertEqual('PlayStation 5', field['value'])
        source = field['sources'][0]
        self.assertEqual('a', source['actionId'])
        self.assertEqual('pair', source['scope'])
        self.assertEqual(action['created_at'], source['createdAt'])
        self.assertEqual('test-operator', source['actor'])
        self.assertEqual('blocked', static['platform_rule']['raw_rule']['result'])
        self.assertEqual(original, self.candidate)

    def test_stale_correction(self):
        action = self.action()
        action['snapshot']['ebay_title'] += ' changed'
        self.assert_platform_blocked([action])

    def test_wrong_scope_and_wrong_variation(self):
        for kind in ('scope', 'variation'):
            with self.subTest(kind=kind):
                action = self.action()
                if kind == 'scope':
                    action['raw_action_context']['matchingFeedback']['corrections'][0]['scope'] = 'asin'
                else:
                    action['ebay_item_id'] = 'v1|123456789|other'
                self.assert_platform_blocked([action])

    def test_latest_correction_wins(self):
        older = self.action()
        newer = self.action([correction(value='PS 4')], created='2026-09-13T12:00:00+00:00', action='b')
        self.assert_platform_blocked([older, newer])
        static, _ = self.evaluate([newer, older])
        self.assertEqual(['b'], [row['actionId'] for row in static['identity_comparison']['correctionApplication']])

    def test_stale_newer_does_not_resurrect_superseded_correction(self):
        older = self.action()
        newer = self.action(created='2026-09-13T12:00:00+00:00', action='b')
        newer['snapshot']['ebay_title'] += ' changed'
        self.assert_platform_blocked([older, newer])

    def test_corrected_conflict(self):
        self.assert_platform_blocked([self.action([correction(value='Xbox Series X')])])

    def test_legacy_ignores_scoped_corrections(self):
        before = evaluate_static_match_rules(self.candidate, self.seed)
        after = evaluate_static_match_rules(self.candidate, self.seed, scoped_reviews=[self.action()], review_cutoff=CUTOFF)
        self.assertEqual(before, after)
        self.assertEqual('blocked', after['platform_rule']['result'])

    def test_other_duplicate_checks_use_only_valid_effective_ebay_fields(self):
        for field, key, raw, safe, unsafe in (
            ('digitalPhysical', 'digital_download', 'digital download', 'Physical', 'Digital'),
            ('completeness', 'incomplete_listing', 'missing manual', 'Complete', 'Incomplete'),
            ('region', 'region', 'PAL', 'NTSC-U/C', 'PAL'),
        ):
            with self.subTest(field=field):
                self.seed, self.candidate = inputs('Crystal Harbor PS5', 'Crystal Harbor PS5', system='PS 5')
                self.candidate['raw_ebay_json']['description'] = raw
                initial, _ = self.evaluate()
                self.assertEqual('blocked', initial[key]['result'])
                action = self.action([correction(field, safe)])
                effective, _ = self.evaluate([action])
                self.assertEqual('pass', effective[key]['result'])
                self.assertTrue(effective[key]['raw_hits'])
                stale = deepcopy(action)
                stale['snapshot']['raw_ebay_json']['description'] = 'old description'
                stale_result, _ = self.evaluate([stale])
                self.assertEqual('blocked', stale_result[key]['result'])
                wrong_scope = deepcopy(action)
                wrong_scope['raw_action_context']['matchingFeedback']['corrections'][0]['scope'] = 'asin'
                wrong_result, _ = self.evaluate([wrong_scope])
                self.assertEqual('blocked', wrong_result[key]['result'])
                amazon_only = deepcopy(action)
                amazon_only['raw_action_context']['matchingFeedback']['corrections'][0]['side'] = 'amazon'
                amazon_result, _ = self.evaluate([amazon_only])
                self.assertEqual('blocked', amazon_result[key]['result'])
                self.candidate['raw_ebay_json']['description'] = 'Brand new sealed game'
                adverse, score = self.evaluate([self.action([correction(field, unsafe)])])
                self.assertEqual('blocked', adverse[key]['result'])
                self.assertEqual('rejected', score['status'])
                unknown = correction(field, None)
                unknown['state'] = 'unknown'
                uncertain, _ = self.evaluate([self.action([unknown])])
                self.assertEqual('review', uncertain[key]['result'])
                self.assertNotEqual('Probable Match', uncertain['recommendation'])

    def test_condition_and_category_are_independent(self):
        self.candidate['condition'] = 'Used'
        static, score = self.evaluate([self.action()])
        self.assertEqual('pass', static['platform_rule']['result'])
        self.assertEqual('blocked', static['condition_mismatch']['result'])
        self.assertEqual('rejected', score['status'])


if __name__ == '__main__':
    unittest.main()
