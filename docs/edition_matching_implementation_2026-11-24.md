# Conservative edition matching and Browse availability implementation

Implemented locally against the approved attached request. No deployment,
production reevaluation, reimport, purchase, bid or offer was performed. The
previous investigation/review artifacts were preserved; the proposed fixture
matrix now links its 20 scenarios to executable regressions and records the
operator's revised Greatest Hits policy. Patch remains uncommitted.

## Edition behavior

The existing shared phase-3 identity/scoring pipeline used by production catalog
sourcing and Flipmine now calls `sourcing_edition_policy.py`.

- Standard and Standard Edition normalize to the same observed value. An omitted
  ordinary designation can be compatible when core game, platform, other material
  attributes and a structured Game Name or exact catalog GTIN corroborate it.
  Unknown edition observations remain unknown; an inference is recorded separately
  with evidence references, corroborating values and policy version.
- Supported marketing re-release labels: **Greatest Hits, Platinum Hits, Player's
  Choice, Nintendo Selects, PlayStation Hits and PlayStation Essentials**. These
  can be compatible with ordinary Standard packaging. Known catalog packaging
  restrictions, extra/different content, source contradictions, region, condition
  and required contents remain independent gates. Packaging labels are extracted
  before platform words so PlayStation Hits does not become an erroneous PS1
  platform or a spurious core-game suffix.
- Deluxe, Collector's, Limited, Premium, Gold, Ultimate, Enhanced, Director's Cut
  and other substantive editions are not inferred from a matching base title.
  Positive named evidence can come from title, Game Name, Edition specifics,
  Features or description. Negated evidence and multiple unresolved editions do
  not corroborate a special edition. A checksum-valid exact catalog UPC/EAN/GTIN
  can corroborate an omitted designation only without identity/SKU contradictions;
  MPN is never treated as UPC. Explicit incompatible editions stay conflicts,
  even when identifiers/negative wording would otherwise lead to review.
- Collector's requires a known contents manifest and affirmative inclusion
  evidence. Merely mentioning the usual contents is insufficient. Explicitly
  provided catalog `included_components` and identifiers are retained inside the
  existing relevant-attributes JSON; no schema, extra provider call or backfill is
  needed. Generic disc/manual components do not manufacture a special package.
  Existing cached catalog records without that data remain conservative until
  normal fresh enrichment provides it or other supported evidence resolves it.
- A catalog edition that is exactly a platform label is ignored as edition only
  when the catalog platform and explicit title platform corroborate it. No
  Standard observation is manufactured. Jewel Case remains meaningful packaging
  evidence and is not converted into Standard or discarded.

The material-evidence hash formula remains intact; policy output is not added
to the hash. Same source inputs retain their hashes. Actual new source/catalog
observations can still change them, as before. Exact operator review application,
scope, holds and lifecycle writers remain unchanged.

## Independent safeguards and Closest Excluded

New persisted reasons distinguish **Edition not corroborated** and **Required
contents not corroborated**, with details such as Deluxe Edition not corroborated
or Collector's Edition/required contents not corroborated. They remain review
outcomes, not confirmed mismatches, and cannot enter Buy List without corroboration.

The existing Closest Excluded list builder, ranking, deduplication, manual review,
action/hold suppression and FM provenance are reused. For these new unresolved
edition/contents reasons, it additionally requires recorded passing shipping,
minimum-profit and minimum-ROI business checks, an active listing and no blocking
independent hold/check or seller-avoid signal. No frontend economics calculation
or separate review queue was introduced. Confirmed substantive edition conflicts
do not become ordinary near misses. Existing legacy rows are not silently rescored.

Affirmative torn/broken/missing seal, cracked case and punched UPC disclosures are
recognized by the existing new-condition blocker, so clearing edition uncertainty
does not accidentally promote the known damaged examples from the investigation.
Other core/platform, region, digital/physical, eligibility, demand and seller
checks continue through the unchanged normal pipeline.

## Browse availability

`ebay_availability.py` supplies shared quantity interpretation to enrichment,
candidate mapping and availability refresh. It accepts positive documented
estimatedRemainingQuantity with IN_STOCK, without inventing an
estimatedAvailableQuantity field. Existing positive estimatedAvailableQuantity
evidence remains supported.

Unknown status/quantity, invalid/fractional/negative/nonfinite values and
contradictory quantities remain unverified. Zero, explicit sold-out/unavailable
status and expired listings remain unavailable. Exact item/variation, currency,
shipping and buyer-context requirements remain enforced. The quote selected by
the existing mapper must have a finite nonnegative USD cost and no contradictory
returned buyer location; unknown amounts cannot become fabricated free shipping.
The regression reproduces Trading shipping failure followed by a Browse response
with IN_STOCK, remaining quantity 20 and valid buyer shipping through the normal
fallback router. No live provider test was necessary.

Official contract verified during the investigation:
[Browse release 1.19.9](https://developer.ebay.com/develop/api/browse-api/release-notes)
documents estimatedRemainingQuantity; the
[Browse guide](https://developer.ebay.com/api-docs/buy/static/api-browse.html)
documents availability status/end-date checks.

## Validation

- Targeted Python suites: **368 tests; 20 skipped; all executed tests passed**.
  Includes 22 edition policy tests, 8 remaining-quantity/router tests, protected
  numeric identities, manual-review/hash/recheck parity, independent economics,
  dismissals and provider parity. All 20 approved fixture scenarios have linked
  executable coverage.
- Disposable PostgreSQL 17: **24 executed acceptance tests passed**: 13 Flipmine
  persistence/concurrency, 4 progress, 7 shared-quota tests. The last suite also
  reports 13 skipped imports of the separately executed Flipmine base suite.
- Frontend/API: **16 test files passed**, including actual Closest Excluded GET
  cases for unresolved Deluxe/Collector reasons, adverse economics, holds,
  confirmed conflicts, FM tags, existing deduplication and review behavior.
- Scoped ESLint passed. Next production build/type check passed. These are local
  checks and are not evidence of authenticated production rendering.
- One pre-existing frozen-response replay, `reviewRouting.test.mjs`, fails because
  its `tmp/sourcing-phase3/responses.json` capture lacks the current opportunities
  query. It fails identically with the **unchanged HEAD route substituted**, so
  the old capture was not rewritten to hide it. All other sourcing frontend tests
  passed. Refreshing that historical capture is outside this patch.

No migration, quota allocation, provider priority, cache TTL, sourcing cadence,
credential or permission change is required. A release should deploy worker and
web together through the normal AWS workflow, then verify the protected Sourcing
page and retry only the authorized failed row before any separately approved
targeted replay of edition exclusions. No candidate outcomes have changed here.
