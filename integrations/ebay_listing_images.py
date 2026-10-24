"""Read original eBay listing photos, including recently ended listings."""
import re
import xml.etree.ElementTree as ET

import requests

IMAGE_METADATA_KEY = "mbop_listing_images"


def listing_picture_urls(access_token, item_id):
    if not re.fullmatch(r"\d{9,15}", str(item_id or "")):
        return []
    root = ET.Element("GetItemRequest", xmlns="urn:ebay:apis:eBLBaseComponents")
    ET.SubElement(root, "ItemID").text = str(item_id)
    ET.SubElement(root, "OutputSelector").text = "Item.ItemID"
    ET.SubElement(root, "OutputSelector").text = "Item.PictureDetails"
    response = requests.post(
        "https://api.ebay.com/ws/api.dll",
        headers={
            "Content-Type": "text/xml",
            "X-EBAY-API-CALL-NAME": "GetItem",
            "X-EBAY-API-COMPATIBILITY-LEVEL": "1423",
            "X-EBAY-API-SITEID": "0",
            "X-EBAY-API-IAF-TOKEN": access_token,
        },
        data=ET.tostring(root, encoding="utf-8", xml_declaration=True),
        timeout=30,
    )
    response.raise_for_status()
    result = ET.fromstring(response.content)
    ns = {"e": "urn:ebay:apis:eBLBaseComponents"}
    if result.findtext("e:Ack", namespaces=ns) not in {"Success", "Warning"}:
        return []
    if result.findtext("e:Item/e:ItemID", namespaces=ns) != str(item_id):
        return []
    urls = []
    for picture in result.findall("e:Item/e:PictureDetails/e:PictureURL", ns):
        url = (picture.text or "").strip()
        if url.startswith("https://") and url not in urls:
            urls.append(url)
    return urls[:12]


def image_metadata(raw):
    if not isinstance(raw, dict):
        return None
    metadata = raw.get(IMAGE_METADATA_KEY)
    return metadata if isinstance(metadata, dict) else None


def attach_listing_images(raw, item_id, urls):
    """Add small normalized metadata without replacing the eBay transaction."""
    result = dict(raw) if isinstance(raw, dict) else {}
    if urls:
        result[IMAGE_METADATA_KEY] = {
            "ItemID": str(item_id), "PictureURL": urls, "source": "ebay_trading_get_item",
        }
    return result
