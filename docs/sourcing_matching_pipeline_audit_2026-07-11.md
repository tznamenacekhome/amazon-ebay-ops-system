# Amazon ASIN -> eBay Matching Pipeline Audit

Date: 2026-07-11

Scope: Amazon ASIN -> eBay sourcing listing matching quality. This is an audit
only. No matching rules, AI calls, model training, eBay-to-Amazon sourcing,
purchase, bid, offer, or sourcing workspace rewrite was implemented.

Note: `CODEX_PROMPTING_GUIDE_v3.md` was requested but was not present in the
repository root or in `rg --files` results. The audit follows `AGENTS.md`,
current project docs, and sourcing/matching documentation.

## Executive Finding

MBOP already stores enough evidence to block many obvious false positives, but
important evidence is either not normalized or not consumed by scoring.

The largest current quality issue is not lack of AI. It is deterministic data
flow loss:

- Seed platform can be inferred and stored under
  `sourcing_seed_asins.raw_context_json.inferred_system`, and eBay search uses
  it, but the scoring platform rule ignores it.
- eBay Browse `localizedAspects.Platform`, `Game Name`, `Region Code`,
  `Format`, `Type`, and related item specifics are usually stored raw but are
  not parsed into structured matcher inputs.
- eBay category evidence is stored, but the hard-block category list is too
  narrow and misses common accessory/non-game categories.
- Images are stored abundantly but are not used for matching.
- Seller descriptions are sometimes stored and are included in keyword search,
  but they are not normalized into durable diagnostic signals.

## Data Reviewed

Queries were read-only against Supabase using `.env.local`.

- Recent opportunity sample: 1,000 newest `sourcing_opportunities` with joined
  seed and candidate rows.
- Recent action sample: 1,200 newest `sourcing_actions`.
- Recent dismissed false-positive review: 300 newest dismissed actions with
  joined opportunities, filtered to 222 identity/condition dismissals.

Recent opportunity statuses in the 1,000-row sample:

| Status | Count |
| --- | ---: |
| rejected | 919 |
| open | 54 |
| dismissed | 23 |
| watching | 4 |

Recent action dismiss reasons in the action sample:

| Dismiss Reason | Count |
| --- | ---: |
| wrong_product | 110 |
| no_longer_available | 83 |
| wrong_edition_version | 70 |
| digital_item | 29 |
| wrong_platform | 27 |
| missing_shrink_wrap | 15 |
| packaging_condition_issue | 9 |
| other | 9 |
| incomplete_product | 8 |
| packaging_damage | 7 |
| sales_velocity_too_low | 4 |
| suspected_reseal | 1 |
| non_north_american_version | 1 |

## Phase 1 - Pipeline Audit

```
Amazon sales/listings/Keepa
  -> sourcing_seed_asins
  -> eBay Browse API search
  -> sourcing_ebay_candidates
  -> deterministic static rules + matching intelligence
  -> score_sourcing_opportunities
  -> sourcing_opportunities
  -> /api/sourcing/opportunities
  -> Sourcing workspace
```

### Amazon / Seed ASIN

What exists:

- Amazon title, ASIN, seller SKU, sales/velocity, target price, listing warning
  context, inferred platform context, and Amazon image.
- Amazon image is fetched from latest Amazon listing snapshots or Keepa.
- Platform is inferred from title, Amazon listing product name, Keepa title,
  product group, or Keepa category tree.

Where stored:

- `sourcing_seed_asins.amazon_title`
- `sourcing_seed_asins.amazon_image_url`
- `sourcing_seed_asins.raw_context_json.inferred_system`
- `sourcing_seed_asins.raw_context_json.inferred_system_source`

Normalization:

- ASIN/title/price are normalized into columns.
- Platform is not normalized into a first-class `system` column.

Passed into matcher:

- Full seed row is passed into scoring.

Actually used:

- Amazon title is used for title overlap and title-based platform detection.
- `raw_context_json.inferred_system` is used by eBay search query generation,
  but not by scoring platform rules.

