"""Deterministic sourcing match rules for Amazon ASIN -> eBay listing review."""

from __future__ import annotations

import re
from typing import Any

from system_detection import SYSTEM_ALIASES, detect_system_from_title, normalize_system
from title_cleaning import clean_marketplace_title_for_search


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
    "edition",
    "esrb",
    "fast",
    "for",
    "game",
    "games",
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
    "base game not included",
    "bonus code",
    "car pack dlc",
    "digital code",
    "digital content",
    "dlc",
    "download",
    "email delivery",
    "gamesharing",
    "in-game",
    "key code",
    "message before purch",
    "message delivery",
    "show packs",
    "steam",
    "unlock all service",
    "vpn",
    "will send",
}

INCOMPLETE_BLOCK_TERMS = {
    "art only",
    "artwork only",
    "booklet only",
    "case only",
    "cover art",
    "disc only",
    "game case",
    "instruction manual",
    "manual only",
    "no disc",
    "no game",
    "replacement case",
    "replacement cover",
    "steelbook only",
}

NOT_GAME_BLOCK_TERMS = {
    "adapter converter",
    "amiibo",
    "blind bag",
    "button pin",
    "collectible figure",
    "decal",
    "enamel pin",
    "figure",
    "fridge magnet",
    "game art keychain",
    "guide book",
    "iron on patch",
    "key chain",
    "keychain",
    "magazine",
    "pin",
    "pin badge",
    "plush",
    "plushie",
    "poster",
    "print ad",
    "sew on patch",
    "skin decal",
    "statue",
    "sticker",
    "strategy guide",
    "thumb grip",
    "toy",
    "trading card",
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
    "usk",
}

EDITION_SIGNALS = {
    "collector": {"collector", "collector's edition", "collectors edition"},
    "deluxe": {"deluxe", "deluxe edition"},
    "gold": {"gold", "gold edition"},
    "greatest_hits": {"greatest hits"},
    "limited": {"limited", "limited edition"},
    "platinum_hits": {"platinum hits"},
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


def evaluate_static_match_rules(
    candidate: dict[str, Any],
    seed: dict[str, Any],
    *,
    excluded_keywords: list[str] | None = None,
    allowed_item_location_countries: list[str] | None = None,
) -> dict[str, Any]:
    amazon_title = str(seed.get("amazon_title") or "")
    ebay_title = str(candidate.get("ebay_title") or "")
    raw_json = candidate.get("raw_ebay_json") or {}
    combined_text = searchable_candidate_text(candidate)
    title_text = " ".join([ebay_title, str(candidate.get("condition") or "")]).casefold()

    flags: list[str] = []
    hard_blocks: list[str] = []
    warnings: list[str] = []
    score_adjustment = 0
    recommendation = "Review"

    platform = platform_rule(amazon_title, ebay_title, seed)
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

    incomplete = keyword_hits(title_text, sorted(INCOMPLETE_BLOCK_TERMS))
    not_game = keyword_hits(title_text, sorted(NOT_GAME_BLOCK_TERMS))
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

    edition = edition_rule(amazon_title, ebay_title)
    if edition["result"] == "review":
        warnings.append(edition["reason"])
        flags.append(edition["reason"])
        score_adjustment -= 15
        recommendation = lower_recommendation(recommendation, "Probable Non-Match")

    category = category_rule(raw_json)
    if category["result"] == "blocked":
        hard_blocks.append(category["reason"])
        flags.append(f"Blocked: {category['reason']}")
        score_adjustment -= 30
        recommendation = "Blocked"

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
        reason = "non-US/Canada item location"
        location["result"] = "blocked"
        hard_blocks.append(reason)
        flags.append(f"Blocked: {reason}")
        score_adjustment -= 30
        recommendation = "Blocked"

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
        "edition_version": edition,
        "category": category,
        "delivery": delivery,
        "location": location,
    }


def searchable_candidate_text(candidate: dict[str, Any]) -> str:
    raw_json = candidate.get("raw_ebay_json") or {}
    parts = [
        candidate.get("ebay_title"),
        candidate.get("condition"),
        raw_json.get("subtitle"),
        raw_json.get("shortDescription"),
        raw_json.get("description"),
    ]
    localized = raw_json.get("localizedAspects") or []
    if isinstance(localized, list):
        for aspect in localized:
            if isinstance(aspect, dict):
                parts.append(aspect.get("name"))
                parts.append(aspect.get("value"))
    return " ".join(str(part or "") for part in parts).casefold()


def platform_rule(amazon_title: str, ebay_title: str, seed: dict[str, Any]) -> dict[str, Any]:
    seed_system = normalize_system(str(seed.get("system") or "")) or detect_system_from_title(amazon_title)
    ebay_systems = detect_all_systems(ebay_title)
    ebay_primary_system = detect_system_from_title(ebay_title)

    result = "unknown"
    reason = "No platform signal available"
    if seed_system and not ebay_systems:
        result = "review"
        reason = "Candidate listing has no detectable platform"
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
        "candidate_system": ebay_primary_system,
        "candidate_systems": ebay_systems,
        "result": result,
        "reason": reason,
    }


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


def edition_rule(amazon_title: str, ebay_title: str) -> dict[str, Any]:
    amazon_signals = edition_signals(amazon_title)
    ebay_signals = edition_signals(ebay_title)
    missing_from_amazon = sorted(ebay_signals - amazon_signals)
    missing_from_ebay = sorted(amazon_signals - ebay_signals)
    result = "pass"
    reason = "Edition/version signals match or are absent"
    if missing_from_amazon or missing_from_ebay:
        result = "review"
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


def category_rule(raw_json: dict[str, Any]) -> dict[str, Any]:
    categories = []
    for category in raw_json.get("categories") or []:
        if isinstance(category, dict):
            categories.append(str(category.get("categoryId") or ""))
    leaf_category_ids = [value for value in categories if value]
    if any(category_id in NON_GAME_CATEGORY_IDS for category_id in leaf_category_ids):
        return {
            "result": "blocked",
            "reason": "eBay category is not Video Games software",
            "category_ids": leaf_category_ids,
        }
    return {"result": "pass", "reason": "No known non-game category signal", "category_ids": leaf_category_ids}


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
