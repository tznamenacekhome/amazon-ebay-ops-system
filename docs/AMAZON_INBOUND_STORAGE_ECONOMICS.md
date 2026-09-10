# Amazon inbound and storage economics

Analysis date: September 9, 2026 (America/Los_Angeles). USD. Analysis only.

## Decision-support results

The strongest game-specific inbound estimate is **$0.3839 per game**, using actual carrier and placement charges for the same 20 shipments and allocating each shipment's cost across every unit in it. The all-product equivalent is **$0.5291**. Neither number includes purchase cost, referral fees, outbound fulfillment, returns, or storage.

| Component | Historical estimate | Sample / interpretation |
|---|---|---|
| Carrier / shipped unit | $0.2454 | 23 shipments; 3,238 units; $794.54 posted |
| Placement / shipment unit | $0.2645 | 23 shipments; 3,304 units; $873.89 posted; allocated denominator |
| Combined inbound / unit | $0.5291 | 20 shipments with both charges; 2,802 units; $1,482.50 |
| Combined inbound / identified game | $0.3839 | 2,146 game units in those same 20 shipments; equal unit allocation |
| Ordinary storage / game / month | $0.0153 | 12 months; 7,486.63 average-on-hand unit-months |
| Ordinary storage / game / month, Jan-Sep | $0.0107 | Inventory-weighted actual historical report rows |
| Ordinary storage / game / month, Q4 | $0.0317 | October-December 2025 |
| Aged inventory charges, all products | $347.53 | 12 posted monthly charges; separate from ordinary storage |

The carrier and placement headline averages have different shipment populations. **Do not add those two averages** to derive combined inbound cost. Use the matched 20-shipment cohort. Game allocations are historical estimates, not item-level Amazon invoices or marginal carrier price quotes. A future wholesale case/carton shipment can have a different mix and packing density.

## Coverage and source quality

- Posted-charge period: **September 1, 2025 through August 31, 2026**, twelve complete months. Source is the previously cached `/finances/2024-06-19/transactions` history, merged with stored MBOP transactions and release-deduplicated using the existing return-economics helper. No new finance sweep was needed.
- **26 distinct FBA shipment IDs** are represented by carrier and/or placement charges in that window. All have item quantities. Carrier: 23 shipments / 3,238 units. Placement: 23 shipments / 3,304 shipment units. Matched combined: 20 shipments / 2,802 units. These are charge-window cohorts, not a claim that all physical ship dates fall within the window.
- Storage inventory-month coverage: **2025-09 through 2026-08**, 12 months. Monthly storage is billed the following month. The September 2026 charge is used only to reconcile August inventory storage, outside the posted-charge headline period.
- Storage reports contain **12,413 ASIN/FNSKU/fulfillment-center rows**, including **809 identified game ASINs**. Average inventory quantities summed across months are unit-month exposure, not unique physical units or shipped sales.
- Aged report coverage: 2025-09 through 2026-08. The posted aged total is authoritative for dollars actually charged. Report line attribution is kept separately and reconciled by month.
- MBOP stored 14 shipment headers (including one legacy placeholder), 3,232 shipment item rows, and six recovery-source rows at extraction. The `legacy_listed_no_shipment_id` rows are not counted as an extra shipment or inbound denominator.
- Existing shipment raw tracking contains selected partnered-carrier options and boxes for eight shipments. Existing InventoryLab tables contain acquisition-cost and valuation history, not a dedicated purchased inbound-label expense ledger. No InventoryLab shipping charge was invented from its COGS fields.
- Existing inventory planning stores age buckets, volume and **estimated** future storage/LTSF fields. Current snapshots and purchase dates cannot reconstruct an exact per-unit FBA residence time. Those estimates were not substituted for historical actual charges.

Source inspection included `docs/AI_README.md`, project state/decisions/issues/roadmap, database schema, business rules, backend architecture, shipment requirements, Supabase capacity notes, the Amazon shipment/client/finance/report integrations, and prior return-economics evidence. A tiny database read succeeded before bounded shipment/metadata reads. No broad inventory history scan or production backfill ran.

## Carrier transportation

Actual observed transaction description: `FBAPostInboundTransportation`. Transaction component: `InboundTransportationFee`; item component: `FBAInboundTransportationFee`. `ORDER_ID` carries the FBA shipment confirmation ID. Total posted carrier expense: **$794.54**. The 26 distinct charged shipment IDs collectively represent **3,740 shipped units**, counted once per shipment. Seller-order label adjustments such as `LabmanLabelPurchase` are not treated as FBA inbound charges.

