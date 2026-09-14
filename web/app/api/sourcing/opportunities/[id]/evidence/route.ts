import { NextRequest, NextResponse } from "next/server";
import { supabase } from "../../../_supabase";
import { buildDiagnosticComparison } from "../../../diagnosticComparison";
import { fetchLatestReviews } from "../../../reviewActions";
export async function GET(request: NextRequest, context: { params: Promise<{ id: string }> }) {
  const headers = { "Cache-Control": "no-store" };
  try {
    const { id } = await context.params;
    if (!/^[0-9a-f-]{36}$/i.test(id)) return NextResponse.json({ error: "Invalid opportunity ID." }, { status: 400, headers });
    const { data: row, error } = await supabase.from("sourcing_opportunities")
      .select("*,sourcing_seed_asins(*),sourcing_ebay_candidates(*)").eq("opportunity_id", id).single();
    if (error) throw new Error(error.message);
    const seed = row.sourcing_seed_asins ?? {};
    let title = seed.asin === row.asin ? seed.amazon_title : null;
    if (!title) {
      const { data, error: titleError } = await supabase.from("vw_latest_keepa_product_snapshot").select("title").eq("asin", row.asin).limit(1);
      if (titleError) throw new Error(titleError.message);
      title = data?.[0]?.title ?? "";
    }
    const reviews = await fetchLatestReviews([row]);
    return NextResponse.json({
      opportunityId: row.opportunity_id, asin: row.asin, candidateId: row.candidate_id,
      ebayItemId: row.sourcing_ebay_candidates?.ebay_item_id ?? null,
      reviewEvidenceLoaded: true, matchingDiagnostics: row.matching_diagnostics_json,
      diagnosticComparison: buildDiagnosticComparison({ opportunity: { ...row, amazon_title: title }, seed, candidate: row.sourcing_ebay_candidates ?? {}, diagnostics: row.matching_diagnostics_json }),
      latestReview: reviews.get(`${row.asin}|${row.ebay_item_id}`) ?? null,
    }, { headers });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "Unable to load review evidence." }, { status: 500, headers });
  }
}
