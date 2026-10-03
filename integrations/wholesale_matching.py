"""Conservative Amazon matching policy for wholesale supplier products.

The functions in this module are deterministic and side-effect free. Network and
database orchestration lives in ``wholesale_enrichment.py`` so matching decisions
remain easy to test and audit.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Iterable


EVALUATOR_VERSION = "wholesale-v1"
ROYAL_PLATFORM_CODES = {
    "SW": "Switch",
    "SW2": "Switch 2",
    "PS5": "PS 5",
    "P4": "PS 4",
    "PS3": "PS 3",
    "XB1": "Xbox One",
    "XBOX": "Xbox Series X",
    "ACCSW": "Switch",
    "ACCSW2": "Switch 2",
    "ACCPS5": "PS 5",
}
ACCESSORY_WORDS = {
    "accessory", "adapter", "case", "charger", "controller", "dock", "headset",
    "accessories", "protector", "stand", "wheel", "cable", "grip", "skin", "cover",
}
EDITION_WORDS = {"collector", "collectors", "deluxe", "gold", "limited", "ultimate"}
BUNDLE_WORDS = {"bundle", "pack", "set", "collection"}
DIGITAL_WORDS = {"digital", "download", "code", "voucher"}
REGION_MARKERS = {
    "us": {"us", "usa", "ntsc-u"},
    "eu": {"eu", "europe", "pal"},
    "jp": {"jp", "japan", "japanese", "ntsc-j"},
    "uk": {"uk", "british"},
    "fr": {"fr", "french"},
    "it": {"it", "italian"},
    "mde": {"mde"},
}
STOP_WORDS = {
    "a", "an", "and", "edition", "for", "game", "nintendo", "of", "playstation",
    "sony", "the", "video", "xbox", "series", "switch", "ps3", "ps4", "ps5",
}


@dataclass(frozen=True)
class CompatibilityResult:
    status: str
    reason_codes: tuple[str, ...]
    details: dict[str, Any]


@dataclass(frozen=True)
class SelectionResult:
    status: str
    selected_asin: str | None
    selection_source: str
    rationale: dict[str, Any]


def identifier_search(normalized_identifier: Any, identifier_type: Any = None) -> tuple[str, str] | None:
    value = re.sub(r"\D", "", str(normalized_identifier or ""))
    supplied_type = str(identifier_type or "").strip().upper()
    if supplied_type in {"UPC", "EAN", "GTIN"} and value:
        return value, "UPC" if supplied_type == "UPC" else "EAN"
    if len(value) == 12:
        return value, "UPC"
    if len(value) == 13:
        return value, "EAN"
    return None


def canonical_platform(raw_system: Any) -> str | None:
    code = re.sub(r"[^A-Z0-9]", "", str(raw_system or "").upper())
    if code in ROYAL_PLATFORM_CODES:
        return ROYAL_PLATFORM_CODES[code]
    text = normalize_text(raw_system)
    aliases = {
        "nintendo switch 2": "Switch 2", "switch 2": "Switch 2",
        "nintendo switch": "Switch", "switch": "Switch",
        "playstation 5": "PS 5", "ps 5": "PS 5", "ps5": "PS 5",
        "playstation 4": "PS 4", "ps 4": "PS 4", "ps4": "PS 4",
        "playstation 3": "PS 3", "ps 3": "PS 3", "ps3": "PS 3",
        "xbox one": "Xbox One", "xbox series x": "Xbox Series X",
    }
    return aliases.get(text)


def title_platform_query(title: Any, raw_system: Any) -> str:
    clean_title = " ".join(str(title or "").split())
    platform = canonical_platform(raw_system)
    if not clean_title:
        raise ValueError("supplier title is required")
    return f"{clean_title} {platform}" if platform else clean_title


def query_fingerprint(query_type: str, query_value: str, marketplace_id: str) -> str:
    payload = json.dumps(
        [query_type.strip().lower(), normalize_text(query_value), marketplace_id.strip()],
        separators=(",", ":"), ensure_ascii=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def search_items(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    container = (payload or {}).get("payload") if isinstance((payload or {}).get("payload"), dict) else payload or {}
    return [row for row in container.get("items") or [] if isinstance(row, dict) and clean_asin(row.get("asin"))]


def merge_candidates(identifier_items: Iterable[dict[str, Any]], title_items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for source, rows in (("identifier", identifier_items), ("title_platform", title_items)):
        for row in rows:
            asin = clean_asin(row.get("asin"))
            if not asin:
                continue
            item = merged.setdefault(asin, {"asin": asin, "match_sources": [], "catalog_item": row})
            if source not in item["match_sources"]:
                item["match_sources"].append(source)
            if source == "identifier" or not item.get("catalog_item"):
                item["catalog_item"] = row
    return [merged[asin] for asin in sorted(merged)]


def evaluate_compatibility(product: dict[str, Any], catalog: dict[str, Any]) -> CompatibilityResult:
    supplier_title = str(product.get("raw_title") or "")
    supplier_system = str(product.get("raw_system") or "")
    attrs = catalog.get("relevant_attributes_json") if isinstance(catalog.get("relevant_attributes_json"), dict) else {}
    candidate_title = str(attrs.get("title") or catalog.get("title") or "")
    supplier_platform = canonical_platform(supplier_system)
    candidate_platform = canonical_platform(catalog.get("normalized_platform") or attrs.get("platform") or candidate_title)
    reasons: list[str] = []
    details = {"supplier_platform": supplier_platform, "candidate_platform": candidate_platform}

    if supplier_platform and candidate_platform and supplier_platform != candidate_platform:
        return result("incompatible", ["platform_mismatch"], details)
    if supplier_platform and not candidate_platform:
        reasons.append("candidate_platform_missing")

    supplier_accessory = supplier_system.upper().startswith("ACC") or has_any(supplier_title, ACCESSORY_WORDS)
    candidate_accessory = is_catalog_accessory(catalog, candidate_title)
    details.update({"supplier_accessory": supplier_accessory, "candidate_accessory": candidate_accessory})
    if supplier_accessory != candidate_accessory:
        return result("incompatible", ["accessory_type_mismatch"], details)

    supplier_format = commercial_format(supplier_title)
    candidate_format = commercial_format(" ".join([candidate_title, str(catalog.get("normalized_format") or "")]))
    details.update({"supplier_format": supplier_format, "candidate_format": candidate_format})
    if supplier_format != candidate_format and (supplier_format != "physical" or candidate_format != "physical"):
        return result("incompatible", ["digital_physical_mismatch"], details)

    supplier_edition = marker_set(supplier_title, EDITION_WORDS)
    candidate_edition = marker_set(" ".join([candidate_title, str(catalog.get("normalized_edition") or "")]), EDITION_WORDS)
    if supplier_edition != candidate_edition and (supplier_edition or candidate_edition):
        return result("incompatible", ["edition_mismatch"], {**details, "supplier_edition": sorted(supplier_edition), "candidate_edition": sorted(candidate_edition)})

    supplier_bundle = marker_set(supplier_title, BUNDLE_WORDS)
    candidate_bundle = marker_set(candidate_title, BUNDLE_WORDS)
    if supplier_bundle != candidate_bundle and (supplier_bundle or candidate_bundle):
        return result("incompatible", ["bundle_mismatch"], details)

    supplier_region = region(supplier_title)
    candidate_region = region(" ".join([candidate_title, str(catalog.get("normalized_region") or "")]))
    if supplier_region and candidate_region and supplier_region != candidate_region:
        return result("incompatible", ["region_mismatch"], {**details, "supplier_region": supplier_region, "candidate_region": candidate_region})
    if bool(supplier_region) != bool(candidate_region):
        reasons.append("region_evidence_incomplete")

    similarity = token_similarity(supplier_title, candidate_title)
    details["title_token_similarity"] = round(similarity, 4)
    if similarity < 0.30:
        return result("incompatible", [*reasons, "title_mismatch"], details)
    if reasons or similarity < 0.60:
        return result("uncertain", [*reasons, "insufficient_identity_evidence"], details)
    return result("compatible", ["platform_and_title_compatible"], details)


def identity_signature(product: dict[str, Any]) -> str:
    payload = {
        "title": normalize_text(product.get("raw_title")),
        "platform": canonical_platform(product.get("raw_system")),
        "accessory": str(product.get("raw_system") or "").upper().startswith("ACC") or has_any(product.get("raw_title"), ACCESSORY_WORDS),
        "edition": sorted(marker_set(product.get("raw_title"), EDITION_WORDS)),
        "bundle": sorted(marker_set(product.get("raw_title"), BUNDLE_WORDS)),
        "format": commercial_format(product.get("raw_title")),
        "region": region(product.get("raw_title")),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def select_preferred(candidates: Iterable[dict[str, Any]], manual_asin: str | None = None) -> SelectionResult:
    rows = list(candidates)
    usable = [row for row in rows if row.get("compatibility_status") == "compatible"]
    if manual_asin:
        manual = next((row for row in usable if clean_asin(row.get("asin")) == clean_asin(manual_asin)), None)
        if manual and fresh_eligible(manual):
            return SelectionResult("matched", clean_asin(manual_asin), "manual", {"reason": "valid_manual_override"})

    eligible = [row for row in usable if fresh_eligible(row)]
    eligible.sort(key=ranking_key)
    if eligible:
        selected = eligible[0]
        return SelectionResult("matched", clean_asin(selected.get("asin")), "automatic", {
            "reason": "prior_sales_then_keepa_velocity_then_asin",
            "prior_account_sale": bool(selected.get("prior_account_sale")),
            "keepa_sales_rank_drops90": selected.get("keepa_sales_rank_drops90"),
            "manual_override_invalidated": bool(manual_asin),
        })
    if not rows:
        return SelectionResult("no_candidates", None, "none", {"reason": "searches_returned_no_candidates"})
    if not usable:
        return SelectionResult("identity_review", None, "none", {"reason": "no_compatible_candidate"})
    unresolved = [row for row in usable if row.get("eligibility_status") in {None, "unknown", "error"} or row.get("eligibility_is_fresh") is False]
    if unresolved:
        return SelectionResult("eligibility_pending", None, "none", {"reason": "eligibility_unknown_or_stale"})
    return SelectionResult("restricted_no_eligible", None, "none", {"reason": "all_compatible_candidates_restricted"})


def ranking_key(row: dict[str, Any]) -> tuple[int, int, int, str]:
    velocity = row.get("keepa_sales_rank_drops90")
    known = velocity is not None
    return (-int(bool(row.get("prior_account_sale"))), -int(known), -int(velocity or 0), clean_asin(row.get("asin")))


def fresh_eligible(row: dict[str, Any]) -> bool:
    return row.get("eligibility_status") == "eligible" and row.get("eligibility_is_fresh", True) is True


def result(status: str, reasons: list[str], details: dict[str, Any]) -> CompatibilityResult:
    return CompatibilityResult(status, tuple(dict.fromkeys(reasons)), details)


def normalize_text(value: Any) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value or "").lower()))


def words(value: Any) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", str(value or "").lower()))


def marker_set(value: Any, markers: set[str]) -> set[str]:
    return words(value) & markers


def has_any(value: Any, markers: set[str]) -> bool:
    return bool(marker_set(value, markers))


def region(value: Any) -> str | None:
    value_words = words(value)
    for name, markers in REGION_MARKERS.items():
        if value_words & markers:
            return name
    return None


def token_similarity(left: Any, right: Any) -> float:
    a = words(left) - STOP_WORDS - EDITION_WORDS - BUNDLE_WORDS
    b = words(right) - STOP_WORDS - EDITION_WORDS - BUNDLE_WORDS
    return len(a & b) / len(a | b) if a and b else 0.0


def is_catalog_accessory(catalog: dict[str, Any], title: str) -> bool:
    product_type = normalize_text(catalog.get("product_type"))
    return has_any(title, ACCESSORY_WORDS) or any(word in product_type for word in ACCESSORY_WORDS)


def commercial_format(value: Any) -> str:
    normalized = normalize_text(value)
    if "code in box" in normalized or "code in a box" in normalized:
        return "code_in_box"
    if has_any(value, DIGITAL_WORDS):
        return "digital"
    return "physical"


def clean_asin(value: Any) -> str:
    asin = str(value or "").strip().upper()
    return asin if re.fullmatch(r"[A-Z0-9]{10}", asin) else ""
