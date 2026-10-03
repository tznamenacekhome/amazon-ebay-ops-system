from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "integrations"))

from amazon_spapi_client import AmazonSPAPIClient
from amazon_sync_catalog_items import INCLUDED_DATA, normalize_catalog_item
from sourcing_common import get_supabase_client
from wholesale_matching import evaluate_compatibility, search_items, title_platform_query, title_search_variants

MARKETPLACE = "ATVPDKIKX0DER"
TARGETS = [
    "Atomic Heart", "Batman: Arkham Knight", "Ben 10 Power Trip", "Borderlands: Game of The Year",
    "Call of Duty Black Ops 6", "Crash Team Racing", "Mario Kart", "Sonic", "Assassin",
]


def pages(query, size=500):
    rows = []
    for offset in range(0, 10000, size):
        batch = query.range(offset, offset + size - 1).execute().data or []
        rows.extend(batch)
        if len(batch) < size:
            return rows
    raise RuntimeError("bounded pagination limit reached")


def main(live: bool, limit: int):
    db = get_supabase_client()
    supplier = db.table("wholesale_suppliers").select("supplier_id,name").ilike("name", "%Royal%").limit(1).execute().data[0]
    latest = (db.table("wholesale_imports").select("import_id,effective_date,summary")
              .eq("supplier_id", supplier["supplier_id"]).eq("status", "completed")
              .order("effective_date", desc=True).order("revision", desc=True).limit(1).execute().data[0])
    observations = pages(db.table("wholesale_supplier_observations")
                         .select("supplier_product_id,raw_title,raw_system,raw_identifier,normalized_identifier,identifier_type")
                         .eq("import_id", latest["import_id"]).order("raw_title"))
    product_ids = {row["supplier_product_id"] for row in observations}
    states = pages(db.table("wholesale_match_states").select("supplier_product_id,match_status")
                   .eq("marketplace_id", MARKETPLACE))
    state_map = {row["supplier_product_id"]: row["match_status"] for row in states if row["supplier_product_id"] in product_ids}
    classifications = pages(db.table("wholesale_product_classifications")
                            .select("supplier_product_id,classification_code")
                            .eq("classification_status", "active"))
    classification_map = {row["supplier_product_id"]: row["classification_code"] for row in classifications
                          if row["supplier_product_id"] in product_ids}
    status = lambda product_id: classification_map.get(product_id) or state_map.get(product_id) or "missing_state"
    counts = Counter(status(row["supplier_product_id"]) for row in observations)
    unmatched = [row for row in observations if status(row["supplier_product_id"]) in {
        "missing_state", "no_candidates", "discovery_pending",
    }]

    sample = []
    seen = set()
    for needle in TARGETS:
        row = next((r for r in unmatched if needle.casefold() in r["raw_title"].casefold()), None)
        if row and row["supplier_product_id"] not in seen:
            sample.append(row); seen.add(row["supplier_product_id"])
    for system in ("PS5", "SW", "SW2", "XB1", "XBOX"):
        row = next((r for r in unmatched if r["raw_system"] == system and r["supplier_product_id"] not in seen), None)
        if row:
            sample.append(row); seen.add(row["supplier_product_id"])
    sample = sample[:limit]

    amazon = AmazonSPAPIClient.from_env() if live else None
    reports = []
    for row in sample:
        searches = (db.table("wholesale_catalog_searches")
                    .select("query_type,query_value,query_fingerprint,search_status,candidate_asins,query_context,searched_at,expires_at")
                    .eq("supplier_product_id", row["supplier_product_id"]).eq("marketplace_id", MARKETPLACE)
                    .order("searched_at", desc=True).execute().data or [])
        old = next((s for s in searches if s["query_type"] == "title_platform"), None)
        report = {
            "supplier_product_id": row["supplier_product_id"], "raw_title": row["raw_title"],
            "system": row["raw_system"], "identifier": row["normalized_identifier"],
            "old_query": title_platform_query(row["raw_title"], row["raw_system"]),
            "old_cache": old, "new_variants": title_search_variants(row["raw_title"], row["raw_system"]),
            "live": [],
        }
        if amazon:
            for variant in report["new_variants"]:
                payload = amazon.search_catalog_items(keywords=variant["query"].split(), included_data=INCLUDED_DATA, page_size=20)
                items = search_items(payload)
                results = []
                plausible = 0
                for item in items:
                    normalized = normalize_catalog_item(item["asin"], item, MARKETPLACE)
                    outcome = evaluate_compatibility(row, normalized, [variant["query_type"]])
                    plausible += int(outcome.status != "incompatible")
                    if outcome.status != "incompatible" and len(results) < 5:
                        results.append({"asin": item["asin"], "status": outcome.status,
                                        "reasons": list(outcome.reason_codes),
                                        "title": (normalized.get("relevant_attributes_json") or {}).get("title"),
                                        "platform": normalized.get("normalized_platform")})
                pagination = (payload.get("pagination") or (payload.get("payload") or {}).get("pagination") or {})
                report["live"].append({"variant": variant["name"], "query": variant["query"],
                                       "count": len(items), "plausible": plausible,
                                       "has_next_page": bool(pagination.get("nextToken")), "results": results})
                time.sleep(0.55)
                if plausible:
                    break
        reports.append(report)
    output = {"supplier": supplier, "latest_import": latest, "accepted": len(observations),
              "match_state_counts": dict(sorted(counts.items())), "unmatched": len(unmatched), "sample": reports}
    print(json.dumps(output, indent=2, default=str))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Inspect bounded wholesale Amazon title-match recall")
    parser.add_argument("--live", action="store_true", help="Run bounded read-only Amazon Catalog searches")
    parser.add_argument("--limit", type=int, default=12, choices=range(1, 26))
    arguments = parser.parse_args()
    main(arguments.live, arguments.limit)
