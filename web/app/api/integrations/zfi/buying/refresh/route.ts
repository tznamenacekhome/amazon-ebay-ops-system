import { authorize, json, requestRefresh } from "../contract";

export const runtime = "nodejs";
export async function POST(request: Request) {
  const denied = authorize(request, true); if (denied) return denied;
  const text = await request.text();
  if (text.trim()) {
    try {
      const body = JSON.parse(text);
      if (!body || Array.isArray(body) || typeof body !== "object" || Object.keys(body).length) throw new Error();
    } catch { return json({ error: "empty_body_required" }, 400); }
  }
  try { return json(await requestRefresh(), 202); }
  catch { return json({ error: "refresh_unavailable" }, 503); }
}
