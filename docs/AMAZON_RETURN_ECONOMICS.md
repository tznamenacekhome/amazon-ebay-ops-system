# Amazon FBA return economics — September 9, 2026

## Finding

For the identified video-game cohort, actual reconciled Amazon transaction costs averaged **$4.73 per returned unit**, with a **$4.65 median**. This is before inventory impairment and reimbursement offsets. The observed physical-return rate was **4.41%**.

A definitive all-in cost per returned game or per unit sold is **not yet supportable**. Historical recovery proceeds are missing, some returned units lack cost basis, and some refunds have no physical-return match. These gaps matter particularly for opened new games. Do not use the measured transaction-fee average as the full economic loss.

This work made no production data/schema changes, accounting recalculations, sourcing-threshold changes, UI changes, or scheduler/deployment changes.

## Coverage and population

- Sales cohort: **September 1, 2025–August 31, 2026**, using stored UTC purchase dates.
- Physical returns observed: report requested September 1, 2025–September 9, 2026 exclusive. Last returned row is September 1, 2026. Reporting lag and future returns remain possible.
- Full report: **191 distinct returned units**. **190** have return dates within the twelve calendar months. The sales-cohort metrics include **180**: nine relate to sales before September 2025, and two relate to replacement orders excluded from paid-sale denominators.
- Denominator: shipped US FBA item quantities, excluding cancelled, pending, replacement, merchant-fulfilled, and non-US sales. Count each Amazon order-item ID once. **3,052 units** across **2,970 item lines**.
- Independent database check: shipped order-header quantity sums to **3,052**. The 34 shipped headers without items all have `sales_channel=Non-Amazon` and S01 identifiers; they are not counted as marketplace sales. One BRL sale item is also excluded.
- Recent sales are less mature: August 2026 purchases have at most about five weeks of return observation. The observed rate is not a lifetime return rate.
- The report measures physical returns received at Amazon. An additional **26 paid-sale lines / 28 posted refund transactions** have no matching physical-return report row. They are exported separately, not fabricated into returned-unit counts or assumed inventory losses.

### Game and condition classification

Amazon catalog identity product types are used where present. Otherwise the existing MBOP platform detector identifies game titles, excluding obvious controllers, consoles, cables, headsets, and other accessories. An ASIN receives one shared classification for both sold and returned quantities, using available sale/report titles. The CSV records the classification source and system. This is a disclosed classification heuristic, not a complete official Amazon category census.

Original condition is absent from many FBA order-item rows. All 191 return SKUs currently show Amazon New codes (`11`: 185; `NewItem`: 6). This supports the new-condition context, but current SKU condition does not independently prove the historical condition of every sale. Results should be described as the identified video-game business subset, predominantly indicated New, rather than an independently verified historical New-only cohort.

## Results

| Metric | All US FBA | Identified video games |
|---|---:|---:|
| Units sold | 3,052 | 2,244 |
| Observed returned units belonging to sales cohort | 180 | 99 |
| Unit return rate | 5.90% | 4.41% |
| Units with reconciled posted transaction costs | 163 / 180 | 94 / 99 |
| Units with known inventory basis | 126 / 180 | 61 / 99 |
| Gross fees, reconciled subset | $2,094.22 | $1,228.79 |
| Fee credits, reconciled subset | $1,147.99 | $783.80 |
| Net transaction fees, reconciled subset | $946.23 | $444.99 |
| Linked reimbursement offsets | $40.20 | $40.20 |
| Confirmed inventory impairment | $5.99 | $0.00 documented |
| Known economic components, incomplete coverage | $912.02 | $404.79 |
| Mean transaction cost per reconciled return | $5.81 | $4.73 |
| Median transaction cost per reconciled return | $5.21 | $4.65 |
| Mean known loss per fee-reconciled return, excluding unknown impairment | $5.56 | $4.31 |
| Known economic components per unit sold | $0.299 | $0.180 |
| Additional known basis at risk where impairment/recovery is unknown | $632.90 | $312.24 |
| Zero-recovery scenario on known components and basis only | $1,544.92 | $717.03 |
| Same incomplete zero-recovery scenario per unit sold | $0.506 | $0.320 |
| Unsellable/unknown-impairment units without basis | 19 | 14 |

