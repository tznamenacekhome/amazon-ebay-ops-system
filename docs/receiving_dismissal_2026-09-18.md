# Receiving dismissal and order correction — September 18, 2026

## Cause and change

Receiving's single-result auto-open effect compared the selected row with the
matching search result. Closing cleared selection, so the effect immediately
reopened that same row. Missing ASIN validation made the operator appear trapped.

Commit `7e385e96f2c4` records explicit dismissal for the current search. Cancel,
X and Escape discard drafts without saving, regardless of validation. Delayed
scan results cannot reopen the dismissed screen. A changed search or explicit
row click can open detail again. The X control now has an accessible name.
The general no-save dismissal requirement is also recorded in `AGENTS.md`.

## Authorized receiving correction

Order `23-15127-96456`, item `298b45e2-56fa-447c-8e74-ac1bfb060c63`:

- Verified exact game/platform against received order `11-15144-05293`:
  Ghost Recon Breakpoint, Xbox One, Sentinel Corp Pack supplier title.
- ASIN `B07RP42TMG`; Amazon title populated; sell price `34.98`.
- Quantity **1**, marketplace **Amazon**, status **received**, date **2026-09-18**.
- Acquisition unit cost remains **13.99**; the comparison order is unchanged.
- Receiving audit note records that this copy arrived in the same package as
  order `11-15144-05293`, with two copies in that package.

The existing receiving POST handler ran with its existing admin-token
authentication inside a one-off ECS task using the production web159 image and
production configuration. Task `9a7a46f415e9467782e7ac744fade180` exited zero.
It used the normal receiving outcome/audit workflow and triggered the ordinary
ASIN-scoped pricing refresh. No direct status SQL or bulk purchase update was
used. A separate Supabase read verified the item and audit outcome. The temporary
operator task definition was deregistered after completion.

## Validation and release

- Actual-page hook/effect regression test passes for Cancel, X, Escape, missing
  ASIN, delayed scan responses, explicit reopening, discarded draft edits and
  zero POSTs during dismissal.
- Existing tracking-scan tests pass.
- Docker production build and TypeScript checks pass.
- Exact production image contains the new close control in receiving chunk
  `13hjxzcbn.~tb.js`, SHA256
  `6ce51d897b5561952ce5ba6a4ef086e107288f4b0a055b9ac8f6181d885554c3`.
- Web revision **160**, source `7e385e96f2c4`, image digest
  `sha256:558434e33b4b3266e2c2d28479ccb2c93fa9333747173df990c764dde0290f66`.
- AWS rollout **COMPLETED**, sole deployment web160, one running task, and
  the exact new load-balancer target verified healthy.
- Scheduler definitions and cadence were not changed by this receiving fix.

Authenticated browser interaction was unavailable: the browser tool reported no
available browsers and could not create an in-app browser. Public asset access
redirects to Cognito. Therefore the interactive close paths are regression-tested
locally; AWS rollout/target health and the production receiving data mutation are
verified separately. An already-open user tab needs a refresh to load the fix.

Local task, readback, audit and runtime evidence: `tmp/receiving-close-20260918/`.
