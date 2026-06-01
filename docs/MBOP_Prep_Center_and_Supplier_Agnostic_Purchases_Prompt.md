# MBOP Supplier-Agnostic Purchases & Prep Center Workflow

## Goal

Add supplier-agnostic purchase support for non-eBay inventory purchases, including purchases shipped to me, purchases sent directly to a prep center, and purchases intended for Amazon FBA, Amazon MFN, or eBay resale.

Important context:
- Do NOT add `acquisition_type`.
- Existing `supplier` already identifies where the item was purchased.
- The more important modeling concept is what happens to the inventory next.
- Add/extend support around `fulfillment_path`, inventory destination, and lightweight prep-center workflow.
- Preserve workflow separation:
  - Purchases workflow != Receiving workflow
  - Receiving workflow != Amazon FBA workflow
  - Prep-center workflow should not be forced into Receiving because I do not physically receive those items.

## Phase 1 — Supplier-Agnostic Purchase Foundation

Add support for non-eBay/manual supplier purchases while keeping the existing `purchases` and `purchase_items` model.

### fulfillment_path

Allowed values:

- self_receive
- prep_center
- amazon_mfn
- ebay_resale

Suggested meanings:

- self_receive: item ships to me and goes through MBOP Receiving.
- prep_center: item ships directly to a prep center; do not show in normal Receiving queue.
- amazon_mfn: item is intended for Amazon Merchant Fulfilled inventory.
- ebay_resale: item is intended for eBay resale.

### Requirements

1. Keep using existing supplier field.
2. Add nullable purchase_items.fulfillment_path.
3. Preserve marketplace field.
4. Allow prep-center rows to target Amazon.
5. Do not add acquisition_type.
6. Prefer extending purchases/purchase_items instead of creating separate purchase tables.

### Optional Future Fields

- prep_center_name
- prep_center_received_date
- prep_center_shipped_date
- prep_center_notes

## Phase 2 — Manual Purchase Entry / Import Capability

Add a lightweight way to enter or import non-eBay purchases manually.

### Required Fields

- supplier
- supplier order number
- purchase date
- item title
- Amazon title
- ASIN
- system
- quantity
- unit cost
- target sell price
- tracking number (optional)
- carrier (optional)
- marketplace
- fulfillment_path
- prep_center_name (if prep_center)
- notes

### Behavior

- Write to purchases and purchase_items.
- If tracking is supplied and fulfillment_path=self_receive, create/link inbound shipment records.
- If fulfillment_path=prep_center, do not send through Receiving.
- Preserve auditability.

## Phase 3 — Lightweight Prep Center Workspace

Create a Prep Center page.

### Navigation

Add:

- Prep Center

### Columns

- Supplier
- Supplier Order Number
- Purchase Date
- Item Title
- Amazon Title
- ASIN
- System
- Quantity
- Unit Cost
- Target Sell Price
- Prep Center Name
- Tracking Number
- Prep Center Received Date
- Prep Center Shipped Date
- Amazon Shipment ID
- Current Status
- Notes

### Actions

#### Mark Prep Center Received

- Save prep_center_received_date
- Set status to prep_center_received

#### Mark Sent To Amazon

- Require Amazon shipment ID
- Save prep_center_shipped_date
- Link to FBA shipment workflow where practical

### Important Rules

- Prep-center items must not use the normal Receiving workflow.
- Do not mark prep-center items as Received.
- Do not break existing FBA workflow.

## Dashboard & Reporting

- Include prep-center inventory in inventory value reporting.
- Do not hide manual supplier purchases.
- Avoid double counting inventory already represented in Amazon FBA.

## Documentation Updates

Update:

- CURRENT_STATE.md
- DECISIONS.md
- ROADMAP.md
- KNOWN_ISSUES.md
- Purchases README
- New Prep Center README

Document:

- supplier identifies where inventory was acquired.
- fulfillment_path identifies workflow path.
- acquisition_type intentionally omitted.
- prep-center inventory remains separate from receiving.

## Validation

1. Purchases page still loads.
2. Receiving excludes prep-center rows.
3. Prep Center page displays prep-center rows.
4. Manual self-receive purchases can flow through Receiving.
5. Manual prep-center purchases bypass Receiving.
6. Dashboard includes manual supplier purchases.
7. No frontend landed-cost calculations added.
