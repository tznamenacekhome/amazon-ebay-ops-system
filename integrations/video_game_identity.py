"""Canonical video-game identity parsing and comparison for sourcing."""

from __future__ import annotations

import re
import hashlib
import json
from copy import deepcopy
from functools import lru_cache
from typing import Any

from system_detection import detect_system_from_title, normalize_system


ROMAN_NUMERAL_VALUES = {
    "ii": "2",
    "iii": "3",
    "iv": "4",
    "v": "5",
    "vi": "6",
    "vii": "7",
    "viii": "8",
    "ix": "9",
    "x": "10",
    "xi": "11",
    "xii": "12",
    "xiii": "13",
    "xiv": "14",
    "xv": "15",
    "xvi": "16",
}

ORDINAL_VALUES = {
    "first": "1",
    "second": "2",
    "third": "3",
    "fourth": "4",
    "fifth": "5",
}

IGNORED_GAME_NAMES = {"", "game", "video game", "games", "software"}

EDITION_PATTERNS = [
    ("Complete Edition", re.compile(r"\bcomplete(?:\s+edition)?\b|\bgame\s+of\s+the\s+year\b|\bgoty\b")),
    ("Deluxe", re.compile(r"\bdeluxe(?:\s+edition)?\b")),
    ("Collector's", re.compile(r"\bcollector'?s?(?:\s+edition)?\b")),
    ("Definitive", re.compile(r"\bdefinitive(?:\s+edition)?\b")),
    ("GOTY", re.compile(r"\bgoty\b|\bgame\s+of\s+the\s+year\b")),
    ("Greatest Hits", re.compile(r"\bgreatest\s+hits\b")),
    ("Nintendo Selects", re.compile(r"\bnintendo\s+selects\b")),
    ("PlayStation Hits", re.compile(r"\bplaystation\s+hits\b|\bps\s+hits\b")),
    ("Platinum Hits", re.compile(r"\bplatinum\s+hits\b")),
]

REGION_PATTERNS = [
    ("NTSC-U/C", re.compile(r"\bntsc[-\s]?u/?c?\b|\bnorth\s+american\b|\busa\b|\bus\s+version\b")),
    ("PAL", re.compile(r"\bpal\b|\bpegi\b|\buk\s+(?:version|import)\b|\beuropean\s+version\b")),
    ("NTSC-J", re.compile(r"\bntsc[-\s]?j\b|\bjapan(?:ese)?\b")),
]

IDENTITY_PATTERNS = [
    {
        "franchise": "Rock Band",
        "coreProduct": "The Beatles",
        "theme": "The Beatles",
        "pattern": re.compile(r"\b(?:the\s+beatles\s+rock\s+band|rock\s+band\s+(?:the\s+)?beatles)\b"),
    },
    {
        "franchise": "Rock Band",
        "coreProduct": "Classic Rock Track Pack",
        "packageType": "Track Pack",
        "theme": "Classic Rock",
        "pattern": re.compile(r"\b(?:classic\s+rock\s+)?rock\s+band\s+(?:classic\s+rock\s+)?track\s+pack\b|\brock\s+band\s+track\s+pack\s+classic\s+rock\b"),
    },
    {
        "franchise": "Rock Band",
        "coreProduct": "Country Track Pack",
        "packageType": "Track Pack",
        "theme": "Country",
        "pattern": re.compile(r"\brock\s+band\s+(?:country\s+)?track\s+pack\b|\brock\s+band\s*:\s*country\s+track\s+pack\b"),
        "requires": ("country",),
    },
    {
        "franchise": "Rock Band",
        "coreProduct": "Metal Track Pack",
        "packageType": "Track Pack",
        "theme": "Metal",
        "pattern": re.compile(r"\brock\s+band\s+(?:metal\s+)?track\s+pack\b|\brock\s+band\s*:\s*metal\s+track\s+pack\b"),
        "requires": ("metal",),
    },
    {
        "franchise": "Rock Band",
        "coreProduct": "Track Pack",
        "packageType": "Track Pack",
        "pattern": re.compile(r"\brock\s+band\b.*\btrack\s+pack\b|\btrack\s+pack\b.*\brock\s+band\b"),
    },
    {
        "franchise": "Rock Band",
        "coreProduct": "Main Game",
        "pattern": re.compile(r"\brock\s+band\b"),
        "installment": re.compile(r"\brock\s+band\s+(?P<value>[2-4])\b"),
    },
    {
        "franchise": "Disney Infinity",
        "coreProduct": "Starter Pack",
        "packageType": "Starter Pack",
        "pattern": re.compile(r"\bdisney\s+infinity\b"),
        "generation": re.compile(r"\bdisney\s+infinity(?:\s+(?P<value>[123]\.0))?\b|\b(?P<value2>[123]\.0)\b"),
        "themes": [
            ("Marvel Super Heroes", re.compile(r"\bmarvel\s+super\s+heroes\b|\bmarvel\b")),
            ("Star Wars", re.compile(r"\bstar\s+wars\b")),
        ],
    },
    {
        "franchise": "Dead Rising",
        "coreProduct": "Main Game",
        "pattern": re.compile(r"\bdead\s+rising\b"),
        "installment": re.compile(r"\bdead\s+rising\s+(?P<value>[2-4])\b"),
    },
    {
        "franchise": "Shrek",
        "coreProduct": "Smash N' Crash Racing",
        "pattern": re.compile(r"\bshrek(?:'s)?\s+smash\s+n'?[\s-]*crash\s+racing\b"),
    },
    {
        "franchise": "Shrek",
        "coreProduct": "Carnival Craze",
        "theme": "Carnival",
        "pattern": re.compile(r"\bshrek(?:'s)?\s+carnival\s+craze\b"),
    },
    {
        "franchise": "Shrek",
        "coreProduct": "Main Game",
        "pattern": re.compile(r"\bshrek\b"),
        "installment": re.compile(r"\bshrek\s+(?:the\s+)?(?P<value>2|third|3)\b"),
    },
    {
        "franchise": "Wipeout",
        "coreProduct": "Main Game",
        "pattern": re.compile(r"\b(?:abc'?s\s+)?wipeout\b"),
        "installment": re.compile(r"\b(?:abc'?s\s+)?wipeout\s+(?P<value>[2-9])\b"),
    },
    {
        "franchise": "Final Fantasy",
        "coreProduct": "Main Game",
        "pattern": re.compile(r"\bfinal\s+fantasy\b"),
        "installment": re.compile(r"\bfinal\s+fantasy\s+(?P<value>xiv|14|xiii|13|xii|12|xv|15|xvi|16|[2-9])\b"),
    },
    {
        "franchise": "Wii Play",
        "coreProduct": "Motion" ,
        "pattern": re.compile(r"\bwii\s+play\s+motion\b"),
    },
    {
        "franchise": "Wii Play",
        "coreProduct": "Main Game",
        "pattern": re.compile(r"\bwii\s+play\b"),
    },
    {
        "franchise": "Tiger Woods PGA Tour",
        "coreProduct": "Main Game",
        "pattern": re.compile(r"\btiger\s+woods\s+pga\s+tour\b"),
        "installment": re.compile(r"\btiger\s+woods\s+pga\s+tour\s+(?P<value>\d{2})\b"),
    },
    {
        "franchise": "New Carnival Games",
        "coreProduct": "Main Game",
        "pattern": re.compile(r"\bnew\s+carnival\s+games\b"),
    },
    {
        "franchise": "Cookie's Counting Carnival",
        "coreProduct": "Main Game",
        "pattern": re.compile(r"\bcookie\s+s\s+counting\s+carnival\b|\bcookies\s+counting\s+carnival\b"),
    },
]


