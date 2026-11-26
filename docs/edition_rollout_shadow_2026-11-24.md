# Edition rollout: shadow gate FAILED

**Do not deploy the current patch.** The operator explicitly required stopping
before deployment if shadow evaluation identified unsafe or materially unexpected
behavior. That condition was met. No implementation fix was made after this gate
failure; the remaining rollout is intentionally stopped for review.

## Method and scope

Production state was captured read-only at approximately **9:59 p.m. Pacific,
Nov 24, 2026**. Database capacity and a tiny read passed first. A read-only client
wrapper rejected insert/update/upsert/delete/RPC operations. Marketplace clients
and source-refresh functions were not invoked.

The HEAD matcher and local revised matcher ran in isolated Python processes over
the **same** captured candidates, seeds, settings, persisted Keepa pricing, owned
units, scoped reviews, seller/matching context, declined-offer and operational
history. Thus baseline-to-revised differences isolate this patch from changes in
current pricing/history. Original stored statuses are separately retained in the
[97-pair machine-readable comparison](edition_rollout_shadow_2026-11-24.json).

This is a stored-evidence shadow, not fresh listing verification or production
reevaluation. An Open shadow score is **not** a verified Buy List entry or purchase
recommendation; normal presentation deduplication/history and fresh enrichment
would still be required before production replay.

| Sample | Size | Revised shadow result |
|---|---:|---|
| All investigated Flipmine pairs | 62 | 30 identity matches marked Open; 2 identity matches independently rejected; 28 continued identity reviews; 2 edition conflicts rejected |
| Initial no-other-comparison-conflict subset | 32 | 28 marked Open; 1 identity match independently rejected; 1 continued review; 2 edition conflicts rejected |
| Bounded affected regular-catalog sample | 6 | 5 identity matches marked Open; 1 continued review |
| Persisted re-release sample | 8 | 3 identity matches, 2 reviews, 3 non-matches; none marked Open; existing dismissed/inventory-hold outcomes retained |
| Additional omitted-special-edition sample | 2 | 1 review and 1 non-match; both rejected, unchanged |
| Previously accepted records | 20 | Two identity matches regress to review; baseline-to-revised lifecycle outcomes unchanged because current independent history still applies |

There are **97 distinct opportunities**; samples overlap. The re-release sample
has two persisted examples each of Greatest Hits, Platinum Hits, Nintendo Selects
and PlayStation Hits. No persisted Player's Choice or PlayStation Essentials
examples were found by the bounded sample selector; those labels have local
regression coverage, not a claimed live sample.

All 62 Flipmine pairs were identity reviews/rejected in the same-input HEAD
baseline. Of the revised 32 identity matches, two remain rejected for punched
UPC disclosures. The new condition gate correctly catches those two cases, but
misses the equally material wording below.

## Unsafe promotions and additional condition/contents risks

| eBay ID / ASIN | Shadow outcome | Saved evidence / blocker |
|---|---|---|
| 880128084759 / B003O6N2NY, Tiger Woods PGA Tour 12 | Rejected → Open | “Has a lot of seal damage. The case is also cracked in a spot.” The new regex does not recognize these wordings. |
| 336887119682 / B00006JBS4, Legends of Wrestling II | Rejected → Open | “This game is missing the plastic seal.” The new regex misses the intervening words. |
| 147693336106 / B000VJRU44, Wii Fit | Rejected → Open | Previously identified package/accessory uncertainty is not resolved by title, description or the captured catalog manifest. Edition compatibility currently clears the review without establishing contents. This does not prove an accessory is absent; it means promotion is not justified. |
| 287741926297 / B00DNGQTFI, Dragon Ball Z Battle of Z | Rejected → Open | “Small tear of plastic listed in photos.” Requires condition review; the phrase is not recognized. |
| 840120275430 / B000MAFXTQ, Samurai Warriors 2 Empires | Rejected → Open | Stretched wrap and disclosed flaws require condition assessment. They are not surfaced as a purchasing blocker. |

The first two are direct failures to retain disclosed condition safeguards. The
Wii Fit case is an unresolved physical-contents risk. The last two are additional
condition-review risks, not claims that the product identity is wrong.

