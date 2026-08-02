-- MBOP sourcing diagnostics / receiving feedback outcomes.
--
-- Additive-only constraint replacement. Existing values are preserved.

alter table public.matching_intelligence_receiving_outcomes
  drop constraint if exists matching_intelligence_receiving_outcomes_outcome_check;

alter table public.matching_intelligence_receiving_outcomes
  add constraint matching_intelligence_receiving_outcomes_outcome_check
  check (outcome in (
    'correct_item',
    'wrong_item',
    'wrong_condition',
    'packaging_issue',
    'incomplete_item',
    'listed_successfully',
    'sourcing_false_positive'
  ));
