# Wholesale purchasing: repository and API discovery

Date: September 9, 2026. Repository baseline: `259c6eb`. Documentation only; no implementation, migrations, marketplace account requests, production changes or deployment.

## 1. Recommendation

Build a separate wholesale evaluation workflow that shares MBOP's Amazon/Keepa clients, cached evidence, inventory sources, authentication and dense sourcing presentation patterns. Do not make Royal rows synthetic eBay listings or overload the current sourcing lifecycle.

The persistent identity is the **supplier product**, with dated supplier observations, multiple Amazon candidates, one selected candidate, one current opportunity, append-only decisions and a separate order-candidate handoff. Imported price changes should normally trigger local reevaluation, not repeat Amazon searches.

Preserve the established decisions: New products only; 25% True ROI; approximately 30 days of expected sales; risk signals are informational; hard passes persist until manual reversal; temporary passes may resurface after changed conditions. Inbound ~$0.38/game, return transaction ~$0.21/game sold and ordinary storage ~$0.015/game/month are versioned future evaluation inputs, not new rules applied in this task. Do not automatically apply game allowances to accessories.

## 2. Existing infrastructure and reuse boundaries

Repository inspection started with `docs/AI_README.md`. Relevant architecture/schema/business-rule, shipment, capacity and scheduler documentation was reviewed alongside the following code. This is a repository capability assessment, not a certification of live API permissions, cache coverage or remaining quota. The Royal workbook statistics are supplied context; the workbook was not re-audited in this task.

