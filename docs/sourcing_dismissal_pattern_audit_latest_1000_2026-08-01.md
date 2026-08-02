# Sourcing Dismissal Pattern Audit - Latest 1,000

Date: 2026-08-01

Scope: read-only analysis of the most recent operator-created MBOP sourcing dismissals. No production data, matching rules, opportunity statuses, schema, settings, or action history were modified.

## Section 1 - Dataset Integrity

| Metric | Value |
| --- | --- |
| Total actions requested | 1000 |
| Operator dismissals analyzed | 1000 |
| Date range | 2026-06-15T02:50:54.610133+00:00 to 2026-08-01T18:18:22.929535+00:00 |
| Excluded system/availability actions | 219 |
| Complete Amazon and eBay titles | 1000 |
| With notes | 33 |
| With snapshots | 1000 |
| With item specifics | 864 |
| With descriptions | 864 |
| With primary images | 1000 |
| With additional images | 938 |
| With stored matching diagnostics | 1000 |

Limitations: this audit uses stored sourcing action, candidate, snapshot, opportunity, and matching-intelligence evidence. It does not call eBay/Amazon/Keepa, does not inspect images with AI, and cannot prove what was visually obvious to the operator unless a textual note or stored metadata records it.

## Section 2 - Dismissal Reason Distribution

| Reason | Count | Pct |
| --- | --- | --- |
| wrong_edition_version | 382 | 38.2% |
| wrong_product | 201 | 20.1% |
| missing_shrink_wrap | 80 | 8.0% |
| sales_velocity_too_low | 68 | 6.8% |
| asin_blocked | 61 | 6.1% |
| wrong_platform | 44 | 4.4% |
| incomplete_product | 44 | 4.4% |
| packaging_damage | 32 | 3.2% |
| digital_item | 27 | 2.7% |
| non_north_american_version | 19 | 1.9% |
| suspected_reseal | 15 | 1.5% |
| roi_too_low | 13 | 1.3% |
| other | 12 | 1.2% |
| nfr | 2 | 0.2% |

### Recency Windows

#### 1-100
| Reason | Count | Pct |
| --- | --- | --- |
| wrong_edition_version | 38 | 38.0% |
| asin_blocked | 24 | 24.0% |
| sales_velocity_too_low | 9 | 9.0% |
| missing_shrink_wrap | 9 | 9.0% |
| packaging_damage | 4 | 4.0% |
| suspected_reseal | 4 | 4.0% |
| wrong_platform | 4 | 4.0% |
| incomplete_product | 3 | 3.0% |
| digital_item | 2 | 2.0% |
| wrong_product | 2 | 2.0% |
| non_north_american_version | 1 | 1.0% |

#### 101-500
| Reason | Count | Pct |
| --- | --- | --- |
| wrong_edition_version | 152 | 38.0% |
| wrong_product | 106 | 26.5% |
| missing_shrink_wrap | 40 | 10.0% |
| asin_blocked | 27 | 6.8% |
| sales_velocity_too_low | 19 | 4.8% |
| packaging_damage | 13 | 3.2% |
| incomplete_product | 10 | 2.5% |
| non_north_american_version | 10 | 2.5% |
| other | 6 | 1.5% |
| digital_item | 5 | 1.2% |
| suspected_reseal | 4 | 1.0% |
| roi_too_low | 3 | 0.8% |
| wrong_platform | 3 | 0.8% |
| nfr | 2 | 0.5% |

#### 501-1000
| Reason | Count | Pct |
| --- | --- | --- |
| wrong_edition_version | 192 | 38.4% |
| wrong_product | 93 | 18.6% |
| sales_velocity_too_low | 40 | 8.0% |
| wrong_platform | 37 | 7.4% |
| missing_shrink_wrap | 31 | 6.2% |
| incomplete_product | 31 | 6.2% |
| digital_item | 20 | 4.0% |
| packaging_damage | 15 | 3.0% |
| roi_too_low | 10 | 2.0% |
| asin_blocked | 10 | 2.0% |
| non_north_american_version | 8 | 1.6% |
| suspected_reseal | 7 | 1.4% |
| other | 6 | 1.2% |

## Section 3 - Wrong Edition / Version Analysis

