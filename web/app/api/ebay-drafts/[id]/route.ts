import { NextResponse } from "next/server";
import { createServerSupabaseClient, requireAdminApiToken } from "../../_server";
import { validateReadyDraft } from "../draftHelpers";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const allowed = new Set(["group_name","grouping_confirmed","listing_kind","title","category_id","category_name","condition_id","condition_name","condition_notes","tested_status","description","quantity","price","item_specifics","required_inputs","identification_status","identification_evidence","visible_flaws","included_items","seller_notes","price_recommendation","comparable_sales"]);
const textFields = new Set(["group_name","category_id","category_name","condition_id","condition_name","condition_notes","title","description","visible_flaws","included_items","seller_notes"]);

export async function PATCH(request: Request, context: { params: Promise<{ id: string }> }) {
  const denied = requireAdminApiToken(request); if (denied) return denied;
  try {
    const { id } = await context.params;
    const payload = await request.json();
    const db = createServerSupabaseClient();
    const { data: draft, error: loadError } = await db.from("ebay_listing_drafts").select("*").eq("id", id).single();
    if (loadError) return NextResponse.json({ error: loadError.message }, { status: 404 });
    const patch: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(payload.fields || {})) {
      if (!allowed.has(key)) continue;
      if (textFields.has(key)) patch[key] = String(value ?? "").slice(0, key === "description" ? 20000 : 2000);
      else patch[key] = value;
    }
    if (payload.photos) {
      for (const photo of payload.photos as Array<Record<string, unknown>>) {
        const fields = { sort_order: Math.max(0, Math.floor(Number(photo.sort_order) || 0)), rotation_degrees: [0,90,180,270].includes(Number(photo.rotation_degrees)) ? Number(photo.rotation_degrees) : 0, role: ["hero","alternate_angle","label","included_item","flaw","unknown"].includes(String(photo.role)) ? photo.role : "unknown" };
        const { error } = await db.from("ebay_listing_draft_photos").update(fields).eq("id", String(photo.id)).eq("draft_id", id);
        if (error) throw error;
      }
    }
    const next = { ...draft, ...patch };
    if (payload.action === "ready") {
      const { count, error } = await db.from("ebay_listing_draft_photos").select("id", { count: "exact", head: true }).eq("draft_id", id);
      if (error) throw error;
      const problems = validateReadyDraft(next, count || 0);
      if (problems.length) return NextResponse.json({ error: "This draft still needs review.", problems }, { status: 422 });
      patch.status = "ready"; patch.reviewed_at = new Date().toISOString();
    } else if (payload.action === "save") patch.status = "draft";
    patch.updated_at = new Date().toISOString();
    const { data, error } = await db.from("ebay_listing_drafts").update(patch).eq("id", id).select("*").single();
    if (error) throw error;
    return NextResponse.json({ draft: data });
  } catch (error) { return NextResponse.json({ error: error instanceof Error ? error.message : "Draft update failed." }, { status: 400 }); }
}
