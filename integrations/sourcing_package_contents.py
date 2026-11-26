"""Exact-ASIN package evidence within the existing catalog/edition policy.

Component vocabulary identifies physical evidence, never franchise requirements.
The small curated evidence artifact is versioned and deployed with integrations.
"""
import json
import re
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from system_detection import normalize_system

US = 'ATVPDKIKX0DER'
VERSION = 'exact_asin_package_evidence_v1'
COMPONENTS = {
    'balance board': r'balance\s+board',
    'guitar controller': r'(?:guitar(?:\s+controller)?(?!\s+hero)|controller\s+guitar)',
    'dance mat': r'(?:dance\s+(?:mat|pad))',
    'portal': r'portal(?:\s+of\s+power)?',
    'base': r'(?:usb\s+|infinity\s+)?base(?!\s+game)',
    'figures': r'figures?',
    'sensor': r'sensors?',
    'AR book': r'(?:ar\s+book(?:let)?|augmented\s+reality\s+book)',
}


@lru_cache(maxsize=1)
def curated_records():
    return json.loads(Path(__file__).with_name('product_package_evidence.json').read_text())['records']


def attach_verified_package(catalog, asin):
    """Reject cross-ASIN/marketplace/platform/title evidence; never mutate source."""
    result = deepcopy(catalog)
    if not result or str(result.get('asin','')).upper() != asin:
        return result
    attrs = result.get('relevant_attributes_json') or {}
    for row in curated_records():
        if row['asin'] != asin or result.get('marketplace_id', US) != row['marketplace_id']:
            continue
        if normalize_system(result.get('normalized_platform')) != normalize_system(row['platform']):
            continue
        if str(attrs.get('title','')).casefold() != row['catalog_title'].casefold():
            continue
        # An explicit, verified exact-ASIN observation can supersede an older
        # unresolved record. Conflicting verified observations remain visible.
        existing = attrs.get('verified_package_evidence')
        if (existing and existing.get('asin') == asin
                and existing.get('marketplace_id') == row['marketplace_id']
                and existing.get('verification_status')=='verified'
                and existing.get('sources')):
            if row['verification_status']=='verified' and (
                    existing.get('configuration')!=row['configuration'] or
                    existing.get('required_contents')!=row['required_contents']):
                result['relevant_attributes_json']={**attrs,'package_evidence_conflict':True,
                    'additional_verified_package_evidence':deepcopy(row)}
            continue
        attrs = {**attrs, 'verified_package_evidence':deepcopy(row)}
        result['relevant_attributes_json'] = attrs
    return result


def plain(value):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', str(value or ''))).casefold()


def component_pattern(name):
    return COMPONENTS.get(name, re.escape(name))


def absent(text, pattern):
    return bool(re.search(r'\b(?:missing|without|no|not included?|does not include)\s+(?:(?:the|a|original)\s+)*'+pattern+r'\b(?!\s+(?:damage|tears?|flaws?|scratches?))',text)
                or re.search(r'\b'+pattern+r'\s+(?:is\s+)?(?:missing|not included|excluded)\b',text))


def included(text, pattern):
    return bool(re.search(r'\b(?:includes?|contains?|comes with|complete with)\s+[^.!?]{0,100}?\b'+pattern+r'\b',text)
                or re.search(r'\b'+pattern+r'\s+(?:(?:is|are)\s+)?included\b',text))


