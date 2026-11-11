import { NextResponse } from "next/server";
import { createServerSupabaseClient, requireAdminApiToken } from "../../../_server";
import { DRAFT_PHOTO_BUCKET } from "../../draftHelpers";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request, context: { params: Promise<{ id: string }> }) {
  const denied = requireAdminApiToken(request); if (denied) return denied;
  const apiKey = process.env.OPENAI_API_KEY?.trim();
  if (!apiKey) return NextResponse.json({ error: "Photo analysis is not configured on this MBOP server. You can still edit and save the draft manually." }, { status: 503 });
  try {
    const { id } = await context.params;
    const db = createServerSupabaseClient();
    const [{ data: draft, error: draftError }, { data: photos, error: photoError }] = await Promise.all([
      db.from("ebay_listing_drafts").select("id,group_name,listing_kind,seller_notes,ai_analysis").eq("id", id).single(),
      db.from("ebay_listing_draft_photos").select("id,storage_path,mime_type,sort_order,role").eq("draft_id", id).order("sort_order"),
    ]);
    if (draftError || photoError || !draft) throw new Error(draftError?.message || photoError?.message || "Draft not found.");
    if (!photos?.length) return NextResponse.json({ error: "Add photos before analysis." }, { status: 400 });
    const imageParts = [];
    for (const photo of photos) {
      const { data, error } = await db.storage.from(DRAFT_PHOTO_BUCKET).download(photo.storage_path);
      if (error || !data) throw new Error(`Could not load photo ${photo.id} for analysis.`);
      const bytes = Buffer.from(await data.arrayBuffer());
      imageParts.push({ type: "image_url", image_url: { url: `data:${photo.mime_type};base64,${bytes.toString("base64")}`, detail: "high" } });
    }
    const prompt = `Inspect this complete photo set for one proposed eBay ${draft.listing_kind === "lot" ? "intentional lot/set" : "item"}. Read visible labels, model numbers, barcodes and markings; identify the exact variant only when evidence supports it. Report conflicting or uncertain evidence. Describe visible condition, flaws, and included pieces. Do not claim testing, functionality, completeness, authenticity, or hidden qualities unless visible evidence establishes them. Suggest a buyer-searchable title of at most 80 characters, factual description, and item-specific key/value pairs. This is a draft for seller review, not a published listing. Seller notes: ${String(draft.seller_notes || "none")}. Return only valid JSON with fields: identification, confidence (0-1), uncertainty, evidence (array), title, description, condition_observations, visible_flaws, included_items, item_specifics (object), required_seller_inputs (array), photo_roles (array of {index, role}). Roles are hero, alternate_angle, label, included_item, flaw, unknown. Input image order is the index order.`;
    const response = await fetch("https://api.openai.com/v1/chat/completions", {
      method: "POST", headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json" },
      body: JSON.stringify({ model: process.env.MBOP_EBAY_DRAFT_VISION_MODEL || "gpt-4.1-mini", temperature: 0.1, response_format: { type: "json_object" }, messages: [{ role: "user", content: [{ type: "text", text: prompt }, ...imageParts] }] }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(`Photo analysis failed (${response.status}): ${result.error?.message || "OpenAI request failed"}`);
    const text = result.choices?.[0]?.message?.content;
    if (!text) throw new Error("The vision service returned no analysis.");
    const analysis = JSON.parse(text);
    const aiAnalysis = { ...analysis, analyzed_at: new Date().toISOString(), model: result.model || process.env.MBOP_EBAY_DRAFT_VISION_MODEL || "gpt-4.1-mini" };
    const { error: updateError } = await db.from("ebay_listing_drafts").update({ ai_analysis: aiAnalysis, ai_model: aiAnalysis.model, identification_evidence: analysis.evidence || [], identification_status: analysis.confidence >= 0.9 && !analysis.uncertainty ? "review_required" : "uncertain", required_inputs: analysis.required_seller_inputs || [], updated_at: new Date().toISOString() }).eq("id", id);
    if (updateError) throw updateError;
    const roles = new Map<number, string>((analysis.photo_roles || []).map((r: { index: number; role: string }) => [r.index, r.role]));
    await Promise.all(photos.map((photo, index) => db.from("ebay_listing_draft_photos").update({ analysis: { role_suggestion: roles.get(index) || "unknown" } }).eq("id", photo.id)));
    return NextResponse.json({ analysis: aiAnalysis });
  } catch (error) { return NextResponse.json({ error: error instanceof Error ? error.message : "Photo analysis failed." }, { status: 502 }); }
}
