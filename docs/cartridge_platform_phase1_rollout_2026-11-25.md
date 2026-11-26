# Cartridge sourcing policy and Phase 1 rollout ? November 25, 2026

## Release gate: PASS

The existing DS unsupported-platform rule now reads a shared configurable policy (`web/lib/sourcingPlatformPolicy.json`). Python and server routes use the same canonical alias taxonomy. Identity and purchasing eligibility remain independent. Catalog, replenishment, Flipmine and wholesale paths reject known ineligible products before unnecessary enrichment; existing Buy List/Closest Excluded rows and stale purchasing actions are filtered by the same policy. Historical records, manual decisions, purchases and inventory are not rewritten.

Excluded platforms: DS, 3DS, Game Boy, Game Boy Color, Game Boy Advance, Nintendo 64, NES, Super Nintendo, Sega Genesis/Mega Drive, Game Gear, Master System, Atari 2600/5200/7800/Lynx, Neo Geo Pocket/Color, Virtual Boy, WonderSwan/Color, Intellivision, ColecoVision, Pokemon Mini, N-Gage and PS Vita. Switch/Switch 2 remain eligible under existing guards. Disc/PC/PSP UMD behavior is preserved. Atari Jaguar, Neo Geo and TurboGrafx need reliable product-specific disc evidence; unknown/conflicting media is not affirmative eligibility. A generic normalized DVD label cannot override known cartridge evidence.

## Frozen shadow

Same frozen 379 captures, SHA recorded in `cartridge_platform_phase1_shadow_2026-11-25.json`. All material hashes unchanged. Identity: baseline 288 non-match / 53 match / 38 review; corrected 277 / 64 / 38. Lifecycle: baseline 322 rejected / 29 Open / 23 dismissed / 4 inventory snoozed / 1 watching; corrected with policy 320 / 31 / 23 / 4 / 1. The previously blocked Phase 1 without policy had 36 Open; five are now intentionally suppressed cartridge products. All 21 independently supported mismatches remain non-matches. Eligible baseline Open controls remain Open.

Mario 920153081093 / B00005B8FZ retains identity Match and is Rejected for cartridge policy. Remaining four newly Open shadows: PES 2012 PSP (377656806812), Wave Race GameCube (900097135752), Splinter Cell Double Agent GameCube (900081321133), Gran Turismo 2 PS (168847018534). Retained evidence and public photos reviewed individually; no material unsafe promotion identified. Splinter Cell is an existing conditional best-offer calculation, not a buy-now ROI approval. Current shipping, availability, eligibility, economics, demand, seller history and holds must pass normal replay. No image-analysis subsystem was added.

## Verification

454 targeted Python tests passed; 39 disposable PostgreSQL tests passed; 13 frontend/API files passed, including 96 Python/server policy parity cases. Production Next.js build and TypeScript compile passed. Diff whitespace check passed. Repository-wide lint has 91 existing errors/24 warnings in unchanged files; focused changed-route lint passed. One stale wholesale Ready-column contract also fails against the HEAD version of the unchanged page; no unrelated UI change was made.

Read-only production preflight: database capacity guard passed. Of 104 raw Open records, three are cartridge-ineligible; history stays stored and the normal API policy suppresses purchasing. One direct wholesale active row remains eligible. Original Flipmine tab is Complete with 558 preserved source pairs. Fresh normal backend presentation counts: baseline Buy List 24 / Closest Excluded 86; policy-only 23 / 82. These are server builder checks, not an authenticated browser claim.

## Controlled release / replay

Authorized manifest is exactly 35 original source pairs; correct N/A rows are 47/279/446, not row 346. Gran Turismo 2 is original source row 445. No broad catalog replay or sheet reimport. Original source/evaluation/old-opportunity snapshots are archived before changes; selected work uses existing lease, guarded writer and full normal evaluation pipeline. Deterministic job/request identifiers and saved checkpoints protect replay. Completion remains pending until opportunity persistence, duplicate checks and presentation counts finish.

Deployment and live replay receipts follow below. No profitability, fee, demand, quota, provider priority, cache TTL, schedule timing or permission changes are authorized or included. Unrelated MF oversale report remains uncommitted.


## Production receipt ? November 25, 2026, approximately 9:56 p.m. Pacific

Implementation pushed: `97c9fba7b017`, then final Vita classification `def0c704ef67`. Worker **181** and web **236** serve the final code. An intermediate worker180 was replaced before replay; no replay ran on it. Worker181 ECS smoke exited0 with the shared JSON and GBA/Vita rejection plus Switch/PSP acceptance. Web236 ECS rollout is **COMPLETED**, desired1/running1/pending0, ALB healthy. All21 EventBridge definitions compared structurally: only sourcing-catalog and keepa-catalog-priority task references changed to181; commands, timing, state, network, roles and permissions stayed identical. No unrelated schedule targets changed. Temporary task-scoped ECR auth file removed.

