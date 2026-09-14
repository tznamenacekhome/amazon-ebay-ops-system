# Sourcing workspace run-aware cache

Supersedes the 15-second browser-cache design in web152. Scope: web/API performance and additive database read-model/cache metadata. No matching/routing rules, scheduler definitions, provider searches or bounded decision refresh.

## Why cold tabs were slow

Web152 still rebuilt each result on demand: bounded candidate selection, presentation/action/listing history, full identity diagnostics, inventory/pipeline, Keepa, images and sales. Closest Excluded's measured handler time was 9.188 seconds with 47,065,513 database response bytes. This was not a browser-render benchmark. Frozen diagnostics contained repeated full identity objects and normalized evidence. Client sorting touches at most 150 displayed rows and is not the primary delay.

## Architecture

- `format=list` uses `sourcing_list_diagnostics(public.sourcing_opportunities)`, a computed PostgREST field. Only qualification, rank, exclusion and evaluation-ID inputs cross the wire. Full/default API behavior remains available and unchanged. List payloads carry only the evaluation ID needed for action guards; full diagnostic comparisons are not built or shipped for every visible row.
- List rows explicitly mark review evidence unloaded. The new exact-opportunity evidence GET loads full comparison and saved corrections when opening a review. The UI blocks a changed ASIN/candidate/listing/evaluation and never submits an incomplete review.
- `sourcing_cache_version()` coalesces dirty markers into a revision. Statement triggers cover 27 source tables used by sourcing views, including operator actions, batches/runs, settings, inventory/pipeline and price/sales annotations. This handles jobs, direct guarded refreshes, other browser sessions and operator actions without assuming that only the daily sourcing job can affect displayed data.
- Markers are per database backend, not a shared operational counter. Source writers hold only their own marker until commit. Cache readers drain committed markers with `FOR UPDATE SKIP LOCKED`, then update a separate cache revision. Rollbacks do not invalidate; readers never wait on operational writers. Idle metadata is bounded by database backends, and consumed markers are removed. No source/business data is written by freshness checks.
- Metadata tables are RLS enabled without public/client grants; the server-only RPC has a fixed empty search_path. No frontend-to-Supabase access is introduced. A two-second migration lock timeout prevents waiting behind operational writers.
- Server list cache is process-local, version-checked on every request, single-flight and capped at 24 entries/32 MiB (4 MiB per entry). A source change during a build prevents caching that response. Process restarts or multiple ECS tasks affect hit rate only. Errors are not cached.
- Browser memory caches at most 24 entries/16 MiB (4 MiB per entry), with no elapsed-time expiry. The version changes on relevant source writes, new web build or UTC date boundary (rolling sales displays). Refresh/actions invalidate immediately. A tiny freshness check runs on entry, browser focus and every 30 seconds while visible; another session/job is therefore observed within that interval. Reuse depends on committed revisions, not job-status labels: production contains abandoned June running records with no completed_at. The RPC reports an advisory running flag, but it cannot disable a cache whose source revision is unchanged. A list built across a source change is not cached or used to start preloading.
- Buy List loads and renders first. A deferred, serial background queue loads all other default tabs. Foreground selections take priority; shared requests coalesce. Background errors are retried visibly on selecting that tab. No hidden panel components or automatic write actions are mounted to preload data.
- Frontend selection, formatting and sorting of already displayed rows remain local. Backend admission, ranking, business exclusions, financial values and summary computation remain authoritative. Removed the frontend summary recomputation after row removal: displayed rows are only a subset of the API-qualified total.

## Validation before rollout