| Pattern | Count | Pct |
| --- | --- | --- |
| item-specific Game Name or Edition conflict | 231 | 60.5% |
| unclear/insufficient evidence | 80 | 20.9% |
| volume/episode/part mismatch | 23 | 6.0% |
| bundled content difference | 17 | 4.5% |
| base game vs complete/GOTY edition | 12 | 3.1% |
| console generation/version mismatch | 8 | 2.1% |
| release-year mismatch | 5 | 1.3% |
| base game vs collector's edition | 3 | 0.8% |
| base game vs deluxe edition | 2 | 0.5% |
| base game vs limited edition | 1 | 0.3% |

Representative examples:

- item-specific Game Name or Edition conflict
  - Amazon: MySims - Nintendo Wii
    eBay: MySims Kingdom  Nintendo Wii 2008 BRAND NEW! FACTORY SEALED!
    Evidence: Game Name=MySims Kingdom; category=Video Games; Video Games & Consoles; current rules=Probable Match
  - Amazon: Minecraft – Xbox One [video game]
    eBay: Minecraft Dungeons Hero Edition for Xbox One Series x New Sealed
    Evidence: Game Name=Minecraft Dungeons Hero Edition; category=Video Games; Video Games & Consoles; current rules=Probable Match
  - Amazon: Minecraft – Xbox One [video game]
    eBay: Minecraft Legends Xbox One &  Series X\|S
    Evidence: Game Name=Legends; category=Video Games; Video Games & Consoles; current rules=Probable Match
- unclear/insufficient evidence
  - Amazon: Madden NFL 25 - Xbox One
    eBay: Madden NFL 25 For Xbox Series X/ Xbox One New Factory Sealed
    Evidence: Game Name=Madden NFL 25; category=Video Games; Video Games & Consoles; current rules=Probable Match
  - Amazon: Madden NFL 25 - Xbox One
    eBay: Madden NFL 25 Xbox Series X & Xbox One Brand New
    Evidence: Game Name=Madden NFL 25; category=Video Games; Video Games & Consoles; current rules=Probable Match
  - Amazon: Sesame Street: Elmo's A-to-Zoo Adventure - Nintendo Wii
    eBay: Sesame Street Elmo's A-to-Zoo Adventure Game NIB w/ Remote Cover Nintendo Wii
    Evidence: Game Name=Sesame Street: Elmo's A-to-Zoo Adventure; category=Video Games; Video Games & Consoles; current rules=Probable Match
- volume/episode/part mismatch
  - Amazon: The Jackbox Party Pack - PlayStation 4
    eBay: The Jackbox Party Pack 7  (Playstation 4) PS4 - DISC SOUNDS LOOSE
    Evidence: Game Name=The Jackbox Party Pack 7; category=Video Games; Video Games & Consoles; current rules=Probable Match
  - Amazon: You Don't Know Jack
    eBay: You Don't Know Jack CD 1998 Original Irreverent Quiz Show Party Game
    Evidence: Game Name=--; category=Music; CDs; current rules=Probable Match
  - Amazon: You Don't Know Jack
    eBay: Vintage 1998 You Don’t Know Jack Volume 2 Sealed NEW
    Evidence: Game Name=--; category=Computers; Tablets & Networking; Software; Other Computer Software; current rules=numeric sequel/year mismatch
- bundled content difference
  - Amazon: Minecraft – Xbox One [video game]
    eBay: MINECRAFT + 3500 COINS For Microsoft Xbox One And Xbox Series X SEALED
    Evidence: Game Name=Minecraft; category=Video Games; Video Games & Consoles; current rules=Probable Match
  - Amazon: Skylanders SuperChargers Racing Starter Pack - Wii
    eBay: Wii Skylanders SuperChargers Racing Game (from Starter Pack) NEW - READ DETAILS!
    Evidence: Game Name=Skylanders SuperChargers; category=Video Games & Consoles; Video Games; current rules=Probable Match
  - Amazon: Sports Champions 2
    eBay: (2)Games Sports Champions + TV Superstars (PS3) Brand New SEALED Bundle Lot
    Evidence: Game Name=Sports Champions; category=Video Games & Consoles; Video Games; current rules=Probable Match
- base game vs complete/GOTY edition
  - Amazon: Sniper Elite 4 - Xbox One
    eBay: Sniper Elite 4 (Xbox One, 2017)
    Evidence: Game Name=Sniper Elite 4; category=Video Games; Video Games & Consoles; current rules=Probable Match
  - Amazon: Lego Star Wars: The Complete Saga [video game]
    eBay: NEW LEGO Batman the video Game (Xbox 360)
    Evidence: Game Name=--; category=Video Games; Video Games & Consoles; current rules=Probable Match
  - Amazon: Need for Speed Rivals Complete Edition - Xbox One
    eBay: Xbox One - Need for Speed Rivals - Brand New - FREE SHIPPING -
    Evidence: Game Name=Need for Speed Rivals; category=Video Games & Consoles; Video Games; current rules=Probable Match