Controlled replay `abc862ae-d2f0-569a-ab98-6a6c09307820`: **35/35 terminal**. Sixteen known cartridge rows excluded with zero providers; two unresolved-platform rows also excluded with zero providers. Seventeen eligible rows passed through the normal freshness-aware pipeline: five new evaluations/opportunities, four guarded existing-opportunity decisions, seven matching exclusions and one confirmed unavailable listing. Five new normal initial snapshots were persisted. No manual decisions/holds were reset. All35 immutable original source/evidence archives verified against their pre-replay contents; all558 source identities/provenance preserved; all523 unselected source rows byte-equivalent as JSON objects. Original completed run remains completed. No duplicate actionable ASIN opportunities in the scoped normal cleanup planner; no duplicate cleanup writes required. Re-running the saved checkpoint returned without provider calls, duplicate jobs or opportunity writes.

Final source counts: **123 evaluated + 6 reused + 429 excluded = 558; pending0, failed0, invalid0**. Persisted tab/run Complete only after audit snapshots, duplicate and normal presentation checks finished. Mario is source Excluded for cartridge policy; corrected identity remains Match in its persisted evaluation.

| Flipmine presentation | Before policy/replay | Policy only | After replay |
|---|---:|---:|---:|
| Buy List |24|23|28|
| Closest Excluded |86|82|78|

Existing affected opportunity observations: three global raw Open records are cartridge-ineligible and dynamically suppressed without rewriting history. Within the original Flipmine presentation, policy removed one Buy List and four Closest Excluded rows. One active direct-wholesale row was checked and remains eligible. The policy applies to all current/future list requests and stale purchase actions; no full regular-history reevaluation or exhaustive regular Closest Excluded census was run.

### Newly actionable eligible-platform results

| Listing / ASIN | Normal route | Estimated profit / ROI | Offer, if applicable |
|---|---|---:|---:|
| PES2012 PSP ? 377656806812 / B005GM7J4M |Buy now|$43.85 /189.1%|?|
| Wave Race GameCube ? 900097135752 / B00005Q8LV |Buy now|$51.02 /59.4%|?|
| Shenmue Dreamcast ? 880090923440 / B00004S99R |Buy now|$69.03 /45.1%|?|
| Splinter Cell Double Agent GameCube ? 900081321133 / B000CC58VM |Best offer|$20.16 /62.3%|$24.22|
| Gran Turismo2 Greatest Hits PS ? 168847018534 / B07FYS9TQC |Best offer|$37.97 /52.8%|$59.84|

These are normal pipeline estimates, not guaranteed realized margins. Best-offer figures require an accepted offer at the displayed amount; none was submitted. All five have known paid shipping, Brand New source evidence and available quantity1. Shenmue was not a newly Open frozen shadow because old shipping was unresolved; fresh normal shipping evidence resolved it. 7 Wonders retains identity Match but is financially rejected. Correct N/A rows279/446 retain edition review; row47 retains a new-evidence core-name conflict. Their financially attractive prices were not used to override those checks. Row346 was untouched.

### API consumption and limits

Replay transport instrumentation: Trading **17 GetItem +8 GetItemShipping**; buyer-history refresh **6 GetMyeBayBuying** calls confirmed by shared ledger; Browse **4** calls; Amazon **13 read calls**; Keepa **0** external calls. Supporting authentication/analytics: eBay OAuth3, eBay Analytics1, Amazon OAuth1. Shared ledger deltas reconcile to Trading31 and Browse4. No rate-limit failure or quota-setting change. All16 cartridge exclusions avoided their listing-detail/enrichment path; two unresolved rows also used no providers. Exact hypothetical shipping/Keepa savings cannot be measured without making the prohibited unnecessary calls. Full379 shadow consumed zero marketplace calls. Eight public CDN photo GETs supported individual human review; no classifier/system was introduced.

Production browser verification remains **unverified**: browser access host unavailable; native browser URL-confidence safety check stopped navigation. ECS/ALB health, worker smoke, actual server list builders against production data, persisted progress and source-preservation checks passed; these do not substitute for an authenticated visual UI check. Known unrelated repository lint and stale wholesale contract failures remain documented above. No Phase2/3 development, schema migration, purchase, bid, offer, listing/inventory mutation, quota/cache/provider-priority change or sheet reimport was performed.

Machine-readable per-row original/revised decisions and receipt: `docs/cartridge_phase1_replay_results_2026-11-25.json`. Frozen gate and manifest are adjacent. Follow-up: visually confirm the sourcing page and Flipmine Complete28/78 presentation when browser access is available; investigate independent edition/lexical review exclusions only under a separately scoped task.
