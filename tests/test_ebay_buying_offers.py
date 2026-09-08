import sys
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integrations"))
from sync_ebay_buying_offers import declined_evidence, fetch_offers, parse_page, request_body


def xml(status="Declined", amount="60.00", currency="USD", pages=1, ack="Success"):
    return f'''<GetMyeBayBuyingResponse xmlns="urn:ebay:apis:eBLBaseComponents">
<Ack>{ack}</Ack><BestOfferList><PaginationResult><TotalNumberOfPages>{pages}</TotalNumberOfPages></PaginationResult>
<ItemArray><Item><ItemID>123456789012</ItemID><BestOfferDetails><BestOffer currencyID="{currency}">{amount}</BestOffer>
<BestOfferStatus>{status}</BestOfferStatus></BestOfferDetails></Item></ItemArray></BestOfferList></GetMyeBayBuyingResponse>'''


class BuyingOfferTests(unittest.TestCase):
    def test_explicit_declines_only(self):
        for status in ["Active", "Countered", "Expired", "Accepted", "Pending", "BuyerCounterOffer", "SellerCounterOffer", "Unknown"]:
            self.assertEqual(declined_evidence(parse_page(xml(status=status))[0]), [])
        self.assertEqual(declined_evidence(parse_page(xml())[0])[0]["declined_offer_amount"], "60.00")

    def test_highest_decline_and_invalid_amounts(self):
        rows = parse_page(xml(amount="60"))[0] + parse_page(xml(amount="55"))[0]
        self.assertEqual(declined_evidence(rows)[0]["declined_offer_amount"], "60")
        for amount in ["NaN", "Infinity", "-1", "0", "bad", "60.005"]:
            self.assertEqual(declined_evidence(parse_page(xml(amount=amount))[0]), [])

    def test_currency_and_variation_safety(self):
        self.assertEqual(declined_evidence(parse_page(xml(currency="GBP"))[0]), [])
        rows, _ = parse_page(xml())
        rows[0]["variation"] = True
        self.assertEqual(declined_evidence(rows), [])

    def test_failure_and_warning_are_not_success(self):
        for ack in ["Failure", "Warning"]:
            with self.assertRaises(RuntimeError):
                parse_page(xml(ack=ack))

    def test_pagination_and_bound(self):
        post = Mock(side_effect=[Mock(text=xml(pages=2)), Mock(text=xml(pages=2, amount="65"))])
        with patch("sync_ebay_buying_offers.time.sleep"):
            self.assertEqual(len(fetch_offers("test", post=post)), 2)
        self.assertIn(b"<PageNumber>2</PageNumber>", post.call_args.kwargs["data"])
        with self.assertRaises(RuntimeError):
            fetch_offers("test", max_pages=1, post=Mock(return_value=Mock(text=xml(pages=2))))

    def test_credential_envelope_and_empty_account(self):
        self.assertIn(b"a&amp;b", request_body("a&b", 1))
        self.assertEqual(parse_page('<GetMyeBayBuyingResponse xmlns="urn:ebay:apis:eBLBaseComponents"><Ack>Success</Ack></GetMyeBayBuyingResponse>'), ([], 0))


if __name__ == "__main__":
    unittest.main()
