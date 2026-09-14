import { NextRequest,NextResponse } from "next/server";
import { requireAdminApiToken,isCloudDeployment } from "../../_server";
import { loadQueue,saveAdjudication } from "./service";
export const dynamic="force-dynamic";
export async function GET(request:NextRequest) {
  if(isCloudDeployment()&&!request.headers.get("x-amzn-oidc-identity")&&!request.headers.get("x-amzn-oidc-data")) {
    const denied=requireAdminApiToken(request);if(denied)return denied;
  }
  try {
    const rows=await loadQueue();
    const eligible=rows.filter(r=>r.adjudicationEligible);
    const exportRow=(r:typeof rows[number])=>({asin:r.asin,ebayItemId:r.ebayItemId,variationId:r.variationId,
      ...r.latestReview,platform_amazon:r.identity.amazon.platform,platform_ebay:r.identity.ebay.platform,
      platform_operator_relationship:r.latestReview.platformRelationship?.operatorRelationship??null,
      platform_relationship_provenance:r.latestReview.platformRelationship,
      platform_corrections:r.latestReview.corrections.filter(c=>c.field==="platform"),pair_verdict:r.latestReview.pairVerdict,
      sourceSnapshotId:r.sourceSnapshotId,frozenEvaluationId:r.snapshotHash,adjudicationExclusionReason:r.adjudicationExclusionReason});
    if(request.nextUrl.searchParams.get("report")==="1") return NextResponse.json({source:"identity_adjudication_queue",total:eligible.length,storedTotal:rows.length,
      positives:eligible.filter(r=>r.latestReview.tierA).map(exportRow),
      negatives:eligible.filter(r=>r.latestReview.pairVerdict==="incorrect").map(exportRow),
      unresolved:eligible.filter(r=>!r.latestReview.tierA&&r.latestReview.pairVerdict!=="incorrect").map(exportRow),
      excluded:rows.filter(r=>!r.adjudicationEligible).map(exportRow)});
    return NextResponse.json({rows,reviewed:eligible.filter(r=>r.latestReview.pairVerdict).length,total:eligible.length,storedTotal:rows.length});
  }catch(error){return NextResponse.json({error:error instanceof Error?error.message:"Queue unavailable"},{status:503});}
}
export async function POST(request:NextRequest) {
  const denied=requireAdminApiToken(request);if(denied)return denied;
  try {const result=await saveAdjudication(await request.json(),request.headers.get("x-amzn-oidc-identity")??"authenticated_admin_api");return NextResponse.json(result,{status:result.status});}
  catch(error){return NextResponse.json({error:error instanceof Error?error.message:"Invalid review"},{status:400});}
}
