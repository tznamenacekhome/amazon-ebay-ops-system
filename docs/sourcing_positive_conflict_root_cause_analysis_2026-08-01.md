# Sourcing Positive Conflict Root-Cause Analysis

Date: 2026-08-01

Scope: read-only root-cause analysis using the same positive dataset and deduplication as `docs/sourcing_positive_match_safety_audit_2026-08-01.md`. No production rows, statuses, settings, schema, rules, marketplace data, AI calls, or deployments were changed.

## Dataset And Conflict Counts

| Metric | Count |
| --- | --- |
| Raw positive evidence rows | 5612 |
| Deduplicated positive rows | 2353 |
| Authoritative confirmed positives | 2280 |
| Review-only watching rows | 73 |
| Conflict rows in this analysis | 787 |
| Confirmed conflict rows | 746 |
| Strongest confirmed-positive conflict rows | 572 |
| Current evaluator hard-blocked confirmed positives | 95 |
| Game Name strict simulated confirmed blocks | 46 |
| Numeric/installment strict simulated confirmed blocks | 511 |
| Edition-family strict simulated confirmed blocks | 70 |
| Short-title strict simulated confirmed blocks | 164 |
| Rock Band-related confirmed positives | 31 |
| Rock Band numeric simulated blocks | 11 |

## Evidence Quality

| Evidence group | Rows |
| --- | --- |
| Confirmed received correct item | 569 |
| Purchased and matched, but not yet receiving-confirmed | 135 |
| Watch-only / not a confirmed match | 41 |
| Purchase pending / weaker positive | 39 |
| Manually verified exact match | 3 |

Rows with `later_received`, `later_listed`, or `later_sold` are sparse because much of the current positive evidence comes from historical purchase/match memory rather than receiving outcome rows. Counts therefore distinguish fully confirmed operational outcomes from purchased/matched evidence.

## Root-Cause Distribution

| Primary root cause among confirmed conflicts | Rows |
| --- | --- |
| release year mistaken for installment number | 254 |
| platform number mistaken for installment number | 224 |
| preserved by platform plus phrase overlap | 86 |
| current rule logic correct | 36 |
| same core game, edition omitted | 29 |
| unclear / needs operator review | 25 |
| Greatest Hits / Platinum Hits / Player's Choice / Nintendo Selects packaging difference | 24 |
| edition omission only | 14 |
| seller omitted edition wording | 8 |
| simulation logic too aggressive | 7 |
| eBay extra number too aggressively treated as identity | 6 |
| quantity/lot number mistaken for installment number | 6 |
| catalog metadata inconsistency | 6 |
| Amazon title number missing from eBay title | 5 |
| safe only with accessory/category corroboration | 4 |
| same core game, subtitle variation | 3 |
| downgrade to Review, not hard block | 3 |
| needs review; bundle or multi-title listing | 2 |
| different sequel/installment | 1 |
| same physical product with packaging-line difference | 1 |
| item-specific Game Name incomplete | 1 |
| valid Xbox cross-generation packaging | 1 |

## Numeric Conflict Deep Dive

| Numeric root cause among confirmed conflicts | Rows |
| --- | --- |
| release year mistaken for installment number | 256 |
| platform number mistaken for installment number | 230 |
| simulation logic too aggressive | 7 |
| eBay extra number too aggressively treated as identity | 6 |
| quantity/lot number mistaken for installment number | 6 |
| Amazon title number missing from eBay title | 5 |
| different sequel/installment | 1 |

Numeric conflicts are dominated by the strict simulation treating release years, platform tokens, lot quantities, and content/currency amounts as if they were sequel/installment identity. As written, the strict numeric simulation is not safe as a hard block.

Explicit cases:

- Rock Band vs Rock Band 3: hard block is safe only when both sides identify software discs and one side explicitly says `Rock Band 3` while the other explicitly identifies base `Rock Band` with no track-pack/accessory/bundle ambiguity. The reverse should also hard-block under the same exact-product conditions.
- Rock Band 2 vs Rock Band 3: safe hard block when both are software and the installment numbers conflict.
- Sports Champions vs Sports Champions 2, Jackbox Party Pack vs 7, NBA 2K19 vs NBA 2K26: safe hard blocks only when the conflicting number is part of the game identity, not a year, bundle quantity, or platform token.
- PS3/PS4/PS5, Xbox 360, Series X/S, lot of 2, 2 games, release years, anniversary editions, and Minecoin/currency amounts must be classified before they can influence hard-blocking.