Ignored:

- Amazon image is ignored.
- Amazon category/catalog context is mostly only used during seed inference,
  then stored as context rather than used directly by scoring.
- Inferred platform is ignored by `platform_rule` unless also present in the
  title.

Primary missing link:

- `platform_rule` uses `seed.get("system")` or title detection, but seed rows
  do not appear to provide `system`; the known inferred system lives under
  `raw_context_json.inferred_system`.

Relevant code:

- `integrations/build_sourcing_seed_asins.py`
- `integrations/ebay_sourcing_search.py`
- `integrations/sourcing_match_rules.py`

### eBay Browse API

What exists:

- Search summary payloads and, when shipping is missing, item detail payloads.
- Title, primary image, item URL, seller username, feedback, location,
  condition, buying options, shipping, categories, localized aspects,
  short description, thumbnail/additional images.

Where stored:

- Selected normalized fields in `sourcing_ebay_candidates`.
- Full payload in `sourcing_ebay_candidates.raw_ebay_json`.
- Later snapshots in `sourcing_listing_snapshots`.

Normalization:

- Normalized into columns: title, primary image, seller username, location,
  condition, buying options, price, shipping, landed cost, quantity, auction,
  Best Offer, raw JSON.
- Not normalized into columns: item specifics, platform, game name, region,
  format/type/media, seller feedback, additional images, description.

Actually used:

- Title, condition, raw subtitle, raw short description/description, and raw
  localized aspect names/values are flattened into keyword text.
- Raw categories are used only against a fixed non-game category ID list.
- Title is used for candidate platform detection; item-specific platform is not.

Ignored or underused:

- `localizedAspects.Platform`
- `localizedAspects.Game Name`
- `localizedAspects.Region Code`
- `localizedAspects.Format`
- `localizedAspects.Type`
- `localizedAspects.Features`
- seller feedback score/percentage for matching
- images
- category hierarchy beyond a narrow deny list

### Candidate Normalization

What exists:

- Candidate rows preserve raw Browse payloads, so MBOP has the source evidence.

What is missing:

- First-class normalized `candidate_platform`, `candidate_game_name`,
  `candidate_region`, `candidate_format`, `candidate_type`,
  `candidate_edition_signals`, `candidate_media_signals`, and
  `candidate_image_urls`.

Consequence:

- The matcher repeatedly re-parses raw JSON ad hoc, mostly as plain text, and
  misses strong structured signals.

### Matching Rules

Implemented:

- Platform title detection.
- Title overlap.
- Excluded keywords.
- Digital/download terms.
- Incomplete terms.
- Accessory/not-game terms.
- Region terms.
- Edition/version title terms.
- Limited non-game category IDs.
- Pickup-only and location rules.
- Historical positive/negative evidence.
- Seller watch/avoid penalty.

Main gaps:

- Platform rule ignores seed `raw_context_json.inferred_system`.
- Platform rule ignores eBay `localizedAspects.Platform`.
- Edition/version rule mostly compares static edition words; it does not catch
  many sequel/year/game-name mismatches.
- Category rule misses many non-game leaf categories, including common eBay
  accessory and merchandise categories.
- No image comparison or image clue extraction.
- No structured item-specific diagnostics for Game Name, Format, Type, Media,
  or Region Code.

### Scoring

What exists:

- Rule diagnostics are merged into `ai_flags`, score adjustment, and
  `matching_diagnostics_json`.
- Hard blocks prevent open opportunities.
- Warnings lower score but can still leave profitable rows open.

Issue:

- Several obviously bad rows are only warnings (`Probable Non-Match`) and can
  remain `open` if profitability passes.
- Some bad rows are `Probable Match` because relevant stored evidence is not
  consumed.

### Opportunity / UI

What exists:

- `matching_diagnostics_json` is stored.
- API flattens diagnostic flags into `aiFlags`.
- Sourcing page displays flags.
- Matching Intelligence tab summarizes dismissals, notes, seller warnings, and
  near misses.

