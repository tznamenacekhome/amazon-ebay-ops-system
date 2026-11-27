"""Text-only wrapping controls; no marketplace requests or photographs."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations'))
from sourcing_match_rules import condition_review_hits, used_condition_hits


class WrappingConditionTests(unittest.TestCase):
    def test_minor_disclosures_require_review(self):
        for text in ('Small tear in shrink wrap.', 'Tears in shrink-wrap.',
                     'Has some tears in the cello wrap', 'Tears in cellophane.',
                     'Has a few holes in seal as shown.', 'Punctures in shrink wrap.',
                     'Shrink wrap has small tears.', 'Punctured cellophane wrap.',
                     'This copy may have holes in seal.',
                     'Holes in seal are not factory vents.'):
            with self.subTest(text=text):
                self.assertTrue(condition_review_hits('', text))
                self.assertFalse(used_condition_hits('', text))

    def test_neutral_scope_and_negation(self):
        for text in ('No tears in shrink wrap.', 'Without holes in seal.',
                     'Free from tears in cellophane.', 'No tears or holes in seal.',
                     'Shrink wrap has no tears.', 'If tears in shrink wrap occur, report them.',
                     'Some items may have holes in seal.',
                     'Other items have tears in cello wrap.',
                     'The camera has tears in shrink wrap.',
                     'Holes in seal must be reported for returns.',
                     'Normal factory vent holes in shrink wrap.',
                     'Holes in seal are normal factory vents.',
                     'Tested.', 'Tested and working.', 'All tested and working.'):
            with self.subTest(text=text):
                self.assertFalse(condition_review_hits('', text))
                self.assertFalse(used_condition_hits('', text))

    def test_independent_hard_condition_guards(self):
        for text in ('The game was opened.', 'Previously played game.',
                     'Factory seal missing.', 'Factory seal is broken.',
                     'Visible cracks on case.', 'Seal is torn.'):
            with self.subTest(text=text):
                self.assertTrue(used_condition_hits('', text))

    def test_factory_vents_do_not_hide_separate_damage(self):
        self.assertTrue(condition_review_hits('', 'Normal factory vent holes in shrink wrap. Small tear in cello wrap.'))

if __name__ == '__main__':
    unittest.main()
