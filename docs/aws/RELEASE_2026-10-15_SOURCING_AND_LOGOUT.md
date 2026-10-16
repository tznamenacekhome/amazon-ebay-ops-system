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

## Deployment receipt

Application commit: `86952d6d42d5`, pushed to `origin/main`.

- Web: `mbop-web-task:187`, pinned image `sha256:da0aed8e723991e42296b171b6a45dc4f8b6b0e22a7d53574252e3ef9c9bf871`. `deploy-web.ps1` completed successfully. At 19:27 Pacific October 15, ECS reported deployment COMPLETED, desired/running 1, pending 0; `aws-web-status.ps1` confirmed both build variables equal `86952d6d42d5`.
- Scheduler: `mbop-scheduler-task:143`, pinned image `sha256:6f1042e5090ec3a9f064f114bf6f970601d8a09ae6981f1e38e7c4c6c8c1a404`. Deployment used revision 142 as the base and changed only `mbop-sourcing-catalog`. Live schedule inspection confirmed ENABLED, `cron(10 0 ? * * *)`, America/Los_Angeles, with launch input pointing to revision 143 and `python run_all_syncs.py --group sourcing-catalog`. `CLOUD_DEPLOYMENT=true` and `LOCAL_SYNC_ENABLED=false` remain set. The image's read-only `--group sourcing-catalog --list` smoke test exited 0 and showed discovery without weekend arguments. No sync was launched and no completed production sync is claimed.
- Logout infrastructure: live Cognito configuration includes `/signed-out`; the ALB has an exact `/signed-out` forward rule. Existing configuration required no mutation.
- Authenticated production browser: build badge `86952d6`; Business Excluded tab absent. Closest Excluded has three selectors (cycle, exclusion reason, inventory), no per-row Review match / Dismiss buttons, and reason/evidence-only explanations. Cycle 99 loaded 11 rows, versus 84 in latest-run mode; no API error appeared. Visible examples identify the recorded core-game difference, including Amazon Minecraft versus eBay Minecraft Story Mode Season Pass Disc. This verifies the UI/backend path; regression fixtures verify pair identity boundaries and history filtering independently.
- Coverage Cycle browser view shows Calls Last Run, Quota After Run, Recorded quota reset, and the last-run explanation.
- Browser logout test: Log out reached Signed out of MBOP, remained there after reload without automatic login, and displayed no operational shell. Clicking Sign in returned to the authenticated Purchases screen. Cookie contents were not inspected.

This receipt is a documentation-only follow-up; the application image remains tied to the application commit above.
