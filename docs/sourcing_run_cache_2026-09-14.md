# Sourcing workspace run-aware cache

Supersedes the 15-second browser-cache design in web152. Scope: web/API performance and additive database read-model/cache metadata. No matching/routing rules, scheduler definitions, provider searches or bounded decision refresh.

## Why cold tabs were slow

Web152 still rebuilt each result on demand: bounded candidate selection, presentation/action/listing history, full identity diagnostics, inventory/pipeline, Keepa, images and sales. Closest Excluded's measured handler time was 9.188 seconds with 47,065,513 database response bytes. This was not a browser-render benchmark. Frozen diagnostics contained repeated full identity objects and normalized evidence. Client sorting touches at most 150 displayed rows and is not the primary delay.

## Architecture

- `format=list` uses `sourcing_list_diagnostics(public.sourcing_opportunities)`, a computed PostgREST field. Only qualification, rank, exclusion and evaluation-ID inputs cross the wire. Full/default API behavior remains available and unchanged.
- List rows explicitly mark review evidence unloaded. The new exact-opportunity evidence GET loads full comparison and saved corrections when opening a review. The UI blocks a changed ASIN/candidate/listing/evaluation and never submits an incomplete review.
- `sourcing_cache_version()` coalesces dirty markers into a revision. Statement triggers cover 27 source tables used by sourcing views, including operator actions, batches/runs, settings, inventory/pipeline and price/sales annotations. This handles jobs, direct guarded refreshes, other browser sessions and operator actions without assuming that only the daily sourcing job can affect displayed data.
- Markers are per database backend, not a shared operational counter. Source writers hold only their own marker until commit. Cache readers drain committed markers with `FOR UPDATE SKIP LOCKED`, then update a separate cache revision. Rollbacks do not invalidate; readers never wait on operational writers. Idle metadata is bounded by database backends, and consumed markers are removed. No source/business data is written by freshness checks.
- Metadata tables are RLS enabled without public/client grants; the server-only RPC has a fixed empty search_path. No frontend-to-Supabase access is introduced. A two-second migration lock timeout prevents waiting behind operational writers.
- Server list cache is process-local, version-checked on every request, single-flight and capped at 24 entries/32 MiB (4 MiB per entry). A source change during a build prevents caching that response. Process restarts or multiple ECS tasks affect hit rate only. Errors are not cached.
- Browser memory caches at most 24 entries/16 MiB (4 MiB per entry), with no elapsed-time expiry. The version changes on relevant source writes, new web build or UTC date boundary (rolling sales displays). Refresh/actions invalidate immediately. A tiny freshness check runs on entry, browser focus and every 30 seconds while visible; another session/job is therefore observed within that interval. A running/planned run with no completed_at disables reuse/preloading while writes progress. Historical running statuses with completed_at are not active jobs.
- Buy List loads and renders first. A deferred, serial background queue loads all other default tabs. Foreground selections take priority; shared requests coalesce. Background errors are retried visibly on selecting that tab. No hidden panel components or automatic write actions are mounted to preload data.
- Frontend selection, formatting and sorting of already displayed rows remain local. Backend admission, ranking, business exclusions, financial values and summary computation remain authoritative.

## Validation before rollout

- Actual SQL function tested against 1,366 frozen diagnostic objects in a network-isolated PostgreSQL container.
- Frozen `format=list` replay: exact non-review field, ordered-ID, summary and action evaluation-ID parity for Buy List 102, Closest Excluded 122/50, Business Excluded 19. Combined database response bytes 30,380,339, versus 76,793,207 in the equivalent web152 offline replay. Live before/after measurements are recorded after migration.
- Default/full API frozen replay retains exact JSON parity excluding refreshedAt.
- SQL regression covers 27 sources, bulk coalescing, insert/update/delete/truncate, rollback, idle revision stability, completed/active runs, null/array/object diagnostics and permissions.
- Concurrency regression: inverse-order writes to different source tables do not deadlock; freshness reads skip in-flight writes; commits invalidate and rollback does not.
- Browser resource/hook tests cover hours-long cache hits, version/explicit invalidation, force refresh, single-flight, superseded responses, inactive panels, debounce, Buy List first, every remaining tab preloaded, and errors.
- Lazy-review tests cover full evidence/preserved verdict, read-only GET, stale pair, inline errors and close cancellation. Existing actual review controls, declined offers, diagnostic comparison and Business Excluded tests pass.
- Server-cache regression covers hits, source revision, forced refresh, single-flight, changed-during-build, active jobs and freshness failure.

## Deployment and recovery

Migration: `20260914193000_mbop_sourcing_read_cache.sql`. It adds cache metadata/functions/triggers only. Reverting the web runtime to web152 remains compatible; full/default opportunity responses are preserved. Do not roll back or edit an applied shared migration. Cache metadata may remain safely installed with the old web runtime.

Production migration, measured timings and final web revision will be recorded after verification. No authenticated browser session was available during the preceding web152 task; runtime verification must distinguish that limitation from API-equivalent checks.
