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
                (r'\bsteel\s*book\b', 'Steelbook'), (r'\bsim\s*city\b', 'Simcity'),
                (r'\broller\s*coaster(?=\s+tycoon\b)', 'Rollercoaster')]
    for pattern, replacement in patterns:
        def change(m):
            if m[0] != replacement:
                spans.append({'text': m[0], 'value': replacement, 'field': 'orthography',
                              'reason': 'audited punctuation/word-boundary equivalent; product words retained'})
            return replacement
        text = re.sub(pattern, change, text, flags=re.I)
    return text, spans


def _phase2_identity_wording(text, *, source, side, evidence, fields, reference_core=None):
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


# Audited corporate attribution relationships, not interchangeable game names.
PUBLISHER_RELATIONSHIPS = (
    ('electronic arts', 'ea sports'), ('lucasarts', 'lucas arts'),
    ('blue byte', 'blue byte software'), ('microsoft', 'microsoft game studios'),
    ('acclaim', 'acclaim entertainment', 'accalim'), ('cosmi',),
)


def publisher_key(value):
    text = re.sub(r"[^\w]+", ' ', str(value or '').casefold()).strip()
    return re.sub(r'\s+(?:inc|incorporated|corp|corporation|ltd|limited)$', '', text).strip()


def publisher_variants(publishers):
    keys = {publisher_key(v) for v in publishers if publisher_key(v)}
    groups = []
    for key in keys:
        groups.append(next((set(group) for group in PUBLISHER_RELATIONSHIPS if key in group), {key}))
    if not groups or any(not (group & groups[0]) for group in groups[1:]):
        return []
    return sorted(set.union(*groups), key=len, reverse=True)


def complete_name_context(evidence, fields):
    names = [orthographic_text(v)[0] for v in evidence.get('game_name_values', []) if not missing_game_name(v) and str(v).strip()]
    if not names or any(';' in n or ',' in n for n in names):
        return None
    cores = {fields(n)['coreGame'] for n in names}
    systems = {normalize_system(v) for v in evidence.get('platform_values', [])}
    systems.discard(None)
    if len(cores) != 1 or None in cores or len(systems) != 1:
        return None
    return names, next(iter(cores)), next(iter(systems))


def core_pattern(core):
    romans = {'2':'ii','3':'iii','4':'iv','5':'v','6':'vi','7':'vii','8':'viii','9':'ix','10':'x','11':'xi','12':'xii','13':'xiii','14':'xiv','15':'xv','16':'xvi'}
    return r'(?<!\w)' + r'\W+'.join('(?:'+re.escape(t)+'|'+romans[t]+')' if t in romans else re.escape(t) for t in core.split()) + r'(?!\w)'


