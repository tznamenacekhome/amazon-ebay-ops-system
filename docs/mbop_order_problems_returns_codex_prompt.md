# MBOP Order Problems + eBay Returns Workflow Implementation Prompt

We are adding the eBay returns/refund workflow to the Midnight Blue Operations Platform (MBOP).

## Current MBOP architecture

MBOP uses:

Python integrations -> Supabase PostgreSQL -> Next.js API routes -> React frontend

Supabase is the operational source of truth. The frontend must not talk directly to Supabase. Frontend components should render backend/API-provided values and should not rebuild business rules in React.

Important existing files / areas to inspect before coding:

- `web/app/page.tsx`
- `web/app/purchases/`
- `web/app/purchases/PurchasesTable.tsx`
- `web/app/purchases/PurchaseDetailDrawer.tsx`
- `web/app/purchases/PurchaseFilters.tsx`
- `web/app/purchases/PurchaseMetrics.tsx`
- `web/app/purchases/usePurchases.ts`
- `web/app/api/purchases/route.ts`
- `web/app/api/receiving/route.ts`
- `integrations/status_logic.py`
- `integrations/ebay_sync_buyer_purchases.py`
- `run_all_syncs.py`
- existing SQL migrations in `sql/`
- docs: `CURRENT_STATE.md`, `DECISIONS.md`, `ROADMAP.md`, `business_rules.md`, `receiving workflow.md`, `backend_architecture.md`

## Important existing MBOP rules

- `purchase_items.current_status` is backend-owned.
- Workflow-locked statuses include:
  - `cancelled`
  - `listed`
  - `received`
  - `return_opened`
  - `return_pending`
- Carrier/status syncs must not downgrade workflow-owned statuses.
- Receiving owns `received` and `return_pending`.
- Return/refund workflow will own `return_opened` and cancellation/refund follow-up.
- `Return Pending` is separate from `Return Opened`.
  - `Return Pending` means the operator identified a return need, usually during receiving.
  - `Return Opened` means an eBay return/case exists.
- Cancelled items must remain visible to refund follow-up until refund receipt is confirmed.
- Frontend must not recalculate landed cost. Use backend/API-provided values.
- Keep the Purchases page componentized. Do not reintroduce a large page.tsx monolith.
- Do not create a separate Returns left-nav item for this MVP.

## Product decision

Do not build a separate Returns screen.

Modify the existing Purchases -> Order Problems screen so it becomes the unified place for:

1. Existing order problems:
   - past ETA
   - stale/no tracking
   - carrier exception
   - return pending

2. Return/refund workflow:
   - return needed
   - return opened
   - seller message needs response
   - waiting for seller
   - waiting for label
   - label received
   - return shipped
   - seller received return
   - refund pending
   - partial refund offered
   - partial refund accepted
   - missing item / replacement pending
   - missing item received
   - escalation available
   - escalated
   - resolved refunded
   - resolved missing item received
   - closed

Think of current Order Problems criteria as the earliest “problem candidate” state before Return Pending / Return Opened.

Stale tracking rule:
- `no_tracking`, `shipped_no_tracking`, and `awaiting_carrier_scan` are stale only after the order is at least 14 days old.
- The stale-tracking candidate window only looks back 90 days.
- `in_transit` is not stale while the carrier ETA is still in the future.
- A past eBay ETA should not create or keep a derived candidate when a usable tracking number has carrier activity within the last 4 days.
- A past eBay ETA should create or keep a derived candidate when there is no usable tracking number or when carrier activity is older than 4 days.
- Carrier events or statuses that indicate return to sender or another exception should create a `carrier_exception_candidate`, even when the activity is recent.
- Derived stale/late/carrier candidates should auto-close when the purchase no longer matches a candidate rule.

## eBay return types

Use these friendly return type names:

| Internal value | UI label | Meaning |
|---|---|---|
| `not_as_listed` | Wrong Item / Not as Listed | The item is not what was listed |
| `buyer_choice` | Changed Plan / Return Anyway | I got what I ordered but want to return it instead of selling it |
| `missing_items` | Missing Item / Incomplete Order | I did not receive all or part of the order |
| `cancelled_refund_followup` | Cancelled / Refund Follow-Up | Cancelled item still needs refund confirmation |
| `late_delivery_candidate` | Late Delivery Candidate | Order problem candidate that may become a case/return |
| `carrier_exception_candidate` | Carrier Exception Candidate | Shipment has carrier exception and needs review |
| `stale_tracking_candidate` | Stale Tracking Candidate | Tracking is stale/no movement and needs review |