**The zero-recovery scenario is not a maximum for the whole business.** Missing basis and unresolved fees cannot be assigned zero and still produce a valid maximum. Likewise, the known-component figure is a measured subtotal, not a guaranteed lower bound after all future credits/reimbursements. No best estimate or complete maximum is supplied because doing so would require invented values.

Confirmed impairment is one disposed/donated unit with a $5.99 basis. Its refund is unresolved, so its inventory loss appears in known components separately from the fee-reconciled subset. Average confirmed impairment is $5.99 for that one applicable unit; there is no corresponding measured game impairment average. A documented $0 game impairment does **not** mean game inventory suffered no loss.

### What Amazon actually charged and credited

| Reconciled fee component | All US FBA | Video games |
|---|---:|---:|
| Original FBA fulfillment fees retained | $741.74 | $325.50 |
| Original referral fees | $961.71 | $597.52 |
| Referral-fee credits | $961.71 | $597.52 |
| FBA fulfillment-fee credits observed | $0.00 | $0.00 |
| Refund administration fees | $192.32 | $119.49 |
| Return-processing fees in reconciled subset | $12.17 | $0.00 |

For these reconciled returns, net transaction costs are the retained fulfillment fees plus refund administration and applicable processing fees. This conclusion comes from actual signed fee records, not a hardcoded fee-refund policy. Gross-fee/credit totals additionally include closing and other fee components that cancel. Raw fee names and signed values are in `fee_events.csv`.

Some disposal/return service charges exist on unresolved records. They remain visible in the fee audit but are not silently allocated into the reconciled averages. Zero in the reconciled removal-fee total is not proof that removals were free.

## Inventory outcomes

Amazon's original dispositions are preserved independently of economic interpretation.

| Raw disposition | All US FBA | Video games |
|---|---:|---:|
| SELLABLE | 97 / 180 (53.89%) | 65 / 99 (65.66%) |
| CUSTOMER_DAMAGED | 80 / 180 (44.44%) | 33 / 99 (33.33%) |
| DEFECTIVE | 3 / 180 (1.67%) | 1 / 99 (1.01%) |
| Unknown raw disposition | 0 | 0 |

Raw unsellable share is **46.11% overall**, **34.34% for games**. It does not establish ultimate loss.

After existing inspection evidence, the cohort has 108 units with sellable/no-impairment evidence, 70 with unresolved recovery, one disposed/donated unit, and one separately reimbursed outcome. Games have 67 sellable/no-impairment outcomes, 31 unresolved recoveries, and one reimbursement outcome. The reimbursed row's raw SELLABLE status remains visible, and its inventory basis is not written off. Twelve overall / three game returns have explicit operator inspection evidence `condition=New`, overriding a raw damaged label for economic classification.

No actual downstream eBay resale proceeds were reliably linked. Existing case decisions such as `sell_on_ebay` are intentions, not realized recovery dollars.

## Segmentation

`segments.csv` contains ASIN/title, system, purchase month, return reason, disposition, sale-price band, and cost-band summaries, including sample counts. Reason/disposition groups have no invented sales denominator. Unknown costs remain an explicit band. Use counts when interpreting rates.

Examples with at least 20 units sold and three observed returns:

| ASIN / product | Sold | Returned | Rate |
|---|---:|---:|---:|
| B01N03NM02 — Harmony 1-cup bowl | 104 | 23 | 22.12% |
| B00KLMOY4K — Plants vs. Zombies Garden Warfare, PS4 | 33 | 7 | 21.21% |
| B01N54QSH6 — Harmony 3-cup bowl | 93 | 18 | 19.35% |
| B01N1GRUUC — Harmony 6-cup bowl | 93 | 12 | 12.90% |
| B07HFMJ4R5 — Minecraft Starter Collection, Xbox One | 48 | 4 | 8.33% |

