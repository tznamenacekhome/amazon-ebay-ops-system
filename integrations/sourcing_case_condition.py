"""Affirmative offered-case damage; no testing or packaging-colour policy."""
import html
import re


def case_damage_hits(title, description, negated):
    text = html.unescape(re.sub(r'<[^>]+>', ' ', f'{title}. {description}')).casefold()
    case = r'(?:(?:jewel|game|plastic|disc)\s+)?cases?'
    pattern = re.compile(r'\b(?:'
        r'(?:visible\s+)?cracks?\s+(?:on|in|to|at|along)\s+(?:the\s+|a\s+)?' + case +
        r'|' + case + r'\s+(?:(?:is|are|has|have|with|shows)\s+)?(?:(?:a|some|also|visible|small|minor|hairline)\s+)*(?:cracks?|cracked)'
        r'|cracked\s+(?:corner\s+of\s+(?:the\s+)?)?' + case + r')\b')
    hits = []
    for match in pattern.finditer(text):
        start = max(text.rfind('.', 0, match.start()), text.rfind('!', 0, match.start()), text.rfind(';', 0, match.start())) + 1
        end = re.search(r'[.!;]', text[match.end():])
        before = text[start:match.start()]
        after = text[match.end():match.end() + (end.start() if end else 120)]
        # Explicit other-product subjects are not offered-item disclosures. A
        # specific current-copy subject prevents this narrow boilerplate escape.
        unrelated = re.search(r'\b(?:other|another)\s+(?:games?|items?|copies|copy|merchandise|products?)\b|\b(?:phone|tablet|camera|laptop)\s*$', before)
        specific = re.search(r'\b(?:this|offered|current)\s+(?:game|copy|item|case)\b', before)
        if unrelated and not specific:
            continue
        if re.match(r'\s+(?:on|of|for)\s+(?:another|other)\s+(?:game|item|product)\b', after):
            continue
        if negated(text, match) or re.search(r'\bfree\s+(?:from|of)\s+(?:(?:any|visible)\s+)*$', before):
            continue
        hits.append(match[0])
    return list(dict.fromkeys(hits))