- console generation/version mismatch
  - Amazon: The Jackbox Party Pack - PlayStation 4
    eBay: NEW The Jackbox Party Pack 7 Sony PlayStation PS4 Video Game Rated Teen
    Evidence: Game Name=The Jackbox Party Pack 7; category=Video Games; Video Games & Consoles; current rules=Probable Match
  - Amazon: The Jackbox Party Pack - PlayStation 4
    eBay: Jackbox Games The Jackbox Party Pack 7 PS4 NTSC-U/C T 2020 Multiplayer Online
    Evidence: Game Name=The Jackbox Party Pack 7; category=Video Games; Video Games & Consoles; current rules=Probable Match
  - Amazon: The Jackbox Party Pack - PlayStation 4
    eBay: The Jackbox 7 Video Game Party Pack - Sony PS4 2021 Teens NEW, SEALED
    Evidence: Game Name=The Jackbox Party Pack 7; category=Video Games; Video Games & Consoles; current rules=Probable Match
- release-year mismatch
  - Amazon: Sports Champions 2
    eBay: Sports Champions (Sony PlayStation 3) PS3 Playstation Move Required - New Sealed
    Evidence: Game Name=Sports Champions; category=Video Games & Consoles; Video Games; current rules=Probable Match
  - Amazon: Sports Champions 2
    eBay: Sports Champions (Sony PlayStation 3) BRAND NEW SEALED
    Evidence: Game Name=Sports Champions; category=Video Games & Consoles; Video Games; current rules=Probable Match
  - Amazon: Sports Champions 2
    eBay: Sports Champions PlayStation 3 PS3 CIB New Sealed Sony
    Evidence: Game Name=Sports Champions; category=Video Games & Consoles; Video Games; current rules=Probable Match
- base game vs collector's edition
  - Amazon: Mass Effect 3 Collector's Edition -Xbox 360
    eBay: Mass Effect 3 Collector's Edition Xbox 360
    Evidence: Game Name=Mass Effect 3; category=Video Games; Video Games & Consoles; current rules=Probable Match
  - Amazon: The Legend of Zelda: Tears of the Kingdom Collector’s Edition [video game]
    eBay: The Legend of Zelda - Tears of the Kingdom Nintendo Switch Game Brand ( Sealed )
    Evidence: Game Name=The Legend of Zelda: Tears of the Kingdom; category=Video Games; Video Games & Consoles; current rules=Probable Match
  - Amazon: Mortal Kombat 1 Premium Edition - Xbox Series X [video game]
    eBay: Mortal Kombat 1 (Xbox Series X, 2023)
    Evidence: Game Name=Mortal Kombat; category=Video Games; Video Games & Consoles; current rules=edition/version mismatch signal
- base game vs deluxe edition
  - Amazon: Titanfall 2 Deluxe Edition - Xbox One
    eBay: XBOX ONE TITANFALL 2 RESPAWN EA
    Evidence: Game Name=Titanfall 2 Deluxe Edition; category=Video Games; Video Games & Consoles; current rules=edition/version mismatch signal
  - Amazon: Titanfall 2 Deluxe Edition - Xbox One
    eBay: XBOX ONE TITANFALL 2 RESPAWN EA
    Evidence: Game Name=Titanfall 2 Deluxe Edition; category=Video Games; Video Games & Consoles; current rules=edition/version mismatch signal
- base game vs limited edition
  - Amazon: Destiny 2 Limited Edition [Playstation 4, PS4]
    eBay: PlayStation 4/3 New Sealed Game Bundle Destiny 2, Bulletstorm Limited Edition
    Evidence: Game Name=Destiny 2; category=Video Games; Video Games & Consoles; current rules=Probable Match

## Section 4 - Wrong Product Analysis

