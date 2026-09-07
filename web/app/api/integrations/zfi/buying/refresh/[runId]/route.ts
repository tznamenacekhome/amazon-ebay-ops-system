import { authorize, json, publicRefresh, readRefresh, UUID } from "../../contract";

export const runtime = "nodejs";
export async function GET(request: Request, context: { params: Promise<{ runId: string }> }) {
  const denied = authorize(request); if (denied) return denied;
  const { runId } = await context.params;
  if (!UUID.test(runId)) return json({ error: "invalid_run_id" }, 400);
  try {
    const row = await readRefresh(runId);
    return row ? json(publicRefresh(row)) : json({ error: "run_not_found" }, 404);
  } catch { return json({ error: "status_unavailable" }, 503); }
}