Use transaction totals once; never add transaction, item, fee-parent and Base amounts together. Charges are positive expenses in the audit output; credits retain negative signs. Only released transactions are used. Stored and fresh finance representations are not added together.

For each shipment, carrier cost / Amazon shipped units is calculated. Games receive their share of all shipment units. No shipment's entire mixed-product cost is assigned to its games. All extracted units mapped to a stored ASIN; game classification remains separately qualified below.

| Metric | Carrier | Placement | Combined |
|---|---|---|---|
| Weighted / unit | $0.2454 | $0.2645 | $0.5291 |
| Median shipment / unit | $0.1649 | $0.3077 | $0.4099 |
| 25th percentile | $0.1023 | $0.2572 | $0.3884 |
| 75th percentile | $0.6650 | $0.4275 | $1.0980 |
| Minimum | $0.0638 | $0.1601 | $0.2995 |
| Maximum | $4.6800 | $3.1200 | $7.8000 |

For the eight shipments with reliable stored box counts: **14 boxes / 1,185 units**, carrier cost per box **$16.6793**, and **84.64 units per box**. Box metrics use only that subset. All eight selected transportation quotes exactly match the posted transportation charges. Quote values are preserved in `shipment_costs.csv` for comparison, but the posted charge is the cost authority. UPS is observed in the stored partnered-carrier options; missing historical carrier names remain blank.

Actual carrier pickup dates are retained when available. Finalized/plan creation dates are separately labeled. For older shipments lacking both, only the charge date is supplied; a charge date is not mislabeled as the physical shipping date.

### Weight sensitivity

Monthly storage reports also supply existing product weights. For shipments where every item has a positive reported weight, the analysis uses each ASIN's median observed weight and allocates carrier expense by quantity times weight. This is a sensitivity, not a new dimensional-weight model: box tare, dimensional billing, minimum label charges and within-ASIN package variation are not reconstructed.

Carrier comparison on the **same 22 shipments / 2,295 game units**: equal-unit allocation **$0.1342 / game**, weight allocation **$0.1262 / game**. Weight coverage is not extrapolated to incomplete shipments. The audit also exposes weight sensitivity for combined costs, but placement fees are not assumed to be weight-priced.

## Placement fees and combined inbound

Observed description: `FBAInboundConvenience`. Components include `InboundConvenienceCharge` and `FBAInboundConvenienceFee`. Recent item descriptions explicitly say `FBA Inbound Placement Service Fee`. These actual fees total **$873.89**, across 30 transactions and 23 shipment IDs.

Some transactions split one shipment's fees across multiple records; those costs are summed while its shipped units are counted once. Older item-shaped fee lines still have null SKU/ASIN and zero quantity. Newer records have null quantity too. Consequently, **exact fee-assessed units and measured game-specific placement fees are unavailable**. The reported $0.2645 is total placement expense / all units in the charged shipments, not a claimed Amazon tariff per assessed unit.

Three placement-only shipments (`FBA18Z5C3Y9H`, `FBA18ZSVSP3G`, `FBA18ZT6M8QQ`) lack carrier charges inside the chosen posting window. Three carrier-only shipments (`FBA19JS2S8FS`, `FBA19KM982VB`, `FBA19LMC4ZJF`) lack placement charges in the cached history through September 8. Missing is not zero. Placement can post well after transport; do not interpret the recent three as a free-placement option.

Matched-cohort combined expense: **$1,482.50 / 2,802 units = $0.5291**. Equal-unit allocation attributes **$823.87 to 2,146 games**, or **$0.3839 per game**. Across the whole posting window, carrier plus placement cash expense is $1,668.43; that cash total has no single common shipped-unit denominator because six shipments have only one in-window cost component.

Different shipment-level per-unit costs are observed, including a one-unit shipment at $7.80 combined. Product mix, batch size and packing can matter, but the available fee data does not identify per-SKU placement quantities or accepted placement-option pricing well enough to attribute every difference to an Amazon option. No confirmed zero-fee placement population was established.

### Quantity caveats discovered during reconciliation

| Shipment | MBOP header units | Amazon shipped units |
|---|---|---|
| FBA19F8YW7CV | 277 | 281 |
| FBA19H2820Z4 | 138 | 142 |
| FBA19LMC4ZJF | 141 | 140 |

Amazon's directly retrieved shipment-item quantities are used for these denominators. MBOP headers were not changed. Recovery-source rows and purchase-source rows are not simply added on top of an already complete Amazon shipment. The legacy item API returned repeated final-page content; the existing client's repeated-page guard excluded that repeated content. Raw cached item lists and source quantities are retained for review.

## Ordinary storage

