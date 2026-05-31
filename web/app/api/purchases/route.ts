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

type PurchaseListRow = {
  item_id: string;
  purchase_id: string;
  order_date: string | null;
  supplier: string | null;
  supplier_order_id: string | null;
  title: string | null;
  system: string | null;
  asin: string | null;
  sell_price: number | null;
  target_price?: number | null;
  unit_cost: number | null;
  quantity: number | null;
  current_status: string | null;
  tracking_number: string | null;
  supplier_listing_url: string | null;
  carrier: string | null;
  delivery_status: string | null;
  estimated_delivery_date: string | null;
  delivered_date: string | null;
};

export async function GET(request: Request) {
  const requestUrl = new URL(request.url);
  const query = parsePurchaseQuery(requestUrl);
  const excludedItemIds = await fetchExcludedItemIds();
  const amazonTitleReviewItemIds = await fetchAmazonTitleReviewItemIds(
    excludedItemIds
  );
  let rows: PurchaseListRow[];
  let total = 0;

  try {
    const result = await fetchPurchaseRows(
      query,
      excludedItemIds,
      amazonTitleReviewItemIds
    );
    rows = result.rows as unknown as PurchaseListRow[];
    total = result.total;
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
    return NextResponse.json({
      rows: viewRows,
      total,
      page: query.page,
      pageSize: query.pageSize,
      stats: await fetchPurchaseStats(
        query,
        total,
        excludedItemIds,
        amazonTitleReviewItemIds
      ),
    });
  }

  const itemMeta = await fetchItemMeta(itemIds);
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

  const responseRows = viewRows.map((row) => ({
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
  }));

  return NextResponse.json({
    rows: responseRows,
    total,
    page: query.page,
    pageSize: query.pageSize,
    stats: await fetchPurchaseStats(
      query,
      total,
      excludedItemIds,
      amazonTitleReviewItemIds
    ),
  });
}

type PurchaseQuery = {
  searchText: string;
  asinFilter: string;
  statusFilter: string;
  sortColumn: string;
  sortDirection: "asc" | "desc";
  page: number;
  pageSize: number;
};

function parsePurchaseQuery(url: URL): PurchaseQuery {
  const page = Math.max(Number(url.searchParams.get("page") || "1"), 1);
  const pageSize = Math.min(
    Math.max(Number(url.searchParams.get("pageSize") || "100"), 25),
    500
  );
  const sortColumn = url.searchParams.get("sortColumn") || "order_date";
  const sortDirection =
    url.searchParams.get("sortDirection") === "asc" ? "asc" : "desc";

  return {
    searchText: (url.searchParams.get("search") || "").trim(),
    asinFilter: url.searchParams.get("asinFilter") || "all",
    statusFilter: url.searchParams.get("statusFilter") || "active",
    sortColumn,
    sortDirection,
    page,
    pageSize,
  };
}

async function fetchPurchaseRows(
  query: PurchaseQuery,
  excludedItemIds: string[],
  amazonTitleReviewItemIds: string[]
) {
  const rangeStart = (query.page - 1) * query.pageSize;
  const rangeEnd = rangeStart + query.pageSize - 1;
  const sortColumn = purchaseSortColumn(query.sortColumn);
  const ascending = query.sortDirection === "asc";

  let request = supabase
    .from("vw_purchases_dashboard")
    .select(
      [
        "item_id",
        "purchase_id",
        "order_date",
        "supplier",
        "supplier_order_id",
        "title",
        "system",
        "asin",
        "sell_price",
        "target_price:sell_price",
        "unit_cost",
        "quantity",
        "current_status",
        "tracking_number",
        "supplier_listing_url",
        "carrier",
        "delivery_status",
        "estimated_delivery_date",
        "delivered_date",
      ].join(","),
      { count: "exact" }
    );

  request = applyServerFilters(
    request,
    query,
    excludedItemIds,
    amazonTitleReviewItemIds
  );

  const { data, error, count } = await request
    .order(sortColumn, { ascending, nullsFirst: false })
    .range(rangeStart, rangeEnd);

  if (error) throw new Error(error.message);

  return {
    rows: data ?? [],
    total: count ?? 0,
  };
}