| Capability | Existing implementation / behavior | Reuse and gap |
|---|---|---|
| Sourcing model | `sourcing_runs`, `sourcing_seed_asins`, `sourcing_ebay_candidates`, `sourcing_opportunities`, `sourcing_actions`, progressive batch tables; [schema](database_schema.md) | Reuse current-state plus historical-action pattern. Existing joins, identities, purchase matching and opportunity types are eBay-oriented. Wholesale needs its own supplier-product keys and lifecycle. |
| Sourcing UI | [page.tsx](../web/app/sourcing/page.tsx): local `ReplenishmentTable`, inline controls/dialogs; [useSourcingOpportunities.ts](../web/app/sourcing/useSourcingOpportunities.ts), [types.ts](../web/app/sourcing/types.ts) | Reuse density, side-by-side product comparison, loading/error/action patterns. Most screen pieces are local to the large page, not already independent reusable components. Extract only a small presentation primitive when both screens actually need it. |
| API and authentication | `web/app/api/sourcing/opportunities/route.ts`, `opportunities/[id]/actions/route.ts`, `history/route.ts`, `_supabase.ts`, `web/app/mutationHeaders.ts`, API `_server.ts` | Reuse server-only Supabase and existing mutation authentication. Separate `/api/wholesale/...` contracts; no direct browser Supabase or marketplace access. Keep aggregation and evaluation server-side. |
| Catalog identity | [amazon_spapi_client.py](../integrations/amazon_spapi_client.py): `get_catalog_item`; [amazon_sync_catalog_items.py](../integrations/amazon_sync_catalog_items.py): `normalize_catalog_item` | Already obtains attributes, identifiers, title, edition, platform, format, region, package quantity, product type, images and relationships. Reuse normalizer, but inspect evidence rather than treating normalized guesses as conclusive. |
| Catalog cache | `amazon_catalog_item_identity_snapshots`, migration `20260804000000_mbop_sourcing_catalog_velocity_suppression.sql` | Existing latest cache has ASIN primary key, timestamp and raw identifiers. Reuse for US marketplace. It is not a multi-marketplace cache or an indexed many-to-many identifier search cache. |
| UPC/EAN and title search | Client currently supports known-ASIN retrieval; no `searchCatalogItems` identifier/keyword method or durable query-result cache found | Add narrow methods to the existing client later. Extract known identifiers from cached catalog/Keepa evidence; never assume one code maps to one ASIN. Existing browser Amazon search links are not an API discovery pipeline. |
| Compatibility | [sourcing_match_rules.py](../integrations/sourcing_match_rules.py), platform detection, shared marketplace-title cleaner, catalog normalizer | Reuse pure identity checks and evidence terminology. Do not run an entire eBay-specific candidate scorer on supplier rows. Edition/bundle/region/physical-format uncertainties need explicit review. Current game-only filters would incorrectly exclude intended wholesale accessories. |
| Keepa | [keepa_client.py](../integrations/keepa_client.py), [keepa_sync_products.py](../integrations/keepa_sync_products.py), `keepa_product_snapshots`, optional history points, `vw_latest_keepa_product_snapshot` | Existing ASIN batching, token status, missing/stale selection, plan-only and adaptive limits. Normalizes Buy Box current/30/90-day prices, sales ranks, rank drops and New-offer count. Reuse; do not create a second Keepa ingestion stack. |
| Velocity | [build_sourcing_seed_asins.py](../integrations/build_sourcing_seed_asins.py): `finalize_seeds` computes `monthly_velocity = units_sold_lookback / max(sales_lookback_days / 30, 1)` | This is MBOP's own historical sell-through, not total Amazon demand. Keepa `sales_rank_drops30/90/180` already exists for comparative market activity. No normalized exact market-wide monthly unit-sales model was found. |
| Seller counts/history | Keepa `offer_count_current` reads `COUNT_NEW` index 11; optional normalized `offer_count` history; raw Keepa retained | Existing metric is New marketplace offers, not FBA-only sellers. FBA count requires suitable offers data and careful freshness/coverage labeling. Direction can be computed from comparable dated snapshots/history without feeding buying math. |
| Eligibility | [amazon_check_listing_restrictions.py](../integrations/amazon_check_listing_restrictions.py), client `get_listings_restrictions`, [blockedAsins.ts](../web/app/api/sourcing/blockedAsins.ts) | New condition is already the CLI default `new_new`. Classification and throttling are reusable. Current storage is an ASIN blocklist, not a full seller/marketplace/condition eligibility cache. |
| FBA and pipeline inventory | `amazon_fba_inventory_snapshots`, `amazon_inventory_planning_snapshots`, `inventory_positions`, FBA shipment/source items; [score_sourcing_opportunities.py](../integrations/score_sourcing_opportunities.py): `fetch_pipeline_quantity_by_asin` | Reuse authoritative source quantities and exclusions. Existing sourcing combines fulfillable inventory with purchased/received/outbound quantities; it is not a complete wholesale exposure allocator and does not automatically deduplicate every Amazon-inbound/local-outbound overlap. |
| Fees | [amazon_sync_fee_estimates.py](../integrations/amazon_sync_fee_estimates.py), client `get_my_fees_estimate_for_asin`, `amazon_fee_estimates` | Cache key already includes ASIN, marketplace, fulfillment channel, listing price, shipping price and currency. Stores total, referral, FBA and variable closing components. Reuse AFN estimates at the actual chosen evaluation price. Validate successful status and required amounts. |
| Profitability | Existing sourcing scorer computes profit/ROI, historical fees and `conservative_fee_estimate = price * 0.22 + 4`; `sale_price_reference` takes the minimum available seed/current/90-day price | Reuse component concepts and backend ownership, not this complete formula. Wholesale requires explicit cost allowances and a fixed primary price policy. Do not inherit eBay minimum-profit/ROI settings, Best Offer assumptions, or automatic minimum-of-risk-prices behavior. |
| Purchase lifecycle | `purchases`, `purchase_items`, eBay sync, receiving, FBA shipment workflow; `non_ebay_purchase_cogs_sources` and InventoryLab bridges | Existing supplier text and non-eBay COGS provenance do not constitute a supplier catalog/order system. Add to Order must not fabricate a purchased item or write COGS. Future order work can explicitly map confirmed orders to receiving infrastructure. |

## 3. ASIN discovery and selection

Recommended sequence:

1. Validate/import row and retain original title, SYS and identifier. Skip non-products and explicitly USED rows, retaining import skip counts/reasons. Preserve questionable codes as unverified; title search can still proceed.
2. Resolve the persistent Royal product and look up both prior identifier-search results and prior title/platform-search results. Reuse unexpired results, including negative results. A known UPC match never cancels the title-search branch.
3. Search identifiers using `searchCatalogItems` v2022-04-01, grouped by identifier type and marketplace. Search supplier title plus canonical platform/product context in a separate keyword request. Include edition/format context where supplied. The 20-keyword limit is words for a query, not a batch of 20 unrelated products.
4. Merge the union by `(supplier_product, marketplace, ASIN)`. Retain every source match, query, returned identifier, timestamp and search-completion state. Attribute batched results using returned identifiers, not response position. Deduplicate ASINs, not evidence. Resolve legitimate variation children; parent containers are not purchasable candidates by default.
5. Validate identity: platform, game versus accessory, edition, physical/digital, bundle/package quantity, region and product facts. Classify each candidate compatible, incompatible or unresolved, with evidence. An exact UPC is evidence, not an override for contradictory identity facts. `country_of_origin` is not proof of game region compatibility. Missing facts require review, not invented compatibility.
6. Enrich compatible/unresolved candidates from shared cached catalog and Keepa data. Resolve identity gaps before spending on clearly wrong ASINs. Known unexpired restrictions can skip unnecessary paid enrichment; retain their candidate records.
7. Check New eligibility for each candidate that could be selected. Unknown or stale checks cannot make a normal actionable opportunity. Persist negatives so future lists do not restart this work.
8. Rank **compatible and sellable** candidates by comparable velocity evidence. Show other plausible candidates and the evidence for rejection/pending status. Do not rank the UPC match first merely because of its discovery source.
9. Automatically select only when compatibility, eligibility, discovery completeness and comparable velocity evidence support it. Otherwise request manual candidate review. Record whether selection is automatic or manual and pin a manual selection until the operator changes it; stale evidence can suspend actionability without silently changing the selected ASIN.

