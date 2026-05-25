import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.SUPABASE_URL!;
const supabaseServiceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY!;

const supabase = createClient(supabaseUrl, supabaseServiceRoleKey);

type DashboardRow = {
  item_id: string;
  purchase_id: string;
  supplier_order_id: string | null;
  order_date: string | null;
  amazon_title: string | null;
  asin: string | null;
  system: string | null;
  quantity: number | null;
  unit_cost: number | null;
  sell_price?: number | null;
  target_price?: number | null;
  current_status: string | null;
};

type ItemMeta = {
  item_id: string;
  amazon_title: string | null;
  marketplace: "Amazon" | "eBay" | null;
  exclude_from_purchase_reporting: boolean | null;
};

type PurchaseMeta = {
  purchase_id: string;
  supplier: string | null;
};

type SaveItem = {
  item_id: string;
  quantity_to_send: number;
};

export async function GET() {
  try {
    const rows = await fetchReceivedRows();
    const itemIds = rows.map((row) => row.item_id).filter(Boolean);
    const purchaseIds = rows.map((row) => row.purchase_id).filter(Boolean);
    const itemMeta = await fetchItemMeta(itemIds);
    const purchaseMeta = await fetchPurchaseMeta(purchaseIds);

    const metaByItemId = new Map(itemMeta.map((item) => [item.item_id, item]));
    const supplierByPurchaseId = new Map(
      purchaseMeta.map((purchase) => [purchase.purchase_id, purchase.supplier])
    );

    const candidates = rows.flatMap((row) => {
      const meta = metaByItemId.get(row.item_id);
      if (meta?.exclude_from_purchase_reporting) return [];
      if (meta?.marketplace === "eBay") return [];

      const asin = normalizeAsin(row.asin);
      if (!asin) return [];

      const quantity = Number(row.quantity ?? 0);
      if (!Number.isFinite(quantity) || quantity <= 0) return [];

      return [
        {
          item_id: row.item_id,
          purchase_id: row.purchase_id,
          supplier_order_id: row.supplier_order_id,
          order_date: row.order_date,
          amazon_title: meta?.amazon_title ?? row.amazon_title ?? null,
          asin,
          system: row.system,
          quantity,
          unit_cost: toNumber(row.unit_cost),
          sell_price: toNumber(row.sell_price ?? row.target_price),
          supplier: supplierByPurchaseId.get(row.purchase_id) ?? null,
        },
      ];
    });

    return NextResponse.json(groupCandidates(candidates));
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Failed to load FBA workflow" },
      { status: 500 }
    );
  }
}

export async function POST(request: Request) {
  const body = await request.json();
  const shipmentCode =
    typeof body.shipment_id === "string" ? body.shipment_id.trim() : "";
  const items = Array.isArray(body.items) ? body.items : [];

  if (!shipmentCode) {
    return NextResponse.json(
      { error: "shipment_id is required" },
      { status: 400 }
    );
  }

  const requestedItems = normalizeSaveItems(items);

  if (requestedItems.length === 0) {
    return NextResponse.json(
      { error: "At least one unit must be included in the shipment" },
      { status: 400 }
    );
  }

  try {
    const { data: shipment, error: shipmentError } = await supabase
      .from("fba_shipments")
      .insert({
        shipment_code: shipmentCode,
        workflow_status: "finalized",
        finalized_at: new Date().toISOString(),
      })
      .select("fba_shipment_id,shipment_code")
      .single();

    if (shipmentError) throw new Error(shipmentError.message);

    const savedItems = [];

    for (const requestedItem of requestedItems) {
      const savedItem = await listPurchaseItem(
        shipment.fba_shipment_id,
        requestedItem.item_id,
        requestedItem.quantity_to_send
      );
      savedItems.push(savedItem);
    }

    return NextResponse.json({
      success: true,
      shipment,
      items: savedItems,
    });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Failed to save FBA shipment" },
      { status: 500 }
    );
  }
}

async function fetchReceivedRows() {
  const rows: DashboardRow[] = [];
  const pageSize = 1000;
  let offset = 0;

  while (true) {
    const { data, error } = await supabase
      .from("vw_purchases_dashboard")
      .select("*")
      .eq("current_status", "received")
      .range(offset, offset + pageSize - 1);

    if (error) throw new Error(error.message);

    rows.push(...((data ?? []) as DashboardRow[]));

    if (!data || data.length < pageSize) break;
    offset += pageSize;
  }

  return rows;
}