function applyServerFilters(
  request: any,
  query: PurchaseQuery,
  excludedItemIds: string[],
  amazonTitleReviewItemIds: string[]
) {
  if (excludedItemIds.length > 0) {
    request = request.not("item_id", "in", `(${excludedItemIds.join(",")})`);
  }

  if (query.statusFilter === "active") {
    request = request.neq("current_status", "listed");
  } else if (query.statusFilter !== "all") {
    request = request.eq("current_status", query.statusFilter);
  }

  if (query.asinFilter === "matched") {
    request = request.not("asin", "is", null).neq("asin", "N/A");
  } else if (query.asinFilter === "needs_review") {
    request = request.not(
      "current_status",
      "in",
      "(listed,cancelled,return_opened,return_pending)"
    );
    const needsReviewClauses = [
      "asin.is.null",
      "asin.eq.N/A",
      "sell_price.is.null",
      "system.is.null",
    ];

    if (amazonTitleReviewItemIds.length > 0) {
      needsReviewClauses.push(
        `item_id.in.(${amazonTitleReviewItemIds.join(",")})`
      );
    }

    request = request.or(needsReviewClauses.join(","));
  } else if (query.asinFilter === "order_problems") {
    request = request.or(
      [
        `and(estimated_delivery_date.lt.${todayDateString()},current_status.not.in.(delivered,received,listed,cancelled,return_opened))`,
        `and(current_status.in.(no_tracking,shipped_no_tracking,awaiting_carrier_scan),order_date.lte.${daysAgoDateString(7)},order_date.gte.${daysAgoDateString(90)})`,
        "current_status.in.(exception,return_pending)",
      ].join(",")
    );
  }

  if (query.searchText) {
    const term = escapeIlike(query.searchText);
    request = request.or(
      [
        `title.ilike.%${term}%`,
        `asin.ilike.%${term}%`,
        `system.ilike.%${term}%`,
        `supplier.ilike.%${term}%`,
        `supplier_order_id.ilike.%${term}%`,
        `tracking_number.ilike.%${term}%`,
        `carrier.ilike.%${term}%`,
      ].join(",")
    );
  }

  return request;
}

function purchaseSortColumn(column: string) {
  const columns: Record<string, string> = {
    order_date: "order_date",
    supplier_order_id: "supplier_order_id",
    item: "title",
    asin: "asin",
    system: "system",
    quantity: "quantity",
    unit_cost: "unit_cost",
    sell_price: "sell_price",
    carrier: "carrier",
    eta: "estimated_delivery_date",
    status: "current_status",
  };

  return columns[column] || "order_date";
}

function escapeIlike(value: string) {
  return value.replace(/[%_,]/g, "\\$&");
}

function todayDateString() {
  return dateStringDaysAgo(0);
}

function daysAgoDateString(days: number) {
  return dateStringDaysAgo(days);
}

function dateStringDaysAgo(days: number) {
  const date = new Date();
  date.setUTCDate(date.getUTCDate() - days);
  return date.toISOString().slice(0, 10);
}

async function fetchPurchaseStats(
  query: PurchaseQuery,
  visibleTotal: number,
  excludedItemIds: string[],
  amazonTitleReviewItemIds: string[]
) {
  const [total, needsReview, orderProblems, delivered] = await Promise.all([
    countPurchaseRows(
      { ...query, searchText: "", asinFilter: "all", statusFilter: "all" },
      excludedItemIds,
      amazonTitleReviewItemIds
    ),
    countPurchaseRows(
      { ...query, searchText: "", asinFilter: "needs_review", statusFilter: "active" },
      excludedItemIds,
      amazonTitleReviewItemIds
    ),
    countPurchaseRows(
      { ...query, searchText: "", asinFilter: "order_problems", statusFilter: "active" },
      excludedItemIds,
      amazonTitleReviewItemIds
    ),
    countPurchaseRows(
      { ...query, searchText: "", asinFilter: "all", statusFilter: "delivered" },
      excludedItemIds,
      amazonTitleReviewItemIds
    ),
  ]);

  return {
    total,
    visible: visibleTotal,
    needsReview,
    orderProblems,
    delivered,
  };
}

