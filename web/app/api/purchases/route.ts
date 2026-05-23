import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

import {
  compactMatchTitle,
  normalizeMatchTitle,
  normalizeSystem,
} from "../../purchases/matchingKeys";

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
        ebayEstimatedDeliveryDate: getEbayEstimatedDeliveryDate(
          purchase.raw_import_json
        ),
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
      estimated_delivery_date:
        row.estimated_delivery_date ??
        purchaseMetaById.get(row.purchase_id)?.ebayEstimatedDeliveryDate ??
        null,
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

function getEbayEstimatedDeliveryDate(rawImportJson: unknown) {
  if (!rawImportJson || typeof rawImportJson !== "object") return null;

  const order = "Order" in rawImportJson ? rawImportJson.Order : rawImportJson;
  const estimate = findNestedValue(order, "EstimatedDeliveryTimeMax");

  return typeof estimate === "string" && estimate.trim() !== ""
    ? estimate
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

  const { data: sourceItem, error: sourceError } = await supabase
    .from("purchase_items")
    .select("item_id,title,amazon_title,system,asin,target_price")
    .eq("item_id", itemId)
    .single();

  if (sourceError) {
    return NextResponse.json(
      { error: sourceError.message },
      { status: 500 }
    );
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

  const propagatedItems = await propagateManualMatch(sourceItem, data, updates);

  return NextResponse.json({
    success: true,
    item: data,
    propagated_items: propagatedItems,
  });
}

type PurchaseItem = {
  item_id: string;
  title: string | null;
  amazon_title: string | null;
  system: string | null;
  asin: string | null;
  target_price: number | string | null;
};

async function propagateManualMatch(
  sourceItem: PurchaseItem,
  updatedItem: PurchaseItem,
  updates: {
    asin?: string | null;
    target_price?: number | null;
  }
) {
  const asinWasUpdated = "asin" in updates;
  const targetPriceWasUpdated = "target_price" in updates;

  if (!asinWasUpdated && !targetPriceWasUpdated) return [];

  const normalizedTitle = normalizeMatchTitle(sourceItem.title);
  const compactTitle = compactMatchTitle(normalizedTitle);
  const system = normalizeSystem(sourceItem.system);
  const correctedAsin = updatedItem.asin?.trim().toUpperCase() || null;
  const correctedTargetPrice =
    updatedItem.target_price === null || updatedItem.target_price === undefined
      ? null
      : Number(updatedItem.target_price);

  if (!normalizedTitle || !compactTitle || !system) return [];

  if (correctedAsin) {
    await upsertManualMatch({
      normalizedTitle,
      compactTitle,
      system,
      asin: correctedAsin,
      amazonTitle: updatedItem.amazon_title,
      targetPrice: correctedTargetPrice,
      sourceItemId: updatedItem.item_id,
      sourceTitle: sourceItem.title,
    });
  }

  const candidateItems = await fetchCandidateItems(updatedItem.item_id);

  const matchingItems = (candidateItems ?? []).filter((item) => {
    if (normalizeSystem(item.system) !== system) return false;

    const candidateTitle = normalizeMatchTitle(item.title);
    if (!candidateTitle) return false;

    return (
      candidateTitle === normalizedTitle ||
      compactMatchTitle(candidateTitle) === compactTitle
    );
  });

  const propagatedItems = [];

  for (const item of matchingItems) {
    if (item.asin && correctedAsin && item.asin !== correctedAsin) {
      continue;
    }

    const itemUpdates: {
      asin?: string;
      amazon_title?: string | null;
      target_price?: number | null;
    } = {};

    if (correctedAsin && !item.asin) {
      itemUpdates.asin = correctedAsin;

      if (updatedItem.amazon_title) {
        itemUpdates.amazon_title = updatedItem.amazon_title;
      }
    }

    if (targetPriceWasUpdated) {
      itemUpdates.target_price = correctedTargetPrice;
    }

    if (Object.keys(itemUpdates).length === 0) continue;

    const { data: propagatedItem, error: updateError } = await supabase
      .from("purchase_items")
      .update(itemUpdates)
      .eq("item_id", item.item_id)
      .select()
      .single();

    if (updateError) {
      console.error("Failed to propagate manual match", updateError);
      continue;
    }

    propagatedItems.push(propagatedItem);
  }

  return propagatedItems;
}

async function fetchCandidateItems(excludedItemId: string) {
  const pageSize = 1000;
  const items: PurchaseItem[] = [];
  let offset = 0;

  while (true) {
    const { data, error } = await supabase
      .from("purchase_items")
      .select("item_id,title,amazon_title,system,asin,target_price")
      .neq("item_id", excludedItemId)
      .range(offset, offset + pageSize - 1);

    if (error) {
      console.error("Failed to load purchase items for manual match propagation", error);
      return items;
    }

    items.push(...((data ?? []) as PurchaseItem[]));

    if ((data ?? []).length < pageSize) return items;

    offset += pageSize;
  }
}

async function upsertManualMatch(match: {
  normalizedTitle: string;
  compactTitle: string;
  system: string;
  asin: string;
  amazonTitle: string | null;
  targetPrice: number | null;
  sourceItemId: string;
  sourceTitle: string | null;
}) {
  const { error } = await supabase
    .from("manual_item_matches")
    .upsert(
      {
        normalized_title: match.normalizedTitle,
        compact_title: match.compactTitle,
        system: match.system,
        asin: match.asin,
        amazon_title: match.amazonTitle,
        target_price: match.targetPrice,
        source_purchase_item_id: match.sourceItemId,
        source_title: match.sourceTitle,
        match_source: "manual_ui",
        updated_at: new Date().toISOString(),
      },
      { onConflict: "normalized_title,system" }
    );

  if (error) {
    console.warn(
      "Manual match memory was not saved. Apply sql/2026-05-22_add_manual_item_matches.sql to enable it.",
      error.message
    );
  }
}
