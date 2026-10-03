import { NextResponse } from "next/server";
import { createServerSupabaseClient } from "../../../_server";

type Context = { params: Promise<{ opportunityId: string }> };
export const dynamic = "force-dynamic";

export async function GET(_request: Request, context: Context) {
  const { opportunityId } = await context.params;
  const supabase = createServerSupabaseClient();
  const { data: opportunity, error } = await supabase.from("wholesale_opportunities").select("*")
    .eq("opportunity_id", opportunityId).maybeSingle();
  if (error) return json({ error: error.message }, 500);
  if (!opportunity) return json({ error: "Wholesale opportunity not found." }, 404);
  const [product, evaluation, history, decisions, drafts, candidates] = await Promise.all([
    supabase.from("vw_wholesale_supplier_products").select("*").eq("supplier_product_id", opportunity.supplier_product_id).maybeSingle(),
    opportunity.current_evaluation_id ? supabase.from("wholesale_evaluations").select("*").eq("evaluation_id", opportunity.current_evaluation_id).maybeSingle() : Promise.resolve({ data: null, error: null }),
    supabase.from("vw_wholesale_observation_history").select("*").eq("supplier_product_id", opportunity.supplier_product_id).eq("is_superseded", false).order("effective_date", { ascending: false }),
    supabase.from("wholesale_decisions").select("*").eq("opportunity_id", opportunityId).order("created_at", { ascending: false }),
    supabase.from("wholesale_order_candidates").select("*").eq("opportunity_id", opportunityId).order("created_at", { ascending: false }),
    supabase.from("wholesale_amazon_candidates").select("*").eq("supplier_product_id", opportunity.supplier_product_id).eq("marketplace_id", opportunity.marketplace_id).order("rank_position"),
  ]);
  const lookupError = product.error || evaluation.error || history.error || decisions.error || drafts.error || candidates.error;
  if (lookupError) return json({ error: lookupError.message }, 500);
  return json({ opportunity, product: product.data, evaluation: evaluation.data,
    supplierHistory: history.data ?? [], decisions: decisions.data ?? [],
    draftCommitments: drafts.data ?? [], candidates: candidates.data ?? [] });
}
function json(body: unknown, status = 200) { const response = NextResponse.json(body, { status }); response.headers.set("Cache-Control", "no-store"); return response; }
