import { NextResponse } from "next/server";
import { sourcingCacheVersion } from "../readCache";
export async function GET() {
  try { return NextResponse.json(await sourcingCacheVersion(), { headers: { "Cache-Control": "no-store" } }); }
  catch (error) { return NextResponse.json({ error: error instanceof Error ? error.message : "Sourcing freshness unavailable." }, { status: 503, headers: { "Cache-Control": "no-store" } }); }
}