| Pattern | Count | Pct |
| --- | --- | --- |
| eBay item-specific Game Name conflict | 133 | 66.2% |
| title ambiguity from a short/generic game name | 30 | 14.9% |
| unclear/insufficient evidence | 18 | 9.0% |
| controller/peripheral | 4 | 2.0% |
| collectible/merchandise | 3 | 1.5% |
| toy/figure/card | 3 | 1.5% |
| bundle containing a different game | 2 | 1.0% |
| wrong numbered installment | 2 | 1.0% |
| digital code/DLC/account/service | 2 | 1.0% |
| accessory | 2 | 1.0% |
| console/hardware | 1 | 0.5% |
| strategy guide/manual/book | 1 | 0.5% |

Representative examples:

- eBay item-specific Game Name conflict
  - Amazon: Wii Play Motion (Nintendo Wii)
    eBay: Go Play Lumberjacks - Wii - Action/Adventure Game - W/ User Manual
    Evidence: Game Name=Go Play Lumberjacks; category=Video Games; Video Games & Consoles; current rules=Probable Match
  - Amazon: NBA 2K19 - Nintendo Switch [Nintendo Switch]
    eBay: NBA 2K26 (2026) 2K Sports Basketball Scripts - PC/PS4/PS5/Xbox/Switch
    Evidence: Game Name=NBA 2K26; category=Video Games; Video Games & Consoles; current rules=Probable Match
  - Amazon: Wii Sports (Nintendo Selects)
    eBay: Mario Power Tennis Nintendo Selects Nintendo Wii New Sealed
    Evidence: Game Name=Mario Power Tennis [Nintendo Selects]; category=Video Games; Video Games & Consoles; current rules=Probable Match
- title ambiguity from a short/generic game name
  - Amazon: Splatoon
    eBay: Splatoon 17" Foil Balloon (Packaged)
    Evidence: Game Name=--; category=Home & Garden; Greeting Cards & Party Supply; Party Supplies; Balloons; current rules=Probable Match
  - Amazon: Deca Sports
    eBay: Ready to Apply DIY Made to Order Iron On Custom Vinyl Deca\|TREE 🎄 DESIGN Adida
    Evidence: Game Name=--; category=Crafts; Fabric Painting & Decorating; Fabric Transfers; current rules=excluded keyword: steam; digital/download listing: steam
  - Amazon: Wii Play Motion (Nintendo Wii)
    eBay: Nintendo Wii Wii Play Game BRAND NEW SEALED
    Evidence: Game Name=Wii Play; category=Video Games & Consoles; Video Games; current rules=Probable Match
- unclear/insufficient evidence
  - Amazon: Super Mario Maker for Nintendo 3DS - Nintendo 3DS
    eBay: Super Mario Maker for Nintendo 3DS Magnet Set 2016 NEW
    Evidence: Game Name=Super Mario Maker; category=Video Games; Video Games & Consoles; current rules=Probable Match
  - Amazon: Animal Crossing: New Horizons - Nintendo Switch
    eBay: Nintendo Switch (Lite) Game Traveler Action Pack - Animal Crossing New Horizons
    Evidence: Game Name=Animal Crossing; category=Video Games; Video Games & Consoles; current rules=Probable Match
  - Amazon: Mario Kart 8 Deluxe - US Version
    eBay: Mario Kart 8 Deluxe Luigi Kart - Nintendo Switch McDonald’s 2024 Happy Meal
    Evidence: Game Name=--; category=Fast Food; Toys & Hobbies; Fast Food & Cereal Premiums; current rules=Probable Match
- controller/peripheral
  - Amazon: Rock Band 3 [video game]
    eBay: NEW Rock Band 4 3 2 1 DOUBLE DRUM PEDAL CABLE splitter XBox 1/360 PS4 PS3 Wii-U
    Evidence: Game Name=--; category=Controllers & Attachments; Video Games & Consoles; Video Game Accessories; current rules=accessory/not game: cable, pedal; eBay category is not Video Games software
  - Amazon: Rock Band 3 [video game]
    eBay: Rock Band Battery Cover RockBand 2 3 4 Fender Stratocaster Guitar Wireless Drums
    Evidence: Game Name=--; category=Controllers & Attachments; Video Games & Consoles; Video Game Accessories; current rules=accessory/not game: battery cover; eBay category is not Video Games software
  - Amazon: Rock Band 3 [video game]
    eBay: Rock Band Replacement Drum Sticks Set For Wii PS2 PS3 PS4 Xbox 360 9825
    Evidence: Game Name=--; category=Controllers & Attachments; Video Games & Consoles; Video Game Accessories; current rules=eBay category is not Video Games software
