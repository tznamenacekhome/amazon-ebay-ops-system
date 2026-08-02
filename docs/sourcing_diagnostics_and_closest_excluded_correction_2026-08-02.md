# Sourcing Diagnostics And Closest Excluded Correction

Date: 2026-08-02

Scope: correct the sourcing dismiss diagnostics presentation and enforce the
operator definition of Closest Excluded.

Out of scope: matching-rule changes, profitability/ROI changes, seller
threshold changes, search behavior, quota behavior, production rescoring,
marketplace writes, and unrelated shipment-sync work.

## Root Causes

Normal Replenishment dismissals reused the new diagnostics dialog but initialized
it collapsed. Operators had to click `Matching Diagnostics`, so diagnostics were
available but not part of the default single-row dismiss workflow.

Closest Excluded filtered mostly on opportunity status plus stored diagnostics.
It did not have an authoritative pre-rank gate for presentation/action history,
and it did not exclude `watching` status rows. The UI also rendered presentation
badges in every table mode, so any returned row with presentation metadata could
display `Previously Presented` in the Closest Excluded tab.

## Production Audit Before Code Change

Read-only audit of the current API-equivalent query:

- latest sourcing runs considered: 1
- raw rows read: 621
- qualifying before limit: 549
- rows returned: 50
- statuses returned: 44 `rejected`, 6 `watching`
- exact opportunity batch membership: 0
- exact opportunity action rows: 0
- previously purchased: 0
- watched actions: 0
- dismissed actions: 0
- marked-valid/confirmed actions: 0
- true never-presented/no-action by exact opportunity id: 50

Interpretation: the screenshot symptom could occur because the API/UI did not
enforce the operator-facing invariant before rendering. The current live top 50
also showed a separate violation: `watching` rows were eligible for Closest
Excluded because only a smaller terminal-status list was excluded.

## API Corrections

`GET /api/sourcing/opportunities?scope=closest_excluded` now builds a dedicated
Closest Excluded context before ranking:

- presentation metadata from `sourcing_opportunity_batch_items`
- operator actions from `sourcing_actions`
- same-ASIN/same-eBay-listing keys already represented in any opportunity batch

Rows are excluded before ranking when they are:

- ever presented by opportunity id
- actioned as watch, purchased, dismiss, block ASIN, mark valid, confirm
  exclusion, or seller listing mismatch
- in a presented listing identity key for the same ASIN/eBay listing
- status `watching`, `purchased`, `purchased_pending_match`, `dismissed`,
  `matched_to_purchase`, `completed`, confirmed, or ROI snoozed
- obvious low-value exclusions already filtered by the prior implementation

Closest Excluded still uses backend ranking and remains capped at 50.

## UI Corrections

Single-row Replenishment dismissal now opens the wide two-column dialog with
diagnostics visible immediately.

When exactly one selected row is dismissed, the workflow routes to the same
single-row dialog so diagnostics are visible and feedback can be saved against
that row. Multi-select dismissal stays compact and does not show one row's
diagnostics as if they applied to all selected rows.

Closest Excluded no longer renders presentation-count badges or `Previously
Presented` metadata in the operator-facing table.

## Diagnostic Evidence Population

The backend diagnostic comparison now fills Amazon-side values from the best
available backend evidence:

- Amazon title
- seed/system diagnostics
- ASIN
- Amazon image/context
- edition and region diagnostic fields
- expected physical resale status
- expected standard physical package contents

React still renders backend-provided comparison JSON only and does not derive
matching logic.

## Verification

Corrected read-only production audit of the new eligibility rules:

- rows returned: 50
- qualifying before limit: 543
- statuses returned: 50 `rejected`
- returned rows with batch membership: 0
- returned rows with operator actions: 0
- returned `watching` rows: 0
- returned open/Replenishment overlap: 0
- returned new-this-run batch overlap: 0

Local validation:

```powershell
Set-Location C:\Dev\amazon-ebay-ops-system\web; npx.cmd eslint app/api/sourcing/diagnosticComparison.ts app/api/sourcing/opportunities/route.ts app/sourcing/page.tsx
Set-Location C:\Dev\amazon-ebay-ops-system\web; npm.cmd run build
```

Both passed.

## Files Changed

- `web/app/api/sourcing/diagnosticComparison.ts`
- `web/app/api/sourcing/opportunities/route.ts`
- `web/app/sourcing/page.tsx`
- `docs/sourcing_diagnostics_near_miss_receiving_feedback_2026-08-02.md`
- `CURRENT_STATE.md`
- `DECISIONS.md`
- `KNOWN_ISSUES.md`
- `docs/MBOP_Sourcing_Workspace_Architecture.md`

## Caveats

No production rows were rescored or modified by the audits. Production UI
behavior still needs final verification through the Cognito-protected app after
deployment.
