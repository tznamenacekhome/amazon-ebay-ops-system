import { createHash } from "node:crypto";
import { adjudicationExclusion, normalizePlatformRelationships } from "../../../sourcing/adjudication/evidence";
import queueData from "./queue.json";
import { supabase } from "../_supabase";
import { buildDiagnosticComparison, type DiagnosticComparisonRow } from "../diagnosticComparison";
import { normalizeMatchingFeedback } from "../matchingFeedback";
import { openingCell, reviewFieldKeys, type SavedCorrection } from "../../../sourcing/reviewFields";

type RecordValue = Record<string, unknown>;
const record = (v: unknown): RecordValue => v && typeof v === "object" && !Array.isArray(v) ? v as RecordValue : {};
export const queue = queueData;
export type QueueRow = typeof queue[number];
export type Action = {action_id:string;asin:string;ebay_item_id:string;created_at:string;listing_snapshot_id:string;raw_action_context:RecordValue};
export type ReviewState = {revision:string;actions:Action[]};
const text = (v:unknown) => v === null || v === undefined || (Array.isArray(v) && !v.length) ? null : typeof v === "string" ? v : JSON.stringify(v);

export function comparisonFor(row:QueueRow) {
  return buildDiagnosticComparison({opportunity:{asin:row.asin},seed:row.reference,candidate:row.candidate,
    diagnostics:{identity_comparison:row.identity,canonicalDecision:{version:row.identity.version,evaluationId:row.snapshotHash,evaluatedAt:row.sourceTimestamp}}});
}
export function additionalRows(row:QueueRow):DiagnosticComparisonRow[] {
  return [
    {key:"derived_base",label:"Derived base product",amazon:text(row.identity.amazon.coreProduct),ebay:text(row.identity.ebay.coreProduct)},
    {key:"included_contents",label:"Included contents",amazon:text(row.identity.amazon.includedContents),ebay:text(row.identity.ebay.includedContents)},
    {key:"release_year",label:"Assigned release year",amazon:text(record(row.identity.amazon.assignedMetadata).release_year),ebay:text(record(row.identity.ebay.assignedMetadata).release_year)},
  ].map(r=>({...r,kind:"identity" as const,evidence:"Stored parser evidence; corrections are separately recorded and do not recompute this frozen evaluation."}));
}
export function summarize(row:QueueRow,state:ReviewState) {
  const actions=[...state.actions].sort((a,b)=>b.created_at.localeCompare(a.created_at)||b.action_id.localeCompare(a.action_id));
  const listingId=(id:string)=>id.replace(/^v1\|/," ").trim().split("|")[0];
  const pair=actions.filter(a=>a.ebay_item_id===row.ebayItemId || (listingId(a.ebay_item_id)===listingId(row.ebayItemId) && (!a.ebay_item_id.startsWith("v1|")||!row.ebayItemId.startsWith("v1|"))));
  const verdict=pair.find(a=>["correct","incorrect","unsure"].includes(String(record(a.raw_action_context.matchingFeedback).pairVerdict)));
  const context=verdict?.raw_action_context;
  const applicable=verdict?.ebay_item_id===row.ebayItemId && context?.source==="identity_adjudication_queue" && context?.queueSnapshotHash===row.snapshotHash;
  const corrections:SavedCorrection[]=[];
  for(const action of actions) {
    const context=action.raw_action_context;
    if(context.source==="identity_adjudication_queue" && !queue.some(q=>q.snapshotHash===context.queueSnapshotHash)) continue;
    for(const correction of (record(context.matchingFeedback).corrections ?? []) as SavedCorrection[]) {
      if(action.ebay_item_id!==row.ebayItemId && !(correction.side==="amazon"&&correction.scope==="asin")) continue;
      if(!corrections.some(c=>c.side===correction.side&&c.field===correction.field)) corrections.push({...correction,actionId:action.action_id,recordedAt:action.created_at});
    }
  }
  const pairVerdict=applicable ? String(record(context?.matchingFeedback).pairVerdict) : null;
  const newerCorrection=Boolean(verdict&&(corrections.some(c=>(c.recordedAt??"")>verdict.created_at) || pair.some(a=>a.created_at>verdict.created_at && ((record(a.raw_action_context.matchingFeedback).flaggedFields??[]) as unknown[]).length>0)));
  const relationshipAction=pair.find(a=>Array.isArray(record(a.raw_action_context.matchingFeedback).fieldRelationships) && (record(a.raw_action_context.matchingFeedback).fieldRelationships as {field:string}[]).some(r=>record(r).field==="platform"));
  let platformRelationship=null;
  let relationshipInvalid=false;
  if(relationshipAction) {
    const ctx=relationshipAction.raw_action_context;
    try {
      if(relationshipAction.ebay_item_id!==row.ebayItemId || ctx.source!=="identity_adjudication_queue" || ctx.queueSnapshotHash!==row.snapshotHash) throw new Error("Unverified relationship source");
      const feedback=normalizePlatformRelationships(record(ctx.matchingFeedback).fieldRelationships)[0];
      if(feedback) platformRelationship={...feedback,actor:ctx.actor??null,reviewedAt:relationshipAction.created_at,actionId:relationshipAction.action_id,snapshotId:relationshipAction.listing_snapshot_id,evaluationId:ctx.queueSnapshotHash,source:ctx.source};
    } catch {relationshipInvalid=true;}
  }
  const newerRelationship=Boolean(verdict&&relationshipAction&&relationshipAction.created_at>verdict.created_at);
  const tierA=!adjudicationExclusion(row) && !relationshipInvalid && !newerRelationship && pairVerdict==="correct" && context?.identityAttested===true && context?.variationVerified===true && !newerCorrection;
  return {pairVerdict,actionId:verdict?.action_id??null,createdAt:verdict?.created_at??null,
    feedback:context ? record(context.matchingFeedback) : null,corrections,tierA,platformRelationship,
    variationResolution:context?.variationResolution??null,actor:context?.actor??null,snapshotId:verdict?.listing_snapshot_id??null,
    evaluationId:context?.queueSnapshotHash??null,source:context?.source??null,
    requiresReReview:Boolean(relationshipInvalid || verdict&&(!applicable||newerCorrection||newerRelationship)),
    lineage:pair.map(a=>({actionId:a.action_id,createdAt:a.created_at,snapshotId:a.listing_snapshot_id,
      verdict:record(a.raw_action_context.matchingFeedback).pairVerdict,actor:a.raw_action_context.actor,
      source:a.raw_action_context.source,evaluationId:a.raw_action_context.queueSnapshotHash,fieldRelationships:record(a.raw_action_context.matchingFeedback).fieldRelationships??[]}))};
}
export async function loadState(row:QueueRow):Promise<ReviewState> {
  const {data,error}=await supabase.rpc("sourcing_adjudication_state",{p_asin:row.asin,p_ebay_item_id:row.ebayItemId});
  if(error) throw new Error(error.message);
  return data as ReviewState;
}
export async function loadQueue() {
  return Promise.all(queue.map(async row=>{
    let state:ReviewState={revision:"unavailable",actions:[]};let unavailableReason:string|null=null;
    try {state=await loadState(row);} catch(error) {unavailableReason=error instanceof Error?error.message:"Evidence storage unavailable";}
    return {...row,adjudicationEligible:!adjudicationExclusion(row),adjudicationExclusionReason:adjudicationExclusion(row),available:!unavailableReason,unavailableReason,revision:state.revision,diagnosticComparison:comparisonFor(row),additionalRows:additionalRows(row),latestReview:summarize(row,state)};
  }));
}
export async function saveAdjudication(body:RecordValue,actor:string) {
  const row=queue.find(q=>q.queueId===body.queueId);
  if(!row) throw new Error("The requested row is not in this exact 16-row queue.");
  if(row.asin!==body.expectedAsin || row.ebayItemId!==body.expectedEbayItemId || row.snapshotHash!==body.expectedSnapshotHash) return {status:409,error:"Frozen pair/evaluation changed. Reload before saving."};
  if(adjudicationExclusion(row)) return {status:409,error:"Excluded from adjudication / informational only. No review was saved."};
  const requestId=String(body.requestId??"");
  if(!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(requestId)) throw new Error("Stable request ID required.");
  const feedback=normalizeMatchingFeedback({...record(body.feedback),version:"matching_feedback_v3",allAssumptionsCorrect:false});
  if(feedback.pairVerdict==="correct" && body.identityAttested!==true) throw new Error("Confirm the exact product identity before saving Confirm Match.");
  const comparison=comparisonFor(row);
  const state=await loadState(row);
  // A retry is checked atomically by fingerprint in the RPC, before its revision check.
  if(!state.actions.some(a=>a.action_id===requestId)) {
    if(body.expectedRevision!==state.revision) return {status:409,error:"A newer review or correction exists. Reload; your edits have not been saved."};
    const latest=summarize(row,state);
    for(const correction of feedback.corrections) {
      const field=[...comparison.rows,...additionalRows(row)].find(r=>reviewFieldKeys[r.key]===correction.field);
      if(!field) throw new Error("Unsupported correction field.");
      if(!(feedback.flaggedFields??[]).includes(correction.field) && !(correction.field==="platform" && feedback.fieldRelationships?.length)) throw new Error("Mark the corrected field Wrong before editing.");
      const opening=openingCell(field,correction.side,latest.corrections);
      correction.before={value:opening.value,state:opening.state,actionId:opening.correction?.actionId??null};
    }
  }
  const context={source:"identity_adjudication_queue",sourceTab:"Identity Adjudication",queueId:row.queueId,
    queueSnapshotHash:row.snapshotHash,snapshotPolicy:"frozen_historical",sourceSnapshotId:row.sourceSnapshotId,
    sourceTimestamp:row.sourceTimestamp,matchingFeedback:feedback,diagnosticComparison:comparison,
    platformEvidence:{amazon:row.identity.amazon.platform,ebay:row.identity.ebay.platform},
    pair:{asin:row.asin,ebayItemId:row.ebayItemId,variationId:row.variationId,opportunityId:row.opportunityId},
    purchaseItemId:row.purchaseItemId,receivingId:row.receivingId,
    // A negative pair verdict never asserts that the listing is the ASIN product.
    identityAttested:feedback.pairVerdict==="correct" && body.identityAttested===true,variationVerified:body.variationVerified===true,
    variationResolution:body.variationVerified===true ? (row.variationId && row.variationId!=="0" ? "verified_stored_variation" : "operator_confirmed_not_applicable") : "unknown",
    learningScope:"exact_pair",build:process.env.MBOP_BUILD_SHA??"local",evaluation:comparison.evaluation,
    notes:String(body.notes??"").slice(0,4000)};
  const snapshot={asin:row.asin,ebay_item_id:row.ebayItemId,ebay_legacy_item_id:row.ebayLegacyItemId,
    amazon_title:row.reference.amazon_title,amazon_system:row.reference.system,ebay_title:row.candidate.ebay_title,
    ebay_description:row.candidate.raw_ebay_json.description,ebay_item_specifics_json:record(row.candidate.raw_ebay_json).localizedAspects??[],
    raw_ebay_json:row.candidate.raw_ebay_json};
  const {data,error}=await supabase.rpc("sourcing_save_adjudication",{p_request_id:requestId,p_asin:row.asin,
    p_ebay_item_id:row.ebayItemId,p_expected_revision:body.expectedRevision,p_actor:actor,
    p_request_hash:createHash("sha256").update(JSON.stringify(body)).digest("hex"),p_context:context,p_snapshot:snapshot});
  if(error) return {status:error.code==="40001"?409:400,error:error.message};
  // The write has committed. A readback failure must not be reported as a failed save.
  try {
    const current=await loadState(row);
    return {status:200,review:data,reviewState:{revision:current.revision,latestReview:summarize(row,current)}};
  } catch(error) {
    return {status:200,review:data,refreshError:error instanceof Error?error.message:"Saved review could not be reloaded."};
  }
}
