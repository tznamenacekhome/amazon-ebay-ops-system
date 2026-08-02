# Context-Aware Numeric Identity Sprint

Date: 2026-08-02

Scope: narrow sourcing matcher change only. This sprint replaced broad numeric
sequel/year hard blocks with context-aware numeric identity matching. It did not
add Game Name rules, edition rules, short-title rules, AI review, production
rescoring, database writes, marketplace writes, or deployment.

## Files Changed

- `integrations/sourcing_match_rules.py`
- `tests/test_sourcing_match_rules.py`
- `docs/business_rules.md`
- `docs/matching_intelligence.md`
- `docs/sourcing_match_quality_report.md`
- `CURRENT_STATE.md`
- `DECISIONS.md`
- `KNOWN_ISSUES.md`
- `docs/sourcing_context_aware_numeric_identity_sprint_2026-08-02.md`

## Parser Design

Numeric hard blocks now use recognized identity families:

- Annual/sports families: `NBA 2Kxx`, `MLB 2Kxx`, `WWE 2Kxx`, `Madden NFL xx`,
  `FIFA xx`, `NHL xx`, `NCAA Football xx`, `Tiger Woods PGA Tour xx`, and
  `Just Dance yyyy/xx`.
- Installment families: `Rock Band`, `Sports Champions`,
  `Jackbox Party Pack`, `Dance Central`, `Sniper Elite`, `Devil May Cry`,
  `Far Cry`, and `Mercenaries`.
- Base identities: `Rock Band`, `Sports Champions`, and
  `Jackbox Party Pack`, with exclusions for Rock Band track packs, Beatles,
  AC/DC, country packs, and volume-style releases.

The matcher compares identity-bearing numbers only when the Amazon and eBay
titles share meaningful title tokens. It hard-blocks recognized same-family
conflicts and recognized base-game-vs-installment conflicts. Ambiguous numeric
disagreement returns `Review` rather than `Blocked`.

Diagnostics now preserve:

- normalized Amazon/eBay titles
- numeric tokens by side
- recognized identity numbers by side
- recognized base identities by side
- ignored platform, release-year, quantity, and included-content numbers
- ambiguous numeric tokens
- evidence sources, shared tokens, and comparison reason

## Rock Band Behavior

- `Rock Band 3 PlayStation 3` vs `Rock Band PlayStation 3`: blocked as
  installment `3` vs base `rock band`; the platform `3` is ignored.
- `Rock Band PS3` vs `Rock Band 3 PS3`: blocked as base `rock band` vs
  installment `3`.
- `Rock Band PlayStation 3` vs `Rock Band PS3`: not numerically blocked.
- `Rock Band 3 PlayStation 3` vs `Rock Band 3 PS3`: not numerically blocked.
- `Rock Band 2 PS3` vs `Rock Band 3 PS3`: blocked as installment `2` vs
  installment `3`.

## Validation Summary

Positive-match safety audit, read-only:

- Raw positive evidence rows: 5,679
- Deduplicated positive rows: 2,379
- Authoritative confirmed positives: 2,306
- Review-only watching rows: 73
- Baseline old strict numeric conflicts from the 2026-08-01 audit: 511
- Same strict simulation on the current dataset: 520
- Revised context-aware numeric confirmed positive hard blocks: 4

The 4 revised numeric positive-status conflicts are all recognized identity
conflicts:

- Two `Rock Band 3` vs base `Rock Band` rows.
- Two `Just Dance 2014` vs `Just Dance 2015` rows.

False blocks eliminated:

- Platform-number disagreements such as `PlayStation 3` vs `PS3`.
- Release years such as `2017` in `Sniper Elite 4 Xbox One 2017`.
- Quantity/lot numbers such as `Lot of 2 Rock Band 3`.
- Included-content counts such as `Minecraft + 3500 Coins`.

Latest 1,000 dismissals audit, read-only:

- Operator dismissals analyzed: 1,000
- Dismissal date range: 2026-06-15 to 2026-08-02
- Identity rows in `wrong_product`, `wrong_platform`, and
  `wrong_edition_version`: 623
- Revised numeric hard blocks in the latest 1,000 dismissals: 55
- Numeric blocks by major dismissal reason: 45 `wrong_edition_version`, 9
  `wrong_product`, and 1 other category.
- Top current numeric signals: `Jackbox Party Pack` base vs `7` (27),
  `Rock Band 3` vs base `Rock Band` (15), `Sports Champions 2` vs base
  `Sports Champions` (5), and `WWE 2K14` vs `WWE 2K16` (2).

Current open opportunities, read-only:

- Open opportunities checked: 33
- Open opportunities affected by revised numeric hard blocks: 0

## Validation Commands

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_sourcing_match_rules
.\.venv\Scripts\python.exe -m unittest tests.test_ebay_sourcing_search
.\.venv\Scripts\python.exe -m py_compile integrations\sourcing_match_rules.py integrations\score_sourcing_opportunities.py integrations\ebay_sourcing_search.py integrations\analyze_sourcing_positive_match_safety.py integrations\analyze_recent_sourcing_dismissals.py
.\.venv\Scripts\python.exe -m unittest tests.test_sourcing_match_rules tests.test_ebay_sourcing_search
.\.venv\Scripts\python.exe integrations\analyze_sourcing_positive_match_safety.py --root-cause --csv tmp\numeric-sprint-positive-conflicts-2026-08-02.csv --json tmp\numeric-sprint-positive-conflicts-2026-08-02.json --report tmp\numeric-sprint-positive-conflicts-2026-08-02.md
.\.venv\Scripts\python.exe integrations\analyze_recent_sourcing_dismissals.py --limit 1000 --csv tmp\numeric-sprint-dismissals-2026-08-02.csv --json tmp\numeric-sprint-dismissals-2026-08-02.json --report tmp\numeric-sprint-dismissals-2026-08-02.md
```

## Generated Read-Only Reports

- `tmp/numeric-sprint-positive-conflicts-2026-08-02.csv`
- `tmp/numeric-sprint-positive-conflicts-2026-08-02.json`
- `tmp/numeric-sprint-positive-conflicts-2026-08-02.md`
- `tmp/numeric-sprint-dismissals-2026-08-02.csv`
- `tmp/numeric-sprint-dismissals-2026-08-02.json`
- `tmp/numeric-sprint-dismissals-2026-08-02.md`

## Deployment Recommendation

Do not deploy automatically. The implementation is narrow and locally
validated, but the 4 revised numeric positive-status conflicts should be
operator-reviewed before deployment and before any production rescore. If those
4 rows are confirmed as valid identity conflicts, this change is a good
candidate for deployment with a separately approved sourcing rescore plan.
