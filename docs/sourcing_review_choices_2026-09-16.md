# Independent parser feedback and Closest Excluded routing

## Behavior

Closest Excluded review separates three decisions:

1. Parser assessment: not reviewed, read the source correctly, parsing error, or unsure.
2. Source accuracy and product identity: seller listing error is separate from parser correctness; the existing correct/incorrect/unsure pair verdict, evidence sources, notes and field corrections remain available.
3. Destination: Save and keep in Closest Excluded, or Move confirmed match to Buy List. No profitability override is offered, as explicitly requested by the operator.

For the Mortal Kombat example, an operator can report correct parsing plus a seller listing error, confirm the exact pair, and choose its destination. This implementation does not itself create a verdict or move that production listing. Raw parser diagnostics remain intact; a successful promotion records a separate exact-pair operator override and presentation decision.

Saving to Closest Excluded appends evidence without changing opportunity status. Explicitly kept reviews remain visible after reload despite the prior blanket reviewed-row exclusion, and display a saved operator-choice explanation. They are not also classified into Business Excluded. Legacy review behavior outside this explicit choice remains unchanged. Unknown/unsure identity cannot move to Buy List. The separate normal Save feedback button is omitted in Closest Excluded so it cannot silently hide the row.

## Safety and economics

`sourcing_save_review_choice` wraps the existing `sourcing_save_review` transaction. It retains its actor/request fingerprint checks, idempotency, append-only review, source snapshot and evidence semantics. A hash from `sourcing_closeout_capture` is captured when loading review evidence. Under the existing guard's NOWAIT table-lock pattern, source, operator, settings, holds and inventory inputs must still match at save time. Contention and staleness fail visibly; dialog selections remain available.

Promotion requires a rejected row (or an open row explicitly excluded by its presentation decision), a correct exact-pair verdict, no active ASIN/velocity/inventory/ROI hold, no protected pair lifecycle, and no other open opportunity for that ASIN. Required recorded business checks must be complete and passing. Condition, region and delivery failures remain blockers. The stored evaluation must be within 48 hours, the listing active with quantity available, not ended, and not updated after evaluation. Stale or incomplete evidence requires a sourcing refresh; this endpoint makes no provider calls.

Using current stored candidate price/shipping and recorded sale-price/fee evidence, the transaction recomputes the allowable cost under current minimum-profit/ROI settings. It follows the existing scorer's cost-cap and item-only Best Offer policy (full shipping reserved, 95% asking-price ceiling, configured minimum offer percentage). It preserves auction/buy-now/multi-unit distinctions and declined-offer restrictions. A qualifying Best Offer may enter the Buy List when full asking price does not meet ROI. Fees and sale price remain stored evidence, not fresh marketplace quotes. Existing parser rules, scorer runtime, thresholds and hold-release rules are unchanged.

Feedback plus promotion either commit together or fully roll back. The stored routing audit identifies before/after status, opportunity type and absence of profitability override. A new explicit move action can follow an earlier keep decision. Idempotent retries do not add verdicts. A plain parser-correct assessment creates no match verdict and does not turn source-field corrections into parser-failure labels.

## Validation and release

Validated the actual new migration against a network-disabled PostgreSQL 17 disposable database with the existing review and guard migrations. Regression cases cover keep/reload, buy-now, Best Offer, independent parser/source evidence, original parser preservation, replay and conflicting request reuse, weak profitability/current settings changes, uncertain identity, changed source/review, ASIN blocks, protected lifecycle, unavailable listing, unknown shipping, declined offer and condition restrictions. Failed saves leave no review behind.

Actual dialog tests cover both parser/source selectors, independent correction controls, keep/move payloads, disabled uncertain promotion and retained selections with inline failure. Actual Closest Excluded GET tests verify kept confirmations survive action-history filtering/reload, moved pairs disappear and legacy behavior is retained. Existing action API/PostgreSQL/Python analyzer tests and lazy evidence tests pass; TypeScript and focused lint pass. The production Docker build passed as `mbop-web:review-choices-local`; it was not pushed or deployed. Existing dependency audit findings were emitted; dependencies are unchanged. The disposable test container was stopped after validation.

