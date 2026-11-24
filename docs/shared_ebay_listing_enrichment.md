# Shared eBay listing enrichment

## Scope and rollout

The existing Browse discovery, matching engine, seller intelligence, opportunity
economics, inventory demand, manual decisions, FM provenance and presentation
deduplication remain authoritative. This adds a provider adapter and router, not
a second evaluator. No Feed, bulk, extra credentials, paid services or marketplace
mutations are introduced.

Feature switch: `MBOP_EBAY_TRADING_ENRICHMENT=true` on scheduler tasks. Default is
off. Deploy with `scripts/deploy-scheduler.ps1 -EnableTradingEnrichment`. Setting
the flag false restores Browse enrichment; shared quota accounting remains on.
Do not revert the additive migration to roll back the provider choice.

## Evidence and routing

`ebay_listing_evidence.py` normalizes public GetItem evidence to MBOP's existing
Browse-shaped payload. Item specifics, description, condition, category, images,
seller, price, availability, auctions and Best Offer feed the unchanged evaluator.
ReturnAll is narrowed by public output selectors; full Trading XML is not stored.

Fresh compatible evidence is used first. Trading is preferred for known US
single-SKU IDs; discovery remains Browse. A selected nonzero variation ID goes
directly to Browse. Any Trading variation container or ambiguous parent requires
Browse and remains unresolved if exact variation identity cannot be established.
Trading variation enrichment is deliberately not enabled without live validation.
The old separate Trading availability fallback is skipped when this router is
enabled, avoiding a second refresh of the same listings in sourcing orchestration.

Each request tries each authorized provider at most once, with bounded transport
retries inside providers. Terminal sold/ended results do not trigger fallback.
Incomplete Trading evidence or a provider circuit can fall back to Browse.
If capacity prevents verification, the saved row remains pending and retains its
retry/reset checkpoint. Provider/identity failures remain visible as unresolved
failures, not product exclusions. Completed import rows are not reprocessed.
Browse-only deferred rows do not stop other eligible Trading rows in the saved
tab; valid outcomes are persisted before the import pauses for outstanding work.

## Shipping

Flat US domestic shipping is accepted only with explicit USD costs and no
unresolved geographic exclusions. Pickup is never treated as free shipping.
Missing cost is unknown, including FreeShipping without an explicit zero.
Quantity >1 requires applicable additional-unit costs or a contextual quote.

Existing matching/condition/economic checks run before calculated shipping.
GetItemShipping is called only for viable calculated-shipping listings, with
configured country, ZIP and quantity. Its returned services are destination
filtered. Unknown shipping cannot create an unconditional buy recommendation.
International/import ambiguity falls back to Browse rather than inventing costs.

## Quota protections

Migration `20261124043618_mbop_shared_ebay_trading_enrichment.sql` adds service-only
policy and daily event tables plus atomic admission/circuit functions. It extends
the existing app-hashed resource rows, usage ledger, cache and checkpoint RPCs.

`trading` is ONE pool for every Trading method, including GetItemShipping,
GetOrders and GetMyeBayBuying. Analytics method counts are not independent
allowances: the pool's consumed count is derived from limit minus shared remaining.
Every actual HTTP attempt reserves a call under the same PostgreSQL row lock.
Same-window delayed observations cannot replenish locally reserved capacity.
Quota reset requires fresh Analytics evidence before new calls.

Operational defaults, adjustable in `ebay_api_quota_policy`:

- Essential headroom: 10% of each actual observed allowance (500 at 5,000).
- Browse discovery: another 20% protected against nonessential detail calls.
- While a saved import is running/paused: manual import and other sourcing each
  receive 50% of the nonessential daily allocation. Neither can spend the other's
  share. Unused partitions release when the import ends. Essential calls are
  separately attributed and bypass sourcing floors, never the actual resource cap.

These are conservative policy defaults, not measured essential demand. Tune them
from production attribution. Sources may wait until the next window rather than
borrow the other class's protected share. A detail-plus-shipping estimate avoids
starting a two-call Trading path with only one call of sourcing headroom.

Operational purchase/order reads use the shared transport without changing API or
order semantics. Optional image and availability refreshes use background priority.
HTTP 429 and XML error 518 pause the shared resource; Retry-After/reset is honored.
Transient HTTP failures use three bounded attempts with jitter; sustained provider
failures create a five-minute shared circuit. Per-day in-app exhaustion notices
reuse `mbop_notifications` and do not repeatedly reopen/read-reset the same notice.

## Cache and telemetry

Reuse the existing app + marketplace + exact item/variation + buyer-context cache.
Quantity is included for non-default quantities. Both providers write the same
normalized payload. ASIN is intentionally absent from this cache key; candidate
identity remains eBay item + ASIN. In-run partial Trading identity evidence can be
reused while a different ASIN receives its own economic/shipping decision.

`MBOP_EBAY_EVIDENCE_TTL_SECONDS` defaults to 900 and is clamped to 30–900 seconds.
Stable and volatile evidence retain the same conservative TTL in this release;
there is no new long-lived raw evidence store. Conflicting fresh search title,
condition or price invalidates the cache. Existing bounded expiry cleanup remains.
eBay display freshness rules are not treated as indefinite retention permission.

System Health shows both pools, actual limits, local consumed/reserved amounts,
remaining, utilization, Pacific reset, observation freshness and circuit state.
Daily usage/event attribution includes methods, cache reuse, preliminary exclusions,
fallback reasons and capacity waits. Counters begin at deployment, not retroactively.

## Verification and limitations

Focused Python normalization/router tests, existing eBay/Flipmine/matching tests,
isolated PostgreSQL reservation/concurrency/checkpoint tests, frontend tests, lint
and Next.js build are required before rollout. Production evidence comparison must
remain bounded and never place purchases/offers/bids. If Browse is exhausted,
document that live cross-provider parity is unavailable rather than probing it in
a retry loop. Equivalent stored Browse-shaped fixtures verify shared evaluator
inputs without claiming live provider parity.

After deploying, inspect API events and quota floors, run a bounded saved-import
recovery (never a new import), and inspect saved candidate/opportunity results.
Verify FM provenance, Buy List/Closest Excluded counts, checkpoint retention and
completion presentation at the authenticated production site. Do not reprocess a
completed import merely to demonstrate the provider switch.
