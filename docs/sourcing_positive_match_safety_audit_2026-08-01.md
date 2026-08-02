# Sourcing Positive Match Safety Audit

Date: 2026-08-01

Scope: read-only safety audit of confirmed positive sourcing matches. No production data, rules, scores, statuses, marketplace data, AI, or deployments were modified.

## Dataset

| Metric | Count |
| --- | --- |
| Raw positive evidence rows | 5612 |
| Deduplicated positive rows | 2353 |
| Authoritative confirmed positives | 2280 |
| Review-only watching rows | 73 |

The authoritative positive dataset includes deduplicated `matched_to_purchase`, `purchased_pending_match`, `purchased` actions, and `matching_intelligence_examples.match` rows. `watching` rows were audited separately as review-only because they are not confirmed purchases or verified matches.

## 34 vs 45 Reconciliation

The prior investigation reported 45 current-rule hard blocks across non-open positive/review statuses: 11 `watching`, 11 `purchased_pending_match`, and 23 `matched_to_purchase`. The 34 figure excludes the 11 `watching` rows and counts only accepted/purchased positive statuses. This audit treats 34 as the status-only confirmed-positive safety number and 45 as the broader status-only positive-or-review caution number.

The all-source deduplicated audit found 95 confirmed positives currently hard-blocked because it expands beyond status-only sourcing opportunities to include `matching_intelligence_examples.match` rows and purchased action history.

## Current Evaluator Blocks

| Rule family | Count |
| --- | --- |
| numeric | 23 |
| accessory | 21 |
| edition | 15 |
| location | 15 |
| platform | 8 |
| title_overlap | 6 |
| incomplete | 3 |
| other | 2 |
| game_name | 1 |
| digital | 1 |

Confirmed positives currently hard-blocked: 95.

| asin | amazon_title | ebay_title | current_hard_blocks |
| --- | --- | --- | --- |
| B01JY2YLHW | Vikings - Wolves of Midgard - Xbox One [Xbox One] | Kalypso Vikings Wolves of Midgard Special Edition Xbox One M Rated Action RPG | edition/version mismatch signal |
| B0050SYPV2 | Sniper: Ghost Warrior 2 - Xbox 360 | Sniper: Ghost Warrior 2 (Microsoft Xbox 360, 2013) Brand New Sealed | non-US item location |
| B07Q219M5D | Warhammer: Vermintide 2 Deluxe Edition Xbox One - Xbox One | Sealed Warhammer WH Vermintide 2 Deluxe Edition Microsoft Xbox One | item-specific Game Name identifies a different game |
| B00EFRN2IQ | The Sims 4 - PC/Mac | The SIMS 4 - for Windows PC & Mac NEW + The Sims 4 Get to Work Expansion Pack | pickup-only listing |
| B00K586O7A | NHL 15 - PlayStation 3 | NHL 15 - Sony playstation 3 PS3 - Complete In Box CIB | non-US item location |
| B06WWF1N6M | Middle-Earth: Shadow Of War Gold Edition - Xbox One | Xbox One X Enhanced Middle Earth Shadow of War Special Steelbook Gold Edition 2 | numeric sequel/year mismatch; edition/version mismatch signal |
| B096HSJ6PJ | Battlefield 2042 - PlayStation 5 [PlayStation 5] | Battlefield 2042 Sony PS5 Game 2021  Mature 17+ EA UltraHD New Sealed | non-US item location |
| B096WZFCHR | Marvel's Guardians of the Galaxy - PlayStation 5 [PlayStation 5] | Marvel's Guardians of the Galaxy (PS5) Brand New, Plastic Seal Has Torn | non-US item location |
| B000NIJ36G | All Pro Football 2K8 - Xbox 360 | All-Pro Football 2K8 Xbox 360 Brand New Sealed | non-US item location |
| B000QB05BM | Mercenaries 2: World in Flames - PC [video game] | Mercenaries 2: World in Flames (PC, 2008) | non-US item location |
| B00D8S4GRY | Just Dance 2014 - PlayStation 4 [video game] | NEW Just Dance 2015 ( Sony Playstation 4, PS4, 2014 ) | non-US item location |
| B000QB05BM | Mercenaries 2: World in Flames - PC [video game] | Mercenaries 2 World in Flames (PC DVD-ROM) *BRAND NEW SEALED* | non-US item location |
| B000QB05BM | Mercenaries 2: World in Flames - PC [video game] | Mercenaries 2 World In Flames PC DVD-Rom 2008 Brand New Sealed EA | non-US item location |
| B00KUY3DBE | Madden NFL 15 (Ultimate Edition) - Xbox One | Madden NFL 15 Ultimate Edition (Xbox One, 2014) Brand New And Factory Sealed! | non-US item location |
| B07L73DW8M | Mortal Kombat 11 (Nintendo Switch) [video game] | Mortal Kombat 11 (Nintendo Switch) Factory Sealed / Never Opened Game | non-US item location |
| B00ZP9GVH2 | Star Wars Battlefront (Xbox One) | Star Wars Battlefront (Microsoft Xbox One, 2015) Sealed | non-US item location |
| B09CQQ7T2L | Halo Infinite - Xbox Series X & Xbox One [video game] | NEW! Halo Infinite - Xbox Series X / Xbox One XB1 - New Factory Sealed | non-US item location |
| B09CQQ7T2L | Halo Infinite - Xbox Series X & Xbox One [video game] | NEW! Halo Infinite - Xbox Series X / Xbox One XB1 - New Factory Sealed | non-US item location |
| B004MXQ3DY | X-Men: Destiny | X-Men: Destiny (Microsoft Xbox 360, 2011) Brand New Sealed! | non-US item location |
| B00YC7DZ3G | fifa 16 - Xbox 360 [Xbox 360] | FIFA 16 - Standard Edition - (Xbox 360, 2016) | platform mismatch: Amazon Xbox 360, eBay PS 4 |
| B07MTZN8P3 | B07MTZN8P3 AmazonUs/BETH3 | The Elder Scrolls Online: Elsweyr - PlayStation 4 Standard Edition | no meaningful title token overlap |
| B01N9QVIRV | Switch Title 3 - | Splatoon 2 | no meaningful title token overlap |
| B00160PA80 | NCAA Football 09 - PlayStation 2 | PS2 NCAA Football 09 game (brand new, unsealed) | incomplete listing: unsealed |
| B003TK1HSM | Nickelodeon Fit [video game] | Nickelodeon Fit-Nintendo Wii & WIIU | platform mismatch: Amazon Wii, eBay Wii U |
| B072JY7NX5 | Wolfenstein II: The New Colossus - PlayStation 4 | Wolfenstein 2 II The New Colossus PlayStation 4 PS4 Sealed | numeric sequel/year mismatch |

