# Sourcing prior-offer checks — November 1, 2026

## Deployed behavior

See [behavior and root cause](../SOURCING_PRIOR_OFFERS_2026-11-01.md).
The two operator-confirmed declines are retained by the audited SQL file
`sql/2026-11-01_record_operator_confirmed_declined_watch_offers.sql`.
The hourly importer also retains status-omitted buyer offers separately.
Daily, progressive, Continue, and single-pass sourcing check buyer history
before scoring. Watch actions remain recorded.

## Deployment

- Application commits: `b07073fce0ae`, `21aa4c648782`; decline audit `e7a6199827ec`.
- Migration `20261102011542` applied to verified project `froeucjkcepuhgwisped`;
  complete shared local/remote ledger matches afterward. CLI emitted a catalog
  cache certificate-path warning after application; database objects and ledger
  were independently verified.
- Web task `mbop-web-task:193`, build `b07073fce0ae`, image digest
  `sha256:20e9add0e5252c69abd9061a803a55c7f884badef9fc314f6b01a90b2e326b0a`.
  ECS services-stable wait completed; new ALB target healthy.
- Purchase-ingestion hourly/catchup schedules: task `149`, cloned from `148`,
  image `sha256:31060139205f216ddca02089b619bae294c071b9abd5193a8f1fe40365da80d5`.
- Sourcing-catalog schedule and latest family revision for on-demand sourcing:
  task `150`, cloned from `143`, image
  `sha256:d6ec07347e0832e82b120d541200af51b8f11e6e15a21ce450e31fc01c8c1f7b`.
  Existing per-group configuration preserved; only those three schedules changed.
- Windows Docker credential helper failed. Deployment succeeded with isolated
  temporary Docker configs; both temporary credential files removed afterward.

## Validation and limits

- 40 Python tests passed across buyer offers, progressive batches, daily retry,
  and coverage-cycle suites; the 11 buyer-offer tests also passed in the actual
  Linux scheduler image.
- Node presentation-filter tests, TypeScript, and production Docker Next build passed.
- Live importer read 519 offers: 72 explicit declines and 81 omitted-status offers
  retained separately. New table RLS and server-only table/view grants verified.
- Actual scorer using live database: Sonic `137887648197`, prior $17 vs maximum
  $15.96 => suppressed; Avengers `403002608732`, prior $19 vs maximum $15.94 =>
  suppressed. Both explicit declines also persisted from operator confirmation.
- Browser verification could not run: both CUA and node_repl failed to start their
  Node runtime (system path not found). Production database/scorer and AWS rollout
  checks passed; authenticated production browser behavior was not directly tested.
- No eBay offer writes, broad orchestration, or new live sourcing run was launched.
