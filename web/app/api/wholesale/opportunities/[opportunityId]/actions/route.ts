import { NextResponse } from "next/server";
import { createServerSupabaseClient, requireAdminApiToken } from "../../../../_server";

type Context = { params: Promise<{ opportunityId: string }> };
type Body = { action?: string; evaluationId?: string; reason?: string; notes?: string; quantity?: number; requestId?: string; orderCandidateId?: string };

export async function POST(request: Request, context: Context) {
  const adminError = requireAdminApiToken(request);
  if (adminError) return adminError;
  const { opportunityId } = await context.params;
  const body = (await request.json().catch(() => ({}))) as Body;
  const supabase = createServerSupabaseClient();
  let result;
  if (["temporary_pass", "hard_pass", "reverse_pass"].includes(body.action || "")) {
    if (!body.evaluationId) return json({ error: "evaluationId is required." }, 400);
    result = await supabase.rpc("wholesale_apply_decision", {
      p_opportunity_id: opportunityId, p_evaluation_id: body.evaluationId,
      p_action: body.action, p_reason_code: body.reason ?? null,
      p_notes: body.notes ?? null, p_actor: "wholesale-ui",
    });
  } else if (body.action === "add_to_order") {
    if (!body.evaluationId || !Number.isInteger(body.quantity) || Number(body.quantity) <= 0 || !body.requestId) {
      return json({ error: "Current evaluation, positive integer quantity, and requestId are required." }, 400);
    }
    result = await supabase.rpc("wholesale_upsert_draft_commitment", {
      p_opportunity_id: opportunityId, p_evaluation_id: body.evaluationId,
      p_quantity: body.quantity, p_idempotency_key: body.requestId, p_actor: "wholesale-ui",
    });
  } else if (body.action === "remove_draft") {
    if (!body.orderCandidateId) return json({ error: "orderCandidateId is required." }, 400);
    result = await supabase.rpc("wholesale_release_draft_commitment", {
      p_order_candidate_id: body.orderCandidateId, p_actor: "wholesale-ui",
    });
  } else return json({ error: "Unsupported action." }, 400);
  if (result.error) return json({ error: result.error.message }, 409);
  return json({ result: result.data });
}
function json(body: unknown, status = 200) { const response = NextResponse.json(body, { status }); response.headers.set("Cache-Control", "no-store"); return response; }
