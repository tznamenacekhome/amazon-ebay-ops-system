const record = (value: unknown): Record<string, unknown> => value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string,unknown> : {};

/** Missing edition evidence is a near miss only after independent business gates. */
export function editionNearMissAllowed(value: unknown, listingStatus: string | null | undefined, projectedVersion?: string | null) {
  const diagnostics=record(value), identity=record(record(diagnostics.static_rules).identity_comparison);
  const comparisons=record(identity.comparisons), edition=record(comparisons.edition), policy=record(edition.policy);
  const conditionReview=record(record(diagnostics.static_rules).condition_review).result==='review';
  if((policy.version??projectedVersion)!=='sourcing_edition_policy_v1') return true;
  const rules=record(diagnostics.static_rules);
  if(Array.isArray(rules.hard_blocks)&&rules.hard_blocks.length) return false;
  if(record(identity.evidenceDecision).productIdentityVerdict==='non-match') return false;
  if(edition.result==='conflict') return false;
  if(record(record(diagnostics.static_rules).condition_mismatch).result==='blocked') return false;
  const decision=record(diagnostics.presentationDecision);
  const reasons=[record(decision.primaryReason),...(Array.isArray(decision.secondaryReasons)?decision.secondaryReasons.map(record):[])];
  if(reasons.some(reason=>reason.code==='condition_unacceptable')) return false;
  const reviewCodes=['edition_not_corroborated','contents_not_corroborated','condition_review'];
  if(!conditionReview&&!reviewCodes.includes(String(policy.code))&&!reasons.some(reason=>reviewCodes.includes(String(reason.code)))) return true;
  if(Object.values(comparisons).some(value=>record(value).result==='conflict')) return false;
  if(!['active','live'].includes(String(listingStatus))) return false;
  if(diagnostics.seller_status==='avoid') return false;
  const checks=Array.isArray(diagnostics.businessEligibilityChecks)?diagnostics.businessEligibilityChecks.map(record):[];
  if(checks.some(check=>check.blocking===true&&check.result!=='pass')) return false;
  return ['shipping','minimum_profit','minimum_roi'].every(code=>checks.some(check=>check.code===code&&check.result==='pass'));
}
