"""Deterministic sourcing match rules for Amazon ASIN -> eBay listing review."""

from __future__ import annotations

import re
from typing import Any

from system_detection import SYSTEM_ALIASES, detect_system_from_title, normalize_system
from title_cleaning import clean_marketplace_title_for_search
from video_game_identity import build_identity_comparison


RECOMMENDATION_RANK = {
    "Strong Match": 4,
    "Probable Match": 3,
    "Review": 2,
    "Probable Non-Match": 1,
    "Blocked": 0,
}

TITLE_OVERLAP_STOP_WORDS = {
    "3ds",
    "360",
    "and",
    "brand",
    "compatible",
    "collection",
    "edition",
    "esrb",
    "fast",
    "for",
    "game",
    "games",
    "hd",
    "mac",
    "microsoft",
    "new",
    "nintendo",
    "one",
    "pc",
    "playstation",
    "ps",
    "ps2",
    "ps3",
    "ps4",
    "ps5",
    "psp",
    "sealed",
    "series",
    "shipping",
    "sony",
    "standard",
    "switch",
    "the",
    "video",
    "wii",
    "wiiu",
    "windows",
    "xbox",
    "xb1",
    "xbone",
}

DIGITAL_BLOCK_TERMS = {
    "account",
    "account service",
    "add-on content",
    "base game not included",
    "bonus code",
    "boost",
    "carry",
    "car pack dlc",
    "double xp",
    "digital code",
    "digital content",
    "dlc",
    "download",
    "download code",
    "email delivery",
    "eridium",
    "gamesharing",
    "gems",
    "in-game",
    "item drop",
    "journey to batuu",
    "key code",
    "keratin",
    "kibble",
    "max cash",
    "message before purch",
    "message delivery",
    "modded",
    "mythic",
    "operator skin",
    "recovery service",
    "global use",
    "legal max",
    "max armor",
    "mindwipe tonic",
    "qurio augment",
    "rune",
    "runes",
    "pve official",
    "dedi full",
    "season 13",
    "season 14",
    "show packs",
    "song pack",
    "skin",
    "star wars bundle",
    "steam",
    "unlock all service",
    "vault card",
    "vpn",
    "will send",
}

INCOMPLETE_BLOCK_TERMS = {
    "art only",
    "art cards only",
    "artwork only",
    "booklet only",
    "cards only",
    "case only",
    "case and cover insert only",
    "case & middle tray only",
    "cartridge only",
    "cover art",
    "cover insert only",
    "damaged case",
    "disc only",
    "game case",
    "instruction manual",
    "manual missing",
    "manual only",
    "middle tray only",
    "missing manual",
    "no disc",
    "no game",
    "not a game",
    "no manual",
    "replacement case",
    "replacement insert",
    "replacement insert & case",
    "replacement cover",
    "steelbook only",
    "unsealed",
    "unsealed never played",
    "used with box",
}

NOT_GAME_BLOCK_TERMS = {
    "adapter converter",
    "amiibo",
    "backpack",
    "battery cover",
    "blind bag",
    "button pin",
    "cable",
    "cake topper",
    "card lot",
    "carrying case",
    "charm",
    "collectible figure",
    "construx",
    "controller",
    "crossbow",
    "decal",
    "diecast",
    "drawstring",
    "element dust",
    "enamel pin",
    "empty steelbook",
    "faceplate",
    "figure",
    "fridge magnet",
    "game art keychain",
    "guide book",
    "helmet",
    "hot wheels",
    "iron on patch",
    "key chain",
    "keychain",
    "kids meal",
    "lenticular card",
    "magazine",
    "magnetic",
    "mediabook",
    "microfiber cleaner",
    "minifig",
    "panini",
    "paperback",
    "party favors",
    "pineapple punch-out",
    "pedal",
    "pin",
    "pin badge",
    "plush",
    "plushie",
    "power disc",
    "power level",
    "protector",
    "puzzle",
    "poster",
    "print ad",
    "replacement case",
    "scrapbook",
    "scrapbooking",
    "safety stud",
    "soundtrack",
    "snakes",
    "sew on patch",
    "skin decal",
    "statue",
    "sticker",
    "strategy guide",
    "thumb grip",
    "topps",
    "tote bag",
    "toy",
    "trading card",
    "vehicle",
}

REGION_BLOCK_TERMS = {
    "australian version",
    "cero",
    "european version",
    "french version",
    "german version",
    "italian version",
    "japanese version",
    "japan version",
    "ntsc-j",
    "pal",
    "pegi",
    "region 2",
    "region 3",
    "spanish version",
    "uk import",
    "uk version",
    "usk",
}

EDITION_SIGNALS = {
    "collector": {"collector", "collector's edition", "collectors edition"},
    "deluxe": {"deluxe", "deluxe edition"},
    "gold": {"gold", "gold edition"},
    "greatest_hits": {"greatest hits"},
    "limited": {"limited", "limited edition"},
    "platinum_hits": {"platinum hits"},
    "premium": {"premium", "premium edition"},
    "player_choice": {"player's choice", "players choice"},
    "special": {"special edition"},
    "steelbook": {"steelbook", "steel book"},
    "ultimate": {"ultimate", "ultimate edition"},
}

NON_GAME_CATEGORY_IDS = {
    "11104",
    "11232",
    "15032",
    "171833",
    "183050",
    "183454",
    "182170",
    "38583",
    "45110",
    "58543",
    "73839",
}

GAME_SOFTWARE_CATEGORY_IDS = {"139973"}

UNSUPPORTED_CANDIDATE_SYSTEMS = {"DS"}

NON_GAME_CATEGORY_TERMS = {
    "accessories",
    "action figures",
    "battery cover",
    "box art",
    "books",
    "books & magazines",
    "cable",
    "cake toppers",
    "carrying cases",
    "cleaners",
    "collectibles",
    "controllers",
    "decals",
    "drum sticks",
    "faceplates",
    "manuals",
    "microfiber",
    "patches",
    "pedals",
    "plush",
    "power discs",
    "puzzles",
    "replacement parts",
    "sports mem",
    "sports trading cards",
    "stickers",
    "strategy guides",
    "trading card",
    "toys to life",
}

BUNDLE_REVIEW_TERMS = {"bundle", "bundled", "with game", "includes game", "game included"}

ANNUAL_IDENTITY_PATTERNS = [
    ("nba", re.compile(r"\bnba\s+2k(?P<value>\d{1,2})\b")),
    ("mlb", re.compile(r"\b(?:mlb|major league baseball)\s+2k(?P<value>\d{1,2})\b")),
    ("wwe", re.compile(r"\bwwe\s+2k(?P<value>\d{1,2})\b")),
    ("all_pro_football", re.compile(r"\ball\s+pro\s+football\s+2k(?P<value>\d{1,2})\b")),
    ("madden", re.compile(r"\bmadden\s+nfl\s+(?P<value>\d{2})\b")),
    ("fifa", re.compile(r"\bfifa\s+(?P<value>\d{2})\b")),
    ("nhl", re.compile(r"\bnhl\s+(?P<value>\d{2})\b")),
    ("ncaa_football", re.compile(r"\bncaa\s+football\s+(?P<value>\d{2})\b")),
    ("tiger_woods", re.compile(r"\btiger\s+woods\s+pga\s+tour\s+(?P<value>\d{2})\b")),
    ("just_dance", re.compile(r"\bjust\s+dance\s+(?P<value>(?:19|20)\d{2}|\d{1,2})\b")),
]

