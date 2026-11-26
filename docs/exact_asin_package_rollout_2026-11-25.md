# Exact-ASIN package correction and controlled edition rollout

## Mechanism and evidence scope

The existing Amazon catalog relevant_attributes_json stores components,
identifiers and package evidence. Normal catalog enrichment now retains
marketplace-scoped descriptions/bullets as well. A small versioned artifact,
integrations/product_package_evidence.json, retains authoritative or unresolved
exact-ASIN observations with platform, marketplace, component quantities,
configuration, sources and verification status. It is deployed with the existing
integrations, attached to cached exact-ASIN catalog identity, and retained on
normal future catalog normalization. No migration, new service or backfill.

Only B006Y76HY6 (original AR Book requirement) and B000VJRU44 (unresolved exact
package configuration) have curated records. No requirement propagates by title
or franchise. Matching exact-ASIN/platform/catalog-title guards apply; explicit
other marketplaces do not receive US evidence. Legacy catalog seed copies lacking
marketplace retain MBOP's existing US sourcing scope. Conflicting verified
observations stay review. Actual new requirement evidence changes material
hashes for affected products; unchanged products preserve their hashes.

The shared package comparator distinguishes software-only, accessory bundle,
required-components and unresolved configurations. Ordinary software without
known ambiguity does not need a manifest. It separates package words such as
Game only from product identity, without waiving missing-case/manual or other
condition checks. Physical component evidence never assigns franchise defaults.
Controllers require compatible platform evidence, and recorded model/quantity
requirements are enforced. Incomplete inferred bundle manifests remain review.

Explicit missing components override UPC/seal claims. Replacements/reproductions
do not prove original New contents. A corroborated original factory-sealed retail
package with exact SKU identifier and compatible package configuration may
establish original contents without enumerating every item. Generic New/sealed
claims alone do not. A named bundle's identity can match while independent
physical contents remain unverified for purchasing.

All prior edition, condition, re-release, numeric identity and remaining-quantity
corrections remain. Existing Closest Excluded qualification/ranking, seller
checks, holds, manual decisions, provenance and duplicate guards remain.

## Production evidence reviewed read-only

The bounded retained review covered 11 catalog ASINs and at most two candidates
each; see exact_asin_package_retained_review_2026-11-25.json.

- B0028ZH7GU explicitly identifies Guitar Hero 5 Wii Game only. It is classified
  software-only and receives no guitar requirement. Other identity checks still
  exclude the retained candidate; this task does not waive them.
- B00VEPK9U6 identifies Guitar Hero Live Xbox 360 Guitar Bundle. Its game-only
  candidate cannot satisfy that package.
- DDR Hottest Party Bundle, Hottest Party 2 with Dance Mat and Skylanders Starter
  Packs retain bundle contents review/conflict independently from ordinary DDR.
- B000VJRU44's title Wii Fit / Standard does not establish software-only versus
  board bundle. Its exact configuration remains unresolved; no board manifest
  was invented.
- Spirit Camera's captured title is Sealed / Brand New, with no description,
  contents specifics or exact SKU identifier. Its original AR Book remains
  uncorroborated, so it is rejected from automatic purchasing and reviewable.

No stored Wii Fit Plus configuration, Rock Band/Disney Infinity catalog pair, or
software-only/bundle pair for the exact same named game was established by this
bounded catalog review. Synthetic fixtures explicitly cover those combinations;
they are not claims about real ASIN configurations. Manufacturer requirements
and references are preserved in the exact-ASIN evidence artifact.

## Four-stage same-input shadow gate: PASS

The same original 97 opportunities and captured settings/pricing/history were
used. All 29 remaining new Open rows were individually reviewed against captured
identity, descriptions, specifics and independent checks. No additional material
purchasing concern was identified. This is not fresh purchase verification.

| Outcome across 97 | HEAD | First edition patch | Previous corrected | Final |
|---|---:|---:|---:|---:|
| Identity match | 16 | 53 | 54 | 53 |
| Identity review | 71 | 34 | 35 | 36 |
| Identity non-match | 10 | 10 | 8 | 8 |
| Shadow Open | 0 | 35 | 30 | 29 |
| Rejected lifecycle | 80 | 45 | 50 | 51 |
| Dismissed lifecycle | 15 | 15 | 15 | 15 |
| Inventory snoozed | 2 | 2 | 2 | 2 |

Only Spirit Camera changes identity/lifecycle relative to the previous corrected
shadow: Match/Open becomes Review/Rejected. All nine prior listing regressions
remain corrected. Accepted sample remains 15 matches, 1 review, 4 non-matches,
with unchanged protected lifecycle. Final Flipmine 62: 30 identity matches,
32 reviews, 24 shadow Open. Initial 32: 27 matches, 5 reviews, 22 shadow Open.
The complete comparison is exact_asin_package_shadow_2026-11-25.json.

## Validation and deployment plan

- 342 Python matching/sourcing/Flipmine/enrichment regression tests passed.
- 24 PostgreSQL 17 disposable acceptance tests passed: 13 persistence/concurrency,
  4 progress and 7 quota. No production database used.
- 15 frontend/API files passed, including 120 Python-to-API/UI comparisons.
- Scoped lint and Next production build/type check passed.
- Known old frozen reviewRouting capture remains incomplete as documented in
  the preceding report; it was not rewritten. Authenticated production UI
  verification is separate from local tests.

Pre-release AWS: account 297464765814, web231 healthy/stable, catalog sourcing
and Keepa-priority recovery use worker177. No active sourcing/Flipmine task was
interrupted. Only those two necessary schedule image revisions will change;
commands, timing, permissions and other schedules are preserved.

Before-replay normal HEAD list-builder counts: Buy List 0, Closest Excluded 115.
These are backend presentation counts, not authenticated UI verification.
Capacity gate passed before these reads.

The authorized cohort is the initial 32 plus 26 directly affected additional
opportunities within the captured 62. Additional rows are selected by changed
edition comparison/normalization or an explicit corrected edition/contents
review reason; four unrelated pairs are not selected. Fresh normal evaluation,
protected-row checks and atomic guarded persistence are required, not shadow
identity promotion. Original evaluations must be archived, holds/manual decisions
skipped, and source rows/provenance retained. No reimport or marketplace actions.

Release and replay results will be recorded after production verification.