Rock Band classifications:
| Classification among confirmed positives | Rows |
| --- | --- |
| true same-product match | 29 |
| seller title ambiguity | 2 |

## Game Name Conflict Deep Dive

| Classification among confirmed conflicts | Rows |
| --- | --- |
| same core game, edition omitted | 42 |
| same core game, subtitle variation | 3 |
| item-specific Game Name incomplete | 1 |

A safe Game Name hard block should require strong Game Name conflict plus conflicting title evidence plus no valid shared core identity. Exact token-set equality is too strict and false-blocks confirmed positives with omitted edition words, subtitles, publisher prefixes, and item-specific shorthand.

## Edition Conflict Deep Dive

| Classification among confirmed conflicts | Rows |
| --- | --- |
| Greatest Hits / Platinum Hits / Player's Choice / Nintendo Selects packaging difference | 38 |
| edition omission only | 17 |
| seller omitted edition wording | 12 |
| harmless packaging-line variation | 2 |
| same physical product with packaging-line difference | 1 |

Omission-only edition differences and packaging-line labels should usually be ignored or downgraded to Review. Hard blocks are safer for explicit conflicting material editions, bundle contents, steelbook-only listings, and starter/collector/complete content differences when both sides have explicit evidence.

## Short/Generic Title Deep Dive

| Classification among confirmed conflicts | Rows |
| --- | --- |
| preserved by platform plus phrase overlap | 149 |
| needs review; bundle or multi-title listing | 7 |
| downgrade to Review, not hard block | 4 |
| safe only with accessory/category corroboration | 4 |

Short titles should not hard-block by themselves. Safer logic requires corroboration from Video Games category, matching platform, item-specific Game Name, strong phrase overlap, absence of accessory/merchandise terms, and no numeric/version conflict.

## Current Hard-Block Safety

| Current family | Rows |
| --- | --- |
| numeric | 23 |
| accessory | 21 |
| edition | 17 |
| location | 15 |
| platform | 9 |
| title_overlap | 6 |
| incomplete | 3 |
| other | 2 |
| digital | 2 |
| game_name | 1 |

Canada item-location blocks are intentional business policy and are kept separate from product-identity matching quality. Product-rule families with positive conflicts should be reviewed before broad rescoring or stricter hard-block expansion.

## Presentation Gate Recommendation

Recommendation: DEPLOY GATE WITH RESTRICTIONS.

The gate merely enforces stored diagnostics for `open` rows before presentation. It can hide valid open opportunities when current stored diagnostics are too aggressive, especially numeric, edition, accessory/category, platform, and title-overlap blocks. Do not recompute diagnostics inside the gate; keep recomputation in explicit dry-run/rescore jobs. Deploy only if the gate is limited to open presentation eligibility, accepted/purchased statuses remain exempt, and Canada remains understood as an intentional sourcing policy.

## Safe Rule Blueprint

### Safe Hard Blocks

- Exact historical negative identity memory by ASIN + eBay item ID when there is no positive-memory conflict. Evidence: matching intelligence exact key. Behavior: hard block. Positive conflicts: none expected after conflict check. Backoff: if any confirmed positive exists for the same key, route to Review.
- Explicit non-game/accessory category plus exact accessory term and no bundle-with-game signal. Evidence: category, Type, title. Behavior: hard block. Backoff: Review if Video Games category or bundle language is present.
- Explicit different software installment where both numbers are classified as game installment or annual sports identity and platform/category match. Evidence: Amazon title, eBay title, Game Name. Behavior: hard block. Backoff: Review if either number is platform/year/quantity/content.

### Review / Penalty Only

- Strict numeric/installment mismatch without number classification.
- Strict Game Name token-set mismatch.
- Edition-family omission or packaging-line mismatch.
- Short/generic title with extra candidate tokens.
- Seller/listing text that conflicts with otherwise plausible title/platform evidence.

### Needs Operator Clarification

- Rock Band base vs numbered installment rows with ambiguous seller title.
- Xbox One / Series X cross-generation packaging when Amazon/eBay system fields disagree.
- Edition omission cases where Amazon and eBay titles differ but photos would settle the packaging.