- collectible/merchandise
  - Amazon: House of the Dead: Overkill - Nintendo Wii
    eBay: PosterThe House Of The Dead Overkill Nintendo Wii BOX ART Unframed Print B1343
    Evidence: Game Name=--; category=Entertainment Memorabilia; Movie Memorabilia; Posters; Reproductions; 2000-Now; current rules=Probable Match
  - Amazon: Splatoon
    eBay: NEW w/ Tags Nintendo Green Squid 8" Plush Splatoon Switch Wii U 2 Game Character
    Evidence: Game Name=--; category=Action Figures; Toys & Hobbies; Action Figures & Accessories; current rules=accessory/not game: plush; eBay category is not Video Games software
  - Amazon: Donkey Kong Country Returns
    eBay: Donkey Kong Country Returns 3D Shopping Tote
    Evidence: Game Name=--; category=Video Games & Consoles; Video Game Merchandise; current rules=excluded keyword: promo, promotional; accessory/not game: type: Tote Bag
- toy/figure/card
  - Amazon: UFC
    eBay: Derek Brunson 2017 Topps Chrome UFC
    Evidence: Game Name=--; category=Sports Mem, Cards & Fan Shop; Sports Trading Cards; Trading Card Singles; current rules=accessory/not game: topps, type: Sports Trading Card; eBay category is not Video Games software
  - Amazon: UFC
    eBay: LOT OF (2) 2022 UFC Paul Craig RC's Rookie - Base Prizm + Select Prizm
    Evidence: Game Name=--; category=Sports Mem, Cards & Fan Shop; Sports Trading Cards; Trading Card Lots; current rules=accessory/not game: type: Sports Trading Card; eBay category is not Video Games software
  - Amazon: UFC
    eBay: 2023 Jessica Andrade Panini Card UFC
    Evidence: Game Name=--; category=Sports Mem, Cards & Fan Shop; Sports Trading Cards; Trading Card Lots; current rules=accessory/not game: panini, type: Sports Trading Card; eBay category is not Video Games software
- bundle containing a different game
  - Amazon: Asphalt 3D
    eBay: HO Slot Car Body - Super Late Model Asphalt - Custom 3D Printed - Tjet
    Evidence: Game Name=--; category=Toys & Hobbies; Slot Cars; HO Scale; 1970-Now; current rules=Probable Match
  - Amazon: Asphalt 3D
    eBay: HO Slot Car Body - Outlaw Super Late Model Asphalt - Custom 3D Printed - Tjet
    Evidence: Game Name=--; category=Toys & Hobbies; Slot Cars; HO Scale; 1970-Now; current rules=Probable Match
- wrong numbered installment
  - Amazon: Rock Band 3 [video game]
    eBay: New Set (2)  Rock Band Drum Sticks Wii PlayStation XBOX PS3 PS4 Rockband Drums
    Evidence: Game Name=--; category=Controllers & Attachments; Video Games & Consoles; Video Game Accessories; current rules=eBay category is not Video Games software; numeric sequel/year mismatch
  - Amazon: Dance Central 3 [video game]
    eBay: $30 New "Everybody Dance 2" PS3 NEW SEALED -PERFECT BIRTHDAY GIFT LET'S DANCE !
    Evidence: Game Name=--; category=Video Games; Video Games & Consoles; current rules=numeric sequel/year mismatch
- digital code/DLC/account/service
  - Amazon: Guitar Hero World Tour [video game]
    eBay: NEW Band/Guitar Hero 5/World Tour FACEPLATE for Nintendo Wii BATTLED Wood skin
    Evidence: Game Name=--; category=Faceplates, Decals & Stickers; Video Games & Consoles; Video Game Accessories; current rules=digital/download listing: skin; accessory/not game: faceplate; eBay category is not Video Games software; numeric sequel/year mismatch
  - Amazon: Forza Horizon 3 – Xbox One [video game]
    eBay: Forza Horizon 3 Controller Stand 2.0 & Carbon Controller Skin Xbox One NEW READ
    Evidence: Game Name=--; category=Other Video Game Accessories; Video Games & Consoles; Video Game Accessories; current rules=digital/download listing: skin; accessory/not game: controller; eBay category is not Video Games software
