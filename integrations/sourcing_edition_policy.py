"""Evidence-based edition decisions. Observations are never replaced by inference."""
import re

VERSION = 'sourcing_edition_policy_v1'
RERELEASES = frozenset({'Greatest Hits', 'Platinum Hits', "Player's Choice", 'Nintendo Selects',
                       'PlayStation Hits', 'PlayStation Essentials'})


def standard(value):
    return str(value or '').casefold() in {'standard', 'standard edition'}


def canonical_catalog_edition(value):
    key = re.sub(r'[^a-z0-9]+',' ',str(value or '').casefold()).strip()
    if key in {'standard','standard edition'}:
        return 'Standard'
    for name in ('deluxe','limited','premium','gold','ultimate','special','enhanced'):
        if key in {name,name+' edition'}:
            return name.title()+' Edition'
    if key in {'collector','collectors','collector s','collector edition','collectors edition','collector s edition'}:
        return "Collector's Edition"
    return value


def gtin(value):
    text = str(value or '').strip()
    if not text.isdigit() or len(text) not in (8,12,13,14) or set(text) == {'0'}:
        return None
    if sum(int(n) * (3 if i % 2 == 0 else 1) for i,n in enumerate(reversed(text[:-1]))) % 10 != (-int(text[-1])) % 10:
        return None
    return text.zfill(14)