- Actual SQL function tested against 1,366 frozen diagnostic objects in a network-isolated PostgreSQL container.
- Frozen `format=list` replay: exact non-review field, ordered-ID, summary and action evaluation-ID parity for Buy List 102, Closest Excluded 122/50, Business Excluded 19. Final compact database response bytes 23,455,224, versus 76,793,207 in the equivalent web152 offline replay. Live before/after measurements are recorded after migration.
- Default/full API frozen replay retains exact JSON parity excluding refreshedAt.
- SQL regression covers 27 sources, bulk coalescing, insert/update/delete/truncate, rollback, idle revision stability, completed/active runs, null/array/object diagnostics and permissions.
- Concurrency regression: inverse-order writes to different source tables do not deadlock; freshness reads skip in-flight writes; commits invalidate and rollback does not.
- Browser resource/hook tests cover hours-long cache hits, version/explicit invalidation, force refresh, single-flight, superseded responses, inactive panels, debounce, Buy List first, every remaining tab preloaded, and errors.
- Lazy-review tests cover full evidence/preserved verdict, read-only GET, stale pair, inline errors and close cancellation. Existing actual review controls, declined offers, diagnostic comparison and Business Excluded tests pass.
- Server-cache regression covers hits, source revision, forced refresh, single-flight, changed-during-build, stale activity labels and freshness failure.

## Deployment and recovery

Migrations: `20260914193000_mbop_sourcing_read_cache.sql` and `20260914193100_mbop_sourcing_keepa_offer_presence.sql`. The second projects offer-array presence as an exact boolean instead of transferring full Keepa offers (including the nonempty `[null]` edge case). It adds cache metadata/functions/triggers only. Reverting the web runtime to web152 remains compatible; full/default opportunity responses are preserved. Do not roll back or edit an applied shared migration. Cache metadata may remain safely installed with the old web runtime.

Production migration, measured timings and final web revision will be recorded after verification. No authenticated browser session was available during the preceding web152 task; runtime verification must distinguish that limitation from API-equivalent checks.

First migration applied successfully; all 20 ledger entries matched. CLI emitted a local pg-delta catalog-cache certificate-path warning after applying; ledger reconciliation and the live service-role RPC/computed projection independently verified success. No migration was reapplied or edited.

Intermediate live profile (before final offer-array and list-JSON slimming): Buy List 3.142 s cold / 115 ms cache hit; Closest Excluded 6.143 s / 97 ms; Business Excluded 3.083 s / 62 ms. A hit reads only the 32-byte cache-version RPC result. Cold combined transfer 32,300,127 bytes. Exact counts remained 102 / 122 (50 returned) / 19. Evidence: tmp/sourcing-run-cache/live-final/. Final measurements follow after the second additive projection.

## Final live validation

Both additive migrations are applied; all 21 local/remote ledger entries match. Final source-query capture (no recorder query cache) and warm-repeat measurements:

| View | Cold API-equivalent build | Server cache hit | Cold DB response bytes | Browser JSON bytes |
| --- | ---: | ---: | ---: | ---: |
| Buy List | 2,739 ms | 72 ms | 6,614,756 | 273,216 |
| Closest Excluded | 5,969 ms | 67 ms | 12,597,485 | 283,162 |
| Business Excluded | 2,931 ms | 68 ms | 5,020,934 | 71,062 |

Every server hit performs only the small version RPC (32-byte result), not another listing/enrichment build. Browser-memory hits make no list request. Compared with the web152 capture, combined DB transfer fell from 81,967,279 to 24,233,326 bytes (~70%); browser JSON fell from 10,636,980 to 627,440 bytes (~94%). Captures occurred at different times, so these are observed checks rather than a controlled browser benchmark. Counts remain 102 / 122 total (50 returned) / 19. Cold Closest Excluded still performs bounded history/qualification and enrichment queries; source-version caching and preloading avoid repeating those queries on tab selection.

Evidence: `tmp/sourcing-run-cache/final-measurement/` (current/manifest/query metrics), and `tmp/sourcing-run-cache/lazy-evidence/` (two fresh full-comparison and pair-ID parity checks). Browser inventory remained empty; no authenticated browser timing or click-through is claimed. TypeScript and focused lint pass (only ten existing unused-code warnings in page.tsx).

Web deployment revision and image digest are appended after stable-rollout verification.
