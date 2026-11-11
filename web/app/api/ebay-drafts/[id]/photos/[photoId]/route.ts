import { createHash } from "node:crypto";
import { NextResponse } from "next/server";
import { createServerSupabaseClient, requireAdminApiToken } from "../../../../_server";
import { DRAFT_PHOTO_BUCKET, MAX_DRAFT_PHOTO_BYTES } from "../../../draftHelpers";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function validImage(bytes: Buffer, type: string) {
  if (type === "image/jpeg") return bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff;
  if (type === "image/png") return bytes.subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10]));
  if (type === "image/webp") return bytes.toString("ascii",0,4) === "RIFF" && bytes.toString("ascii",8,12) === "WEBP";
  return false;
}

export async function POST(request: Request, context: { params: Promise<{ id: string; photoId: string }> }) {
  const denied = requireAdminApiToken(request); if (denied) return denied;
  try {
    const { id, photoId } = await context.params;
    const form = await request.formData(); const file = form.get("file");
    if (!(file instanceof File) || file.size < 1 || file.size > MAX_DRAFT_PHOTO_BYTES) return NextResponse.json({ error: "Rotated photo must be at most 20 MB." }, { status: 400 });
    const rotation = Number(form.get("rotation")), width = Number(form.get("width")), height = Number(form.get("height"));
    if (![0,90,180,270].includes(rotation) || !Number.isInteger(width) || !Number.isInteger(height) || width < 1 || height < 1 || width > 20000 || height > 20000) return NextResponse.json({ error: "Invalid rotation or dimensions." }, { status: 400 });
    const bytes = Buffer.from(await file.arrayBuffer());
    if (!validImage(bytes,file.type)) return NextResponse.json({ error: "Corrected photo is not a valid JPEG, PNG, or WebP image." }, { status: 400 });
    const hash = createHash("sha256").update(bytes).digest("hex"), db = createServerSupabaseClient();
    const { data: photo, error: photoError } = await db.from("ebay_listing_draft_photos").select("id,storage_path,mime_type").eq("id",photoId).eq("draft_id",id).single();
    if (photoError || !photo) return NextResponse.json({ error: "Photo not found." }, { status: 404 });
    if (photo.mime_type !== file.type) return NextResponse.json({ error: "The rotated image format must match the original." }, { status: 400 });
    const path = `${id}/${id}/${photoId}/review-${hash}.${file.type.split("/")[1]}`;
    const { error: uploadError } = await db.storage.from(DRAFT_PHOTO_BUCKET).upload(path,bytes,{contentType:file.type,upsert:true});
    if (uploadError) throw uploadError;
    const { error: updateError } = await db.from("ebay_listing_draft_photos").update({ storage_path:path, processed_sha256:hash, byte_size:file.size, width,height,rotation_degrees:rotation }).eq("id",photoId).eq("draft_id",id);
    if (updateError) throw updateError;
    return NextResponse.json({ saved:true });
  } catch (error) { return NextResponse.json({ error:error instanceof Error ? error.message : "Could not save rotated photo." },{status:400}); }
}
