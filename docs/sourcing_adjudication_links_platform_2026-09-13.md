# Adjudication listing links and platform feedback - 2026-09-13

## Scope and checkpoint

**Deployed: web148 from `833837d8c94d`, rollout COMPLETED, exact ALB target healthy.** Baseline is web146 / scheduler92, source checkpoint `672b48f`. The worktree was clean at task start. Python runtime, matching rules, frozen queue snapshots, SQL schema/RPC definitions, production sourcing membership and business-release rules are unchanged. No provider search, marketplace write, sourcing refresh or production synthetic review is authorized or performed for this task.

## Outbound links

Every queue row and dialog shows the exact ASIN and full stored eBay identity with Open Amazon Listing / Open eBay Listing links. Amazon uses `https://www.amazon.com/dp/{ASIN}`. eBay uses `https://www.ebay.com/itm/{numeric_id}`; either an all-numeric stored ID or the numeric component of a full `v1|item|variation` ID is accepted. This normalization affects only the public URL. The original Browse ID and variation remain displayed and stored unchanged. Links use target=_blank and rel=noopener noreferrer. Missing/malformed identities show the explicit unavailable label. URL construction performs no API calls.

## Platform review semantics

Only the Platform row receives a relationship control: Not specified initially, then Match / Compatible / Wrong / Unknown. Match means effectively identical platform identity; Compatible means supported compatibility despite different values; Wrong identifies a faulty parse and enables the existing either-side editors; Unknown records inability to establish the relationship. No state creates an overall pair verdict or rewrites platform values.

The operator still independently chooses Confirm Match, Incorrect Match or Not Sure. Compatible can accompany any of them. Confirm Match plus Compatible can qualify as Tier A under the existing exact-pair, variation, source and explicit-attestation requirements; textual platform equality is not required. A later relationship-only change requires renewed pair review before restoring Tier A. Correction-only never creates a verdict.

Actual platform corrections remain in the original v3 corrections array. Amazon remains pair-scoped unless explicitly changed to ASIN scope; eBay remains exact-pair scoped. Wrong-to-Compatible preserves pending corrections and prior append-only history. Non-platform Wrong/Undo behavior is unchanged. Unedited saved relationships are not resubmitted with a new actor/time merely because another part of the review was saved; use Unknown to explicitly replace a prior relationship with uncertainty.

The optional Supported platforms fields accept comma-separated operator-evidence names per side. They become bounded, trimmed/deduplicated string arrays, not canonical parser output. No platform values or platform support lists are invented from title text. Canonical set-valued platform schema work is deferred.

## Storage, provenance and export

The existing `matching_feedback_v3` JSON adds optional `fieldRelationships`:

```json
{"fieldRelationships":[{"field":"platform","operatorRelationship":"compatible","compatiblePlatforms":{"amazon":["Xbox One"],"ebay":["Xbox One","Xbox Series X"]}}]}
```

The server validates one platform relationship with the four allowed states and at most eight bounded names per side. It records original canonical values in `platformEvidence`. Existing action/snapshot context supplies actor, database timestamp, exact pair, source marker, frozen evaluation and snapshot identity. The existing atomic save RPC stores the JSON unchanged; no migration or new correction store is needed. Full-context revisions automatically cover relationship changes. Latest valid same-pair/frozen-source feedback wins; invalid or unverifiable newer evidence cannot silently create Tier A. History includes relationship entries and corrections independently.

Report `/api/sourcing/adjudication?report=1` includes `platform_amazon`, `platform_ebay`, `platform_operator_relationship`, `platform_relationship_provenance`, `platform_corrections`, `pair_verdict`, variation, original source snapshot and frozen evaluation IDs, plus existing actor/time/supersession lineage. The relationship provenance contains its own actor/time/action/snapshot; it need not share the later pair-verdict actor/time.

Existing sourcing latest-review reads exclude the adjudication source, so relationship evidence does not change Buy List, Closest Excluded or Business Excluded. Existing Python `platforms_compatible` already contains an Xbox One/Series X branch; this corpus can validate it in a later Phase 3 task. No Python helper, compatibility admission rule or policy activation was changed. Future consumers must explicitly reconcile this relationship evidence; merely recording it does not apply it to scoring.

## Mixed-lot sample policy

The original 16-row frozen queue and manifest remain intact. `B072JZB85B / 233733278405` is retained as **Excluded from adjudication / informational only**, with reason:

`not useful as exact single-product validation sample; mixed/random lot intentionally left as-is`

