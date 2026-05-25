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
  let rows;

  try {
    rows = await fetchAllPurchaseRows();
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Failed to load purchases" },
      { status: 500 }
    );
  }

  const viewRows = rows.map((row) => ({
    ...row,
    ebay_title: row.title,
  }));
  const itemIds = viewRows
    .map((row) => row.item_id)
    .filter((itemId): itemId is string => typeof itemId === "string");
  const purchaseIds = viewRows
    .map((row) => row.purchase_id)
    .filter((purchaseId): purchaseId is string => typeof purchaseId === "string");

  if (itemIds.length === 0 && purchaseIds.length === 0) {
    return NextResponse.json(viewRows);
  }

  const itemMeta = await fetchItemMeta(itemIds);
  const excludedItemIds = new Set(
    itemMeta
      .filter((item) => item.exclude_from_purchase_reporting)
      .map((item) => item.item_id)
  );
  const includedRows = viewRows.filter(
    (row) => !excludedItemIds.has(row.item_id)
  );

  const amazonTitleByItemId = new Map(
    itemMeta.map((item) => [item.item_id, item.amazon_title])
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
    includedRows.map((row) => ({
      ...row,
      amazon_title: amazonTitleByItemId.get(row.item_id) ?? null,
      exclude_from_purchase_reporting: false,
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

async function fetchAllPurchaseRows() {
  const rows = [];
  const pageSize = 1000;
  let offset = 0;

  while (true) {
    const { data, error } = await supabase
      .from("vw_purchases_dashboard")
      .select("*")
      .order("order_date", { ascending: false })
      .range(offset, offset + pageSize - 1);

    if (error) {
      throw new Error(error.message);
    }

    rows.push(...(data ?? []));

    if (!data || data.length < pageSize) break;

    offset += pageSize;
  }

  return rows;
}

async function fetchItemMeta(itemIds: string[]) {
  const rows: {
    item_id: string;
    amazon_title: string | null;
    exclude_from_purchase_reporting: boolean | null;
    exclusion_reason: string | null;
  }[] = [];
  const chunkSize = 500;

  for (let index = 0; index < itemIds.length; index += chunkSize) {
    const chunk = itemIds.slice(index, index + chunkSize);
    const { data, error } = await supabase
      .from("purchase_items")
      .select("item_id,amazon_title,exclude_from_purchase_reporting,exclusion_reason")
      .in("item_id", chunk);

    if (error) {
      console.warn("Purchase item title lookup failed", error.message);
      continue;
    }

    rows.push(
      ...((data ?? []) as {
        item_id: string;
        amazon_title: string | null;
        exclude_from_purchase_reporting: boolean | null;
        exclusion_reason: string | null;
      }[])
    );
  }

  return rows;
}

async function fetchPurchaseMeta(purchaseIds: string[]) {
  const rows: {
    purchase_id: string;
    order_status: string | null;
    raw_import_json: unknown;
  }[] = [];
  const chunkSize = 500;

  for (let index = 0; index < purchaseIds.length; index += chunkSize) {
    const chunk = purchaseIds.slice(index, index + chunkSize);
    const { data, error } = await supabase
      .from("purchases")
      .select("purchase_id,order_status,raw_import_json")
      .in("purchase_id", chunk);

    if (error) {
      console.warn("Purchase metadata lookup failed", error.message);
      continue;
    }

    rows.push(
      ...((data ?? []) as {
        purchase_id: string;
        order_status: string | null;
        raw_import_json: unknown;
      }[])
    );
  }

  return rows;
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
    title?: string | null;
    unit_cost?: number | null;
    system?: string | null;
    manual_title_override?: boolean;
    manual_unit_cost_override?: boolean;
  } = {};

  if ("asin" in body) {
    updates.asin = body.asin ? String(body.asin).trim().toUpperCase() : null;
  }

  if ("sell_price" in body) {
    updates.target_price =
      body.sell_price === null || body.sell_price === ""
        ? null
        : Number(body.sell_price);

    if (Number.isNaN(updates.target_price)) {
      return NextResponse.json(
        { error: "sell_price must be a valid number" },
        { status: 400 }
      );
    }
  }

  if ("title" in body) {
    const title = body.title === null ? "" : String(body.title ?? "").trim();
    updates.title = title || null;
    updates.manual_title_override = true;
  }

  if ("unit_cost" in body) {
    updates.unit_cost =
      body.unit_cost === null || body.unit_cost === ""
        ? null
        : Number(body.unit_cost);

    if (Number.isNaN(updates.unit_cost)) {
      return NextResponse.json(
        { error: "unit_cost must be a valid number" },
        { status: 400 }
      );
    }

    updates.manual_unit_cost_override = true;
  }

  if ("system" in body) {
    const system = body.system === null ? "" : String(body.system ?? "").trim();
    updates.system = system || null;
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

  const responseItem = {
    ...data,
    ebay_title: data.title,
    sell_price: data.target_price,
  };
  const propagatedItems = await propagateManualMatch(
    sourceItem,
    responseItem,
    updates
  );

  return NextResponse.json({
    success: true,
    item: responseItem,
    propagated_items: propagatedItems,
  });
}

export async function POST(request: Request) {
  const body = await request.json();
  const sourceItemId = body.source_item_id as string | undefined;

  if (!sourceItemId) {
    return NextResponse.json(
      { error: "source_item_id is required" },
      { status: 400 }
    );
  }

  const { data: sourceData, error: sourceError } = await supabase
    .from("purchase_items")
    .select(
      "item_id,purchase_id,title,system,tracking_number,current_status,condition," +
        "supplier_listing_url,import_batch_id,raw_import_json"
    )
    .eq("item_id", sourceItemId)
    .single();

  if (sourceError) {
    return NextResponse.json(
      { error: sourceError.message },
      { status: 500 }
    );
  }

  const sourceItem = sourceData as unknown as {
    item_id: string;
    purchase_id: string;
    title: string | null;
    system: string | null;
    tracking_number: string | null;
    current_status: string | null;
    condition: string | null;
    supplier_listing_url: string | null;
    import_batch_id: string | null;
    raw_import_json: unknown;
  };

  const title =
    typeof body.title === "string" && body.title.trim()
      ? body.title.trim()
      : "Split item";
  const unitCost =
    body.unit_cost === null || body.unit_cost === undefined || body.unit_cost === ""
      ? null
      : Number(body.unit_cost);

  const splitPayload: Record<string, unknown> = {
    purchase_id: sourceItem.purchase_id,
    title,
    quantity: 1,
    unit_cost: Number.isNaN(unitCost) ? null : unitCost,
    asin: null,
    target_price: null,
    system: sourceItem.system,
    tracking_number: sourceItem.tracking_number,
    current_status: sourceItem.current_status,
    condition: sourceItem.condition,
    supplier_listing_url: sourceItem.supplier_listing_url,
    import_batch_id: sourceItem.import_batch_id,
    raw_import_json: sourceItem.raw_import_json,
    manual_title_override: true,
    manual_unit_cost_override: true,
    manual_split_child: true,
    manual_split_parent_item_id: sourceItem.item_id,
  };

  const { data: item, error } = await supabase
    .from("purchase_items")
    .insert(splitPayload)
    .select()
    .single();

  if (error) {
    return NextResponse.json(
      { error: error.message },
      { status: 500 }
    );
  }

  await linkSplitItemToExistingShipments(item.item_id, sourceItem.purchase_id);

  return NextResponse.json({ success: true, item });
}

async function linkSplitItemToExistingShipments(
  itemId: string,
  purchaseId: string
) {
  const { data: shipments, error } = await supabase
    .from("inbound_shipments")
    .select("inbound_shipment_id")
    .eq("purchase_id", purchaseId);

  if (error) {
    console.warn("Split item was not linked to shipments", error.message);
    return;
  }

  for (const shipment of shipments ?? []) {
    const { error: linkError } = await supabase
      .from("inbound_shipment_items")
      .insert({
        inbound_shipment_id: shipment.inbound_shipment_id,
        item_id: itemId,
        quantity_expected_in_package: 1,
        quantity_received_from_package: null,
        received_verified: false,
        notes: "Linked from manual purchase item split",
      });

    if (linkError && !linkError.message.includes("duplicate")) {
      console.warn("Split item shipment link failed", linkError.message);
    }
  }
}

type PurchaseItem = {
  item_id: string;
  title: string | null;
  ebay_title?: string | null;
  amazon_title: string | null;
  system: string | null;
  asin: string | null;
  target_price: number | string | null;
  sell_price?: number | string | null;
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

  const sourceTitle = updatedItem.title || sourceItem.title;
  const normalizedTitle = normalizeMatchTitle(sourceTitle);
  const compactTitle = compactMatchTitle(normalizedTitle);
  const system = normalizeSystem(updatedItem.system || sourceItem.system);
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
      sourceTitle,
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

    propagatedItems.push({
      ...propagatedItem,
      ebay_title: propagatedItem.title,
      sell_price: propagatedItem.target_price,
    });
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
