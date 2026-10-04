import { NextResponse } from "next/server";
import { createServerSupabaseClient } from "../../_server";

export const dynamic = "force-dynamic";

export async function GET() {
  const supabase = createServerSupabaseClient();
  const { data, error } = await supabase.from("wholesale_email_ingestions")
    .select("ingestion_id,source_type,source_name,source_host,sender_address,received_at,status,effective_date,wholesale_import_id,error_summary,attempt_count,completed_at,wholesale_imports(summary,revision)")
    .order("received_at", { ascending: false }).limit(100);
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  const rows = (data ?? []).map((row: any) => ({
    ingestionId: row.ingestion_id, sourceType: row.source_type, sourceName: row.source_name,
    sourceHost: row.source_host, sender: row.sender_address, receivedAt: row.received_at,
    status: row.status, effectiveDate: row.effective_date, importId: row.wholesale_import_id,
    rowCount: row.wholesale_imports?.summary?.rows_imported ?? null,
    revision: row.wholesale_imports?.revision ?? null, attempts: row.attempt_count,
    error: row.error_summary, completedAt: row.completed_at,
  }));
  return NextResponse.json({ rows }, { headers: { "Cache-Control": "no-store" } });
}
