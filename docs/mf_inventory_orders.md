# Amazon-backed MF Inventory and Orders

MF Inventory (`/mf-inventory`) and MF Orders (`/mf-orders`) extend List on Amazon. All reads/mutations go through `/api/mf`; provider traffic runs in the existing Python scheduler. No new queue, service, upload workflow or Amazon write endpoint is introduced. The workflow is explicitly scoped to the configured seller, marketplace and merchant fulfillment channel. Amazon customer order/item identities remain separate from purchase orders.

## Sources and synchronization

`integrations/amazon_sync_mf.py` uses the existing `AmazonSPAPIClient`, LWA credentials, retry/backoff, Supabase service-role persistence, ECS scheduler and telemetry. Job group `mf` supports manual refresh; the same job participates in the existing `amazon-sales-recent` scheduled group. No buyer, recipient, package or other PII datasets are requested or persisted.

Current official references verified during implementation:

- [Orders API v2026-01-01 searchOrders](https://developer-docs.amazon/sp-api/reference/searchorders): marketplaceIds, fulfilledBy=MERCHANT, lastUpdatedAfter/Before and embedded items with FULFILLMENT,CANCELLATION.
- [Amazon's Orders model](https://github.com/amzn/selling-partner-api-models/blob/main/models/orders-api-model/orders_2026-01-01.json): quantityFulfilled, quantityUnfulfilled, order/item identifiers, source update time and replacement associations.
- [Orders migration guide](https://developer-docs.amazon/sp-api/docs/orders-api-migration-guide): select operational datasets; do not request BUYER/RECIPIENT.
- [searchListingsItems](https://developer-docs.amazon/sp-api/reference/searchlistingsitems): seller-scoped discovery with marketplaceIds; pageSize <=20; summaries, attributes and fulfillmentAvailability.
- [Listings Items guide](https://developer-docs.amazon/sp-api/docs/listings-items-api): fulfillmentAvailability is the live offer quantity; submitted attributes can retain an old quantity after sales. MBOP never uses submitted quantity as live stock.

Initial discovery reads 30 days of updated MF orders plus outstanding orders within Amazon's supported order-history window. Subsequent downloads use a persisted source-time watermark with a ten-minute overlap and a three-minute safety delay. Previously tracked outstanding orders are explicitly revisited, including older ones. Both feeds paginate completely; page budgets, malformed payloads, missing quantities and API failures prevent advancing the success checkpoint. Orders pagination conservatively respects the documented 0.0056 requests/sec rate; listing discovery uses <=4 calls/sec. No routine report upload is required.

Successful offers and order changes persist as bounded normalized records. A compact source timestamp/fingerprint audit records duplicate/stale/conflicting observations without copying raw provider PII. Orders keep millisecond source precision. Equal-timestamp conflicting payloads are flagged instead of arbitrarily replacing stock facts; older observations cannot roll state backward. Each run records failure details. The UI shows last successful sync, last attempt, stale offers and errors. A failed run can have committed valid individual observations, but cannot advance the overall success watermark.

The seller must be configured through AMAZON_SP_API_SELLER_ID (or the existing aliases), along with the existing marketplace and LWA variables. Initialization refuses to reassign inventory if scheduler credentials differ from the configured seller/marketplace. Bounded local credential probes verified both Orders 2026 MF reads and Listings search successfully. Cloud verification is recorded in the release notes.

## Physical stock and allocation

`amazon_mf_lots` is a ledger registry of original listing lots or explicit counted openings. A unique listing_lot_id makes the listing-completion trigger/reconciliation retry-safe. The original listing allocations, purchase/receipt links, acquisition cost and export snapshots remain authoritative and unchanged. Opening lots have an explicit source, optional unknown cost, and no fabricated purchase.

Physical on hand = original lot quantity minus immutable allocated shipment quantities. Reservations, inspection holds and FBA-transfer allocations are distinct quantities. Available quantity also includes unallocated order demand, so shortages can make it negative. Amazon-listed quantity is an independent observation; it never replaces a physical count. Physical-vs-offer differences, unknown/mismatched SKUs, stale observations and shipment/reservation shortfalls remain visible.

The existing economic allocation convention is FIFO. Physical MF allocation narrows interchangeability to the exact account, MSKU, ASIN and normalized condition, then orders by original acquisition date and stable lot UUID. Already consumed shipment allocations never change acquisition costs or get reassigned retrospectively. Current reservations are rebuilt in customer-order purchase-time order from matching available lots. Source rows and shipment effects are serialized by the account row lock, including opening/count confirmation and listing registration.

Cumulative fulfilled quantity creates only a positive high-water delta. Repeated downloads cannot consume it twice. Partial fulfillment consumes only the delta and retains outstanding demand. Cancellation releases unshipped reservations but never returns shipped units. Quantity decreases and replacement orders use their own Amazon identities; a shipped-quantity regression is flagged without restocking. Buyer cancellation requests alone are not confirmed cancellations. Refunds have no stock-writing path.

Shipment event timestamps retain Amazon's order LastUpdatedTime, which is an observation boundary rather than a carrier dispatch timestamp. First-seen fulfilled quantities on orders created before tracking began are historical baselines, even if an old order was updated recently (for example, by a refund). Ambiguous first sightings after tracking began are flagged for reconciliation; known unshipped orders still consume fulfillment deltas normally. A newly counted opening cannot satisfy an earlier unresolved shipment: its stock_start_at is later than that event. Such shortfalls remain reconciliation evidence instead of consuming current stock twice.

The existing inventory projection reads remaining MF listing-lot balances rather than projecting sold units as physically present. It remains a derived scheduled projection; MF Inventory uses current ledger balances directly.

## Existing inventory and Keep MF

Amazon offers are a preview, not physical intake. An operator enters the total actually counted existing MF stock, including already recorded MF listing lots and excluding unlisted Received preparation units. The database subtracts existing MBOP on-hand quantity and creates only the surplus as an opening lot. A revision check rejects a count if stock, orders or offers changed after preview. A unique per-SKU/condition opening and request UUID protect retries/overlap. Counts below recorded stock require investigation; this phase does not silently write negative adjustments. Cost can remain unknown.

Keep MF is a persistent offer preference. A structured exact Tilly Tackers/Tilly Tacker brand, or reviewed ASIN B092FLB415 from the prior audited Tilly inventory, seeds Keep MF. No fuzzy title matching is used. Defaults insert only when no preference exists; later operator true/false choices survive every sync.

Inspection-held and FBA-allocation columns are represented independently and default to zero. This phase does not receive returns, buy labels, execute transfers or write Amazon quantities. Returns/refunds do not fabricate receipt events. Multi-source Amazon MF availability without an unambiguous aggregate is flagged for reconciliation rather than guessed. History is paginated; stock lineage shows up to 500 lots per MSKU.

## Deployment and validation

Migrations: `supabase/migrations/20261108042001_mbop_mf_inventory_orders.sql` and `supabase/migrations/20261108044257_mbop_mf_historical_order_baseline.sql`. It is additive to the listing foundation and does not modify applied migrations. Reconcile all shared versions with `supabase migration list --linked`, dry-run the linked push, then list again before the real push. Verify project `froeucjkcepuhgwisped`. All MF tables have RLS and only server-role access; functions use invoker security with public/anon/authenticated execution revoked.

Before initial discovery, the existing Supabase capacity guard requires fresh memory/disk metrics and a tiny read. This does not measure remaining Disk IO Budget. Initial discovery is bounded to MF order windows and at most 5,000 seller listing records; it is not a broad historical order backfill. Do not run full orchestration as a verification shortcut.

Focused checks:

```powershell
.venv/Scripts/python.exe tests/test_mf_inventory_orders.py
.venv/Scripts/python.exe -m unittest discover -s tests -p test_amazon_mf.py
.venv/Scripts/python.exe -m unittest discover -s tests -p test_mf_inventory_projection.py
.venv/Scripts/python.exe -m unittest discover -s tests -p test_amazon_orders_2026.py
node web/app/fba/listingBatchApi.test.mjs
node web/app/fba/inventoryLabExport.test.mjs
cd web
npm.cmd run build
```

The PostgreSQL tests run only explicitly (or with MBOP_POSTGRES_TESTS=1) in a disposable container. They verify the real migration over workflow fixtures, preserve the prior eight listing transaction regressions, and test order reservation/partial shipment/cancellation transitions, replacement shortages, late observations, concurrent retries, FIFO cost lineage, opening overlap/unknown cost, Keep MF choices and failed-sync checkpoints. No production physical opening is generated by these tests.
