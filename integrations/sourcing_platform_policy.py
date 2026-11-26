"""Shared configurable business eligibility, independent of product matching."""
import json
import re
from pathlib import Path
from system_detection import canonical_systems

POLICY = json.loads((Path(__file__).resolve().parents[1] / 'web/lib/sourcingPlatformPolicy.json').read_text())
CARTRIDGE_PLATFORMS = frozenset(POLICY['excludedCartridgePlatforms'])


def platform_eligibility(seed, candidate=None):
    seed, candidate = seed or {}, candidate or {}
    context = seed.get('raw_context_json') or {}
    catalog = context.get('amazon_catalog_identity') or {}
    if catalog and catalog.get('asin') and str(catalog['asin']).upper() != str(seed.get('asin') or '').upper():
        catalog = {}
    attrs = catalog.get('relevant_attributes_json') or {}
    observations = [catalog.get('normalized_platform'), attrs.get('platform'), seed.get('system'), context.get('inferred_system')]
    systems = {system for value in observations for system in canonical_systems(value)}
    if not systems:
        systems.update(canonical_systems(seed.get('amazon_title')))
    # Candidate observations may deny eligibility but cannot supply missing exact
    # Amazon identity or waive an Amazon-side restriction.
    candidate_systems = set()
    for aspect in (candidate.get('raw_ebay_json') or {}).get('localizedAspects', []):
        if str(aspect.get('name') or '').casefold() == 'platform':
            candidate_systems.update(canonical_systems(aspect.get('value')))
    known = systems | candidate_systems
    def result(status, reason):
        return {'version': POLICY['version'], 'result': status, 'reason': reason,
                'platforms': sorted(known), 'source': 'shared sourcing platform business policy'}
    if known & CARTRIDGE_PLATFORMS:
        return result('blocked', POLICY['cartridgeReason'])
    if not systems or len(systems) != 1:
        return result('unresolved', POLICY['unresolvedReason'])
    system = next(iter(systems))
    if system in POLICY['mixedFormatPlatforms']:
        # Only explicit product-specific physical format observations can resolve
        # mixed hardware. A generic cartridge console's bad DVD-ROM catalog label
        # never overrides the cartridge-only platform set above.
        formats = [attrs.get('format'), catalog.get('normalized_format'), attrs.get('platform'), catalog.get('normalized_platform')]
        formats += [attrs.get(key) for key in ('media_type', 'physical_format')]
        formats += re.findall(r'\b(?:CD-ROM|DVD-ROM|cartridge|HuCard|disc)\b', str(seed.get('amazon_title') or ''), re.I)
        text = ' '.join(str(v or '') for v in formats)
        cartridge = bool(re.search(r'\bcartridge\b|\bhu[ -]?card\b|\bcard\b', text + ' ' + str(candidate.get('ebay_title') or ''), re.I))
        disc = bool(re.search(r'\b(?:cd(?:[ _-]?rom)?|dvd(?:[ _-]?rom)?|blu[ -]?ray|disc)\b', text, re.I))
        explicit_format = ' '.join(str(v or '') for v in [attrs.get('physical_format'), attrs.get('media_type'),
            attrs.get('platform'), catalog.get('normalized_platform'),
            *re.findall(r'\b(?:CD-ROM|DVD-ROM|disc)\b', str(seed.get('amazon_title') or ''), re.I)])
        explicit_disc = bool(re.search(r'\b(?:cd(?:[ _-]?rom)?|dvd(?:[ _-]?rom)?|blu[ -]?ray|disc)\b', explicit_format, re.I))
        if cartridge:
            return result('blocked', POLICY['cartridgeReason'])
        if not disc or not explicit_disc:
            return result('unresolved', POLICY['unresolvedReason'])
        return result('pass', 'Product-specific disc format; normal sourcing safeguards still apply.')
    if system in POLICY['exceptionPlatforms'] or system in POLICY['discOrComputerPlatforms']:
        return result('pass', 'Platform permitted; normal sourcing safeguards still apply.')
    return result('unresolved', POLICY['unresolvedReason'])
