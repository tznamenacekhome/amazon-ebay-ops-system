"""Evidence-gated Phase 2 roles. Original evidence is never edited or discarded."""
import re
from sourcing_identity_metadata import missing_game_name
from system_detection import normalize_system


def orthographic_text(value):
    text = str(value or '')
    spans = []
    # Possessive/apostrophe spelling, not removal of the possessive word.
    patterns = [(r"(?<=\w)['’]s\b", 's'),
                (r'\bsmack\s*down\b', 'Smackdown'), (r'\bwar\s*zone\b', 'Warzone'),
                (r'\bsteel\s*book\b', 'Steelbook'), (r'\bsim\s*city\b', 'Simcity')]
    for pattern, replacement in patterns:
        def change(m):
            if m[0] != replacement:
                spans.append({'text': m[0], 'value': replacement, 'field': 'orthography',
                              'reason': 'audited punctuation/word-boundary equivalent; product words retained'})
            return replacement
        text = re.sub(pattern, change, text, flags=re.I)
    return text, spans


def typed_identity_wording(text, *, source, side, evidence, fields, reference_core=None):
    """Only classify edge wording with a complete, consistent structured name.

    No arbitrary residue, inventory code, year, subtitle, or publisher alias is
    accepted. Package/edition fields still parse the source title, and all other
    evaluators retain the complete original title/description/item specifics.
    """
    working, assigned = orthographic_text(text)
    assigned = [{**span, 'source': source} for span in assigned]
    if side != 'ebay' or source != 'title':
        return working, assigned
    if reference_core and fields(working)['coreGame'] == reference_core:
        return working, assigned
    names = [orthographic_text(v)[0] for v in evidence.get('game_name_values', [])
             if not missing_game_name(v) and str(v).strip()]
    cores = {fields(name)['coreGame'] for name in names}
    cores.discard(None)
    if len(cores) != 1 or not any(normalize_system(v) for v in evidence.get('platform_values', [])):
        return working, assigned
    core = next(iter(cores))
    # A competing actual name prevents corroboration; semicolon lists stay out
    # of Phase 2 even where their parser would happen to produce one value.
    if any(';' in name or ',' in name for name in names):
        return working, assigned
    romans = {'ii': 2, 'iii': 3, 'iv': 4, 'v': 5, 'vi': 6, 'vii': 7, 'viii': 8,
              'ix': 9, 'x': 10, 'xi': 11, 'xii': 12, 'xiii': 13, 'xiv': 14, 'xv': 15, 'xvi': 16}
    def duplicate(m):
        a, b = m[1].lower(), m[2].lower()
        roman, digit = (a, b) if a in romans else (b, a)
        if roman in romans and digit.isdigit() and romans[roman] == int(digit) and re.search(r'(?<!\w)' + digit + r'(?!\w)', core):
            assigned.append({'text': m[0], 'value': digit, 'source': source, 'field': 'installment',
                             'corroboration': names, 'reason': 'adjacent equivalent Roman/Arabic installment; structured complete name agrees'})
            return digit
        return m[0]
    numeral = '|'.join(sorted(romans, key=len, reverse=True))
    working = re.sub(r'\b(' + numeral + r'|\d+)\s+(' + numeral + r'|\d+)\b', duplicate, working, flags=re.I)
    core_tokens = re.findall(r'[a-z0-9]+', core.casefold())
    core_match = re.search(r'(?<!\w)' + r'\W+'.join(map(re.escape, core_tokens)) + r'(?!\w)', working, re.I) if core_tokens else None
    if not core_match:
        return working, assigned
    # These are semantic roles, not ignored words. Assignment succeeds only if
    # the entire residual named product equals the full structured name below.
    candidates = []
    patterns = [
        ('condition', r'\b(?:brand new(?:\s*(?:&|and)\s*sealed)?|factory seal(?:ed)?|new(?:\s*(?:&|and)\s*sealed)?|sealed|unopened|never opened|new old stock|NIB|BNIB|NIP|OEM sealed|Y[- ]fold)\b'),
        ('sellerDescription', r'\b(?:rare|read description|ready to ship|free ship(?:ping|n)?|fast shipping|ships fast)\b'),
        ('packageDescription', r'\b(?:original case|with slipcover|retail release with hangtab)\b'),
    ]
    proposed = working
    for role, pattern in patterns:
        core_match = re.search(r'(?<!\w)' + r'\W+'.join(map(re.escape, core_tokens)) + r'(?!\w)', proposed, re.I)
        if not core_match:
            return working, assigned
        def classify(m):
            candidates.append({'text': m[0], 'field': role, 'source': source,
                               'reason': 'seller wording outside complete corroborating Game Name; raw evidence retained for independent safeguards'})
            return ' '
        # Never consume words that belong to the structured product name.
        proposed = re.sub(pattern, lambda m: m[0] if (
            re.search(r'(?<!\w)' + re.escape(m[0]) + r'(?!\w)', ' '.join(names), re.I)
            or (m.start() < core_match.end() and m.end() > core_match.start())
            or (m[0].casefold() == 'new' and re.match(r'\s+(?:super\s+mario\s+bros|carnival\s+games)\b', proposed[m.end():], re.I))
        ) else classify(m), proposed, flags=re.I)
    # Publisher metadata must match an actual structured edge attribution; no
    # Electronic Arts -> EA or other publisher aliases are invented here.
    publishers = (evidence.get('aspects') or {}).get('publisher') or []
    for publisher in publishers:
        pub = str(publisher).strip()
        pub = re.sub(r'[,\s]+(?:inc\.?|corporation|corp\.?)$', '', pub, flags=re.I)
        if not pub or pub.casefold() in ' '.join(names).casefold():
            continue
        pattern = r'(?<!\w)' + re.escape(pub).replace(r'\ ', r'\s*') + r'(?!\w)'
        for match in list(re.finditer(pattern, proposed, re.I))[::-1]:
            # The remainder must reduce to the corroborated full name; the
            # final equality test prohibits dropping an internal product word.
            left, right = proposed[:match.start()], proposed[match.end():]
            if not fields(left)['coreGame'] or fields(right)['coreGame']:
                continue
            candidates.append({'text': match[0], 'field': 'publisherAttribution', 'source': source,
                               'corroboration': [publisher, *names], 'reason': 'structured publisher at title edge; complete Game Name and platform corroborate attribution'})
            proposed = left + ' ' + right
    if fields(proposed)['coreGame'] == core and candidates:
        assigned.extend({**span, 'corroboration': span.get('corroboration', names)} for span in candidates)
        working = proposed
    return working, assigned
