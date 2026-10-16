# October 15, 2026 release: sourcing review and logout

## Included changes

- `web/app/api/sourcing/opportunities/route.ts`: when a coverage cycle is selected in Closest Excluded, exclude an ASIN/eBay listing pair recorded in an earlier cycle, even when its opportunity ID differs. Compare listing identities before reason counts, search, inventory filtering, ranking, and the display limit. History queries use current ASIN batches, paginated identity columns, and earlier run timestamps; latest-run mode retains its existing behavior. Existing Buy List presentation and operator-action suppression remains in place.
- Exclusion explanations use persisted conflicting/review identity fields to name the Amazon and eBay values, then relevant failed decision-trace summaries or supporting signals when available. List mode hydrates parsed identity evidence only for visible exclusions; it does not expand raw provider payloads for the full candidate set. Missing historical evidence remains explicit rather than inventing a mismatch.
- `web/app/sourcing/page.tsx`: remove the Business Excluded tab and suppression-record panel. On Closest Excluded, remove listing-type and source selectors and force both query values to all so hidden selections from another tab cannot restrict results. Remove the per-row Review match / Dismiss button on that screen; selection/bulk actions remain available. Excluded Because displays only its reason and supporting explanation, without severity, secondary-reason count, source, or final-status badges.
- Coverage Cycle metrics now say Calls Last Run, Quota After Run, and Recorded quota reset, with text explaining that these are last-run values.
- `integrations/run_daily_sourcing_discovery.py` and `run_all_syncs.py`: run sourcing every day, including weekends. Remove the weekend guard and its timezone/skip arguments. Rename the bounded pass setting to `--max-daily-passes` while retaining `--max-weekday-passes` as an alias; retain quota checks and the five-pass default.
- `web/app/api/logout/route.ts`: redirect through Cognito to `/signed-out`, mark the route dynamic and uncached, and expire ALB authentication cookies with secure/HTTP-only flags.
- `web/app/signed-out/page.tsx` and `web/app/AppShell.tsx`: provide a static signed-out landing page with explicit Sign in navigation; hide the operational shell and stop notification polling there.
- `scripts/configure-signed-out.py`: plan/apply the exact public `/signed-out` ALB path and Cognito allowed logout URL, verifying account 297464765814 and preserving existing client configuration.
- `docs/aws/LOGOUT_RECOVERY_2026-10-11.md`: preserve the previous recovery investigation, scheduler/web rollout evidence, and remaining browser verification caveat. The Python weekend regression tests, sourcing API tests, and review UI test expectations cover the changed behavior.

## Validation

- Local production Next.js build and TypeScript checking passed.
- `python -m unittest tests.test_daily_sourcing_schedule`: two tests passed with provider calls mocked; no discovery/sync was launched.
- `node web/app/api/sourcing/closestExcludedFilter.test.mjs`: passed cycle pair suppression, pair boundaries, full-result counts/filtering before limit, latest-run behavior, review persistence, and concrete mismatch explanations.
- `node web/app/sourcing/MatchingReviewControls.test.mjs`: passed dialog/selection actions, dismissal, correction payloads, and queue choices.
- `node web/app/api/sourcing/businessExclusion.test.mjs`: passed the retained backend compatibility contract, including its expected changed-row error path.
- No schema migration or operational database data change is part of this release. Earlier operator-directed order corrections and manual match memory are database records, not uncommitted source changes.

## Deployment and verification

Use `scripts/deploy-web.ps1` from the committed clean tree, then `scripts/aws-web-status.ps1`, and verify the authenticated production sourcing screen in the browser. The local build alone does not establish production success.

Preflight on October 15 found web revision 186 healthy with its prior dirty-build recovery image and sourcing scheduled daily at 00:10 America/Los_Angeles. The October 11 recovery notes record scheduler revision 142 already deployed with the weekend correction. Inspect the actual schedule launcher task reference before deciding whether a scheduler rollout is necessary. Do not launch a broad sourcing run as a deployment check.

The signed-out helper can inspect/configure the existing logout infrastructure. Its October 11 application is documented in the recovery notes; verify live configuration rather than broadening public routes.

Post-deployment evidence will be recorded in a follow-up deployment receipt.
