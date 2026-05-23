import re


LEADING_SYSTEM_ALIASES = [
    "Nintendo Switch 2",
    "Nintendo Switch",
    "Nintendo 3DS",
    "Nintendo DS",
    "Nintendo Wii U",
    "Nintendo Wii",
    "Playstation 5",
    "PlayStation 5",
    "Playstation 4",
    "PlayStation 4",
    "Playstation 3",
    "PlayStation 3",
    "Playstation 2",
    "PlayStation 2",
    "Xbox Series X",
    "Xbox Series S",
    "Xbox One",
    "Xbox 360",
    "Gamecube",
    "Nintendo 64",
    "Super Nintendo",
    "PS Vita",
    "Switch 2",
    "Switch",
    "PS5",
    "PS4",
    "PS3",
    "PS2",
    "PSP",
    "NES",
    "DS",
    "PC",
    "Wii U",
    "Wii",
    "Xbox",
]

NOISE_PHRASES = [
    "new:",
    "brand new sealed",
    "brand new / sealed",
    "brand new/sealed",
    "brand new factory sealed read",
    "brand new factory sealed",
    "factory sealed",
    "free shipping",
    "fast shipping",
    "ships fast",
    "please read",
    "read description",
    "new sealed",
]

NOISE_WORDS = {
    "brand",
    "factory",
    "fast",
    "free",
    "new",
    "read",
    "sealed",
    "shipping",
    "ships",
}


def clean_marketplace_title_for_search(title: str | None) -> str:
    """Clean an eBay/marketplace title for Amazon catalog search.

    This keeps useful title and platform terms, removes common condition/shipping
    noise, drops release years inside system parentheticals, and moves leading
    system terms to the end of the query.
    """
    if not title:
        return ""

    title_with_clean_parentheticals = remove_parenthetical_release_years(title)
    title_without_noise = trim_noise_words(
        remove_noise_phrases(title_with_clean_parentheticals)
    )
    cleaned_title, leading_systems = move_leading_system_terms(title_without_noise)
    search_term = cleanup_search_text(
        " ".join([cleaned_title, " ".join(leading_systems)])
    )

    return search_term


def remove_noise_phrases(value: str) -> str:
    current_value = value

    for phrase in NOISE_PHRASES:
        current_value = re.sub(
            rf"(^|\b){re.escape(phrase)}(?=\s|\b|$)",
            " ",
            current_value,
            flags=re.IGNORECASE,
        )

    return current_value


def remove_parenthetical_release_years(value: str) -> str:
    def replace_match(match):
        contents = match.group(1)
        cleaned_contents = cleanup_search_text(
            re.sub(r"\b(?:19|20)\d{2}\b", " ", contents)
        )

        return f" {cleaned_contents} " if cleaned_contents else " "

    return re.sub(r"\(([^)]*)\)", replace_match, value)


def trim_noise_words(value: str) -> str:
    words = cleanup_search_text(value).split(" ")

    while words and words[0].lower() in NOISE_WORDS:
        words.pop(0)

    while words and words[-1].lower() in NOISE_WORDS:
        words.pop()

    return " ".join(words)


def move_leading_system_terms(value: str) -> tuple[str, list[str]]:
    leading_systems = []
    remaining_title = cleanup_search_text(value)
    matched = True

    while matched:
        matched = False

        for alias in LEADING_SYSTEM_ALIASES:
            match = re.match(
                rf"^{re.escape(alias)}(?=\s|[-:/|]|$)",
                remaining_title,
                flags=re.IGNORECASE,
            )

            if not match:
                continue

            leading_systems.append(match.group(0))
            remaining_title = cleanup_search_text(
                re.sub(r"^[-:/|\s]+", "", remaining_title[match.end():])
            )
            matched = True
            break

    return remaining_title, leading_systems


def cleanup_search_text(value: str) -> str:
    text = re.sub(r"[()[\]{}]", " ", value or "")
    text = re.sub(r"[.,!?]+", " ", text)
    text = re.sub(r"\s*[/|]\s*", " ", text)
    text = re.sub(r"\s*[-:]\s*", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