def package_decision(amazon, ebay, comparisons):
    catalog = (amazon.get('referenceMetadata') or {}).get('catalog') or {}
    attrs = catalog.get('relevant_attributes_json') or {}
    explicit = attrs.get('verified_package_evidence') or {}
    valid = (explicit.get('asin') == catalog.get('asin') and
             explicit.get('marketplace_id', US) == catalog.get('marketplace_id', US) and
             explicit.get('sources') and
             (not explicit.get('platform') or normalize_system(explicit['platform']) == normalize_system(catalog.get('normalized_platform'))))
    explicit = explicit if valid else {}
    title = plain(attrs.get('title'))
    catalog_text = ' '.join([title,plain(amazon.get('packageType')),plain(catalog.get('normalized_edition')),
                            plain(attrs.get('product_description')),plain(attrs.get('bullet_points'))])
    manifest = explicit.get('required_contents') if explicit else attrs.get('required_contents',[])
    manifest = [manifest] if isinstance(manifest,str) else manifest or []
    required = [dict(name=r,quantity=1) if isinstance(r,str) else r for r in manifest]
    required = [r for r in required if not re.fullmatch(r'(?:video game|game(?: disc)?|disc|cartridge|instruction manual|manual|user guide)',r['name'],re.I)]
    standalone = bool(re.search(r'\b(?:game|software)\s*[- ]only\b',catalog_text))
    declared_bundle = bool(re.search(r'\b(?:bundle|starter (?:pack|kit)|with (?:balance board|guitar|dance mat|sensor))\b',catalog_text))
    config = explicit.get('configuration') or attrs.get('package_configuration')
    if explicit and explicit.get('verification_status')!='verified':
        config='unresolved'
    if config in {'game_only','software_only'}:
        config='software_only'
    elif not config:
        config = 'software_only' if standalone else 'bundle' if declared_bundle else 'required_components' if required else 'ordinary_software'
    contradiction = ((config=='software_only' and (required or declared_bundle)) or
                     (config in {'bundle','required_components'} and standalone))
    inferred_manifest = config=='bundle' and not required
    if inferred_manifest:
        # Only attributes of this exact ASIN can establish these components.
        required=[dict(name=name,quantity=1) for name,pattern in COMPONENTS.items()
                  if re.search(pattern,catalog_text) and name!='base']
    context=ebay.get('editionContext') or {}
    text=plain(context.get('text'))
    known={str(x.get('value')) for x in attrs.get('product_identifiers',[]) if str(x.get('type')).lower() in {'upc','ean','gtin'}}
    from sourcing_edition_policy import gtin
    known={gtin(x) for x in known}-{None}
    observed={gtin(x) for x in context.get('gtins',[])}-{None}
    exact_identifier=bool(known & observed) and observed <= known
    unit_only=bool(re.search(r'\b(?:game|software|disc)\s*[- ]only\b',text))
    accessory_only=bool(re.search(r'\b(?:controller|guitar|board|portal|base|instruments?)\s+only\b|\b(?:no|without|missing)\s+(?:the\s+)?game\b',text))
    extra_components=[name for name,pattern in COMPONENTS.items() if included(text,pattern)]
    listed_bundle=bool(re.search(r'\b(?:bundle|starter pack|starter kit)\b',plain(context.get('title'))) or
                       re.search(r'\b(?:guitar|instrument|board|game|retail)\s+bundle\b|\bbundle\s+(?:includes?|contains?)\b',text))
    result=dict(version=VERSION,configuration=config,requiredContents=required,evidence=explicit or {'source':'exact_asin_catalog'},result='match',reason='',code=None)
    def decide(outcome,reason,code='contents_not_corroborated'):
        return {**result,'result':outcome,'reason':reason,'code':code}
    if contradiction or attrs.get('package_evidence_conflict'):
        return decide('review','Amazon package configuration unresolved: exact-ASIN sources contradict.')
    if config=='unresolved':
        return decide('review','Amazon package configuration unresolved.')
    if config=='software_only' and (listed_bundle or extra_components):
        return decide('conflict','Package mismatch: accessory bundle offered against software-only Amazon ASIN.','package_mismatch')
    if config=='ordinary_software' and (listed_bundle or extra_components):
        return decide('review','Purchasing unit package configuration unresolved: additional physical components disclosed.')
    if accessory_only:
        return decide('conflict','Required game is missing from purchasing unit.','contents_confirmed_missing')
    if config=='bundle' and unit_only:
        return decide('conflict','Package mismatch: game only offered against accessory-bundle ASIN.','contents_confirmed_missing')
    if not required:
        if config=='bundle':
            return decide('review','Required bundle contents not corroborated; exact-ASIN manifest unresolved.')
        return result
    for part in required:
        name=part['name'];pattern=component_pattern(name)
        if absent(text,pattern) or unit_only:
            return decide('conflict',f'Required {name} is explicitly missing.','contents_confirmed_missing')
        if re.search(r'\b(?:replacement|reproduced|printable|downloadable|third.party)\s+(?:(?:original|ar)\s+)?'+pattern+r'\b',text):
            return decide('review',f'Required original {name} not corroborated; replacement evidence only.')
        if re.search(r'\b'+pattern+r'\s+(?:is\s+)?(?:a\s+)?(?:replacement|reproduction|printout|reprint)\b',text):
            return decide('review',f'Required original {name} not corroborated; replacement evidence only.')
    if unit_only and listed_bundle:
        return decide('conflict','Purchasing unit has contradictory package configuration.','package_mismatch')
    safe_identity=all(comparisons[k]['result']=='match' for k in ('coreGame','platform')) and not any(v['result']=='conflict' for v in comparisons.values())
    # Factory seal is useful only with exact retail-package identity, rather than
    # a generic sealed software claim. Explicit missing/replacement claims above win.
    original_sealed=bool(re.search(r'\b(?:original|manufacturer)\s+(?:factory[- ]sealed|unopened)\s+retail\s+(?:box|package)\b|\bfactory[- ]sealed\s+original\s+retail\s+(?:box|package)\b',text))
    sealed_package=original_sealed and safe_identity and exact_identifier and (config!='bundle' or listed_bundle)
    if inferred_manifest and not sealed_package:
        return decide('review','Required bundle contents not corroborated; exact-ASIN manifest is incomplete.')
    for part in required:
        name=part['name'];pattern=component_pattern(name)
        if not sealed_package and not included(text,pattern):
            return decide('review',f'Required {name} not corroborated.')
        if part.get('model') and not sealed_package and plain(part['model']) not in text:
            return decide('review',f'Required {name} model not corroborated.')
        if part.get('quantity',1)>1 and not sealed_package and not re.search(r'\b'+str(part['quantity'])+r'\s+'+pattern,text):
            return decide('review',f'Required quantity of {name} not corroborated.')
        if name in {'guitar controller','portal','base','sensor','dance mat'} and included(text,pattern):
            # Explicit platform attached to hardware must agree. Missing hardware
            # platform requires review unless exact unopened SKU corroborates it.
            from system_detection import detect_system_from_title, SYSTEM_ALIASES
            hardware=[m.group(0) for m in re.finditer(r'[^.!?]*'+pattern+r'[^.!?]*',text)
                      if re.search(r'\b(?:includes?|contains?|comes with|complete with|included)\b',m.group(0))]
            platforms=[]
            for sentence in hardware:
                # Longest aliases consume their spans before generic PS/Xbox/Wii,
                # retaining two explicitly different hardware platforms.
                remaining=sentence
                aliases=sorted([(a,p) for p,aa in SYSTEM_ALIASES.items() for a in aa],key=lambda row:len(row[0]),reverse=True)
                for alias,platform in aliases:
                    pattern_alias=r'(?<![a-z0-9])'+re.escape(alias)+r'(?![a-z0-9])'
                    if re.search(pattern_alias,remaining):
                        platforms.append(platform)
                        remaining=re.sub(pattern_alias,' ',remaining)
            if any(p and p!=normalize_system(catalog.get('normalized_platform')) for p in platforms):
                return decide('conflict',f'Required {name} has incompatible platform.','package_mismatch')
            if not any(platforms) and not sealed_package:
                return decide('review',f'Required {name} platform not corroborated.')
    return result
