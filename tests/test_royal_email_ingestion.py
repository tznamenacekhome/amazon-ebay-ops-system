from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "integrations"))

from royal_email_ingestion import IntakeError, allowed_host, body_links, validate_source
from wholesale_royal import filename_effective_date, parse_price_list


class RoyalEmailSafetyTests(unittest.TestCase):
    def test_download_domain_requires_exact_host_or_subdomain(self):
        allowed = {"portal.royalelec.com"}
        self.assertTrue(allowed_host("portal.royalelec.com", allowed))
        self.assertTrue(allowed_host("files.portal.royalelec.com", allowed))
        self.assertFalse(allowed_host("portal.royalelec.com.evil.test", allowed))

    def test_body_links_are_extracted_without_logging_or_storage(self):
        links = body_links({"content": '<a href="https://portal.royalelec.com/d?id=secret">Download</a>'})
        self.assertEqual(links, ["https://portal.royalelec.com/d?id=secret"])

    def test_binary_csv_is_rejected(self):
        with self.assertRaises(IntakeError):
            validate_source("Royal.csv", b"ORDER,TITLE\x00bad")

    def test_filename_date_is_conservative(self):
        self.assertEqual(str(filename_effective_date("Royal Price List 2026-10-03.csv")), "2026-10-03")
        self.assertIsNone(filename_effective_date("unrelated-2026-10-03.csv"))

    def test_csv_uses_existing_royal_normalization(self):
        content = "ORDER,TITLE,SYS,UPC / SKU,PRICE,QTY,SUB\n1,Example Game,Switch,012345678905,19.99,5,\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Royal Price List 2026-10-03.csv"
            path.write_text(content, encoding="utf-8")
            parsed = parse_price_list(path)
        self.assertEqual(parsed["status"], "completed")
        self.assertEqual(parsed["date_source"], "supplier_filename")
        self.assertEqual(parsed["products"][0]["normalized_identifier"], "012345678905")
        self.assertEqual(parsed["products"][0]["supplier_price"], "19.99")


if __name__ == "__main__":
    unittest.main()