Gap:

- The normal opportunity row does not expose/render full per-candidate
  diagnostics such as platform source, category result, item-specific platform,
  Game Name, Region Code, or image/description availability.

## Phase 2 - Evidence Inventory

| Evidence | Stored | Parsed | Used | Notes |
| --- | --- | --- | --- | --- |
| Amazon title | Yes | Yes | Yes | Used for title overlap and title platform detection. |
| Amazon image | Yes | No | No | Stored in seed and API display context; not used for matching. |
| Amazon platform | Partial | Partial | Partial/bug | Inferred into `raw_context_json.inferred_system`; eBay search uses it, scoring does not. |
| Amazon category | Partial | Partial | No | Keepa category tree/product group can infer platform, but not used directly in scoring. |
| Amazon metadata | Partial | Partial | Limited | Listing/Keepa context informs seed construction, not matcher diagnostics. |
| eBay title | Yes | Yes | Yes | Primary matching input. |
| eBay subtitle | Raw only | Text-flattened | Keyword only | Used only if present in raw payload. |
| eBay category | Raw + snapshot | Partial | Partial | Uses small deny list; many accessory categories are missed. |
| eBay item specifics | Raw + snapshot | Text-flattened | Keyword only | Platform/Game Name/Region/Format/Type are not structured matcher inputs. |
| eBay condition | Yes | Yes | Partial | Brand New filter and text rules; no nuanced condition semantics. |
| eBay seller description | Raw when available | Text-flattened | Keyword only | Present in 184/1,000 recent rows. |
| eBay primary image | Yes | No | No | Stored as `ebay_image_url` and raw image URL. |
| Additional eBay images | Raw + snapshot | URL extraction in snapshots | No | Present in 994/1,000 recent raw payloads. |
| Seller username | Yes | Yes | Yes | Used for seller intelligence lookup. |
| Seller feedback | Raw + snapshot | Snapshot only | No/limited | Not used in live scoring except derived seller intelligence from outcomes. |
| Region | Raw item specifics/title | Keyword only | Partial | Region terms searched in flattened text, not structured Region Code. |
| Edition | Title only | Static title terms | Partial | Misses many sequel/year/base-vs-premium cases. |
| Buying options | Yes | Yes | Yes | Used for opportunity type, auction/Best Offer logic. |

## Phase 3 - False Positive Review

In the 222 recent dismissed identity/condition rows reviewed:

| Evidence Classification | Count |
| --- | ---: |
| Stored evidence existed but no rule hit | 141 |
| Existing rules already hit | 62 |
| Thin evidence in raw payload/title | 19 |

Pattern counts from the same reviewed set:

| Pattern | Count |
| --- | ---: |
| wrong_product/title | 69 |
| edition/version | 68 |
| wrong platform | 27 |
| condition/completeness | 26 |
| non-game category/accessory | 22 |
| digital/code/service | 10 |

Representative failures:

| Expected | Actual | Why matcher failed | Sufficient evidence already available? |
| --- | --- | --- | --- |
| Block PS4 seed vs Xbox One listing | `Probable Match` then dismissed wrong_platform | Seed platform was present only as `raw_context_json.inferred_system`; scoring ignored it. | Yes |
| Block PS4 seed vs PS3 listing | `Probable Match` then dismissed wrong_platform | Same seed inferred-system gap. | Yes |
| Block PC seed vs puzzle listing | Open / warning only | Category was Toys/Puzzles; category blocklist did not catch it. | Yes |
| Block game vs drum pedal/cable/sticks/accessory | `Probable Match` then dismissed wrong_product | Accessory category and terms such as pedal, cable, drum sticks, battery cover are not hard-blocked. | Yes |
| Block game vs plush/merch | Sometimes blocked, sometimes open | Some terms exist; category coverage is inconsistent. | Yes |
| Block digital service / modded item / XP / skin / operator | Often warning or match | Digital/service keyword list misses boost/service/skin/operator/modded/drop phrasing. | Yes |
| Block Premium Edition seed vs base game listing | `Probable Match` then dismissed wrong_edition_version | Edition rule misses when Amazon has Premium but eBay lacks it in some title shapes. | Yes |
| Block Just Dance 2018 vs Just Dance 2025/song pack | Open / warning | Edition/version rule does not treat sequel/year/title identity mismatch strongly enough. | Yes |
| Block game vs strategy guide | Warning only in some rows | Category and title terms are enough but not always hard-blocking. | Yes |
| Block missing shrink wrap / open box | `Probable Match` | Some evidence requires description/image/condition phrase normalization; current title terms are too narrow. | Partial |