async function countPurchaseRows(
  query: PurchaseQuery,
  excludedItemIds: string[],
  amazonTitleReviewItemIds: string[]
) {
  let request = supabase
    .from("vw_purchases_dashboard")
    .select("item_id", { count: "exact", head: true });

  request = applyServerFilters(
    request,
    query,
    excludedItemIds,
    amazonTitleReviewItemIds
  );

  const { count, error } = await request;
  if (error) {
    console.warn("Purchase count failed", error.message);
    return 0;
  }

  return count ?? 0;
}

async function fetchExcludedItemIds() {
  const excludedItemIds: string[] = [];
  const pageSize = 1000;
  let offset = 0;

  while (true) {
    const { data, error } = await supabase
      .from("purchase_items")
      .select("item_id")
      .eq("exclude_from_purchase_reporting", true)
      .range(offset, offset + pageSize - 1);

    if (error) {
      console.warn("Purchase exclusion lookup failed", error.message);
      return excludedItemIds;
    }

    excludedItemIds.push(
      ...((data ?? []) as { item_id: string }[]).map((item) => item.item_id)
    );

    if ((data ?? []).length < pageSize) return excludedItemIds;

    offset += pageSize;
  }
}

async function fetchAmazonTitleReviewItemIds(excludedItemIds: string[]) {
  const itemIds: string[] = [];
  const pageSize = 1000;
  let offset = 0;

  while (true) {
    let request: any = supabase
      .from("purchase_items")
      .select("item_id")
      .not("asin", "is", null)
      .neq("asin", "N/A")
      .is("amazon_title", null)
      .not(
        "current_status",
        "in",
        "(listed,cancelled,return_opened,return_pending)"
      );

    if (excludedItemIds.length > 0) {
      request = request.not("item_id", "in", `(${excludedItemIds.join(",")})`);
    }

    const { data, error } = await request.range(offset, offset + pageSize - 1);

    if (error) {
      console.warn("Amazon title review lookup failed", error.message);
      return itemIds;
    }

    itemIds.push(
      ...((data ?? []) as { item_id: string }[]).map((item) => item.item_id)
    );

    if ((data ?? []).length < pageSize) return itemIds;

    offset += pageSize;
  }
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
    amazon_title?: string | null;
    target_price?: number | null;
    title?: string | null;
    unit_cost?: number | null;
    system?: string | null;
    current_status?: string;
    manual_title_override?: boolean;
    manual_unit_cost_override?: boolean;
  } = {};

  if ("asin" in body) {
    updates.asin = body.asin ? String(body.asin).trim().toUpperCase() : null;
  }

  if ("amazon_title" in body) {
    const amazonTitle =
      body.amazon_title === null ? "" : String(body.amazon_title ?? "").trim();
    updates.amazon_title = amazonTitle || null;
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

  if ("current_status" in body) {
    const currentStatus = String(body.current_status ?? "").trim();

    if (currentStatus !== "return_pending") {
      return NextResponse.json(
        { error: "current_status can only be set to return_pending here" },
        { status: 400 }
      );
    }

    updates.current_status = currentStatus;
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
    amazon_title?: string | null;
    target_price?: number | null;
  }
) {
  const asinWasUpdated = "asin" in updates;
  const amazonTitleWasUpdated = "amazon_title" in updates;
  const targetPriceWasUpdated = "target_price" in updates;

  if (!asinWasUpdated && !amazonTitleWasUpdated && !targetPriceWasUpdated) {
    return [];
  }

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

      if (updatedItem.amazon_title && (!item.amazon_title || amazonTitleWasUpdated)) {
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