## Production release

On September 16 UTC (September 15 Pacific), the operator authorized deployment. The linked target was verified as MBOP/College Planner project `froeucjkcepuhgwisped`. All 22 existing migrations matched before applying the sole pending additive migration, `supabase/migrations/20260916035218_mbop_sourcing_review_choices.sql`, through `supabase db push --linked --yes`. All 23 migrations matched afterward. A read-only catalog query verified the 12-argument function exists, uses security invoker, denies execution to anon/authenticated, and permits service_role. The CLI emitted a local pg-delta catalog-cache certificate warning after application; the remote ledger and function checks passed.

Web task revision **157** was deployed from source **`d708139ff982`**, with pinned ECR image digest **`sha256:6daa4f1c5025be9eedd5bb26d12843d3eae5f2bf4bf92fcd8b845751e6e9a23a`**. The deployment Docker build passed compilation and TypeScript. New task `174036fb3c3a447392391c967efbaf81` reached RUNNING with a healthy load-balancer target at `172.31.35.84`; its startup log reported Ready in 491ms without errors. Final rollout evidence is recorded in the ignored artifact `tmp/ops-20260915/web157-deployment.json`.

Final ECS rollout state was **COMPLETED**, with only revision 157 deployed, desired/running count 1 and pending count 0. The new target remained healthy; the removed old task's target was finishing its normal load-balancer drain.

Authenticated production dialog verification was unavailable because computer-use reported no browser sessions. Component/API/transaction tests and AWS health checks do not substitute for a production click-through. No production pair verdict or opportunity was changed to test this release. No sourcing run, provider search, marketplace write or scheduler change was performed.

## Move-button usability follow-up

The operator screenshot showed an unchanged pair verdict with a green-looking disabled Move button. The follow-up makes the required Product match label explicit for Closest Excluded, visibly greys the disabled button, gives the exact Correct match selection instruction, and repeats save errors beside the footer actions. Corrections do not silently confirm a pair; promotion and profitability protections remain unchanged. Actual dialog regressions cover disabled appearance, prerequisite guidance, enabled confirmed state and footer error visibility. Deployment verification follows below.

Follow-up deployed as web158 from source `0e2be14edc2e`, image `sha256:20d4dfa4e1fa908c1c516dcb459a40e0f730b1462c0161f0e3cea9965ac4b973`. Actual dialog tests, TypeScript and the production Docker build passed. New task `13db47e2ba344e9c81e3f2572cf42547` reported Ready in 494ms and its target `172.31.31.33` was healthy. No database migration or scheduler change was needed. Authenticated browser verification remains unavailable.
Final web158 ECS rollout: COMPLETED, desired/running 1, pending 0, new target healthy; old target finishing its normal drain. Evidence: tmp/ops-20260915/web158-deployment.json.

## Specific review explanations

Closest Excluded now replaces the generic review-threshold label/summary with the recorded decision-trace stage and specific matching warnings/failures. Final recommendation, confidence summary and presentation/profitability context entries are excluded from that explanation to avoid repeating the generic gate outcome. Multiple specific reasons are retained; missing trace data is stated explicitly. The review_threshold code remains stable for filters. No evaluation, eligibility or routing is changed. Actual GET regressions cover the Just Dance edition reason, multiple reasons, legacy/missing traces and unchanged category filtering; Business Excluded tests and TypeScript pass.
Deployed as web159 from source 5e3b627e56f7, image sha256:af81fbc0b085121c4eb15f779ee45d225373eea0aac0af8cc11ee78e193fa04f. Production Docker build passed. Final ECS rollout COMPLETED with desired/running 1, pending 0; task 24c5fbfd967b4ed0913c469dde3f4608 and its sole load-balancer target 172.31.36.132 healthy. Evidence: tmp/ops-20260915/web159-deployment.json. Authenticated browser click-through remains unavailable.
