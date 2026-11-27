"""Offered-product wrapping disclosures: review uncertainty, preserve hard facts."""
import html
import re

WRAP = r'(?:(?:factory|security|plastic)\s+)?seal|(?:shrink|cello(?:phane)?)\s*[- ]?\s*wrap(?:ping)?|cellophane|wrapp?er|wrap|plastic'
DAMAGE = r'(?:tears?|holes?|punctures?|rips?)'
PATTERN = re.compile(r'\b(?:'
    + DAMAGE + r'\s+(?:in|on|through|to|of)\s+(?:the\s+|its\s+|a\s+)?(?:original\s+)?(?:' + WRAP + r')'
    + r'|(?:' + WRAP + r')\s+(?:(?:is|are|has|have|shows|with|contains)\s+)?(?:(?:a|some|few|several|small|minor|tiny|visible|no|not|any|normal|factory|vent|breather|air)\s+)*'
    + r'(?:tears?|holes?|punctures?|rips?|torn|punctured|ripped)'
    + r'|(?:torn|punctured|ripped)\s+(?:' + WRAP + r'))\b', re.I)
SEVERE = re.compile(r'\b(?:(?:factory|security)\s+seal\s+(?:(?:is|has been)\s+)?(?:removed|missing|broken)'
                     r'|(?:all|entire)\s+(?:original\s+)?shrink\s*[- ]?wrap\s+(?:(?:is|was|has been)\s+)?removed)\b', re.I)


def _scope(text, match, negated):
    start = max(text.rfind(mark, 0, match.start()) for mark in '.!?;\n') + 1
    end = re.search(r'[.!?;\n]', text[match.end():])
    before = text[start:match.start()]
    after = text[match.end():match.end() + (end.start() if end else 180)]
    phrase = match[0]
    sentence = before + phrase + after
    specific = bool(re.search(r'\b(?:this|offered|current)\s+(?:game|item|copy|product|seal|wrap)\b', before, re.I))
    if re.search(r'\b(?:other|another|some)\s+(?:games?|items?|copies|copy|merchandise|products?|inventory)\b|\b(?:phone|tablet|camera|laptop)\b', before, re.I) and not specific:
        return False
    if re.match(r'\s+(?:on|of|for)\s+(?:another|other)\s+(?:game|item|product)\b', after, re.I):
        return False
    # A hypothetical shipping/return policy is not an observed disclosure.
    if re.search(r'\b(?:if|should)\b', before, re.I):
        return False
    if re.search(r'\b(?:may|might|could)\b', before + phrase, re.I) and not specific:
        return False
    if re.search(r'\b(?:sometimes|occasionally|common in our|we sell items with|we stock items with)\b', sentence, re.I) and not specific:
        return False
    if not specific and (re.search(r'\b(?:returns?|report|notify)\b', before, re.I) or re.match(r'\s+(?:should|must)\s+be\s+reported\b', after, re.I)):
        return False
    if re.search(r'\b(?:no|without)\s+(?:tears?|holes?|punctures?|rips?)\s+(?:or|and)\s*$', before, re.I):
        return False
    defect = r'(?:tears?|holes?|punctures?|rips?|torn|punctured|ripped)'
    if re.search(r'\b(?:free from|free of)\s+(?:any\s+)?$', before, re.I):
        return False
    if re.search(r'\b(?:no|not|without)\s+(?:(?:a|any|small|minor|tiny|visible)\s+)*$', before, re.I):
        return False
    if re.search(r'\b(?:no|not|without|free from|free of)\s+(?:(?:any|visible|signs of|evidence of)\s+)*' + defect, phrase, re.I):
        return False
    # Use the existing negation semantics; preserve explicit current-copy
    # uncertainty for review rather than suppressing it as generic boilerplate.
    negative = negated(text, match)
    if re.match(r'\s+(?:is|are)\s+not\s+(?:normal\s+)?factory\s+(?:vents?|vent holes?)\b', after, re.I) and not re.search(r'\b(?:no|without|never)\s*$', before, re.I):
        negative = False
    if negative and not (specific and re.search(r'\b(?:may|might|could)\b', before, re.I) and not re.search(r'\b(?:no|not|without|never)\b', before[-35:], re.I)):
        return False
    return True


def wrapping_disclosures(title, description, negated):
    result = {'review': [], 'unacceptable': []}
    for source, value in [('title', title), ('description', description)]:
        text = html.unescape(re.sub(r'<[^>]+>', ' ', str(value or ''))).casefold()
        for pattern, kind in [(PATTERN, 'review'), (SEVERE, 'unacceptable')]:
            for match in pattern.finditer(text):
                if not _scope(text, match, negated):
                    continue
                before = text[max(0, match.start()-55):match.start()]
                after = text[match.end():match.end()+65]
                # Exempt only clearly identified normal vent holes, not another
                # tear/puncture elsewhere in the same sentence.
                vent_before = re.search(r"\b(?:normal\s+)?(?:factory(?:[- ]made)?|manufacturer(?:'s)?)\s+(?:vent(?:ilation)?|breather|air)\s*[- ]?\s*$", before, re.I)
                vent_inside = re.search(r'\b(?:normal\s+)?factory\s+(?:vent|breather|air)\s+holes?\b', match[0], re.I)
                vent_after = re.match(r'\s+(?:are|is)\s+(?:normal\s+)?factory\s+(?:vents?|vent holes?|breather holes?)\b', after, re.I)
                if kind == 'review' and 'hole' in match[0] and (vent_before or vent_inside or vent_after) and not re.search(r'\b(?:oversized|enlarged|abnormal|not normal)\b', before[-70:] + match[0] + after[:65], re.I):
                    continue
                entry = {'source': source, 'text': match[0], 'classification': kind,
                         'scope': 'offered product or unresolved specific wrapping disclosure'}
                if entry not in result[kind]:
                    result[kind].append(entry)
    return result
