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
    def test_scoring_keeps_stream_and_bounds_raw_candidate_memory(self):
        from score_sourcing_opportunities import score_candidate_batches
        candidates = ({"seed_id": "seed", "candidate_id": n} for n in range(205))
        batch_sizes = []
        def lookup(db, rows):
            batch_sizes.append(len(rows))
            return {"123": 60}
        def score(candidate, seed, settings, keepa, history, context, **kwargs):
            self.assertEqual(context["declined_offers"], {"123": 60})
            return candidate["candidate_id"]
        with patch("score_sourcing_opportunities.fetch_declines", side_effect=lookup), patch("score_sourcing_opportunities.score_candidate", side_effect=score):
            result = list(score_candidate_batches(None, candidates, {"seed": {}}, None, {}, {}, {}, {}))
        self.assertEqual(result, list(range(205)))
        self.assertEqual(batch_sizes, [100, 100, 5])

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
