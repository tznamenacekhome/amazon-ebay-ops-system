import type { ExclusionReason } from "../../sourcing/types";
import type { LatestReview } from "./reviewActions";
type Obj=Record<string,unknown>;
const obj=(v:unknown):Obj=>v&&typeof v==="object"&&!Array.isArray(v)?v as Obj:{};
export type BusinessCheck={code:string;label:string;actual:unknown;threshold:unknown;units:string;result:string;blocking:boolean;scenario:string;evaluatedAt:string|null;source:string;explanation?:string};
export type VelocityHold={asin:string|null;current_velocity:number|null;required_velocity:number|null;metric_window_days:number|null;last_evaluated_at:string|null;status:string|null};

export function selectRecordedHold(row:{asin:string;ebay_item_id?:string|null;status:string|null},actions:Obj[]):Obj|undefined {
  return actions.find(action=>action.asin===row.asin && (row.status==="inventory_snoozed"
    ? ["inventory_snoozed","inventory_snooze"].includes(String(action.action_type))
    : action.ebay_item_id===row.ebay_item_id && ["roi_snoozed","watching","watch"].includes(String(action.action_type))));
}

export function recordedHoldCheck(row:{status:string|null;sourcing_seed_asins?:{current_inventory_units:number|null}|null},action:Obj|undefined):BusinessCheck[] {
  if(!action)return [];
  const context=obj(action.raw_action_context);
  if(row.status==="inventory_snoozed" && ["inventory_snoozed","inventory_snooze"].includes(String(action.action_type))) {
    const hold=obj(context.inventorySnooze);
    return [{code:"inventory_hold",label:"Inventory sell-through hold",actual:row.sourcing_seed_asins?.current_inventory_units??null,threshold:hold.representAtUnits??null,units:"units",result:"fail",blocking:true,scenario:"active operator hold",evaluatedAt:null,source:"sourcing_actions.inventorySnooze",explanation:`Hold recorded ${action.created_at??"time unavailable"}. Recorded inventory may be stale; the existing sync owns release.`}];
  }
  if(["roi_snoozed","watching"].includes(row.status??"") && ["roi_snoozed","watching","watch"].includes(String(action.action_type)) && (action.expected_purchase_cost!=null||action.required_max_landed_cost!=null)) {
    return [{code:"roi_hold",label:"Price-improvement hold",actual:action.expected_purchase_cost??null,threshold:action.required_max_landed_cost??null,units:"USD",result:"fail",blocking:true,scenario:"recorded purchase cost / recorded landed-cost cap",evaluatedAt:String(action.created_at??"")||null,source:"sourcing_actions",explanation:"The existing release rule requires an improved purchase price or improved sale-price cost cap. These are recorded hold inputs, not a fresh threshold evaluation."}];
  }
  return [];
}

export function businessExclusion(row:{asin?:string;status:string|null;matching_diagnostics_json:unknown;sourcing_seed_asins?:{asin:string|null}|null;sourcing_ebay_candidates?:{listing_status:string|null}|null},review:LatestReview|undefined,hold?:VelocityHold,blocked=false):ExclusionReason|null {
  if (["dismissed","purchased","purchased_pending_match","matched","matched_to_purchase","completed","cancelled"].includes(row.status??"")) return null;
  const diagnostics=obj(row.matching_diagnostics_json);
  const rules=obj(diagnostics.static_rules);
  const identity=obj(rules.identity_comparison??diagnostics.identity_comparison);
  const canonical=row.asin && row.sourcing_seed_asins?.asin===row.asin ? obj(identity.evidenceDecision).productIdentityVerdict : "unknown";
  const verdict=review?.pairVerdict;
  if (verdict ? verdict!=="correct" : canonical!=="match") return null;
  const checks=(Array.isArray(diagnostics.businessEligibilityChecks)?diagnostics.businessEligibilityChecks:[]) as BusinessCheck[];
  const failed=checks.filter(check=>check.blocking===true&&["fail","unknown"].includes(check.result));
  if(row.sourcing_ebay_candidates?.listing_status === "ended")failed.push({code:"listing_ended",label:"Listing unavailable",actual:"ended",threshold:"active",units:"",result:"fail",blocking:true,scenario:"stored availability check",evaluatedAt:null,source:"sourcing_ebay_candidates.listing_status"});
  if (hold?.status==="active") failed.unshift({code:"sales_velocity_suppression",label:"Sales velocity suppression",actual:hold.current_velocity,threshold:hold.required_velocity,units:"units/month",result:"fail",blocking:true,scenario:"active ASIN hold",evaluatedAt:hold.last_evaluated_at,source:"sourcing_sales_velocity_suppressions",explanation:"Active hold. Synced metric refresh owns release; match confirmation does not release it."});
  if(blocked)failed.unshift({code:"asin_blocked",label:"ASIN blocked",actual:"blocked",threshold:"not blocked",units:"",result:"fail",blocking:true,scenario:"active ASIN restriction",evaluatedAt:null,source:"sourcing_blocked_asins"});
  if(!failed.length)return null;
  const reasons=failed.map(check=>({code:check.code,label:check.label,summary:`${check.actual??"Data unavailable"}${check.units?` ${check.units}`:""}; required: ${check.threshold??"Data unavailable"}${check.units?` ${check.units}`:""}. ${check.scenario}. ${check.explanation??""} Evaluated: ${check.evaluatedAt??"time unavailable"}.`,source:check.source,severity:"other_eligibility_gate" as const,category:"business",diagnosticKeys:[`businessEligibilityChecks.${check.code}`]}));
  return {...reasons[0],eligible:false,finalRecommendation:null,finalStatus:row.status,secondaryReasons:reasons.slice(1),supportingSignals:[verdict==="correct"?"Exact pair confirmed by operator":"Canonical positive identity evidence"]};
}
