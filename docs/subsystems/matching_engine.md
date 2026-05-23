# Matching Engine

# Purpose

The matching engine enriches purchase_items using RevSeller Google Sheet data
and operator-confirmed manual matches.

Primary goals:
- assign ASINs
- assign target sell prices
- minimize incorrect matches
- support future automation

---

# Core Rules

## Video Games Are Platform-Specific

Never auto-match across systems.

Examples:
- Minecraft PS4 != Minecraft Switch
- Madden Xbox != Madden PS5

---

# Current Matching Rules

## Preferred Match

Match:
- normalized title
- normalized system

## Compact Same-System Fallback

If normalized title + system does not match exactly, RevSeller enrichment also
checks a compact title key with spaces and punctuation removed.

This fallback is only accepted when:
- the system matches
- the compact title key maps to exactly one ASIN in the RevSeller sheet

Example:
- eBay: `Farcry New Dawn XBox One`
- RevSeller: `Far Cry New Dawn - Xbox One Standard Edition`
- compact key: `farcrynewdawn`

This catches spacing/compound-word variants without matching across systems.

## Manual Match Memory

When an operator manually adds an ASIN or target sell price in the purchases UI,
the API updates matching purchase_items with the same normalized title and
system. Rows with an existing different ASIN are skipped.

Manual corrections are stored in:
- `manual_item_matches`

The RevSeller enrichment script loads these manual rows together with Google
Sheet rows, so future purchases of the same title/system can be enriched even
when the game is missing from the RevSeller sheet.

---

# Title Cleaning

Reusable marketplace-title cleaning is named:
- Python: `clean_marketplace_title_for_search`
- Frontend TypeScript: `cleanMarketplaceTitleForSearch`

Purpose:
- clean eBay/marketplace titles before Amazon search
- provide a shared preprocessing step before RevSeller matching/future fuzzy matching
- support future Amazon catalog search automation

Current behavior:
- removes common condition and shipping terms
- removes release years inside parenthetical system patterns
- preserves useful system/platform words
- moves leading system/platform terms to the end of the search query
- normalizes punctuation and separators

Examples:
- `PS5 Playstation 5 Battlefield 2042 BRAND NEW FACTORY SEALED READ`
  -> `Battlefield 2042 PS5 Playstation 5`
- `NEW: Country Dance (Nintendo Wii, 2011) FREE SHIPPING`
  -> `Country Dance Nintendo Wii`
- `Destiny: The Collection | Brand New/Sealed | Sony PlayStation 4`
  -> `Destiny The Collection PlayStation 4`

RevSeller enrichment uses the Python cleaner before normalized title matching.
