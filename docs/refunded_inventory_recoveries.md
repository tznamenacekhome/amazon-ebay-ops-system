# Refunded inventory recoveries

MBOP supports a fully refunded purchase for which the operator also retained a
usable item or received the correct replacement. The existing purchase item is
reused, so inventory and FBA export quantities are not duplicated. This is an
operational inventory adjustment; the supplier order's original total remains
unchanged. No ZFI or personal finance data is read or modified.

## Database contract

`public.purchase_item_refund_recoveries` retains original unit cost, quantity,
full refund amount/currency, source problem case, resolution, notes and the
time the operator reported possession. It is RLS-enabled and server-only.
Resolution values are `refunded_replacement_received` and
`refunded_item_retained`. Partial refunds and mixed-quantity outcomes are outside
this workflow. Use the normal receiving/problem split workflows first.

The service-role-only, security-invoker RPC
`public.mbop_record_refunded_inventory_recovery` validates that the item and
closed, confirmed-refunded case belong together, then atomically records the
recovery, fills the normalized actual refund, logs one problem event, sets the
item's authoritative unit cost to zero with manual override enabled, and
restores Delivered status for Receiving. Original outlay is retained in the
recovery record; do not subtract the refund from the zero net cost again.

The operator possession report is distinct from warehouse verification. The RPC
does not set Received or received_date, invent a historical arrival date,
change ASIN/sell price, or create an FBA shipment. An original package link
marked Return Pending is reopened, and open/return-pending package quantities
from the wrong item are cleared for correct-item verification. Existing Receiving and
Amazon FBA paths then set Received and Listed normally.

A database trigger protects zero cost and prevents stale shipment/return sync
from removing recovered inventory. A separate new open order-problem episode
still permits a genuine new return. Explicit Return Pending remains available.
Replaying the RPC returns the existing recovery without duplicating units or
events, and never resets Received/Listed. Conflicting retries are rejected.
The recovery audit is append-only to the application service role; corrections
require a separately reviewed backend adjustment.

## Applying and verifying

The schema migration is
`supabase/migrations/20261024204208_mbop_refunded_inventory_recoveries.sql`.
Follow the shared migration ledger rules: migration list, reconcile all owners,
dry-run, then db push from MBOP. No College Planner objects change.

The explicit first adjustment is committed in
`sql/2026-10-24_record_story_of_seasons_refunded_replacement.sql` for order
23-15229-99266. Apply only to MBOP production `froeucjkcepuhgwisped` after the
migration. Verify one item, zero unit cost, Delivered, a closed refund case with
$26.07 actual refund, one recovery record, one recovery event, and visibility in
the authenticated Purchases and Receiving screens. Leave receiving and FBA
actions to the operator.

Disposable PostgreSQL regression fixtures live in
`tests/refunded_inventory_recovery.sql` and
`tests/refunded_inventory_recovery_assertions.sql`. Concatenate the fixture,
migration, and assertions into an isolated PostgreSQL 17 database. They verify
full-refund validation, audit preservation, sync replay protection, Received and
Listed progression, idempotency, new return episodes, and client access denial.
Never load the fixture table definitions into production.