GAME_INSTALLMENT_PATTERNS = [
    ("final_fantasy", re.compile(r"\bfinal\s+fantasy\s+(?P<value>xiv|14|xiii|13|xii|12|xv|15|xvi|16|[2-9])\b")),
    ("wipeout", re.compile(r"\b(?:abc'?s\s+)?wipeout\s+(?P<value>[2-9])\b")),
    ("rock_band", re.compile(r"\brock\s+band\s+(?P<value>[2-4])\b")),
    ("sports_champions", re.compile(r"\bsports\s+champions\s+(?P<value>[2-9])\b")),
    ("jackbox_party_pack", re.compile(r"\b(?:the\s+)?jackbox\s+(?:party\s+)?pack\s+(?P<value>[2-9]|[1-9][0-9])\b")),
    ("dance_central", re.compile(r"\bdance\s+central\s+(?P<value>[2-9])\b")),
    ("sniper_elite", re.compile(r"\bsniper\s+elite\s+(?P<value>[2-9])\b")),
    ("devil_may_cry", re.compile(r"\bdevil\s+may\s+cry\s+(?P<value>[2-9])\b")),
    ("far_cry", re.compile(r"\bfar\s+cry\s+(?P<value>[2-9])\b")),
    ("mercenaries", re.compile(r"\bmercenaries\s+(?P<value>[2-9])\b")),
]

BASE_IDENTITY_PATTERNS = {
    "rock_band": re.compile(r"\brock\s+band\b"),
    "rock_band_track_pack": re.compile(r"\brock\s+band\s+(?:classic\s+rock\s+)?track\s+pack\b|\brock\s+band\s+track\s+pack\s+classic\s+rock\b"),
    "final_fantasy": re.compile(r"\bfinal\s+fantasy\b"),
    "wipeout": re.compile(r"\b(?:abc'?s\s+)?wipeout\b"),
    "sports_champions": re.compile(r"\bsports\s+champions\b"),
    "jackbox_party_pack": re.compile(r"\b(?:the\s+)?jackbox\s+(?:party\s+)?pack\b"),
}

BASE_IDENTITY_EXCLUSIONS = {
    "rock_band": re.compile(r"\b(?:track\s+pack|beatles|ac/dc|country\s+track|vol(?:ume)?\.?\s*\d)\b"),
    "final_fantasy": re.compile(r"\bfinal\s+fantasy\s+(?:xiv|14|xiii|13|xii|12|xv|15|xvi|16|[2-9])\b"),
    "wipeout": re.compile(r"\b(?:abc'?s\s+)?wipeout\s+[2-9]\b"),
}

ASPECT_NAMES = {
    "platform": "platform",
    "game name": "game_name",
    "region code": "region_code",
    "country of origin": "country_of_origin",
    "format": "format",
    "type": "type",
    "features": "features",
    "release year": "release_year",
}

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

EDITION_DISPLAY_SIGNALS = [
    ("Complete Edition", re.compile(r"\bcomplete\s+edition\b")),
    ("Collector's Edition", re.compile(r"\bcollector'?s?\s+edition\b")),
    ("Deluxe Edition", re.compile(r"\bdeluxe\s+edition\b")),
    ("Gold Edition", re.compile(r"\bgold\s+edition\b")),
    ("Greatest Hits", re.compile(r"\bgreatest\s+hits\b")),
    ("Limited Edition", re.compile(r"\blimited\s+edition\b")),
    ("Platinum Hits", re.compile(r"\bplatinum\s+hits\b")),
    ("Premium Edition", re.compile(r"\bpremium\s+edition\b")),
    ("Player's Choice", re.compile(r"\bplayer'?s?\s+choice\b")),
    ("Special Edition", re.compile(r"\bspecial\s+edition\b")),
    ("Steelbook", re.compile(r"\bsteel\s*book\b")),
    ("Ultimate Edition", re.compile(r"\bultimate\s+edition\b")),
]

REGION_DISPLAY_SIGNALS = [
    ("NTSC-U/C", re.compile(r"\bntsc[-\s]?u/?c?\b|\busa\b|\bus\s+version\b|\bnorth\s+american\b")),
    ("NTSC-J", re.compile(r"\bntsc[-\s]?j\b|\bjapan(?:ese)?\b")),
    ("PAL", re.compile(r"\bpal\b|\bpegi\b|\buk\s+(?:import|version)\b|\beuropean\s+version\b")),
]


