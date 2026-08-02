# FBA Shipment Source Item Reconciliation

Date: 2026-08-02

## Purpose

The FBA shipment sync now reconciles shipment-level Amazon quantities back to included `fba_shipment_source_items`, not only legacy `fba_shipment_items` rows. This keeps MBOP source rows aligned with Amazon when a shipment is built from received source items.

## Behavior

- Loads included source items for every selected MBOP FBA shipment.
- Fetches Amazon v0 shipment item details when either legacy shipment items or source items exist.
- Groups MBOP legacy items and source items by ASIN.
- Allocates Amazon expected, received, available, reserved, unfulfillable, missing, and outbound quantities across included source rows.
- Writes source-row cost fields from each source item's quantity and unit cost.
- Includes source-row quantities and costs in shipment aggregate totals.

## SP-API Pagination Guard

The Amazon SP-API inbound shipment item iterator now tracks page content signatures. If Amazon repeats the same item page, the iterator logs a warning and stops to avoid duplicate processing or an endless pagination loop.

## Verification

Run:

```powershell
.\.venv\Scripts\python.exe -m py_compile integrations\amazon_spapi_client.py integrations\amazon_sync_fba_shipments.py
```