It has links and read-only evidence, no review action buttons, and server-side save rejection. Prior actions remain intact. It is excluded from progress, positive/negative/unresolved corpus membership and the Tier A denominator. API/export now report `total=15`, `storedTotal=16`, with one separately listed excluded row. No replacement is introduced. This is sample policy only, not mixed-lot matching, dismissal or sourcing routing logic.

## Verification

- Updated actual React component tests cover safe links, missing/malformed IDs, unchanged Browse ID, relationship default/states, Wrong editors, retained corrections, optional support arrays, saved state, unchanged-review provenance and informational-only controls. Existing shared dialog controls also pass.
- Actual API -> disposable PostgreSQL -> reload/export tests pass (156 RPC calls), including the supplied Xbox pair, all four relationships, Compatible with each verdict, correction plus Compatible, relationship supersession/history, source preservation, correct 15/16 counts, informational save rejection and export provenance.
- Existing review API/PostgreSQL/Python analyzer tests pass, including stale state, retries, full rollback, protected purchases and Business Excluded. Updated adjudication tests retain concurrent-save and injected late-transaction-failure checks and compare all opportunity/hold/block rows before and after.
- 55 Python tests pass: 24 Phase 3, 10 feedback and 21 identity engine. No Python source changes.
- Focused lint, TypeScript, Next production build and Docker/web build pass. The built image preserves frozen **37 Buy List / 50 Closest Excluded / 2 Business Excluded** rows, full routing fields, summaries and order, using 110 frozen reads with networking disabled.
- Actual component screenshots (`tmp/adjudication-refinements/editor.png`, `compatible.png`) show exact links, distinct Xbox values and selected Compatible. They are offline evidence, not authenticated production verification.
- Final AWS comparison verifies web148 healthy, scheduler92 unchanged and all 20 schedules semantically identical to the web146 baseline. The exact release image passes the full frozen routing test and read-only production queue/export verification (32 RPC reads): 16 stored rows, 15 eligible, 0 reviewed, 0 Tier A, 1 informational exclusion.

No production synthetic review was used to test persistence: that proof comes from the disposable transaction tests. Browser inventory returned no enabled apps or browsers. Authenticated production UI verification remains a gap; offline rendered UI and exact-release read-only API-equivalent evidence are the documented fallback. A Cognito redirect is not feature verification.

## Operator instructions for the Xbox example

Open Sourcing > Identity Adjudication and locate `B07FF3F7F9 / v1|267725836968|0`. Open both listing links and verify the exact release. Under Platform choose Compatible when the evidence supports cross-generation compatibility; optionally record Amazon `Xbox One` and eBay `Xbox One, Xbox Series X` in Supported platforms. Leave the canonical values alone unless their parse is actually wrong; select Wrong to correct one or both sides if necessary.

Then independently judge the entire product and choose Confirm Match / Incorrect Match / Not Sure. The frozen titles currently show Subnautica versus Subnautica: Below Zero, so platform compatibility alone does not resolve the product question. Do not automatically Confirm Match from the compatibility selection. Review 15 eligible rows; the mixed-lot informational row requires no decision. Phase 3 remains incomplete and shadow-only.


## Final release evidence

Implementation commit: `3ca7bad0ec46`; final UI/release commit: `833837d8c94d`. Both are pushed. A queue-level visual check found long Browse IDs spilling into the next cell and insufficient standalone background contrast; the follow-up makes queue links stacked, wraps IDs and supplies an explicit white page background. The corrected queue screenshot was inspected before the final release. Intermediate web147 was superseded by final web148; both deployment logs are retained.

Release used the documented web-only deployment script from a clean detached checkout, followed by the AWS status script and final task/ALB/schedule readback. Healthy target: 172.31.29.223:3103. Image: `297464765814.dkr.ecr.us-west-2.amazonaws.com/mbop-web@sha256:6b14297661359d537043b4b3fd171513eb96140250e6c0bea0af3b534b3cc1bc`. CLOUD_DEPLOYMENT=true and LOCAL_SYNC_ENABLED=false remain set. Python integrations, scheduler runtime, migrations, frozen queue identities and sourcing opportunity handlers are unchanged from task baseline.

Exact release hashes, task/target evidence, before/after AWS artifacts, full read-only queue/export result and test summary are recorded in `sourcing_adjudication_links_platform_deployment_2026-09-13.json`. No current opportunity or historical record was rewritten by this task. Stop after these refinements; the operator's 15-row review and a later Phase 3 safety gate remain outstanding.
