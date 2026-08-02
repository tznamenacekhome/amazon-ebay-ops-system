# Sourcing Rejection Decision Trace and Reprocess

Date: 2026-08-02

## Purpose

Closest Excluded rows need a durable backend explanation for why MBOP screened them out. The prior UI could infer a display reason from status and diagnostics, but many historical rows only showed `status_rejected_without_block`.

This change persists a first-class `presentationDecision` and `decisionTrace` inside `sourcing_opportunities.matching_diagnostics_json`.

## Stored Shape

`presentationDecision` contains:

- `eligible`
- `finalStatus`
- `finalOpportunityType`
- `finalRecommendation`
- `primaryReason`
- `secondaryReasons`
- `evaluatedAt`
- `ruleVersion`

`decisionTrace` contains ordered checks with:

- `stage`
- `diagnosticKey`
- `result`
- `summary`
- `reasonCode`

## Scope Boundaries

This change does not add matching rules, broaden matching, reopen rejected rows, change purchase/shipment workflow state, call eBay Browse/Search, or change marketplace actions.

The reprocess script rescored stored candidates against the current local rule set only to rebuild diagnostics. Its write path updates only:

- `matching_diagnostics_json`
- `updated_at`

## Reprocess Command

Dry-run:

```powershell
.\.venv\Scripts\python.exe integrations\reprocess_recent_rejected_sourcing_decisions.py --limit 500
```

Write diagnostics only:

```powershell
.\.venv\Scripts\python.exe integrations\reprocess_recent_rejected_sourcing_decisions.py --limit 500 --write
```

Artifacts are saved under `tmp/sourcing_rejected_decision_trace_<mode>_<timestamp>.json`.

## 2026-08-02 Production Reprocess

Dry-run artifact:

- `tmp/sourcing_rejected_decision_trace_dry_run_20260802203535.json`

Write artifact:

- `tmp/sourcing_rejected_decision_trace_write_20260802203556.json`

Post-write readback artifact:

- `tmp/sourcing_rejected_decision_trace_dry_run_20260802203701.json`

Result:

- 500 rejected rows in scope
- 500 rows received a persisted decision trace
- 0 rows would become presentation-eligible under current rules
- 0 rows remained generic/missing after write
- primary reasons after write: 365 `profitability`, 133 `duplicate_history`, 2 `numeric_installment_mismatch`

## UI Behavior

The Sourcing Closest Excluded table and diagnostics drawer now prefer persisted `presentationDecision.primaryReason` and `decisionTrace`. Older rows without persisted payloads still use the legacy API fallback.
