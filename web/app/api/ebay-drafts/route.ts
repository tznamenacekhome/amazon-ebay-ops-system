import { createHash, randomUUID } from "node:crypto";
import { NextResponse } from "next/server";
import { createServerSupabaseClient, requireAdminApiToken } from "../_server";
import { DRAFT_PHOTO_BUCKET, MAX_DRAFT_PHOTOS, MAX_DRAFT_PHOTO_BYTES, MAX_DRAFT_TOTAL_BYTES, detectedItemNumber, importIdempotencyKey, safeRelativePath } from "./draftHelpers";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const photoColumns = "id,draft_id,storage_path,original_name,relative_path,mime_type,byte_size,width,height,rotation_degrees,sort_order,role,analysis";
function imageMime(bytes: Buffer) {
  if (bytes.length >= 3 && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff) return "image/jpeg";
  if (bytes.length >= 8 && bytes.subarray(0, 8).equals(Buffer.from([137,80,78,71,13,10,26,10]))) return "image/png";
  if (bytes.length >= 12 && bytes.toString("ascii", 0, 4) === "RIFF" && bytes.toString("ascii", 8, 12) === "WEBP") return "image/webp";
  return null;
}

export async function GET(request: Request) {
  const denied = requireAdminApiToken(request); if (denied) return denied;
  const db = createServerSupabaseClient();
  const id = new URL(request.url).searchParams.get("id");
  if (id) {
    const [{ data: batch, error: batchError }, { data: drafts, error: draftError }] = await Promise.all([
      db.from("ebay_draft_imports").select("*").eq("id", id).single(),
      db.from("ebay_listing_drafts").select("*").eq("import_id", id).order("created_at"),
    ]);
    if (batchError || draftError) return NextResponse.json({ error: batchError?.message || draftError?.message }, { status: 404 });
    const rows = [];
    for (const draft of drafts || []) {
      const { data: photos, error } = await db.from("ebay_listing_draft_photos").select(photoColumns).eq("draft_id", draft.id).order("sort_order");
      if (error) return NextResponse.json({ error: error.message }, { status: 500 });
      const signed = await Promise.all((photos || []).map(async photo => {
        const { data } = await db.storage.from(DRAFT_PHOTO_BUCKET).createSignedUrl(photo.storage_path, 1800);
        return { ...photo, url: data?.signedUrl || null };
      }));
      rows.push({ ...draft, photos: signed });
    }
    return NextResponse.json({ batch, drafts: rows });
  }
  const { data, error } = await db.from("ebay_draft_imports").select("id,source_name,status,grouping_summary,created_at,updated_at").order("updated_at", { ascending: false }).limit(100);
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  const { data: drafts, error: draftError } = await db.from("ebay_listing_drafts").select("id,import_id,group_name,title,status,identification_status,price,updated_at").order("updated_at", { ascending: false }).limit(300);
  if (draftError) return NextResponse.json({ error: draftError.message }, { status: 500 });
  return NextResponse.json({ batches: data || [], drafts: drafts || [] });
}

