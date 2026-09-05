# ASIN Correction, Sourcing Purchase Matching, and Keepa Cycle Update - 2026-09-05

## Summary

This change set closes three operational gaps:

- Sourced purchases now remain matchable for auction and bid-sniper workflows for
  10 days instead of 72 hours.
- ASIN corrections can be made in Purchases, Sourcing, Receiving, and Send to
  Amazon/FBA Prep. When an ASIN is changed, MBOP resolves Amazon title and sell
  price from existing catalog/intelligence data.
- Matching-intelligence restore is more tolerant of transient Supabase failures
  and replaces rows by source key instead of clearing entire source-table
  histories before insert.

## Sourcing Purchase Matching

`integrations/match_sourcing_purchases.py` now:

- scans up to 5,000 sourcing rows by default
- includes both `purchased_pending_match` and recent `watching` rows
- requires a real operator `purchased` action before matching a row to an eBay
  purchase
- keeps watchlist rows matchable until the 10-day purchased/offer/bid window
  expires
- prevents multiple sourcing opportunities from matching the same purchase item
- retries transient Supabase/PostgREST failures through shared retry handling

`run_all_syncs.py` now invokes sourcing purchase matching with `--limit 5000`.

Business rule documentation was updated so Purchased Pending Match represents
operator purchases, Best Offers, and auction bids. If no imported eBay purchase
appears within 10 days, MBOP moves the row back to Watchlist.

## Matching Intelligence Restore

`integrations/build_matching_intelligence_examples.py` now:

- deduplicates generated examples by source table, source id, and source detail
- deletes/replaces only the source keys being rebuilt
- chunks replacement batches so duplicate source keys stay together
- tolerates transient Supabase schema-cache, timeout, connection, and Cloudflare
  failures with retries
- skips stale backfill snapshot cleanup after retry exhaustion instead of
  failing the entire restore

Shared retry logic was added to `integrations/sourcing_common.py`, and
`integrations/run_daily_catalog_sourcing.py` recognizes the same transient
Supabase/PostgREST failure shapes.

## ASIN Correction and Metadata Autofill

`web/app/api/_asinMetadata.ts` centralizes ASIN metadata resolution for API
routes. It normalizes ASINs and resolves:

- Amazon title from manual match memory, Keepa catalog snapshots, or Amazon SKU
  listings
- target sell price from manual match memory, recent Amazon sales profitability,
  Keepa 90-day/current prices, or Amazon SKU listing price

Purchases:

- the purchase detail drawer can still edit ASIN, Amazon title, and sell price
- when the ASIN changes and the operator did not explicitly change title/price,
  `/api/purchases` fills them from the shared metadata resolver

Sourcing:

- opportunity rows now include an inline ASIN correction field
- saving a corrected ASIN records `sourcing_actions.action_type =
  asin_updated`
- the opportunity stays visible and reloads with corrected ASIN title/image/price
  context
- corrected opportunities prefer Keepa metadata for the new ASIN instead of the
  original seed title/image

Receiving:

- the receiving drawer still requires an ASIN for Amazon-bound received units
- a blank sell price is allowed at save time so the server can resolve it
- the server writes the resolved Amazon title and sell price to the received item
  and any split rows it creates

Send to Amazon/FBA Prep:

- expanded prep detail rows now allow ASIN edits for purchase-item backed rows
- `/api/fba-shipments` accepts item ASIN updates and writes ASIN, Amazon title,
  and target sell price together
- existing sell-price-only edits continue to work

## Keepa Catalog Cycle Length

Live scheduler telemetry for `Keepa catalog priority refresh` was checked on
2026-09-05.

- completed recent cycles: 4
- average completed cycle length: 5.67 days
- median completed cycle length: 5.46 days
- latest completed cycles covered about 6,184 to 6,186 eligible ASINs
- current cycle started at `2026-09-02T23:22:37Z`; at the time checked it had
  covered 2,470 of 6,187 eligible ASINs, leaving 3,717

Cycle length was calculated from the latest scheduler metadata row per cycle and
only counted cycles with `remaining_after = 0`.

## Validation

- `npm.cmd run build` passed for the Next.js web/API routes.
- `integrations/match_sourcing_purchases.py` had already been run against
  production after the 10-day matching update and matched additional exact eBay
  purchases from eligible watchlist rows.