Current open false-positive examples from the 1,000-row sample:

- `Wii Music` -> `Rock Band Cake Topper And Rings Music Celebration Wii Xbox
  PS4`; category was Cake Toppers/Home & Garden; result only warned about
  multiple platforms.
- `YO-KAI WATCH - 3DS` -> `Yo-Kai Watch Microfiber Cleaner Yokai cloth`;
  category was Collectibles/Animation Merchandise; result only warned no
  detectable platform.
- `Just Dance 2018 - Nintendo Switch` -> `Just Dance 2025 Limited Edition
  Nintendo Switch Ariana Grande Song Pack`; result was edition warning but
  remained open.
- `Transformers: Revenge of the Fallen - PC` -> Hasbro puzzle; category was
  Toys & Hobbies/Puzzles; result only warned no detectable platform.
- `Call of Duty: Black Ops Cold War (PS5)` -> operator skin / service listings;
  result only warned no detectable platform or weak title overlap.
- `Wreck-It Ralph - Nintendo Wii` -> Disney Infinity power discs/action figure
  listings; category was Toys to Life or Action Figures; result only warned
  multiple platforms.

## Phase 4 - Rule Opportunity Report

| Rule | Example | Historical Occurrences | Confidence | False Negative Risk | Recommended Action |
| --- | --- | ---: | --- | --- | --- |
| Use seed `raw_context_json.inferred_system` in scoring platform rule | PS4 seed "Need for Speed: Rivals" vs Xbox One/PS3/PC listings | 27 recent wrong-platform dismissals; many were `Probable Match` | High | Low | Hard Block |
| Parse eBay `localizedAspects.Platform` before title-only platform detection | Browse detail had Platform = Microsoft Xbox One | Item specifics Platform appeared 175 times in 1,000-row sample | High | Low | Hard Block when incompatible |
| Treat non-Video-Games leaf categories as blocks unless explicitly allowlisted | Cake Toppers, Puzzles, Controllers, Faceplates, Plush, Power Discs | 22 recent dismissed accessory/category false positives plus many open rows | High | Low/Medium | Hard Block |
| Add accessory category IDs to deny list | Video Game Accessories, Controllers & Attachments, Faceplates, Manuals/Box Art | Category evidence stored in 943/1,000 rows | High | Medium for legitimate game+accessory bundles | Hard Block or Review for bundles |
| Parse item-specific `Game Name` and compare to Amazon title | Game Party 2 vs DJ Hero 2, Just Dance 4 vs Disney Party | Game Name appeared 171 times in sample | Medium/High | Medium | Score Penalty / Warning, hard block when no overlap |
| Detect sequel/year mismatches | Just Dance 2018 vs 2025; Country Dance vs Country Dance 2 | 68 edition/version pattern rows | High | Medium | Hard Block when numeric title token conflicts |
| Expand digital/service terms | modded, max cash, item drop, operator skin, recovery service, boost, carry | 10 recent digital/service dismissals; some were `Probable Match` | High | Low | Hard Block |
| Expand accessory/not-game title terms | pedal, cable, drum sticks, faceplate, battery cover, power disc, puzzle, cake topper, microfiber cleaner | 69 wrong-product pattern rows include many accessories | High | Medium | Hard Block for exact accessory phrases |
| Normalize `Region Code`, `Country of Origin`, and region terms | PEGI/PAL/CERO/USK/import/Japanese | Region Code appeared 87 times in sample | Medium/High | Medium | Hard Block for explicit non-NA; Warning for unknown |
| Use seller description phrase extraction | open box, cartridge only, manual missing, add-on content | Description present in 184/1,000 rows | Medium | Medium | Warning / Hard Block for exact bad phrases |
| Add image availability diagnostics before AI | empty steelbook, PEGI, disc only, accessory photo | Images present in almost every row | Medium | N/A without AI | Warning / Future AI Review |