Amazon's storage report is documented as an estimate by ASIN. Here its historical `est-base-msf` rows reconcile closely to actual posted monthly storage charges, making it a defensible allocation of real account expense. **The ASIN allocation is report-derived; posted account charges are measured.** No current public rate card is used.

Formula: sum game `est-base-msf` / sum game `average-quantity-on-hand`, across US/USD rows for the selected inventory months. Fulfillment centers for the same ASIN are summed. The median is computed after grouping to ASIN-month, not across arbitrary FC row fragments. Zero/absent quantities cannot become a valid denominator.

| Inventory month | Report ordinary cost | Posted following month | Game average units | Game cost / unit-month |
|---|---|---|---|---|
| 2025-09 | $18.5195 | $18.5200 | 539.81 | $0.0097 |
| 2025-10 | $59.5511 | $59.5500 | 626.70 | $0.0344 |
| 2025-11 | $69.3878 | $69.3900 | 629.63 | $0.0297 |
| 2025-12 | $61.8005 | $61.8000 | 380.55 | $0.0304 |
| 2026-01 | $18.7793 | $18.7800 | 402.52 | $0.0112 |
| 2026-02 | $18.4100 | $18.4100 | 546.90 | $0.0111 |
| 2026-03 | $20.8194 | $20.8200 | 578.49 | $0.0107 |
| 2026-04 | $18.3598 | $18.3600 | 740.23 | $0.0107 |
| 2026-05 | $15.4797 | $15.4800 | 711.98 | $0.0114 |
| 2026-06 | $16.1296 | $16.1300 | 732.40 | $0.0114 |
| 2026-07 | $13.5408 | $13.5400 | 748.52 | $0.0103 |
| 2026-08 | $16.4306 | $16.4300 | 848.90 | $0.0102 |

All-product report ordinary storage totals **$347.2081**. Observed storage-utilization surcharges total **$0.00** in the report population and are excluded from the ordinary formula. Aged storage is always separate. No exceptional charge is presumed absent merely because it has a different label: cached non-sale transaction types were reviewed, and the audit lists the exact categories included.

Posted storage within September 2025-August 2026 is **$349.16**, including an August correction/reversal pair with a net $0.02 credit. A separate `FBAStorageFeeAdjustment` credits another $0.02, producing **$349.14 net posted storage-related expense**. These posting-period totals cover a different inventory-month range from the report table. Small credits lack reliable ASIN attribution and are not silently spread into game costs.

Game ordinary rate: **$0.0153/month**. ASIN-month median: **$0.0098**. Jan-Sep weighted rate: **$0.0107**, median **$0.0094**. Q4 weighted rate: **$0.0317**, median **$0.0270**. Seasonal comparisons also reflect changing product mix; they are not a controlled estimate of a pure rate change.

## Holding-time scenarios

| Holding days | Historical inventory-weighted estimate | Calendar seasonal minimum | Calendar seasonal maximum |
|---|---|---|---|
| 30 | $0.0151 | $0.0106 | $0.0312 |
| 60 | $0.0302 | $0.0212 | $0.0624 |
| 90 | $0.0453 | $0.0317 | $0.0937 |
| 180 | $0.0906 | $0.0635 | $0.1268 |
| 365 | $0.1837 | $0.1921 | $0.1921 |

Use days times 12/365 to convert monthly rates to approximate daily expense. The historical estimate uses inventory-weighted observed months. Calendar bounds use the observed normal and Q4 rates, with at most 92 Q4 days and 273 normal days per non-leap year. A 180-day period cannot be six Q4 months; a 365-day period includes both seasons. These scenarios exclude aged penalties and assume one unit remains stored for the entire interval. Exact actual storage per game's realized holding period is not supportable from the available per-unit movement linkage.

## Aged inventory and slow-inventory risk

Actually posted aged charges: **$347.53**. Itemized aged report total: **$347.99**. Their difference is **$0.46**; `aged_monthly.csv` preserves the reconciliation. Do not replace the cash total with rounded/itemized report amounts or force that difference onto games.

Identified game report attribution: **$100.60**, **113 ASINs**, **1,451 unit assessments**. A unit charged in multiple months appears in multiple assessments; this is not a distinct-unit count. Age-tier detail is retained, and the same ASIN may move between tiers.

