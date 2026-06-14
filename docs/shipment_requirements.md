# MBOP FBA Shipment Requirements

## Purpose

MBOP should become the source of truth for Amazon-bound inventory after an operator sends a batch to Amazon. InventoryLab may be used as an occasional audit file, but MBOP should own shipment workflow state, shipment valuation, Amazon receiving visibility, and fulfillment-center timing history.

## Navigation

Add a `Send to Amazon` area with these workflow views:

- `Prep Queue`: existing received Amazon-bound inventory ready to be grouped into an FBA shipment.
- `Shipments`: new shipment list for current and historical Amazon inbound shipments.
- `Shipment Detail`: drill-down for one shipment, showing what MBOP sent and what Amazon has received or made available.

## Shipment List

The shipment list must support dense, large-monitor review. Each row should show:

- MBOP shipment code / Amazon shipment ID.
- MBOP workflow status.
- Amazon inbound status.
- Fulfillment center or destination FC when Amazon exposes it.
- Created/finalized date.
- Tracking number when available.
- Carrier delivery ETA when available, or carrier delivered date once delivered.
- Carrier pickup date/time when available.
- Carrier delivery date/time when available.
- Amazon checked-in date/time.
- Amazon receiving started date/time.
- Amazon closed date/time.
- Units sent.
- Units received by Amazon.
- Units currently FBA available / fulfillable.
- Units reserved.
- Units unfulfillable.
- Units missing or not yet available.
- FBA availability percentage: `available units / sent units`.
- Cost sent.
- Cost still counted as outbound-to-Amazon.
- Cost received or available at Amazon.
- Attention flags for stale, discrepant, delayed, or closed-with-shortage shipments.

The shipment list should label the two status lines as `MBOP:` and `FBA:` so the workflow state and Amazon state are easy to distinguish. Carrier name is not required in the list because current operations use UPS consistently.

Delivered column behavior:

- The column title should be `Delivered`.
- If carrier tracking has a delivered timestamp, show the delivered date with the tracking number underneath.
- If tracking has not delivered and an ETA is available, show `ETA: MM/DD/YY` with the tracking number underneath.
- If tracking has not delivered and no ETA is available, show `No ETA`.
- If a tracking number exists, show it underneath as a UPS tracking-history link.
- Do not use Amazon inbound shipment status as a carrier-delivered proxy; Amazon `DELIVERED`, `RECEIVING`, or `CLOSED` is separate from carrier delivery unless the carrier event timestamp is captured.
- Carrier ETA should be shown as a date-only value when only date-level confidence is available, to avoid timezone day-shift confusion.

## Shipment Detail

Shipment detail should show item-level reconciliation:

- ASIN.
- Amazon title.
- Seller SKU / MSKU when known.
- FNSKU when known.
- System.
- Quantity MBOP sent.
- Quantity Amazon expected.
- Quantity Amazon received.
- Quantity currently FBA available / fulfillable.
- Quantity reserved.
- Quantity unfulfillable.
- Quantity still missing or not yet available.
- Unit cost.
- Total sent cost.
- Outbound remaining cost.
- Linked purchase items.
- Raw Amazon shipment item status context.
- Manual notes / reconciliation notes.

## Amazon SP-API Sources

Use read-only Amazon SP-API integration patterns.

Primary shipment source:

- Fulfillment Inbound API.
- Legacy `getShipments` can be used where useful for shipment status values and shipment lookup.
- Current Fulfillment Inbound v2024-03-20 should be preferred for new calls when it can read Send to Amazon shipment details.
- As of June 13, 2026, legacy v0 `getTransportDetails` returns an Amazon deprecation error for the current shipment and should not be used.
- MBOP should run a best-effort v2024 identity bridge from the saved Amazon shipment confirmation ID, such as `FBA19F8YW7CV`, to any discoverable `inboundPlanId` and internal v2024 `shipmentId`.
- If the v2024 bridge finds that identity pair, MBOP may call allowed v2024 `getShipment`, `listShipmentBoxes`, and `listTransportationOptions` reads, storing discovered IDs, transportation option IDs, raw payloads, and tracking details in the shipment tracking payload.
- Missing v2024 identity or missing tracking details is not a sync error when legacy v0 shipment status and item quantities are still available.
- Current testing found that v2024 `listInboundPlans`, `getShipment`, and `listShipmentBoxes` can provide recent Send to Amazon shipment identity, destination FC, delivery-window dates, tracking IDs, and box contents. MBOP should synthesize read-only historical shipment detail from v2024 box contents when local `fba_shipment_items` rows do not exist.
- Null carrier pickup/delivery/check-in milestone timestamps can mean Amazon did not expose those event timestamps through the available read endpoints, not that the shipment lacks carrier progress in Seller Central.
- For older v2024-discovered shipments without local MBOP shipment items, FBA availability and shipment cost should display as not tracked instead of zero because current FBA inventory snapshots cannot reconstruct historical per-shipment availability.

Primary inventory availability source:

