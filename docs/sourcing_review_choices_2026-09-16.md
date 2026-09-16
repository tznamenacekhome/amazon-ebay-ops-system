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

Migration: `supabase/migrations/20260916035218_mbop_sourcing_review_choices.sql`. It is additive and has been applied only to the disposable local database. Before production activation, verify the shared target and reconcile `supabase migration list`, apply this migration through the documented MBOP workflow, then deploy the web release and verify the authenticated review flow. No production review writes, sourcing runs, provider searches, scheduler changes or web deployment were performed for this implementation. Production remains web156.
