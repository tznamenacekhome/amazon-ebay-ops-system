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

Read-only verification against the reported listing `287652912629` used one
listing-scoped request (364 ms): both open ASIN candidates were suppressed while
a different variation and the purchased-pending-history row remained. No action
or opportunity record was changed. Index/size metadata inspection found an
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
