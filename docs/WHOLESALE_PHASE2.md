# Wholesale Purchasing Phase 2: Amazon Matching and Enrichment

Status: implemented locally; the Phase 1 and Phase 2 migrations have not been applied to production.

## Pipeline

Each active supplier product is searched through the existing Amazon Catalog Items client in two independent branches:

1. The exact Phase 1 normalized UPC/EAN is searched when Amazon can accept its type and length. No digit is added, repaired, or removed.
2. The exact supplier title is searched with the canonical platform represented by the supplier `SYS` code.

An empty or failed branch does not suppress the other branch. Results are merged by ASIN while retaining `identifier` and `title_platform` discovery sources. Search keys contain the query type, normalized query text, and marketplace; supplier price is deliberately absent.

Catalog identity is read from or written to the shared `amazon_catalog_item_identity_snapshots` cache. Compatibility then compares title, platform, physical/digital form, edition, bundle, region/language evidence, and accessory/game type. A clear conflict is `incompatible`; incomplete or ambiguous evidence is `uncertain`; only sufficiently consistent evidence is `compatible`. The stored reason codes and details are intended for the Phase 3 review UI.

## Ranking and eligibility

Only compatible candidates enter selection. Existing `amazon_sales_order_items` data provides the prior-account-sale preference. The shared Keepa snapshot cache provides `sales_rank_drops90`; it is stored with the snapshot timestamp, and missing velocity remains unknown. Known velocity ranks ahead of unknown velocity.

Listings Restrictions is checked for `new_new`. Evidence is keyed by seller, marketplace, ASIN, and condition. Eligible and restricted results are cached for seven days; unknown and error results are retried after six hours. A restricted candidate is skipped. Unknown, stale, or error evidence leaves the product in `eligibility_pending`. `restricted_no_eligible` is used only when all compatible candidates have fresh restricted evidence.

The selection order is:

1. fresh, eligible, compatible candidates previously sold by this Amazon account;
2. highest Keepa `sales_rank_drops90` within that group;
3. if none were previously sold, highest known Keepa velocity among all fresh eligible compatible candidates;
4. deterministic ASIN tie-break.

## Manual selection and identity changes

`wholesale_set_manual_candidate` accepts only a compatible candidate with fresh eligible evidence. A manual choice remains selected across imports and ranking changes. It is invalidated when the candidate disappears from discovery, becomes incompatible, loses fresh eligibility, or the operator clears it. Clearing requests a rematch.

Matching uses the latest observation's raw title/system/identifier while ignoring price and availability. A changed platform, edition, bundle, accessory type, digital marker, region, or normalized title changes the identity signature. If a previously matched supplier product has a different signature, the prior selection is cleared and the state becomes `identity_review`; the Phase 1 product identity is not rewritten.

## Cache and resumability

- successful Catalog searches: 30 days
- empty Catalog searches: 7 days
- failed Catalog searches: 1 hour
- exact-ASIN catalog snapshots: 30 days
- eligibility eligible/restricted evidence: 7 days
- eligibility unknown/error evidence: 6 hours

`wholesale_enrichment_runs` and `wholesale_enrichment_work_items` persist bounded work. The worker accepts explicit product IDs or resumes up to `--limit` pending/retry items from a run. Each item finishes or returns to retry independently. Amazon client retry/backoff remains authoritative. Keepa calls are not made from page loads; Phase 2 reuses the existing shared cache, leaving absent values unknown for the existing token-aware Keepa sync to fill in batches.

Example local worker command after both migrations are applied:

```powershell
.\.venv\Scripts\python.exe integrations\wholesale_enrichment.py --product-id <UUID> --limit 1
```

## Backend access

`GET /api/wholesale/products/{productId}/matching?marketplaceId=...` returns the supplier product, match state, and all candidates. Authenticated mutation actions on the same route are `select_candidate`, `clear_candidate`, and `request_rematch`. The API uses the server service-role client; frontend code never accesses Supabase directly.

Phase 3 can consume the selected ASIN and full candidate evidence. Phase 2 does not calculate profitability, ROI, fees, opportunity decisions, inventory exposure, risk signals, order quantities, or supplier orders.
