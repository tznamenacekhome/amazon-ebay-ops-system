# MBOP Matching Intelligence Layer Requirements + Codex Prompt

Status: Foundation implemented; remaining work tracked in `ROADMAP.md`  
System: Midnight Blue Operations Platform (MBOP)  
Business: Midnight Blue Enterprises, LLC  
Feature Theme: Sourcing / Matching Engine / eBay to Amazon Preparation  

---

## 1. Purpose

Build a reusable **Matching Intelligence Layer** inside MBOP that improves how the system determines whether an eBay listing matches an Amazon ASIN.

This layer should use MBOP's growing body of verified match and non-match data to improve:

1. Existing Amazon to eBay replenishment sourcing.
2. Future eBay to Amazon sourcing.
3. AI visual/title analysis.
4. Operator review efficiency.
5. Long-term personalized sourcing intelligence.

This is a foundation feature. Do **not** jump directly into eBay to Amazon sourcing yet.

Implementation note, 2026-06-14:
The storage layer, rebuild script, diagnostics API, minimal Sourcing UI tab,
receiving outcome capture, best-effort historical/manual purchase snapshots,
seller intelligence foundation, and live Amazon-to-eBay scoring integration are
implemented. Remaining work includes full row-level diagnostics, uncertain-match
review workflow, sample-driven fuzzy matching, AI opportunity review, richer
seller/return intelligence, configurable weights, and future eBay-to-Amazon
sourcing after the Amazon-to-eBay workflow is validated.

The correct sequence is:

```text
Build Matching Intelligence Layer
-> Apply it to Amazon to eBay sourcing
-> Test and iterate
-> Then build eBay to Amazon sourcing
```

---

## 2. Existing MBOP Context

MBOP already has relevant match-learning data in several places:

- eBay purchases imported into `purchases` and `purchase_items`
- manually verified ASINs on purchase items
- `manual_item_matches`
- sourcing opportunities
- sourcing actions
- dismissals
- purchases marked from sourcing and later matched to eBay buyer purchases
- AI flags / observations
- receiving outcomes
- listed outcomes
- eventual sales and profitability outcomes

MBOP architecture remains:

```text
Python integrations
-> Supabase PostgreSQL
-> Next.js API routes
-> React frontend
```

Supabase remains the source of truth.

Frontend must not contain matching business logic. Matching diagnostics, scores, and recommendations must be backend/API-provided.

---

## 3. Core Business Rules

### 3.1 Video Game Matching

Video games are platform-specific.

Never auto-match across systems.

Examples:

```text
Minecraft PS4 != Minecraft Switch
Wii != Wii U
Madden Xbox One != Madden PS5
```

System/platform must remain a hard matching boundary.

### 3.2 ASIN Identity

ASIN is the primary Amazon product identity.

### 3.3 eBay Listing Identity

For sourced eBay listings, use:

- `ebay_item_id`
- `ebay_legacy_item_id`

as primary eBay listing identity where available.

### 3.4 Advisory Boundary

Matching Intelligence may recommend, score, flag, or route for review.

It must not:

- purchase on eBay
- bid on eBay
- submit offers
- modify Amazon listings
- modify Informed
- modify Keepa data
- overwrite manual purchase-item corrections without explicit rules

---

## 4. Training Data Philosophy

The system should learn from both positive and negative examples.

### Positive examples

Examples:

- imported eBay purchase with manually verified ASIN
- sourcing opportunity marked Purchased and later matched to eBay purchase
- purchase item received successfully
- item listed successfully
- item sold profitably
- manual ASIN correction
- manual match memory

### Negative examples

Examples:

- permanent dismissals
- non-match decisions
- wrong platform
- wrong edition
- non-North-American version
- incomplete product
- condition/packaging issue

### Business-only examples

Some dismissals do not mean the product is not a match. They mean the opportunity is poor.

Example:

```text
Valid product, but ROI too low.
```

These should improve sourcing ranking, not identity matching.

---