def evaluate_static_match_rules(
    candidate: dict[str, Any],
    seed: dict[str, Any],
    *,
    excluded_keywords: list[str] | None = None,
    allowed_item_location_countries: list[str] | None = None,
) -> dict[str, Any]:
    amazon_title = str(seed.get("amazon_title") or "")
    ebay_title = str(candidate.get("ebay_title") or "")
    evidence = normalize_candidate_evidence(candidate)
    raw_json = candidate.get("raw_ebay_json") or {}
    combined_text = evidence["searchable_text"]
    description_text = str(evidence.get("description") or "").casefold()
    title_text = " ".join([ebay_title, str(candidate.get("condition") or "")]).casefold()

    flags: list[str] = []
    hard_blocks: list[str] = []
    warnings: list[str] = []
    score_adjustment = 0
    recommendation = "Review"

    platform = platform_rule(amazon_title, ebay_title, seed, evidence)
    if platform["result"] == "blocked":
        hard_blocks.append(platform["reason"])
        flags.append(f"Blocked: {platform['reason']}")
        score_adjustment -= 35
        recommendation = "Blocked"
    elif platform["result"] == "review":
        warnings.append(platform["reason"])
        flags.append(platform["reason"])
        score_adjustment -= 10
        recommendation = lower_recommendation(recommendation, "Probable Non-Match")

    title_overlap = title_overlap_rule(amazon_title, ebay_title)
    if title_overlap["result"] == "blocked":
        hard_blocks.append(title_overlap["reason"])
        flags.append(f"Blocked: {title_overlap['reason']}")
        score_adjustment -= 30
        recommendation = "Blocked"
    elif title_overlap["result"] == "review":
        warnings.append(title_overlap["reason"])
        flags.append(title_overlap["reason"])
        score_adjustment -= 12
        recommendation = lower_recommendation(recommendation, "Probable Non-Match")

    excluded = keyword_hits(combined_text, excluded_keywords or [])
    if excluded:
        hard_blocks.append(f"excluded keyword: {', '.join(excluded[:3])}")
        flags.append(f"Blocked: excluded keyword: {', '.join(excluded[:3])}")
        score_adjustment -= 30
        recommendation = "Blocked"

    digital = keyword_hits(combined_text, sorted(DIGITAL_BLOCK_TERMS))
    if digital:
        hard_blocks.append(f"digital/download listing: {', '.join(digital[:3])}")
        flags.append(f"Blocked: digital/download listing: {', '.join(digital[:3])}")
        score_adjustment -= 35
        recommendation = "Blocked"

    incomplete = incomplete_hits(title_text, description_text)
    not_game = keyword_hits(title_text, sorted(NOT_GAME_BLOCK_TERMS))
    structured_not_game = structured_not_game_hits(evidence)
    for hit in structured_not_game:
        if hit not in not_game:
            not_game.append(hit)
    if incomplete:
        hard_blocks.append(f"incomplete listing: {', '.join(incomplete[:3])}")
        flags.append(f"Blocked: incomplete listing: {', '.join(incomplete[:3])}")
        score_adjustment -= 30
        recommendation = "Blocked"
    if not_game:
        hard_blocks.append(f"accessory/not game: {', '.join(not_game[:3])}")
        flags.append(f"Blocked: accessory/not game: {', '.join(not_game[:3])}")
        score_adjustment -= 30
        recommendation = "Blocked"

    region = keyword_hits(combined_text, sorted(REGION_BLOCK_TERMS))
    if region:
        hard_blocks.append(f"non-North-American version signal: {', '.join(region[:3])}")
        flags.append(f"Blocked: non-North-American version signal: {', '.join(region[:3])}")
        score_adjustment -= 30
        recommendation = "Blocked"

    category = category_rule(raw_json, evidence)
    if category["result"] == "blocked":
        hard_blocks.append(category["reason"])
        flags.append(f"Blocked: {category['reason']}")
        score_adjustment -= 30
        recommendation = "Blocked"
    elif category["result"] == "review":
        warnings.append(category["reason"])
        flags.append(category["reason"])
        score_adjustment -= 12
        recommendation = lower_recommendation(recommendation, "Review")

    game_name = game_name_rule(amazon_title, evidence)
    if game_name["result"] == "blocked":
        hard_blocks.append(game_name["reason"])
        flags.append(f"Blocked: {game_name['reason']}")
        score_adjustment -= 30
        recommendation = "Blocked"
    elif game_name["result"] == "review":
        warnings.append(game_name["reason"])
        flags.append(game_name["reason"])
        score_adjustment -= 12
        recommendation = lower_recommendation(recommendation, "Review")

    numeric = numeric_identity_rule(amazon_title, ebay_title, evidence)
    if numeric["result"] == "blocked":
        hard_blocks.append(numeric["reason"])
        flags.append(f"Blocked: {numeric['reason']}")
        score_adjustment -= 30
        recommendation = "Blocked"
    elif numeric["result"] == "review":
        warnings.append(numeric["reason"])
        flags.append(numeric["reason"])
        score_adjustment -= 12
        recommendation = lower_recommendation(recommendation, "Review")

    edition = edition_rule(amazon_title, ebay_title, evidence)
    if edition["result"] == "blocked":
        hard_blocks.append(edition["reason"])
        flags.append(f"Blocked: {edition['reason']}")
        score_adjustment -= 30
        recommendation = "Blocked"
    elif edition["result"] == "review":
        warnings.append(edition["reason"])
        flags.append(edition["reason"])
        score_adjustment -= 15
        recommendation = lower_recommendation(recommendation, "Probable Non-Match")

    delivery = delivery_rule(raw_json)
    if delivery["result"] == "blocked":
        hard_blocks.append(delivery["reason"])
        flags.append(f"Blocked: {delivery['reason']}")
        score_adjustment -= 30
        recommendation = "Blocked"

    country = candidate.get("item_location_country")
    allowed_countries = allowed_item_location_countries or []
    location = {
        "item_location_country": country,
        "allowed_countries": allowed_countries,
        "result": "pass",
    }
    if allowed_countries and country and country not in allowed_countries:
        reason = "non-US item location"
        location["result"] = "blocked"
        hard_blocks.append(reason)
        flags.append(f"Blocked: {reason}")
        score_adjustment -= 30
        recommendation = "Blocked"

    identity_comparison = build_identity_comparison(
        amazon_title=amazon_title,
        ebay_title=ebay_title,
        seed=seed,
        evidence=evidence,
    )
    if identity_comparison.get("hard_block"):
        reason = f"video game identity conflict: {identity_comparison.get('reason')}"
        hard_blocks.append(reason)
        flags.append(f"Blocked: {reason}")
        score_adjustment -= 40
        recommendation = "Blocked"
    elif identity_comparison.get("result") == "review":
        warnings.append(str(identity_comparison.get("reason") or "video game identity requires review"))
        score_adjustment -= 12
        recommendation = lower_recommendation(recommendation, "Review")

    derived_identity = dict(identity_comparison)
    if identity_comparison.get("result") == "conflict":
        conflicts = set(identity_comparison.get("conflicts") or [])
        if "installment" in conflicts:
            derived_identity["result"] = "installment_conflict"
        elif "platform" in conflicts:
            derived_identity["result"] = "platform_conflict"
        elif "edition" in conflicts:
            derived_identity["result"] = "edition_conflict"

    if not hard_blocks and not warnings and title_overlap.get("shared_tokens"):
        recommendation = "Probable Match"

    return {
        "recommendation": recommendation,
        "hard_blocks": hard_blocks,
        "warnings": warnings,
        "score_adjustment": score_adjustment,
        "flags": flags,
        "platform_rule": platform,
        "title_overlap": title_overlap,
        "excluded_keywords": {"hits": excluded, "result": "blocked" if excluded else "pass"},
        "digital_download": {"hits": digital, "result": "blocked" if digital else "pass"},
        "incomplete_listing": {"hits": incomplete, "result": "blocked" if incomplete else "pass"},
        "not_game": {"hits": not_game, "result": "blocked" if not_game else "pass"},
        "region": {"hits": region, "result": "blocked" if region else "pass"},
        "normalized_evidence": evidence,
        "game_name": game_name,
        "numeric_identity": numeric,
        "edition_version": edition,
        "category": category,
        "delivery": delivery,
        "location": location,
        "identity_comparison": identity_comparison,
        "derived_identity": derived_identity,
    }


def normalize_candidate_evidence(candidate: dict[str, Any]) -> dict[str, Any]:
    raw_json = candidate.get("raw_ebay_json") or {}
    aspects = normalized_aspects(raw_json.get("localizedAspects") or [])
    categories = normalized_categories(raw_json)
    image_urls = normalized_image_urls(candidate, raw_json)
    subtitle = raw_json.get("subtitle")
    short_description = raw_json.get("shortDescription")
    description = raw_json.get("description")
    searchable_parts = [
        candidate.get("ebay_title"),
        candidate.get("condition"),
        subtitle,
        short_description,
        description,
    ]
    for name, values in aspects.items():
        searchable_parts.append(name)
        searchable_parts.extend(values)
    searchable_text = " ".join(str(part or "") for part in searchable_parts).casefold()
    return {
        "aspects": aspects,
        "platform_values": aspects.get("platform") or [],
        "game_name_values": aspects.get("game_name") or [],
        "region_code_values": aspects.get("region_code") or [],
        "country_of_origin_values": aspects.get("country_of_origin") or [],
        "format_values": aspects.get("format") or [],
        "type_values": aspects.get("type") or [],
        "features_values": aspects.get("features") or [],
        "release_year_values": aspects.get("release_year") or [],
        "category_ids": categories["ids"],
        "category_names": categories["names"],
        "category_path": categories["path"],
        "subtitle": subtitle,
        "description": " ".join(str(value or "") for value in [short_description, description]).strip(),
        "primary_image_url": candidate.get("ebay_image_url") or ((raw_json.get("image") or {}).get("imageUrl")),
        "image_urls": image_urls,
        "searchable_text": searchable_text,
    }