The CSV contains every confirmed/review positive row and every current/proposed block flag. Markdown examples are capped at 25 rows per section for readability.

Canada location blocking is treated as intentional business policy for this audit. Canadian positives are still reported in the CSV when present, but this audit does not recommend relaxing the Canada location block.

## Proposed Rule Simulation

| Simulation | Confirmed positives blocked | Recommendation |
| --- | --- | --- |
| Game Name strict token-set block | 46 | Needs relaxation; exact token-set matching is too strict for confirmed positives. |
| Numeric/installment strict block | 511 | Needs relaxation and title-family guards before implementation. |
| Edition-family strict block | 70 | Needs relaxation; use review/penalty first unless high-confidence edition evidence exists. |
| Short-title strict block | 164 | Needs relaxation; short-title ambiguity should route to review, not hard block. |

### Game Name Simulation

| asin | amazon_title | ebay_title | game_name | game_name_strict_reason |
| --- | --- | --- | --- | --- |
| B07Q219M5D | Warhammer: Vermintide 2 Deluxe Edition Xbox One - Xbox One | Sealed Warhammer WH Vermintide 2 Deluxe Edition Microsoft Xbox One | Wh: Vermintide 2: Ultimate Edition | Game Name token-set mismatch: Wh: Vermintide 2: Ultimate Edition; extra_game=['ultimate', 'wh']; extra_amazon=['deluxe', 'warhammer'] |
| B00IQCRKP2 | Kinect Sports Rivals - XBOX One [video game] | Kinect Sports Rivals (Xbox One, 2014) Brand New Factory Sealed Rare Microsoft | Sports Rivals | Game Name token-set mismatch: Sports Rivals; extra_game=[]; extra_amazon=['kinect'] |
| B0794QSXP5 | Dragon Ball Fighterz - Xbox One [Xbox One] | Dragon Ball FighterZ - Microsoft Xbox One | Dragon Ball: Fighter Z | Game Name token-set mismatch: Dragon Ball: Fighter Z; extra_game=['fighter']; extra_amazon=['fighterz'] |
| B00ZJ211Q6 | Destiny: The Taken King - Legendary Edition - Xbox One [Xbox One] | Destiny: The Taken King - Legendary Edition - Xbox One New & Sealed (LK) | Destiny: The Taken King | Game Name token-set mismatch: Destiny: The Taken King; extra_game=[]; extra_amazon=['legendary'] |
| B00IQCRKP2 | Kinect Sports Rivals - XBOX One [video game] | Kinect Sports Rivals (Microsoft Xbox One, 2014) Brand New Sealed | Sports Rivals | Game Name token-set mismatch: Sports Rivals; extra_game=[]; extra_amazon=['kinect'] |
| B01LDUYU60 | Super Mario Maker for Nintendo 3DS - Nintendo 3DS | Super Mario Maker for 3DS - Nintendo Selects Edition - Nintendo 3DS sealed | Super Mario Maker for 3DS-Nintendo Selects Edition | Game Name token-set mismatch: Super Mario Maker for 3DS-Nintendo Selects Edition; extra_game=['select']; extra_amazon=[] |
| B01LDUYU60 | Super Mario Maker for Nintendo 3DS - Nintendo 3DS | Super Mario Maker for 3DS - Nintendo Selects Edition - Nintendo 3DS - Sealed | Super Mario Maker for 3DS-Nintendo Selects Edition | Game Name token-set mismatch: Super Mario Maker for 3DS-Nintendo Selects Edition; extra_game=['select']; extra_amazon=[] |
| B002SRNFX2 | Jumpstart Escape Adventure island - Nintendo Wii | JumpStart Escape from Adventure Island Video Game Nintendo Wii w/ Manual, Code | JumpStart: Escape from Adventure Island | Game Name token-set mismatch: JumpStart: Escape from Adventure Island; extra_game=['from']; extra_amazon=[] |
| B07FF3F7F9 | Subnautica - Xbox One [Xbox One] | Subnautica: Below Zero -- Standard Edition (Microsoft Xbox One/Xbox Series X/S, | Subnautica: below Zero | Game Name token-set mismatch: Subnautica: below Zero; extra_game=['below', 'zero']; extra_amazon=[] |
| B096NB1JS9 | Madden NFL 22 - PlayStation 4 [video game] | Madden NFL 22 for PS4 by EA Sports New Opened NFL Football Cib PlayStation 4 | Madden NFL Football | Game Name token-set mismatch: Madden NFL Football; extra_game=['football']; extra_amazon=['22'] |
| B072JLJ2GB | Assassin's Creed Origins - Xbox One Deluxe Edition | Assassin's Creed: Origins [Deluxe Edition] Microsoft Xbox One - Sealed | Assasain's Creed: Origins | Game Name token-set mismatch: Assasain's Creed: Origins; extra_game=['assasain']; extra_amazon=['assassin', 'deluxe'] |
| B072JZB85B | FIFA 18 (PS4) [video game] | FIFA 18 Bonus (Sony PlayStation 4, 2017) Brand New | Fifa 18 [Bonus] | Game Name token-set mismatch: Fifa 18 [Bonus]; extra_game=['bonu']; extra_amazon=[] |
| B07SJHN2LF | FIFA 20 Champions Edition - PlayStation 4 | EA SPORTS FIFA 20 Champions Edition PS4 E 2019 NTSC-U/C | FIFA 20 | Game Name token-set mismatch: FIFA 20; extra_game=[]; extra_amazon=['champion'] |
| B011AE8CXQ | Snoopy's Grand Adventure - PlayStation 4 | Peanuts Movie: Snoopy's Grand Adventure (Sony PlayStation 4, 2015) | Peanuts Movie: Snoopy's Grand Adventure | Game Name token-set mismatch: Peanuts Movie: Snoopy's Grand Adventure; extra_game=['movie', 'peanut']; extra_amazon=[] |
| B00AXI9WFS | DISNEY INFINITY Starter Pack Xbox 360 | Xbox 360 Disney Infinity Starter Pack 1.0 & Accessories Lot New/Sealed | Disney Infinity | Game Name token-set mismatch: Disney Infinity; extra_game=[]; extra_amazon=['pack', 'starter'] |
| B000HCQJZQ | Age of Empires III: The WarChiefs Expansion Pack PC | Age of Empires III The War Chiefs PC New Sealed with Slipcover | Age of Empires III: The War Chiefs | Game Name token-set mismatch: Age of Empires III: The War Chiefs; extra_game=['chief', 'war']; extra_amazon=['expansion', 'pack', 'warchief'] |
| B01MDNZOZP | Star Wars Battlefront Ultimate Edition - PlayStation 4 | Star Wars Battlefront Ultimate Edition (PS4) T Shooter VR Compatible | Star Wars Battlefront | Game Name token-set mismatch: Star Wars Battlefront; extra_game=[]; extra_amazon=['ultimate'] |
| B0081AWU4A | Just Dance Greatest Hits - Nintendo Wii | Just Dance Greatest Hits Nintendo Wii Brand New Factory Sealed | Just Dance | Game Name token-set mismatch: Just Dance; extra_game=[]; extra_amazon=['greatest', 'hits'] |
| B0039QWK0A | Guilty Party for wii | Disney Guilty Party (Nintendo Wii, 2010) Brand New Sealed | Disney Guilty Party | Game Name token-set mismatch: Disney Guilty Party; extra_game=['disney']; extra_amazon=[] |
| B00IQCRKP2 | Kinect Sports Rivals - XBOX One [video game] | Kinect Sports Rivals Microsoft Xbox One, 2014, Video Game BRAND NEW SEALED | Sports Rivals | Game Name token-set mismatch: Sports Rivals; extra_game=[]; extra_amazon=['kinect'] |
| B00I6E6SH6 | Minecraft – Xbox One [video game] | NEW Minecraft Starter Collection Xbox One Game 700 Minecoins Included Mint | Minecraft Starter Collection | Game Name token-set mismatch: Minecraft Starter Collection; extra_game=['starter']; extra_amazon=[] |
| B072JZB85B | FIFA 18 (PS4) [video game] | New Sealed EA Sports FIFA 18 For PS4 Rated E For Everyone | Fifa 18 [Bonus] | Game Name token-set mismatch: Fifa 18 [Bonus]; extra_game=['bonu']; extra_amazon=[] |
| B0062VM8LU | Final Fantasy XIII-2 Collector's Edition - Playstation 3 [PlayStation 3] | Final Fantasy XIII-2 Collector's Edition NEW factory sealed Playstation 3 PS3 | Final Fantasy XIII-2 | Game Name token-set mismatch: Final Fantasy XIII-2; extra_game=[]; extra_amazon=['collector'] |
| B072JZB85B | FIFA 18 (PS4) [video game] | New Sealed EA Sports FIFA 18 For PS4 Rated E For Everyone | Fifa 18 [Bonus] | Game Name token-set mismatch: Fifa 18 [Bonus]; extra_game=['bonu']; extra_amazon=[] |
| B00RUZPKYY | Disgaea 5: Alliance of Vengeance - PlayStation 4 | Disgaea 5: Alliance of Vengeance Bundle (Sony PlayStation 4, 2015) | Disgaea 5: Alliance of Vengeance [Bundle] | Game Name token-set mismatch: Disgaea 5: Alliance of Vengeance [Bundle]; extra_game=['bundle']; extra_amazon=[] |

### Numeric / Rock Band Simulation

Rock Band-related confirmed positives found: 31.
| asin | amazon_title | ebay_title | numeric_installment_strict_reason |
| --- | --- | --- | --- |
| B003RS8I92 | Rock Band 3 [video game] | Rock Band (Sony PlayStation 3, PS3) New Sealed In Box 🎸 | numeric/installment mismatch: amazon=['3'] ebay=[] shared=['band', 'rock'] |
| B003RS8I92 | Rock Band 3 [video game] | Rock Band Game PS3 Brand New & Factory Sealed-PlayStation 3 Rare Harmonix | numeric/installment mismatch: amazon=['3'] ebay=[] shared=['band', 'rock'] |
| B002AO7DHW | Rock Band: Country Track Pack - Nintendo Wii | Rock Band: Country Track Pack (Nintendo Wii, 2009) Brand New Sealed | numeric/installment mismatch: amazon=[] ebay=['2009'] shared=['band', 'country', 'pack', 'rock', 'track'] |
| B001TOQ8LG | The Beatles: Rock Band (Game Only) - Nintendo Wii | Rock Band the Beatles - Nintendo Wii |  |
| B001LJPAAO | AC/DC Live: Rock Band Track Pack - Nintendo Wii | AC/DC Live Rock Band Track Pack Nintendo Wii Video Game music rhythm concert |  |
| B001LJPAAO | AC/DC Live: Rock Band Track Pack - Nintendo Wii | AC/DC Live: Rock Band Track Pack (Nintendo Wii) New Sealed |  |
| B001LJPAAO | AC/DC Live: Rock Band Track Pack - Nintendo Wii | AC/DC Live: RockBand Track Pack Video Game For Nintendo Wii FACTORY SEALED |  |
| B001LJPAAO | AC/DC Live: Rock Band Track Pack - Nintendo Wii | New AC/DC Live: Rock Band Track Pack Nintendo Wii Game |  |
| B001LJPAAO | AC/DC Live: Rock Band Track Pack - Nintendo Wii | AC/DC Live: Rock Band Track Pack, NEW FACTORY SEALED (Nintendo Wii, 2008) | numeric/installment mismatch: amazon=[] ebay=['2008'] shared=['ac', 'band', 'dc', 'live', 'pack', 'rock', 'track'] |
| B001LJPAAO | AC/DC Live: Rock Band Track Pack - Nintendo Wii | AC/DC Live: Rock Band Track Pack Nintendo Wii Multiplayer Music Game 2008 | numeric/installment mismatch: amazon=[] ebay=['2008'] shared=['ac', 'band', 'dc', 'live', 'pack', 'rock', 'track'] |
| B001LJPAAO | AC/DC Live: Rock Band Track Pack - Nintendo Wii | AC/DC Live: Rock Band Track Pack  (Wii, 2008) Brand New Sealed | numeric/installment mismatch: amazon=[] ebay=['2008'] shared=['ac', 'band', 'dc', 'live', 'pack', 'rock', 'track'] |
| B001KAMZ8E | AC/DC Live: Rock Band Track Pack - Playstation 3 | AC/DC Live: Rock Band Track Pack (Sony PlayStation 3, 2008) BRAND NEW SEALED | numeric/installment mismatch: amazon=[] ebay=['2008'] shared=['ac', 'band', 'dc', 'live', 'pack', 'rock', 'track'] |
| B001LJPAAO | AC/DC Live: Rock Band Track Pack - Nintendo Wii | AC/DC Live: Rock Band Track Pack (Nintendo Wii, 2008), SEALED, Brand NEW | numeric/installment mismatch: amazon=[] ebay=['2008'] shared=['ac', 'band', 'dc', 'live', 'pack', 'rock', 'track'] |
| B002AO7DHW | Rock Band: Country Track Pack - Nintendo Wii | Rock Band: Country Track Pack (Nintendo Wii, 2009) Brand New Sealed | numeric/installment mismatch: amazon=[] ebay=['2009'] shared=['band', 'country', 'pack', 'rock', 'track'] |
| B002AO7DHW | Rock Band: Country Track Pack - Nintendo Wii | Brand New & Sealed Rock Band: Country Track Pack (Nintendo Wii, 2009) | numeric/installment mismatch: amazon=[] ebay=['2009'] shared=['band', 'country', 'pack', 'rock', 'track'] |
| B001LJPAAO | AC/DC Live: Rock Band Track Pack - Nintendo Wii | AC/DC Live: Rock Band Track Pack - Nintendo Wii Complete SEALED NEW |  |
| B002AO7DAY | Rock Band: Country Track Pack - Xbox 360 | Rock Band: Country Track Pack Microsoft Xbox 360 Brand NEW Factory Sealed! Rare. |  |
| B001KAMZ8E | AC/DC Live: Rock Band Track Pack - Playstation 3 | AC/DC Live: Rock Band Track Pack (Sony PlayStation 3, 2008) BRAND NEW SEALED | numeric/installment mismatch: amazon=[] ebay=['2008'] shared=['ac', 'band', 'dc', 'live', 'pack', 'rock', 'track'] |
| B001LJPAAO | AC/DC Live: Rock Band Track Pack - Nintendo Wii | AC/DC Live Rock Band Track Pack Nintendo Wii Video Game NEW |  |
| B001LJPAAO | AC/DC Live: Rock Band Track Pack - Nintendo Wii | AC/DC Live: Rock Band Track Pack |  |
| B001F03MY0 | Rock Band Track Pack: Vol. 2 - PlayStation 2 | Rock Band Track Pack: Vol. 2 |  |
| B001KAMZ8E | AC/DC Live: Rock Band Track Pack - Playstation 3 | AC/DC Live: Rock Band Track Pack |  |
| B003RS8I92 | Rock Band 3 | ROCK BAND 3 |  |
| B002ARW2CA | Rock Band: Country Track Pack | Rock Band Country Track Pack |  |
| B001BXA9CE | Rock Band 2 - Nintendo Wii (Game only) | Rock Band 2 |  |

Numeric simulation examples:
| asin | amazon_title | ebay_title | numeric_installment_strict_reason |
| --- | --- | --- | --- |
| B00NP8J1UY | Need for Speed Rivals Complete Edition - Xbox One | Need for Speed Rivals Complete Edition - Xbox One - 2014 - NEW Sealed | numeric/installment mismatch: amazon=[] ebay=['2014'] shared=['complete', 'need', 'rival', 'speed'] |
| B0050SYPV2 | Sniper: Ghost Warrior 2 - Xbox 360 | Sniper: Ghost Warrior 2 (Microsoft Xbox 360, 2013) Brand New Sealed | numeric/installment mismatch: amazon=['2'] ebay=['2', '2013'] shared=['ghost', 'sniper', 'warrior'] |
| B000P0SETO | Madden NFL 08 - Playstation 3 [PlayStation 3] | Madden NFL 08 (Sony PlayStation 3, 2007) Sealed | numeric/installment mismatch: amazon=['8'] ebay=['2007', '8'] shared=['08', 'madden', 'nfl'] |
| B00182QCXS | DEAL OR NO DEAL WII [Nintendo Wii] | Deal or No Deal (Nintendo Wii, 2009) Brand New | numeric/installment mismatch: amazon=[] ebay=['2009'] shared=['deal', 'no', 'or'] |
| B00IQCRKP2 | Kinect Sports Rivals - XBOX One [video game] | Kinect Sports Rivals (Xbox One, 2014) Brand New Factory Sealed Rare Microsoft | numeric/installment mismatch: amazon=[] ebay=['2014'] shared=['kinect', 'rival', 'sport'] |
| B06WWF1N6M | Middle-Earth: Shadow Of War Gold Edition - Xbox One | Xbox One X Enhanced Middle Earth Shadow of War Special Steelbook Gold Edition 2 | numeric/installment mismatch: amazon=[] ebay=['2'] shared=['earth', 'gold', 'middle', 'of', 'shadow', 'war'] |
| B08FS6BB8W | Far Cry 6 PlayStation 5 Standard Edition [PlayStation 5] | Far Cry 6 Standard Edition (Sony PlayStation 5, 2020) | numeric/installment mismatch: amazon=['6'] ebay=['2020', '6'] shared=['cry', 'far'] |
| B01GOK4FX2 | NHL 17 Deluxe Edition - PlayStation 4 [PlayStation 4] | NHL 17: Deluxe Edition (Sony PlayStation 4, 2016) - Near Mint Disc - CIB | numeric/installment mismatch: amazon=['17'] ebay=['17', '2016'] shared=['17', 'deluxe', 'nhl'] |
| B096HSJ6PJ | Battlefield 2042 - PlayStation 5 [PlayStation 5] | Battlefield 2042 Sony PS5 Game 2021  Mature 17+ EA UltraHD New Sealed | numeric/installment mismatch: amazon=['2042'] ebay=['17', '2021', '2042'] shared=['battlefield'] |
| B096WZFCHR | Marvel's Guardians of the Galaxy - PlayStation 5 [PlayStation 5] | New Marvel's Guardians of the Galaxy (Sony PlayStation 5 PS5, 2021) | numeric/installment mismatch: amazon=[] ebay=['2021'] shared=['galaxy', 'guardian', 'marvel', 'of'] |
| B00IQCRKP2 | Kinect Sports Rivals - XBOX One [video game] | Kinect Sports Rivals (Microsoft Xbox One, 2014) Brand New Sealed | numeric/installment mismatch: amazon=[] ebay=['2014'] shared=['kinect', 'rival', 'sport'] |
| B07BHHDTL4 | Sonic Mania Plus - PlayStation 4 [PlayStation 4] | Sonic Mania (Sony PlayStation 4, 2018) *NEW LOOSE DISC* | numeric/installment mismatch: amazon=[] ebay=['2018'] shared=['mania', 'sonic'] |
| B072JZB85B | FIFA 18 (PS4) [video game] | FIFA 18 , Tom Clancy’s The Division & Destiny 2 , Lot Of 3 , PS4 Free Shipping | numeric/installment mismatch: amazon=['18'] ebay=['18', '2', '3'] shared=['18', 'fifa'] |
| B072JZB85B | FIFA 18 (PS4) [video game] | FIFA 18 , Destiny 2 & Battleborn Lot Of 3 (PS4) | numeric/installment mismatch: amazon=['18'] ebay=['18', '2', '3'] shared=['18', 'fifa'] |
| B0051TLAF4 | LEGO Harry Potter: Years 5-7 - Xbox 360 [Xbox 360] | New LEGO Harry Potter Years 5-7 (Microsoft Xbox 360, 2011) | numeric/installment mismatch: amazon=['5', '7'] ebay=['2011', '5', '7'] shared=['harry', 'lego', 'potter', 'year'] |
| B07K85L726 | Devil May Cry 5 (Xbox One) [video game] | Devil May Cry 5 (Xbox, 2019) * New,Sealed* | numeric/installment mismatch: amazon=['5'] ebay=['2019', '5'] shared=['cry', 'devil', 'may'] |
| B00K1JBMGQ | NBA 2K15 - Xbox 360 | NBA 2K15 (Microsoft Xbox 360, 2014) BRAND NEW Seal Tare | numeric/installment mismatch: amazon=[] ebay=['2014'] shared=['2k15', 'nba'] |
| B000Q4SREG | MySims - Nintendo Wii | MySims Wii Nintendo 2007 Simulation E Rated EA Game Manual Included Factory Seal | numeric/installment mismatch: amazon=[] ebay=['2007'] shared=['mysim'] |
| B011I7WJUM | Goosebumps the Game 3DS - Nintendo 3DS | Goosebumps: The Game (Nintendo 3DS, 2015) Brand NEW / Sealed | numeric/installment mismatch: amazon=[] ebay=['2015'] shared=['goosebump'] |
| B000QB05BM | Mercenaries 2: World in Flames - PC [video game] | Mercenaries 2: World in Flames (PC, 2008) | numeric/installment mismatch: amazon=['2'] ebay=['2', '2008'] shared=['flame', 'in', 'mercenarie', 'world'] |
| B072JZB85B | FIFA 18 (PS4) [video game] | FIFA 18 Bonus (Sony PlayStation 4, 2017) Brand New | numeric/installment mismatch: amazon=['18'] ebay=['18', '2017'] shared=['18', 'fifa'] |
| B07SJHN2LF | FIFA 20 Champions Edition - PlayStation 4 | EA SPORTS FIFA 20 Champions Edition PS4 E 2019 NTSC-U/C | numeric/installment mismatch: amazon=['20'] ebay=['20', '2019'] shared=['20', 'champion', 'fifa'] |
| B01GWGX836 | Just Dance 2017 - PlayStation 4 | Ubisoft Just Dance 2017 PS4 Multiplayer E10+ NTSC-U/C 2016 Just Dance | numeric/installment mismatch: amazon=['2017'] ebay=['2016', '2017'] shared=['dance', 'just'] |
| B003RS8I92 | Rock Band 3 [video game] | Rock Band (Sony PlayStation 3, PS3) New Sealed In Box 🎸 | numeric/installment mismatch: amazon=['3'] ebay=[] shared=['band', 'rock'] |
| B0013EF17O | Speed Racer: The Videogame - Nintendo Wii | Speed Racer: The Videogame (Nintendo Wii, 2008) STILL SEALED! | numeric/installment mismatch: amazon=[] ebay=['2008'] shared=['racer', 'speed', 'videogame'] |

### Edition-Family Safety

| asin | amazon_title | ebay_title | edition_family_strict_reason |
| --- | --- | --- | --- |
| B01JY2YLHW | Vikings - Wolves of Midgard - Xbox One [Xbox One] | Kalypso Vikings Wolves of Midgard Special Edition Xbox One M Rated Action RPG | edition-family mismatch: amazon=[] ebay=['special'] |
| B00K586O7A | NHL 15 - PlayStation 3 | NHL 15 - Sony playstation 3 PS3 - Complete In Box CIB | edition-family mismatch: amazon=[] ebay=['complete'] |
| B06WWF1N6M | Middle-Earth: Shadow Of War Gold Edition - Xbox One | Xbox One X Enhanced Middle Earth Shadow of War Special Steelbook Gold Edition 2 | edition-family mismatch: amazon=['gold'] ebay=['gold', 'steelbook'] |
| B01LDUYU60 | Super Mario Maker for Nintendo 3DS - Nintendo 3DS | Super Mario Maker for 3DS - Nintendo Selects Edition - Nintendo 3DS sealed | edition-family mismatch: amazon=[] ebay=['nintendo_selects'] |
| B01LDUYU60 | Super Mario Maker for Nintendo 3DS - Nintendo 3DS | Super Mario Maker for 3DS - Nintendo Selects Edition - Nintendo 3DS - Sealed | edition-family mismatch: amazon=[] ebay=['nintendo_selects'] |
| B007MM9E2E | Disney Epic Mickey 2: The Power of Two - Playstation 3 [video game] | Disney Epic Mickey 2 the Power of Two Complete PS3 Brand New Sealed | edition-family mismatch: amazon=[] ebay=['complete'] |
| B00D3RBZHY | Need for Speed: Rivals [PlayStation 4] | Electronic Arts Need for Speed Rivals PS4 PlayStation Hits Multiplayer Racing | edition-family mismatch: amazon=[] ebay=['playstation_hits'] |
| B072N865DQ | ARK: Survival Evolved (Xbox One) [video game] | Ark Survival Evolved (Xbox One, 2017) - NIB Complete Brand New & Sealed | edition-family mismatch: amazon=[] ebay=['complete'] |
| B01LDUYU60 | Super Mario Maker for Nintendo 3DS - Nintendo 3DS | Super Mario Maker for 3DS - Nintendo Selects Edition - Nintendo 3DS New Sealed | edition-family mismatch: amazon=[] ebay=['nintendo_selects'] |
| B003TJVKAS | Deca Sports Freedom Kinect | Deca Sports Freedom (Microsoft Xbox 360, 2010, Kinect) Brand New Factory Sealed! | edition-family mismatch: amazon=[] ebay=['complete'] |
| B009E480RS | Dance Central 3 - Xbox 360 | Kinect Dance Central 3 (Microsoft Xbox 360) Brand New Sealed Authentic | edition-family mismatch: amazon=[] ebay=['complete'] |
| B002NN7AKU | God of War: Collection - Playstation 3 | Sony God of War Collection PS3 w/ God of War I & II HD Remastered, Sealed In Box | edition-family mismatch: amazon=[] ebay=['remaster'] |
| B00ZP9GVH2 | Star Wars Battlefront (Xbox One) | Star Wars Battlefront (Microsoft Xbox One, 2015) Factory Sealed New | edition-family mismatch: amazon=[] ebay=['complete'] |
| B002I0K3Z2 | Dance Central 3 [video game] | Kinect Dance Central 3 (Microsoft Xbox 360) Brand New Sealed Authentic | edition-family mismatch: amazon=[] ebay=['complete'] |
| B01LDUYU60 | Super Mario Maker for Nintendo 3DS - Nintendo 3DS | Super Mario Maker for 3DS - Nintendo Selects Edition - Nintendo 3DS - Brand New! | edition-family mismatch: amazon=[] ebay=['nintendo_selects'] |
| B01LDUYU60 | Super Mario Maker for Nintendo 3DS - Nintendo 3DS | Super Mario Maker for 3DS - Nintendo Selects Edition - Nintendo 3DS sealed | edition-family mismatch: amazon=[] ebay=['nintendo_selects'] |
| B01LDUYU60 | Super Mario Maker for Nintendo 3DS - Nintendo 3DS | Super Mario Maker for 3DS - Nintendo Selects Edition - Nintendo 3DS - Sealed | edition-family mismatch: amazon=[] ebay=['nintendo_selects'] |
| B072N865DQ | ARK: Survival Evolved (Xbox One) [video game] | Ark Survival Evolved (Xbox One, 2017) - NIB Complete Brand New & Sealed | edition-family mismatch: amazon=[] ebay=['complete'] |
| B01LDUYU60 | Super Mario Maker for Nintendo 3DS - Nintendo 3DS | Super Mario Maker for 3DS - Nintendo Selects Edition - Nintendo 3DS New Sealed | edition-family mismatch: amazon=[] ebay=['nintendo_selects'] |
| B01IW7Z746 | Nintendo Land | Nintendo Land Nintendo Selects (Nintendo Wii U, 2016) Brand New Factory Sealed | edition-family mismatch: amazon=[] ebay=['nintendo_selects'] |
| B01LDUYU60 | Super Mario Maker for Nintendo 3DS - Nintendo 3DS | Super Mario Maker Nintendo 3DS Brand New Factory Sealed Nintendo Selects | edition-family mismatch: amazon=[] ebay=['nintendo_selects'] |
| B00D3RBZHY | Need for Speed: Rivals [PlayStation 4] | Electronic Arts Need for Speed Rivals PS4 PlayStation Hits Multiplayer Racing | edition-family mismatch: amazon=[] ebay=['playstation_hits'] |
| B01LDUYU60 | Super Mario Maker for Nintendo 3DS - Nintendo 3DS | Super Mario Maker Nintendo 3DS Brand New Factory Sealed Nintendo Selects | edition-family mismatch: amazon=[] ebay=['nintendo_selects'] |
| B00K586O7A | NHL 15 - PlayStation 3 | NHL 15 - Sony playstation 3 PS3 - Complete In Box CIB | edition-family mismatch: amazon=[] ebay=['complete'] |
| B06WWF1N6M | Middle-Earth: Shadow Of War Gold Edition - Xbox One [Xbox One] | Xbox One X Enhanced Middle Earth Shadow of War Special Steelbook Gold Edition 2 | edition-family mismatch: amazon=['gold'] ebay=['gold', 'steelbook'] |

### Short-Title Safety

| asin | amazon_title | ebay_title | short_title_strict_reason |
| --- | --- | --- | --- |
| B07HFMJ4R5 | Minecraft: Starter Collection - Xbox One [Xbox One] | Minecraft Starter Collection - Xbox One NEW Cellophane Tear | short-title extra candidate tokens: shared=['minecraft', 'starter'] extra=['cellophane', 'tear'] |
| B096HSJ6PJ | Battlefield 2042 - PlayStation 5 [PlayStation 5] | Battlefield 2042 Sony PS5 Game 2021  Mature 17+ EA UltraHD New Sealed | short-title extra candidate tokens: shared=['battlefield'] extra=['17', 'ea', 'mature', 'ultrahd'] |
| B004FUI84G | Prototype 2 PS3 - PlayStation 3 [PlayStation 3] | PS3 Prototype 2 (Sony Playstation 3) NEW SEALED Free Shipping W/ Slipcover | short-title extra candidate tokens: shared=['prototype'] extra=['slipcover'] |
| B072JZB85B | FIFA 18 (PS4) [video game] | FIFA 18 , Tom Clancy’s The Division & Destiny 2 , Lot Of 3 , PS4 Free Shipping | short-title extra candidate tokens: shared=['18', 'fifa'] extra=['clancy', 'destiny', 'division', 'lot', 'of', 'tom'] |
| B072JZB85B | FIFA 18 (PS4) [video game] | FIFA 18 , Destiny 2 & Battleborn Lot Of 3 (PS4) | short-title extra candidate tokens: shared=['18', 'fifa'] extra=['battleborn', 'destiny', 'lot', 'of'] |
| B01MTQWAFN | Watch Dogs 2 Xbox One | Cokem Watch Dogs 2 (Xbox One) | short-title extra candidate tokens: shared=['dogs', 'watch'] extra=['cokem'] |
| B00XR3YBNO | WWE 2K16 - PlayStation 3 | 2K WWE 2K16 Wrestling Sports Game, T Teen, Multiplayer Online, Sony PS3 | short-title extra candidate tokens: shared=['2k16', 'wwe'] extra=['2k', 'multiplayer', 'online', 'sport', 'teen', 'wrestling'] |
| B000Q4SREG | MySims - Nintendo Wii | MySims Wii Nintendo 2007 Simulation E Rated EA Game Manual Included Factory Seal | short-title extra candidate tokens: shared=['mysim'] extra=['ea', 'included', 'manual', 'rated', 'seal', 'simulation'] |
| B0C2F82HSS | Paleo Pines | Paleo Pines: The Dino Valley (XSX) | short-title extra candidate tokens: shared=['paleo', 'pine'] extra=['dino', 'valley', 'xsx'] |
| B00K1JBMGQ | NBA 2K15 - Xbox 360 | NBA 2K15 (Microsoft Xbox 360, 2014) BRAND NEW Seal Tare | short-title extra candidate tokens: shared=['2k15', 'nba'] extra=['seal', 'tare'] |
| B01GWGX836 | Just Dance 2017 - PlayStation 4 | Ubisoft Just Dance 2017 PS4 Multiplayer E10+ NTSC-U/C 2016 Just Dance | short-title extra candidate tokens: shared=['dance', 'just'] extra=['e10', 'multiplayer', 'ubisoft'] |
| B0039QWK0A | Guilty Party for wii | Disney Guilty Party (Nintendo Wii, 2010) Brand New Sealed | short-title extra candidate tokens: shared=['guilty', 'party'] extra=['disney'] |
| B01E6239QY | NBA 2K17 | NBA 2K17 - Early Tip Off Edition | short-title extra candidate tokens: shared=['2k17', 'nba'] extra=['early', 'off', 'tip'] |
| B0043B5SKE | Fighters Uncaged - Xbox 360 | Fighters Uncaged Kinect XBOX 360 Factory Sealed Brand New Video Game | short-title extra candidate tokens: shared=['fighter', 'uncaged'] extra=['kinect'] |
| B0060ZN5T2 | Just Dance 3 | Just Dance 3 (Nintendo Wii, 2011) Target Exclusive Edition New Sealed | short-title extra candidate tokens: shared=['dance', 'just'] extra=['exclusive', 'target'] |
| B072JZB85B | FIFA 18 (PS4) [video game] | New Sealed EA Sports FIFA 18 For PS4 Rated E For Everyone | short-title extra candidate tokens: shared=['18', 'fifa'] extra=['ea', 'everyone', 'rated', 'sport'] |
| B00I6E6SH6 | Minecraft – Xbox One [video game] | NEW Minecraft Starter Collection Xbox One Game 700 Minecoins Included. Sealed. | short-title extra candidate tokens: shared=['minecraft'] extra=['700', 'included', 'minecoin', 'starter'] |
| B00I6E6SH6 | Minecraft – Xbox One [video game] | Minecraft Starter Collection - Xbox One, New Xbox One,Xbox One Video Games | short-title extra candidate tokens: shared=['minecraft'] extra=['starter'] |
| B01IW7Z746 | Nintendo Land | Nintendo Land Nintendo Selects (Nintendo Wii U, 2016) Brand New Factory Sealed | short-title extra candidate tokens: shared=['land'] extra=['select'] |
| B0060ZN5T2 | Just Dance 3 Wii | Just Dance 3 (Nintendo Wii) BRAND NEW Factory Sealed - NTSC Ships Fast | short-title extra candidate tokens: shared=['dance', 'just'] extra=['ntsc'] |
| B0060ZN5T2 | Just Dance 3 Wii | Just Dance 3 (Nintendo Wii) NEW Factory Sealed \| Ubisoft Dance Game | short-title extra candidate tokens: shared=['dance', 'just'] extra=['ubisoft'] |
| B07FF3F7F9 | Subnautica - Xbox One [Xbox One] | Subnautica: Below Zero -- Standard Edition (Microsoft Xbox One/Xbox Series X/S, | short-title extra candidate tokens: shared=['subnautica'] extra=['below', 'zero'] |
| B01GWGX74Q | Just Dance 2017 - Wii [video game] | Just Dance 2017 - Wii #ABOR | short-title extra candidate tokens: shared=['dance', 'just'] extra=['abor'] |
| B002I0HJZO | Battlefield 3 PC | Battlefield 3 (Windows PC, 2011) 2 DVD set SEALED!! | short-title extra candidate tokens: shared=['battlefield'] extra=['set'] |
| B0032FCM6U | MLB 2K10 - PC | Major League Baseball 2K10 PC Brand NEW Factory SEALED | short-title extra candidate tokens: shared=['2k10'] extra=['baseball', 'league', 'major'] |

## Recommendations

- Presentation gate: safe to deploy as written. It only honors stored hard-block diagnostics for `open` rows before presentation and does not rescore or modify confirmed positives.
- Safe now: enforcement of already-stored hard blocks at presentation; exact historical negative memory for future candidates when the positive-memory conflict is absent.
- Needs relaxation: strict Game Name token-set blocks, Rock Band/Rock Band 3-style numeric blocks, expanded edition-family hard blocks, and short-title hard blocks.
- Recommended backoff: use review/probable-non-match for proposed identity expansions until confirmed-positive fixtures are added and false positives are cleared.