## Phase 5 - Structured Metadata Audit

| Metadata | Exists In Raw Browse Payload | Current Matcher Behavior | Where It Should Enter |
| --- | --- | --- | --- |
| eBay Category | Yes, 943/1,000 sample rows | Partial deny-list only | Candidate normalization + category allow/deny rule |
| eBay Item Specifics | Yes, 196/1,000 sample rows | Flattened text only | Candidate normalization |
| Platform | Title + item specifics | Title only in scoring | Platform rule |
| Edition | Title | Static title terms only | Edition/version rule plus aspects |
| Region | Title/description/aspects | Keyword only | Region rule with `Region Code` |
| Format | Sometimes | Ignored except flattened keyword | Digital/physical media rule |
| Type | Sometimes | Ignored except flattened keyword | Accessory/not-game rule |
| Game Name | Yes when detail exists | Ignored as structured data | Title identity rule |
| Media | Sometimes in terms/aspects | Mostly ignored | Completeness/physical rule |
| Condition | Yes | Filtered to condition ID 1000 and title text | Condition/completeness diagnostics |
| Seller Description | Sometimes | Keyword only | Description signal extraction |

Top item-specific fields observed:

- Platform: 175
- Game Name: 171
- Publisher: 157
- Rating: 146
- UPC: 134
- Genre: 123
- Release Year: 97
- Region Code: 87
- Country of Origin: 77
- Features: 74

## Phase 6 - Image Audit

Stored:

- Amazon primary image: yes, `sourcing_seed_asins.amazon_image_url`.
- eBay primary image: yes, `sourcing_ebay_candidates.ebay_image_url` and raw
  `image.imageUrl`.
- Additional eBay images: yes in raw `thumbnailImages` / `additionalImages`;
  snapshots extract `ebay_image_urls`.

Observed availability:

- eBay primary image: 1,000/1,000 recent opportunity rows.
- Additional eBay images: 994/1,000 recent opportunity rows.

Used for matching:

- No. Images are displayed and snapshotted but not consumed by deterministic
  matching or AI.

Where images disappear:

- `sourcing_ebay_candidates` has only the primary image as a column; additional
  images remain raw JSON.
- `/api/sourcing/opportunities` returns primary image only.
- `matching_diagnostics_json` does not include image availability or image clue
  results.

Changes required before image analysis:

- Normalize image URL list into candidate diagnostics or a candidate image URL
  column/table.
- Preserve Amazon/eBay image URL pairs in per-opportunity diagnostics.
- Add an image-clue review/debug surface.
- Only then consider AI image review for accessory, empty steelbook, download
  card, PEGI/CERO/USK, missing shrink wrap, reseal, wrong edition, or wrong
  platform.

## Phase 7 - Seller Description Audit

Availability:

- Seller description / short description was present in 184/1,000 recent
  opportunity rows.

Stored:

- Yes, in `raw_ebay_json.shortDescription` or `raw_ebay_json.description`.
- Snapshots also preserve `ebay_description`.

Parsed:

- Only flattened into searchable text in `searchable_candidate_text`.

Used:

- Only through keyword hits for excluded/digital/region terms.

Ignored:

- No normalized description signals for `download code`, `opened but unused`,
  `resealed`, `disc only`, `case only`, `manual missing`, `new open box`,
  `add-on content`, or service/delivery phrases.

