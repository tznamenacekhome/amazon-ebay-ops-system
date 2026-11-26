import { sourcingPlatformEligibility, sourcingPlatformPolicyVersion } from '../sourcing/platformPolicy';
import type { createServerSupabaseClient } from '../_server';

type RecordValue=Record<string,unknown>;
const object=(v:unknown):RecordValue=>v&&typeof v==='object'&&!Array.isArray(v)?v as RecordValue:{};
export function wholesalePlatformEligibility(value: unknown) {
  const evaluation=object(value), evidence=object(evaluation.source_evidence_json);
  const recorded=object(evidence.sourcing_platform_policy);
  if(recorded.version===sourcingPlatformPolicyVersion&&recorded.result!=='pass')return {version:String(recorded.version),result:String(recorded.result),reason:String(recorded.reason),platforms:[]};
  return sourcingPlatformEligibility({asin:evaluation.asin,amazon_title:evidence.amazon_title,
    raw_context_json:{inferred_system:evidence.amazon_platform,amazon_catalog_identity:evidence.amazon_catalog_identity}});
}

export async function filterWholesalePlatforms<T extends {current_evaluation_id?:string|null}>(
  db: ReturnType<typeof createServerSupabaseClient>, rows:T[],
) {
  const ids=[...new Set(rows.map(r=>r.current_evaluation_id).filter((v):v is string=>Boolean(v)))];
  const allowed=new Set<string>();
  for(let index=0;index<ids.length;index+=100) {
    const {data,error}=await db.from('wholesale_evaluations').select('evaluation_id,asin,source_evidence_json').in('evaluation_id',ids.slice(index,index+100));
    if(error)throw new Error(error.message);
    for(const value of data??[]) {const evaluation=object(value);if(wholesalePlatformEligibility(evaluation).result==='pass')allowed.add(String(evaluation.evaluation_id));}
  }
  return rows.filter(row=>row.current_evaluation_id&&allowed.has(row.current_evaluation_id));
}
