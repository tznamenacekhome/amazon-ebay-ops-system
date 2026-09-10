# Amazon inbound and storage review package

Read [the analysis](../../AMAZON_INBOUND_STORAGE_ECONOMICS.md) first. USD. Posted-charge period September 2025-August 2026; storage inventory months cover the same twelve months, with following-month billing reconciliation.

| File | Purpose |
|---|---|
| `summary.json` | Headline rates, populations, storage seasons, aged totals |
| `fee_transactions.csv` | Signed actual charges, exact observed descriptions, transaction and FBA shipment IDs |
| `shipment_costs.csv` | One row per shipment, quantities, cost components, missing components, header discrepancies and allocation inputs |
| `shipment_units.csv` | Shipment SKU/ASIN quantities, title and game classification |
| `storage_monthly.csv` | Report-to-posted reconciliation and average inventory denominators |
| `storage_detail.csv` | ASIN/FNSKU/FC allocation, ordinary base cost, separate utilization surcharge and observed weight/volume |
| `holding_scenarios.csv` | Approximate 30/60/90/180/365-day storage, including seasonal bounds |
| `aged_monthly.csv` | Actual posted aged charges versus itemized report amounts |
| `aged_detail.csv` | ASIN/SKU/age-tier unit assessments and report charges |
| `aged_game_concentration.csv` | Game ASIN and age-tier concentrations; assessments can repeat the same unit across months |
| `source_manifest.json` | Input filenames, sizes and SHA-256 hashes for the frozen local evidence |

Blank fees are unknown, not zero. Placement fees divided by shipment units are allocations; Amazon's transaction quantity fields do not identify the assessed units. Carrier, placement and combined headline populations differ, so their separately weighted averages must not be added. Use the matched combined cohort.

The offline CLI is `integrations/analyze_amazon_inbound_storage.py`. Its invocation and caveats are in the analysis document. Raw local caches, credentials, customer data and shipping addresses are not part of this package.

Validation: 10 analysis/client tests and 19 return-economics regression tests passed. Independent audit checks reconciled 26 shipments / 3,740 units, the 20-shipment combined cohort / 2,802 units, every included inbound dollar, eight selected carrier quotes, and all twelve monthly storage reports within one cent of posted charges.
