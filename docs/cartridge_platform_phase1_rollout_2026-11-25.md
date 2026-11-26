# Cartridge sourcing policy and Phase 1 rollout ? November 25, 2026

## Release gate: PASS

The existing DS unsupported-platform rule now reads a shared configurable policy (`web/lib/sourcingPlatformPolicy.json`). Python and server routes use the same canonical alias taxonomy. Identity and purchasing eligibility remain independent. Catalog, replenishment, Flipmine and wholesale paths reject known ineligible products before unnecessary enrichment; existing Buy List/Closest Excluded rows and stale purchasing actions are filtered by the same policy. Historical records, manual decisions, purchases and inventory are not rewritten.

Excluded platforms: DS, 3DS, Game Boy, Game Boy Color, Game Boy Advance, Nintendo 64, NES, Super Nintendo, Sega Genesis/Mega Drive, Game Gear, Master System, Atari 2600/5200/7800/Lynx, Neo Geo Pocket/Color, Virtual Boy, WonderSwan/Color, Intellivision, ColecoVision, Pokemon Mini and N-Gage. Switch/Switch 2 remain eligible under existing guards. Disc/PC/PSP UMD behavior is preserved. Atari Jaguar, Neo Geo and TurboGrafx need reliable product-specific disc evidence; unknown/conflicting media is not affirmative eligibility. A generic normalized DVD label cannot override known cartridge evidence.

## Frozen shadow

Same frozen 379 captures, SHA recorded in `cartridge_platform_phase1_shadow_2026-11-25.json`. All material hashes unchanged. Identity: baseline 288 non-match / 53 match / 38 review; corrected 277 / 64 / 38. Lifecycle: baseline 322 rejected / 29 Open / 23 dismissed / 4 inventory snoozed / 1 watching; corrected with policy 320 / 31 / 23 / 4 / 1. The previously blocked Phase 1 without policy had 36 Open; five are now intentionally suppressed cartridge products. All 21 independently supported mismatches remain non-matches. Eligible baseline Open controls remain Open.

Mario 920153081093 / B00005B8FZ retains identity Match and is Rejected for cartridge policy. Remaining four newly Open shadows: PES 2012 PSP (377656806812), Wave Race GameCube (900097135752), Splinter Cell Double Agent GameCube (900081321133), Gran Turismo 2 PS (168847018534). Retained evidence and public photos reviewed individually; no material unsafe promotion identified. Splinter Cell is an existing conditional best-offer calculation, not a buy-now ROI approval. Current shipping, availability, eligibility, economics, demand, seller history and holds must pass normal replay. No image-analysis subsystem was added.

## Verification

454 targeted Python tests passed; 39 disposable PostgreSQL tests passed; 13 frontend/API files passed, including 96 Python/server policy parity cases. Production Next.js build and TypeScript compile passed. Diff whitespace check passed. Repository-wide lint has 91 existing errors/24 warnings in unchanged files; focused changed-route lint passed. One stale wholesale Ready-column contract also fails against the HEAD version of the unchanged page; no unrelated UI change was made.

Read-only production preflight: database capacity guard passed. Of 104 raw Open records, three are cartridge-ineligible; history stays stored and the normal API policy suppresses purchasing. One direct wholesale active row remains eligible. Original Flipmine tab is Complete with 558 preserved source pairs. Fresh normal backend presentation counts: baseline Buy List 24 / Closest Excluded 86; policy-only 23 / 82. These are server builder checks, not an authenticated browser claim.

## Controlled release / replay

Authorized manifest is exactly 35 original source pairs; correct N/A rows are 47/279/446, not row 346. Gran Turismo 2 is original source row 445. No broad catalog replay or sheet reimport. Original source/evaluation/old-opportunity snapshots are archived before changes; selected work uses existing lease, guarded writer and full normal evaluation pipeline. Deterministic job/request identifiers and saved checkpoints protect replay. Completion remains pending until opportunity persistence, duplicate checks and presentation counts finish.

Deployment and live replay receipts will be appended after execution. No profitability, fee, demand, quota, provider priority, cache TTL, schedule timing or permission changes are authorized or included. Unrelated MF oversale report remains uncommitted.
