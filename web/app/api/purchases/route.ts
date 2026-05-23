import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.SUPABASE_URL!;
const supabaseServiceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY!;

const supabase = createClient(supabaseUrl, supabaseServiceRoleKey);

export async function GET() {
  const { data, error } = await supabase
    .from("vw_purchases_dashboard")
    .select("*")
    .order("order_date", { ascending: false })
    .limit(200);

  if (error) {
    return NextResponse.json(
      { error: error.message },
      { status: 500 }
    );
  }

  const rows = (data ?? []).map((row) => ({
    ...row,
    ebay_title: row.title,
  }));
  const itemIds = rows
    .map((row) => row.item_id)
    .filter((itemId): itemId is string => typeof itemId === "string");

  if (itemIds.length === 0) {
    return NextResponse.json(rows);
  }

  const { data: itemTitles, error: itemTitlesError } = await supabase
    .from("purchase_items")
    .select("item_id,amazon_title")
    .in("item_id", itemIds);

  if (itemTitlesError) {
    return NextResponse.json(rows);
  }

  const amazonTitleByItemId = new Map(
    (itemTitles ?? []).map((item) => [item.item_id, item.amazon_title])
  );

  return NextResponse.json(
    rows.map((row) => ({
      ...row,
      amazon_title: amazonTitleByItemId.get(row.item_id) ?? null,
    }))
  );
}

export async function PATCH(request: Request) {
  const body = await request.json();

  const itemId = body.item_id as string | undefined;

  if (!itemId) {
    return NextResponse.json(
      { error: "item_id is required" },
      { status: 400 }
    );
  }

  const updates: {
    asin?: string | null;
    target_price?: number | null;
  } = {};

  if ("asin" in body) {
    updates.asin = body.asin ? String(body.asin).trim().toUpperCase() : null;
  }

  if ("sell_price" in body) {
    updates.target_price =
      body.sell_price === null || body.sell_price === ""
        ? null
        : Number(body.sell_price);
  }

  const { data, error } = await supabase
    .from("purchase_items")
    .update(updates)
    .eq("item_id", itemId)
    .select()
    .single();

  if (error) {
    return NextResponse.json(
      { error: error.message },
      { status: 500 }
    );
  }

  return NextResponse.json({
    success: true,
    item: data,
  });
}
