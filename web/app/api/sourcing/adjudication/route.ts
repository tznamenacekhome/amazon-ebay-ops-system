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
    if(request.nextUrl.searchParams.get("report")==="1") return NextResponse.json({source:"identity_adjudication_queue",
      positives:rows.filter(r=>r.latestReview.tierA).map(r=>({asin:r.asin,ebayItemId:r.ebayItemId,variationId:r.variationId,...r.latestReview})),
      negatives:rows.filter(r=>r.latestReview.pairVerdict==="incorrect").map(r=>({asin:r.asin,ebayItemId:r.ebayItemId,variationId:r.variationId,...r.latestReview})),
      unresolved:rows.filter(r=>!r.latestReview.tierA&&r.latestReview.pairVerdict!=="incorrect").map(r=>({asin:r.asin,ebayItemId:r.ebayItemId,...r.latestReview}))});
    return NextResponse.json({rows,reviewed:rows.filter(r=>r.latestReview.pairVerdict).length,total:rows.length});
  }catch(error){return NextResponse.json({error:error instanceof Error?error.message:"Queue unavailable"},{status:503});}
}
export async function POST(request:NextRequest) {
  const denied=requireAdminApiToken(request);if(denied)return denied;
  try {const result=await saveAdjudication(await request.json(),request.headers.get("x-amzn-oidc-identity")??"authenticated_admin_api");return NextResponse.json(result,{status:result.status});}
  catch(error){return NextResponse.json({error:error instanceof Error?error.message:"Invalid review"},{status:400});}
}
