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

## Leading Condition Variant Fallback

If normalized title + system and compact title + system do not match, RevSeller
enrichment can try a condition-noise variant that removes a leading or trailing
`new`.

This fallback is only accepted when:
- the system matches
- the normal exact or compact same-system match succeeds after removing leading `new`

Reason:
eBay sellers often use title prefixes such as `New Hitman 3`, while RevSeller
stores the catalog title as `Hitman 3 - PlayStation 5 Standard Edition`.
The fallback is deliberately narrow so real game titles that begin with `New`
are not globally rewritten before normal matching.

Example:
- eBay: `New Hitman 3 (Sony PlayStation 5 PS5, 2021)`
- RevSeller: `Hitman 3 - PlayStation 5 Standard Edition`
- system: `PS 5`
- result: ASIN `B08MG5FYS6`

Trailing condition example:
- eBay: `My Little Pony: A Zephyr Heights Mystery Xbox Series X & Xbox One new`
- RevSeller: `My Little Pony: A Zephyr Heights Mystery - Xbox Series X`
- system: `Xbox Series X`
- result: ASIN `B0CXF5QZC8`

## Catalog Connector Variant Fallback

RevSeller enrichment indexes safe title variants from the RevSeller sheet as
well as purchase items. This includes removing a trailing connector word `for`
from a catalog title when the system is already detected separately.

Reason:
Catalog titles often use phrasing such as `ARK Ultimate Survivor Edition for
PlayStation 4`, while eBay titles may omit `for` and include publisher noise.

Example:
- eBay: `ARK: Ultimate Survior Edition Studio Wildcard PlayStation 4`
- RevSeller: `ARK Ultimate Survivor Edition for PlayStation 4`
- system: `PS 4`
- result: ASIN `B09KVJKH7V`

## Token-Set Same-System Fallback

If exact and compact same-system matching still fail, RevSeller enrichment can
compare the sorted unique title tokens for the same system.

This fallback is only accepted when:
- the system matches
- the token-set key maps to exactly one ASIN in the RevSeller sheet

Reason:
Some eBay titles use different word order than the catalog title.

Example:
- eBay: `Rock Band the Beatles - Nintendo Wii`
- RevSeller: `The Beatles: Rock Band (Game Only) - Nintendo Wii`
- token set: `band beatles rock the`
- system: `Wii`
- result: ASIN `B001TOQ8LG`

## AI Same-System Review

After deterministic matching fails, RevSeller enrichment can optionally call
OpenAI with `--ai-review`.

This is a conservative second-pass reviewer, not a free-form matcher:
- AI only sees RevSeller candidates already filtered to the same detected system.
- Candidates are pre-ranked locally by normalized title, compact title, and
  token-set similarity.
- AI must return structured JSON with `match` or `no_match`.
- MBOP accepts the match only when the selected candidate index is one of the
  supplied candidates and confidence is at or above the configured threshold
  (`0.86` by default).
- AI is never allowed to invent an ASIN, change system, change price/cost, or
  match across platforms.
- If `OPENAI_API_KEY` is missing, the enrichment safely skips AI review and
  falls back to deterministic matching only.

Scheduled sync runs AI review with a small per-run cap so it can improve fuzzy
coverage without turning the daily purchase sync into a broad AI batch job. AI
review calls are limited to open purchase-work rows; deterministic matching may
still enrich older workflow rows without spending AI calls. AI matches are
written into the diagnostics CSV with selected ASIN/title, confidence, and
reason for auditability.

## Manual Match Memory

When an operator manually adds an ASIN or target sell price in the purchases UI,
the API updates matching purchase_items with the same normalized title and
system. Rows with an existing different ASIN are skipped.

Manual corrections are stored in:
- `manual_item_matches`

The RevSeller enrichment script loads these manual rows together with Google
Sheet rows, so future purchases of the same title/system can be enriched even
when the game is missing from the RevSeller sheet. The scheduled RevSeller pass
only scans Open Purchase Work rows: Listed, Cancelled, Return Opened, and Return
Pending rows are excluded from deterministic and AI matching, and rows marked
`exclude_from_purchase_reporting` are skipped the same way they are skipped by
the default Purchases list.

## Legacy Purchases Sheet Backfill

Historical spreadsheet data can be imported with:
- `integrations/backfill_purchase_items_from_purchase_sheet.py`

Source:
- Google Sheet: `ebay purchases`
- tab: `Purchases`

The script:
- parses an exported `.xlsx` workbook with `openpyxl`
- matches purchase_items by eBay order number
- disambiguates multi-row orders with normalized title and system
- updates missing ASIN, amazon_title, and target sell price
- skips ambiguous or missing order matches

Latest run:
- filled 340 ASINs
- filled 2,141 target sell prices
- left 37 missing ASINs and 62 missing target sell prices

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
