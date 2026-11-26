import re
from typing import Any


# Single canonical alias source shared with the sourcing server APIs.
import json
from pathlib import Path
SYSTEM_ALIASES = json.loads((Path(__file__).resolve().parents[1] / 'web/lib/canonicalSystems.json').read_text())


def normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_system(value: str | None) -> str | None:
    if not value:
        return None

    text = normalize_spaces(value.lower())
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = normalize_spaces(text)
    for canonical in SYSTEM_ALIASES:
        if text == normalize_spaces(re.sub(r'[^a-z0-9]+', ' ', canonical.lower())):
            return canonical

    for canonical, aliases in SYSTEM_ALIASES.items():
        for alias in aliases:
            alias_norm = normalize_spaces(re.sub(r"[^a-z0-9]+", " ", alias.lower()))
            if text == alias_norm:
                return canonical

    for canonical, aliases in SYSTEM_ALIASES.items():
        for alias in aliases:
            alias_norm = normalize_spaces(re.sub(r"[^a-z0-9]+", " ", alias.lower()))
            if re.search(rf"\b{re.escape(alias_norm)}\b", text):
                return canonical

    return None


def canonical_systems(value):
    """All explicit systems, longest overlapping aliases win; shared with API."""
    text = ' ' + re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9]+', ' ', str(value or '').lower())).strip() + ' '
    exact = [key for key in SYSTEM_ALIASES if text.strip() == re.sub(r'[^a-z0-9]+', ' ', key.lower()).strip()]
    if exact:
        return exact
    found = []
    for system, aliases in SYSTEM_ALIASES.items():
        for alias in aliases:
            needle = ' ' + re.sub(r'[^a-z0-9]+', ' ', alias.lower()).strip() + ' '
            start = text.find(needle)
            while start >= 0:
                found.append((start, start + len(needle) - 1, system))
                start = text.find(needle, start + 1)
    kept = []
    for row in sorted(found, key=lambda item: -(item[1]-item[0])):
        if not any(row[0] < other[1] and row[1] > other[0] for other in kept):
            kept.append(row)
    return list(dict.fromkeys(row[2] for row in kept))


def detect_system_from_title(title: str | None) -> str | None:
    if not title:
        return None

    text = title.lower()
    matches = []

    for canonical, aliases in SYSTEM_ALIASES.items():
        for alias in aliases:
            pattern = rf"(?<![a-z0-9]){re.escape(alias.lower())}(?![a-z0-9])"
            if re.search(pattern, text):
                matches.append((len(alias), canonical))

    if not matches:
        return None

    matches.sort(reverse=True)
    return matches[0][1]


def remove_system_terms(text: str) -> str:
    cleaned = text

    aliases = []
    for alias_list in SYSTEM_ALIASES.values():
        aliases.extend(alias_list)

    aliases.sort(key=len, reverse=True)

    for alias in aliases:
        cleaned = re.sub(
            rf"(?<![a-z0-9]){re.escape(alias.lower())}(?![a-z0-9])",
            " ",
            cleaned,
        )

    return cleaned

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
