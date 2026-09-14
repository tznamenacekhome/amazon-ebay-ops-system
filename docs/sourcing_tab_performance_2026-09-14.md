# Sourcing tab performance ? 2026-09-14

Scope: web UI and read-only sourcing API. No matcher, scheduler, schema, decision refresh, provider search, marketplace write, or business-rule changes.

## Changes

- Supporting presented-listing lookup selects only opportunity/ASIN/listing identifiers, instead of full diagnostics and provider payloads.
- Primary opportunity queries project shipping and currency fields. Full eBay evidence is fetched in batches of at most 100 IDs only after qualification, ordering, deduplication and display limits. Review descriptions/aspects/images remain available. A disappearing row fails visibly rather than silently losing evidence.
- Keepa queries omit unused historical provider data; prices, offer-source classification and images use the same inputs.
- Independent presentation, inventory, pipeline, price and sales lookups run concurrently. Existing chunk sizes and qualification bounds are preserved.
- The hook cancels superseded requests, ignores late responses, debounces search by 250 ms, and skips opportunities requests on Coverage Cycle, History, Matching Intelligence and Settings.
- A hook-local, eight-query maximum, 15-second cache accelerates return visits. Reload after actions and row removal invalidate all tab entries. Cache is not shared between users; server responses remain no-store. Cross-session changes can take up to the cache TTL to appear unless Refresh is clicked; atomic action guards remain authoritative.

## Validation

- Frozen post-closeout replay: exact full JSON parity (excluding refreshedAt) for Buy List 102, Closest Excluded 122 total / 50 returned, Business Excluded 19. Ordered IDs, summaries, diagnostics, financial displays and exclusions preserved.
- Offline optimized replay transferred 76,793,207 JSON bytes across 148 requests; no production requests used for replay. Recorded source: tmp/sourcing-closeout/views-after/; runner: tmp/replay-sourcing-performance.cjs.
- One live read-only API-handler capture: 81,967,279 database response bytes versus earlier 117,028,006 (~30% less). The earlier capture already compacted the supporting listing-key lookup, so this comparison understates that additional deployed improvement. Captures are different times, not a controlled latency benchmark.
- Live optimized handler timings: Buy List 4.101 s, Closest Excluded 9.188 s, Business Excluded 4.253 s. Same counts as frozen replay. This is API-equivalent verification, not browser timing. Evidence: tmp/sourcing-tab-performance/live/current-manifest.json.
- Hook regression covers cancellation/out-of-order completion, cache hit/expiry, mutation/removal invalidation, inactive tabs, inline errors and search debounce.
- Actual Business Excluded handler regression covers compact qualification, visible evidence hydration, vanished rows and exclusion of unknown identity. Existing declined-offer and diagnostic-comparison regressions passed. TypeScript noEmit passed.

## Remaining limits

Cold requests still read persisted diagnostics for qualification and sorting across the existing bounded candidate set. Closest Excluded is the heaviest cold tab. No smaller candidate window, changed rank, weakened business filter or incomplete review evidence is used to claim faster loads.

Deployment and final verification are recorded after the implementation commit.
