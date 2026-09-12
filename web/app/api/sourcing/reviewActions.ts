import { createHash } from "node:crypto";
import { NextResponse } from "next/server";
import { supabase } from "./_supabase";
import { buildDiagnosticComparison } from "./diagnosticComparison";
import { buildListingSnapshot } from "./matchingIntelligence";
import { normalizeMatchingFeedback, reviewSemantics } from "./matchingFeedback";
import { dismissReasons } from "../../sourcing/matchingTaxonomy";

type RecordValue = Record<string, unknown>;
const record = (v: unknown): RecordValue => v && typeof v === "object" && !Array.isArray(v) ? v as RecordValue : {};
export const reviewActions = new Set(["dismiss","block_asin","mark_valid_match","confirm_exclusion","save_match_feedback"]);

export async function saveMatchingReview(request: Request, opportunity: RecordValue, body: RecordValue) {
  try {
    const requestId = String(body.requestId ?? "");
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(requestId)) throw new Error("A stable review request ID is required.");
    const actionType = String(body.actionType);
    if (body.expectedAsin !== opportunity.asin || body.expectedEbayItemId !== opportunity.ebay_item_id || (body.expectedCandidateId ?? null) !== (opportunity.candidate_id ?? null)) {
      return NextResponse.json({error:"The displayed pair changed. Reload before saving feedback."},{status:409});
    }
    const reason = actionType === "block_asin" ? "asin_blocked" : String(body.reason ?? "") || null;
    if (["dismiss","confirm_exclusion"].includes(actionType) && !dismissReasons.some(([value]) => value === reason)) throw new Error("Select an existing dismissal reason.");
    const feedback = normalizeMatchingFeedback({...record(body.diagnosticsFeedback),version:"matching_feedback_v3"});
    const semantics = reviewSemantics(actionType,reason,feedback.pairVerdict);
    feedback.pairVerdict = semantics.pairVerdict as typeof feedback.pairVerdict;
    const candidate = record(opportunity.sourcing_ebay_candidates);
    const seed = record(opportunity.sourcing_seed_asins);
    const exactSeed = seed.asin === opportunity.asin ? seed : {};
    const comparison = buildDiagnosticComparison({opportunity,seed,candidate,diagnostics:opportunity.matching_diagnostics_json});
    if((body.expectedEvaluationId??null)!==(comparison.evaluation.id??null)) return NextResponse.json({error:"The displayed evaluation changed. Reload before saving."},{status:409});
    feedback.availableEvidenceSources = comparison.rows.filter(row=>row.kind==="evidence"&&(row.amazon||row.ebay)).map(row=>row.evidenceSource).filter((value):value is string=>Boolean(value));
    const fieldKeys: Record<string,string> = {coreGame:"core_game_identity",installment:"installment_number",generation:"generation",theme:"theme",platform:"platform_system",edition:"edition_version",region:"region",packageType:"package_bundle_contents",completeness:"completeness",digitalPhysical:"digital_physical"};
    feedback.corrections = feedback.corrections.map(correction => ({...correction,before:comparison.rows.find(row=>row.key===fieldKeys[correction.field])?.[correction.side] ?? null}));
    const raw = record(candidate.raw_ebay_json);
    const context = {
      actionType,sourceTab:String(body.sourceTab ?? "legacy"),matchingFeedback:feedback,
      feedbackCategory:semantics.category,learningScope:semantics.learningScope,
      pair:{opportunityId:opportunity.opportunity_id,candidateId:opportunity.candidate_id,asin:opportunity.asin,
        ebayItemId:opportunity.ebay_item_id,ebayLegacyItemId:candidate.ebay_legacy_item_id ?? null,
        variationId:String(opportunity.ebay_item_id ?? "").split("|")[2] ?? null,itemGroupId:raw.itemGroupId ?? null},
      diagnosticComparison:comparison,diagnosticVersion:comparison.version,evaluation:comparison.evaluation,
      build:process.env.MBOP_BUILD_SHA ?? "local",notes:typeof body.notes === "string" ? body.notes.slice(0,4000) : null,
      imageClues:Array.isArray(body.imageClues) ? body.imageClues.map(String).slice(0,20) : [],
      availableEvidenceSources:comparison.rows.filter(row=>row.kind==="evidence"&&row.ebay).map(row=>row.evidenceSource),
    };
    const snapshot = buildListingSnapshot({opportunity,candidate,seed:exactSeed,event:"matching_feedback",rawContext:context});
    const hash = createHash("sha256").update(JSON.stringify(body)).digest("hex");
    const actor = request.headers.get("x-amzn-oidc-identity") ?? "authenticated_admin_api";
    const {data,error} = await supabase.rpc("sourcing_save_review",{
      p_opportunity_id:opportunity.opportunity_id,p_request_id:requestId,p_asin:opportunity.asin,p_candidate_id:opportunity.candidate_id,
      p_action_type:actionType,p_reason:reason,p_notes:context.notes,p_actor:actor,p_request_hash:hash,
      p_context:context,p_snapshot:snapshot,p_label:semantics.label,
    });
    if(error) return NextResponse.json({error:error.message},{status:error.code==="40001" ? 409 : 500});
    return NextResponse.json({review:data,opportunity,feedback});
  } catch(error) {
    return NextResponse.json({error:error instanceof Error ? error.message : "Invalid review"},{status:400});
  }
}

export type LatestReview = {asin:string;ebayItemId:string;pairVerdict:string|null;feedback:RecordValue|null;actionId:string|null;createdAt:string|null;corrections?:unknown[]};
export async function fetchLatestReviews(rows: Array<{asin:string;ebay_item_id?:string|null}>) {
  const pairs = [...new Map(rows.filter(row=>row.ebay_item_id).map(row=>[`${row.asin}|${row.ebay_item_id}`,{asin:row.asin,ebay_item_id:row.ebay_item_id}])).values()];
  const output = new Map<string,LatestReview>();
  for(let index=0;index<pairs.length;index+=100) {
    const {data,error}=await supabase.rpc("sourcing_latest_reviews",{p_pairs:pairs.slice(index,index+100)});
    if(error) throw new Error(`Could not load latest matching feedback: ${error.message}`);
    for(const row of data as LatestReview[] ?? []) if(row.actionId || row.corrections?.length) output.set(`${row.asin}|${row.ebayItemId}`,row);
  }
  return output;
}
