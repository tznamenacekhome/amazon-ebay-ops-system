"""Typed identity metadata spans; never seller wording or fuzzy title cleanup."""
import re
from system_detection import SYSTEM_ALIASES, normalize_system

MISSING_GAME_NAMES = frozenset({'n/a', 'n a', 'na', 'none', 'unknown', 'does not apply', 'not applicable'})
LEGACY_SYSTEMS = frozenset({'Gamecube', 'Game Boy Advance', 'Game Boy Color', 'Game Boy',
                            'Super Nintendo', 'Nintendo 64', 'Dreamcast', 'Sega CD', 'PSP'})


def missing_game_name(value):
    return re.sub(r'\s+', ' ', str(value or '').strip().casefold()) in MISSING_GAME_NAMES


def typed_product_text(text, *, source, side, evidence, catalog):
    """Retain source text separately; return parsing text plus auditable spans.

    Only complete canonical legacy phrases are new removals. Region and media
    suffixes need independent structured corroboration and must not occur in a
    real Game Name. Platform-like title words on another known system are masked
    from the old platform regex, not discarded from product identity.
    """
    raw = str(text or '')
    expected = {normalize_system(v) for v in evidence.get('platform_values', [])}
    attrs = catalog.get('relevant_attributes_json') or {}
    expected.add(normalize_system(catalog.get('normalized_platform')))
    expected.add(normalize_system(attrs.get('platform')))
    expected.discard(None)
    names = [str(v) for v in evidence.get('game_name_values', []) if not missing_game_name(v)]
    assigned, masks = [], {}
    working = raw
    # Protect a meaningful bare Switch when the independent platform says this
    # is another system. Explicit Nintendo Switch remains contradictory evidence.
    if expected - {'Switch', 'Switch 2'}:
        for match in list(re.finditer(r'(?<!\w)switch(?!\w)', working, re.I))[::-1]:
            if re.search(r'nintendo\s*$', working[:match.start()], re.I):
                continue
            token = 'MBOPIDENTITYWORD'
            masks[token.casefold()] = match[0]
            working = working[:match.start()] + token + working[match.end():]
            assigned.append({'text': match[0], 'field': 'coreGame', 'source': source,
                             'reason': 'product word retained; independent platform is not Switch'})
    aliases = sorted(((alias, system) for system in LEGACY_SYSTEMS
                      for alias in SYSTEM_ALIASES[system]), key=lambda v: -len(v[0]))
    occupied = []
    for alias, system in aliases:
        for match in re.finditer(r'(?<!\w)' + re.escape(alias) + r'(?!\w)', working, re.I):
            if any(match.start() < end and match.end() > start for start, end in occupied):
                continue
            # Short aliases/names need a consistent independent platform. A full
            # phrase is usable with structured platform or a corroborating name.
            if system not in expected:
                continue
            if source == 'game_name' and not re.search(r'[([][^])]*' + re.escape(alias), raw, re.I):
                continue
            occupied.append(match.span())
            assigned.append({'text': match[0], 'field': 'platform', 'value': system,
                             'source': source, 'reason': 'complete canonical platform span corroborated by independent platform'})
    for start, end in sorted(occupied, reverse=True):
        working = working[:start] + ' ' + working[end:]
    # Restrict new region/media extraction to terminal metadata with corroboration.
    media = evidence.get('format_values') or ([catalog['normalized_format']] if catalog.get('normalized_format') else [])
    patterns = [('region', r'USA|US Version|NTSC[- ]U(?:/C)?|PAL', evidence.get('region_code_values') or ([catalog['normalized_region']] if catalog.get('normalized_region') else [])),
                ('mediaFormat', r'CD[- ]ROM|DVD[- ]ROM', media)]
    for field, pattern, corroboration in patterns:
        match = re.search(r'(?<!\w)(' + pattern + r')\s*[)\]]?\s*(?:Brand New|New|Sealed)?\s*$', working, re.I)
        if not match or source != 'title' or not corroboration:
            continue
        if any(re.search(r'(?<!\w)' + re.escape(match[1]) + r'(?!\w)', name, re.I) for name in names):
            continue
        assigned.append({'text': match[1], 'field': field, 'source': source,
                         'corroboration': list(corroboration),
                         'reason': 'terminal metadata corroborated by structured field; independent evaluation retained'})
        working = working[:match.start()] + working[match.end(1):]
    return working, assigned, masks