These are shadow outputs only: **none was promoted in production**. Unit tests
used simpler condition paraphrases and did not catch the actual saved wording;
passing those tests was insufficient evidence for release.

## Materially unexpected identity behavior

- Pandora's Tower, **407348790546 and 257841605061 / B00B2QL2Y4**: both change from
  review to confirmed non-match because the Features field says Complete Edition.
  The latter has an exact UPC/title/platform corroboration from the investigation.
  The Features label may describe generic completeness rather than a different
  retail SKU; current code upgrades that ambiguity to a hard conflict prematurely.
  Do not blindly ignore the feature either: resolve its meaning conservatively.
- Previously accepted **Resident Evil 4, 314068158958 / B000B69E9G**: a Features
  sentence beginning “Enhanced remake” becomes an Enhanced Edition observation,
  creating a new edition review. An adjective is not sufficient named-SKU evidence.
- Previously accepted **The Crew Ultimate Edition, 168877999113 / B01KGR9QJC**:
  description wording “this special edition” is parsed as a competing Special
  Edition, conflicting with the positively named Ultimate Edition. This is a
  generic descriptor being mistaken for another substantive SKU.

For the accepted-record sample, the same-input baseline already suppresses many
records because newer operational history is dismissed or otherwise ineligible.
The two identity regressions above do not represent new production dismissals:
their revised and baseline lifecycle outcomes are identical. The complete report
keeps original stored status, same-input baseline and revised status distinct.

## Closest Excluded findings

21 of the 62 have new explicit edition/contents-related primary review reasons
and pass the new scoped edition-near-miss business gate on captured evidence.
That is **not** 21 newly presented listings: these were already review exclusions,
and the full normal list's manual/history/deduplication/ranking gates would still
apply. Remaining reviews include internal title/Game Name contradictions, special
edition/contents uncertainty and Jewel Case packaging. The revised Division Gold
Steelbook record is instead primarily excluded on current profitability.

No normal queue was rewritten and no actual Buy List/Closest Excluded count was
changed. Full before/after production presentation verification is deferred because
the prerequisite deployment gate failed.

## Required corrections before another release attempt

1. Add regressions using the **actual captured descriptions**, including modifiers
   and articles in the missed condition phrases. Preserve negation and avoid
   treating unrelated boilerplate as a defect. Edition clearance must not turn
   known condition uncertainty into an automatic purchase recommendation.
2. Carry and enforce the required package/accessory uncertainty through edition
   compatibility. Require positive relevant contents evidence or retain review;
   an absent manifest is not proof that no accessory is required.
3. Distinguish named edition evidence from generic Features/description adjectives
   and phrases. Do not infer Enhanced Edition from Enhanced remake or create a
   new Special Edition SKU from a generic description of Ultimate Edition.
4. Resolve Complete Edition feature ambiguity against exact SKU and contents
   evidence before assigning confirmed edition mismatch. Never weaken a real
   conflicting named edition or assume UPC overrides physical contradiction.
5. Rerun the full 97-pair comparison and focused negative/regression cases before
   commit, deployment or candidate changes. Then follow the approved order:
   deploy worker+web, retry only row 238, reconcile completion guards, and perform
   only the authorized targeted edition replay with fresh protected enrichment.

These are proposed corrections, **not additional changes made in this stopped
rollout**. Profitability, demand, fees, quotas, cache settings and schedules must
remain unchanged.

## Production state and work deliberately not performed

Final tiny production read confirms **Partial**, with **558 original rows**:
433 excluded, 118 evaluated, 6 reused, 1 failed, 0 pending. Source snapshot hash
remains `f60131aafdf2ccd6908fc2239f3942f0972166502f870ea26ba142eae4c1c13c`.

- Production candidate/evaluation/history writes: **0**.
- eBay/Amazon/Keepa provider calls during this shadow task: **0**.
- Commits, pushes, deployment revisions and migrations: **none**.
- Failed Super Mario Advance retry: **not attempted**, since deployment was gated.
- Targeted edition replay: **not started**.
- Existing jobs/schedules, permissions, credentials and manual decisions: untouched.
- Authenticated UI verification: not attempted; no new release exists to verify.

The implementation and this shadow report remain uncommitted for review.