Plants vs. Zombies warrants product-specific review, but seven returns are still a modest sample. It should not establish a wholesale-wide assumption. The overall return rate is materially affected by non-game products.

## Sources, retrieval, and reconciliation

Existing architecture reviewed: `docs/AI_README.md`, relevant `CURRENT_STATE.md` sections, `docs/database_schema.md`, `docs/backend_architecture.md`, `docs/supabase_capacity.md`, Amazon return-recovery importer/client, sales-finance importer, sales profitability, and existing COGS consumption/InventoryLab sources.

Existing stored coverage before retrieval:

| Source | Stored rows | Earliest–latest |
|---|---:|---|
| Customer-return report rows | 448 | Apr 2–Sep 1, 2026 |
| Reimbursement rows | 216 | Apr 4–Sep 3, 2026 |
| Removal order rows | 34 | May 29–Aug 23, 2026 |
| Removal shipment rows | 31 | Jun 2–Aug 27, 2026 |
| Amazon order headers | 8,000 | Jul 1, 2024–Sep 9, 2026 |
| Financial event rows | 31,495 | Jan 2, 2025–Sep 9, 2026 |
| Finance transaction rows | 5,447 | Feb 6, 2025–Sep 9, 2026 |
| Sales profitability rows | 5,570 | Current calculated snapshot |
| Return-recovery cases | 21 | May–Aug 2026 returns |

Additional Amazon reports, all requested September 1, 2025–September 9, 2026 exclusive:

| Report type | Report ID | Rows |
|---|---|---:|
| GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA | 1123557020705 | 191 |
| GET_FBA_REIMBURSEMENTS_DATA | 1123558020705 | 75 |
| GET_FBA_FULFILLMENT_REMOVAL_ORDER_DETAIL_DATA | 1123559020705 | 82 |
| GET_FBA_FULFILLMENT_REMOVAL_SHIPMENT_DETAIL_DATA | 1123560020705 | 85 |

The existing `AmazonSPAPIClient`, report document downloader, and flat-file parser were reused. Reports were cached locally, not imported into production. All four completed successfully, despite older documentation noting removal-report failures.

Finance retrieval used `/finances/2024-06-19/transactions` in three bounded windows, Sep–Jan, Feb–Jun, and Jul–Sep 8, respecting Amazon's 180-day window constraint and pacing pagination. It retrieved **5,078 transaction records in 12 pages**, followed by **14 targeted order checks returning 20 records** for unresolved refunds. These overlap existing data and are deduplicated. No accounting writes or per-order scan of the entire sales history occurred.

Important reconciliation rules:

1. The 448 stored return rows represent only **90 distinct order/SKU/LPN keys** because imports overlap. The single historical report supplies the primary physical-return population; different LPNs from the same order are retained.
2. A transaction ID alone is not enough: Amazon emits separate deferred/released IDs. Follow `RELEASE_TRANSACTION_ID` and `DEFERRED_TRANSACTION_ID`, keeping the released representation once. Fresh status supersedes cached status. Unreleased DEFERRED transactions are excluded.
3. Read fee components at one hierarchy level. Do not sum parent totals plus child/Base values. Legacy normalized events are supporting checks, not added to the newer representation of the same transaction.
4. Match finance items by exact Amazon order and SKU. The audit quarantines partial-quantity lines rather than inventing original-fee allocations. Two small principal differences ($0.30 and $0.08) are also kept out of the headline reconciled averages.
5. Customer refunds are revenue reversals. They are shown for reconciliation but never added as a cost alongside lost inventory or expected profit.
6. Use stored order-item COGS divided by its recorded quantity; preserve FIFO/InventoryLab provenance. Existing SKU-based InventoryLab sources were checked for gaps. Do not use today's replacement price or recalculate historical FIFO.
7. Reimbursement offsets come from the reimbursement report once. Do not also subtract corresponding finance reimbursement transactions. The report totals **$939.04** across all 75 rows; **52 rows lack an order ID**. Only **$40.20** directly joins this physical-return cohort. Warehouse/inbound losses, reversals, and unrelated customer issues are not spread across returns.
8. All 82 removal order records are Return-type orders. They and the 85 shipment rows contain SKU/FNSKU/removal-order evidence but no reliable customer-return LPN linkage. A shared SKU is insufficient to allocate a removal fee, conclude disposal, or infer recovered value. Existing inspected cases are used only when directly linked by LPN.