def derived_game_identity(
    *,
    amazon_title: str,
    ebay_title: str,
    seed: dict[str, Any],
    evidence: dict[str, Any],
    platform: dict[str, Any],
    numeric: dict[str, Any],
    edition: dict[str, Any],
    region: list[str],
    incomplete: list[str],
    digital: list[str],
) -> dict[str, Any]:
    ebay_identity_title = first_text(evidence.get("game_name_values")) or ebay_title
    raw_context = seed.get("raw_context_json") if isinstance(seed.get("raw_context_json"), dict) else {}
    catalog_identity = raw_context.get("amazon_catalog_identity") if isinstance(raw_context.get("amazon_catalog_identity"), dict) else {}
    amazon = parse_game_identity(
        amazon_title,
        platform=catalog_identity.get("normalized_platform") or platform.get("seed_system"),
        explicit_region=first_text(catalog_identity.get("normalized_region"), seed.get("region"), raw_context.get("region")),
        incomplete_hits=[],
        digital_hits=[],
    )
    if catalog_identity.get("normalized_edition"):
        amazon["edition"] = catalog_identity.get("normalized_edition")
    ebay = parse_game_identity(
        ebay_identity_title,
        fallback_text=ebay_title,
        platform=platform.get("candidate_system"),
        explicit_region=first_text(evidence.get("region_code_values"), evidence.get("country_of_origin_values")),
        incomplete_hits=incomplete,
        digital_hits=digital,
    )
    result = "pass"
    conflicts: list[str] = []
    comparison = numeric.get("comparison") if isinstance(numeric.get("comparison"), dict) else {}
    if comparison.get("blocked") or comparison.get("review"):
        result = "installment_conflict"
        conflicts.append("installment")
    if platform.get("result") == "blocked":
        result = "platform_conflict"
        conflicts.append("platform")
    if edition.get("result") == "blocked":
        result = "edition_conflict"
        conflicts.append("edition")
    if region:
        result = "region_conflict"
        conflicts.append("region")
    return {
        "amazon": amazon,
        "ebay": ebay,
        "result": result,
        "conflicts": conflicts,
        "source": {
            "amazon": "catalog_attributes" if catalog_identity else "amazon_title",
            "ebay": "ebay_game_name" if first_text(evidence.get("game_name_values")) else "ebay_title",
        },
    }


def parse_game_identity(
    title: Any,
    *,
    fallback_text: Any = None,
    platform: Any = None,
    explicit_region: Any = None,
    incomplete_hits: list[str] | None = None,
    digital_hits: list[str] | None = None,
) -> dict[str, Any]:
    text = str(title or fallback_text or "")
    search_text = " ".join([text, str(fallback_text or "")])
    normalized = normalize_numeric_text(search_text)
    family, raw_installment, installment = first_installment(normalized)
    core_game = core_game_name(text, family)
    return {
        "coreGame": core_game,
        "installment": installment_display(raw_installment, installment),
        "installmentNormalized": installment,
        "edition": edition_display(search_text),
        "platform": platform_display(normalize_system(str(platform or "")) or detect_system_from_title(search_text)),
        "region": normalize_region(explicit_region) or region_display(search_text),
        "packageContents": package_contents_display(search_text),
        "completeness": "Incomplete" if incomplete_hits else "Complete",
        "digitalPhysical": "Digital" if digital_hits else "Physical",
    }


def first_installment(normalized: str) -> tuple[str | None, str | None, str | None]:
    for family, pattern in GAME_INSTALLMENT_PATTERNS:
        match = pattern.search(normalized)
        if match:
            raw = str(match.group("value"))
            return family, raw.upper() if raw in ROMAN_NUMERAL_VALUES else raw, normalize_installment_value(raw)
    return None, None, None


def normalize_installment_value(value: Any) -> str:
    text = str(value or "").strip().casefold()
    return ROMAN_NUMERAL_VALUES.get(text, text.lstrip("0") or text)


def installment_display(raw: str | None, normalized: str | None) -> str:
    if not normalized:
        return "None / Base title"
    if raw and raw.casefold() in ROMAN_NUMERAL_VALUES:
        return f"{raw.upper()} / {normalized}"
    return raw or normalized


def core_game_name(title: Any, family: str | None) -> str:
    normalized_title = normalize_numeric_text(title)
    if "rock band" in normalized_title and "track pack" in normalized_title:
        return "Rock Band Track Pack: Classic Rock" if "classic rock" in normalized_title else "Rock Band Track Pack"
    if family == "rock_band_track_pack":
        return "Rock Band Track Pack: Classic Rock" if "classic rock" in normalized_title else "Rock Band Track Pack"
    if family == "rock_band":
        return "Rock Band"
    if family == "final_fantasy":
        return "Final Fantasy"
    if family == "wipeout":
        return "Wipeout"
    cleaned = remove_identity_noise(str(title or ""))
    return title_case_game(cleaned) or "Unknown"


