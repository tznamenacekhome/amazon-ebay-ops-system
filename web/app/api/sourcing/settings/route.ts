import { NextRequest, NextResponse } from "next/server";
import { normalizeArray, supabase, toNumber } from "../_supabase";
import { requireAdminApiToken } from "../../_server";

export async function GET() {
  const { data, error } = await supabase
    .from("sourcing_settings")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(1)
    .maybeSingle();

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ settings: data });
}

export async function PATCH(request: NextRequest) {
  const adminError = requireAdminApiToken(request);
  if (adminError) return adminError;

  const body = await request.json();
  const { data: current, error: readError } = await supabase
    .from("sourcing_settings")
    .select("setting_id")
    .order("created_at", { ascending: false })
    .limit(1)
    .maybeSingle();

  if (readError) return NextResponse.json({ error: readError.message }, { status: 500 });

  const update = {
    min_amazon_price: toNumber(body.min_amazon_price ?? body.minAmazonPrice, 20.99),
    min_roi_percent: toNumber(body.min_roi_percent ?? body.minRoiPercent, 40),
    min_profit_dollars: toNumber(body.min_profit_dollars ?? body.minProfitDollars, 5),
    sales_lookback_days: toNumber(body.sales_lookback_days ?? body.salesLookbackDays, 90),
    inventory_need_months_threshold: toNumber(
      body.inventory_need_months_threshold ?? body.inventoryNeedMonthsThreshold,
      2,
    ),
    buyer_zip: String(body.buyer_zip ?? body.buyerZip ?? "93022"),
    buyer_country: String(body.buyer_country ?? body.buyerCountry ?? "US"),
    item_location_countries: normalizeArray(
      body.item_location_countries ?? body.itemLocationCountries ?? ["US", "CA"],
    ),
    delivery_country: String(body.delivery_country ?? body.deliveryCountry ?? "US"),
    best_offer_min_ask_percent: toNumber(
      body.best_offer_min_ask_percent ?? body.bestOfferMinAskPercent,
      60,
    ),
    excluded_keywords: normalizeArray(body.excluded_keywords ?? body.excludedKeywords),
    updated_at: new Date().toISOString(),
  };

  const result = current?.setting_id
    ? await supabase
        .from("sourcing_settings")
        .update(update)
        .eq("setting_id", current.setting_id)
        .select("*")
        .single()
    : await supabase.from("sourcing_settings").insert(update).select("*").single();

  if (result.error) return NextResponse.json({ error: result.error.message }, { status: 500 });
  return NextResponse.json({ settings: result.data });
}
