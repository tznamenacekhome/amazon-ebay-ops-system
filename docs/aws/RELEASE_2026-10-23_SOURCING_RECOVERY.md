# Sourcing request recovery — October 23, 2026

## Scope

The operator confirmed release of the five sourcing files held during the
October 22–23 overnight review. The checkout contained exactly those files;
supported task status showed no competing active MBOP checkout worker.
This release adds the request helper and tests, updates the resource cache and
its tests, and connects the sourcing page's single/bulk review requests and
recovery links. No backend, schema, permission, credential or scheduler change
is required. Existing authentication remains enforced by ALB/Cognito.

## Behavior

- Sourcing reads retry once after a network error or interrupted response body,
  unless their signal has already aborted. HTTP/API failures are not replayed.
- Fetch uses manual redirect handling. Opaque login redirects, HTTP 401/302,
  and HTML responses produce a readable sign-in/reconnect message instead of
  an opaque CORS error or an HTML-as-JSON parser error.
- Review saves are never automatically replayed. When their response is lost,
  the message explains that the change may have saved and asks the operator to
  reload and inspect the opportunity before retrying. Bulk actions stop on the
  existing error path; no workflow action is submitted by validation.
- Structured API error status/body and response headers are retained. Empty
  204/205/304 responses keep their status without constructing an invalid body.
- Session/network recovery messages consistently expose the page's existing
  Reload / sign in link. Cache invalidation, request coalescing and focus
  freshness behavior retain their existing rules.

## Validation

Passed on October 23 before commit:

```text
node web/app/sourcing/sourcingRequest.test.mjs
node web/app/sourcing/sourcingResourceCache.test.mjs
node web/app/sourcing/MatchingReviewControls.test.mjs
git diff --check
cd web
npx eslint app/sourcing/sourcingRequest.ts app/sourcing/sourcingResourceCache.ts app/sourcing/page.tsx
npm run build
```

Lint exited 0, with ten unused-symbol warnings in unchanged portions of page.tsx;
no lint errors. The production Next.js build, TypeScript checks and static-page
generation passed. Transport fixtures verify bounded GET retry, response-body
retry, aborted requests, redirect/401/HTML handling, structured API errors, empty
responses, and no replay of POST saves. Existing cache and review-control tests
passed. These are controlled failure tests, not a live session-expiration claim.

The supported browser interface permits DOM interaction but does not expose
network interception or session-cookie editing. Therefore expired-session and
lost-save-response scenarios are tested with injected transports, without
expiring the operator's live session or submitting production mutations.

## Delivery and rollback

Commit/push the five authorized files and this release document. Deploy the web
image using scripts/deploy-web.ps1 from a clean checkout, then confirm stable
ECS state with scripts/aws-web-status.ps1 and authenticated production browser
verification. Verify the new build label, Sourcing tabs and a page reload.
No provider jobs or operational actions are needed. Rollback by redeploying the
previous web revision 188; no database rollback is required.

## Deployment receipt

Application commit `12e16c0e5d8c` was pushed to origin/main and deployed from the
clean checkout with scripts/deploy-web.ps1. Docker's production build also passed.
The helper completed its service-stability wait successfully.

- Task definition: `mbop-web-task:189`.
- Image: `sha256:d735ca4988721aa1a85debc7625ff5f7263302676b2957275b3cbc67950ff3d5`.
- At October 23, 07:35:48 Pacific, ECS reported deployment COMPLETED and steady
  state. scripts/aws-web-status.ps1 confirmed desired/running 1/1, pending 0,
  with both build variables `12e16c0e5d8c`. The new ALB target was healthy;
  the retired revision's target was draining normally.
- Authenticated Chrome verification at the production Sourcing URL showed the
  exact new build after a full page reload. Buy List loaded 11 actionable rows,
  Coverage Cycle rendered cycle 115 and its buckets/history, and Closest
  Excluded loaded 58 rows. Returning to Buy List retained the expected 11 rows.
  No JSON/login error appeared and the browser error log was empty.
- No operational action, provider job, or save was submitted. Session-expiry,
  interrupted POST and retry guarantees remain controlled-test results, as
  explained above; no live cookie-expiration or lost-save test is claimed.

This was a web-only deployment. No scheduler, other service, schema, credentials,
permissions or application dependency files were changed. The Docker install
reported dependency audit findings from the existing lockfile; dependency
remediation was not part of this scoped request-recovery release.

The documentation-only receipt is committed/pushed separately and does not
require another image build. The held October 22–23 batch is now released;
there is no remaining release blocker.