def remove_identity_noise(value: str) -> str:
    text = normalize_numeric_text(value)
    for alias_list in SYSTEM_ALIASES.values():
        for alias in alias_list:
            text = re.sub(rf"(?<![a-z0-9]){re.escape(normalize_numeric_text(alias))}(?![a-z0-9])", " ", text)
    for _, pattern in EDITION_DISPLAY_SIGNALS:
        text = pattern.sub(" ", text)
    text = re.sub(r"\b(?:brand|new|sealed|video|game|standard|edition|for)\b", " ", text)
    text = re.sub(r"\b(?:19|20)\d{2}\b", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def title_case_game(value: str) -> str:
    acronyms = {"ps", "psp", "xbox", "wii", "u", "ds", "3ds", "pc", "xiv"}
    words = []
    for word in value.split():
        words.append(word.upper() if word in acronyms else word.capitalize())
    return " ".join(words)


def edition_display(value: Any) -> str:
    text = normalize_numeric_text(value)
    for label, pattern in EDITION_DISPLAY_SIGNALS:
        if pattern.search(text):
            return label
    return "Base / Standard"


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


def normalize_region(value: Any) -> str | None:
    text = " ".join(str(item or "") for item in value) if isinstance(value, list) else str(value or "")
    return region_display(text)


def region_display(value: Any) -> str | None:
    text = normalize_numeric_text(value)
    for label, pattern in REGION_DISPLAY_SIGNALS:
        if pattern.search(text):
            return label
    return None


def package_contents_display(value: Any) -> str:
    text = normalize_numeric_text(value)
    if "track pack" in text:
        return "Track pack"
    if any(term in text for term in ("bundle", "includes", "with game")):
        return "Bundle"
    return "Standard physical software"


def first_text(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, list):
            for item in value:
                text = str(item or "").strip()
                if text:
                    return text
        else:
            text = str(value or "").strip()
            if text:
                return text
    return None


def normalized_aspects(localized_aspects: Any) -> dict[str, list[str]]:
    output: dict[str, list[str]] = {}
    if not isinstance(localized_aspects, list):
        return output
    for aspect in localized_aspects:
        if not isinstance(aspect, dict):
            continue
        raw_name = str(aspect.get("name") or "").strip()
        name = ASPECT_NAMES.get(raw_name.casefold(), raw_name.casefold())
        value = aspect.get("value")
        values = value if isinstance(value, list) else [value]
        for item in values:
            text = str(item or "").strip()
            if not text:
                continue
            output.setdefault(name, [])
            if text not in output[name]:
                output[name].append(text)
    return output


def normalized_categories(raw_json: dict[str, Any]) -> dict[str, list[str]]:
    ids: list[str] = []
    names: list[str] = []
    for category in raw_json.get("categories") or []:
        if not isinstance(category, dict):
            continue
        category_id = str(category.get("categoryId") or "").strip()
        category_name = str(category.get("categoryName") or category.get("name") or "").strip()
        if category_id and category_id not in ids:
            ids.append(category_id)
        if category_name and category_name not in names:
            names.append(category_name)
    for key in ("categoryPath", "categoryPathNames"):
        value = raw_json.get(key)
        if isinstance(value, str):
            for part in re.split(r"\s*[>/|]\s*", value):
                part = part.strip()
                if part and part not in names:
                    names.append(part)
    return {"ids": ids, "names": names, "path": names}


def normalized_image_urls(candidate: dict[str, Any], raw_json: dict[str, Any]) -> list[str]:
    urls = []
    for value in [
        candidate.get("ebay_image_url"),
        (raw_json.get("image") or {}).get("imageUrl") if isinstance(raw_json.get("image"), dict) else None,
    ]:
        if value and value not in urls:
            urls.append(value)
    for key in ("thumbnailImages", "additionalImages"):
        for image in raw_json.get(key) or []:
            if isinstance(image, dict):
                url = image.get("imageUrl")
                if url and url not in urls:
                    urls.append(url)
    return urls


def searchable_candidate_text(candidate: dict[str, Any]) -> str:
    return str(normalize_candidate_evidence(candidate).get("searchable_text") or "")


def platform_rule(
    amazon_title: str,
    ebay_title: str,
    seed: dict[str, Any],
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    evidence = evidence or normalize_candidate_evidence({})
    seed_system, seed_source = resolve_seed_system(seed, amazon_title)
    aspect_systems = systems_from_values(evidence.get("platform_values") or [])
    title_systems = detect_all_systems(ebay_title)
    ebay_systems = aspect_systems or title_systems
    ebay_primary_system = ebay_systems[0] if ebay_systems else None
    ebay_source = "item_specifics_platform" if aspect_systems else "ebay_title" if title_systems else None

    result = "unknown"
    reason = "No platform signal available"
    unsupported_systems = [system for system in ebay_systems if system in UNSUPPORTED_CANDIDATE_SYSTEMS]
    if unsupported_systems:
        result = "blocked"
        reason = f"unsupported sourcing platform: {', '.join(unsupported_systems)}"
    elif seed_system and not ebay_systems:
        result = "review"
        reason = "Candidate listing has no detectable platform"
    elif seed_system and ebay_systems and xbox_one_series_compatible(seed_system, ebay_systems):
        result = "pass"
        reason = "Xbox One / Xbox Series cross-generation-compatible platform"
    elif seed_system and ebay_systems and seed_system not in ebay_systems:
        result = "blocked"
        reason = f"platform mismatch: Amazon {seed_system}, eBay {', '.join(ebay_systems)}"
    elif seed_system and len([system for system in ebay_systems if system != seed_system]) > 0:
        result = "review"
        reason = f"candidate lists multiple platforms including {seed_system}"
    elif seed_system and seed_system in ebay_systems:
        result = "pass"
        reason = "Candidate platform matches Amazon platform"

    return {
        "seed_system": seed_system,
        "seed_system_source": seed_source,
        "candidate_system": ebay_primary_system,
        "candidate_systems": ebay_systems,
        "candidate_system_source": ebay_source,
        "candidate_item_specific_platform_values": evidence.get("platform_values") or [],
        "candidate_title_systems": title_systems,
        "result": result,
        "reason": reason,
    }


def xbox_one_series_compatible(seed_system: str | None, ebay_systems: list[str]) -> bool:
    xbox_cross_gen = {"Xbox One", "Xbox Series X", "Xbox Series S"}
    known = {seed_system, *ebay_systems}
    known = {system for system in known if system}
    return bool(known) and known.issubset(xbox_cross_gen)


def resolve_seed_system(seed: dict[str, Any], amazon_title: str) -> tuple[str | None, str | None]:
    first_class = normalize_system(str(seed.get("system") or ""))
    if first_class:
        return first_class, "seed_system"
    raw_context = seed.get("raw_context_json") or {}
    if isinstance(raw_context, dict):
        inferred = normalize_system(str(raw_context.get("inferred_system") or ""))
        if inferred:
            return inferred, str(raw_context.get("inferred_system_source") or "seed_raw_context")
    title_system = detect_system_from_title(amazon_title)
    if title_system:
        return title_system, "amazon_title"
    return None, None


def systems_from_values(values: list[str]) -> list[str]:
    systems: list[str] = []
    for value in values:
        system = normalize_system(str(value or "")) or detect_system_from_title(str(value or ""))
        if system and system not in systems:
            systems.append(system)
    return suppress_generic_platforms(systems)


def detect_all_systems(title: str | None) -> list[str]:
    if not title:
        return []
    text = title.casefold()
    matches = []
    for canonical, aliases in SYSTEM_ALIASES.items():
        for alias in aliases:
            pattern = rf"(?<![a-z0-9]){re.escape(alias.casefold())}(?![a-z0-9])"
            if re.search(pattern, text):
                matches.append((len(alias), canonical))
                break
    matches.sort(reverse=True)
    ordered = []
    for _, canonical in matches:
        if canonical not in ordered:
            ordered.append(canonical)
    ordered = suppress_generic_platforms(ordered)
    return ordered


def suppress_generic_platforms(systems: list[str]) -> list[str]:
    specific_groups = {
        "Xbox": {"Xbox One", "Xbox 360", "Xbox Series X", "Xbox Series S"},
        "PS": {"PS 2", "PS 3", "PS 4", "PS 5", "PSP", "PS Vita"},
        "Wii": {"Wii U"},
        "Switch": {"Switch 2"},
    }
    present = set(systems)
    suppressed = set()
    for generic, specifics in specific_groups.items():
        if generic in present and present & specifics:
            suppressed.add(generic)
    return [system for system in systems if system not in suppressed]


def title_overlap_rule(amazon_title: Any, ebay_title: Any) -> dict[str, Any]:
    amazon_tokens = meaningful_title_tokens(amazon_title)
    ebay_tokens = meaningful_title_tokens(ebay_title)
    shared = sorted(amazon_tokens & ebay_tokens)
    result = "unknown"
    reason = "No meaningful title tokens available"
    overlap_ratio = 0
    if amazon_tokens and ebay_tokens and not shared:
        result = "blocked"
        reason = "no meaningful title token overlap"
    elif amazon_tokens and ebay_tokens:
        minimum = min(len(amazon_tokens), len(ebay_tokens))
        overlap_ratio = len(shared) / max(minimum, 1)
        if len(shared) == 1 and minimum >= 3:
            result = "review"
            reason = "weak meaningful title overlap"
        else:
            result = "pass"
            reason = "meaningful title overlap present"
    else:
        overlap_ratio = 0
    return {
        "amazon_tokens": sorted(amazon_tokens),
        "ebay_tokens": sorted(ebay_tokens),
        "shared_tokens": shared,
        "overlap_ratio": round(overlap_ratio, 3) if amazon_tokens and ebay_tokens else 0,
        "result": result,
        "reason": reason,
    }


def meaningful_title_tokens(value: Any) -> set[str]:
    cleaned = clean_marketplace_title_for_search(str(value or ""))
    tokens = set()
    for token in re.findall(r"[a-z0-9]+", cleaned.casefold()):
        if len(token) <= 1 or token in TITLE_OVERLAP_STOP_WORDS:
            continue
        if re.fullmatch(r"(?:19|20)\d{2}", token):
            continue
        tokens.add(singular_token(token))
    return tokens


def singular_token(token: str) -> str:
    if len(token) > 4 and token.endswith("s"):
        return token[:-1]
    return token


def keyword_hits(text: str, terms: list[str] | set[str]) -> list[str]:
    hits = []
    normalized = text.casefold()
    for term in terms:
        if not term:
            continue
        term_text = str(term).casefold()
        if " " in term_text or "-" in term_text:
            if term_text in normalized:
                hits.append(str(term))
        elif re.search(rf"(?<![a-z0-9]){re.escape(term_text)}(?![a-z0-9])", normalized):
            hits.append(str(term))
    return sorted(dict.fromkeys(hits))


def incomplete_hits(title_text: str, description_text: str) -> list[str]:
    text = f"{title_text} {description_text}".casefold()
    protected = {"loose disc in case", "loose disc inside", "complete with disc", "disc included"}
    hits = keyword_hits(text, sorted(INCOMPLETE_BLOCK_TERMS))
    if "disc only" in hits and any(phrase in text for phrase in protected):
        hits.remove("disc only")
    return hits


def structured_not_game_hits(evidence: dict[str, Any]) -> list[str]:
    hits: list[str] = []
    for value in evidence.get("type_values") or []:
        text = str(value).casefold()
        if keyword_hits(text, NOT_GAME_BLOCK_TERMS):
            hits.append(f"type: {value}")
    for value in evidence.get("format_values") or []:
        if keyword_hits(str(value).casefold(), DIGITAL_BLOCK_TERMS):
            hits.append(f"format: {value}")
    return hits


def game_name_rule(amazon_title: str, evidence: dict[str, Any]) -> dict[str, Any]:
    game_names = evidence.get("game_name_values") or []
    if not game_names:
        return {"result": "unknown", "reason": "No item-specific Game Name", "game_name_values": []}
    amazon_tokens = meaningful_title_tokens(amazon_title)
    results = []
    for game_name in game_names:
        game_tokens = meaningful_title_tokens(game_name)
        shared = sorted(amazon_tokens & game_tokens)
        results.append({"game_name": game_name, "tokens": sorted(game_tokens), "shared_tokens": shared})
        if amazon_tokens and game_tokens and not shared and not has_bundle_signal(evidence):
            return {
                "result": "blocked",
                "reason": "item-specific Game Name identifies a different game",
                "game_name_values": game_names,
                "comparisons": results,
            }
        if amazon_tokens and game_tokens and len(shared) <= 1 and min(len(amazon_tokens), len(game_tokens)) >= 3 and not has_bundle_signal(evidence):
            return {
                "result": "blocked",
                "reason": "item-specific Game Name identifies a different game",
                "game_name_values": game_names,
                "comparisons": results,
            }
    return {
        "result": "pass",
        "reason": "Item-specific Game Name overlaps or is ambiguous",
        "game_name_values": game_names,
        "comparisons": results,
    }


def numeric_identity_rule(amazon_title: str, ebay_title: str, evidence: dict[str, Any]) -> dict[str, Any]:
    amazon_analysis = numeric_identity_analysis(amazon_title, "amazon_title")
    ebay_title_analysis = numeric_identity_analysis(ebay_title, "ebay_title")
    game_name_analysis = merge_numeric_analyses(
        numeric_identity_analysis(value, "ebay_item_specific_game_name")
        for value in evidence.get("game_name_values") or []
    )
    ebay_analysis = merge_numeric_analyses([ebay_title_analysis, game_name_analysis])
    shared_title_tokens = meaningful_title_tokens(amazon_title) & meaningful_title_tokens(
        " ".join([ebay_title, " ".join(evidence.get("game_name_values") or [])])
    )
    result = "pass"
    reason = "No conflicting numeric product identity"
    comparison = compare_numeric_identity(amazon_analysis, ebay_analysis)
    if shared_title_tokens and comparison["blocked"]:
        result = "blocked"
        reason = comparison["reason"]
    elif shared_title_tokens and comparison["review"]:
        result = "review"
        reason = comparison["reason"]

    return {
        "result": result,
        "reason": reason,
        "normalized_amazon_title": normalize_numeric_text(amazon_title),
        "normalized_ebay_title": normalize_numeric_text(ebay_title),
        "amazon_numeric_tokens": amazon_analysis["numeric_tokens"],
        "ebay_numeric_tokens": ebay_analysis["numeric_tokens"],
        "amazon_identity_numbers": sorted(amazon_analysis["identity_numbers"]),
        "ebay_identity_numbers": sorted(ebay_analysis["identity_numbers"]),
        "amazon_base_identities": sorted(amazon_analysis["base_identities"]),
        "ebay_base_identities": sorted(ebay_analysis["base_identities"]),
        "ignored_amazon_platform_numbers": sorted(amazon_analysis["ignored_platform_numbers"]),
        "ignored_ebay_platform_numbers": sorted(ebay_analysis["ignored_platform_numbers"]),
        "ignored_amazon_release_years": sorted(amazon_analysis["ignored_release_years"]),
        "ignored_ebay_release_years": sorted(ebay_analysis["ignored_release_years"]),
        "ignored_amazon_quantity_numbers": sorted(amazon_analysis["ignored_quantity_numbers"]),
        "ignored_ebay_quantity_numbers": sorted(ebay_analysis["ignored_quantity_numbers"]),
        "ignored_amazon_content_amounts": sorted(amazon_analysis["ignored_content_amounts"]),
        "ignored_ebay_content_amounts": sorted(ebay_analysis["ignored_content_amounts"]),
        "ambiguous_amazon_numbers": sorted(amazon_analysis["ambiguous_numbers"]),
        "ambiguous_ebay_numbers": sorted(ebay_analysis["ambiguous_numbers"]),
        "evidence_sources": sorted(amazon_analysis["evidence_sources"] | ebay_analysis["evidence_sources"]),
        "shared_tokens": sorted(shared_title_tokens),
        "comparison": comparison,
    }


def numeric_identity_analysis(text: Any, source: str) -> dict[str, Any]:
    normalized = normalize_numeric_text(text)
    platform_spans = platform_alias_spans(normalized)
    tokens = numeric_tokens(normalized, source)
    analysis = empty_numeric_analysis()
    analysis["evidence_sources"].add(source)
    for span_start, span_end in platform_spans:
        for number in re.findall(r"\d+", normalized[span_start:span_end]):
            analysis["ignored_platform_numbers"].add(number.lstrip("0") or "0")
    for family, pattern in GAME_INSTALLMENT_PATTERNS:
        for match in pattern.finditer(normalized):
            raw_value = str(match.group("value"))
            value = normalize_installment_value(raw_value)
            if not value:
                continue
            analysis["identity_numbers"].add(value)
            analysis["identity_details"].append(
                {
                    "raw": raw_value,
                    "value": value,
                    "family": family,
                    "classification": "game_installment",
                    "source": source,
                    "context": match.group(0),
                }
            )
    for token in tokens:
        classification = classify_numeric_token(token, normalized, platform_spans)
        token["classification"] = classification
        analysis["numeric_tokens"].append(token)
        value = token["value"]
        if classification in {"game_installment", "annual_sports_identity"}:
            analysis["identity_numbers"].add(value)
            analysis["identity_details"].append(token)
        elif classification == "platform_number":
            analysis["ignored_platform_numbers"].add(value)
        elif classification == "release_year":
            analysis["ignored_release_years"].add(value)
        elif classification in {"package_quantity", "lot_quantity"}:
            analysis["ignored_quantity_numbers"].add(value)
        elif classification == "included_content_amount":
            analysis["ignored_content_amounts"].add(value)
        elif classification == "ambiguous":
            analysis["ambiguous_numbers"].add(value)
    for family, pattern in BASE_IDENTITY_PATTERNS.items():
        if pattern.search(normalized) and not any(detail.get("family") == family for detail in analysis["identity_details"]):
            exclusion = BASE_IDENTITY_EXCLUSIONS.get(family)
            if not exclusion or not exclusion.search(normalized):
                analysis["base_identities"].add(family)
    return analysis


def compare_numeric_identity(amazon: dict[str, Any], ebay: dict[str, Any]) -> dict[str, Any]:
    amazon_by_family = identity_numbers_by_family(amazon)
    ebay_by_family = identity_numbers_by_family(ebay)
    shared_families = sorted((set(amazon_by_family) | amazon["base_identities"]) & (set(ebay_by_family) | ebay["base_identities"]))
    for family in shared_families:
        amazon_values = amazon_by_family.get(family, set())
        ebay_values = ebay_by_family.get(family, set())
        if amazon_values and ebay_values and amazon_values.isdisjoint(ebay_values):
            return {
                "blocked": True,
                "review": False,
                "family": family,
                "amazon_values": sorted(amazon_values),
                "ebay_values": sorted(ebay_values),
                "reason": f"numeric identity mismatch: Amazon {family_label(family)} {', '.join(sorted(amazon_values))}, eBay {family_label(family)} {', '.join(sorted(ebay_values))}",
            }
        if amazon_values and family in ebay["base_identities"]:
            value_text = ", ".join(sorted(amazon_values))
            return {
                "blocked": True,
                "review": False,
                "family": family,
                "amazon_values": sorted(amazon_values),
                "ebay_values": [],
                "reason": f"numeric identity mismatch: Amazon installment {value_text}, eBay base game {family_label(family)}",
            }
        if ebay_values and family in amazon["base_identities"]:
            value_text = ", ".join(sorted(ebay_values))
            return {
                "blocked": True,
                "review": False,
                "family": family,
                "amazon_values": [],
                "ebay_values": sorted(ebay_values),
                "reason": f"numeric identity mismatch: Amazon base game {family_label(family)}, eBay installment {value_text}",
            }
    if amazon["identity_numbers"] and ebay["identity_numbers"] and amazon["identity_numbers"].isdisjoint(ebay["identity_numbers"]):
        return {
            "blocked": False,
            "review": True,
            "family": None,
            "amazon_values": sorted(amazon["identity_numbers"]),
            "ebay_values": sorted(ebay["identity_numbers"]),
            "reason": "numeric identity numbers differ but shared title family is ambiguous",
        }
    return {"blocked": False, "review": False, "family": None, "amazon_values": [], "ebay_values": [], "reason": ""}


def empty_numeric_analysis() -> dict[str, Any]:
    return {
        "numeric_tokens": [],
        "identity_numbers": set(),
        "identity_details": [],
        "base_identities": set(),
        "ignored_platform_numbers": set(),
        "ignored_release_years": set(),
        "ignored_quantity_numbers": set(),
        "ignored_content_amounts": set(),
        "ambiguous_numbers": set(),
        "evidence_sources": set(),
    }


def merge_numeric_analyses(analyses: Any) -> dict[str, Any]:
    merged = empty_numeric_analysis()
    for analysis in analyses:
        if not analysis:
            continue
        merged["numeric_tokens"].extend(analysis.get("numeric_tokens") or [])
        merged["identity_details"].extend(analysis.get("identity_details") or [])
        for key in (
            "identity_numbers",
            "base_identities",
            "ignored_platform_numbers",
            "ignored_release_years",
            "ignored_quantity_numbers",
            "ignored_content_amounts",
            "ambiguous_numbers",
            "evidence_sources",
        ):
            merged[key].update(analysis.get(key) or set())
    return merged


def numeric_tokens(text: str, source: str) -> list[dict[str, Any]]:
    tokens = []
    for match in re.finditer(r"(?<![a-z0-9])(?:2k\d{1,2}|[0-9]+(?:st|nd|rd|th)?)(?![a-z0-9])", text):
        raw = match.group(0)
        value = raw[2:] if raw.startswith("2k") else re.sub(r"(st|nd|rd|th)$", "", raw)
        value = value.lstrip("0") or "0"
        tokens.append(
            {
                "raw": raw,
                "value": f"2k{value}" if raw.startswith("2k") else value,
                "start": match.start(),
                "end": match.end(),
                "source": source,
                "context": text[max(0, match.start() - 32) : match.end() + 32].strip(),
            }
        )
    return tokens


def classify_numeric_token(token: dict[str, Any], text: str, platform_spans: list[tuple[int, int]]) -> str:
    start = token["start"]
    end = token["end"]
    raw = str(token["raw"])
    value = str(token["value"])
    before = text[max(0, start - 32) : start]
    after = text[end : end + 32]
    if any(span_start <= start and end <= span_end for span_start, span_end in platform_spans):
        return "platform_number"
    annual = annual_identity_for_span(text, start, end)
    if annual:
        token["family"] = annual
        return "annual_sports_identity"
    installment = game_installment_for_span(text, start, end)
    if installment:
        token["family"] = installment
        return "game_installment"
    if re.fullmatch(r"(?:19|20)\d{2}", value):
        return "release_year"
    if re.search(r"(lot\s+of|lot|bundle|set\s+of|\()\s*$", before) or re.search(r"^\s*(games?|pcs|pieces?|pack)", after):
        return "lot_quantity" if "lot" in before else "package_quantity"
    if re.search(r"(coins?|minecoins?|points?|v-?bucks?|currency)\b", after) or re.search(r"\b(coins?|minecoins?|points?|v-?bucks?|currency)\s*$", before):
        return "included_content_amount"
    if re.search(r"(anniversary|birthday)", after) or re.search(r"\banniversary\s*$", before) or re.search(r"(st|nd|rd|th)$", raw):
        return "anniversary_number"
    if re.search(r"(sku|model|item\s*#|item\s+number|stock\s*#|stock\s+number|#)\s*$", before):
        return "model_or_sku_number"
    return "ambiguous"


def annual_identity_for_span(text: str, start: int, end: int) -> str | None:
    for family, pattern in ANNUAL_IDENTITY_PATTERNS:
        for match in pattern.finditer(text):
            value_span = match.span("value")
            if (value_span[0] <= start and end <= value_span[1]) or (start <= value_span[0] and value_span[1] <= end):
                return family
    return None


def game_installment_for_span(text: str, start: int, end: int) -> str | None:
    for family, pattern in GAME_INSTALLMENT_PATTERNS:
        for match in pattern.finditer(text):
            value_span = match.span("value")
            if value_span[0] <= start and end <= value_span[1]:
                return family
    return None


def identity_numbers_by_family(analysis: dict[str, Any]) -> dict[str, set[str]]:
    output: dict[str, set[str]] = {}
    for detail in analysis.get("identity_details") or []:
        family = detail.get("family")
        value = detail.get("value")
        if family and value:
            output.setdefault(family, set()).add(str(value))
    return output


def family_label(family: str) -> str:
    return family.replace("_", " ")


def normalize_numeric_text(value: Any) -> str:
    text = str(value or "").casefold()
    text = re.sub(r"[\[\]{}()\"']", " ", text)
    text = re.sub(r"[/|:_\-–—+]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def platform_alias_spans(text: str) -> list[tuple[int, int]]:
    spans = []
    aliases = []
    for alias_list in SYSTEM_ALIASES.values():
        aliases.extend(alias.casefold() for alias in alias_list)
    aliases.extend(["x360", "xb360", "xbox360", "wiiu"])
    for alias in sorted(set(aliases), key=len, reverse=True):
        normalized_alias = normalize_numeric_text(alias)
        if not normalized_alias:
            continue
        pattern = rf"(?<![a-z0-9]){re.escape(normalized_alias)}(?![a-z0-9])"
        spans.extend(match.span() for match in re.finditer(pattern, text))
    return spans


def identity_numbers(value: str) -> dict[str, set[str]]:
    text = value.casefold()
    for aliases in SYSTEM_ALIASES.values():
        for alias in sorted(aliases, key=len, reverse=True):
            text = re.sub(rf"(?<![a-z0-9]){re.escape(alias.casefold())}(?![a-z0-9])", " ", text)
    years = set(re.findall(r"(?<![0-9])(?:19|20)\d{2}(?![0-9])", text))
    numbers = set()
    for match in re.finditer(r"(?<![a-z0-9])(0?[2-9]|[1-9][0-9])(?![a-z0-9])", text):
        before = text[max(0, match.start() - 10) : match.start()]
        after = text[match.end() : match.end() + 10]
        if re.search(r"(pack|pcs|piece|lot|quantity|qty|x)\s*$", before) or re.search(r"^\s*(pack|pcs|piece)", after):
            continue
        numbers.add(match.group(1).lstrip("0") or "0")
    return {"years": years, "numbers": numbers}


def edition_rule(amazon_title: str, ebay_title: str, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    evidence = evidence or {}
    amazon_signals = edition_signals(amazon_title)
    ebay_signals = edition_signals(" ".join([ebay_title, " ".join(evidence.get("features_values") or []), " ".join(evidence.get("type_values") or [])]))
    missing_from_amazon = sorted(ebay_signals - amazon_signals)
    missing_from_ebay = sorted(amazon_signals - ebay_signals)
    result = "pass"
    reason = "Edition/version signals match or are absent"
    if missing_from_amazon or missing_from_ebay:
        result = "blocked"
        reason = "edition/version mismatch signal"
    return {
        "amazon_signals": sorted(amazon_signals),
        "ebay_signals": sorted(ebay_signals),
        "missing_from_amazon": missing_from_amazon,
        "missing_from_ebay": missing_from_ebay,
        "result": result,
        "reason": reason,
    }


def edition_signals(title: str) -> set[str]:
    text = title.casefold()
    signals = set()
    for label, terms in EDITION_SIGNALS.items():
        if keyword_hits(text, terms):
            signals.add(label)
    return signals


def has_bundle_signal(evidence: dict[str, Any]) -> bool:
    return bool(keyword_hits(evidence.get("searchable_text") or "", BUNDLE_REVIEW_TERMS))


def category_rule(raw_json: dict[str, Any], evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    evidence = evidence or normalize_candidate_evidence({"raw_ebay_json": raw_json})
    leaf_category_ids = evidence.get("category_ids") or []
    category_names = evidence.get("category_names") or []
    category_text = " ".join(category_names).casefold()
    if any(category_id in NON_GAME_CATEGORY_IDS for category_id in leaf_category_ids) or keyword_hits(category_text, NON_GAME_CATEGORY_TERMS):
        if has_bundle_signal(evidence):
            return {
                "result": "review",
                "reason": "category suggests non-game/bundle review",
                "category_ids": leaf_category_ids,
                "category_names": category_names,
            }
        return {
            "result": "blocked",
            "reason": "eBay category is not Video Games software",
            "category_ids": leaf_category_ids,
            "category_names": category_names,
        }
    positive = any(category_id in GAME_SOFTWARE_CATEGORY_IDS for category_id in leaf_category_ids)
    return {
        "result": "pass",
        "reason": "Known game software category" if positive else "No known non-game category signal",
        "category_ids": leaf_category_ids,
        "category_names": category_names,
        "positive_game_software_category": positive,
    }


def delivery_rule(raw_json: dict[str, Any]) -> dict[str, Any]:
    delivery_options = []
    for availability in raw_json.get("estimatedAvailabilities") or []:
        if isinstance(availability, dict):
            delivery_options.extend(str(option) for option in availability.get("deliveryOptions") or [])
    pickup_options = raw_json.get("pickupOptions") or []
    shipping_options = raw_json.get("shippingOptions") or []
    has_shipping = bool(shipping_options)
    has_pickup = any("PICKUP" in option.upper() for option in delivery_options) or bool(pickup_options)
    if has_pickup and not has_shipping:
        return {
            "result": "blocked",
            "reason": "pickup-only listing",
            "delivery_options": delivery_options,
            "has_shipping_options": has_shipping,
        }
    return {
        "result": "pass",
        "reason": "No pickup-only delivery signal",
        "delivery_options": delivery_options,
        "has_shipping_options": has_shipping,
    }


def lower_recommendation(current: str, candidate: str) -> str:
    if RECOMMENDATION_RANK.get(candidate, 2) < RECOMMENDATION_RANK.get(current, 2):
        return candidate
    return current
