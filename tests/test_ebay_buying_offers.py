import sys
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integrations"))
from sync_ebay_buying_offers import declined_evidence, unresolved_evidence, fetch_offers, parse_page, request_body


def xml(status="Declined", amount="60.00", currency="USD", pages=1, ack="Success"):
    return f'''<GetMyeBayBuyingResponse xmlns="urn:ebay:apis:eBLBaseComponents">
<Ack>{ack}</Ack><BestOfferList><PaginationResult><TotalNumberOfPages>{pages}</TotalNumberOfPages></PaginationResult>
<ItemArray><Item><ItemID>123456789012</ItemID><BestOfferDetails><BestOffer currencyID="{currency}">{amount}</BestOffer>
<BestOfferStatus>{status}</BestOfferStatus></BestOfferDetails></Item></ItemArray></BestOfferList></GetMyeBayBuyingResponse>'''


class BuyingOfferTests(unittest.TestCase):
    def test_on_demand_checks_history_before_progressive_run(self):
        import run_sourcing_workflow as workflow
        from types import SimpleNamespace
        args = SimpleNamespace(single_pass=False, run_id="run")
        calls = []
        with patch.object(workflow, "parse_args", return_value=args), \
             patch.object(workflow, "run_python", side_effect=lambda step: calls.append(step)), \
             patch.object(workflow, "run_progressive", side_effect=lambda value: calls.append("score") or 0):
            self.assertEqual(workflow.main(), 0)
        self.assertEqual(calls, [["integrations/sync_ebay_buying_offers.py", "--apply"], "score"])

    def test_failed_history_check_does_not_run_sourcing(self):
        import run_sourcing_workflow as workflow
        from types import SimpleNamespace
        for single in [False, True]:
            with patch.object(workflow, "parse_args", return_value=SimpleNamespace(single_pass=single, run_id="run")), \
                 patch.object(workflow, "run_python", side_effect=RuntimeError("eBay unavailable")), \
                 patch.object(workflow, "mark_run_failed") as failed, \
                 patch.object(workflow, "run_progressive") as score:
                with self.assertRaisesRegex(RuntimeError, "eBay unavailable"):
                    workflow.main()
                score.assert_not_called()
                failed.assert_called_once()

    def test_live_status_omitted_offer_is_retained_without_inventing_decline(self):
        for item, amount in [("137887648197", "17.0"), ("403002608732", "19.0")]:
            response = xml(amount=amount).replace("123456789012", item).replace("<BestOfferStatus>Declined</BestOfferStatus>", "")
            rows, _ = parse_page(response)
            self.assertEqual(declined_evidence(rows), [])
            self.assertEqual(unresolved_evidence(rows), [{"ebay_legacy_item_id": item, "offer_amount": amount}])

    def test_unresolved_requires_valid_usd_nonvariation_offer_and_missing_status(self):
        for response in [xml(status="Pending"), xml(status="Accepted"), xml(status="Declined"),
                         xml(status="", currency="GBP"), xml(status="", amount="NaN"), xml(status="", amount="0")]:
            self.assertEqual(unresolved_evidence(parse_page(response)[0]), [])
        rows, _ = parse_page(xml(status=""))
        rows[0]["variation"] = True
        self.assertEqual(unresolved_evidence(rows), [])

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
