"""Derived listing text and conservative evidence scopes; never fetch resources."""
from html.parser import HTMLParser
import re

NON_CONTENT = {'style', 'script', 'template', 'head'}
BOUNDARIES = {'p', 'div', 'br', 'hr', 'li', 'ul', 'ol', 'tr', 'td', 'th', 'table',
              'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'section', 'article', 'header', 'footer', 'nav', 'a'}

class ListingTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.hidden = [], []
    def boundary(self):
        if self.parts and self.parts[-1] != '\n':
            self.parts.append('\n')
    def handle_starttag(self, tag, attrs):
        if tag in NON_CONTENT:
            self.hidden.append(tag)
        elif not self.hidden and tag in BOUNDARIES:
            self.boundary()
    def handle_startendtag(self, tag, attrs):
        if not self.hidden and tag in BOUNDARIES:
            self.boundary()
    def handle_endtag(self, tag):
        if tag in self.hidden:
            self.hidden = self.hidden[:len(self.hidden)-1-self.hidden[::-1].index(tag)]
        elif not self.hidden and tag in BOUNDARIES:
            self.boundary()
    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def readable_listing_text(value):
    parser = ListingTextParser()
    parser.feed(str(value or ''))
    parser.close()
    # Decode once: escaped markup must not be interpreted as executable HTML.
    lines = [re.sub(r'\s+', ' ', line).strip() for line in ''.join(parser.parts).splitlines()]
    return '\n'.join(line for line in lines if line), bool(parser.hidden)


def evidence_scope(text):
    """Only demonstrably generic marketing/navigation is non-product evidence.

    Categorical policies, mixed inventory, ambiguous prose, disclosures and
    ordinary product text are kept. Seller names/classes never select scope.
    """
    value = text.casefold().strip()
    if re.search(r'\b(?:(?:all|every)\s+(?:of\s+)?(?:our\s+|the\s+)?(?:offered\s+)?(?:items?|merchandise|products?|games?|inventory)\b.{0,45}\b(?:are|is|have|has)\b.{0,25}(?:used|pre[- ]owned|opened|unsealed)|we\s+(?:only|exclusively)\s+(?:sell|stock|offer)\s+(?:used|pre[- ]owned|opened|unsealed))\b', value):
        return 'seller_policy', 'Categorical condition policy retained for the offered merchandise.'
    if re.search(r'\b(?:mixed\s+new|new\s*(?:and|&|/)\s*used)\b', value):
        return 'mixed_inventory', 'Mixed inventory is retained for purchasing-unit and condition review.'
    marketing = [
        r'^welcome to .{0,100}\b(?:ebay\s+)?store\b.{0,100}\bbest deals\b.{0,60}\bpre[- ]owned tech\.?$',
        r'^pre[- ]owned tech(?:\s+from\s+[^.!?]{1,80})?[:.!]?$',
        r'^your new home for pre[- ]owned tech[.!]?$',
        r'^shop thousands of high[- ]quality pre[- ]owned devices\b.{0,160}\bfraction of the price of buying new\.?$',
        r'^shop pre[- ]owned tech[.!]?$',
        r'^(?:visit|shop|browse|check out)\s+(?:our|the)\s+(?:store|shop)\b.{0,100}\b(?:promo(?:tional)?\s+(?:deals|offers)|promotions)\b[.!]?$',
    ]
    if any(re.fullmatch(pattern, value) for pattern in marketing):
        return 'seller_advertising', 'Generic shop marketing/navigation does not describe the offered product.'
    return 'product_or_unresolved', 'Readable evidence retained; no affirmative non-product scope established.'


def prepare_listing_description(*values):
    blocks, incomplete = [], False
    for value in values:
        readable, damaged = readable_listing_text(value)
        incomplete |= damaged
        for line in readable.splitlines():
            # Sentence splitting keeps a specific disclosure following shop prose.
            for text in re.split(r'(?<=[.!?])\s+(?=[A-Z])', line):
                scope, reason = evidence_scope(text)
                blocks.append({'text': text, 'scope': scope, 'reason': reason})
    return {'version': 'listing_text_scope_v1', 'readable_text': '\n'.join(b['text'] for b in blocks),
            'product_text': '\n'.join(b['text'] for b in blocks if b['scope'] != 'seller_advertising'),
            'blocks': blocks, 'incomplete_markup': incomplete}