- accessory
  - Amazon: Guitar Hero World Tour [video game]
    eBay: NEW Band/Guitar Hero 5/World Tour FACEPLATE Nintendo Wii PINK GIRL Replacement
    Evidence: Game Name=--; category=Faceplates, Decals & Stickers; Video Games & Consoles; Video Game Accessories; current rules=accessory/not game: faceplate; eBay category is not Video Games software; numeric sequel/year mismatch
  - Amazon: Guitar Hero World Tour [video game]
    eBay: NEW Band/Guitar Hero 5/World Tour FACEPLATE for Nintendo Wii MILITIA replacement
    Evidence: Game Name=--; category=Faceplates, Decals & Stickers; Video Games & Consoles; Video Game Accessories; current rules=accessory/not game: faceplate; eBay category is not Video Games software; numeric sequel/year mismatch
- console/hardware
  - Amazon: Witcher 3: Wild Hunt - Nintendo Switch [video game]
    eBay: The Witcher 3 The Wild Hunt Switch Travel Case - PowerA CD Projekt Red - 2019
    Evidence: Game Name=--; category=Original Game Cases & Boxes; Video Games & Consoles; current rules=Probable Match
- strategy guide/manual/book
  - Amazon: Brothers In Arms: Hell's Highway - Playstation 3
    eBay: Brothers In Arms Hell's Highway Prima Official Game Guide For XBOX 360 PS3 PC
    Evidence: Game Name=Brothers in Arms: Hell's Highway; category=Books & Magazines; Books; current rules=accessory/not game: type: Strategy Guide; eBay category is not Video Games software

## Section 5 - Existing Rule Miss Analysis

| Classification | Count | Pct |
| --- | --- | --- |
| no current deterministic rule covers pattern | 587 | 81.9% |
| current rule should already block | 109 | 15.2% |
| evidence unavailable before detail but available afterward | 19 | 2.6% |
| current rule produces review/probable non-match | 2 | 0.3% |

Top current hard-block signals among dismissed identity examples:

| Signal | Count |
| --- | --- |
| non-US item location | 57 |
| numeric sequel/year mismatch | 30 |
| eBay category is not Video Games software | 19 |
| edition/version mismatch signal | 16 |
| platform mismatch: Amazon PS 4, eBay Xbox One | 8 |
| unsupported sourcing platform: DS | 5 |
| excluded keyword: download | 3 |
| item-specific Game Name identifies a different game | 3 |
| platform mismatch: Amazon PS 4, eBay PS 3 | 3 |
| accessory/not game: faceplate | 3 |
| pickup-only listing | 3 |
| digital/download listing: modded | 2 |
| digital/download listing: eridium | 2 |
| accessory/not game: cable, pedal | 2 |
| digital/download listing: skin | 2 |

## Section 6 - Notes Analysis

Rows with notes: 33 of 1000.

| Recurring note term | Count |
| --- | --- |
| version | 10 |
| professional | 10 |
| edition | 7 |
| wii | 5 |
| price | 4 |
| too | 4 |
| high | 4 |
| ebay | 4 |
| windows | 4 |
| sale | 2 |
| deluxe | 2 |
| party | 2 |
| nfr | 1 |
| shipping | 1 |
| pickup | 1 |
| only | 1 |
| has | 1 |
| employee | 1 |
| purchase | 1 |
| sticker | 1 |
| making | 1 |
| non-resellable | 1 |
| different | 1 |
| games | 1 |
| digital | 1 |

No new structured dismissal reason is recommended unless operator review confirms a recurring distinction that cannot be expressed by the existing identity/condition split.

## Section 7 - Image and Description Dependency

| Evidence dependency | Count | Pct |
| --- | --- | --- |
| title_plus_item_specifics_or_category | 651 | 77.1% |
| image_or_operator_visual_review | 121 | 14.3% |
| title_only | 71 | 8.4% |
| description | 1 | 0.1% |

Image-dependent rows are inferred from condition/packaging dismissals or insufficient textual metadata. No image AI was used.

## Section 8 - Deterministic Rule Candidates