## 5. Evidence to Store for Matching Intelligence

For every candidate or reviewed opportunity, preserve as much evidence as reasonably available.

### Amazon evidence

- ASIN
- Amazon title
- Amazon primary image URL
- system/platform if known
- Keepa title/metadata when available
- Amazon listing metadata when available

### eBay evidence

- eBay item ID
- eBay legacy item ID
- eBay title
- eBay subtitle if available
- eBay seller manual description if available
- eBay item specifics
- eBay condition
- eBay category
- eBay platform/item specific
- eBay region/item specific
- eBay primary image URL
- all eBay image URLs
- eBay listing URL
- raw eBay payload

### Operator evidence

- action type
- dismiss reason
- free-form note
- timestamp
- operator decision
- later purchase match if applicable
- later receiving/listing/sales outcome if applicable

---

## 6. Important New Requirement: Store Notes for Every Dismissal

The dismiss screen already has a note field.

Requirement:

```text
Store the note for every dismissal reason, not only when the selected reason is Other.
```

The note must be captured and preserved whenever the operator enters it.

This applies to all dismiss reasons.

Examples:

| Dismiss Reason | Note |
|---|---|
| Non-North-American Version | PEGI logo visible on back cover image |
| Wrong Edition / Version | Greatest Hits copy, Amazon ASIN is standard black-label |
| Packaging / Condition Issue | Missing shrink wrap; seller says "new open box" |
| Incomplete Product | Disc only shown in image 4 |
| ROI Too Low | Valid product but price would need to drop below $18 landed |

Why this matters:

1. Notes provide better AI training data than generic categories alone.
2. Notes can identify new recurring dismissal reasons.
3. Notes can help decide when to add a dedicated button/reason.
4. Notes can explain why an item was rejected months later.
5. Notes can help build a better eBay to Amazon matching engine later.

---

## 7. Improved Dismissal Taxonomy

The previous list mixed identity problems, condition problems, and business problems.

Use this improved taxonomy.

The UI may group these into sections.

### 7.1 Identity / Match Reasons

These reasons mean the eBay listing should not be considered a valid match to the Amazon ASIN.

They are high-value training data for the matching engine.

#### Wrong Product

Meaning:

The eBay listing is fundamentally a different product than the Amazon ASIN.

Examples:

- Amazon ASIN is Mario Kart Wii, eBay item is Mario Party 8.
- Amazon ASIN is a video game, eBay item is an accessory.
- Amazon ASIN is a game, eBay item is DLC or download code.

Training use:

- Strong negative match example.
- Helps prevent incorrect title similarity matches.

#### Wrong Platform

Meaning:

Same or similar product title, but wrong system/platform.

Examples:

- PS4 vs PS5
- Xbox One vs Xbox Series X
- Wii vs Wii U
- Switch vs 3DS

Training use:

- Hard negative.
- Reinforces platform boundary rules.

#### Wrong Edition / Version

Meaning:

Same product and same platform, but the edition/version does not match the Amazon ASIN.

Examples:

- Standard edition vs Collector's Edition
- Standard edition vs Steelbook
- Black-label vs Greatest Hits / Player's Choice / Platinum Hits
- Base game vs Game of the Year edition
- Bundle version vs standalone version

Training use:

- Negative match or warning depending on context.
- Helps AI and title matcher distinguish edition-level differences.

#### Non-North-American Version

Meaning:

The product appears to be outside the North American region and is not suitable for the operator's Amazon workflow.

Examples / clues:

- PEGI rating
- PAL region
- CERO rating
- USK rating
- Japanese packaging
- foreign-region packaging
- non-ESRB rating
- foreign-language packaging that indicates non-North-American release

Important clarification:

Bilingual North American packaging can be acceptable. The issue is non-North-American region, not simply the presence of more than one language.

Training use:

- Strong negative for sourcing.
- AI image/title/description analysis should learn these visual and text clues.

### 7.2 Completeness Reasons

#### Incomplete Product

Meaning:

The listing is missing required components for a complete new retail product.