def typed_identity_wording(text, *, source, side, evidence, fields, reference_core=None, protected_franchise=None):
    base, assigned = _phase2_identity_wording(text, source=source, side=side, evidence=evidence, fields=fields, reference_core=reference_core)
    context = complete_name_context(evidence, fields)
    if re.search(r'\b(?:disney\s+infinity|ea\s+sports\s+fc|tom\s+clancy|microsoft\s+flight\s+simulator)\b', str(text), re.I):
        return base, assigned
    if side != 'ebay' or source != 'title' or not context or (reference_core and fields(base)['coreGame'] == reference_core):
        return base, assigned
    names, core, system = context
    anchor = re.search(core_pattern(core), base, re.I)
    if not anchor:
        return base, assigned
    proposed, additions = base, []
    publishers = (evidence.get('aspects') or {}).get('publisher') or []
    for variant in publisher_variants(publishers):
        if protected_franchise and publisher_key(protected_franchise).startswith(variant + ' '):
            continue
        pattern = r'(?<!\w)' + r'\W+'.join(map(re.escape, variant.split())) + r'(?!\w)'
        if any(re.search(pattern, name, re.I) for name in names):
            continue
        matches = [m for m in re.finditer(pattern, proposed, re.I) if m.end() <= anchor.start() or m.start() >= anchor.end()]
        for match in reversed(matches):
            additions.append({'text': match[0], 'field':'publisherAttribution', 'source':source,
                'corroboration':{'publisher':publishers, 'gameName':names, 'platform':system},
                'reason':'Audited corporate relationship at the edge of a complete corroborated named product; no game alias applied.'})
            proposed = proposed[:match.start()] + ' ' + proposed[match.end():]
        if matches:
            break
    # Each role is independently constrained; the final full-name equality is
    # still mandatory. No unclassified word, code or extra product is discarded.
    role_patterns = [
        ('condition', r'\bbrand\s+new\s*(?:&|and)\s*(?:factory\s+)?sealed\b'),
        ('sellerDescription', r'\b(?:computer game|video game|game|original)\b'),
        ('packaging', r'\b(?:(?:and|&)\s+)?Y[- ]fold\b|\b(?:complete manual|CIB|with slipcover|w/\s*slipcover|retail release w/ ?hangtab|retail release w hangtab)\b'),
    ]
    if system == 'PC':
        role_patterns += [('physicalMedia', r'\b(?:CD[- ]?ROM|DVD[- ]?ROM)\b'),
                          ('operatingSystem', r'\b(?:Microsoft\s+)?Windows(?:\s+(?:95|98|2000|ME|XP|Vista|7|8|10|11|NT))?\b')]
    regions = ' '.join(map(str, evidence.get('region_code_values') or []))
    if re.search(r'NTSC[- ]U|US/Canada|North American', regions, re.I):
        role_patterns.append(('region', r'\b(?:North American|USA|US retail release)\b'))
    genre = ' '.join(map(str, (evidence.get('aspects') or {}).get('genre') or []))
    if 'dance' in genre.casefold() and ('music' in genre.casefold() or re.search(r'\b\d+\s+hit\s+tracks\b', ' '.join(evidence.get('features_values') or []), re.I)):
        role_patterns.append(('genre', r'\bdance music\b'))
    edition_support = ' '.join(map(str, (evidence.get('aspects') or {}).get('edition') or [])) + ' ' + ' '.join(map(str, evidence.get('features_values') or []))
    if re.search(r'greatest hits', edition_support, re.I):
        role_patterns.append(('editionPackaging', r'\bGH\b'))
    for year in evidence.get('release_year_values') or []:
        if re.fullmatch(r'(?:19|20)\d{2}', str(year).strip()):
            role_patterns.append(('releaseYear', r'(?<!\w)' + re.escape(str(year).strip()) + r'(?!\w)'))
    for role, pattern in role_patterns:
        anchor = re.search(core_pattern(core), proposed, re.I)
        if not anchor:
            return base, assigned
        matches = [m for m in re.finditer(pattern, proposed, re.I) if m.end() <= anchor.start() or m.start() >= anchor.end()]
        for match in reversed(matches):
            additions.append({'text':match[0], 'field':role, 'source':source,
                'corroboration':{'gameName':names,'platform':system},
                'reason':'Bounded metadata outside a complete corroborated product name; original independent purchasing evidence retained.'})
            proposed = proposed[:match.start()] + ' ' + proposed[match.end():]
    # The same installment may be repeated after the complete subtitle, as in
    # Myst IV Revelation4. No numeral can be removed from inside the named game.
    anchor = re.search(core_pattern(core), proposed, re.I)
    installment = fields(names[0]).get('installment')
    if anchor and installment and len(set(re.findall(r'(?<!\w)\d+(?!\w)', core))) == 1:
        repeat = re.match(r'\s+' + re.escape(str(installment)) + r'(?!\w)', proposed[anchor.end():])
        if repeat:
            additions.append({'text':repeat[0], 'field':'installment', 'source':source,
                'corroboration':names,'reason':'Repeated equivalent installment after full named product/subtitle; complete name and same structured installment preserved.'})
            proposed = proposed[:anchor.end()] + ' ' + proposed[anchor.end()+repeat.end():]
    proposed, roles = _phase2_identity_wording(proposed, source=source, side=side, evidence=evidence, fields=fields, reference_core=reference_core)
    if additions and fields(proposed)['coreGame'] == core:
        return proposed, [*assigned, *additions, *roles]
    return base, assigned


