import re


SYSTEM_ALIASES = {
    "Switch 2": ["nintendo switch 2", "switch 2"],
    "Switch": ["nintendo switch", "switch"],
    "3DS": ["nintendo 3ds", "3ds"],
    "DS": ["nintendo ds", "ds"],
    "Wii U": ["nintendo wii u", "wii u", "wiiu"],
    "Wii": ["nintendo wii", "wii"],
    "Gamecube": ["gamecube", "game cube", "nintendo gamecube"],
    "Nintendo 64": ["nintendo 64", "n64"],
    "Super Nintendo": ["super nintendo", "snes"],
    "NES": ["nes", "nintendo entertainment system"],
    "PS 5": ["playstation 5", "ps5", "ps 5"],
    "PS 4": ["playstation 4", "ps4", "ps 4"],
    "PS 3": ["playstation 3", "ps3", "ps 3"],
    "PS 2": ["playstation 2", "ps2", "ps 2"],
    "PS": ["playstation", "ps1", "psx"],
    "PSP": ["psp", "playstation portable"],
    "PS Vita": ["playstation vita", "ps vita", "vita"],
    "Xbox Series X": ["xbox series x", "series x"],
    "Xbox Series S": ["xbox series s", "series s"],
    "Xbox One": ["xbox one", "xbone", "xb1"],
    "Xbox 360": ["xbox 360", "360"],
    "Xbox": ["original xbox", "xbox"],
    "PC": ["pc", "windows pc", "windows", "mac"],
}


def normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_system(value: str | None) -> str | None:
    if not value:
        return None

    text = normalize_spaces(value.lower())
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = normalize_spaces(text)

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