## Key UX decision

The Order Problems table should show a single unified queue. Add filters/chips for:

- All Open Problems
- Candidates
- Return Needed
- Return Opened
- Needs My Response
- Waiting on Seller
- Ready to Ship Back
- Return Shipped
- Refund Pending
- Missing Item Pending
- Escalation Available
- Resolved / Closed

Default view should show open/unresolved problems only.

Sort priority:

1. Needs My Response
2. Overdue next action
3. Escalation Available
4. Refund Pending
5. Return Pending / Return Needed
6. Oldest detected order problems

## Read-only eBay policy

Keep this feature read-only with respect to eBay.

MBOP may:
- read eBay return/case/inquiry data
- store eBay IDs, status, deadlines, action URLs, refund amounts, and raw JSON
- provide links to eBay pages for the operator to act manually
- allow the operator to update MBOP-local workflow state and notes

MBOP must not yet:
- create an eBay return
- send return messages
- accept or decline partial refund offers
- escalate a return/case
- issue refunds
- upload files
- write anything back to eBay

The operator will perform all actions on ebay.com.

## Data reset requirement

A previous process imported legacy returns from a spreadsheet and from eBay. We want to wipe that legacy return workflow data and start fresh, with one exception:

- Preserve all existing `purchase_items.current_status = 'return_pending'`.
- Preserve `cancelled`, `return_opened`, `received`, and `listed` workflow-locked statuses.
- Do not import completed/refunded legacy return history into the new workflow right now.
- If existing supplier return tables contain legacy completed/refunded rows, create a safe cleanup SQL script that deletes only old return workflow rows and does not delete or downgrade purchase_items.
- Existing `Return Pending` items should seed new problem cases.

The current eBay supplier returns sync should remain disabled until the redesigned workflow is implemented.

## Schema requirement

Because this requires schema work, first create a SQL migration file and show the SQL before dependent code work.

Suggested migration name:

`sql/2026-06-02_add_order_problem_return_workflow.sql`

Create new tables rather than overloading `purchase_items`.

Suggested table 1: `order_problem_cases`

Purpose: one persistent workflow row for an item/order problem, including return/refund tracking.

Recommended fields:

- `problem_case_id uuid primary key default gen_random_uuid()`
- `purchase_item_id uuid not null references purchase_items(item_id)`
- `purchase_id uuid references purchases(purchase_id)`
- `supplier text default 'eBay'`
- `supplier_order_id text`
- `problem_source text not null`
  - values: `derived_order_problem`, `receiving_return_pending`, `manual`, `ebay_return_sync`, `ebay_inquiry_sync`, `ebay_cancellation_sync`
- `problem_type text not null`
  - values include `late_delivery_candidate`, `stale_tracking_candidate`, `carrier_exception_candidate`, `return_needed`, `not_as_listed`, `buyer_choice`, `missing_items`, `cancelled_refund_followup`
- `workflow_state text not null`
  - values include:
    - `candidate`
    - `return_needed`
    - `return_opened`
    - `seller_message_needs_response`
    - `waiting_on_seller`
    - `partial_refund_offered`
    - `partial_refund_accepted`
    - `label_pending`
    - `label_received`
    - `return_shipped`
    - `seller_received_return`
    - `refund_pending`
    - `replacement_pending`
    - `replacement_shipped`
    - `replacement_received`
    - `escalation_available`
    - `escalated`
    - `resolved_refunded`
    - `resolved_received_item`
    - `closed_no_action`
    - `closed_no_refund`
      - Use for cases where the item is not recoverable and no refund will be received, such as an eBay return closed because the return shipment was lost or missed the return deadline.
      - This closes the order problem without moving the item back to Received, Listed, or Amazon-bound inventory.
- `priority text`
  - values: `urgent`, `high`, `normal`, `low`