| Rule | Pattern | Observed | Pct Identity | Fields | Behavior | Risk | Code | Tests |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| game_name_conflict_block | eBay item-specific Game Name conflicts with Amazon title | 414 | 57.7% | localizedAspects.Game Name | hard block when no meaningful overlap | low/medium | integrations/sourcing_match_rules.py: game_name_rule | Add item-specific Game Name conflict fixtures. |
| edition_alias_family_expansion | wrong-version edition aliases and content-pack variants | 276 | 38.5% | title, item specifics Features/Type | probable non-match or hard block for explicit conflicting families | medium | integrations/sourcing_match_rules.py: EDITION_SIGNALS / edition_rule | Add base-vs-deluxe, GOTY, starter-pack/content-pack fixtures. |
| short_title_stricter_identity | short/generic titles with weak identity evidence | 128 | 17.9% | title tokens, Game Name, platform | review flag or probable non-match | medium | integrations/sourcing_match_rules.py: title_overlap_rule / game_name_rule | Add one-word title and same-franchise wrong-game fixtures. |
| numeric_installment_year_conflict_tuning | sequel, installment, release-year, sports-year mismatch | 38 | 5.3% | title, Game Name, Release Year | hard block for clear conflicts; review for annual sports edge cases | medium | integrations/sourcing_match_rules.py: numeric_identity_rule | Add Just Dance, LEGO, sports-year safe/unsafe fixtures. |
| accessory_non_game_phrase_expansion | wrong-product accessories, guides, cases, merchandise | 5 | 0.7% | title, category, Type/Format, description | hard block for exact non-game phrases | low/medium | integrations/sourcing_match_rules.py: NOT_GAME_BLOCK_TERMS / category_rule | Add strategy guide, empty steelbook, replacement case, merch fixtures. |

## Section 9 - Historical Memory Effectiveness

| Repeated eBay item ID | Count |
| --- | --- |
| v1\|336711600319\|0 | 2 |
| v1\|396706750514\|0 | 2 |
| v1\|287351168212\|0 | 2 |
| v1\|178159317411\|0 | 2 |
| v1\|366103936379\|0 | 2 |
| v1\|327273856622\|0 | 2 |
| v1\|168313531540\|0 | 2 |
| v1\|318584093001\|0 | 2 |
| v1\|257552747121\|0 | 2 |
| v1\|386052227031\|0 | 2 |

| Repeated ASIN/title pair | Count |
| --- | --- |
| B00CZCA6RI \| assassin brotherhood creed | 31 |
| B000R0SRNU \| awaken force lego star wars | 25 |
| B07JMHZMX1 \| dungeon hero minecraft | 22 |
| B0140Z6SZQ \| jackbox pack party | 20 |
| B0056C2LIG \| play | 17 |
| B00I6E6SH6 \| dungeon hero minecraft | 16 |
| B0009Z3HYW \| combat gun top zone | 14 |
| B002BSA1C6 \| gran turismo | 13 |
| B0056C2LIG \| 09 all pga play tiger tour wood | 13 |
| B0056C2LIG \| 09 all madden nfl play | 12 |

| Repeated seller/ASIN/title | Count |
| --- | --- |
| hlqualitybuys \| B071NFMKR2 \| fantasy final online stormblood strategy xiv | 4 |
| sephiroth_ff7 \| B07JMHZMX1 \| dungeon hero minecraft | 2 |
| video_games_galore \| B00CZCA6RI \| assassin brotherhood creed | 2 |
| suziesclozet \| B0140Z6SZQ \| jackbox pack party rated teen | 2 |
| videogamerescuesquad \| B00CZCA6RI \| assassin brotherhood creed | 2 |
| retro_sold_here \| B001ET07O0 \| 5ft banner dead flag house lightgun of overkill sega | 2 |
| northmenresale \| B000BL3A5U \| element kameo of power | 2 |
| svtsupplychainus \| B07JMHZMX1 \| 3500 box code in minecoin minecraft with | 2 |
| svtsupplychainus \| B00I6E6SH6 \| 3500 box code in minecoin minecraft with | 2 |
| ecthe_0 \| B00168ESPI \| deca island sport | 2 |

Business dismissals were kept separate from identity analysis in this report, preserving the current rule that business reasons should not poison identity matching.

## Section 10 - Recommended Next Sprint

Expected directly addressable share from the top five conservative rule candidates: about 120.1% of identity dismissals, before overlap adjustment.

Recommended sprint:

1. Add focused regression fixtures from this report for wrong-version and wrong-product rows.
2. Tune edition/content-pack aliases and short-title identity review without hard-blocking single ambiguous edition words.
3. Strengthen item-specific Game Name and numeric conflict handling where stored evidence is explicit.
4. Expand exact accessory/non-game phrase tests only for low-risk terms.
5. Dry-run against recent opportunities, inspect potential false positives, then rescore only after operator approval.

Rollback strategy: keep changes in deterministic rule code behind tests, dry-run before write, and do not change historical actions or business dismissals.

