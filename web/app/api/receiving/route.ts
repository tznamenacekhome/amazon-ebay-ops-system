import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.SUPABASE_URL!;
const supabaseServiceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY!;

const supabase = createClient(supabaseUrl, supabaseServiceRoleKey);

type ReceivingUpdate = {
  item_id: string;
  quantity_received: number;
  return_pending: boolean;
  marketplace: "Amazon" | "eBay" | null;
};

export async function GET() {
  const { data, error } = await supabase
    .from("vw_purchases_dashboard")
    .select("*")
    .order("order_date", { ascending: false })
    .limit(1000);

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
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

  const itemMeta = await fetchItemMeta(itemIds);

  const itemMetaById = new Map(
    (itemMeta ?? []).map((item) => [item.item_id, item])
  );

  const purchases = await fetchPurchaseMeta(purchaseIds);

  const purchaseMetaById = new Map(
    (purchases ?? []).map((purchase) => [
      purchase.purchase_id,
      {
        orderStatus: purchase.order_status,
        sellerShipped: hasSellerShipped(purchase.raw_import_json),
        ebayCancelled: isEbayCancelled(purchase.raw_import_json, purchase.order_status),
        ebayEstimatedDeliveryDate: getEbayEstimatedDeliveryDate(
          purchase.raw_import_json
        ),
      },
    ])
  );

  return NextResponse.json(
    rows.map((row) => {
      const item = itemMetaById.get(row.item_id);
      const ebayListingUrl = getEbayListingUrl(item);

      return {
        ...row,
        amazon_title: item?.amazon_title ?? row.amazon_title ?? null,
        marketplace: item?.marketplace ?? null,
        received_date: item?.received_date ?? null,
        supplier_sku: item?.supplier_sku ?? null,
        supplier_listing_url: item?.supplier_listing_url ?? row.supplier_listing_url ?? null,
        ebay_listing_url: ebayListingUrl,
        order_status: purchaseMetaById.get(row.purchase_id)?.orderStatus ?? null,
        seller_shipped: purchaseMetaById.get(row.purchase_id)?.sellerShipped ?? false,
        ebay_cancelled: purchaseMetaById.get(row.purchase_id)?.ebayCancelled ?? false,
        estimated_delivery_date:
          row.estimated_delivery_date ??
          purchaseMetaById.get(row.purchase_id)?.ebayEstimatedDeliveryDate ??
          null,
      };
    })
  );
}

async function fetchItemMeta(itemIds: string[]) {
  const rows = [];
  const chunkSize = 100;

  for (let index = 0; index < itemIds.length; index += chunkSize) {
    const chunk = itemIds.slice(index, index + chunkSize);
    const { data, error } = await supabase
      .from("purchase_items")
      .select(
        "item_id,amazon_title,marketplace,received_date,supplier_sku,supplier_listing_url,raw_import_json"
      )
      .in("item_id", chunk);

    if (error) {
      console.error("Receiving item metadata lookup failed", error);
      continue;
    }

    rows.push(...(data ?? []));
  }

  return rows;
}

async function fetchPurchaseMeta(purchaseIds: string[]) {
  const rows = [];
  const chunkSize = 100;

  for (let index = 0; index < purchaseIds.length; index += chunkSize) {
    const chunk = purchaseIds.slice(index, index + chunkSize);
    const { data, error } = await supabase
      .from("purchases")
      .select("purchase_id,order_status,raw_import_json")
      .in("purchase_id", chunk);

    if (error) {
      console.error("Receiving purchase metadata lookup failed", error);
      continue;
    }

    rows.push(...(data ?? []));
  }

  return rows;
}

export async function POST(request: Request) {
  const body = await request.json();
  const updates = Array.isArray(body.items) ? body.items : [];
  const receivedDate =
    typeof body.received_date === "string" && body.received_date.trim()
      ? body.received_date.trim()
      : localDateString();

  if (updates.length === 0) {
    return NextResponse.json(
      { error: "items are required" },
      { status: 400 }
    );
  }

  try {
    const results = [];

    for (const update of updates) {
      const result = await receiveItem(update, receivedDate);
      results.push(result);
    }

    return NextResponse.json({ success: true, items: results });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Receiving save failed" },
      { status: 500 }
    );
  }
}