def edition_decision(amazon, ebay, comparisons):
    a, b = amazon.get('edition'), ebay.get('edition')
    context = ebay.get('editionContext') or {}
    catalog = (amazon.get('referenceMetadata') or {}).get('catalog') or {}
    attributes = catalog.get('relevant_attributes_json') or {}
    text = context.get('text', '').casefold()
    from sourcing_package_contents import package_decision
    package = package_decision(amazon, ebay, comparisons)
    manifest = [part['name'] for part in package['requiredContents']]
    if isinstance(manifest, str):
        manifest = [manifest]
    required = [part for part in manifest if not re.fullmatch(r'(?:video\s*game|game(?: disc)?|disc|cartridge|instruction manual|manual|user guide)',str(part).strip(),re.I)]
    collector = a and 'collector' in a.casefold()
    known = {gtin(x.get('value')) for x in attributes.get('product_identifiers',[]) if x.get('type','').casefold() in {'upc','ean','gtin'}} - {None}
    observed = {gtin(x) for x in context.get('gtins',[])} - {None}
    contents_ok = bool(required) and (not collector or len(manifest) >= 2) and package['result']=='match'
    material = [k for k,v in comparisons.items() if k != 'edition' and v['result'] in {'conflict','review'}]
    corroborated = (comparisons['coreGame']['result'] == 'match' and comparisons['platform']['result'] == 'match'
                    and not material and (bool(context.get('corroboratingName')) or bool(known and observed and observed <= known)))
    result = dict(version=VERSION, amazon=a, ebay=b, result=comparisons['edition']['result'],
                  reason=comparisons['edition']['reason'], code=None, compatibleOmission=False,
                  evidence=context.get('sources', []) + [{'side':side, 'identityField':field, 'value':identity[field], 'evidenceRef':side+'.fields.'+field} for side,identity in [('amazon',amazon),('ebay',ebay)] for field in ('coreGame','platform')],
                  corroboration={k:{'result':comparisons[k]['result'],'amazon':comparisons[k]['amazon'],'ebay':comparisons[k]['ebay']} for k in ('coreGame','platform','installment','packageType','region')},
                  requiredContents=required, unresolvedMaterialFields=material)
    result['packagePolicy'] = package
    independent_contents_review = (package['result']=='review' and package['configuration']=='bundle'
        and not required and amazon.get('packageType') and amazon.get('packageType')==ebay.get('packageType'))
    if independent_contents_review:
        # Same named retail bundle can be an identity match while its physical
        # contents remain independently unverified for purchasing.
        result['independentContentsReview']=True
        result['code']='contents_not_corroborated'

    def decide(outcome, reason, code=None, omission=False):
        return {**result, 'result':outcome, 'reason':reason, 'code':code or result['code'], 'compatibleOmission':omission}

    ordinary_a = not a or standard(a) or a in RERELEASES
    ordinary_b = not b or standard(b) or b in RERELEASES
    if package['result'] != 'match' and not independent_contents_review:
        return decide(package['result'], package['reason'], package['code'])
    ambiguous = context.get('ambiguousEditions') and b and ' + ' in b and a in b.split(' + ')
    # Missing/contradictory corroboration must never downgrade a confirmed
    # substantive edition conflict into an economically attractive near miss.
    if comparisons['edition']['result'] == 'conflict' and not (ordinary_a and ordinary_b) and not ambiguous:
        return result
    if context.get('ambiguousFeatureEditions') and not (b == 'Complete Edition' or a == 'Complete Edition'):
        return decide('review', 'Complete Edition appears only in Features; named retail edition versus generic completeness is unresolved.', 'edition_not_corroborated')
    if a and a in context.get('explicitlyExcludedEditions',[]):
        return decide('conflict', f'Listing explicitly states it is not {a}.')
    if not b and (attributes.get('edition_variants') or re.search(r'edition|bundle|package',str(catalog.get('variation_theme') or ''),re.I)):
        return decide('review', 'Multiple plausible edition/SKU variants require positive disambiguation.', 'edition_not_corroborated')
    if context.get('negativeEditionEvidence'):
        return decide('review', 'Edition evidence contains a negated or missing designation.', 'edition_not_corroborated')
    if (a or b) and known and observed and not observed <= known:
        return decide('review', 'Product identifiers leave a material edition/SKU discrepancy unresolved.', 'edition_not_corroborated')
    if context.get('ambiguousEditions') and b and ' + ' in b and a in b.split(' + '):
        return decide('review', 'Multiple plausible editions remain unresolved.', 'edition_not_corroborated')
    if amazon['fields']['edition']['state'] == 'conflicting_sources' or ebay['fields']['edition']['state'] == 'conflicting_sources':
        return result
    if required and not contents_ok:
        return decide('review', f'{a or "Product"} required contents not corroborated.', 'contents_not_corroborated')
    packaging = attributes.get('packaging_requirement')
    if packaging and (b in RERELEASES or a in RERELEASES) and str(packaging).casefold() not in text:
        return decide('review', 'Amazon catalog packaging requirement not corroborated.', 'contents_not_corroborated')
    differences = list(re.finditer(r'\b(?:additional|extra|different|bonus)\s+(?:discs?|content|chapters?|levels?)\b', text))
    if (a in RERELEASES or b in RERELEASES) and any(not re.search(r'\b(?:no|not|without)\s*$',text[max(0,m.start()-12):m.start()]) for m in differences):
        return decide('review', 'Re-release has potentially material content differences.', 'contents_not_corroborated')
    if a == 'Jewel Case' and not b:
        if corroborated and re.search(r'\bjewel\s+case\b',text) and not re.search(r'\b(?:dvd case|missing (?:jewel )?case|no (?:jewel )?case|jewel case[^.!?]{0,20}(?:missing|not included))\b',text):
            return decide('match', 'Jewel Case packaging is positively corroborated.', omission=True)
        return decide('review', 'Jewel Case packaging not corroborated.', 'contents_not_corroborated')
    if ordinary_a and ordinary_b and (standard(a) or standard(b) or a in RERELEASES or b in RERELEASES):
        if corroborated:
            return decide('match', 'Core game/platform and a corroborating structured name or exact catalog GTIN agree; ordinary edition omission or marketing re-release is compatible.', omission=not a or not b)
        if not a or not b or a != b:
            return decide('review', 'Ordinary edition compatibility lacks sufficient corroboration.', 'edition_not_corroborated')
    # A named material edition is not inferred from the base title or an identifier alone.
    if a and not ordinary_a and not b:
        unambiguous = not catalog.get('variation_parent_asins') and not catalog.get('variation_child_asins')
        if known & observed and corroborated and unambiguous and (not required or contents_ok) and (not collector or contents_ok):
            return decide('match', f'Exact catalog GTIN corroborates {a}; material identity and required contents agree.', omission=True)
        reason = ("Collector's Edition or required contents not corroborated." if 'collector' in a.casefold()
                  else f'{a} not corroborated.')
        return decide('review', reason, 'edition_not_corroborated')
    if (a and a == b and required) or (a and a == b and collector):
        if not contents_ok:
            return decide('review', f'{a} or required contents not corroborated.', 'contents_not_corroborated')
    return result