export async function POST(request: Request) {
  const denied = requireAdminApiToken(request); if (denied) return denied;
  try {
    const form = await request.formData();
    const metadata = JSON.parse(String(form.get("manifest") || "{}")) as { photos?: Array<Record<string, unknown>>; sourceName?: string };
    const files = form.getAll("original");
    if (!files.length || files.length > MAX_DRAFT_PHOTOS || files.some(value => !(value instanceof File))) return NextResponse.json({ error: `Choose 1 to ${MAX_DRAFT_PHOTOS} photos.` }, { status: 400 });
    const corrected = form.getAll("corrected");
    if (corrected.length !== files.length || corrected.some(value => !(value instanceof File))) return NextResponse.json({ error: "Each original photo needs its corrected copy." }, { status: 400 });
    const meta = metadata.photos || [];
    if (meta.length !== files.length) return NextResponse.json({ error: "The photo manifest does not match the uploaded files." }, { status: 400 });
    const totalBytes = [...files, ...corrected].reduce((sum, file) => sum + (file instanceof File ? file.size : 0), 0);
    if (files.some(file => !(file instanceof File) || file.size < 1 || file.size > MAX_DRAFT_PHOTO_BYTES) || corrected.some(file => !(file instanceof File) || file.size < 1 || file.size > MAX_DRAFT_PHOTO_BYTES) || totalBytes > MAX_DRAFT_TOTAL_BYTES) return NextResponse.json({ error: "Each original and corrected photo must be at most 20 MB, with a combined upload limit of 120 MB." }, { status: 413 });
    const entries = [];
    for (let i = 0; i < files.length; i++) {
      const original = files[i] as File, fixed = corrected[i] as File;
      const originalBytes = Buffer.from(await original.arrayBuffer()), fixedBytes = Buffer.from(await fixed.arrayBuffer());
      const mime = imageMime(originalBytes), correctedMime = imageMime(fixedBytes);
      if (!mime || mime !== correctedMime) return NextResponse.json({ error: `${original.name}: only valid JPEG, PNG, or WebP images are supported; original and corrected formats must match.` }, { status: 400 });
      const record = meta[i];
      const relativePath = safeRelativePath(String(record.relativePath || original.name));
      entries.push({ original, fixed, originalBytes, fixedBytes, mime, relativePath,
        groupKey: String(record.groupKey || `photo-${i + 1}`).slice(0, 120), groupName: String(record.groupName || `Item ${i + 1}`).slice(0, 240),
        confidence: Math.max(0, Math.min(1, Number(record.groupingConfidence) || 0)), reason: String(record.groupingReason || "Seller grouped in folder review").slice(0, 500),
        kind: record.listingKind === "lot" ? "lot" : "single", order: Number(record.order) || i, rotation: [0,90,180,270].includes(Number(record.rotation)) ? Number(record.rotation) : 0,
        role: ["hero","alternate_angle","label","included_item","flaw","unknown"].includes(String(record.role)) ? record.role : "unknown",
        width: Math.max(1, Number(record.width) || 1), height: Math.max(1, Number(record.height) || 1), itemNumber: detectedItemNumber(relativePath),
      });
    }
    const key = importIdempotencyKey(entries.map(e => ({ relativePath: e.relativePath, sha256: createHash("sha256").update(e.originalBytes).digest("hex") })));
    const db = createServerSupabaseClient();
    const { data: previous } = await db.from("ebay_draft_imports").select("id").eq("idempotency_key", key).maybeSingle();
    if (previous) return NextResponse.json({ importId: previous.id, duplicate: true });
    const groups = new Map<string, typeof entries>();
    for (const entry of entries) groups.set(entry.groupKey, [...(groups.get(entry.groupKey) || []), entry]);
    const importId = randomUUID();
    const sourceName = String(metadata.sourceName || "Photo folder").slice(0, 240);
    const { error: importError } = await db.from("ebay_draft_imports").insert({ id: importId, idempotency_key: key, source_name: sourceName, source_manifest: { photos: entries.map(e => ({ path: e.relativePath, sha256: createHash("sha256").update(e.originalBytes).digest("hex") })) }, grouping_summary: { photoCount: entries.length, groupCount: groups.size } });
    if (importError) {
      if (importError.code === "23505") { const { data } = await db.from("ebay_draft_imports").select("id").eq("idempotency_key", key).single(); return NextResponse.json({ importId: data?.id, duplicate: true }); }
      throw importError;
    }
    const draftIds = new Map<string, string>();
    const draftRows = [...groups].map(([groupKey, photos]) => {
      const id = randomUUID(); draftIds.set(groupKey, id); const first = photos[0];
      return { id, import_id: importId, group_key: groupKey, group_name: first.groupName, source_item_number: first.itemNumber, grouping_confidence: Math.min(...photos.map(p => p.confidence)), grouping_reason: first.reason, grouping_confirmed: false, listing_kind: first.kind };
    });
    const { error: draftError } = await db.from("ebay_listing_drafts").insert(draftRows);
    if (draftError) throw draftError;
    for (const entry of entries) {
      const draftId = draftIds.get(entry.groupKey)!;
      const photoId = randomUUID();
      const stem = `${importId}/${draftId}/${photoId}`;
      const originalHash = createHash("sha256").update(entry.originalBytes).digest("hex");
      const fixedHash = createHash("sha256").update(entry.fixedBytes).digest("hex");
      const ext = entry.mime.split("/")[1];
      const originalPath = `${stem}/original.${ext}`, fixedPath = `${stem}/review.${ext}`;
      const uploadOriginal = await db.storage.from(DRAFT_PHOTO_BUCKET).upload(originalPath, entry.originalBytes, { contentType: entry.mime, upsert: false });
      if (uploadOriginal.error) throw new Error(`Photo upload failed for ${entry.original.name}: ${uploadOriginal.error.message}`);
      const uploadFixed = await db.storage.from(DRAFT_PHOTO_BUCKET).upload(fixedPath, entry.fixedBytes, { contentType: entry.mime, upsert: false });
      if (uploadFixed.error) throw new Error(`Corrected photo upload failed for ${entry.original.name}: ${uploadFixed.error.message}`);
      const { error } = await db.from("ebay_listing_draft_photos").insert({ id: photoId, draft_id: draftId, original_name: entry.original.name.slice(0, 240), relative_path: entry.relativePath, original_sha256: originalHash, processed_sha256: fixedHash, original_storage_path: originalPath, storage_path: fixedPath, mime_type: entry.mime, byte_size: entry.fixed.size, width: entry.width, height: entry.height, rotation_degrees: entry.rotation, sort_order: entry.order, role: entry.role });
      if (error) throw error;
    }
    return NextResponse.json({ importId, duplicate: false }, { status: 201 });
  } catch (error) { return NextResponse.json({ error: error instanceof Error ? error.message : "Photo intake failed." }, { status: 400 }); }
}
