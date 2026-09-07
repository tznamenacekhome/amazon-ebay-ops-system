import { NextRequest } from "next/server";
import { createServerSupabaseClient } from "../../../../_server";
import { authorize, FIELDS, json, parseFactsQuery, VERSION } from "../contract";

export const runtime = "nodejs";
export async function GET(request: NextRequest) {
  const denied = authorize(request); if (denied) return denied;
  let input;
  try { input = parseFactsQuery(request.nextUrl); }
  catch { return json({ error: "invalid_query", detail: "Provide from/to dates (exclusive to, max 93 days), limit 1-500, optional UUID after." }, 400); }
  try {
    let query = createServerSupabaseClient().from("zfi_ebay_purchase_facts").select(FIELDS)
      .gte("purchase_date", input.from).lt("purchase_date", input.to)
      .order("source_purchase_id").limit(input.limit + 1);
    if (input.after) query = query.gt("source_purchase_id", input.after);
    const result = await query;
    if (result.error) throw new Error("facts_unavailable");
    const rows = result.data || [];
    const page = rows.slice(0, input.limit);
    return json({ contract_version: VERSION, from: input.from, to: input.to,
      facts: page, next_cursor: rows.length > input.limit ? page.at(-1)?.source_purchase_id : null });
  } catch { return json({ error: "facts_unavailable" }, 503); }
}