- `is_open boolean not null default true`
- `needs_response boolean not null default false`
- `next_action text`
- `next_action_due_at timestamptz`
- `first_detected_at timestamptz not null default now()`
- `last_detected_at timestamptz`
- `return_needed_at timestamptz`
- `ebay_return_opened_at timestamptz`
- `seller_message_last_at timestamptz`
- `operator_responded_at timestamptz`
- `partial_refund_offered_at timestamptz`
- `partial_refund_accepted_at timestamptz`
- `label_available_at timestamptz`
- `return_shipped_at timestamptz`
- `seller_received_return_at timestamptz`
- `refund_due_at timestamptz`
- `refund_received_at timestamptz`
- `replacement_promised_at timestamptz`
- `replacement_shipped_at timestamptz`
- `replacement_received_at timestamptz`
- `escalation_available_at timestamptz`
- `escalated_at timestamptz`
- `closed_at timestamptz`
- `ebay_return_id text`
- `ebay_inquiry_id text`
- `ebay_case_id text`
- `ebay_return_state text`
- `ebay_return_status text`
- `ebay_current_type text`
- `ebay_action_url text`
- `expected_refund_amount numeric(12,2)`
- `actual_refund_amount numeric(12,2)`
- `partial_refund_amount numeric(12,2)`
- `refund_currency text default 'USD'`
- `replacement_tracking_number text`
- `notes text`
- `raw_ebay_json jsonb`
- `created_at timestamptz not null default now()`
- `updated_at timestamptz not null default now()`

Add uniqueness so there is at most one open case for a purchase item, unless a future design supports multiple separate cases:
- unique partial index on `purchase_item_id` where `is_open = true`

Suggested table 2: `order_problem_events`

Purpose: append-only timeline for all problem/return/refund events.

Recommended fields:

- `problem_event_id uuid primary key default gen_random_uuid()`
- `problem_case_id uuid not null references order_problem_cases(problem_case_id) on delete cascade`
- `event_type text not null`
- `event_source text not null`
  - values: `system`, `operator`, `ebay_api`, `tracking`
- `event_at timestamptz not null default now()`
- `message text`
- `amount numeric(12,2)`
- `currency text`
- `tracking_number text`
- `raw_json jsonb`
- `created_at timestamptz not null default now()`

Add indexes:
- `order_problem_cases(purchase_item_id)`
- `order_problem_cases(workflow_state)`
- `order_problem_cases(is_open, next_action_due_at)`
- `order_problem_cases(needs_response, next_action_due_at)`
- `order_problem_cases(ebay_return_id)`
- `order_problem_cases(ebay_inquiry_id)`
- `order_problem_cases(ebay_case_id)`
- `order_problem_events(problem_case_id, event_at desc)`

## Candidate upsert behavior

Order Problems currently derives rows from criteria like past ETA, stale/no tracking, carrier exception, and return pending.

Enhance the Order Problems API so that when a row qualifies as an order problem, it upserts an `order_problem_cases` row if there is not already an open one for that `purchase_item_id`.

Rules:
- Derived late/stale/exception rows become `workflow_state = 'candidate'`.
- Existing `purchase_items.current_status = 'return_pending'` rows become `workflow_state = 'return_needed'` and `problem_type = 'return_needed'`.
- Existing `purchase_items.current_status = 'return_opened'` rows become `workflow_state = 'return_opened'` if no more specific eBay state is known.
- Existing `purchase_items.current_status = 'cancelled'` rows become `problem_type = 'cancelled_refund_followup'` and should remain open until refund confirmation.
- Preserve `first_detected_at`; update only `last_detected_at` on repeated detection.
- Do not auto-close a case just because the derived condition disappears. Instead mark `last_detected_at` and leave manual close/resolution to the operator unless there is a clearly safe automatic resolution rule.

## Workflow actions in MBOP

Add local-only actions to the Order Problems detail drawer. These actions update MBOP tables only.

Actions:
- Mark Return Needed
- Mark Return Opened in eBay
- Mark Seller Messaged Me
- Mark I Responded in eBay
- Mark Partial Refund Offered
- Mark Partial Refund Accepted
- Mark Label Available
- Mark Return Shipped
- Mark Seller Received Return
- Mark Refund Pending
- Mark Refund Received
- Mark Missing Item / Replacement Pending
- Mark Missing Item Received
- Mark Escalation Available
- Mark Escalated in eBay
- Close / Resolve

When appropriate, update `purchase_items.current_status`:
- Mark Return Needed -> `return_pending`
- Mark Return Opened -> `return_opened`
- Mark Refund Received for a full refund/no inventory retained -> likely `cancelled` or a future resolved return status; do not invent if existing status vocabulary cannot support it.
- Mark Missing Item Received -> move item back to `received` only when the operator explicitly confirms the missing item is now received and the item is ready for normal inventory flow.
- For partial refunds where item is kept, do not automatically adjust multi-item costs. Store refund info first; cost adjustment should be a controlled later step or explicit operator action.

## eBay API sync

Add a read-only integration script, for example:

`integrations/ebay_sync_order_problem_returns.py`

Use eBay Post-Order API read endpoints only.