def amazon_attribution(amazon, ebay_title, evidence, fields):
    """Cross-source corroboration classifies a catalog edge, never imports its name."""
    context = complete_name_context(evidence, fields)
    if not context:
        return amazon
    names, core, system = context
    if fields(ebay_title)['coreGame'] != core or amazon.get('coreGame') == core:
        return amazon
    if normalize_system(amazon.get('platform')) != system:
        return amazon
    if any(amazon['fields'][key]['state'] == 'conflicting_sources' for key in ['coreGame', 'coreProduct']):
        return amazon
    publishers = (evidence.get('aspects') or {}).get('publisher') or []
    variants = publisher_variants(publishers)
    catalog = (amazon.get('referenceMetadata') or {}).get('catalog') or {}
    attrs = catalog.get('relevant_attributes_json') or {}
    catalog_publishers = [attrs.get(k) for k in ('publisher','manufacturer') if attrs.get(k)]
    if any(publisher_key(value) not in variants for value in catalog_publishers):
        return amazon
    for variant in variants:
        if amazon.get('franchise') and publisher_key(amazon['franchise']).startswith(variant + ' '):
            continue
        if re.search(r'\b(?:disney\s+infinity|ea\s+sports\s+fc|tom\s+clancy|microsoft\s+flight\s+simulator)\b', str(amazon.get('coreGame')), re.I):
            continue
        pattern = r'(?<!\w)' + r'\W+'.join(map(re.escape, variant.split())) + r'(?!\w)'
        if any(re.search(pattern, name, re.I) for name in names):
            continue
        value = str(amazon.get('coreGame') or '')
        for match in re.finditer(pattern, value, re.I):
            if match.start() != 0 and match.end() != len(value):
                continue
            remainder = (value[:match.start()]+' '+value[match.end():]).strip()
            if remainder != core:
                continue
            for key in ['coreGame','coreProduct']:
                previous = amazon[key]
                derived = fields(remainder)[key]
                amazon[key] = derived
                amazon['fields'][key]['value'] = derived
                for source in amazon['fields'][key]['sources']:
                    source['normalizedSpan'] = remainder
                amazon['fields'][key]['sourceReconciliation'].append({'source':'ebay.publisher_and_complete_game_name','relation':'corroborated_catalog_publisher_attribution','originalValue':previous,'value':derived})
            amazon['assignedMetadata'].append({'text':match[0],'field':'publisherAttribution','source':'amazon.title',
                'corroboration':{'ebayPublisher':publishers,'ebayGameName':names,'platform':system},
                'reason':'Catalog edge attribution corroborated by full offered named product, publisher and platform; original catalog sources retained.'})
            return amazon
    return amazon


def amazon_operating_system_metadata(amazon, title, ebay, evidence, fields):
    context = complete_name_context(evidence, fields)
    if not context or context[2] != 'PC' or normalize_system(amazon.get('platform')) != 'PC':
        return amazon
    if ebay.get('coreGame') != context[1] or ebay['fields']['coreGame']['state'] != 'supported':
        return amazon
    match = re.search(r'\[\s*Windows\b[^]\n]+\]\s*$', str(title), re.I)
    if not match:
        return amazon
    words = re.sub(r'\bWindows\b|[|,/\[\] ]', ' ', match[0], flags=re.I).split()
    if not words or any(w.casefold() not in {'95','98','2000','me','xp','vista','7','8','10','11','nt'} for w in words):
        return amazon
    text = str(title)[:match.start()]
    if fields(text)['coreGame'] != context[1]:
        return amazon
    for key in ['coreGame','coreProduct']:
        amazon[key] = fields(text)[key]
        amazon['fields'][key]['value'] = amazon[key]
        for source in amazon['fields'][key]['sources']:
            source['normalizedSpan'] = text
    amazon['assignedMetadata'].append({'text':match[0],'source':'amazon.title','field':'operatingSystem',
        'corroboration':{'platform':'PC','offeredGameName':context[0]},
        'reason':'Explicit Windows compatibility bracket; complete catalog product and offered name agree independently.'})
    return amazon
