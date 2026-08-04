"""Cache read-only Amazon Catalog Items identity evidence for sourcing."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

from amazon_spapi_client import AmazonSPAPIClient
from sourcing_common import get_supabase_client, paginate_table
from system_detection import detect_system_from_title, normalize_system


INCLUDED_DATA = [
    "attributes",
    "summaries",
    "relationships",
    "productTypes",
    "classifications",
    "images",
    "identifiers",
]

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    args = parse_args()
    supabase = get_supabase_client()
    asins = selected_asins(supabase, args.asin, args.current_opportunities, args.limit)
    client = AmazonSPAPIClient.from_env()
    rows = []
    key_inventory: dict[str, set[str]] = {}
    for asin in asins:
        payload = client.get_catalog_item(asin, included_data=INCLUDED_DATA)
        normalized = normalize_catalog_item(asin, payload, client.config.marketplace_id)
        rows.append(normalized)
        collect_keys(payload, key_inventory)
    artifact = write_artifact(rows, key_inventory, args.write)
    print("Amazon Catalog Items identity sync")
    print("----------------------------------")
    print(f"Mode: {'write' if args.write else 'dry-run'}")
    print(f"ASINs fetched: {len(rows)}")
    print(f"Artifact: {artifact}")
    if args.write and rows:
        for row in rows:
            supabase.table("amazon_catalog_item_identity_snapshots").upsert(row, on_conflict="asin").execute()
        print(f"Rows written: {len(rows)}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cache Amazon Catalog Items identity evidence.")
    parser.add_argument("--asin", action="append", default=[], help="ASIN to fetch; may be repeated.")
    parser.add_argument("--current-opportunities", action="store_true", help="Fetch ASINs from current open sourcing opportunities.")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args()


def selected_asins(supabase, explicit_asins: list[str], current_opportunities: bool, limit: int) -> list[str]:
    asins = [clean_asin(asin) for asin in explicit_asins if clean_asin(asin)]
    if current_opportunities:
        rows = paginate_table(
            supabase,
            "sourcing_opportunities",
            "asin",
            max_rows=limit,
            order_column="created_at",
            desc=True,
        )
        for row in rows:
            asin = clean_asin(row.get("asin"))
            if asin and asin not in asins:
                asins.append(asin)
            if len(asins) >= limit:
                break
    return asins[:limit]


def normalize_catalog_item(asin: str, payload: dict[str, Any], marketplace_id: str) -> dict[str, Any]:
    attributes = payload.get("attributes") if isinstance(payload.get("attributes"), dict) else {}
    summaries = payload.get("summaries") if isinstance(payload.get("summaries"), list) else []
    relationships = payload.get("relationships") if isinstance(payload.get("relationships"), list) else []
    product_types = payload.get("productTypes") if isinstance(payload.get("productTypes"), list) else []
    title = first_attribute(attributes, "item_name", "title") or first_summary_value(summaries, "itemName")
    platform = first_attribute(attributes, "platform", "hardware_platform", "part_number")
    edition = first_attribute(attributes, "edition", "version_for_country", "style")
    release_date = first_attribute(attributes, "release_date", "publication_date")
    region = first_attribute(attributes, "region_code", "country_of_origin")
    item_format = first_attribute(attributes, "format", "binding")
    package_quantity = integer_value(first_attribute(attributes, "item_package_quantity", "number_of_items"))
    return {
        "asin": asin,
        "marketplace_id": marketplace_id,
        "product_type": first_product_type(product_types),
        "normalized_platform": normalize_system(str(platform or "")) or detect_system_from_title(str(title or "")),
        "normalized_edition": text_or_none(edition),
        "normalized_release_date": date_or_none(release_date),
        "normalized_release_year": release_year(release_date),
        "normalized_region": text_or_none(region),
        "normalized_format": text_or_none(item_format),
        "package_quantity": package_quantity,
        "variation_parent_asins": variation_asins(relationships, "PARENT"),
        "variation_child_asins": variation_asins(relationships, "CHILD"),
        "variation_theme": variation_theme(relationships),
        "relevant_attributes_json": {
            "title": title,
            "platform": platform,
            "edition": edition,
            "release_date": release_date,
            "region": region,
            "format": item_format,
            "package_quantity": package_quantity,
            "observed_attribute_keys": sorted(attributes.keys()),
        },
        "raw_catalog_json": payload,
        "source_version": "spapi_catalog_items_2022_04_01",
        "fetched_at": dt.datetime.now(dt.UTC).isoformat(),
        "updated_at": dt.datetime.now(dt.UTC).isoformat(),
    }


def first_attribute(attributes: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = attributes.get(name)
        if isinstance(value, list) and value:
            first = value[0]
            if isinstance(first, dict):
                for key in ("value", "displayValue", "name"):
                    if first.get(key):
                        return first.get(key)
            return first
        if value:
            return value
    return None


def first_summary_value(summaries: list[Any], key: str) -> Any:
    for summary in summaries:
        if isinstance(summary, dict) and summary.get(key):
            return summary.get(key)
    return None


def first_product_type(product_types: list[Any]) -> str | None:
    for row in product_types:
        if isinstance(row, dict):
            text = text_or_none(row.get("productType") or row.get("name"))
            if text:
                return text
    return None


def variation_asins(relationships: list[Any], relation_type: str) -> list[str]:
    found: list[str] = []
    for relationship in relationships:
        if not isinstance(relationship, dict):
            continue
        for row in relationship.get("relationships") or []:
            if not isinstance(row, dict):
                continue
            if str(row.get("type") or "").upper() != relation_type:
                continue
            asin_values = row.get("asin") if isinstance(row.get("asin"), list) else [row.get("asin")]
            for asin in asin_values:
                cleaned = clean_asin(asin)
                if cleaned and cleaned not in found:
                    found.append(cleaned)
    return found


def variation_theme(relationships: list[Any]) -> Any:
    themes = []
    for relationship in relationships:
        if isinstance(relationship, dict) and relationship.get("variationTheme"):
            themes.append(relationship.get("variationTheme"))
    return themes or None


def collect_keys(value: Any, output: dict[str, set[str]], prefix: str = "") -> None:
    if isinstance(value, dict):
        output.setdefault(prefix or "$", set()).update(value.keys())
        for key, item in value.items():
            collect_keys(item, output, f"{prefix}.{key}" if prefix else key)
    elif isinstance(value, list):
        for item in value[:3]:
            collect_keys(item, output, f"{prefix}[]")


def write_artifact(rows: list[dict[str, Any]], key_inventory: dict[str, set[str]], write: bool) -> Path:
    timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d%H%M%S")
    path = ROOT / "tmp" / f"amazon_catalog_items_identity_{'write' if write else 'dry_run'}_{timestamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "rows": [{key: value for key, value in row.items() if key != "raw_catalog_json"} for row in rows],
                "observed_keys": {key: sorted(values) for key, values in key_inventory.items()},
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    return path


def clean_asin(value: Any) -> str:
    return str(value or "").strip().upper()


def text_or_none(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def integer_value(value: Any) -> int | None:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def date_or_none(value: Any) -> str | None:
    text = text_or_none(value)
    if not text:
        return None
    return text[:10] if len(text) >= 10 else None


def release_year(value: Any) -> int | None:
    text = text_or_none(value)
    if not text:
        return None
    for part in text.replace("/", "-").split("-"):
        if len(part) == 4 and part.isdigit():
            return int(part)
    return None


if __name__ == "__main__":
    raise SystemExit(main())