Amazon supports separate identifier and keyword searches, up to 20 identifiers per request and 20 results per page. Use returned pagination. If a configured page/call budget is reached, mark discovery incomplete and resume later; do not claim the resulting subset contains the highest-velocity valid listing. [Catalog search reference](https://developer-docs.amazon/sp-api/reference/searchcatalogitems).

### Velocity recommendation

Use existing **Keepa `sales_rank_drops90`** as the initial common market-activity ranking metric among compatible New-eligible ASINs, with `sales_rank_drops30` as a documented tie-breaker. Keep the metric/window visible. Do not convert rank-drop counts into an asserted monthly unit forecast or compare 30-day counts directly with 90-day counts. Rank-reference/category differences, variation-shared ranks, missing data and close ties should produce an uncertain recommendation/manual review rather than a false winner. Rank drops indicate sales activity but are not an exact unit counter. [Keepa statistics](https://keepa.com/api-docs/statistics-object.html).

The raw Keepa object may also contain `monthlySold`, but the current MBOP normalizer does not expose it as a typed metric. Keepa describes it as Amazon's bracketed bought-in-past-month value, often absent, and variation-specific. It is a lower bound such as 100+, not a precise estimate. Preserve/display it when available; do not mix it numerically with rank drops or assume missing means zero. [Keepa product object](https://keepa.com/api-docs/product-object.html).

Use **MBOP's existing own-sales `monthly_velocity`** for the 30-day exposure target where usable history exists. The supplier-product view must also disclose inventory held under other *confirmed interchangeable* candidate ASINs, without summing market demand across duplicate listings. Do not pool incompatible regions/editions or unrelated platform versions.

There is no demonstrated existing forecast of MBOP's likely share of sales for an ASIN it has never stocked. Until that input is decided, leave automated proposed quantity unavailable and support an explicit operator quantity. Do not invent `market sales / seller count`: that would use a competition signal to change quantity and violate the business rule.

## 4. Eligibility gate

Reuse `get_listings_restrictions(asin, condition_type='new_new')`. Inputs are seller ID (`AMAZON_SP_API_SELLER_ID`), marketplace, ASIN, New condition and reason locale. The existing classifier treats an empty restrictions array as sellable; `APPROVAL_REQUIRED`, `NOT_ELIGIBLE` and `ASIN_NOT_FOUND` have explicit statuses. API errors, missing arrays or unrecognized nonempty restrictions are unknown, not sellable. These are listing restrictions at a point in time, not an unrestricted guarantee against future account/category changes.

Introduce a shared eligibility evidence cache keyed by **seller + marketplace + ASIN + condition**, storing status, reason codes, approval links, checked time, expiry and source evidence. Current `sourcing_blocked_asins` lacks that key, positive checks and a complete audit trail. Its absence is not eligibility proof.

Honor existing operator/global ASIN blocks as an additional gate. Reuse the read/check behavior of `blockedAsins.ts`; do not blindly call the bulk blocklist writer. Its restricted upsert can replace an existing reason, and its sellable path deletes matching Amazon-restriction blocks. Wholesale should not erase unrelated manual decisions or change eBay sourcing. Keep an operator hard pass separate from API evidence so an automatically refreshed sellable result does not reverse a hard pass.

If all candidates are restricted, retain product/snapshots/candidates and mark the evaluation non-actionable. If one is eligible, it may be selected among valid candidates. If none is confirmed eligible because checks are pending/unknown, show pending review internally rather than a normal buying opportunity. Recheck the selected candidate on Add to Order when its evidence is stale.

## 5. Quota-safe enrichment

Use the existing Python integration/client and ECS scheduler-task architecture. An authenticated API request accepts a bounded job and returns its ID; it must not process 1,000 rows synchronously or launch local Python from the web container. Persist cursors, attempts and a leased reservation with heartbeat/expiry. One active job per supplier import plus shared per-operation quota coordination prevents duplicate work across imports and existing jobs. Do not change existing scheduled cadence.

**Suggested initial freshness policy, not an existing MBOP guarantee:**

| Evidence | Proposed cache/revalidation policy |
|---|---|
| Imported observations | Immutable; parse the identical supplier/file/date once. A later dated unchanged list is still a new price/availability observation. |
| Supplier identity and reviewed compatibility | Persist indefinitely with provenance; revalidate after identity fields change, manual invalidation or contradictory catalog evidence. |
| Identifier and title search results | Separate query hashes including marketplace, query type, normalized inputs and search version; positive sets 30 days, empty results 7 days. Retain failed versus genuinely empty distinction. |
| Catalog identity | Reuse current cache; refresh after 30 days or identity conflict. Fetch missing details in ASIN batches where supported. |
| New eligibility | Positive 7 days, restricted 30 days, unknown retry with exponential backoff. Selected Add-to-Order checks should be at most 24 hours old. These intervals are proposed configurable starting points. |
| Keepa active opportunity | Reuse fresh evidence within 24 hours; refresh only stale distinct ASINs with an explicit token budget. Passive Watch/temporary passes can use a longer, e.g. 7-day window. Hard passes do not receive routine paid enrichment. |
| Fee estimate | Exact existing price/currency/AFN cache key; refresh on evaluation price change or age beyond a proposed 7 days. A supplier-only price change does not require new Amazon fee data at the same selling price. |
| Current inventory | Read existing source snapshots and pipeline records in bounded ASIN batches. Recompute exposure at Add to Order and after commitment changes. |

Price-only changes create a new supplier observation and local evaluation using fresh shared evidence. They do not invalidate an identifier/title mapping. Identity changes invalidate matching. Unchanged imports do not overwrite decisions or trigger every external API. Active prices, eligibility and inventory have independent freshness; do not treat a recently imported spreadsheet as fresh Amazon data.

Amazon's documented defaults are 2 requests/second per account-application pair for Catalog search and get-item (burst 2); Listings Restrictions is 5/second per account-application pair (burst 10). Application-wide limits also apply. Observe returned usage-plan headers and 429 backoff; MBOP's current restrictions worker targets 4/second but its limiter is process-local. [Catalog limits](https://developer-docs.amazon/sp-api/docs/catalog-items-api-rate-limits), [Restrictions limits](https://developer-docs.amazon/sp-api/lang-en_EN/docs/listings-restrictions-api-rate-limits).

For 1,000 entirely new distinct rows, an illustrative first pass is about 50 identifier requests plus 1,000 distinct title queries, before pagination and type-group rounding. At 2/second that is roughly nine minutes of Catalog request pacing alone. Do not promise instant full-list completion. Later price-only imports can require **zero discovery calls** while the two search caches remain valid.

Keepa supports up to 100 ASINs/request; MBOP defaults to batches of 50. Basic retrieval costs one token/product; batching reduces HTTP overhead, not token cost. Offers cost more, and MBOP's default rating request can add cost. Use no-rating/no-stock, existing plan-only/token/adaptive guards and deduplicate ASINs across supplier products. Reserve detailed offers for active candidates that need them. The client has no dedicated `buybox` parameter currently; if required price evidence is unavailable, a narrow optional parameter is preferable to always buying extensive offers. [Keepa product request](https://keepa.com/api-docs/product.html).

Do not mislabel `offer_count_current` as FBA sellers. Raw `stats.offerCountFBA`, where successfully retrieved, counts retrieved live New FBA offers and may be incomplete. Store retrieval depth, success, timestamp and completeness with it. Trends require comparable observations; missing or truncated samples are not a decline. [Keepa statistics](https://keepa.com/api-docs/statistics-object.html).

Store bounded normalized history and reference shared evidence. Avoid copying full Keepa histories into every import row. Before introducing large snapshot writes, follow `docs/supabase_capacity.md`; no database load or quota-spending job was run for this discovery.

## 6. Recommended conceptual data model

Names below are proposals, not migrations. All are MBOP operational objects in `public`, server-only under existing auth/RLS conventions.

| Entity | Proposed mapping and uniqueness |
|---|---|
| Supplier | Small supplier registry, e.g. `wholesale_suppliers`; stable Royal identity. Existing purchase supplier text can be mapped later without rewriting history. |
| Import | `wholesale_imports`: supplier, price-list date, file hash, import revision, parser version, status/counts. Unique supplier/date/file hash; corrected lists are explicit revisions. |
| Supplier product | `wholesale_supplier_products`: stable surrogate ID, supplier, source SKU if truly stable, exact title/SYS/identifier plus separately normalized identity. Do not use ASIN or blindly use UPC as the primary identity. Supplier SKU uniqueness is conditional on evidence; conflicting identifier/platform/pack rows require resolution. |
| Supplier snapshot | `wholesale_supplier_observations`: product/import association, exact values, price/currency, quantity raw text, lower bound, exactness flag and provenance. At most one accepted observation per product/import; preserve duplicate/conflicting row provenance and quarantine conflicts. Later unchanged lists remain observations. |
| Discovery evidence | Shared query-result cache and identifier-to-ASIN associations; unique query fingerprint/version/marketplace, many ASINs per identifier. Reuse existing ASIN catalog cache for detailed facts. |
| Candidate match | `wholesale_amazon_candidates`: unique product/marketplace/ASIN, source evidence union, compatibility status/reasons/version, manual overrides; links to shared Keepa and eligibility evidence. Never deduplicate by UPC into one ASIN. |
| Selected match and current opportunity | One `wholesale_opportunities` row per supplier product/marketplace. Selected candidate FK, selection source/pin, current observation, stage/decision state, evaluated input version, component costs, price basis, qualification and separate informational signals. No separate selected-match table needed initially. |
| Evaluation history | Immutable evaluations keyed by opportunity + input fingerprint + evaluator/policy version. Decisions and order candidates reference the exact evaluation; current opportunity points to the latest one. |
| Decision | Append-only `wholesale_decisions`: opportunity/product, selected candidate, observation/evaluation, actor/time, action/reason, hard/temporary scope and reversal reference. One current decision pointer; never destroy prior decisions when reopening. |
| Order candidate | `wholesale_order_candidates`: requested quantity, product, chosen ASIN, observation/quoted unit cost/currency, evaluation, actor, version and state. Unique request idempotency key and one active line per product/marketplace. Repeated Add updates an explicit requested total, not an implicit duplicate/additive purchase. |
| Eligibility evidence | Shared seller/marketplace/ASIN/condition cache described above, distinct from operator decisions. |
| Enrichment run/work items | Durable import-linked run, stage cursors, retry state, work-key deduplication and leased ownership; reuse existing run/reservation patterns rather than a new scheduling platform. |

Import normalization preserves `144+` as raw `144+`, lower bound 144 and `is_exact=false`; it does not assert total available stock equals 144. Punctuation removal is recorded normalization; inferred missing digits remain an unconfirmed candidate transformation. Preserve leading zeros and original Excel cell representation; never pass identifiers through floating-point conversion. Date comes from explicit list metadata/operator confirmation, not the upload timestamp alone.

Supplier history is sparse observation history. “Previous price” means the prior dated observation. A 30/90-day statistic must declare whether it is observation-weighted or carried-forward/time-weighted and show coverage; do not imply daily supplier prices exist. Missing products on a later list are not automatically sold out. Out-of-order imports remain historical and do not silently replace the current dated observation.

## 7. Evaluation, inventory and risk separation

The future evaluator should expose supplier cost, item-specific selling/FBA fees, inbound allowance, expected return transaction allowance, holding-time storage, true dollar profit, margin, ROI, 25% price floor and headroom. Persist the chosen selling-price source and evidence timestamp. All calculations belong in backend services, with versioned policy inputs; React only renders results.

Do not reuse `sale_price_reference` unchanged: it automatically takes the minimum of current/90-day/seed prices. Choose one explicit primary wholesale selling-price policy. Suggested starting policy for approval is the selected ASIN's New 90-day Buy Box average; current price, 30-day average and direction remain separate information. Missing primary-price or fee evidence yields incomplete evaluation, not a silent fallback that changes semantics.

Use the cached Amazon **total** fee estimate or its non-overlapping components, never both. Historical selling fees alone are not a price-correct fee quote. The 25% price floor must account for price-dependent referral/closing fees; a constant-fee subtraction is insufficient. Validate a component-based fee function or leave the floor unavailable when fee behavior is not supported, rather than issuing unbounded trial-price API calls.

Risk signals reside in a separate informational structure with no inputs into ROI, price selection, hurdle, quantity or qualification. Unit tests should prove that changing risk signals alone leaves those outputs unchanged. A human may temporarily Pass for Price Risk or Competition; that human action is distinct from automated qualification.

Exposure should partition mutually exclusive physical/commitment quantities: FBA sellable inventory, valid reserved/transfer/processing exposure as appropriate, in-transit FBA units, received warehouse stock, ordered-not-received purchases and active order-candidate commitments. Exclude cancelled/returned/business-excluded/eBay-destination quantities. Unfulfillable inventory needs its own visibility, not automatic sellable stock.

Reconcile Amazon inbound and local outbound by shipment/source identity before summing. Do not add aggregate `inventory_positions` on top of the same purchase/FBA rows. Include recovery-source shipment units. The recent inbound study found header/item disagreements, so prefer reconciled item quantities with explicit discrepancy state. A later confirmed wholesale order must atomically replace its candidate commitment, not double-count both. Return/cancellation/release transitions remove the corresponding commitment.

Target roughly one month of MBOP-expected sales, less existing exposure, bounded by confirmed stock/pack constraints once known. No competition-price-risk multiplier is allowed. `144+` supports a conservative available minimum, not a claim of exact stock. Quantity above the known lower bound requires supplier confirmation rather than invented availability.

## 8. Lifecycle and Add to Order boundary

`Imported → discovery pending → identity review or eligibility pending → evaluated → actionable / nonqualifying`.

Hard-pass reasons **Listing/ASIN Issue** and **Restricted / Can't Sell** create persistent supplier-product suppression until an audited manual reversal. Preserve per-candidate incompatibility/restriction separately, so rejecting one ASIN during candidate review does not unnecessarily discard other legitimate matches. A product-level hard pass must not create a global block on every other supplier's valid use of that ASIN.

Temporary Pass reasons are Low Profitability, Price Risk, Too Much Inventory, Competition and Other. Save baseline evaluation/evidence, then reevaluate on later dated observations or relevant fresh operational evidence. Resurface the same opportunity when qualification is met and decision-relevant conditions change; append a new evaluation and reopening event. Reimporting the same content/date or rerunning the same evaluation must not create new decision/opportunity history. Risk changes may trigger a human re-review notification for a prior risk-based Pass, but must not change the evaluator's qualification result. Watch follows the same evidence model while remaining a distinct user intent.

Add to Order opens a small quantity dialog showing supplier availability, 30-day target, FBA/inbound/on-order/committed exposure, resulting days of supply, unit cost and extended cost. The server validates positive integer quantity, current observation/version, selected compatible New-eligible ASIN and fresh evaluation, then atomically saves an idempotent **order candidate** and decision event. Handle stale-price/version conflicts explicitly. Record any permitted quantity override as an operator choice.

This state is a draft buying intention, not a supplier order, purchase, inventory receipt or COGS entry. Count it separately as a soft commitment to prevent two buying decisions using the same remaining demand. Support editing/releasing the candidate. The future order workflow will consume it by stable ID; no supplier submission, payment, shipment, purchase import or order UI is designed here.

## 9. UI reuse plan

Reuse AppShell/navigation conventions, desktop table density, supplier/Amazon image-and-title comparison, external links, `KeepaPriceIndicator`, mutation headers, error/loading states and authenticated API patterns. Use typed backend DTOs and server filtering/pagination/summary totals.

Wholesale-specific UI will need: list import/date/supplier selector with validation summary; current/prior supplier prices and availability; multi-ASIN candidate review with evidence/eligibility/velocity; itemized True ROI cost display; inventory exposure/days of supply; informational risk columns; hard/temporary Pass controls; Watch; and the quantity dialog.

Do not copy eBay auction, Gixen, Best Offer, seller-decline, Purchased Pending Match, or eBay listing deduplication behavior. Do not undertake a broad sourcing-page refactor merely to create wholesale UI. Small reusable display primitives are sufficient initially.

## 10. Implementation phases

| Phase | Objective / likely areas | Success criteria | Dependencies |
|---|---|---|---|
| 1. Supplier history foundation | Future MBOP migrations; bounded Royal parser; import API and fixtures | Exact raw identifiers/titles retained, USED/nonproducts skipped, 144+ represented correctly, repeat import idempotent, new dated observations retained, conflicting duplicates quarantined | Confirm price currency/unit/pack interpretation and import-date source; no ASIN/API work required |
| 2. Discovery and New eligibility | Extend existing Amazon client; reuse catalog normalizer/match helpers; query/candidate/eligibility caches; bounded ECS work runner | Both identifier and title branches execute/cache; union retained; platform/edition/region/bundle tests pass; unknown restrictions fail closed; resume/idempotency/quota tests pass | Phase 1; actual role/access smoke tests on a tiny sample, no broad permission expansion |
| 3. Evaluation and exposure | Reuse Keepa/fee clients and snapshots, own-sales velocity and inventory sources; dedicated wholesale evaluator/read API | Price/cost provenance visible; 25% True ROI inputs agreed; exposure reconciles without duplicate shipment/commitment units; risk-only mutations cannot change buying math; incomplete data explicit | Phase 2; resolve the economic/quantity questions below; documented freshness policy |
| 4. Review lifecycle and candidate handoff | New wholesale screen/API, small shared display primitives, decisions/order-candidate state | Manual ASIN pinning, reversible hard passes, conditional temporary resurfacing, repeat-import stability, idempotent quantity dialog and concurrency conflict tests | Phase 3; no actual wholesale-order workflow |
| 5. Bounded pilot and operating checks | Existing scheduler/deployment conventions, telemetry and read-only sample comparisons | Small Royal subset reviewed against source lists/Amazon evidence; measured API/token cost; no repeated enrichment on unchanged import; existing sourcing regression suite passes | Phases 1-4; rollout authorization in its own task; existing schedule cadence preserved |

Each phase is suitable for a separate session/commit. Future migrations belong to MBOP's canonical shared-project migration history and must not modify already-applied migrations. This report creates none.

## 11. Genuine remaining decisions

1. **Primary selling-price policy.** Approve one explicit basis and missing-data behavior. Recommendation above is New 90-day Buy Box; current sourcing's automatic minimum would conflict with the informational-only treatment of alternative price signals.
2. **True ROI denominator and storage horizon.** Confirm whether capital basis is supplier cost alone or supplier cost plus inbound acquisition-to-FBA expense. Recommend the latter, with all listed variable expenses deducted in profit and the same definition used for the 25% floor. Confirm an initial assumed holding interval when no trustworthy item-specific forecast exists. The 25% hurdle itself is settled.
3. **New-to-MBOP demand.** Existing data can compare ASIN market activity but cannot reliably predict this seller's share for a never-stocked ASIN. Recommend explicit operator quantity initially; no seller-count allocation or new velocity model without separate agreement.
4. **Supplier commercial identity/units and accessory costs.** Confirm whether PRICE is per saleable unit, currency, case packs/MOQs and whether the supplied SKU is stable. Game allowances should not silently qualify accessories; approve a separate accessory allowance policy or leave those evaluations incomplete pending measured costs.

No need to reopen New-only importing, multiple candidate discovery, fastest legitimate eligible ASIN preference, 25% hurdle, 30-day target, informational risks, supplier price history, pass semantics or the order-workflow boundary.

## Verification

Reviewed repository modules/schema definitions and official Amazon/Keepa documentation. No live seller account or supplier calls, workbook reprocessing, SQL, code edits, migrations or deployment were performed. Only this documentation file was added. No build/tests were necessary for a documentation-only discovery; the phases specify the tests required before implementation.
