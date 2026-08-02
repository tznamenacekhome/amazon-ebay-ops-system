# Closest Excluded Reason Display

Date: 2026-08-02

Scope: display backend-owned exclusion explanations for every row in the
Sourcing `Closest Excluded` tab.

Out of scope: matching-rule changes, ranking changes, profitability/ROI
changes, production rescoring, status changes, marketplace writes, search/quota
changes, and unrelated shipment work.

## Production Audit Before Implementation

Read-only audit of the current 50 `Closest Excluded` rows:

- rows returned: 50
- rows with a clear stored exclusion diagnostic: 0
- rows with multiple exclusion diagnostics: 0
- rows where status is the only exclusion cause: 48
- rows with missing or ambiguous exclusion cause: 48
- rows with historical positive-match supporting signals: 24
- rows with no hard block, blocked flag, or warning: 24

Distribution by stored reason class:

| Reason class | Count |
|---|---:|
| `status_rejected_without_block` | 48 |
| `profitability` | 1 |
| `review_threshold` | 1 |

The valid-looking rows are not being hidden by a visible current hard block.
They are `rejected` opportunities whose stored diagnostics often say `Strong
Match` or `Probable Match`; 24 also have historical positive title/system
signals. This points to stale or earlier-run eligibility/status decisions, not a
new deterministic matching rule.

## API Shape

`GET /api/sourcing/opportunities?scope=closest_excluded` now returns
`exclusionReason` as an object:

```json
{
  "code": "status_rejected_without_block",
  "label": "Rejected before presentation",
  "summary": "Status is rejected, but stored diagnostics do not include a mapped exclusion rule.",
  "source": "opportunity_status",
  "severity": "other_eligibility_gate",
  "category": "other eligibility gate",
  "diagnosticKeys": ["final_recommendation", "confidence_summary", "opportunity_context"],
  "finalRecommendation": "Strong Match",
  "finalStatus": "rejected",
  "secondaryReasons": [],
  "supportingSignals": ["Historical positive title/system match", "Strong Match"]
}
```

Unknown reasons are explicit:

- `code`: `unknown`
- `label`: `Unknown - inspect diagnostics`
- `source`: `unknown`

## Priority Order

Primary reason derivation is deterministic. The first matching reason wins:

1. historical exact negative
2. different Game Name
3. numeric installment/identity mismatch
4. wrong platform
5. unsupported platform
6. edition/version conflict
7. digital/service listing
8. accessory/not-game
9. incomplete product
10. region/location conflict
11. unavailable listing
12. seller policy
13. probable non-match
14. other hard block
15. profitability
16. review threshold
17. rejected status without a mapped block
18. unknown

Supporting signals may include non-exclusion evidence, such as historical
positive-match hints, but only hard blocks, blocked flags, warnings, and final
recommendation text select the primary reason.

## UI Behavior

Closest Excluded rows now show a compact `Excluded Because` block in the table:

- primary reason label
- short summary
- severity badge
- source and final recommendation/status
- `+N more` when secondary reasons exist

`Open Diagnostics` shows a highlighted primary reason panel and highlights the
diagnostic rows referenced by `diagnosticKeys`.

## Validation

Local validation:

```powershell
Set-Location C:\Dev\amazon-ebay-ops-system\web; npx.cmd eslint app/api/sourcing/opportunities/route.ts app/sourcing/page.tsx app/sourcing/types.ts
Set-Location C:\Dev\amazon-ebay-ops-system\web; npm.cmd run build
```

Both passed before commit.

Production verification:

- ECS web rollout completed on task definition `mbop-web-task:103`.
- Protected production root returned the expected Cognito `302` auth redirect.
- Read-only production audit after deploy returned 50 current Closest Excluded
  rows with reason objects, 0 missing reasons, and 0 unknown reasons.

## Caveats

This change intentionally does not rescore or change statuses. Because the
current top 50 have no mapped exclusion diagnostic, the UI will surface them as
`Rejected before presentation` until a separate operator-approved investigation
decides whether those rows should be rescored, reopened, or left as historical
near misses.
