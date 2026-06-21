# Keepa Active Listing Refresh Plan

## Current Implementation

`integrations/keepa_sync_products.py` uses `KeepaClient.get_products()` with these parameters for the scheduled active-products job:

```text
domain=1
asin=<comma-separated batch>
stats=90
history=0
rating=1
wait=1
offers=20
stock=1
```

The scheduled command is:

```text
integrations/keepa_sync_products.py --source amazon_active --limit 10 --batch-size 10 --stale-days 7 --min-tokens 100 --offers 20 --stock --no-history --write
```

Source selection for `amazon_active` reads `vw_latest_amazon_fba_inventory_snapshot` and includes ASINs with positive current quantity, then filters to ASINs with no Keepa snapshot or a latest snapshot older than `--stale-days`, ordered oldest first. It writes `keepa_product_snapshots`; `keepa_product_history_points` are written only when `--write-history` is passed and history is requested.

## Observed Token Behavior

- Active-products run on 2026-06-20: 10 ASINs, tokens before 300, tokens after 202. Observed cost: 98 tokens total, about 9.8 tokens/ASIN.
- FBA prep pricing run on 2026-06-20: first 20-ASIN batch, tokens before 207, tokens after -21. Observed cost: 228 tokens total, about 11.4 tokens/ASIN; the next 20-ASIN batch immediately hit HTTP 429.
- Keepa refill observed in logs: 5 tokens/minute with 300 max tokens.
- The current code stores `payload.tokenFlowReduction` into each snapshot row as `token_cost`. That value appears to be response/batch-level, so it should not be treated as exact per-ASIN cost until the code normalizes it, for example `tokenFlowReduction / returned_products` plus run-level token-before/token-after.

## Parameter Effects

- `stats=90` is what gives current/avg30/avg90/avg180 arrays and sales-rank drop counters in `product.stats`. The current implementation reads current Buy Box, 90-day Buy Box, current new/FBA/new/used prices, sales rank averages, and `salesRankDrops30/90/180` from this stats payload.
- `--no-history` sets `history=0`. This avoids returning full `csv` history arrays and prevents history point parsing/writes. It reduces payload size and Supabase write volume. It does not remove the `stats=90` summary fields that MBOP currently stores.
- `--offers 20` requests live offer data. Combined with `--stock`, it materially increases observed token use. The 9.8-11.4 tokens/ASIN observed cost is far above a simple product/stats-only call and should be assumed to be driven mainly by offers/stock/rating extras.
- `--stock` requests stock detail for offers and is explicitly documented in the script help as potentially costing extra tokens.
- Sales frequency/rank drops do not require writing history rows in the current implementation; they are taken from `stats.salesRankDrops30`, `stats.salesRankDrops90`, and `stats.salesRankDrops180`. Full history is only needed if MBOP wants its own time-series analysis beyond Keepa's stats window.

## Full Refresh Math

Using ~1,028 active Amazon listing ASINs and the observed active config cost of 9.8 tokens/ASIN:

- Tokens for one full refresh: about 10,074.
- Refill capacity: 7,200 tokens/day, but only 300 can be held at once.
- Minimum refill time for one full refresh: about 33.6 hours of continuous refill.
- Because max balance is 300 tokens, the refresh must be spread across small runs. Starting at 300 tokens helps only for the first run.

## Rolling Cadence Feasibility

| Target cadence | ASINs/day | Tokens/day at 9.8/ASIN | Feasible on 7,200 tokens/day refill? | Practical note |
| --- | ---: | ---: | --- | --- |
| Every 3 days | 343 | 3,358 | Yes by refill math | Requires about 34-35 ASINs/day. With batch 10, run 4 times/day. |
| Every 5 days | 206 | 2,015 | Yes | Requires about 21 ASINs/day. With batch 10, run 3 times/day or 2 runs plus occasional catch-up. |
| Every 7 days | 147 | 1,439 | Yes | Requires about 15 ASINs/day. With batch 10, run 2 times/day. |

The limiting factor is not daily refill; it is burst size and overlapping jobs. A 20-ASIN offers+stock batch can consume more than 200 tokens and push the account below zero/429. Keep batch size at 10 or lower unless the code checks tokens between batches.

## Recommended Strategy

### Active Amazon Listings

- Keep `--no-history` for routine refreshes.
- For buy-opportunity detection, split into two Keepa modes:
  - Light daily rolling mode: `stats=90`, `rating=1`, `history=0`, no `offers`, no `stock`, batch 20-50 after measuring token cost.
  - Deep offer/stock mode: `--offers 20 --stock`, batch 5-10, used only for candidate ASINs needing offer-depth/stock intelligence.
- If keeping the current deep config for all active listings, use `--batch-size 10`, `--limit 10`, `--min-tokens 150`, and run:
  - every 6 hours for a 3-day target,
  - every 8 hours for a 5-day target,
  - every 12 hours for a 7-day target.
- Never run active-products and FBA-prep Keepa jobs at the same time.
- Add per-batch token checks before every product request. The current script checks `--min-tokens` only once before all batches.

### FBA Prep Pricing

- Change scheduled command to include a small limit, for example `--limit 5` or `--limit 10`, and `--min-tokens 150`.
- Prefer on-demand/manual during shipment prep. Product Fees estimates should run after Keepa FBA prep pricing.
- Current command without a limit selected 40 ASINs and hit 429. It is not safe as an unattended cloud scheduled task on the observed token plan.

## Fields To Store

For ongoing buy-opportunity detection, store or expose these fields from each refresh:

- ASIN
- current Buy Box price
- 90-day average Buy Box price
- current new price
- 90-day average new price
- current/new FBA price when available
- current sales rank
- 90-day average sales rank
- sales rank drops over 30/90/180 days or normalized sales frequency
- refresh timestamp
- token cost, normalized per ASIN and run-level total
- tokens before and after run/batch
- source, e.g. `amazon_active`, `received_fba_prep`, `purchase_pre_listed`, `explicit`
- request mode, e.g. `stats_only` vs `offers_stock`

Current schema already stores many of these in `keepa_product_snapshots`: current/avg Buy Box, current prices, sales rank stats, drops, rating/review/offer count, raw payload, tokens_left, token_cost, source. The recommended improvement is to make token accounting explicit and distinguish source/mode more precisely.