- FBA Inventory API `getInventorySummaries`.
- Use latest normalized FBA inventory snapshots to derive FBA available/fulfillable, reserved, inbound, and unfulfillable quantities.

Supplemental audit sources:

- FBA inbound discrepancy/noncompliance reports may be added later if Amazon shipment detail does not provide enough received/expected discrepancy detail.

Primary carrier tracking source:

- EasyPost should enrich FBA shipment carrier tracking once Amazon/SP-API has provided a tracking number.
- EasyPost owns carrier pickup, carrier delivery, carrier ETA, public tracking URL, carrier status, and carrier tracking events for FBA shipments.
- Amazon inbound shipment status must remain separate from carrier status. Amazon `DELIVERED`, `RECEIVING`, or `CLOSED` does not mean the carrier delivered timestamp is known.
- EasyPost tracker IDs and raw carrier payloads may be stored inside `fba_shipments.raw_tracking_json.easypost` unless a future reporting need justifies dedicated columns.
- The daily dashboard sync should run Amazon FBA shipment sync first, then FBA EasyPost carrier tracking, then inventory reconciliation/business value jobs.

## Status Model

Store both Amazon's raw status and MBOP's normalized status.

Normalized shipment statuses:

- `created`
- `finalized`
- `working`
- `ready_to_ship`
- `shipped`
- `in_transit`
- `delivered_to_fc`
- `checked_in`
- `receiving`
- `closed`
- `closed_with_shortage`
- `discrepancy`
- `cancelled`
- `historical`

Known Amazon inbound status examples include `WORKING`, `READY_TO_SHIP`, `SHIPPED`, `IN_TRANSIT`, `DELIVERED`, `CHECKED_IN`, `RECEIVING`, `CLOSED`, and `ERROR`.

## Fulfillment-Center Timing Capture

MBOP should store milestone timestamps by shipment and fulfillment center so a future report can show how long each fulfillment center takes to process inbound shipments.

Milestones to capture:

- Carrier picked up.
- Carrier delivered.
- Amazon checked-in.
- Amazon received / receiving started.
- Amazon closed.
- Amazon available, meaning all units are FBA available when that can be observed.

Derived durations:

- Carrier pickup -> carrier delivery.
- Carrier delivery -> Amazon check-in.
- Amazon check-in -> Amazon receiving.
- Amazon receiving -> all units FBA available.
- Carrier pickup -> all units FBA available.

Roadmap UI:

- Add a fulfillment-center performance report.
- Show average/median duration by FC and stage.
- Show slowest shipments.
- Show open shipments stuck after delivery, check-in, or receiving.
- Show trend over time by FC.

## Business Value Rules

MBOP must not double-count shipment value.

Shipment valuation rules:

- MBOP shipment items count as `outbound_to_amazon` only while the units are not yet covered by Amazon receiving or current Amazon inventory quantities.
- Once Amazon shows received/available/reserved/unfulfillable quantity for a shipment item, that quantity should no longer be valued as MBOP outbound.
- If a shipment is partially received, only the unreceived or unavailable remainder should remain outbound.
- If a shipment is closed, no shipment quantity should remain outbound unless an explicit discrepancy workflow keeps unresolved value open.
- InventoryLab must not overwrite MBOP inventory, costs, shipment rows, or purchase items.

## InventoryLab Reconciliation

InventoryLab is audit-only.

Recommended audit workflow:

- Operator provides an InventoryLab valuation CSV when there is an unexplained discrepancy.
- MBOP parses the file as an audit artifact or in-memory comparison.
- MBOP compares InventoryLab totals to MBOP by FBA sellable, reserved, inbound, MFN, outbound-to-Amazon, SKU/ASIN quantity mismatches, cost mismatches, and missing cost overlays.
- MBOP produces an audit report and does not import InventoryLab as an operational source of truth.

## Jobs

Add a shipment sync job that:

- Looks up open/current MBOP FBA shipments by Amazon shipment ID.
- Pulls Amazon shipment status and shipment item quantities.
- Can discover recent shipment headers from Amazon when Amazon exposes them through Fulfillment Inbound discovery APIs.
- Runs a cached best-effort v2024 identity bridge so normal scheduled syncs do
  not repeatedly scan inbound plans when Amazon did not expose a matching
  v2024 shipment identity.
- Captures fulfillment center and milestone timestamps when available.
- Captures carrier/tracking metadata and carrier delivery ETA when available from Amazon or carrier data.
- Refreshes current FBA inventory availability before computing shipment availability when needed.
- Updates shipment health metrics incrementally as the job runs so System Health can reflect partial progress.

The job should run at least daily. More frequent lightweight refresh is acceptable for open shipments.

## Non-Goals

- Do not write shipment updates back to Amazon.
- Do not merge the shipment workflow into Purchases or Receiving.
- Do not treat InventoryLab as the source of truth.
- Do not request restricted buyer/order PII.
- Do not use frontend code to calculate authoritative inventory value.