Examples:

- Disc only
- Case only
- Missing manual when manual is expected
- Missing inserts or required components
- Missing bonus content when the Amazon ASIN requires it

Important clarification:

```text
Disc only = do not buy.
```

Disc only means there is no complete retail package.

Training use:

- Strong negative.
- Should eventually support auto-hide when confidence is high.

### 7.3 Packaging / Condition Reasons

These reasons mean the product may be the right product, platform, and edition, but the condition or packaging is not acceptable.

#### Missing Shrink Wrap

Meaning:

The product appears to be missing factory shrink wrap / factory seal.

Examples:

- Seller title says "new open box"
- photo shows game case without wrap
- description says "opened but unused"
- listing says "new" but package is clearly unsealed

Training use:

- Strong condition warning.
- Usually no-buy for new Amazon resale.

#### Suspected Reseal

Meaning:

The product appears sealed, but there are signs it may not be factory sealed.

Examples:

- unusual shrink wrap seams
- loose or sloppy wrap
- reseal language in seller description
- seller says "resealed"
- inconsistent packaging appearance

Training use:

- High-value AI visual/description training.
- May require operator review rather than immediate auto-hide at first.

#### Packaging Damage

Meaning:

Packaging damage is significant enough to make the item undesirable for Amazon new-condition resale.

Examples:

- crushed corners
- water damage
- torn cover art
- damaged case
- heavy sticker damage
- major dents or bends
- excessive shrink-wrap damage

Clarification:

A small shrink-wrap tear may still be acceptable depending on price and item value.

Training use:

- AI should flag severity where possible.
- Operator note is important.

### 7.4 Business / Sourcing Reasons

These reasons generally mean the eBay listing may be a valid match, but the business opportunity is not attractive.

These should **not** poison identity matching.

#### ROI Too Low

Meaning:

The item appears to match, but landed cost is too high for the configured ROI/profit threshold.

Training use:

- Sourcing ranking/pricing only.
- Do not use as a negative ASIN identity match.

#### Sales Velocity Too Low

Meaning:

The item may match and may even be profitable, but demand is too slow or inventory need is too low.

Training use:

- Sourcing prioritization only.

#### Too Much Competition

Meaning:

The item may match, but Amazon competitive context is unattractive.

Examples:

- too many sellers
- Amazon Retail present in a problematic way
- repricer/Buy Box opportunity poor
- price pressure too high

Training use:

- Sourcing prioritization only.

#### Capital Better Used Elsewhere

Meaning:

The item may be valid and possibly profitable, but capital should be saved for better opportunities.

Training use:

- Sourcing prioritization only.

#### Valid Product, Poor Opportunity

Meaning:

General business no-buy reason when the item appears to be a match but is not worth pursuing for non-identity reasons.

Use this when none of the more specific business reasons fit.

Training use:

- Business ranking only.
- Do not use as identity non-match.

### 7.5 System Reason

#### Other

Meaning:

Fallback for reasons not represented above.

Requirement:

When Other is selected, note should be strongly encouraged or required.

Training use:

- Review notes periodically to identify new dismissal reasons that deserve a dedicated button.

---

## 8. Notes and New Reason Discovery

Create a process/report to review dismissal notes.

Goal:

Identify repeated free-form notes that should become structured dismissal reasons or AI flags.

Examples:

| Repeated Note Pattern | Possible New Reason / Flag |
|---|---|
| "PEGI on back cover" | Non-North-American Version signal |
| "Greatest Hits" | Wrong Edition / Version signal |
| "missing shrink" | Missing Shrink Wrap |
| "seller says resealed" | Suspected Reseal |
| "disc only in image" | Incomplete Product |
| "ROI too low even with offer" | ROI Too Low |

Codex should add backend storage now even if the analysis UI/report comes later.

---

## 9. AI Review Requirements

The AI review layer should evaluate more than the title and primary image.

Inputs should include:

- Amazon title
- Amazon primary image
- eBay title
- eBay primary image
- all eBay image URLs when available
- seller description when available
- item specifics when available
- eBay condition
- eBay category

AI should produce:

- observations
- flags
- confidence
- severity
- explanation
- evidence source

Examples:

| Flag | Evidence Source |
|---|---|
| PEGI detected | image 3 |
| Missing shrink wrap | primary image |
| Seller says "opened but unused" | seller description |
| Greatest Hits edition | title and image |
| Disc only | title and image 4 |

AI should not decide whether to buy.

AI should not auto-dismiss in this phase.

---

## 10. Matching Intelligence Dataset

Create a backend-accessible view or table that combines historical evidence into labeled examples.

Suggested name:

```text
vw_matching_intelligence_examples
```

or a table plus materialized refresh process:

```text
matching_intelligence_examples
```

Each row should represent a reviewed eBay listing / Amazon ASIN relationship.

Suggested fields:

- example_id
- source_table
- source_id
- asin
- amazon_title
- amazon_image_url
- amazon_system
- ebay_item_id
- ebay_legacy_item_id
- ebay_title
- ebay_description
- ebay_primary_image_url
- ebay_image_urls
- ebay_item_specifics_json
- ebay_condition
- ebay_category
- detected_system
- operator_action
- dismiss_reason
- dismissal_note
- match_label
- label_type
- confidence
- created_at
- reviewed_at
- purchase_item_id
- sourcing_opportunity_id
- later_received
- later_listed
- later_sold
- later_profit
- raw_context_json

---

## 11. Label Semantics

Use explicit label semantics.

### Positive identity label

```text
match
```

Meaning:

eBay listing is a valid match to the ASIN.

Sources:
- manual ASIN correction
- matched sourcing purchase
- purchase item with verified ASIN
- successful received/listed/sold chain

### Negative identity label

```text
non_match
```

Meaning:

eBay listing is not a valid match to the ASIN.

Sources:
- Wrong Product
- Wrong Platform
- Wrong Edition / Version
- Non-North-American Version
- Incomplete Product

### Condition issue label

```text
condition_problem
```

Meaning:

Product identity may be correct, but condition/packaging fails.

Sources:
- Missing Shrink Wrap
- Suspected Reseal
- Packaging Damage

### Business issue label

```text
valid_match_poor_opportunity
```

Meaning:

Product likely matches, but sourcing opportunity is not worth pursuing.

Sources:
- ROI Too Low
- Sales Velocity Too Low
- Too Much Competition
- Capital Better Used Elsewhere
- Valid Product, Poor Opportunity

### Unknown / other

```text
needs_review
```

Meaning:

Not enough structured information.

Sources:
- Other
- ambiguous or incomplete data

---

## 12. Apply Matching Intelligence to Amazon to eBay First

Before building eBay to Amazon sourcing, apply the Matching Intelligence Layer to existing Amazon to eBay replenishment sourcing.

The improved Amazon to eBay matching should:

1. Use hard rules first.
2. Use historical positive match memory.
3. Use historical negative match memory.
4. Use AI observations as flags.
5. Use notes and dismiss reasons for diagnostics.
6. Produce explainable match diagnostics.
7. Route uncertain matches to review.

Do not launch eBay to Amazon sourcing until Amazon to eBay matching has been tested and iterated.

---

## 13. Diagnostics and Review UI

Add diagnostics that make matching transparent.

For each candidate, show:

- match score
- hard-rule pass/fail
- system match
- title overlap
- historical positive examples
- historical negative examples
- AI flags
- dismissal-history similarity
- final recommendation
- explanation

Possible statuses:

- Strong Match
- Probable Match
- Review
- Probable Non-Match
- Blocked

The frontend displays diagnostics from backend/API only.

---

## 14. Storage Requirements for Sourcing Actions

Update or verify `sourcing_actions` supports:

- action type
- dismiss reason
- note
- timestamp
- opportunity ID
- candidate ID
- ASIN
- eBay item ID
- optional structured metadata

Important:

