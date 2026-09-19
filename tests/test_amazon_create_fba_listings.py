import sys
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integrations"))

from amazon_create_fba_listings import (
    build_fba_conversion_patches,
    build_plan,
    submission_accepted,
)
from amazon_spapi_client import AmazonSPAPIClient, AmazonSPAPIConfig, AmazonSPAPIError


def config() -> AmazonSPAPIConfig:
    return AmazonSPAPIConfig(
        client_id="client",
        client_secret="secret",
        refresh_token="refresh",
        marketplace_id="ATVPDKIKX0DER",
        endpoint="https://sellingpartnerapi-na.amazon.com",
        aws_region="us-east-1",
        seller_id="seller",
    )


class AmazonFbaListingTests(unittest.TestCase):
    def test_plan_creates_fba_offer_without_merchant_quantity(self) -> None:
        plan = build_plan(
            asin="B07RZ67CVL",
            title="Mortal Kombat 11 - Nintendo Switch",
            price=Decimal("39.99"),
            units=11,
            marketplace_id="ATVPDKIKX0DER",
        )

        self.assertEqual(plan["seller_sku"], "MBOP-B07RZ67CVL-NEW")
        self.assertEqual(
            plan["attributes"]["fulfillment_availability"],
            [{"fulfillment_channel_code": "AMAZON_NA"}],
        )
        self.assertNotIn("quantity", plan["attributes"]["fulfillment_availability"][0])
        self.assertEqual(plan["attributes"]["merchant_suggested_asin"][0]["value"], "B07RZ67CVL")
        self.assertFalse(plan["attributes"]["batteries_required"][0]["value"])
        self.assertEqual(
            plan["attributes"]["supplier_declared_dg_hz_regulation"][0]["value"],
            "not_applicable",
        )

    def test_listing_writes_require_explicit_client_gate(self) -> None:
        path = "/listings/2021-08-01/items/seller/MBOP-B07RZ67CVL-NEW"
        with self.assertRaises(AmazonSPAPIError):
            AmazonSPAPIClient(config()).validate_read_only_request("PUT", path)

        write_client = AmazonSPAPIClient(config(), allow_listing_writes=True)
        write_client.validate_read_only_request("PUT", path)
        write_client.validate_read_only_request("PATCH", path)
        with self.assertRaises(AmazonSPAPIError):
            write_client.validate_read_only_request("DELETE", path)

    def test_inventory_sku_filter_is_comma_delimited(self) -> None:
        client = AmazonSPAPIClient(config())
        with patch.object(client, "request", return_value={}) as request:
            client.get_inventory_summaries(seller_skus=["SKU-1", "SKU-2"])

        self.assertEqual(request.call_args.kwargs["params"]["sellerSkus"], "SKU-1,SKU-2")

    def test_only_accepted_submissions_pass(self) -> None:
        self.assertTrue(submission_accepted({"status": "VALID"}))
        self.assertTrue(submission_accepted({"status": "ACCEPTED"}))
        self.assertFalse(submission_accepted({"status": "INVALID"}))
        self.assertFalse(submission_accepted(None))

    def test_conversion_patch_explicitly_removes_fbm(self) -> None:
        catalog = {
            "batteries_required": [{"value": False}],
            "item_package_dimensions": [{"height": {"value": 1, "unit": "inches"}}],
            "item_package_weight": [{"value": 1, "unit": "ounces"}],
        }
        patches = build_fba_conversion_patches(catalog)

        self.assertEqual(patches[0]["value"], [{"fulfillment_channel_code": "AMAZON_NA"}])
        self.assertEqual(patches[1]["value"], [{"fulfillment_channel_code": "DEFAULT"}])
        self.assertEqual(patches[1]["op"], "delete")


if __name__ == "__main__":
    unittest.main()
