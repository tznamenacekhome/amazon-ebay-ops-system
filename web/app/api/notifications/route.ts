import { NextResponse } from "next/server";
import { createServerSupabaseClient, requireAdminApiToken } from "../_server";

export const dynamic = "force-dynamic";

export async function GET() {
  const supabase = createServerSupabaseClient();
  const { data, error } = await supabase.from("mbop_notifications").select("notification_id,severity,title,message,href,occurrence_count,last_seen_at,read_at")
    .is("resolved_at", null).order("last_seen_at", { ascending: false }).limit(30);
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ rows: data ?? [], unread: (data ?? []).filter(row => !row.read_at).length }, { headers: { "Cache-Control": "no-store" } });
}

export async function PATCH(request: Request) {
  const rejected = requireAdminApiToken(request);
  if (rejected) return rejected;
  const body = await request.json().catch(() => ({}));
  const supabase = createServerSupabaseClient();
  let query = supabase.from("mbop_notifications").update({ read_at: new Date().toISOString() }).is("read_at", null);
  if (body.notificationId) query = query.eq("notification_id", body.notificationId);
  const { error } = await query;
  return error ? NextResponse.json({ error: error.message }, { status: 500 }) : NextResponse.json({ ok: true });
}