The note field must be stored regardless of dismissal reason.

Suggested schema fields:

```sql
action_type text not null
dismiss_reason text null
notes text null
training_note text null
raw_action_context jsonb
```

If `notes` already exists, use it consistently.

No need to create separate `training_note` unless the current notes field is ambiguous or already used for non-training workflow notes.

---

## 15. Backfill Existing Data

Create a script to backfill matching intelligence examples from existing data.

Suggested script:

```text
integrations/build_matching_intelligence_examples.py
```

Responsibilities:

1. Read purchase items with verified ASINs.
2. Read manual match memory.
3. Read sourcing opportunities/actions.
4. Read purchased pending/matched sourcing purchase rows.
5. Read permanent dismissals and notes.
6. Normalize titles and systems.
7. Label examples.
8. Write examples or refresh materialized table.
9. Generate diagnostics summary.

Support:

```text
--dry-run
--write
--limit
--source purchases|sourcing|manual_matches|all
```

---

## 16. Future eBay to Amazon Sourcing Dependency

After the Matching Intelligence Layer is working and Amazon to eBay matching has improved, then build eBay to Amazon sourcing.

Future eBay to Amazon flow:

1. Search eBay broadly.
2. Detect title/system/condition.
3. Generate Amazon ASIN candidates.
4. Score using matching intelligence.
5. Apply business sourcing rules.
6. Show review candidates.
7. Learn from operator decisions.

Do not implement this in the current task.

---

## 17. Codex Prompt

Use this prompt with Codex.