Target capabilities:
- Search returns.
- Get return details.
- Get return tracking.
- Search INR/item-not-received inquiries for Type C style cases.
- Search cases if available.
- Store raw payloads.
- Map eBay return IDs, inquiry IDs, case IDs, cancellation IDs, states,
  statuses, buyer action URLs, due dates, escalation eligibility dates, seller
  make-it-right dates, estimated refund amount, actual refund amount,
  replacement tracking, and return tracking status into `order_problem_cases`.
- For INR inquiries, call `GET /post-order/v2/inquiry/{inquiryId}` after
  `inquiry/search`; the search summary does not include every seller action
  date or seller-provided replacement tracking field needed by MBOP.
- Append material changes to `order_problem_events`.

Important: do not call any eBay POST/write endpoint in this MVP.

Map eBay states conservatively:
- `RETURN_REQUESTED` -> `return_opened`
- `WAITING_FOR_RETURN_LABEL` or `RETURN_LABEL_REQUESTED` -> `label_pending`
- `READY_FOR_SHIPPING` -> `label_received`
- `ITEM_SHIPPED` -> `return_shipped`
- `ITEM_DELIVERED` -> `seller_received_return`
- `PARTIAL_REFUND_REQUESTED`, `PARTIAL_REFUND_INITIATED`, `LESS_THAN_A_FULL_REFUND_ISSUED` -> partial refund states as appropriate
- `ESCALATED` -> `escalated`
- `CLOSED` -> only close automatically if refund/item resolution can be confidently identified; otherwise leave open for manual review
- Unknown/new states should be preserved in `ebay_return_status` and `raw_ebay_json`, and mapped to a safe `waiting_on_seller` or `return_opened` fallback.

## UI detail drawer

Modify the existing Order Problems detail view rather than creating a new screen.

Show:
- Problem summary
- Item title, system, ASIN, purchase price, quantity
- eBay order link
- eBay listing link if available
- Return, inquiry, or cancellation/order detail link if available
- Current MBOP workflow state
- Current eBay return/inquiry/case status
- Return type selector
- Next action
- Next action due date
- All captured dates
- Refund expected / actual
- Partial refund amount
- Replacement/missing-item tracking
- Notes
- Timeline from `order_problem_events`
- Link/button to open eBay return/case/action URL if available; avoid showing
  duplicate links when the table already exposes the detail link.

## Table columns

Update Order Problems table columns to support both problems and returns:

- Priority
- Issue
- Due / Age
- Order ID
- Item
- System
- Status
- Next Action
- Refund Expected
- Refund Received
- Tracking / ETA
- Details drawer button

The Order ID cell should link the order number to the eBay order page and show
a secondary Return/Inquiry/Cancellation Details link when MBOP has a case URL or
identifier. Notes belong in the drawer, not the dense table.

Keep it dense and operational. This is not a card UI.

## API routes

Recommended API structure:

- Extend existing purchases/order-problems API if one exists.
- Otherwise create:
  - `web/app/api/order-problems/route.ts`
  - `web/app/api/order-problems/[id]/route.ts`
  - `web/app/api/order-problems/[id]/events/route.ts`
  - `web/app/api/order-problems/[id]/actions/route.ts`

API should own filtering, sorting, pagination, and summary counts. Do not reintroduce full-table client-side filtering for this workflow.

## Refresh / freshness

Update `/api/screen-data-freshness` so Order Problems reflects the latest relevant source:
- latest order problem case update
- latest eBay return sync
- latest eBay buyer purchase sync / EasyPost tracking sync if relevant

## Validation

After implementation, run:

PowerShell:

```powershell
git status
cd C:\Dev\amazon-ebay-ops-system
python -m compileall integrations
cd web
npm run build
```

Also validate:
- Existing purchases page still loads.
- Existing normal purchases table still works.
- Receiving can still mark items `Return Pending`.
- eBay buyer purchase sync does not downgrade `return_pending`, `return_opened`, `cancelled`, `received`, or `listed`.
- Order Problems shows existing past-ETA/stale/no-tracking/carrier exception rows.
- Existing `Return Pending` rows appear as Return Needed.
- Closed/refunded legacy return data is not reintroduced.
- No eBay write endpoints are called.

## Git checkpoint

Before coding:
- run `git status`
- commit the current stable state
- create a focused branch such as `feature/order-problems-returns`

After schema migration:
- commit SQL migration separately if practical

After API/data model:
- commit backend/API changes

After UI:
- commit frontend changes