| ASIN | Product | Attributed aged fee | Unit assessments | Age tiers |
|---|---|---|---|---|
| B07KN77NXY | FIFA 19/NHL 19 Bundle PlayStation 4 [video game] | $39.46 | 217 | 181-210, 211-240, 241-270, 271-300, 301-330, 331-365, 366-455, 456+ |
| B000L422L0 | Brooktown High: Senior Year - Sony PSP [video game] | $10.31 | 162 | 181-210, 211-240, 241-270, 271-300, 301-330, 331-365, 366-455 |
| B0748VH8ZF | The Sims 4 - Xbox One [video game] | $6.86 | 69 | 181-210, 211-240, 241-270, 271-300, 301-330, 331-365, 366-455 |
| B01EZA0D8O | Call of Duty: Infinite Warfare - Standard Edition - Xbox One [video game] | $6.45 | 82 | 181-210, 211-240, 241-270, 271-300, 301-330, 331-365, 366-455 |
| B08JHP4Q7Y | Sniper: Ghost Warrior - Contracts 2 - PlayStation 4 [video game] | $6.31 | 55 | 181-210, 211-240, 241-270, 271-300, 301-330, 331-365, 366-455, 456+ |
| B0CGY48TGT | EA SPORTS WRC - Xbox Series X [video game] | $4.17 | 45 | 181-210, 211-240, 241-270, 271-300, 301-330, 331-365, 366-455, 456+ |
| B097PJX3Z9 | Shin Megami Tensei V: Steelbook Launch Edition - Nintendo Switch [video game] | $3.42 | 20 | 301-330, 331-365, 365+, 456+ |
| B0BRNY8987 | The Witcher 3: Wild Hunt Complete Edition - Xbox Series X [video game] | $2.29 | 18 | 181-210, 241-270, 271-300, 331-365, 366-455 |

These penalties are evidence of slow-inventory risk and are not averaged into the ordinary storage allowance. Financial data lacks the product detail needed to assert that every attributed report cent is the final net posted game charge.

## Classification and other limits

- Reuses the return-economics classifier: stored Amazon game-software product types where available, otherwise platform/title evidence with accessory exclusions. One consistent ASIN classification is used across shipments and storage. This is an **identified-game sample**, not a manually audited complete product taxonomy. Titles and `is_game` are available for review.
- Shipment charges are actuals; game shares are allocations. The relationship between product weight and real parcel price is not necessarily linear. Shipment minima and non-game bulky goods explain why an overall average can be higher than the game allocation.
- Some placement charges fall outside the posting window or have not appeared in cached data. The matched cohort reduces, but cannot eliminate, late-adjustment risk. Historical totals are as observed through September 8, 2026.
- No reliable unit-level start/end FBA residence interval was built from today's inventory snapshot, purchase date or aggregate inventory age. No historical COGS audit or recalculation was performed.

## Reproduction and audit files

Run from repository root:

```powershell
.venv/Scripts/python.exe integrations/analyze_amazon_inbound_storage.py --cache logs/diagnostics/inbound-storage-20260909 --previous-cache logs/diagnostics/returns-economics-20260909 --output logs/diagnostics/inbound-storage-20260909/results
.venv/Scripts/python.exe -m unittest discover -s tests -p test_amazon_inbound_storage.py
```

The CLI is offline and does not access credentials, databases or Amazon endpoints. Output source hashes freeze its inputs. The review directory is `docs/analysis/amazon-inbound-storage-2026-09-09/`: summary, source manifest, fee transactions, shipment costs and units, monthly/detail storage, monthly/detail aged fees, game aged concentration, and holding scenarios. Raw payloads and credentials are not included in the review package.

Retrieval reused the existing `AmazonSPAPIClient`, report downloader/parser, and read-only Supabase management query workflow. Two documented, non-PII storage report types were added to the local client allow-list. No report importer, schedule, schema, production UI or parallel Amazon integration was added. Reports were requested one calendar month at a time and cached locally. Initial report creation hit HTTP 429; remaining creation was reduced to one request per 65 seconds, retaining completed work.

Official definitions: [Amazon FBA report types](https://developer-docs.amazon/sp-api/docs/report-type-values-fba), specifically Storage Fees and Long Term Storage Fee Charges. These support report interpretation only; all dollar estimates above come from this account's cached transactions/reports. The aged report requests use one-month intervals as documented.

## Validation and change boundary

Ten analysis/client allow-list tests and 19 existing return-economics tests passed. Checks cover signed credits, duplicate/conflicting transactions, currency isolation, date/status boundaries, weighted denominators, mixed-product allocations, missing versus zero, percentiles and seasonal bounds. Report-month checks, duplicate storage-row detection, posted/report reconciliation, shipment denominator differences and source hashes are also recorded.

No wholesale purchasing feature, sourcing threshold, purchase/receiving behavior, historical COGS, production data/schema, deployment, or scheduler cadence was changed. The only shared-client code edit permits the two read-only report types for the authorized local analysis.
