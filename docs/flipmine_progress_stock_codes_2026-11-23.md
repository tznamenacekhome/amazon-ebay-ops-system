# Flipmine progress and seller stock-code correction

## Scope and findings

The Nov 23 review found 226 terminal / 332 pending candidates but a saved
210 / 348 summary. Worker summaries were refreshed only every 20 row indexes;
the deadline pause happens before the row exception handler and skipped its
refresh. Stored summaries could also use stale in-memory row status.

Progress now aggregates persisted outcomes at existing checkpoints and in a
non-masking finally handler. One bounded aggregate RPC on the existing status
request reconciles all displayed tab counts, including interrupted workers;
there is no new polling. The original row total must agree. API-capacity waits
remain pending. Completion still requires database evaluation/persistence guards
and presentation-count persistence; an inconsistent completed state is labeled
failed rather than Complete. The new migration adds only two service-role RPCs.

Rows 2 and 3, eBay IDs 137956960282 / 137956960309, ASIN B007H45AZ2,
seller junk-b-gone, are confirmed false *identity* conflicts. Titles start with
724b: and 835:; both have Game Name Dead or Alive 5, PlayStation 3, installment 5,
NTSC-U/C, new condition and matching descriptions. The shared phase-3 parser
retained the prefixes in coreGame/coreProduct. Both persisted examples used
Trading. Browse and Trading normalization feed the same matcher; regression
fixtures demonstrate equivalent behavior, without spending exhausted Browse quota
on a new live comparison. Removing this identity conflict does not establish that
either listing passes every purchase/profitability requirement.

The shared correction recognizes ONLY those two audited codes for that seller,
requiring a single corroborating Game Name and consistent explicit platform,
core title and installment. Source titles remain preserved. Unknown seller/code,
missing or contradictory evidence and numeric product names remain protected.
Condition, edition, platform, region and other purchasing checks are unchanged.
Seller attribution changes review evidence hashes only for corrected cases;
unaffected manual-review evidence hashes remain stable.

## Historical scope and targeted follow-up

A read-only scan of retained candidates found two affected Flipmine records and
zero regular catalog records with the audited codes. A broader digit-containing
2–8-character colon-prefix scan found five regular catalog rows: Norn9,
DDRMAX2, 007 and two PS4 examples. These are product/platform information, not
evidence for generalized numeric stripping. The two audited stock-code rows
were the only such records in Flipmine. Candidates rejected before persistence
are not comprehensively represented here; zero retained catalog matches is not
proof of zero occurrences in all historical search results.

Do not reimport or broadly reevaluate. Recommend a separate targeted replay of
only the two affected pairs, preserving manual decisions and provenance, using
cached listing/catalog/Keepa evidence only while valid under existing freshness
rules. Other codes need individual corroboration before extending the allowlist.
This deployment does not reset their excluded outcomes.

## Validation

- Python: 336 tests, 20 skipped, all executed tests passed.
- Disposable PostgreSQL 17: four new progress acceptance tests passed.
- Two frontend test files passed; scoped ESLint and Next production build passed.
- Fixtures cover Browse/Trading parity, audited prefixes, unknown seller/code,
  missing/wrong evidence, protected numeric games, incompatible products,
  condition/edition/platform/region safeguards and unchanged unrelated hashes.
- Progress tests cover stale summaries, duplicate/reused outcomes, pending waits,
  failed runs, lease ownership, interrupted checkpoints and inconsistent completion.

At the pre-deployment read, the original 558-pair import was still running:
50 evaluated, 5 duplicates, 208 excluded, 295 pending, zero failed (263 terminal).
All changes preserve allocations, provider priorities, cache TTLs and schedule
cadences/commands. Existing workers are allowed to finish; only subsequent
sourcing/recovery launches receive the corrected worker image.

Deployment receipt and final production readback will be appended after rollout.
