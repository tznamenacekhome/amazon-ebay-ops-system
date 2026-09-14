# Sourcing matching feature and runbook

## Workspace

Buy List presents identity-positive, business-eligible opportunities. Closest Excluded presents existing near-miss/review/excluded scope, with its normal ordering and limits. Business Excluded explains real business restrictions on identity-positive or confirmed pairs. Identity Adjudication and normal feedback retain exact-pair evidence; no new queue is introduced by closeout.

## Accepted matching engine

Canonical fields cover base game, installment, platform, edition, generation, theme, package/contents, completeness, digital/physical, region and supported release-year evidence. Unknown remains Unknown: no invented Standard, Base, Complete or Physical defaults. Platform numbers, years and quantities remain distinct from installments. Deluxe, GOTY, Anniversary, expansions, bundles, Starter Packs and Track Packs retain their distinctions.

Sources remain distinguishable: exact-ASIN Amazon reference/catalog metadata, eBay title, Game Name, specifics, descriptions and operator corrections. Omission is not automatically contradiction. Trusted reference metadata survives a scoped field correction; stale raw platform text does not override the corrected platform. Disney Infinity alone has the operator-authorized unnumbered generation 1.0 convention; explicit 2.0/3.0 conflicts remain.

The tested Phase 3 parser is accepted for closeout. It is not an assurance of perfect title interpretation. No title-specific whitelist or new parser investigation is part of this release. Future real-world feedback may identify improvements, including descriptive wording retained in core-game comparisons.

## Feedback and corrections

Confirm Match, Incorrect Match and Not Sure apply to the exact reviewed pair. Incorrect Match does not blacklist a listing against other ASINs. Not Sure supplies neither positive nor negative ground truth. Wrong-field corrections retain original/corrected values, side, scope, provenance, timestamp and snapshot/evaluation identity. Amazon ASIN scope is explicit; eBay corrections remain exact listing/pair scoped. Platform Compatible is a relationship, not an inferred same-platform identity verdict.

The dedicated Save variation scope action is independent of pair verdicts, corrections and notes. Its saved qualification/progress updates do not change routing or buying eligibility. Save corrections only and variation-only saves remain separate.

## Business and lifecycle separation

Match does not buy, offer, bid or release a hold. Profitability, condition, region/location, shipping, availability, inventory, ROI and velocity restrictions remain separate. Inventory snoozes are ASIN-wide, including legacy `roi_snoozed` records with inventory context. Release uses existing sell-through thresholds and owned/pipeline inventory. ROI holds remain pair-scoped with existing improvement rules. Protected lifecycle rows and human review history are preserved.

## Runtime and bounded refresh

`MBOP_SOURCING_PHASE3=1` activates Phase 3 in the sourcing scoring runtime. Existing-row updates use the atomic refresh path; with the flag absent, legacy default outputs remain unchanged. The sourcing task is the only schedule target intended to change; web deployment is unnecessary for this backend release.

`integrations/sourcing_phase3_refresh.py` reads stored evidence only. It defaults to dry-run; `--write` explicitly enables database decision updates. The cohort is the current Los Angeles calendar date and the preceding 29 dates, frozen at run start. Both previously admitted and failed results are included. Explicit identity reviews (including Not Sure), human dismissals and protected lifecycle rows are excluded. Recognized automation/availability/duplicate cleanup is not human identity review. Valid scoped corrections can apply to other unreviewed pairs.

Each batch captures exact guarded state, evaluates, recaptures immediately before writing and invokes a database atomic compare/write. Stale, newly reviewed and protected rows skip without stopping other rows. Durable pending requests and stable request IDs allow resuming the same output directory without duplicate writes. Do not change the output directory to retry an interrupted write run. The journal, compressed source captures and summary preserve the run evidence.

The guard hashes large source payloads rather than copying them into every state/log record. Source records remain in their existing tables. Decision audit rows are compact; no historical snapshots/actions/reviews are rewritten. No provider or marketplace client is called by the bounded runner.

Example inside the exact deployed scheduler image:

```text
python integrations/sourcing_phase3_refresh.py --output /app/closeout/run --write
```

Before a new production run, use the project cloud workflow and verify target project, strict regressions and atomic-guard tests. Migration application follows the shared ledger workflow. Deployment preserves all twenty schedules except the intended sourcing task revision. See the dated [closeout report](sourcing_matching_30_day_reprocess_2026-09-13.md) for actual activation, counts and verification; this runbook alone is not proof that deployment happened.

## Future reuse

The canonical comparison boundary is intended to support related-ASIN discovery, wholesale supplier matching and eBay-first discovery later. Those workflows are not implemented by this closeout.
