import { createHash, randomUUID } from "node:crypto";
import { NextResponse } from "next/server";
import { createServerSupabaseClient, requireAdminApiToken } from "../_server";
import { BUCKET, COLUMNS, MAX_BYTES, launchExtraction, receiptMime } from "./_shared";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const db = createServerSupabaseClient();
  const url = new URL(request.url);
  const page = Math.max(1, Math.min(10000, Number(url.searchParams.get("page")) || 1));
  const search = (url.searchParams.get("search") || "").trim().slice(0, 100).replace(/[%_,().]/g, " ");
  let purchases = db.from("purchases").select("purchase_id,supplier,supplier_order_id,order_date,total_order_cost,order_status", { count: "exact" })
    .not("supplier", "ilike", "ebay");
  if (search) purchases = purchases.or(`supplier.ilike.%${search}%,supplier_order_id.ilike.%${search}%`);
  const [drafts, orders] = await Promise.all([
    db.from("purchase_intake_drafts").select(COLUMNS).order("created_at", { ascending: false }).limit(50),
    purchases.order("order_date", { ascending: false, nullsFirst: false }).order("purchase_id").range((page - 1) * 50, page * 50 - 1),
  ]);
  if (drafts.error || orders.error) return NextResponse.json({ error: drafts.error?.message || orders.error?.message }, { status: 500 });
  return NextResponse.json({ drafts: drafts.data, purchases: orders.data, total: orders.count, page });
}

export async function POST(request: Request) {
  const denied = requireAdminApiToken(request); if (denied) return denied;
  try {
    if (Number(request.headers.get("content-length")) > MAX_BYTES + 1024 * 1024) return NextResponse.json({ error: "Receipt limit is 12 MB." }, { status: 413 });
    const file = (await request.formData()).get("file");
    if (!(file instanceof File) || !file.size || file.size > MAX_BYTES) return NextResponse.json({ error: "Choose one receipt up to 12 MB." }, { status: 400 });
    const bytes = Buffer.from(await file.arrayBuffer());
    const mime = receiptMime(bytes);
    const hash = createHash("sha256").update(bytes).digest("hex");
    const db = createServerSupabaseClient();
    const { data: existing, error: findError } = await db.from("purchase_intake_drafts").select(COLUMNS).eq("document_sha256", hash).maybeSingle();
    if (findError) throw findError;
    if (existing && existing.status !== "uploaded" && existing.status !== "failed") return NextResponse.json({ draft: existing, duplicate: true });
    const id = existing?.id || randomUUID();
    const path = `${hash}/receipt.${mime === "application/pdf" ? "pdf" : mime.split("/")[1]}`;
    const { error: uploadError } = await db.storage.from(BUCKET).upload(path, bytes, { contentType: mime, upsert: false });
    // Concurrent uploads share an immutable hash path.
    if (uploadError && !["409", "Duplicate"].includes(String(uploadError.statusCode)) && !/already exists|duplicate/i.test(uploadError.message)) throw new Error("Receipt storage failed. Confirm the private receipt bucket is configured.");
    if (!existing) {
      const { error } = await db.from("purchase_intake_drafts").insert({ id, document_sha256: hash, original_filename: file.name.slice(0, 240), mime_type: mime, storage_path: path });
      if (error?.code === "23505") {
        const { data, error: lookupError } = await db.from("purchase_intake_drafts").select(COLUMNS).eq("document_sha256", hash).single();
        if (lookupError) throw lookupError;
        return NextResponse.json({ draft: data, duplicate: true });
      }
      if (error) throw error;
    }
    let launchError: string | undefined;
    try { await launchExtraction(id); } catch { launchError = "Receipt saved, but extraction could not start. Open the draft and retry extraction."; }
    const { data, error } = await db.from("purchase_intake_drafts").select(COLUMNS).eq("id", id).single();
    if (error) throw error;
    return NextResponse.json({ draft: data, warning: launchError }, { status: 202 });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "Receipt upload failed." }, { status: 400 });
  }
}