### Do Not Implement

- Any hard block based solely on short title length.
- Any hard block based on exact Game Name token-set equality.
- Any numeric hard block that treats all extra numbers as identity.
- Any expanded edition hard block that treats omission-only packaging labels as mismatch.

## Operator Review Queue

Queue size: 50 rows.

| amazon_title | ebay_title | game_name | rule_families | evidence_confidence_group | operator_review_question |
| --- | --- | --- | --- | --- | --- |
| All Pro Football 2K8 - Xbox 360 | All-Pro Football 2K8 Xbox 360 Brand New Sealed | All-Pro Football 2K8 | current:location | Purchased and matched, but not yet receiving-confirmed | Is this historical positive evidence a true product match? |
| Mercenaries 2: World in Flames - PC [video game] | Mercenaries 2 World In Flames PC DVD-Rom 2008 Brand New Sealed EA | Mercenaries 2: World in Flames | current:location; numeric | Purchased and matched, but not yet receiving-confirmed | Which numbers are product identity, and which are platform/year/quantity/content? |
| Mercenaries 2: World in Flames - PC [video game] | Mercenaries 2 World in Flames (PC DVD-ROM) *BRAND NEW SEALED* | Mercenaries 2: World in Flames | current:location | Purchased and matched, but not yet receiving-confirmed | Is this historical positive evidence a true product match? |
| Mercenaries 2: World in Flames - PC [video game] | Mercenaries 2: World in Flames (PC, 2008) |  | current:location; numeric | Purchased and matched, but not yet receiving-confirmed | Which numbers are product identity, and which are platform/year/quantity/content? |
| Rock Band Game Only PS3 | Rock Band (Sony PlayStation 3, PS3) New Sealed In Box 🎸 |  | rock_band | Confirmed received correct item | Is this the exact Rock Band disc/track-pack product, or a different installment/accessory? |
| Rock Band Game Only PS3 | Rock Band (Sony PlayStation 3, PS3) New Sealed In Box 🎸 |  | rock_band | Confirmed received correct item | Is this the exact Rock Band disc/track-pack product, or a different installment/accessory? |
| Rock Band Game Only PS3 | Rock Band Game PS3 Brand New & Factory Sealed-PlayStation 3 Rare Harmonix |  | rock_band | Confirmed received correct item | Is this the exact Rock Band disc/track-pack product, or a different installment/accessory? |
| Rock Band Game Only PS3 | Rock Band Game PS3 Brand New & Factory Sealed-PlayStation 3 Rare Harmonix |  | rock_band | Confirmed received correct item | Is this the exact Rock Band disc/track-pack product, or a different installment/accessory? |
| NCAA Football 09 - PlayStation 2 | PS2 NCAA Football 09 game (brand new, unsealed) |  | current:incomplete | Confirmed received correct item | Is this historical positive evidence a true product match? |
| NCAA Football 09 - PlayStation 2 | PS2 NCAA Football 09 game (brand new, unsealed) |  | current:incomplete | Confirmed received correct item | Is this historical positive evidence a true product match? |
| Rock Band 2 - Nintendo Wii (Game only) | Rock Band 2 |  | rock_band | Confirmed received correct item | Is this the exact Rock Band disc/track-pack product, or a different installment/accessory? |
| Rock Band Track Pack: Vol. 2 - PlayStation 2 | Rock Band Track Pack: Vol. 2 |  | rock_band | Confirmed received correct item | Is this the exact Rock Band disc/track-pack product, or a different installment/accessory? |
| AC/DC Live: Rock Band Track Pack - Playstation 3 | AC/DC Live: Rock Band Track Pack |  | rock_band | Confirmed received correct item | Is this the exact Rock Band disc/track-pack product, or a different installment/accessory? |
| AC/DC Live: Rock Band Track Pack - Nintendo Wii | AC/DC Live Rock Band Track Pack Nintendo Wii Video Game NEW |  | rock_band | Confirmed received correct item | Is this the exact Rock Band disc/track-pack product, or a different installment/accessory? |
| AC/DC Live: Rock Band Track Pack - Nintendo Wii | AC/DC Live Rock Band Track Pack Nintendo Wii Video Game music rhythm concert |  | rock_band | Confirmed received correct item | Is this the exact Rock Band disc/track-pack product, or a different installment/accessory? |
| AC/DC Live: Rock Band Track Pack - Nintendo Wii | AC/DC Live: Rock Band Track Pack |  | rock_band | Confirmed received correct item | Is this the exact Rock Band disc/track-pack product, or a different installment/accessory? |
| AC/DC Live: Rock Band Track Pack - Nintendo Wii | AC/DC Live: Rock Band Track Pack (Nintendo Wii) New Sealed |  | rock_band | Confirmed received correct item | Is this the exact Rock Band disc/track-pack product, or a different installment/accessory? |
| AC/DC Live: Rock Band Track Pack - Nintendo Wii | AC/DC Live: RockBand Track Pack Video Game For Nintendo Wii FACTORY SEALED |  | rock_band | Confirmed received correct item | Is this the exact Rock Band disc/track-pack product, or a different installment/accessory? |
| AC/DC Live: Rock Band Track Pack - Nintendo Wii | New AC/DC Live: Rock Band Track Pack Nintendo Wii Game |  | rock_band | Confirmed received correct item | Is this the exact Rock Band disc/track-pack product, or a different installment/accessory? |
| The Beatles: Rock Band (Game Only) - Nintendo Wii | Rock Band the Beatles - Nintendo Wii |  | rock_band | Confirmed received correct item | Is this the exact Rock Band disc/track-pack product, or a different installment/accessory? |
| The Beatles: Rock Band (Game Only) - Nintendo Wii | Rock Band the Beatles - Nintendo Wii |  | rock_band | Confirmed received correct item | Is this the exact Rock Band disc/track-pack product, or a different installment/accessory? |
| Toy Story Mania! - Nintendo Wii | Toy Story Mania! |  | current:accessory | Confirmed received correct item | Is this historical positive evidence a true product match? |
| Rock Band: Country Track Pack - Xbox 360 | Rock Band: Country Track Pack Microsoft Xbox 360 Brand NEW Factory Sealed! Rare. |  | rock_band | Confirmed received correct item | Is this the exact Rock Band disc/track-pack product, or a different installment/accessory? |
| Rock Band: Country Track Pack | Rock Band Country Track Pack |  | rock_band | Confirmed received correct item | Is this the exact Rock Band disc/track-pack product, or a different installment/accessory? |
| Rock Band 3 | ROCK BAND 3 |  | rock_band | Confirmed received correct item | Is this the exact Rock Band disc/track-pack product, or a different installment/accessory? |
| Rock Band 3 [video game] | Rock Band (Sony PlayStation 3, PS3) New Sealed In Box 🎸 | Rock Band | numeric; rock_band | Purchased and matched, but not yet receiving-confirmed | Is this the exact Rock Band disc/track-pack product, or a different installment/accessory? |
| Rock Band 3 [video game] | Rock Band Game PS3 Brand New & Factory Sealed-PlayStation 3 Rare Harmonix | Rock Band | numeric; rock_band | Purchased and matched, but not yet receiving-confirmed | Is this the exact Rock Band disc/track-pack product, or a different installment/accessory? |
| Nickelodeon Fit [video game] | Nickelodeon Fit-Nintendo Wii & WIIU |  | current:platform | Confirmed received correct item | Is this historical positive evidence a true product match? |
| Nickelodeon Fit [video game] | Nickelodeon Fit-Nintendo Wii & WIIU |  | current:platform | Confirmed received correct item | Is this historical positive evidence a true product match? |
| Rock Band Country Track Pack 2 - Nintendo Wii | Rock Band: Country Track Pack 2 |  | rock_band | Confirmed received correct item | Is this the exact Rock Band disc/track-pack product, or a different installment/accessory? |
| X-Men: Destiny | X-Men: Destiny (Microsoft Xbox 360, 2011) Brand New Sealed! | X-Men: Destiny | current:location; numeric | Purchase pending / weaker positive | Which numbers are product identity, and which are platform/year/quantity/content? |
| Sniper: Ghost Warrior 2 - Xbox 360 | Sniper: Ghost Warrior 2 (Microsoft Xbox 360, 2013) Brand New Sealed |  | current:location; numeric | Purchased and matched, but not yet receiving-confirmed | Which numbers are product identity, and which are platform/year/quantity/content? |
| Paper Mario: Sticker Star | Paper Mario: Sticker Star |  | current:accessory | Confirmed received correct item | Is this historical positive evidence a true product match? |
| Toy Story Mania for Xbox 360 Kinect | Toy Story Mania |  | current:accessory | Confirmed received correct item | Is this historical positive evidence a true product match? |
| DISNEY INFINITY Starter Pack PS3 | NEW Disney Infinity 1.0 Starter Pack PS3 PlayStation 3 + Power Disc Packs (x4) |  | current:accessory | Confirmed received correct item | Is this historical positive evidence a true product match? |
| Rocksmith 2014 Edition - No Cable Included for Rocksmith Owners | Rocksmith 2014 Edt No Cable Incl - Microsoft Xbox 360 |  | current:accessory | Confirmed received correct item | Is this historical positive evidence a true product match? |
| Just Dance 2014 - PlayStation 4 [video game] | NEW Just Dance 2015 ( Sony Playstation 4, PS4, 2014 ) | Just Dance 2015 | current:location; numeric | Purchased and matched, but not yet receiving-confirmed | Which numbers are product identity, and which are platform/year/quantity/content? |
| The Sims 4 - PC/Mac | The SIMS 4 - for Windows PC & Mac NEW + The Sims 4 Get to Work Expansion Pack | The Sims 4 | current:other | Purchased and matched, but not yet receiving-confirmed | Is this historical positive evidence a true product match? |
| NHL 15 - PlayStation 3 | NHL 15 - Sony playstation 3 PS3 - Complete In Box CIB | NHL 15 | current:location; edition | Purchased and matched, but not yet receiving-confirmed | Is the edition/package line materially different for resale, or only seller/Amazon wording? |
| Madden NFL 15 (Ultimate Edition) - Xbox One | Madden NFL 15 Ultimate Edition (Xbox One, 2014) Brand New And Factory Sealed! | Madden NFL 15 Ultimate Edition | current:location; numeric | Purchase pending / weaker positive | Which numbers are product identity, and which are platform/year/quantity/content? |
| Toy Soldiers War Chest Hall of Fame Edition | Toy Soldiers War Chest Hall of Fame Edition Xbox One Brand New Sealed Mint |  | current:accessory | Confirmed received correct item | Is this historical positive evidence a true product match? |
| Toy Soldiers War Chest Hall of Fame Edition | Toy Soldiers: War Chest Hall of Fame Edition |  | current:accessory | Confirmed received correct item | Is this historical positive evidence a true product match? |
| Star Wars Battlefront (Xbox One) | Star Wars Battlefront (Microsoft Xbox One, 2015) Sealed | Star Wars: Battlefront | current:location; numeric | Purchase pending / weaker positive | Which numbers are product identity, and which are platform/year/quantity/content? |
| Kirby amiibo - Nintendo Switch | Kirby amiibo |  | current:accessory | Confirmed received correct item | Is this historical positive evidence a true product match? |
| Devil May Cry - PlayStation 4 | Devil May Cry 5 |  | current:numeric; numeric | Confirmed received correct item | Which numbers are product identity, and which are platform/year/quantity/content? |
| Nintendo Labo Toy-Con 03: Vehicle Kit - Switch | Nintendo Labo Toy-Con 03: Vehicle Kit |  | current:accessory | Confirmed received correct item | Is this historical positive evidence a true product match? |
| Nintendo Labo Toy-Con 03 Vehicle Kit | Nintendo Labo Toy-Con 03 Vehicle Kit |  | current:accessory | Confirmed received correct item | Is this historical positive evidence a true product match? |
| Mortal Kombat 11 (Nintendo Switch) [video game] | Mortal Kombat 11 (Nintendo Switch) Factory Sealed / Never Opened Game | Mortal Kombat 11 | current:location | Purchase pending / weaker positive | Is this historical positive evidence a true product match? |
| Nintendo Labo Toy-Con 04: VR Kit - Starter Set + Blaster - Switch | Nintendo Labo Toy-Con 04 VR Kit Starter Set • Nintendo Switch • New |  | current:accessory | Confirmed received correct item | Is this historical positive evidence a true product match? |
| Nintendo Labo Toy-Con 04: VR Kit - Starter Set + Blaster - Switch | Nintendo Labo Toy-Con 04: VR Kit - Starter Set + Blaster |  | current:accessory | Confirmed received correct item | Is this historical positive evidence a true product match? |
