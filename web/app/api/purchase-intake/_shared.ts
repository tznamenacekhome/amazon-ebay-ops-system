import { runSchedulerCommandTask } from "../_awsScheduler";
import { createServerSupabaseClient } from "../_server";

export const BUCKET = "mbop-purchase-receipts";
export const MAX_BYTES = 12 * 1024 * 1024;
export const COLUMNS = "id,original_filename,mime_type,status,extracted_data,reviewed_data,cost_snapshot,extraction_model,extraction_error,extraction_started_at,purchase_id,created_at,updated_at,saved_at";
export const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function receiptMime(bytes: Buffer) {
  if (bytes.subarray(0, 5).toString() === "%PDF-") return "application/pdf";
  if (bytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))) return "image/png";
  if (bytes[0] === 255 && bytes[1] === 216 && bytes[2] === 255) return "image/jpeg";
  if (bytes.subarray(0, 4).toString() === "RIFF" && bytes.subarray(8, 12).toString() === "WEBP") return "image/webp";
  throw new Error("Use a valid PDF, PNG, JPEG or WebP receipt.");
}

export async function launchExtraction(id: string) {
  const db = createServerSupabaseClient();
  const token = crypto.randomUUID();
  const dispatch = await db.rpc("mbop_dispatch_purchase_intake", { p_id: id, p_token: token });
  if (dispatch.error) throw new Error(dispatch.error.message);
  if (!dispatch.data) throw new Error("Extraction was already requested. Wait two minutes before retrying, or reload its progress.");
  const task = await runSchedulerCommandTask({
    command: ["python", "-m", "integrations.purchase_receipt_intake", "--draft-id", id],
    source: "purchase-receipt-intake", job: "purchase-receipt-intake", runId: id,
    // Fixed per attempt; duplicate workers are also protected by the DB lease.
    clientToken: token,
    taskDefinition: process.env.MBOP_RECEIPT_TASK_DEFINITION,
  });
  const { error } = await db.from("purchase_intake_drafts")
    .update({ task_arn: task.taskArn }).eq("id", id).eq("dispatch_token", token);
  if (error) throw new Error("Extraction was launched, but task tracking could not be saved. Reload the draft.");
}
