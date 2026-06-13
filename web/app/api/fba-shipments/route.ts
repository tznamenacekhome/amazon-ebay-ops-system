import { NextRequest, NextResponse } from "next/server";
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

type ShipmentRow = {
  fba_shipment_id: string;
  shipment_code: string;
  workflow_status: string | null;
  amazon_status_raw: string | null;
  amazon_status_normalized: string | null;
  fulfillment_center_id: string | null;
  destination_fulfillment_center_id: string | null;
  carrier_name: string | null;
  tracking_number: string | null;
  carrier_tracking_url: string | null;
  carrier_pickup_at: string | null;
  carrier_delivery_eta: string | null;
  carrier_delivered_at: string | null;
  amazon_checked_in_at: string | null;
  amazon_receiving_started_at: string | null;
  amazon_closed_at: string | null;
  all_units_available_at: string | null;
  units_sent: number | null;
  units_expected: number | null;
  units_received: number | null;
  units_available: number | null;
  units_reserved: number | null;
  units_unfulfillable: number | null;
  units_missing: number | null;
  fba_availability_pct: number | null;
  cost_sent: number | null;
  outbound_remaining_cost: number | null;
  amazon_received_cost: number | null;
  amazon_available_cost: number | null;
  attention_flags: string[] | null;
  finalized_at: string | null;
  last_amazon_sync_at: string | null;
  updated_at: string | null;
};

type ShipmentItemRow = {
  fba_shipment_item_id: string;
  fba_shipment_id: string;
  item_id: string;
  quantity: number | null;
  asin: string | null;
  amazon_title: string | null;
  system: string | null;
  unit_cost: number | null;
  target_price: number | null;
  seller_sku: string | null;
  fnsku: string | null;
  expected_quantity: number | null;
  received_quantity: number | null;
  available_quantity: number | null;
  reserved_quantity: number | null;
  unfulfillable_quantity: number | null;
  missing_quantity: number | null;
  outbound_remaining_quantity: number | null;
  cost_sent: number | null;
  outbound_remaining_cost: number | null;
  amazon_received_cost: number | null;
  amazon_available_cost: number | null;
};

export async function GET(request: NextRequest) {
  const mode = request.nextUrl.searchParams.get("mode");
  if (mode === "shipments") {
    return getShipments();
  }

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

    const titleFallbacks = await fetchAmazonTitleFallbacks(
      Array.from(new Set(candidates.map((candidate) => candidate.asin)))
    );

    return NextResponse.json(groupCandidates(candidates, titleFallbacks));
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Failed to load FBA workflow" },
      { status: 500 }
    );
  }
}