def build_identity_comparison(
    *,
    amazon_title: Any,
    ebay_title: Any,
    seed: dict[str, Any] | None = None,
    evidence: dict[str, Any] | None = None,
    policy: str = "legacy",
) -> dict[str, Any]:
    if policy == "phase3_shadow":
        return evaluated_identity(amazon_title, ebay_title, seed or {}, evidence or {})
    if policy != "legacy":
        raise ValueError("Unapproved identity policy")
    seed = seed or {}
    evidence = evidence or {}
    amazon_identity = parse_video_game_identity(
        amazon_title,
        side="amazon",
        platform=amazon_platform(seed, amazon_title),
        catalog_identity=catalog_identity(seed),
    )
    ebay_identity = parse_video_game_identity(
        ebay_title,
        side="ebay",
        platform=ebay_platform(evidence, ebay_title),
        game_names=usable_game_names(evidence),
        item_specifics=evidence,
    )
    catalog = catalog_identity(seed)
    if catalog and (not catalog.get("asin") or str(catalog["asin"]).upper() != str(seed.get("asin") or "").upper()):
        for key in ("platform", "edition", "region"):
            field = amazon_identity["fields"][key]
            if any(source["field"].startswith("raw_context_json.amazon_catalog_identity.") for source in field["sources"]):
                field.update(value=None, state="unknown", sources=[], reason="Catalog ASIN not verified against seed")
    comparisons = compare_identities(amazon_identity, ebay_identity)
    overall = overall_result(comparisons)
    reason = reason_for_result(comparisons)
    return {
        "version": "video_game_identity_v1",
        # Phase 1: evidence diagnostics are additive. These legacy result and
        # hard_block fields remain the admission policy until the policy phase.
        "evidenceDecision": evidence_decision(amazon_identity, ebay_identity),
        "amazon": amazon_identity,
        "ebay": ebay_identity,
        "comparisons": comparisons,
        "result": overall,
        "reason": reason,
        "conflicts": [key for key, value in comparisons.items() if value.get("result") == "conflict"],
        "hard_block": overall == "conflict",
    }