Final fee reconciliation covers 172 of 191 report units, including 163 of the 180-unit paid-sale cohort. The remaining cohort records require refund, quantity, or principal reconciliation. The two excluded replacement returns also have no posted refund and are not treated as paid-sale losses.

## Recommendation

Use **$4.73 per returned game** as the observed transaction-cost component for this sample, with the measured **4.41%** physical-return frequency and explicit recognition of sampling and maturity limits. Their simple product is approximately **$0.209 per unit sold before reimbursement and impairment**, an illustrative frequency/severity calculation rather than a fully reconciled all-in allowance.

The directly measured known game-cost subtotal is **$0.180 per unit sold** after the one linked reimbursement. Assigning zero recovery to the known at-risk basis increases the incomplete scenario to **$0.320 per unit sold**. Neither covers the 14 unsellable game units missing basis or the refund-only population. Do not select a lower purchasing ROI on the assumption that $0.18 or $0.32 is the true total cost.

The most useful next evidence is realized recovery proceeds and historical basis for the unresolved unsellable game units, plus resolution of refund-only orders. No new cross-platform matching system or wholesale feature was built.

## Reproduction and deliverables

Run from the repository root against the frozen local cache:

```powershell
.\.venv\Scripts\python.exe integrations/analyze_amazon_return_economics.py --cache logs/diagnostics/returns-economics-20260909 --output logs/diagnostics/returns-economics-20260909/results
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_amazon_return_economics.py
```

The analysis CLI has no database client or write operation. It uses the existing Amazon identifier parser and platform detector, reads cached JSON, and writes local reports. Raw source caches stay under ignored `logs/diagnostics/`; no secrets are embedded in code or reports. At the operator's request, the six generated review outputs are committed under [analysis/amazon-returns-2026-09-09](analysis/amazon-returns-2026-09-09/README.md). These outputs support review without local cache access; rerunning the analysis still requires the local source cache.

Outputs:

- `results/summary.json`: exact numeric totals and missing-data counts.
- `results/return_detail.csv`: 191 physical-return records, original disposition/reason, matched costs, fee components, reimbursements, outcome, scenario amounts, and cohort/reconciliation flags. Line-level revenue/refund fields repeat on multiple returns from one sale line and must not be summed blindly.
- `results/fee_events.csv`: signed fee components and transaction identifiers for audit, including unresolved lines.
- `results/sales_denominator.csv`: eligible paid US FBA item quantities and game classification.
- `results/segments.csv`: grouped counts/rates/costs.
- `results/refunds_without_physical_return.csv`: unresolved refund-only evidence.
- Source cache: report manifests, existing sales/finance/cost extracts, report rows, and fresh finance responses.

Validation: ten focused unit tests cover deferred/release deduplication, fresh status precedence, fee hierarchy, revenue reversal treatment, sellable basis preservation, recovery scenarios, missing maximums, and accessory exclusion. The analysis was run against the actual cache; its US unit denominator reconciles independently to order headers. No Next.js build is needed because web code was untouched.

Customer comments are omitted. Automatic approval review rejected retaining that field under the project's customer-data restriction; it was not required for the monetary calculations. No attempt was made to bypass that rejection.

Official source semantics: [Amazon FBA report definitions](https://developer-docs.amazon.com/sp-api/docs/report-type-values-fba) document physical returns, reimbursements, and removals. [Amazon listTransactions](https://developer-docs.amazon.com/sp-api/lang-en_US/reference/listtransactions) documents status, pagination, date windows, and potential recent-data lag. Actual account records, rather than published fee schedules, supply all monetary amounts above.
