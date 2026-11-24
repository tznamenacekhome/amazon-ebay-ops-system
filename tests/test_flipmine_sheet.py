import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations'))
from flipmine_sheet import parse_tab, tab_fingerprint


class FlipmineSheetTests(unittest.TestCase):
    def test_headers_not_positions_and_source_is_unconfirmed(self):
        rows = parse_tab([['eBay Price', 'ASIN', 'eBay Item ID', 'Amazon Title', 'eBay Title'],
                          ['$19.99', 'b000000001', 137956960282, 'Untrusted Deluxe', 'Untrusted eBay']])
        self.assertEqual(rows[0]['asin'], 'B000000001')
        self.assertEqual(rows[0]['ebay_legacy_item_id'], '137956960282')
        self.assertEqual(rows[0]['status'], 'pending')
        self.assertNotIn('confirmed', rows[0])
        self.assertEqual(rows[0]['source_evidence']['amazon title'], 'Untrusted Deluxe')

    def test_blank_rows_ignored_invalid_rows_retained(self):
        rows = parse_tab([['ASIN', 'eBay Item ID'], ['', ' '], ['B000000001', ''],
                          ['', '137956960282'], ['bad', 'wrong'], ['B000000001', '137956960282']])
        self.assertEqual([r['status'] for r in rows], ['invalid', 'invalid', 'invalid', 'pending'])
        self.assertEqual(rows[-1]['row_number'], 6)

    def test_missing_or_ambiguous_headers_fail(self):
        for header in ([], [['Amazon Title']], [['ASIN', 'ASIN', 'eBay Item ID']]):
            with self.assertRaises(ValueError): parse_tab(header)

    def test_competing_asins_remain_separate_and_snapshot_stable(self):
        values = [['ASIN', 'eBay Item ID'], ['B000000001', '137956960282'], ['B000000002', '137956960282']]
        self.assertEqual(len(parse_tab(values)), 2)
        self.assertEqual(tab_fingerprint(values), tab_fingerprint(values))


if __name__ == '__main__': unittest.main()