async function receiveItem(update: ReceivingUpdate, receivedDate: string) {
  if (!update.item_id) {
    throw new Error("item_id is required");
  }

  const quantityReceived = Number(update.quantity_received);

  if (!Number.isFinite(quantityReceived) || quantityReceived < 0) {
    throw new Error("quantity_received must be zero or greater");
  }

  const { data: sourceData, error: sourceError } = await supabase
    .from("purchase_items")
    .select(
      "item_id,purchase_id,title,amazon_title,quantity,unit_cost,asin,target_price," +
        "system,condition,supplier_listing_url,import_batch_id,raw_import_json," +
        "manual_title_override,manual_unit_cost_override"
    )
    .eq("item_id", update.item_id)
    .single();

  if (sourceError) {
    throw new Error(sourceError.message);
  }

  const source = sourceData as unknown as {
    item_id: string;
    purchase_id: string;
    title: string | null;
    amazon_title: string | null;
    quantity: number | null;
    unit_cost: number | null;
    asin: string | null;
    target_price: number | null;
    system: string | null;
    condition: string | null;
    supplier_listing_url: string | null;
    import_batch_id: string | null;
    raw_import_json: unknown;
    manual_title_override: boolean | null;
    manual_unit_cost_override: boolean | null;
  };

  const expectedQuantity = Number(source.quantity ?? 1);

  if (quantityReceived > expectedQuantity) {
    throw new Error("quantity_received cannot exceed quantity expected");
  }

  await updateShipmentReceipt(source.item_id, quantityReceived, !update.return_pending);

  if (update.return_pending) {
    const { data, error } = await supabase
      .from("purchase_items")
      .update({
        current_status: "return_pending",
        marketplace: null,
        received_date: null,
      })
      .eq("item_id", source.item_id)
      .select()
      .single();

    if (error) throw new Error(error.message);
    return data;
  }

  if (quantityReceived === 0) {
    const { data, error } = await supabase
      .from("purchase_items")
      .update({
        current_status: "no_tracking",
        marketplace: null,
        tracking_number: null,
        received_date: null,
      })
      .eq("item_id", source.item_id)
      .select()
      .single();

    if (error) throw new Error(error.message);
    return data;
  }

  const remainingQuantity = expectedQuantity - quantityReceived;

  const { data, error } = await supabase
    .from("purchase_items")
    .update({
      quantity: quantityReceived,
      current_status: "received",
      marketplace: update.marketplace || "Amazon",
      received_date: receivedDate,
    })
    .eq("item_id", source.item_id)
    .select()
    .single();

  if (error) throw new Error(error.message);

  if (remainingQuantity > 0) {
    await createMissingQuantitySplit(source, remainingQuantity);
  }

  return data;
}

async function createMissingQuantitySplit(
  source: {
    item_id: string;
    purchase_id: string;
    title: string | null;
    amazon_title: string | null;
    unit_cost: number | null;
    asin: string | null;
    target_price: number | null;
    system: string | null;
    condition: string | null;
    supplier_listing_url: string | null;
    import_batch_id: string | null;
    raw_import_json: unknown;
    manual_title_override: boolean | null;
    manual_unit_cost_override: boolean | null;
  },
  quantity: number
) {
  const { error } = await supabase.from("purchase_items").insert({
    purchase_id: source.purchase_id,
    title: source.title,
    amazon_title: source.amazon_title,
    quantity,
    unit_cost: source.unit_cost,
    asin: source.asin,
    target_price: source.target_price,
    system: source.system,
    condition: source.condition,
    supplier_listing_url: source.supplier_listing_url,
    import_batch_id: source.import_batch_id,
    raw_import_json: source.raw_import_json,
    current_status: "no_tracking",
    tracking_number: null,
    marketplace: null,
    manual_title_override: source.manual_title_override ?? false,
    manual_unit_cost_override: source.manual_unit_cost_override ?? false,
    manual_split_child: true,
    manual_split_parent_item_id: source.item_id,
  });

  if (error) throw new Error(error.message);
}

async function updateShipmentReceipt(
  itemId: string,
  quantityReceived: number,
  receivedVerified: boolean
) {
  const { error } = await supabase
    .from("inbound_shipment_items")
    .update({
      quantity_received_from_package: quantityReceived,
      received_verified: receivedVerified,
    })
    .eq("item_id", itemId);

  if (error) {
    console.warn("Failed to update inbound shipment receipt", error.message);
  }
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

function getEbayEstimatedDeliveryDate(rawImportJson: unknown) {
  if (!rawImportJson || typeof rawImportJson !== "object") return null;

  const order = "Order" in rawImportJson ? rawImportJson.Order : rawImportJson;
  const estimate = findNestedValue(order, "EstimatedDeliveryTimeMax");

  return typeof estimate === "string" && estimate.trim() !== ""
    ? estimate
    : null;
}

function getEbayListingUrl(
  item?: {
    supplier_listing_url?: string | null;
    supplier_sku?: string | null;
    raw_import_json?: unknown;
  } | null
) {
  if (!item) return null;
  if (item.supplier_listing_url) return item.supplier_listing_url;

  const itemId =
    extractItemIdFromSku(item.supplier_sku) ||
    findNestedString(item.raw_import_json, "ItemID");

  return itemId ? `https://www.ebay.com/itm/${itemId}` : null;
}

function extractItemIdFromSku(value?: string | null) {
  if (!value) return null;

  const match = value.match(/^(\d{9,15})(?:-|$)/);

  return match ? match[1] : null;
}

function findNestedString(value: unknown, key: string): string | null {
  const foundValue = findNestedValue(value, key);

  return typeof foundValue === "string" && foundValue.trim() !== ""
    ? foundValue.trim()
    : null;
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

function localDateString() {
  const formatter = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Los_Angeles",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });

  return formatter.format(new Date());
}
