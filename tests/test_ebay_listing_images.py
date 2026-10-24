import unittest
import xml.etree.ElementTree as ET
from unittest.mock import Mock, patch

from integrations import ebay_listing_images as images
from integrations import ebay_sync_buyer_purchases as sync


class ListingImageTests(unittest.TestCase):
    def setUp(self):
        sync.ITEM_PICTURE_CACHE.clear()

    def test_original_item_identity_is_required(self):
        response = Mock(content=b'<GetItemResponse xmlns="urn:ebay:apis:eBLBaseComponents"><Ack>Success</Ack><Item><ItemID>999999999999</ItemID><PictureDetails><PictureURL>https://i.ebayimg.com/cover.jpg</PictureURL></PictureDetails></Item></GetItemResponse>')
        with patch.object(images.requests, "post", return_value=response):
            self.assertEqual(images.listing_picture_urls("token", "123456789012"), [])

    def test_only_picture_details_are_saved(self):
        response = Mock(content=b'<GetItemResponse xmlns="urn:ebay:apis:eBLBaseComponents"><Ack>Success</Ack><Item><ItemID>123456789012</ItemID><PictureDetails><PictureURL>https://i.ebayimg.com/cover.jpg</PictureURL><PictureURL>http://unsafe.example/picture</PictureURL></PictureDetails></Item></GetItemResponse>')
        with patch.object(images.requests, "post", return_value=response):
            self.assertEqual(images.listing_picture_urls("token", "123456789012"), ["https://i.ebayimg.com/cover.jpg"])

    def test_resync_keeps_saved_photos_without_provider_call(self):
        transaction = ET.fromstring('<Transaction><Item><ItemID>123456789012</ItemID><Title>Game</Title></Item></Transaction>')
        existing = {"raw_import_json": images.attach_listing_images({"old": True}, "123456789012", ["https://i.ebayimg.com/cover.jpg"])}
        with patch.object(sync, "listing_picture_urls") as fetch:
            raw = sync.transaction_with_listing_images(transaction, "token", existing)
        fetch.assert_not_called()
        self.assertEqual(raw[images.IMAGE_METADATA_KEY]["PictureURL"], ["https://i.ebayimg.com/cover.jpg"])
        self.assertIn("Transaction", raw)

    def test_provider_failure_does_not_break_ingestion(self):
        transaction = ET.fromstring('<Transaction><Item><ItemID>123456789012</ItemID></Item></Transaction>')
        with patch.object(sync, "listing_picture_urls", side_effect=images.requests.Timeout):
            self.assertIn("Transaction", sync.transaction_with_listing_images(transaction, "token", None))

    def test_lookup_budget_and_cache(self):
        with patch.object(sync, "MAX_LISTING_IMAGE_LOOKUPS", 1), patch.object(sync, "listing_picture_urls", return_value=[]) as fetch:
            for item_id in ["123456789012", "123456789012", "123456789013"]:
                transaction = ET.fromstring(f'<Transaction><Item><ItemID>{item_id}</ItemID></Item></Transaction>')
                sync.transaction_with_listing_images(transaction, "token", None)
        self.assertEqual(fetch.call_count, 1)


if __name__ == "__main__":
    unittest.main()
