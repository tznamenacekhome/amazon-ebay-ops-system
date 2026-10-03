# Wholesale Purchasing Phase 3: Opportunity Evaluation

Status: deployed to production on October 3, 2026. Phase 1 through Phase 3 migrations and the bounded first evaluation run are verified.

## Architecture

Phase 3 consumes the selected compatible, freshly eligible Phase 2 ASIN. The bounded Python evaluator reads cached supplier observations, Keepa snapshots, Product Fees estimates, Amazon FBA inventory, and active draft commitments. It writes immutable `wholesale_evaluations` and updates one current `wholesale_opportunities` row per supplier product and marketplace. Decisions are append-only. Draft commitments remain separate from purchases and inventory.

The Next.js wholesale APIs read these server-owned results. React displays them and submits protected actions; it does not query Supabase or calculate profitability.

## True ROI and dual-price qualification

Both price bases are evaluated independently:

- current price: the selected ASIN's current New Buy Box from the latest shared Keepa snapshot; a Buy Box explicitly marked Used is rejected
- historical price: Keepa's existing 90-day Buy Box average

For each available price and exact cached Product Fees estimate:

```text
True profit = selling price
            - supplier unit cost
            - total Amazon fee estimate
            - inbound allowance
            - expected return-transaction allowance
            - ordinary 30-day storage allowance

True ROI = True profit / supplier unit cost
```

Supplier cost is the denominator. Qualification is `current_only`, `avg90_only`, `both`, or `neither`. Either ROI at or above 25% is sufficient. If one basis is unavailable, the other can still qualify independently. Missing prices or fees remain explicit and are never replaced by another price period.

The 25% selling-price floor separates the price-dependent referral rate from fixed fees:

```text
floor = (1.25 × supplier cost + fixed fees + allowances) / (1 - referral rate)
```

Current-price headroom is `(current Buy Box - current floor) / current Buy Box`. Headroom is informational only.

## Cost assumptions

Policy version `video-games-2026-10-v1` applies these historical per-game estimates:

- inbound carrier plus placement allocation: `$0.3839`
- expected Amazon return-transaction allowance: `$0.21`
- ordinary storage for a 30-day horizon: `$0.0153`

Accessories are marked `accessory_review_required`; game assumptions are not silently applied and their evaluations remain incomplete until an accessory policy is approved.

Product Fees are reused from `amazon_fee_estimates`. `amazon_sync_fee_estimates.py --source wholesale_selected` plans or fetches the two exact selected-ASIN price points in bounded mode. No fee calls occur during page rendering.

## Inventory and capacity

The existing Keepa `sales_rank_drops90` metric remains the market-velocity source. Expected monthly sales and the 30-day target equal `sales_rank_drops90 / 3`. Unknown velocity produces unknown guidance.

Capacity is:

```text
max(30-day target
    - current FBA fulfillable units
    - Amazon inbound working/shipped/receiving units
    - active wholesale draft commitments,
    0)
```

The evaluator uses one latest Amazon inventory snapshot cohort per ASIN and marketplace and does not add overlapping local shipment aggregates. Capacity is guidance. Operators can order above or below it. Exact supplier availability is enforced; `144+` remains a lower bound and is not treated as an upper limit.

## Supplier history and informational risk

Supplier history uses non-superseded Phase 1 observations. Previous price is the preceding dated observation. A 30-day or 90-day baseline is shown only when an observation exists at or before that boundary. The UI also shows historical low.

Current-versus-Keepa 30/90-day changes, generic relevant offer count, supported Keepa FBA offer count, and supplier/Amazon divergence are stored separately in `risk_signals_json`. Generic offers are never labeled FBA sellers. Keepa `offerCountFBA` is labeled as potentially incomplete live-offer evidence. Risk fields never enter ROI, qualification, price floor, or capacity.

## Lifecycle and decisions

One `wholesale_opportunities` row is reused across reevaluations. Immutable evaluations preserve the exact supplier observation, ASIN, prices, fees, assumptions, inventory, output, and evidence timestamps.

States are ready for review, temporarily passed, hard passed, added to order, pending matching, pending eligibility, not financially qualified, inactive, and evaluation incomplete.

Temporary reasons are low profitability, price risk, too much inventory, competition, and other. The same opportunity resurfaces when its evaluation fingerprint changes; an audit event records the transition. Hard reasons are listing/ASIN issue and confirmed restricted/cannot sell. Hard passes persist across new evaluations until explicit reversal. A restricted hard pass is rejected unless Phase 2 has confirmed `restricted_no_eligible`; unknown or stale eligibility cannot create that hard pass.

## Add to Order

Add to Order creates or updates one active `wholesale_order_candidates` draft line per supplier product and marketplace. The server requires a positive integer, current actionable evaluation, selected eligible ASIN, and exact-availability compliance. Each request has a durable idempotency record. The snapshot stores quantity, supplier unit price, extended cost, observation, ASIN, evaluation, actor, and revision.

Draft lines count as soft commitments in capacity. They are not supplier orders, purchases, owned inventory, receiving records, COGS, invoices, payments, or accounting entries. Releasing a draft is audited and removes its capacity commitment. A future order workflow must consume the stable draft ID atomically so commitment and confirmed order quantities are never double counted.

## UI and API

`/wholesale` provides Ready for Review, Temporary Passes, Added to Order, Pending Match / Eligibility, Not Qualified, and Hard Passes queues. The dense table displays supplier and Amazon identity, both ROI cases, itemized assumptions, price floor/headroom, inventory exposure, supplier history, and informational risk evidence.

APIs:

- `GET /api/wholesale/opportunities`
- `GET /api/wholesale/opportunities/{id}`
- `POST /api/wholesale/opportunities/{id}/actions`
- the existing Phase 2 matching endpoint for candidate review and manual selection

Supplier observations, ASIN changes, and draft changes mark evaluation requested without rerunning Catalog discovery. Cached Amazon/Keepa/fee refreshes are consumed on the next bounded evaluation pass; no polling was added.

Local bounded sequence after migrations and Phase 2 matching:

```powershell
.\.venv\Scripts\python.exe integrations\amazon_sync_fee_estimates.py --source wholesale_selected --limit 50 --plan-only
.\.venv\Scripts\python.exe integrations\amazon_sync_fee_estimates.py --source wholesale_selected --limit 50
.\.venv\Scripts\python.exe integrations\wholesale_evaluate_opportunities.py --supplier-id <SUPPLIER_UUID> --limit 50
```
