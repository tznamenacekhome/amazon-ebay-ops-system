"""Conservative seller-lot interpretation, never bundle allocation or pricing."""
import html
import re
from decimal import Decimal, InvalidOperation


def purchase_unit_evidence(candidate, evidence, identity=None):
    title = str(candidate.get('ebay_title') or '')
    description = html.unescape(re.sub(r'<[^>]+>', ' ', str(evidence.get('description') or '')))
    text = re.sub(r'\s+', ' ', description)
    raw = candidate.get('raw_ebay_json') or {}
    lot = r'\b(?:lot|bundle|set)\s+(?:of\s+)?\d+\s+(?:video\s+)?games?\b|\b(?:video\s+)?game\s+lot\b'
    selection = r'\b(?:choose|select|pick)\s+(?:your\s+|a\s+|the\s+)?(?:game|title|variation)\b'
    mixed = r'\bmixed\s+new\s*(?:and|&|/)\s*used\s+(?:video\s+)?(?:games|inventory)\b'
    signals = [m[0] for m in re.finditer(lot + '|' + selection + '|' + mixed + r'|\bindividually priced\b|\bbundle deals\b', title + '. ' + text, re.I)]
    if not signals:
        return {'version': 'purchase_unit_v1', 'result': 'pass', 'kind': 'ordinary_listing', 'reason': 'No seller lot or selection ambiguity observed.'}
    def review(reason):
        return {'version': 'purchase_unit_v1', 'result': 'review', 'kind': 'unresolved_lot_or_selection',
                'reason': reason, 'signals': signals, 'pricingBasis': 'unverified; no allocation or replacement price computed'}
    if re.search(lot + '|' + selection, title, re.I):
        return review('Purchase unit review — title offers a lot or unresolved game selection for a single-ASIN proposal.')
    if any(raw.get(k) for k in ('variationAspects', 'itemGroupType', 'primaryItemGroup')) or re.search(selection, text, re.I):
        return review('Purchase unit review — selectable listing configuration is not independently resolved.')
    core = ((identity or {}).get('ebay') or {}).get('coreGame')
    comparison = ((identity or {}).get('comparisons') or {}).get('coreGame') or {}
    if comparison.get('result') != 'match' or not core:
        return review('Purchase unit review — individual offered game identity is not established.')
    # Only an explicit named individual price can bind a boilerplate multi-game
    # description to this fixed-price listing. Never divide a lot total.
    name = r'\W+'.join(re.escape(t) for t in re.findall(r'[a-z0-9]+', core.casefold()))
    if re.search(mixed, text, re.I) and not re.search(r'(?<!\w)' + name + r'(?!\w)\s*(?:\(\s*\$\d+(?:\.\d{1,2})?\s*\))?\s*(?:is|:|-)?\s*(?:brand new|factory sealed)\b', text, re.I):
        return review('Purchase unit review — specific-game New condition within mixed inventory is not established.')
    quotes = re.findall(r'(?<!\w)' + name + r'(?!\w)\s*\(\s*\$\s*(\d+(?:\.\d{1,2})?)\s*\)', text, re.I)
    if not re.search(r'\bindividually priced\b', text, re.I) or not quotes:
        return review('Purchase unit review — no explicit individual-game price binds the description to the listing price.')
    try:
        prices = {Decimal(q) for q in quotes}
        price = Decimal(str(candidate.get('price')))
        raw_price = raw.get('price') or {}
        if not price.is_finite() or price <= 0 or prices != {price} or not raw_price or (
                raw_price.get('currency') != 'USD' or Decimal(str(raw_price.get('value'))) != price):
            return review('Purchase unit review — named-game and provider prices do not unambiguously agree.')
        available = Decimal(str(candidate.get('available_quantity')))
    except (InvalidOperation, TypeError, ValueError):
        return review('Purchase unit review — price or availability is unresolved.')
    if not available.is_finite() or available <= 0 or candidate.get('listing_status') == 'ended' or 'FIXED_PRICE' not in (candidate.get('buying_options') or []):
        return review('Purchase unit review — available fixed-price individual unit is not established.')
    if any(str(row.get('estimatedAvailabilityStatus') or '').upper() in {'OUT_OF_STOCK','SOLD_OUT'}
           for row in raw.get('estimatedAvailabilities') or []):
        return review('Purchase unit review — provider availability contradicts the individual-unit observation.')
    return {'version': 'purchase_unit_v1', 'result': 'pass', 'kind': 'individual_with_seller_inventory_description',
            'reason': 'Complete game identity, explicitly individually priced name and current fixed price agree; an individual unit is available.',
            'signals': signals, 'namedPrices': quotes, 'price': str(price), 'quantityAvailable': str(available),
            'pricingBasis': 'provider individual item price; no lot allocation',
            'conditionBasis': 'Independent specific-item condition safeguards; generic testing is not a condition signal.'}
