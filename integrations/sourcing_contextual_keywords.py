"""Bounded lexical evidence roles; never a game identity or package approval."""
import re
from video_game_identity import general_product_fields
from sourcing_identity_wording import core_pattern, complete_name_context


def _mask_named_term(text, phrase, term):
    def replace(match):
        return re.sub(r'(?<![a-z0-9])'+re.escape(term)+r'(?![a-z0-9])', 'MBOP_NAMED_WORD', match[0], flags=re.I)
    return re.sub(core_pattern(phrase), replace, text, flags=re.I)


def contextual_keyword_text(candidate, seed, evidence, identity):
    search = str(evidence.get('searchable_text') or '')
    title = str(candidate.get('ebay_title') or '')
    roles = []
    # Generic retailer vocabulary does not offer a game carry service. Any
    # separate carry/service occurrence remains visible to the same block list.
    carry = r'\bbrands?\s+(?:that\s+)?we\s+carry\b'
    def stock_role(match):
        roles.append({'term':'carry','role':'seller_stock_policy','source':'description','text':match[0]})
        return re.sub(r'\bcarry\b','MBOP_STOCK_VERB',match[0],flags=re.I)
    search = re.sub(carry, stock_role, search, flags=re.I)
    software = '139973' in set(map(str,evidence.get('category_ids') or []))
    platform_match = ((identity or {}).get('comparisons') or {}).get('platform',{}).get('result') == 'match'
    if not software or not platform_match:
        return {'digital_text':search,'accessory_title':title,'roles':roles,'requires_kit_review':False}
    ebay = identity['ebay'];amazon=identity['amazon']
    context = complete_name_context(evidence,general_product_fields)
    if context and ebay['fields']['coreGame']['state']=='supported' and context[1]==ebay.get('coreGame') and re.search(r'\brune\s+factory\b',context[1],re.I):
        updated=_mask_named_term(search,context[1],'rune')
        if updated!=search:roles.append({'term':'rune','role':'corroborated_game_name','source':'title/game_name','text':context[1]})
        search=updated
    # Puzzle gameplay describes matching jewels, not buying currency. Other
    # gems occurrences (including offers/prices) remain untouched and blocking.
    genre=' '.join((evidence.get('aspects')or{}).get('genre')or[])
    if context and 'puzzle' in genre.casefold() and context[1]==amazon.get('coreGame') and re.search(core_pattern(context[1]),title,re.I):
        def puzzle_role(match):
            roles.append({'term':'gems','role':'puzzle_gameplay','source':'description','text':match[0]})
            return re.sub(r'\bgems\b','MBOP_PUZZLE_PIECES',match[0],flags=re.I)
        search=re.sub(r'\b(?:match|swap)\s+gems\b',puzzle_role,search,flags=re.I)
    # A generic catalog media suffix is not used here to clear an identity or
    # edition dispute; it only corroborates the full software name for this word.
    named=ebay.get('coreGame')or'';catalog_name=amazon.get('coreGame')or''
    if re.search(r'\((?:CD|DVD)[- ]ROM\)\s*$',str(seed.get('amazon_title')or''),re.I):
        catalog_name=re.sub(r'\s+(?:cd|dvd)\s+rom$','',catalog_name)
    if named and named==catalog_name and ebay['fields']['coreGame']['state']=='supported':
        updated=_mask_named_term(title,named,'helmet')
        if updated!=title:roles.append({'term':'helmet','role':'corroborated_game_name','source':'title','text':named})
        title=updated
    # Toy-Con is a named physical kit family, not automatically a complete kit.
    # Without existing exact-ASIN required-contents proof, mandatory review stays.
    original=str(candidate.get('ebay_title')or'')
    kit=bool(re.search(r'\blabo\b',original,re.I) and re.search(r'\btoy[- ]con\b',original,re.I) and re.search(r'\bkit\b',original,re.I))
    contrary=re.search(r'\b(?:replacement|accessory only|cardboard only|no game|no software|game not included|software not included)\b',evidence.get('searchable_text')or'',re.I)
    if kit and not contrary:
        title=re.sub(r'\btoy(?=[- ]con\b)','MBOP_KIT_FAMILY',title,flags=re.I)
        roles.append({'term':'toy','role':'physical_game_kit_name','source':'title','text':'Toy-Con; exact-ASIN kit completeness remains required'})
    return {'digital_text':search,'accessory_title':title,'roles':roles,'requires_kit_review':kit and not contrary}
