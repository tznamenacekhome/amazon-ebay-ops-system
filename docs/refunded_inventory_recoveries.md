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

## Production receipt — October 24, 2026

- Feature commit `158ca0d` pushed to origin/main. Migration `20261024204208`
  applied using reconciled migration list, single-file dry-run and linked db
  push. The shared local/remote ledger now matches, including College Planner.
- CLI reported a pg-delta catalog-cache certificate-path warning after applying
  the migration; the schema objects and remote migration ledger were verified
  successfully. No migration repair or direct schema application was used.
- Targeted adjustment created recovery `5c582ccc-761b-4ce1-bb29-279bce3a5749`
  for item `95f098c4-66b6-45dc-9cef-e5622f328819` and its original refund case.
  Original unit cost and confirmed refund are both $26.07; operational cost is
  $0, quantity one, status Delivered, warehouse received_date unset. One recovery
  event exists; the original problem remains resolved_refunded and closed.
- Original open package now has expected one, received zero, and verification
  false. This removes the old wrong-item quantity from the remaining-unit check.
- Authenticated production Purchases search and Receiving search for
  23-15229-99266 both showed one Delivered row at $0. Receiving Detail showed
  expected remaining one, ASIN B08PMRRN7K, sell price $62.98, and enabled Received.
  No Receiving save or FBA shipment action was submitted during verification.
- Restored this item's original eBay listing-photo metadata using the bounded
  exact-item repair. No provider sync or broad backfill was launched.
- Disposable PostgreSQL regression tests passed. Production privilege checks
  confirmed anon cannot read the recovery table, authenticated cannot execute
  the RPC, and service_role can execute it. Security advisor's no-policy info
  for this server-only table is intentional; no client policies/grants exist.
- No web or scheduler deployment is necessary: the database transaction and
  trigger are live, and existing APIs/UI consume the corrected source fields.
