"""Canonical video-game identity parsing and comparison for sourcing."""

from __future__ import annotations

import re
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
) -> dict[str, Any]:
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
    comparisons = compare_identities(amazon_identity, ebay_identity)
    overall = overall_result(comparisons)
    reason = reason_for_result(comparisons)
    return {
        "version": "video_game_identity_v1",
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
    return identity


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
