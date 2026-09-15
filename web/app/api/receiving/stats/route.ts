import { NextResponse } from "next/server";
import { createServerSupabaseClient } from "../../_server";
import { fetchDeliveryStats } from "../../purchases/deliveryStats";

export async function GET() {
  const result = await fetchDeliveryStats(createServerSupabaseClient());
  return NextResponse.json(result, {
    status: result.deliveryError ? 503 : 200,
    headers: { "Cache-Control": "no-store" },
  });
}