async function getShipments() {
  try {
    const { data, error } = await supabase
      .from("fba_shipments")
      .select("*")
      .neq("shipment_code", "legacy_listed_no_shipment_id")
      .order("finalized_at", { ascending: false, nullsFirst: false })
      .limit(100);

    if (error) throw new Error(error.message);

    const shipments = (data ?? []) as ShipmentRow[];
    const shipmentIds = shipments.map((row) => row.fba_shipment_id).filter(Boolean);
    const items = await fetchShipmentItems(shipmentIds);
    const itemsByShipment = new Map<string, ShipmentItemRow[]>();
    for (const item of items) {
      const rows = itemsByShipment.get(item.fba_shipment_id) ?? [];
      rows.push(item);
      itemsByShipment.set(item.fba_shipment_id, rows);
    }

    const rows = shipments.map((shipment) => {
      const detailRows = itemsByShipment.get(shipment.fba_shipment_id) ?? [];
      const computed = summarizeShipmentFromItems(detailRows);
      return {
        id: shipment.fba_shipment_id,
        shipment_code: shipment.shipment_code,
        workflow_status: shipment.workflow_status,
        amazon_status_raw: shipment.amazon_status_raw,
        amazon_status_normalized: shipment.amazon_status_normalized,
        fulfillment_center_id:
          shipment.fulfillment_center_id || shipment.destination_fulfillment_center_id,
        carrier_name: shipment.carrier_name,
        tracking_number: shipment.tracking_number,
        carrier_tracking_url: shipment.carrier_tracking_url,
        carrier_pickup_at: shipment.carrier_pickup_at,
        carrier_delivery_eta: shipment.carrier_delivery_eta,
        carrier_delivered_at: shipment.carrier_delivered_at,
        amazon_checked_in_at: shipment.amazon_checked_in_at,
        amazon_receiving_started_at: shipment.amazon_receiving_started_at,
        amazon_closed_at: shipment.amazon_closed_at,
        all_units_available_at: shipment.all_units_available_at,
        units_sent: toNumber(shipment.units_sent) ?? computed.units_sent,
        units_expected: toNumber(shipment.units_expected) ?? computed.units_expected,
        units_received: toNumber(shipment.units_received) ?? computed.units_received,
        units_available: toNumber(shipment.units_available) ?? computed.units_available,
        units_reserved: toNumber(shipment.units_reserved) ?? computed.units_reserved,
        units_unfulfillable:
          toNumber(shipment.units_unfulfillable) ?? computed.units_unfulfillable,
        units_missing: toNumber(shipment.units_missing) ?? computed.units_missing,
        fba_availability_pct:
          toNumber(shipment.fba_availability_pct) ??
          percent(computed.units_available, computed.units_sent),
        cost_sent: toNumber(shipment.cost_sent) ?? computed.cost_sent,
        outbound_remaining_cost:
          toNumber(shipment.outbound_remaining_cost) ?? computed.outbound_remaining_cost,
        amazon_received_cost:
          toNumber(shipment.amazon_received_cost) ?? computed.amazon_received_cost,
        amazon_available_cost:
          toNumber(shipment.amazon_available_cost) ?? computed.amazon_available_cost,
        attention_flags: Array.isArray(shipment.attention_flags)
          ? shipment.attention_flags
          : [],
        finalized_at: shipment.finalized_at,
        last_amazon_sync_at: shipment.last_amazon_sync_at,
        updated_at: shipment.updated_at,
        details: detailRows
          .map((item) => ({
            id: item.fba_shipment_item_id,
            item_id: item.item_id,
            asin: item.asin,
            amazon_title: item.amazon_title,
            system: item.system,
            seller_sku: item.seller_sku,
            fnsku: item.fnsku,
            quantity_sent: toNumber(item.quantity) ?? 0,
            expected_quantity: toNumber(item.expected_quantity),
            received_quantity: toNumber(item.received_quantity),
            available_quantity: toNumber(item.available_quantity),
            reserved_quantity: toNumber(item.reserved_quantity),
            unfulfillable_quantity: toNumber(item.unfulfillable_quantity),
            missing_quantity: toNumber(item.missing_quantity),
            outbound_remaining_quantity: toNumber(item.outbound_remaining_quantity),
            unit_cost: toNumber(item.unit_cost),
            target_price: toNumber(item.target_price),
            cost_sent: toNumber(item.cost_sent),
            outbound_remaining_cost: toNumber(item.outbound_remaining_cost),
            amazon_received_cost: toNumber(item.amazon_received_cost),
            amazon_available_cost: toNumber(item.amazon_available_cost),
          }))
          .sort((left, right) => compareStrings(left.asin, right.asin)),
      };
    });

    const totals = rows.reduce(
      (sum, row) => ({
        shipments: sum.shipments + 1,
        units_sent: sum.units_sent + Number(row.units_sent ?? 0),
        units_received: sum.units_received + Number(row.units_received ?? 0),
        units_available: sum.units_available + Number(row.units_available ?? 0),
        outbound_remaining_cost:
          sum.outbound_remaining_cost + Number(row.outbound_remaining_cost ?? 0),
      }),
      {
        shipments: 0,
        units_sent: 0,
        units_received: 0,
        units_available: 0,
        outbound_remaining_cost: 0,
      }
    );

    return NextResponse.json({ totals, rows });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Failed to load FBA shipments" },
      { status: 500 }
    );
  }
}

