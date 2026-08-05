# Video Game Identity Engine

Date: 2026-08-04

## Scope

Implemented a dedicated deterministic video-game identity parser and comparator for sourcing diagnostics. The engine is conservative: it hard-blocks explicit product identity conflicts and leaves unknown or ambiguous evidence as unknown/review instead of treating it as a positive match signal.

No AI calls, image analysis, eBay quota-consuming search, marketplace writes, schema changes, or historical opportunity reopening were performed.

## Identity Schema

The canonical identity object is emitted in `identity_comparison` and mirrored into the existing `derived_identity` display shape.

Fields:

- `franchise`
- `coreProduct`
- `coreGame`
- `installment`
- `installmentNormalized`
- `generation`
- `theme`
- `edition`
- `packageType`
- `platform`
- `region`
- `completeness`
- `digitalPhysical`
- `confidence`
- `evidence`

## Evidence Precedence

The parser uses backend evidence only. Current precedence:

1. Exact-ASIN Amazon Catalog Items attributes when cached in seed context.
2. Amazon exact title.
3. Exact child-ASIN variation evidence when present in cached catalog payloads.
4. eBay title.
5. eBay Game Name, excluding generic values such as `Game`.
6. eBay item specifics.
7. eBay description.
8. Category/product type through existing diagnostics.
9. Stored normalized diagnostics through existing scoring context.

Each parsed field carries source evidence and confidence in the identity object.

## Comparator Behavior

Hard-block conflicts:

- different franchise
- different core product
- different installment
- different generation
- materially different theme
- explicit material edition conflict

Visible but non-authoritative inside this comparator:

- platform
- region
- completeness
- digital/physical
- package type

Those fields remain displayed in identity diagnostics, but their hard-blocking remains owned by the existing proven rules so the new engine does not duplicate historical false-positive risks such as generic `PS`/`Xbox` platform labels or "free digital upgrade" wording.

Unknown does not count as positive evidence. Platform-only agreement does not make the identity result a match.

## Required Example Results

- Rock Band 3 vs The Beatles: Rock Band: blocked, core product conflict.
- Rock Band 3 vs Metal Track Pack: blocked, core product/theme conflict.
- Rock Band 3 vs Country Track Pack: blocked, core product/theme conflict.
- Rock Band 3 vs Classic Rock Track Pack: blocked, core product/theme conflict.
- Shrek 2 vs Shrek the Third: blocked, installment conflict.
- Shrek 2 vs Shrek Smash N' Crash Racing: blocked, core product conflict.
- Disney Infinity base Starter Pack vs 2.0 Marvel Super Heroes: blocked, generation/theme conflict.
- Disney Infinity base Starter Pack vs 3.0 Star Wars: blocked, generation/theme conflict.
- Disney Infinity 2.0 Marvel vs 3.0 Star Wars: blocked, generation/theme conflict.
- Dead Rising 4 vs Dead Rising 3: blocked, installment conflict.
- Wipeout 3 vs Wipeout 2: blocked, installment conflict.
- Wii Play Motion vs Tiger Woods PGA Tour 2009: blocked, franchise/core product conflict.
- New Carnival Games vs Cookie's Counting Carnival: blocked, franchise/core product conflict.
- New Carnival Games vs Shrek's Carnival Craze: blocked, franchise/core product conflict.
- Final Fantasy XIV Complete Edition PS4 vs Final Fantasy XIV/14 Complete Edition PS4: valid; installment normalizes to `14`.
- Rock Band PlayStation 3 vs Rock Band PS3: valid; PS3 is platform evidence, not installment evidence.
- PS3 is not installment `3`.
- Xbox 360 is not installment `360`.
- Generic Game Name `Game` does not override clear title evidence.
- Unknown core identity remains `unknown` and does not create positive core-game evidence.

## Safety Results

Local validation passed:

- `python -m unittest tests.test_video_game_identity_engine tests.test_sourcing_match_rules tests.test_sourcing_progressive_batches tests.test_sourcing_decision_trace`
- `python -m unittest tests.test_sourcing_match_rules tests.test_video_game_identity_engine tests.test_amazon_catalog_items tests.test_sourcing_velocity_suppression tests.test_sourcing_progressive_batches tests.test_sourcing_decision_trace tests.test_matching_feedback tests.test_ebay_sourcing_search`
- `python -m py_compile` for changed sourcing and reprocessing modules
- `npm.cmd --prefix web run build`

Confirmed-positive safety audit, read-only rerun:

- Artifact: `tmp/video-identity-positive-safety-rerun-2026-08-04.md`
- Raw positive evidence rows: 6,110
- Deduplicated positive rows: 2,436
- Authoritative confirmed positives: 2,353
- Review-only watching rows: 83
- Current hard-blocked confirmed positives: 85
- Prior documented baseline: 95 current hard-blocked confirmed positives
- Video-identity hard blocks in the rerun: 1 watch-only row, 0 authoritative confirmed positives

Latest 1,000 dismissals, read-only first pass:

- Artifact: `tmp/video-identity-dismissals-2026-08-04.md`
- Operator dismissals analyzed: 1,000
- Date range: 2026-07-11T14:35:18.776324+00:00 to 2026-08-04T14:57:12.841521+00:00
- Top reasons remained wrong edition/version, wrong product, missing shrink wrap, sales velocity too low, and ASIN blocked.

Current open/unreviewed sample dry-run after narrowing:

- Artifact: `tmp/sourcing_unreviewed_reprocess_dry_run_20260805011030.json`
- Rows in scope: 1,000
- Rows processed: 1,000
- Newly hard-blocked: 49
- Downgraded: 144
- Rows leaving presentation: 147
- Rows entering presentation: 0
- Purchased/completed/dismissed rows touched: 0

Recent rejected/Closest Excluded style dry-run after narrowing:

- Artifact: `tmp/sourcing_rejected_decision_trace_dry_run_20260805011020.json`
- Rows in scope: 459
- Diagnostic update count: 459
- Primary reason changes: 43
- Final recommendation changes: 45
- Would-be presentation eligible: 0

## Blocked Follow-Up

The final full production-read validation pass was blocked by the Codex tool usage limit. The escalation reviewer rejected additional networked production reads until 2026-08-07 21:05.

Not completed because of that gate:

- Full all-current-open dry-run without `--limit`.
- Final rerun of latest 1,000 dismissals after the last narrowing patch.
- Production deployment.
- Approved write-mode reprocessing.
- Production diagnostic verification.

Per the prompt requirement, deployment should remain blocked until the remaining full validation pass is completed.

## Files

- `integrations/video_game_identity.py`
- `integrations/sourcing_match_rules.py`
- `integrations/sourcing_decision_trace.py`
- `tests/test_video_game_identity_engine.py`

## Caveats

- The first engine version intentionally recognizes a controlled set of high-risk identity families from the prompt and prior audits.
- Platform, region, completeness, and digital/physical fields are included in the canonical object but are not new identity hard-block sources.
- No schema migration is required.