async function fetchItemMeta(itemIds: string[]) {
  const rows: ItemMeta[] = [];
  const chunkSize = 500;

  for (let index = 0; index < itemIds.length; index += chunkSize) {
    const chunk = itemIds.slice(index, index + chunkSize);
    const { data, error } = await supabase
      .from("purchase_items")
      .select("item_id,amazon_title,marketplace,exclude_from_purchase_reporting")
      .in("item_id", chunk);

    if (error) {
      console.warn("FBA item metadata lookup failed", error.message);
      continue;
    }

    rows.push(...((data ?? []) as ItemMeta[]));
  }

  return rows;
}

async function fetchPurchaseMeta(purchaseIds: string[]) {
  const rows: PurchaseMeta[] = [];
  const chunkSize = 500;

  for (let index = 0; index < purchaseIds.length; index += chunkSize) {
    const chunk = purchaseIds.slice(index, index + chunkSize);
    const { data, error } = await supabase
      .from("purchases")
      .select("purchase_id,supplier")
      .in("purchase_id", chunk);

    if (error) {
      console.warn("FBA purchase metadata lookup failed", error.message);
      continue;
    }

    rows.push(...((data ?? []) as PurchaseMeta[]));
  }

  return rows;
}

function groupCandidates(
  candidates: Array<{
    item_id: string;
    purchase_id: string;
    supplier_order_id: string | null;
    order_date: string | null;
    amazon_title: string | null;
    asin: string;
    system: string | null;
    quantity: number;
    unit_cost: number | null;
    sell_price: number | null;
    supplier: string | null;
  }>
) {
  const groups = new Map<string, {
    asin: string;
    title: string | null;
    system: string | null;
    quantity: number;
    total_cost: number;
    cost_quantity: number;
    cost_per_unit: number | null;
    sell_price: number | null;
    purchase_date: string | null;
    supplier: string;
    details: typeof candidates;
  }>();

  for (const candidate of candidates) {
    const group = groups.get(candidate.asin) ?? {
      asin: candidate.asin,
      title: candidate.amazon_title,
      system: candidate.system,
      quantity: 0,
      total_cost: 0,
      cost_quantity: 0,
      cost_per_unit: null,
      sell_price: null,
      purchase_date: candidate.order_date,
      supplier: "",
      details: [],
    };

    group.title = group.title || candidate.amazon_title;
    group.system = group.system || candidate.system;
    group.quantity += candidate.quantity;

    if (candidate.unit_cost !== null) {
      group.total_cost += candidate.unit_cost * candidate.quantity;
      group.cost_quantity += candidate.quantity;
    }

    if (candidate.sell_price !== null) {
      group.sell_price = Math.max(group.sell_price ?? candidate.sell_price, candidate.sell_price);
    }

    if (
      candidate.order_date &&
      (!group.purchase_date ||
        new Date(candidate.order_date).getTime() < new Date(group.purchase_date).getTime())
    ) {
      group.purchase_date = candidate.order_date;
    }

    group.details.push(candidate);
    groups.set(candidate.asin, group);
  }

  const groupedRows = Array.from(groups.values()).map((group) => {
    const suppliers = Array.from(
      new Set(group.details.map((detail) => detail.supplier).filter(Boolean))
    ) as string[];

    return {
      ...group,
      cost_per_unit:
        group.cost_quantity > 0 ? group.total_cost / group.cost_quantity : null,
      supplier: suppliers.join(", "),
      details: group.details.sort((left, right) =>
        compareStrings(left.supplier_order_id, right.supplier_order_id)
      ),
    };
  });

  groupedRows.sort((left, right) => {
    const systemCompare = compareStrings(left.system, right.system);
    if (systemCompare !== 0) return systemCompare;
    return compareStrings(left.title, right.title);
  });

  const totals = groupedRows.reduce(
    (sum, row) => ({
      units: sum.units + row.quantity,
      cost: sum.cost + row.total_cost,
      asins: sum.asins + 1,
    }),
    { units: 0, cost: 0, asins: 0 }
  );

  return { totals, rows: groupedRows };
}