async function fetchShipmentItems(shipmentIds: string[]) {
  const rows: ShipmentItemRow[] = [];
  const chunkSize = 250;
  for (let index = 0; index < shipmentIds.length; index += chunkSize) {
    const chunk = shipmentIds.slice(index, index + chunkSize);
    const { data, error } = await supabase
      .from("fba_shipment_items")
      .select("*")
      .in("fba_shipment_id", chunk)
      .eq("included", true);

    if (error) throw new Error(error.message);
    rows.push(...((data ?? []) as ShipmentItemRow[]));
  }
  return rows;
}

function summarizeShipmentFromItems(items: ShipmentItemRow[]) {
  return items.reduce(
    (sum, item) => {
      const quantity = toNumber(item.quantity) ?? 0;
      const unitCost = toNumber(item.unit_cost) ?? 0;
      const costSent = toNumber(item.cost_sent) ?? quantity * unitCost;
      const outboundCost =
        toNumber(item.outbound_remaining_cost) ??
        (toNumber(item.outbound_remaining_quantity) ?? quantity) * unitCost;

      return {
        units_sent: sum.units_sent + quantity,
        units_expected: sum.units_expected + (toNumber(item.expected_quantity) ?? quantity),
        units_received: sum.units_received + (toNumber(item.received_quantity) ?? 0),
        units_available: sum.units_available + (toNumber(item.available_quantity) ?? 0),
        units_reserved: sum.units_reserved + (toNumber(item.reserved_quantity) ?? 0),
        units_unfulfillable:
          sum.units_unfulfillable + (toNumber(item.unfulfillable_quantity) ?? 0),
        units_missing: sum.units_missing + (toNumber(item.missing_quantity) ?? 0),
        cost_sent: sum.cost_sent + costSent,
        outbound_remaining_cost: sum.outbound_remaining_cost + outboundCost,
        amazon_received_cost:
          sum.amazon_received_cost + (toNumber(item.amazon_received_cost) ?? 0),
        amazon_available_cost:
          sum.amazon_available_cost + (toNumber(item.amazon_available_cost) ?? 0),
      };
    },
    {
      units_sent: 0,
      units_expected: 0,
      units_received: 0,
      units_available: 0,
      units_reserved: 0,
      units_unfulfillable: 0,
      units_missing: 0,
      cost_sent: 0,
      outbound_remaining_cost: 0,
      amazon_received_cost: 0,
      amazon_available_cost: 0,
    }
  );
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

async function fetchAmazonTitleFallbacks(asins: string[]) {
  const titleByAsin = new Map<string, string>();
  const chunkSize = 500;

  for (let index = 0; index < asins.length; index += chunkSize) {
    const chunk = asins.slice(index, index + chunkSize);
    const { data, error } = await supabase
      .from("purchase_items")
      .select("asin,amazon_title")
      .in("asin", chunk)
      .not("amazon_title", "is", null);

    if (error) {
      console.warn("FBA title fallback lookup failed", error.message);
      continue;
    }

    for (const item of data ?? []) {
      const asin = normalizeAsin(item.asin);
      if (asin && item.amazon_title && !titleByAsin.has(asin)) {
        titleByAsin.set(asin, item.amazon_title);
      }
    }
  }

  return titleByAsin;
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
  }>,
  titleFallbacks: Map<string, string>
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
      title: candidate.amazon_title || titleFallbacks.get(candidate.asin) || null,
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

    group.title =
      group.title ||
      candidate.amazon_title ||
      titleFallbacks.get(candidate.asin) ||
      null;
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
      details: group.details.sort((left, right) => {
        const dateCompare = compareStrings(left.order_date, right.order_date);
        if (dateCompare !== 0) return dateCompare;
        return compareStrings(left.supplier_order_id, right.supplier_order_id);
      }),
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

function percent(numerator: number, denominator: number) {
  if (!denominator) return null;
  return Math.round((numerator / denominator) * 1000) / 10;
}

function compareStrings(left?: string | null, right?: string | null) {
  return (left || "").localeCompare(right || "", undefined, {
    numeric: true,
    sensitivity: "base",
  });
}