```text
You are working in the Midnight Blue Operations Platform (MBOP) repository.

Goal:
Build the Matching Intelligence Layer requirements described in this document. This is a foundation for improving Amazon to eBay sourcing first, and later enabling eBay to Amazon sourcing. Do not build eBay to Amazon sourcing yet.

Read all current project documentation before implementing, especially:
- AGENTS.md
- CURRENT_STATE.md
- DECISIONS.md
- KNOWN_ISSUES.md
- ROADMAP.md
- docs/database_schema.md
- docs/backend_architecture.md
- docs/business_rules.md
- docs/subsystems/sourcing documents if present

Important architecture rules:
- MBOP uses Python integrations -> Supabase PostgreSQL -> Next.js API routes -> React frontend.
- Supabase is the operational source of truth.
- Frontend must not talk directly to Supabase.
- Frontend must not own matching logic.
- Sourcing remains advisory.
- Do not purchase, bid, submit Best Offers, or make marketplace write actions.
- Do not merge Sourcing with Purchases, Receiving, FBA, Repricing, or Order Problems.
- Do not auto-match across video game systems.
- Keep all matching diagnostics backend-owned and explainable.

Implement this iteratively.

Phase 1: Verify current schema
1. Inspect existing sourcing tables, especially sourcing_actions, sourcing_opportunities, sourcing_ebay_candidates, sourcing_purchase_matches, and any AI observation tables.
2. Determine whether dismiss notes are currently stored for all dismiss reasons or only for Other.
3. Report findings before making schema changes.

Phase 2: Schema/migration
1. If needed, add or adjust fields so every dismissal action stores:
   - dismiss_reason
   - notes
   - raw_action_context
   - candidate/opportunity/ASIN/eBay identifiers
2. Preserve existing data.
3. Add constraints or documentation comments only where safe.
4. Follow MBOP migration workflow. Provide SQL first if required.

Phase 3: Dismissal taxonomy
Implement or update the sourcing dismissal reason taxonomy with these structured values:

Identity / Match:
- wrong_product
- wrong_platform
- wrong_edition_version
- non_north_american_version

Completeness:
- incomplete_product

Packaging / Condition:
- missing_shrink_wrap
- suspected_reseal
- packaging_damage

Business / Sourcing:
- roi_too_low
- sales_velocity_too_low
- too_much_competition
- capital_better_used_elsewhere
- valid_product_poor_opportunity

System:
- other

Make sure notes can be saved with any reason, not only Other.

Phase 4: Matching intelligence examples
Create a backend view/table/process for matching intelligence examples.

Suggested names:
- matching_intelligence_examples table
or
- vw_matching_intelligence_examples view

Each example should capture:
- Amazon ASIN/title/image/system
- eBay item ID/title/description/images/item specifics/condition/category
- operator action
- dismiss reason
- dismissal note
- match label
- label type
- source table/source id
- confidence
- linked purchase item or sourcing opportunity where available
- raw context JSON

Label semantics:
- match
- non_match
- condition_problem
- valid_match_poor_opportunity
- needs_review

Map dismissal reasons to labels:
- wrong_product -> non_match
- wrong_platform -> non_match
- wrong_edition_version -> non_match
- non_north_american_version -> non_match
- incomplete_product -> non_match
- missing_shrink_wrap -> condition_problem
- suspected_reseal -> condition_problem
- packaging_damage -> condition_problem
- roi_too_low -> valid_match_poor_opportunity
- sales_velocity_too_low -> valid_match_poor_opportunity
- too_much_competition -> valid_match_poor_opportunity
- capital_better_used_elsewhere -> valid_match_poor_opportunity
- valid_product_poor_opportunity -> valid_match_poor_opportunity
- other -> needs_review

Phase 5: Backfill script
Create:
integrations/build_matching_intelligence_examples.py

Features:
- --dry-run default
- --write required to persist
- --source purchases|sourcing|manual_matches|all
- --limit optional
- prints summary counts by source, label, dismiss reason, and missing evidence
- preserves raw context
- does not overwrite workflow-owned purchase data

Phase 6: Diagnostics API
Add a backend API route to expose summary diagnostics.

Suggested route:
GET /api/sourcing/matching-intelligence

Return:
- counts by label
- counts by dismiss reason
- examples missing notes
- recent notes grouped by reason
- top candidate reasons for future structured buttons
- source coverage counts

No frontend matching logic.

Phase 7: Minimal UI
Add a simple page or section under Sourcing Settings or Sourcing History:
- Matching Intelligence Summary
- counts by label
- counts by dismissal reason
- examples with notes
- missing-note count
- "potential new reason" placeholder from repeated notes if easy, otherwise leave as future work

Do not build full eBay to Amazon sourcing.

Phase 8: Prepare Amazon to eBay matcher integration
Add documentation and, if practical, a backend utility module that future sourcing scoring can call to use:
- hard platform rules
- title overlap
- positive match memory
- negative match memory
- AI flags
- dismissal notes

Do not rewrite the entire sourcing algorithm unless required.
The first goal is to store clean training data and expose diagnostics.

Validation:
- Run type checks/builds used by the project.
- Run dry-run backfill and show summary.
- If write mode is safe, ask before running write mode unless the project convention allows applying after SQL confirmation.
- Confirm notes are stored for all dismiss reasons.
- Confirm dismissal reasons map to the correct label semantics.
- Confirm no marketplace write actions are added.
- Confirm frontend still uses API routes only.

Deliverables:
1. Schema migration if needed.
2. Updated backend action handling so notes persist for every dismissal reason.
3. Matching intelligence examples view/table or build process.
4. Backfill script.
5. Diagnostics API.
6. Minimal UI/report if feasible.
7. Documentation update explaining dismissal taxonomy and label semantics.
```

---

## 18. Acceptance Criteria

The implementation is complete when:

1. Dismiss notes are stored for every dismissal reason.
2. The improved dismissal reason taxonomy exists in backend-supported workflow.
3. Existing sourcing action records remain intact.
4. Matching intelligence examples can be generated from existing data.
5. Each example has a label: match, non_match, condition_problem, valid_match_poor_opportunity, or needs_review.
6. Business reasons do not poison identity matching.
7. Identity/condition/business reasons are clearly separated.
8. Diagnostics summarize counts by label and reason.
9. Amazon to eBay matching can later consume this layer.
10. eBay to Amazon sourcing has not been implemented yet.