function normalizeSaveItems(items: unknown[]): SaveItem[] {
  return items.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const value = item as Record<string, unknown>;
    const itemId = typeof value.item_id === "string" ? value.item_id : "";
    const quantityToSend = Number(value.quantity_to_send);

    if (!itemId || !Number.isFinite(quantityToSend) || quantityToSend <= 0) {
      return [];
    }

    return [{ item_id: itemId, quantity_to_send: quantityToSend }];
  });
}

async function listPurchaseItem(
  fbaShipmentId: string,
  itemId: string,
  quantityToSend: number
) {
  const { data, error } = await supabase
    .from("purchase_items")
    .select(
      "item_id,purchase_id,title,amazon_title,quantity,unit_cost,asin,target_price," +
        "system,condition,supplier_listing_url,supplier_sku,import_batch_id," +
        "raw_import_json,current_status,marketplace,received_date,tracking_number," +
        "manual_title_override,manual_unit_cost_override"
    )
    .eq("item_id", itemId)
    .single();

  if (error) throw new Error(error.message);

  const source = data as unknown as {
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
    supplier_sku: string | null;
    import_batch_id: string | null;
    raw_import_json: unknown;
    current_status: string | null;
    marketplace: "Amazon" | "eBay" | null;
    received_date: string | null;
    tracking_number: string | null;
    manual_title_override: boolean | null;
    manual_unit_cost_override: boolean | null;
  };

  const currentQuantity = Number(source.quantity ?? 0);
  const asin = normalizeAsin(source.asin);

  if (source.current_status !== "received") {
    throw new Error("Only Received items can be sent to FBA");
  }

  if (source.marketplace === "eBay") {
    throw new Error("eBay marketplace items cannot be sent to FBA");
  }

  if (!asin) {
    throw new Error("ASIN is required before sending to FBA");
  }

  if (!Number.isFinite(currentQuantity) || currentQuantity <= 0) {
    throw new Error("Purchase item quantity must be greater than zero");
  }

  if (quantityToSend > currentQuantity) {
    throw new Error("Quantity to send cannot exceed received quantity");
  }

  await markItemListed(source.item_id, quantityToSend);

  if (quantityToSend < currentQuantity) {
    await createReceivedRemainderSplit(source, currentQuantity - quantityToSend);
  }

  const { data: shipmentItem, error: shipmentItemError } = await supabase
    .from("fba_shipment_items")
    .insert({
      fba_shipment_id: fbaShipmentId,
      item_id: source.item_id,
      quantity: quantityToSend,
      asin,
      amazon_title: source.amazon_title,
      system: source.system,
      unit_cost: source.unit_cost,
      target_price: source.target_price,
      included: true,
    })
    .select()
    .single();

  if (shipmentItemError) throw new Error(shipmentItemError.message);

  return shipmentItem;
}

async function markItemListed(itemId: string, quantity: number) {
  const { error } = await supabase
    .from("purchase_items")
    .update({
      quantity,
      current_status: "listed",
    })
    .eq("item_id", itemId);

  if (error) throw new Error(error.message);
}

async function createReceivedRemainderSplit(
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
    supplier_sku: string | null;
    import_batch_id: string | null;
    raw_import_json: unknown;
    marketplace: "Amazon" | "eBay" | null;
    received_date: string | null;
    tracking_number: string | null;
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
    supplier_sku: source.supplier_sku,
    import_batch_id: source.import_batch_id,
    raw_import_json: source.raw_import_json,
    tracking_number: source.tracking_number,
    current_status: "received",
    marketplace: source.marketplace,
    received_date: source.received_date,
    manual_title_override: source.manual_title_override ?? false,
    manual_unit_cost_override: source.manual_unit_cost_override ?? false,
    manual_split_child: true,
    manual_split_parent_item_id: source.item_id,
  });

  if (error) throw new Error(error.message);
}

function normalizeAsin(value?: string | null) {
  return value ? value.trim().toUpperCase() : "";
}

function toNumber(value?: number | string | null) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function compareStrings(left?: string | null, right?: string | null) {
  return (left || "").localeCompare(right || "", undefined, {
    numeric: true,
    sensitivity: "base",
  });
}
