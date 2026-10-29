# Receiving HTML/session response recovery — October 28, 2026

Receiving previously parsed totals responses as JSON without checking whether
the server returned HTML, exposing `Unexpected token '<'` on a sign-in or
unavailable page. Queue, scan, cover-image and receipt-save fetches also lacked
consistent redirect handling. A fresh authenticated production session loaded
without this error; the exact historical HTML response could not be recovered,
so an expired session versus transient gateway error is not conclusively known.

The new receivingRequest transport uses manual redirects, identifies sign-in
responses and HTML (including bodies with missing/incorrect Content-Type),
and gives readable recovery messages. Queue/totals expose Reload / sign in.
Scan errors now surface in the page. Failed queue reads show unavailable rather
than claiming there are no receiving candidates. GET network/body interruptions
retry once; HTTP failures and auth redirects are not retried. POST saves never
replay, and interrupted saves tell the operator to reload and inspect the item
before trying again. Structured API errors and empty responses are preserved.

TypeScript, transport fixtures, dismissal and tracking-scan regression checks
passed. The dismissal fixture now uses a real Response to exercise the actual
transport contract. No inventory mutation is needed for verification. Auth
failure scenarios are tested with injected transport responses, without
expiring the operator's live session. No schema or scheduler change is needed.
Focused lint reports two existing set-state-in-effect errors in unchanged
Receiving page effects (scan reset and selection reset); the new transport and
other changed components have no reported lint errors.

Deploy with scripts/deploy-web.ps1, confirm stable ECS state with
scripts/aws-web-status.ps1, then verify authenticated production Receiving.
The SQL file for the earlier one-unit Ice Age routing adjustment is recorded
in a separate audit commit; it is not applied again by this release.

## Deployment receipt

- Application commit `463e140afb33`, pushed to origin/main.
- ECS web task revision `192` replaces `191`.
- ECR digest `sha256:8c07ed87f44e6e533a3d20e63712bda2d067931bf05e4d3cc35785c032b0d5c5`.
- Production Docker build passed compilation, TypeScript and page generation.
- ECS services-stable waiter passed; one running task, zero pending.
- Authenticated browser confirmed build `463e140` and successful Receiving
  queue/totals loads. The page's Refresh button completed without HTML/JSON
  errors. Current production result was zero units and no receiving candidates.
- No receipt save, provider sync, inventory update, or schema change was made.
- Expired-session/HTML/interrupted-save behavior was verified with transport
  fixtures; the operator's live authentication session was not invalidated.
