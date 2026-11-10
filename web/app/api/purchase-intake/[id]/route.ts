import { NextResponse } from "next/server";
import { createServerSupabaseClient, requireAdminApiToken } from "../../_server";
import { BUCKET, COLUMNS, UUID, launchExtraction } from "../_shared";
import { matchReceiptItems, prepareReceipt } from "../receiptPreparation";
import type { ReceiptData } from "../../../purchases/receiptTypes";

export const dynamic = "force-dynamic";
type Context = { params: Promise<{ id: string }> };

export async function GET(request: Request, context: Context) {
  const { id } = await context.params;
  if (!UUID.test(id)) return NextResponse.json({ error: "Invalid draft ID." }, { status: 400 });
  const db = createServerSupabaseClient();
  if (new URL(request.url).searchParams.get("document") === "1") {
    const { data, error } = await db.from("purchase_intake_drafts").select("storage_path").eq("id", id).single();
    if (error || !data) return NextResponse.json({ error: "Receipt not found." }, { status: 404 });
    const result = await db.storage.from(BUCKET).createSignedUrl(data.storage_path, 60, { download: true });
    if (result.error) return NextResponse.json({ error: "Original receipt is unavailable." }, { status: 500 });
    return NextResponse.redirect(result.data.signedUrl, { status: 302, headers: { "Cache-Control": "private, no-store", "Referrer-Policy": "no-referrer" } });
  }
  const { data, error } = await db.from("purchase_intake_drafts").select(COLUMNS).eq("id", id).single();
  return error ? NextResponse.json({ error: "Draft not found." }, { status: 404 }) : NextResponse.json({ draft: data });
}

export async function POST(request: Request, context: Context) {
  const denied = requireAdminApiToken(request); if (denied) return denied;
  const { id } = await context.params;
  if (!UUID.test(id)) return NextResponse.json({ error: "Invalid draft ID." }, { status: 400 });
  try {
    const text = await request.text();
    if (text.length > 150000) return NextResponse.json({ error: "Draft is too large." }, { status: 413 });
    const body = JSON.parse(text);
    const db = createServerSupabaseClient();
    if (body.action === "retry") {
      const { data, error } = await db.from("purchase_intake_drafts").select("status,extraction_started_at").eq("id", id).single();
      if (error || !data) throw new Error("Draft not found.");
      if (["saved", "review"].includes(data.status)) throw new Error("This receipt is already extracted. Open its review.");
      if (data.status === "extracting" && Date.now() - Date.parse(data.extraction_started_at) < 15 * 60 * 1000) throw new Error("Extraction is still running. Reload its progress.");
      await launchExtraction(id);
      return NextResponse.json({ queued: true });
    }
    if (!body.data || typeof body.data !== "object" || !Array.isArray(body.data.items) || body.data.items.length > 100) throw new Error("Invalid draft.");
    const draft = await db.from("purchase_intake_drafts").select("extracted_data,status").eq("id", id).single();
    if (draft.error) throw new Error("Receipt draft not found.");
    let prepared = prepareReceipt(body.data as ReceiptData, draft.data.extracted_data);
    let matchWarning: string | undefined;
    if (body.action === "prepare" || body.action === "match") {
      try { prepared = await matchReceiptItems(db, prepared); }
      catch (error) { matchWarning = error instanceof Error ? error.message : "ASIN lookup unavailable. Enter the ASIN manually."; }
    }
    if (body.action === "draft") {
      const { data, error } = await db.from("purchase_intake_drafts").update({ reviewed_data: prepared, updated_at: new Date().toISOString() })
        .eq("id", id).in("status", ["review", "failed"]).select("id").maybeSingle();
      if (error) throw error; if (!data) throw new Error("Draft is not editable. Reload its current status.");
      return NextResponse.json({ saved: true });
    }
    if (!["preview", "save", "prepare", "match"].includes(body.action)) throw new Error("Unknown receipt action.");
    const { data, error } = body.action === "save"
      ? await db.rpc("mbop_save_purchase_intake", { p_id: id, p_data: prepared })
      : await db.rpc("mbop_purchase_intake_costs", { p_data: prepared });
    if (error && body.action === "save") return NextResponse.json({ error: error.message }, { status: 409 });
    return NextResponse.json(body.action === "save" ? { result: data } : { data: prepared, costs: error ? null : data, costError: error?.message, matchWarning });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "Receipt action failed." }, { status: 400 });
  }
}
