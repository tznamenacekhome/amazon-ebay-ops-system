import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import ts from 'typescript';
const require=createRequire(import.meta.url),out={};
new Function('require','exports',ts.transpileModule(readFileSync(new URL('./editionPresentation.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText)(require,out);
const {editionNearMissAllowed}=out;
const fixture=()=>({recommendation:'Review',static_rules:{identity_comparison:{comparisons:{edition:{result:'review',policy:{version:'sourcing_edition_policy_v1',code:'edition_not_corroborated'}}}}},businessEligibilityChecks:['shipping','minimum_profit','minimum_roi'].map(code=>({code,result:'pass',blocking:false}))});
for(const code of ['edition_not_corroborated','contents_not_corroborated']){
 const d=fixture();d.static_rules.identity_comparison.comparisons.edition.policy.code=code;
 assert(editionNearMissAllowed(d,'active'));
 for(const bad of ['shipping','minimum_profit','minimum_roi']){const x=structuredClone(d);x.businessEligibilityChecks.find(c=>c.code===bad).result='fail';assert(!editionNearMissAllowed(x,'active'));}
 for(const hold of ['roi_hold','inventory_hold']){const x=structuredClone(d);x.businessEligibilityChecks.push({code:hold,result:'fail',blocking:true});assert(!editionNearMissAllowed(x,'active'));}
 assert(!editionNearMissAllowed(d,'ended'));d.seller_status='avoid';assert(!editionNearMissAllowed(d,'active'));
}
const mismatch=fixture();mismatch.static_rules.identity_comparison.comparisons.edition.result='conflict';assert(!editionNearMissAllowed(mismatch,'active'));
const wrong=fixture();wrong.static_rules.identity_comparison.comparisons.platform={result:'conflict'};assert(!editionNearMissAllowed(wrong,'active'));
assert(editionNearMissAllowed({recommendation:'Review'},'active'),'Legacy presentation is unchanged');
const condition=fixture();
condition.static_rules.identity_comparison.comparisons.edition={result:'match',policy:{version:'sourcing_edition_policy_v1',code:null}};
condition.static_rules.condition_review={result:'review',hits:['shrink-wrap damage']};
assert(editionNearMissAllowed(condition,'active'));
assert(!editionNearMissAllowed(condition,'ended'));
condition.businessEligibilityChecks[0].result='fail';
assert(!editionNearMissAllowed(condition,'active'));
const compact={
 static_rules:{hard_blocks:['not new condition signal: missing the plastic seal'],identity_comparison:{evidenceDecision:{productIdentityVerdict:'match'}}},
 presentationDecision:{primaryReason:{code:'condition_unacceptable'}},
 businessEligibilityChecks:['shipping','minimum_profit','minimum_roi'].map(code=>({code,result:'pass',blocking:false}))
};
assert(!editionNearMissAllowed(compact,'active','sourcing_edition_policy_v1'),'Compact production projection retains condition rejection');
const compactReview=structuredClone(compact);
compactReview.static_rules.hard_blocks=[];
compactReview.presentationDecision.primaryReason.code='contents_not_corroborated';
assert(editionNearMissAllowed(compactReview,'active','sourcing_edition_policy_v1'));
compactReview.businessEligibilityChecks[0].result='fail';
assert(!editionNearMissAllowed(compactReview,'active','sourcing_edition_policy_v1'));
compactReview.businessEligibilityChecks[0].result='pass';
compactReview.decisionTrace=[{reasonCode:'seller_policy',result:'fail'}];
assert(!editionNearMissAllowed(compactReview,'active','sourcing_edition_policy_v1'),'Retained compact seller-avoid trace remains authoritative');
compactReview.decisionTrace[0].result='warning';
assert(editionNearMissAllowed(compactReview,'active','sourcing_edition_policy_v1'),'Seller watch remains reviewable');
condition.businessEligibilityChecks[0].result='pass';
condition.static_rules.condition_mismatch={result:'blocked'};
assert(!editionNearMissAllowed(condition,'active'));
console.log('Edition near misses require recorded economics/shipping, active listing and independent hold/seller/identity gates.');