def parse_video_game_identity(
    title: Any,
    *,
    side: str,
    platform: Any = None,
    catalog_identity: dict[str, Any] | None = None,
    game_names: list[str] | None = None,
    item_specifics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    catalog_identity = catalog_identity or {}
    item_specifics = item_specifics or {}
    sources = evidence_texts(title, game_names, item_specifics)
    primary = sources[0]["text"] if sources else ""
    parsed = parse_known_identity(sources)
    normalized_platform = normalize_system(str(catalog_identity.get("normalized_platform") or platform or "")) or detect_system_from_title(" ".join(source["text"] for source in sources))
    edition = catalog_identity.get("normalized_edition") or first_edition(sources)
    region = catalog_identity.get("normalized_region") or first_region(sources)
    identity = {
        "franchise": parsed.get("franchise"),
        "coreProduct": parsed.get("coreProduct"),
        "coreGame": display_core_game(parsed),
        "installment": installment_display(parsed.get("installmentRaw"), parsed.get("installment")),
        "installmentNormalized": parsed.get("installment"),
        "generation": parsed.get("generation"),
        "theme": parsed.get("theme"),
        "edition": edition or "Base / Standard",
        "packageType": parsed.get("packageType") or package_type(primary),
        "platform": platform_display(normalized_platform),
        "region": region,
        "completeness": completeness(primary, item_specifics),
        "digitalPhysical": digital_physical(primary, item_specifics),
        "confidence": parsed.get("confidence", 0.35 if primary else 0),
        "evidence": parsed.get("evidence", []) + field_evidence(side, sources, catalog_identity, normalized_platform, edition, region),
    }
    field_sources = sources + [{"source": "platform_values", "text": str(value)} for value in item_specifics.get("platform_values", [])]
    identity["fields"] = identity_fields(identity, field_sources, catalog_identity, side)
    identity["confidenceKind"] = "uncalibrated_parser_heuristic"
    return identity


EVIDENCE_VERSION = "video_game_evidence_v2"
IDENTITY_FIELDS = ("franchise", "coreProduct", "coreGame", "installment", "generation", "theme",
                   "edition", "packageType", "platform", "region", "completeness", "digitalPhysical")


def identity_fields(identity, sources, catalog, side):
    """Attach provenance to the existing parser; never feed this view to admission.

    Absence of a negative term is not evidence of the expected positive value.
    Unsupported legacy defaults remain available only as labeled expectations.
    """
    fields = {}
    defaults = {"edition": "Base / Standard", "packageType": "Standard software",
                "installment": "None / Base title", "completeness": "Complete", "digitalPhysical": "Physical"}
    identity_keys = {"franchise", "coreProduct", "coreGame", "installment", "generation", "theme"}
    for key in IDENTITY_FIELDS:
        value = identity.get(key)
        expectation = value if value and value == defaults.get(key) else None
        provenance = []
        if key in identity_keys:
            provenance = [dict(field=row["source"], span=row["value"], snapshot=None)
                          for row in identity["evidence"] if row.get("field") == "identity"]
        elif key in {"edition", "region"}:
            catalog_key = "normalized_" + key
            if catalog.get(catalog_key):
                provenance = [dict(field="raw_context_json.amazon_catalog_identity." + catalog_key,
                                   span=str(catalog[catalog_key]), snapshot=catalog.get("snapshot_id") or catalog.get("captured_at"))]
            else:
                parser = first_edition if key == "edition" else first_region
                provenance = [dict(field=row["source"], span=row["text"], snapshot=None) for row in sources
                              if row["source"] != "country_of_origin_values" and parser([row]) == value and value]
        elif key == "platform":
            provenance = [dict(field=row["source"], span=row["text"], snapshot=None) for row in sources
                          if detect_system_from_title(row["text"]) or row["source"] == "platform_values"]
            if catalog.get("normalized_platform"):
                provenance = [dict(field="raw_context_json.amazon_catalog_identity.normalized_platform",
                                   span=str(catalog["normalized_platform"]), snapshot=catalog.get("snapshot_id") or catalog.get("captured_at"))]
        else:
            provenance = [dict(field=row["source"], span=row["text"], snapshot=None) for row in sources
                          if row["source"] not in {"country_of_origin_values", "region_code_values"}]
        if expectation:
            value = None
        if key == "region" and not provenance:
            value = None
        if key == "generation" and value == "1.0" and not any("1.0" in row["span"] for row in provenance):
            expectation, value = value, None
        state = "inferred" if value and provenance else "unknown"
        if value and provenance and all(row["field"].startswith("raw_context_json.amazon_catalog_identity.") for row in provenance):
            state = "supported"
        # Edition words such as 'complete with manual' do not establish an edition.
        if key == "edition" and value == "Complete Edition" and not catalog.get("normalized_edition"):
            if not any("complete edition" in normalize_text(row["span"]) for row in provenance):
                expectation, value, state = value, None, "unknown"
        if key in identity_keys and value:
            source_values = []
            for source in sources:
                parsed = parse_known_identity([source])
                parsed_value = display_core_game(parsed) if key == "coreGame" else parsed.get(key)
                if parsed_value:
                    source_values.append((parsed_value, source))
            if len({str(item[0]) for item in source_values}) > 1:
                state = "conflicting_sources"
                provenance = [dict(field=source["source"], span=source["text"], snapshot=None) for _, source in source_values]
        if not provenance:
            value, state = None, "unknown"
        # Keep diagnostic JSON bounded; full evidence remains in the source snapshot.
        provenance = [{**source, "span": source["span"][:240],
                       "spanTruncated": len(source["span"]) > 240,
                       "sourceHash": hashlib.sha256(source["span"].encode()).hexdigest()}
                      for source in provenance[:3]]
        fields[key] = {"value": value, "state": state, "sources": provenance if value else [],
                       "parserVersion": "video_game_identity_v1", "evidenceVersion": EVIDENCE_VERSION,
                       "side": side, "expectation": expectation,
                       "availability": "new", "confidenceKind": "uncalibrated_parser_heuristic"}
    return fields


def evidence_decision(amazon, ebay):
    """Use the existing comparator on evidenced values, for diagnostics only."""
    sides = {}
    for side, identity in (("amazon", amazon), ("ebay", ebay)):
        sides[side] = {key: field["value"] for key, field in identity["fields"].items()}
        sides[side]["installmentNormalized"] = identity.get("installmentNormalized") if sides[side].get("installment") else None
    comparisons = compare_identities(sides["amazon"], sides["ebay"])
    comparisons["coreGame"] = compare_field(sides["amazon"], sides["ebay"], "coreGame", conflict=True)
    for key, comparison in comparisons.items():
        comparison["reason"] = ("Evidence missing on one or both sides" if comparison["result"] == "unknown"
                                else "Normalized evidence agrees" if comparison["result"] == "match"
                                else "Normalized evidence differs")
        comparison["amazonEvidenceRef"] = "amazon.fields." + key
        comparison["ebayEvidenceRef"] = "ebay.fields." + key
        if comparison["result"] != "unknown" and any(identity["fields"][key]["state"] == "conflicting_sources" for identity in (amazon, ebay)):
            comparison["result"] = "review"
            comparison["reason"] = "Sources disagree within one listing"
    result = "unknown"
    if any(row["result"] == "conflict" for row in comparisons.values()):
        result = "non-match"
    elif any(row["result"] == "review" for row in comparisons.values()):
        result = "needs_review"
    elif comparisons["coreGame"]["result"] == "match" and (
        comparisons["installment"]["result"] == "match"
        or (comparisons["coreProduct"]["result"] == "match" and amazon.get("coreProduct") != "Main Game")
    ):
        result = "match"
    return {"version": EVIDENCE_VERSION, "productIdentityVerdict": result, "comparisons": comparisons,
            "policyRole": "diagnostic_only_legacy_admission_unchanged"}


def evidence_texts(title: Any, game_names: list[str] | None, item_specifics: dict[str, Any]) -> list[dict[str, str]]:
    rows = []
    if text_or_none(title):
        rows.append({"source": "title", "text": str(title)})
    for game_name in game_names or []:
        normalized = normalize_text(game_name)
        if normalized not in IGNORED_GAME_NAMES:
            rows.append({"source": "game_name", "text": game_name})
    for key in ("features_values", "type_values", "format_values", "description"):
        value = item_specifics.get(key)
        if isinstance(value, list):
            text = " ".join(str(item) for item in value if item)
        else:
            text = str(value or "")
        if text.strip():
            rows.append({"source": key, "text": text})
    for key in ("region_code_values", "country_of_origin_values"):
        values = item_specifics.get(key)
        if isinstance(values, list) and values:
            rows.append({"source": key, "text": " ".join(str(item) for item in values if item)})
    return rows


def parse_known_identity(sources: list[dict[str, str]]) -> dict[str, Any]:
    for source in sources:
        text = normalize_text(source["text"])
        for spec in IDENTITY_PATTERNS:
            requires = spec.get("requires")
            if requires and not all(term in text for term in requires):
                continue
            if not spec["pattern"].search(text):
                continue
            installment_raw = regex_value(spec.get("installment"), text)
            generation_raw = regex_value(spec.get("generation"), text)
            theme = first_theme(spec, text)
            return {
                "franchise": spec["franchise"],
                "coreProduct": spec["coreProduct"],
                "installmentRaw": display_raw_number(installment_raw),
                "installment": normalize_number_value(installment_raw),
                "generation": normalize_number_value(generation_raw) or ("1.0" if spec["franchise"] == "Disney Infinity" and "2.0" not in text and "3.0" not in text else None),
                "theme": theme or spec.get("theme"),
                "packageType": spec.get("packageType"),
                "confidence": 0.95 if source["source"] in {"title", "game_name"} else 0.75,
                "evidence": [{"field": "identity", "source": source["source"], "value": source["text"], "confidence": 0.95}],
            }
    return {"confidence": 0.0, "evidence": []}


def compare_identities(amazon: dict[str, Any], ebay: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        "franchise": compare_field(amazon, ebay, "franchise", conflict=True),
        "coreProduct": compare_field(amazon, ebay, "coreProduct", conflict=True),
        "installment": compare_field(amazon, ebay, "installmentNormalized", label="installment", conflict=True),
        "generation": compare_field(amazon, ebay, "generation", conflict=True),
        "theme": compare_field(amazon, ebay, "theme", conflict=True),
        "edition": compare_edition(amazon, ebay),
        "platform": compare_field(amazon, ebay, "platform", conflict=False),
        "region": compare_field(amazon, ebay, "region", conflict=False),
        "packageType": compare_field(amazon, ebay, "packageType", conflict=False),
        "completeness": compare_field(amazon, ebay, "completeness", conflict=False),
        "digitalPhysical": compare_field(amazon, ebay, "digitalPhysical", conflict=False),
    }


def compare_field(
    amazon: dict[str, Any],
    ebay: dict[str, Any],
    key: str,
    *,
    label: str | None = None,
    conflict: bool,
) -> dict[str, Any]:
    field = label or key
    left = amazon.get(key)
    right = ebay.get(key)
    if not left or not right:
        return {"field": field, "result": "unknown", "amazon": left, "ebay": right}
    if key == "platform" and platforms_compatible(str(left), str(right)):
        return {"field": field, "result": "match", "amazon": left, "ebay": right}
    if left == right:
        return {"field": field, "result": "match", "amazon": left, "ebay": right}
    return {"field": field, "result": "conflict" if conflict else "review", "amazon": left, "ebay": right}


def platforms_compatible(left: str, right: str) -> bool:
    xbox_cross_generation = {"Xbox One", "Xbox Series X"}
    if {left, right} <= xbox_cross_generation:
        return True
    if left in {"PS", "PlayStation"} or right in {"PS", "PlayStation"}:
        return True
    if left == "Xbox" or right == "Xbox":
        return True
    return False


def compare_edition(amazon: dict[str, Any], ebay: dict[str, Any]) -> dict[str, Any]:
    left = amazon.get("edition")
    right = ebay.get("edition")
    if not left or not right:
        return {"field": "edition", "result": "unknown", "amazon": left, "ebay": right}
    if left == right:
        return {"field": "edition", "result": "match", "amazon": left, "ebay": right}
    material = {"Complete Edition", "Deluxe", "Collector's", "Definitive", "GOTY"}
    if left in material and right in material:
        return {"field": "edition", "result": "conflict", "amazon": left, "ebay": right}
    return {"field": "edition", "result": "review", "amazon": left, "ebay": right}


def overall_result(comparisons: dict[str, dict[str, Any]]) -> str:
    if any(row.get("result") == "conflict" for row in comparisons.values()):
        return "conflict"
    if any(row.get("result") == "review" for row in comparisons.values()):
        return "review"
    positive_identity = comparisons.get("franchise", {}).get("result") == "match" or comparisons.get("coreProduct", {}).get("result") == "match"
    if positive_identity:
        return "match"
    return "unknown"


def reason_for_result(comparisons: dict[str, dict[str, Any]]) -> str:
    conflicts = [row for row in comparisons.values() if row.get("result") == "conflict"]
    if conflicts:
        return "; ".join(f"{row['field']} conflict: Amazon {row.get('amazon')}, eBay {row.get('ebay')}" for row in conflicts[:3])
    reviews = [row for row in comparisons.values() if row.get("result") == "review"]
    if reviews:
        return "; ".join(f"{row['field']} review: Amazon {row.get('amazon')}, eBay {row.get('ebay')}" for row in reviews[:3])
    return "Identity matched or unknown; unknown fields are not positive evidence."


def usable_game_names(evidence: dict[str, Any]) -> list[str]:
    return [value for value in evidence.get("game_name_values") or [] if normalize_text(value) not in IGNORED_GAME_NAMES]


def amazon_platform(seed: dict[str, Any], amazon_title: Any) -> str | None:
    raw_context = seed.get("raw_context_json") if isinstance(seed.get("raw_context_json"), dict) else {}
    catalog = catalog_identity(seed)
    return (
        catalog.get("normalized_platform")
        or seed.get("system")
        or raw_context.get("inferred_system")
        or detect_system_from_title(str(amazon_title or ""))
    )


def ebay_platform(evidence: dict[str, Any], ebay_title: Any) -> str | None:
    for value in evidence.get("platform_values") or []:
        system = normalize_system(str(value or ""))
        if system:
            return system
    return detect_system_from_title(str(ebay_title or ""))


def catalog_identity(seed: dict[str, Any]) -> dict[str, Any]:
    raw_context = seed.get("raw_context_json") if isinstance(seed.get("raw_context_json"), dict) else {}
    value = raw_context.get("amazon_catalog_identity")
    return value if isinstance(value, dict) else {}


def first_edition(sources: list[dict[str, str]]) -> str | None:
    text = normalize_text(" ".join(source["text"] for source in sources))
    for label, pattern in EDITION_PATTERNS:
        if pattern.search(text):
            return label
    return None


def first_region(sources: list[dict[str, str]]) -> str | None:
    text = normalize_text(" ".join(source["text"] for source in sources))
    for label, pattern in REGION_PATTERNS:
        if pattern.search(text):
            return label
    return None


def package_type(value: Any) -> str:
    text = normalize_text(value)
    if "starter pack" in text:
        return "Starter Pack"
    if "track pack" in text:
        return "Track Pack"
    if "steelbook only" in text or "steel book only" in text:
        return "Steelbook only"
    if "bundle" in text:
        return "Bundle"
    if "game only" in text:
        return "Game only"
    return "Standard software"


def completeness(title: Any, item_specifics: dict[str, Any]) -> str:
    text = normalize_text(" ".join([str(title or ""), str(item_specifics.get("description") or "")]))
    if any(term in text for term in ("disc only", "case only", "manual only", "no game", "no disc", "incomplete")):
        return "Incomplete"
    return "Complete"


def digital_physical(title: Any, item_specifics: dict[str, Any]) -> str:
    text = normalize_text(" ".join([str(title or ""), str(item_specifics.get("description") or "")]))
    if any(term in text for term in ("digital", "download", "dlc", "code only", "email delivery")):
        return "Digital"
    return "Physical"


def field_evidence(
    side: str,
    sources: list[dict[str, str]],
    catalog: dict[str, Any],
    platform: str | None,
    edition: str | None,
    region: str | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if catalog:
        rows.append({"field": "amazonCatalog", "source": "exact_asin_catalog_items", "value": compact_catalog(catalog), "confidence": 0.98})
    if platform:
        rows.append({"field": "platform", "source": f"{side}_structured_or_title", "value": platform, "confidence": 0.9})
    if edition:
        rows.append({"field": "edition", "source": f"{side}_structured_or_title", "value": edition, "confidence": 0.75})
    if region:
        rows.append({"field": "region", "source": f"{side}_structured_or_title", "value": region, "confidence": 0.75})
    rows.extend({"field": "sourceText", "source": source["source"], "value": source["text"], "confidence": 0.65} for source in sources[:4])
    return rows


def compact_catalog(catalog: dict[str, Any]) -> dict[str, Any]:
    return {
        key: catalog.get(key)
        for key in ("product_type", "normalized_platform", "normalized_edition", "normalized_region", "variation_theme")
        if catalog.get(key) is not None
    }


def first_theme(spec: dict[str, Any], text: str) -> str | None:
    for label, pattern in spec.get("themes") or []:
        if pattern.search(text):
            return label
    return None


def regex_value(pattern: Any, text: str) -> str | None:
    if not pattern:
        return None
    match = pattern.search(text)
    if not match:
        return None
    return match.groupdict().get("value") or match.groupdict().get("value2")


def normalize_number_value(value: Any) -> str | None:
    text = normalize_text(value)
    if not text:
        return None
    return ORDINAL_VALUES.get(text) or ROMAN_NUMERAL_VALUES.get(text) or text.lstrip("0") or text


def display_raw_number(value: Any) -> str | None:
    text = str(value or "").strip()
    return text.upper() if text.casefold() in ROMAN_NUMERAL_VALUES else text or None


def installment_display(raw: Any, normalized: Any) -> str:
    if not normalized:
        return "None / Base title"
    if raw and str(raw).casefold() in ROMAN_NUMERAL_VALUES:
        return f"{str(raw).upper()} / {normalized}"
    return str(raw or normalized)


def display_core_game(identity: dict[str, Any]) -> str | None:
    franchise = identity.get("franchise")
    core = identity.get("coreProduct")
    if not franchise:
        return None
    if core in {None, "Main Game"}:
        return str(franchise)
    if franchise == "Rock Band" and core == "Classic Rock Track Pack":
        return "Rock Band Track Pack: Classic Rock"
    if franchise == "Rock Band" and str(core).endswith("Track Pack"):
        return f"Rock Band {core}"
    return str(core)


def platform_display(value: str | None) -> str | None:
    display = {
        "3DS": "Nintendo 3DS",
        "DS": "Nintendo DS",
        "Switch": "Nintendo Switch",
        "Switch 2": "Nintendo Switch 2",
        "Wii": "Nintendo Wii",
        "Wii U": "Nintendo Wii U",
        "PS 2": "PlayStation 2",
        "PS 3": "PlayStation 3",
        "PS 4": "PlayStation 4",
        "PS 5": "PlayStation 5",
    }
    return display.get(value or "", value)


def text_or_none(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def normalize_text(value: Any) -> str:
    text = str(value or "").casefold()
    text = text.replace("&", " and ")
    text = re.sub(r"[\[\]{}()\"']", " ", text)
    text = re.sub(r"[/|:_\-+]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# Candidate Phase 3 policy. Only explicit offline callers can select it; the
# deployed scorer stays on legacy until the complete visibility gate passes.
PHASE3_VERSION = "video_game_identity_phase3_shadow_v3"
PHASE3_EDITIONS = [
    ("Complete Edition", r"\bcomplete\s+edition\b"),
    ("GOTY", r"\b(?:goty|game\s+of\s+the\s+year)(?:\s+edition)?\b"),
    ("Anniversary", r"\b\d+(?:st|nd|rd|th)\s+anniversary(?:\s+edition)?\b"),
    *[(label.title() + " Edition", rf"\b{label}\s+edition\b") for label in
      ("standard", "ultimate", "deluxe", "gold", "definitive", "limited", "special", "premium")],
    ("Collector's Edition", r"\bcollector\s*s?\s+edition\b"),
    *[(label, re.escape(label.casefold())) for label in
      ("Greatest Hits", "Nintendo Selects", "PlayStation Hits", "Platinum Hits")],
]
PHASE3_PLATFORM = re.compile(
    r"\b(?:(?:sony\s+)?play\s*station\s*[1-5]?|ps\s*[1-5]|"
    r"(?:microsoft\s+)?xbox\s*(?:360|one(?:\s+x)?|series\s*[xs])?|"
    r"(?:nintendo\s+)?(?:switch(?:\s+2)?|3ds|nds|ds|wii\s+u|wii(?!\s+play))|"
    r"nintendo|windows|pc|mac)\b", re.I)


def evidence_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()


def split_game_names(value):
    """Separate repeated names without tearing apart parenthesized metadata."""
    parts, start, depth = [], 0, 0
    for index, char in enumerate(value):
        if char in "([": depth += 1
        elif char in ")]": depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            parts.append(value[start:index].strip())
            start = index + 1
    parts.append(value[start:].strip())
    return [part for part in parts if part]


def reconcile_listing_title(title, evidence):
    """Assign corroborated post-platform metadata without shortening a product.

    Only the suffix after an explicit platform is considered. Product words in
    Game Name and everything before the platform remain protected. Contents of
    an explicitly named inclusive edition are separated only when a structured
    name agrees with the prefix and the description calls them expansions.
    """
    raw = str(title or "")
    platforms = list(PHASE3_PLATFORM.finditer(raw))
    if not platforms: return raw, []
    boundary = platforms[-1].end()
    prefix, suffix = raw[:boundary], raw[boundary:]
    aspects = evidence.get("aspects") or {}
    names = usable_game_names(evidence)
    protected = " ".join(normalize_text(n) for n in names)
    assigned = []
    metadata = []
    for key in ("release_year", "genre", "sub-genre"):
        metadata.extend((str(v), key) for v in aspects.get(key, []))
    for value in aspects.get("rating", []):
        rating = re.match(r"\s*(E10\+|EC|E|T|M|AO|RP)\b", str(value), re.I)
        if rating: metadata.append((rating[1], "rating"))
    for value in aspects.get("region_code", []):
        region = re.match(r"\s*(NTSC[- ]?[UJ](?:/C)?|PAL)\b", str(value), re.I)
        if region: metadata.append((region[1], "region_code"))
    features = " ".join(str(v).lower() for v in aspects.get("features", []))
    for feature in ("multiplayer", "online"):
        if feature in features: metadata.append((feature, "features"))
    for value, source in sorted(metadata, key=lambda v: len(v[0]), reverse=True):
        if not value or re.search(r"\b"+re.escape(normalize_text(value))+r"\b", protected): continue
        pattern = r"(?<!\w)" + re.escape(value) + r"(?!\w)"
        if re.search(pattern, suffix, re.I):
            assigned.append({"text":value,"reason":"post-platform metadata corroborated by " + source})
            suffix = re.sub(pattern, " ", suffix, flags=re.I)
    # A list after the platform is not blanket permission to erase a subtitle.
    # Require an explicitly inclusive edition, matching structured core name,
    # and an inclusion statement identifying multiple expansion names.
    prefix_fields = general_product_fields(prefix)
    description = str(evidence.get("description") or "")
    content_parts = [re.sub(r"\W*new\W*$", "", part, flags=re.I).strip(" *-()") for part in suffix.split("+")]
    inclusive = prefix_fields["edition"] in {"Complete Edition", "GOTY"}
    name_agrees = any(general_product_fields(part)["coreGame"] == prefix_fields["coreGame"]
                      for name in names for part in split_game_names(name))
    inclusion = re.search(r"\bincludes?\b[^.]{0,300}\bexpansions?\b", description, re.I)
    identified = sum(bool(part) and bool(inclusion) and normalize_text(part) in normalize_text(inclusion[0]) for part in content_parts)
    if inclusive and name_agrees and len(content_parts) >= 2 and identified >= 2:
        # Keep every enumerated component as evidence, including abbreviated
        # names. We establish its role as contents, not exact contents parity.
        assigned.append({"text":suffix.strip(),"reason":"enumerated included contents; title edition, Game Name and description corroborate role",
                         "contents":content_parts})
        suffix = ""
    return prefix + suffix, assigned


def general_product_fields(value, publishers=()):
    """Keep the full named retail product; no franchise is required to parse it.

    This is identity normalization, not fuzzy matching or an Amazon search.
    In particular the search cleaner intentionally shortens Wii Play Motion;
    it cannot replace raw identity evidence here.
    """
    raw = re.sub(r"(?<=[a-z])(?=[A-Z][a-z])", " ", str(value))
    # Only remove generic Game when it follows a platform label, not from
    # product names such as Untitled Goose Game or Family Game Night.
    raw = re.sub("(" + PHASE3_PLATFORM.pattern + r")\s+game\b", r"\1", raw, flags=re.I)
    ignored = []
    # Hyphenated alphanumeric product identifiers are not sequel numbers.
    raw = re.sub(r"\b([A-Za-z]+)-(\d+)\b", r"\1XHYPHENX\2", raw)
    # Release metadata in parentheses is not a sequel; annual titles outside
    # parentheses (FIFA 2011 etc.) retain their numbers.
    text = re.sub(r"\([^)]*\)", lambda m: re.sub(r"\b(?:19|20)\d{2}\b", " ", m[0]), raw.casefold())
    text = normalize_text(text)
    text = PHASE3_PLATFORM.sub(" ", text)
    for publisher in publishers:
        publisher = normalize_text(publisher)
        if not publisher: continue
        # A structured Publisher is corroboration for attribution at an edge,
        # not permission to remove that word anywhere in a product name.
        pattern = r"^" + re.escape(publisher) + r"\s+|\s+(?:for\s+)?by\s+" + re.escape(publisher) + r"\b"
        if re.search(pattern, text): ignored.append({"text":publisher,"reason":"structured publisher attribution"})
        text = re.sub(pattern, " ", text)
    text = re.sub(r"\b(?:sku|stock|item)\s*#?\s*[a-z0-9-]+\b|\blot\s+of\s+\d+\b", " ", text)
    text = re.sub(r"\b(?:nwt|bnib|brand\s+new|factory\s+seal(?:ed)?|new\s+(?:and\s+)?sealed|sealed\s+new|sealed|free\s+shipping|(?:super\s+)?fast\s+shipping|"
                  r"shipping\s+fluff|ships\s+fast|shrink\s+wrapped|video\s+game|brand\s+new)\b", " ", text)
    # Standalone leading New is ambiguous and is retained. Never strip New
    # from New Super Mario Bros. / New Carnival Games.
    text = re.sub(r"^new\s*/?\s*sealed\s+", "", text)
    edition_values = []
    for label, pattern in PHASE3_EDITIONS:
        found = re.search(pattern, text)
        if found:
            edition_values.append(found[0] if label == "Anniversary" else label)
            text = re.sub(pattern, " ", text)
    text = re.sub(r"\bcomplete\s+(?:with\s+)?(?:case|manual)\b|\b(?:with\s+)?case\s+and\s+manual\b", " ", text)
    text = re.sub(r"\bnew\s*$", "", text.strip())
    text = re.sub(r"\b(?:for|on)\s*$", "", text.strip())
    text = re.sub(r"\b(?:the\s+)?(first|second|third|fourth|fifth)\b", lambda m: ORDINAL_VALUES[m[1]], text)
    text = re.sub(r"\b(" + "|".join(sorted(ROMAN_NUMERAL_VALUES, key=len, reverse=True)) + r")\b",
                  lambda m: ROMAN_NUMERAL_VALUES[m[1]], text)
    text = re.sub(r"[^\w\s.'+&]", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" .!")
    text = re.sub(r"\b(?:new|rare)\s*$", "", text).strip()
    text = re.sub(r"\b(?:by|for)\s*$", "", text).strip()
    text = re.sub(r"\bready\s+to\s+ship\s*$", "", text).strip()
    # Keep the name of an unfamiliar variant; only the generic label goes.
    # Explicit named editions were extracted above and are still compared.
    if len(text.split()) > 1:
        text = re.sub(r"\bedition\s*$", "", text).strip()
    text = text.replace("xhyphenx", "-")
    numbers = re.findall(r"(?<![\w-])(?:2k)?(\d+(?:\.\d+)?)\b", text)
    product = text if text not in IGNORED_GAME_NAMES and re.search(r"[a-z]", text) else None
    packages = [label for label in ("starter pack", "track pack", "expansion pack", "bundle", "game only", "steelbook only") if label in text]
    fields = {"coreGame": product, "coreProduct": product,
              "installment": numbers[0] if len(numbers) == 1 else None,
              "edition": " + ".join(sorted(set(edition_values))) or None,
              "packageType": " + ".join(packages) or None}
    if product and len(numbers) == 1:
        fields["coreProduct"] = re.sub(r"(?<![\w-])(?:2k)?" + re.escape(numbers[0]) + r"\b", "", product)
        fields["coreProduct"] = re.sub(r"\s+", " ", fields["coreProduct"]).strip()
    fields["tokenHandling"] = {"ignored": ignored, "assignedInstallments": numbers}
    # Family rules keep typed generation separate from the product name.
    # Omitted-generation policy is applied after all side sources reconcile.
    known = parse_known_identity([{"source": "title", "text": str(value)}])
    fields["franchise"] = known.get("franchise")
    if known.get("franchise") == "Disney Infinity":
        fields["generation"] = next((n for n in numbers if n in {"1.0", "2.0", "3.0"}), None)
        if fields["generation"] and len(numbers) == 1:
            fields["coreGame"] = fields["coreProduct"]
        fields["theme"] = known.get("theme")
    if "track pack" in text:
        fields["theme"] = next((x for x in ("classic rock", "country", "metal") if x in text), None)
    return fields


def source_name_relation(title, supporting):
    """Asymmetric within-listing reconciliation, never pair-match containment."""
    if not title or not supporting: return "unknown"
    compact = lambda text: re.sub(r"[^a-z0-9]", "", str(text).casefold())
    if compact(title) == compact(supporting): return "same"
    title_tokens, source_tokens = normalize_text(title).split(), normalize_text(supporting).split()
    # A structured Game Name can corroborate a displaced standalone installment.
    # Preserve word order, every product word and the exact number; this is not
    # token-set matching, cross-market containment, or a missing-number default.
    numbers = lambda tokens: [t for t in tokens if re.fullmatch(r"\d+(?:\.\d+)?", t)]
    left_numbers, right_numbers = numbers(title_tokens), numbers(source_tokens)
    if len(left_numbers) == len(right_numbers) == 1 and left_numbers == right_numbers:
        if [t for t in title_tokens if t not in left_numbers] == [t for t in source_tokens if t not in right_numbers]:
            return "same_typed_installment"
    remaining = iter(title_tokens)
    if all(any(token == candidate for candidate in remaining) for token in source_tokens):
        return "compatible_omission"
    return "explicit_conflict"


def phase3_side(title, side, evidence=None, catalog=None, platform=None):
    evidence, catalog = evidence or {}, catalog or {}
    cleaned_title, assigned = reconcile_listing_title(title, evidence) if side == "ebay" else (title, [])
    rows = [{"source": "title", "text": str(cleaned_title), "originalText":str(title)}] if title else []
    rows += [{"source": "game_name", "text": part.strip(), "originalText":value}
             for value in usable_game_names(evidence) for part in split_game_names(value)]
    publishers = (evidence.get("aspects") or {}).get("publisher") or []
    # A publisher appearing in the structured product name may be part of
    # that identity (for example Disney Infinity), not an attribution.
    names = usable_game_names(evidence)
    publishers = [p for p in publishers if names and not any(
        normalize_text(name).startswith(normalize_text(p) + " ") for name in names)]
    parsed = [(row, general_product_fields(row["text"], publishers)) for row in rows]
    output = {}
    for key in IDENTITY_FIELDS:
        values = [(values.get(key), row) for row, values in parsed if values.get(key) is not None]
        if key == "platform":
            platform_text = lambda text: re.sub(r"\bplaystation\s+ps\s*([1-5])\b", r"PlayStation \1", text, flags=re.I)
            values = [(platform_display(detect_system_from_title(platform_text(row["text"]))), row) for row in rows if detect_system_from_title(platform_text(row["text"]))]
            values += [(platform_display(normalize_system(v)), {"source": "platform_values", "text": v}) for v in evidence.get("platform_values", []) if normalize_system(v)]
            if not values and platform:
                values = [(platform_display(normalize_system(platform)), {"source": "seed.system", "text": platform})]
        if key == "region":
            allowed = rows + [{"source": "region_code_values", "text": v} for v in evidence.get("region_code_values", [])]
            values = [(first_region([row]), row) for row in allowed if first_region([row])]
        catalog_key = "normalized_" + key
        if key in {"edition", "platform", "region"} and catalog.get(catalog_key):
            val = catalog[catalog_key]
            if key == "edition": val = general_product_fields(val)["edition"] or val
            if key == "platform": val = platform_display(normalize_system(val))
            values.append((val, {"source": "exact_asin_catalog." + catalog_key, "text": str(catalog[catalog_key])}))
        reconciliation = []
        if key in {"coreGame", "coreProduct"} and values:
            primary = next(((v,r) for v,r in values if r["source"] == "title"), values[0])
            for value, source in values:
                relation = source_name_relation(primary[0], value)
                reconciliation.append({"source":source["source"],"relation":relation,"value":value})
            # Game Name may omit a subtitle, attribution, or edition/package
            # qualifier. Keep the full listing title; never collapse it to the
            # supporting subset, and never use cross-market containment.
            if any(r["relation"] == "same_typed_installment" for r in reconciliation):
                # Use the corroborating structured spelling; the source title,
                # independent installment and original spans remain available.
                primary = next((v for v in values if v[1]["source"] == "game_name" and
                    source_name_relation(primary[0], v[0]) == "same_typed_installment"), primary)
            if all(r["relation"] in {"same", "compatible_omission", "same_typed_installment"} for r in reconciliation):
                values = [(primary[0], source) for _, source in values]
        distinct = {str(v).casefold() for v, _ in values}
        state = "conflicting_sources" if len(distinct) > 1 else "supported" if values else "unknown"
        sources = [{"field": row["source"], "span": row.get("originalText",row["text"])[:240], "normalizedSpan":row["text"][:240], "sourceHash": evidence_hash(row.get("originalText",row["text"])),
                    "snapshot": catalog.get("snapshot_id") if row["source"].startswith("exact_asin") else None} for _, row in values]
        output[key] = {"value": values[0][0] if values else None, "state": state, "sources": sources[:3],
                       "side": side, "parserVersion": PHASE3_VERSION, "evidenceVersion": PHASE3_VERSION,
                       "expectation": None, "sourceReconciliation": reconciliation, "confidenceKind": "uncalibrated_parser_heuristic"}
    # Operator-approved Disney Infinity convention: an unnumbered release is
    # generation 1.0. Reconcile every source first so an abbreviated Game Name
    # cannot manufacture 1.0 against an explicit later generation. This is a
    # policy inference, not a source observation or a saved operator correction.
    if (output["franchise"]["value"] == "Disney Infinity"
            and output["generation"]["state"] == "unknown"
            and output["installment"]["state"] == "unknown"
            and not any(v["tokenHandling"]["assignedInstallments"] for _, v in parsed)):
        for key in ("generation", "installment"):
            output[key].update(value="1.0", state="inferred",
                sources=[{"field": "identity_policy", "policy": "disney_infinity_unnumbered_is_1.0",
                          "basis": "Operator-approved unnumbered first-generation convention"}])
    result = {key: field["value"] for key, field in output.items()}
    result.update(fields=output, installmentNormalized=result["installment"], confidenceKind="uncalibrated_parser_heuristic",
                  tokenHandling=[{"source":r["source"],**v["tokenHandling"]} for r,v in parsed],
                  assignedMetadata=assigned, includedContents=[c for item in assigned for c in item.get("contents",[])])
    return result


@lru_cache(maxsize=2048)
def _exact_reference(asin, title, system, serialized_catalog):
    return phase3_side(title, "amazon", catalog=json.loads(serialized_catalog), platform=system)


def evaluated_identity(amazon_title, ebay_title, seed, evidence):
    asin = str(seed.get("asin") or "").upper()
    catalog = catalog_identity(seed)
    verified_catalog = catalog if asin and str(catalog.get("asin") or "").upper() == asin else {}
    amazon = deepcopy(_exact_reference(asin, str(amazon_title or ""), seed.get("system"), json.dumps(verified_catalog, sort_keys=True)))
    ebay = phase3_side(ebay_title, "ebay", evidence=evidence)
    result = phase3_comparison(amazon, ebay)
    result["reference"] = {"asin": asin or None, "catalogAccepted": bool(verified_catalog),
                           "catalogRejected": bool(catalog and not verified_catalog), "version": PHASE3_VERSION}
    result["materialEvidenceHash"] = evidence_hash({"asin": asin, "amazonTitle": amazon_title,
        "catalog": verified_catalog, "ebayTitle": ebay_title, "evidence": evidence})
    return result


def phase3_comparison(amazon, ebay):
    comparisons = {}
    for key in IDENTITY_FIELDS:
        left, right = amazon["fields"][key], ebay["fields"][key]
        if any(v["state"] == "conflicting_sources" for v in (left, right)):
            outcome, reason = "review", "Strong sources disagree within a side"
        elif left["state"] in {"unknown", "not_applicable"} or right["state"] in {"unknown", "not_applicable"}:
            outcome, reason = "unknown", "Omitted information is not a contradiction or a pass"
        elif str(left["value"]).casefold() == str(right["value"]).casefold() or key == "platform" and platforms_compatible(str(left["value"]), str(right["value"])):
            outcome, reason = "match", "Supported normalized values agree"
        else:
            outcome = "conflict" if key in {"coreGame", "coreProduct", "installment", "generation", "theme", "edition", "packageType", "platform"} else "review"
            reason = "Supported values differ"
        relation = "explicit_conflict" if outcome == "conflict" else "same" if outcome == "match" else "compatible_omission" if outcome == "unknown" and bool(left["value"]) != bool(right["value"]) else "unknown"
        comparisons[key] = {"field": key, "result": outcome, "relation": relation, "amazon": left["value"], "ebay": right["value"], "reason": reason,
                            "amazonEvidenceRef": "amazon.fields." + key, "ebayEvidenceRef": "ebay.fields." + key}
    outcomes = {c["result"] for c in comparisons.values()}
    verdict = "non-match" if "conflict" in outcomes else "needs_review" if "review" in outcomes else "match" if comparisons["coreGame"]["result"] == "match" else "unknown"
    unresolved_required = [k for k in ("edition", "packageType", "generation", "installment") if bool(amazon[k]) != bool(ebay[k])]
    if verdict == "match" and unresolved_required:
        verdict = "needs_review"
    result = {"match": "match", "non-match": "conflict", "needs_review": "review", "unknown": "unknown"}[verdict]
    decision = {"version": PHASE3_VERSION, "productIdentityVerdict": verdict, "comparisons": comparisons, "policyRole": "shadow_only"}
    return {"version": PHASE3_VERSION, "amazon": amazon, "ebay": ebay, "comparisons": comparisons,
            "evidenceDecision": decision, "result": result, "hard_block": result == "conflict",
            "conflicts": [k for k, v in comparisons.items() if v["result"] == "conflict"],
            "reason": "Unresolved identity detail on one side: " + ", ".join(unresolved_required) if verdict == "needs_review" and unresolved_required else reason_for_result(comparisons)}
