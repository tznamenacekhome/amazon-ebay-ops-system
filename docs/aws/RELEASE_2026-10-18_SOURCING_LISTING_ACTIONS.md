# Sourcing listing actions and cost labels — October 18, 2026

## Scope and provenance

The operator authorized reviewing, documenting, committing, pushing and deploying
the previously preserved sourcing edits. At task start those were exactly:

- Modified `web/app/api/sourcing/opportunities/route.ts` and
  `web/app/sourcing/page.tsx`.
- Untracked `web/app/api/sourcing/actionedListings.ts` and its test.

The implementation and existing test establish the intended behavior: an eBay
listing already marked purchased should not remain actionable under a duplicate
ASIN; dismissals should follow the exact ASIN/listing pair across opportunity
IDs. The UI edit adds listing type beneath displayed cost. No temporary
diagnostics, credentials or ignored files are part of this release. The active
API migrations were already delivered separately and are not redeployed here.

## Resulting behavior

- Before summaries, filters and row limits, the opportunities API removes
  purchased listings from open/rejected/watching candidates, including duplicate
  ASIN rows for the same listing. It does not relabel those rows as purchased or
  modify purchase matching or lifecycle history.
- Dismiss/confirmed-exclusion actions suppress only the same ASIN/listing pair.
  A later explicit valid-match confirmation can restore that pair; unrelated
  notes, watches or feedback cannot silently reverse a dismissal. Ordering uses
  action timestamp then action ID for deterministic ties.
- Numeric legacy IDs match the parent Browse ID ending in `|0`. Different
  variations remain distinct. Invalid IDs do not initiate lookups. History-only
  views bypass this lookup and retain their records.
- Reads are scoped to candidate listing IDs, chunked to 75 normalized keys with
  parent aliases, paginated at 1,000 rows, restricted to decision action types,
  and select only five identity/action columns. No raw action context is fetched.
  A read failure surfaces an API error rather than showing possibly actioned
  listings as actionable.
- Cost cells show Auction first, then Best Offer, then BuyItNow, from existing
  backend metadata. Unknown listing type stays unlabeled. Both known and unknown
  shipping branches retain their existing amounts and currency/shipping text.
  Displayed landed cost remains authoritative; no frontend cost calculation was
  added.

No schema migration, provider sync, security change or database mutation is part
of the feature or its deployment verification.

## Validation

Passed targeted scripts:

```text
node web/app/api/sourcing/actionedListings.test.mjs
node web/app/api/sourcing/closestExcludedFilter.test.mjs
node web/app/api/sourcing/declinedOffers.test.mjs
node web/app/sourcing/MatchingReviewControls.test.mjs
node web/app/sourcing/CostCell.test.mjs
```

Coverage includes purchased duplicate-ASIN suppression, dismissal/reconfirmation,
timestamp ties, exact variation boundaries, legacy/candidate IDs, lookup batching,
pagination past 1,000 actions, protected history, ignored feedback, invalid IDs,
read failures, API counts/limits after suppression, review controls and listing
labels with known/free/unknown shipping and original currency. The cost test
renders the actual CostCell/helpers and verifies authoritative cost is retained.

Read-only helper verification used a representative four-row input and the real
stored actions for reported listing `287652912629`. It used one listing-scoped
request (364 ms): both open input ASIN candidates were suppressed while a
different variation and the protected-history input row remained. This probe
did not assert those input lifecycle statuses were current database statuses.
No action or opportunity record was changed. Index/size metadata inspection found an
approximately 8 MiB heap and 16,571 estimated sourcing-action rows; the check did
not scan raw payloads or apply SQL changes.

The local production Next.js build passed, including TypeScript and static-page
generation. Its first sandbox attempt could not fetch the existing Google Fonts;
the network-enabled retry passed without changing dependencies or font code.
`git diff --check` passed. Local compilation is not production verification.

## Deployment and verification

Commit the six sourcing code/test files plus this release document, push to
origin/main, then deploy only the web image with `scripts/deploy-web.ps1`.
Confirm stable ECS deployment with `scripts/aws-web-status.ps1`, then verify the
authenticated production Sourcing workspace. Check listing type under cost,
Closest Excluded, and purchased history without submitting operational actions.
Do not rerun scheduler migrations or provider syncs as a release check.

Rollback: redeploy the prior web revision 187 through the documented ECS workflow
if necessary. Existing sourcing action history remains intact; no data/schema
rollback is needed. A deployment receipt follows after verification.

## Deployment receipt

Application commit `93740307e3d9` was pushed to `origin/main`. Deployment used
the clean working tree with no dirty-build override.

- Web: `mbop-web-task:188`, digest
  `sha256:c97c5d450bc9936db083dbb064d85f055417a70ad83925538464cc2864de862e`.
  The Docker production build passed. AWS service-stability wait succeeded;
  `aws-web-status.ps1` confirmed deployment COMPLETED, desired/running 1/1,
  pending 0, and both build variables `93740307e3d9`. ECS reported steady state
  at 09:28 Pacific October 18; the new load-balancer target was healthy.
- Authenticated Chrome verification at the production domain showed build
  `9374030`. Buy List decreased from 9 to 6 rows. A separate read-only,
  listing-scoped action lookup verified all three removed pairs had existing
  dismissals: `B08H9KGMWK` / `227562662634`, `B001LJPAAO` / `128128528624`,
  and `B0050SVFWE` / `198524037168`. No operational action was submitted.
- Live cost cells displayed BuyItNow, Auction and Best Offer under the existing
  cost/shipping values. Observed examples included $17.99/free shipping/BuyItNow,
  $10.72/shipping $3.72/Auction and $24.96/shipping $5.96/Best Offer.
- Closest Excluded loaded 73 rows (previously 82), with 50 displayed under the
  existing limit and populated exclusion-reason/cycle selectors. Purchased
  Pending Match loaded 11 rows. These views showed no MBOP API error. The
  inspected console error was from an unrelated Chrome extension, not MBOP.
- Scheduler targets were read-only verified unchanged: purchase enrichment 144,
  Amazon sales schedules 145, sourcing catalog 143. No scheduler deployment,
  provider job, schema application or database mutation was performed for this
  web release.

The verification receipt is a documentation-only follow-up; the deployed image
remains pinned to the application commit above. All intended previously
uncommitted sourcing files are now versioned; ignored diagnostics and secrets
were not staged.
