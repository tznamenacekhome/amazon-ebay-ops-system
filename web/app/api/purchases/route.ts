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
  const purchaseIds = rows
    .map((row) => row.purchase_id)
    .filter((purchaseId): purchaseId is string => typeof purchaseId === "string");

  if (itemIds.length === 0 && purchaseIds.length === 0) {
    return NextResponse.json(rows);
  }

  const { data: itemTitles } = await supabase
    .from("purchase_items")
    .select("item_id,amazon_title")
    .in("item_id", itemIds);

  const amazonTitleByItemId = new Map(
    (itemTitles ?? []).map((item) => [item.item_id, item.amazon_title])
  );

  const { data: purchases } = await supabase
    .from("purchases")
    .select("purchase_id,order_status,raw_import_json")
    .in("purchase_id", purchaseIds);

  const purchaseMetaById = new Map(
    (purchases ?? []).map((purchase) => [
      purchase.purchase_id,
      {
        orderStatus: purchase.order_status,
        sellerShipped: hasSellerShipped(purchase.raw_import_json),
        ebayCancelled: isEbayCancelled(purchase.raw_import_json, purchase.order_status),
      },
    ])
  );

  return NextResponse.json(
    rows.map((row) => ({
      ...row,
      amazon_title: amazonTitleByItemId.get(row.item_id) ?? null,
      order_status: purchaseMetaById.get(row.purchase_id)?.orderStatus ?? null,
      seller_shipped: purchaseMetaById.get(row.purchase_id)?.sellerShipped ?? false,
      ebay_cancelled: purchaseMetaById.get(row.purchase_id)?.ebayCancelled ?? false,
    }))
  );
}

function hasSellerShipped(rawImportJson: unknown) {
  if (!rawImportJson || typeof rawImportJson !== "object") return false;

  const order = "Order" in rawImportJson ? rawImportJson.Order : rawImportJson;

  return hasNestedKey(order, "ShippedTime");
}

function isEbayCancelled(rawImportJson: unknown, orderStatus?: string | null) {
  if (normalizeText(orderStatus).includes("cancel")) return true;
  if (!rawImportJson || typeof rawImportJson !== "object") return false;

  const order = "Order" in rawImportJson ? rawImportJson.Order : rawImportJson;
  const cancelStatus = findNestedValue(order, "CancelStatus");

  return (
    typeof cancelStatus === "string" &&
    cancelStatus.trim() !== "" &&
    normalizeText(cancelStatus) !== "notapplicable"
  );
}

function hasNestedKey(value: unknown, key: string): boolean {
  if (!value || typeof value !== "object") return false;

  if (key in value) return Boolean(value[key as keyof typeof value]);

  return Object.values(value).some((childValue) => hasNestedKey(childValue, key));
}

function findNestedValue(value: unknown, key: string): unknown {
  if (!value || typeof value !== "object") return null;

  if (key in value) return value[key as keyof typeof value];

  for (const childValue of Object.values(value)) {
    const foundValue = findNestedValue(childValue, key);
    if (foundValue !== null && foundValue !== undefined) return foundValue;
  }

  return null;
}

function normalizeText(value?: string | null) {
  return (value || "").trim().toLowerCase().replace(/[\s_-]+/g, "");
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
