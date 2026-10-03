import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integrations"))

from amazon_spapi_client import AmazonSPAPIClient  # noqa: E402
from wholesale_enrichment import (  # noqa: E402
    WholesaleEnrichmentService, effective_product_identity, explicit_non_na_region, process_work_batch,
)


class FakeRepository:
    def __init__(self, cached=None):
        self.cached = cached
        self.saved = []

    def fresh_search(self, *_args):
        return self.cached

    def save_search(self, row):
        self.saved.append(row)


class FakeAmazon:
    def __init__(self):
        self.calls = []

    def search_catalog_items(self, **kwargs):
        self.calls.append(kwargs)
        return {"items": [{"asin": "B000000001"}, {"asin": "B000000002"}]}


class WholesaleEnrichmentTests(unittest.TestCase):
    def test_search_cache_reuse_avoids_amazon_call(self):
        repository = FakeRepository({"candidate_asins": ["B000000001"]})
        amazon = FakeAmazon()
        service = WholesaleEnrichmentService(repository, amazon, seller_id="seller", marketplace_id="US")
        rows = service._search({"supplier_product_id": "p1"}, "identifier", "012345678905", identifiers=["012345678905"], identifiers_type="UPC")
        self.assertEqual(rows, [{"asin": "B000000001"}])
        self.assertEqual(amazon.calls, [])

    def test_uncached_search_persists_result_set(self):
        repository = FakeRepository()
        amazon = FakeAmazon()
        service = WholesaleEnrichmentService(repository, amazon, seller_id="seller", marketplace_id="US")
        rows = service._search({"supplier_product_id": "p1"}, "title_platform", "Game PS 5", keywords=["Game", "PS", "5"])
        self.assertEqual(len(rows), 2)
        self.assertEqual(repository.saved[0]["search_status"], "success")
        self.assertEqual(repository.saved[0]["candidate_asins"], ["B000000001", "B000000002"])

    def test_search_context_is_persisted_for_human_evidence(self):
        repository = FakeRepository()
        service = WholesaleEnrichmentService(repository, FakeAmazon(), seller_id="seller", marketplace_id="US")
        service._search({"supplier_product_id": "p1"}, "title_platform", "Game PS 5",
                        query_context={"title_terms": "Game", "platform_term": "PS 5"}, keywords=["Game", "PS", "5"])
        self.assertEqual(repository.saved[0]["query_context"], {"title_terms": "Game", "platform_term": "PS 5"})

    def test_enrich_source_always_invokes_both_discovery_branches(self):
        source = (Path(__file__).resolve().parents[1] / "integrations/wholesale_enrichment.py").read_text(encoding="utf-8")
        identifier_position = source.index('self._search(product, "identifier"')
        title_position = source.index('self._search(product, "title_platform"')
        merge_position = source.index("merge_candidates(identifier_items, title_items)")
        self.assertLess(identifier_position, title_position)
        self.assertLess(title_position, merge_position)

    def test_explicit_rematch_bypasses_fresh_search_cache(self):
        repository = FakeRepository({"candidate_asins": ["B000000009"], "search_status": "success"})
        amazon = FakeAmazon()
        service = WholesaleEnrichmentService(repository, amazon, seller_id="seller", marketplace_id="US")
        rows = service._search({"supplier_product_id": "p1"}, "identifier", "012345678905",
                               force_refresh=True, identifiers=["012345678905"], identifiers_type="UPC")
        self.assertEqual([row["asin"] for row in rows], ["B000000001", "B000000002"])
        self.assertEqual(len(amazon.calls), 1)

    def test_latest_observation_drives_identity_but_price_is_ignored(self):
        row = effective_product_identity({"raw_title": "Old", "raw_system": "SW", "latest_observation": {
            "raw_title": "New", "raw_system": "PS5", "supplier_price": "99.00"
        }})
        self.assertEqual((row["raw_title"], row["raw_system"]), ("New", "PS5"))
        self.assertNotIn("supplier_price", row)

    def test_non_na_classification_requires_explicit_low_ambiguity_marker(self):
        self.assertEqual(explicit_non_na_region("Game EU Version"), "eu")
        self.assertEqual(explicit_non_na_region("Jeu French Language"), "fr")
        self.assertIsNone(explicit_non_na_region("It Takes Two"))
        self.assertIsNone(explicit_non_na_region("Friday the 13th"))

    def test_catalog_identifier_and_keyword_requests_use_same_client_method(self):
        client = AmazonSPAPIClient.__new__(AmazonSPAPIClient)
        client.config = SimpleNamespace(marketplace_id="US")
        calls = []
        client.request = lambda method, path, params=None: calls.append((method, path, params)) or {}
        client.search_catalog_items(identifiers=["012345678905"], identifiers_type="UPC")
        client.search_catalog_items(keywords=["Game", "PS5"])
        self.assertEqual(calls[0][2]["identifiersType"], "UPC")
        self.assertEqual(calls[1][2]["keywords"], "Game PS5")
        self.assertTrue(all(call[1] == "/catalog/2022-04-01/items" for call in calls))

    def test_catalog_search_rejects_ambiguous_mode(self):
        client = AmazonSPAPIClient.__new__(AmazonSPAPIClient)
        client.config = SimpleNamespace(marketplace_id="US")
        with self.assertRaises(ValueError):
            client.search_catalog_items(identifiers=["012345678905"], identifiers_type="UPC", keywords=["Game"])

    def test_bounded_work_batch_is_resumable_after_item_failure(self):
        class WorkRepository:
            def __init__(self):
                self.updates = []
            def update_work(self, work_item_id, values):
                self.updates.append((work_item_id, values["work_status"]))
        class Service:
            def enrich_product(self, product_id):
                if product_id == "bad":
                    raise RuntimeError("temporary provider error")
                return {"status": "matched"}
        repository = WorkRepository()
        counters = process_work_batch(repository, Service(), [
            {"work_item_id": "w1", "supplier_product_id": "bad", "attempt_count": 0},
            {"work_item_id": "w2", "supplier_product_id": "good", "attempt_count": 1},
        ])
        self.assertEqual(counters, {"processed": 2, "matched": 1, "review": 0, "errors": 1})
        self.assertIn(("w1", "retry"), repository.updates)
        self.assertIn(("w2", "completed"), repository.updates)


if __name__ == "__main__":
    unittest.main()