Where it should enter:

- Candidate diagnostics should include `description_signals` separate from
  title signals, because description evidence has different reliability and
  should explain why a listing was blocked or warned.

## Phase 8 - Recommendations

### High Value Changes

1. Make platform evidence first-class.
   - Add or derive `seed_system` from `seed.system` or
     `seed.raw_context_json.inferred_system`.
   - Parse candidate platform from `localizedAspects.Platform` before falling
     back to title detection.
   - Hard-block incompatible known systems.

2. Change category logic from a small deny list to stronger game-software
   validation.
   - Allow known game software category `139973`.
   - Hard-block obvious non-software leaves such as accessories, controllers,
     faceplates, manuals, box art, plush, action figures, puzzles, cake toppers,
     stickers, and merchandise.
   - Use category path/name as well as ID.

3. Normalize item specifics into diagnostics.
   - Platform, Game Name, Region Code, Format, Type, Features, Release Year.
   - Use these alongside title, not as replacement source of truth.

4. Strengthen deterministic title identity.
   - Treat conflicting numeric title tokens/sequels/years as high-risk.
   - Compare item-specific Game Name when available.
   - Require stronger meaningful overlap for listings with accessory/category
     signals.

5. Expand exact digital/service and accessory phrase blocks.
   - Digital/service: `modded`, `boost`, `carry`, `operator skin`,
     `recovery service`, `item drop`, `max cash`, `eridium`, `vault card`,
     `add-on content`.
   - Accessory/non-game: `pedal`, `cable`, `drum sticks`, `faceplate`,
     `battery cover`, `power disc`, `puzzle`, `cake topper`,
     `microfiber cleaner`, `plush`, `patch`, `decal`.

6. Rescore current opportunities after deterministic metadata changes.
   - Existing rows have raw payloads, so many diagnostics can be rebuilt without
     another eBay call.

### Medium Value Changes

- Add normalized candidate metadata columns or a JSON `normalized_evidence_json`
  so rules do not repeatedly parse raw Browse payloads.
- Add full per-opportunity diagnostics UI or drawer.
- Include diagnostic source labels: title, item specifics, category,
  description, history, seller, image availability.
- Improve historical dismissal memory beyond exact eBay item ID and exact title
  token key.
- Use seller feedback as a weak advisory signal, while keeping outcome-based
  seller intelligence primary.

### Future AI Changes

AI should wait until deterministic metadata use is improved.

Future AI candidates:

- Image clue extraction for accessories, empty steelbooks, region logos,
  reseals, missing shrink wrap, and wrong platform cover art.
- Description clue extraction for nuanced condition/completeness phrasing.
- Near-miss review over structured evidence after rules have reduced obvious
  false positives.

AI should remain advisory/review-first and should not purchase, bid, submit
offers, train a model, or create eBay-to-Amazon sourcing.

## Prioritized Implementation Plan

1. Fix platform data flow.
   - Use seed inferred system in `platform_rule`.
   - Parse eBay item-specific platform.
   - Add diagnostics explaining source: Amazon title, inferred system, eBay
     title, eBay item specifics.

2. Add category allow/deny diagnostics.
   - Expand deny IDs/names.
   - Consider hard-blocking leaf categories outside game software when the
     title/aspects do not prove a physical game.

3. Add structured item-specific parser.
   - Convert `localizedAspects` to a normalized dict.
   - Feed Platform, Game Name, Region Code, Format, Type, Features, Release
     Year into diagnostics.

4. Strengthen deterministic rules.
   - Digital/service terms.
   - Accessory/not-game terms.
   - Numeric sequel/version mismatch.
   - Premium/base edition mismatch.

5. Update analyzer output.
   - Add structured metadata hit counts.
   - Add current-open false-positive candidates.
   - Add "stored but ignored" counters.

6. Rescore current opportunities and review before/after counts.

7. Only after the above, design image/AI review as an optional diagnostic layer.

