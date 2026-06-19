import { NextRequest, NextResponse } from "next/server";
import { createServerSupabaseClient, requireAdminApiToken } from "../_server";

const supabase = createServerSupabaseClient();

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

type KeepaPriceRow = {
  asin: string | null;
  captured_at: string | null;
  buy_box_price_current_cents: number | null;
  buy_box_price_avg90_cents: number | null;
  new_fba_price_current_cents: number | null;
};

type LastSoldRow = {
  asin: string;
  price: number;
  sold_at: string | null;
};

type FeeEstimateRow = {
  asin: string | null;
  listing_price: number | null;
  total_fees_estimate: number | null;
  referral_fee_estimate: number | null;
  fba_fee_estimate: number | null;
  variable_closing_fee_estimate: number | null;
  estimate_status: string | null;
  updated_at: string | null;
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

type PriceUpdateItem = {
  item_id: string;
  target_price: number;
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
  raw_tracking_json: unknown;
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

type ShipmentDetailApiRow = {
  id: string;
  item_id: string | null;
  asin: string | null;
  amazon_title: string | null;
  system: string | null;
  seller_sku: string | null;
  fnsku: string | null;
  quantity_sent: number;
  expected_quantity: number | null;
  received_quantity: number | null;
  available_quantity: number | null;
  reserved_quantity: number | null;
  unfulfillable_quantity: number | null;
  missing_quantity: number | null;
  outbound_remaining_quantity: number | null;
  unit_cost: number | null;
  target_price: number | null;
  cost_sent: number | null;
  outbound_remaining_cost: number | null;
  amazon_received_cost: number | null;
  amazon_available_cost: number | null;
  source: "mbop" | "amazon_v2024_box";
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
    const asins = Array.from(new Set(candidates.map((candidate) => candidate.asin)));
    const keepaPrices = await fetchKeepaPrices(asins);
    const lastSoldPrices = await fetchLastSoldPrices(asins);
    const feeEstimates = await fetchFeeEstimates(candidates);

    return NextResponse.json(
      groupCandidates(candidates, titleFallbacks, keepaPrices, lastSoldPrices, feeEstimates)
    );
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Failed to load FBA workflow" },
      { status: 500 }
    );
  }
}

export async function PATCH(request: NextRequest) {
  const adminError = requireAdminApiToken(request);
  if (adminError) return adminError;

  try {
    const body = await request.json();
    const items = normalizePriceUpdateItems(
      Array.isArray(body.items) ? body.items : []
    );

    if (!items.length) {
      return NextResponse.json(
        { error: "At least one item price update is required." },
        { status: 400 }
      );
    }

    for (const item of items) {
      const { error } = await supabase
        .from("purchase_items")
        .update({ target_price: item.target_price })
        .eq("item_id", item.item_id)
        .eq("current_status", "received");

      if (error) throw new Error(error.message);
    }

    return NextResponse.json({ success: true, updated: items.length });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Failed to update sell price" },
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
    const syntheticDetailRows = shipments.flatMap((shipment) =>
      buildV2024BoxDetails(shipment)
    );
    const titleFallbacks = await fetchAmazonTitleFallbacks(
      Array.from(
        new Set(
          syntheticDetailRows
            .map((detail) => normalizeAsin(detail.asin))
            .filter((asin): asin is string => Boolean(asin))
        )
      )
    );

    const rows = shipments.map((shipment) => {
      const detailRows = itemsByShipment.get(shipment.fba_shipment_id) ?? [];
      const hasTrackedItemRows = detailRows.length > 0;
      const computed = summarizeShipmentFromItems(detailRows);
      const details: ShipmentDetailApiRow[] = hasTrackedItemRows
        ? detailRows
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
              source: "mbop" as const,
            }))
            .sort((left, right) => compareStrings(left.asin, right.asin))
        : buildV2024BoxDetails(shipment, titleFallbacks);
      const unitsAvailable = hasTrackedItemRows
        ? toNumber(shipment.units_available) ?? computed.units_available
        : null;
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
        units_available: unitsAvailable,
        units_reserved: hasTrackedItemRows
          ? toNumber(shipment.units_reserved) ?? computed.units_reserved
          : null,
        units_unfulfillable: hasTrackedItemRows
          ? toNumber(shipment.units_unfulfillable) ?? computed.units_unfulfillable
          : null,
        units_missing: toNumber(shipment.units_missing) ?? computed.units_missing,
        fba_availability_pct:
          hasTrackedItemRows
            ? toNumber(shipment.fba_availability_pct) ??
              percent(computed.units_available, computed.units_sent)
            : null,
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
        detail_source: hasTrackedItemRows ? "mbop" : "amazon_v2024_box",
        fba_availability_tracked: hasTrackedItemRows,
        details,
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
      const quantity = toNumberFromUnknown(item.quantity) ?? 0;
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

function buildV2024BoxDetails(
  shipment: ShipmentRow,
  titleFallbacks = new Map<string, string>()
): ShipmentDetailApiRow[] {
  const boxes = getV2024Boxes(shipment.raw_tracking_json);
  const byKey = new Map<string, ShipmentDetailApiRow>();

  for (const box of boxes) {
    const items = Array.isArray(box.items) ? box.items : [];
    for (const item of items) {
      if (!isRecord(item)) continue;
      const asin = normalizeAsin(cleanString(item.asin));
      const sellerSku = cleanString(item.msku ?? item.sellerSku ?? item.seller_sku);
      const fnsku = cleanString(item.fnsku);
      const quantity = toNumberFromUnknown(item.quantity) ?? 0;
      if (!asin || quantity <= 0) continue;

      const key = `${asin}|${sellerSku ?? ""}|${fnsku ?? ""}`;
      const existing = byKey.get(key);
      if (existing) {
        existing.quantity_sent += quantity;
        existing.expected_quantity = (existing.expected_quantity ?? 0) + quantity;
        continue;
      }

      byKey.set(key, {
        id: `${shipment.fba_shipment_id}-${key}`,
        item_id: null,
        asin,
        amazon_title: titleFallbacks.get(asin) ?? null,
        system: null,
        seller_sku: sellerSku,
        fnsku,
        quantity_sent: quantity,
        expected_quantity: quantity,
        received_quantity: null,
        available_quantity: null,
        reserved_quantity: null,
        unfulfillable_quantity: null,
        missing_quantity: null,
        outbound_remaining_quantity: null,
        unit_cost: null,
        target_price: null,
        cost_sent: null,
        outbound_remaining_cost: null,
        amazon_received_cost: null,
        amazon_available_cost: null,
        source: "amazon_v2024_box",
      });
    }
  }

  return Array.from(byKey.values()).sort((left, right) =>
    compareStrings(left.asin, right.asin)
  );
}

function getV2024Boxes(rawTrackingJson: unknown): Array<Record<string, unknown>> {
  if (!isRecord(rawTrackingJson)) return [];
  const raw = rawTrackingJson.raw;
  if (!isRecord(raw)) return [];
  return Array.isArray(raw.boxes)
    ? raw.boxes.filter((box): box is Record<string, unknown> => isRecord(box))
    : [];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function cleanString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function toNumberFromUnknown(value: unknown): number | null {
  if (typeof value !== "number" && typeof value !== "string") return null;
  return toNumber(value);
}

export async function POST(request: Request) {
  const adminError = requireAdminApiToken(request);
  if (adminError) return adminError;

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

  for (let index = 0; index < asins.length; index += chunkSize) {
    const chunk = asins.slice(index, index + chunkSize);
    const { data, error } = await supabase
      .from("amazon_skus")
      .select("asin,product_name")
      .in("asin", chunk)
      .not("product_name", "is", null);

    if (error) {
      console.warn("FBA Amazon SKU title fallback lookup failed", error.message);
      continue;
    }

    for (const item of data ?? []) {
      const asin = normalizeAsin(item.asin);
      if (asin && item.product_name && !titleByAsin.has(asin)) {
        titleByAsin.set(asin, item.product_name);
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
  titleFallbacks: Map<string, string>,
  keepaPrices: Map<string, {
    buy_box_price_current: number | null;
    buy_box_price_avg90: number | null;
    low_fba_new_price_current: number | null;
    updated_at: string | null;
  }>,
  lastSoldPrices: Map<string, LastSoldRow>,
  feeEstimates: Map<string, {
    listing_price: number;
    total_fees_estimate: number | null;
    referral_fee_estimate: number | null;
    fba_fee_estimate: number | null;
    variable_closing_fee_estimate: number | null;
    adjusted_total_fees_estimate: number | null;
    referral_fee_rate: number | null;
    non_referral_fee_estimate: number | null;
    updated_at: string | null;
    estimate_status: string | null;
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
    last_sold_price: number | null;
    last_sold_at: string | null;
    current_buy_box_price: number | null;
    low_fba_new_price_current: number | null;
    buy_box_price_avg90: number | null;
    amazon_fee_estimate: number | null;
    amazon_fee_estimate_basis_price: number | null;
    referral_fee_estimate: number | null;
    non_referral_fee_estimate: number | null;
    referral_fee_rate: number | null;
    fee_estimate_status: string | null;
    fee_cache_updated_at: string | null;
    keepa_cache_updated_at: string | null;
    pricing_cache_updated_at: string | null;
    profit_per_unit: number | null;
    roi: number | null;
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
      last_sold_price: null,
      last_sold_at: null,
      current_buy_box_price: null,
      low_fba_new_price_current: null,
      buy_box_price_avg90: null,
      amazon_fee_estimate: null,
      amazon_fee_estimate_basis_price: null,
      referral_fee_estimate: null,
      non_referral_fee_estimate: null,
      referral_fee_rate: null,
      fee_estimate_status: null,
      fee_cache_updated_at: null,
      keepa_cache_updated_at: null,
      pricing_cache_updated_at: null,
      profit_per_unit: null,
      roi: null,
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
    const keepa = keepaPrices.get(group.asin);
    const lastSold = lastSoldPrices.get(group.asin);
    const feeEstimate =
      group.sell_price === null ? undefined : feeEstimates.get(group.asin);
    const costPerUnit =
      group.cost_quantity > 0 ? group.total_cost / group.cost_quantity : null;
    const profitPerUnit =
      group.sell_price !== null &&
      costPerUnit !== null &&
      feeEstimate?.adjusted_total_fees_estimate !== null &&
      feeEstimate?.adjusted_total_fees_estimate !== undefined
        ? group.sell_price -
          costPerUnit -
          feeEstimate.adjusted_total_fees_estimate
        : null;
    const pricingDates = [keepa?.updated_at ?? null, feeEstimate?.updated_at ?? null].filter(
      (value): value is string => Boolean(value)
    );

    return {
      ...group,
      cost_per_unit: costPerUnit,
      last_sold_price: lastSold?.price ?? null,
      last_sold_at: lastSold?.sold_at ?? null,
      current_buy_box_price: keepa?.buy_box_price_current ?? null,
      low_fba_new_price_current: keepa?.low_fba_new_price_current ?? null,
      buy_box_price_avg90: keepa?.buy_box_price_avg90 ?? null,
      amazon_fee_estimate: feeEstimate?.adjusted_total_fees_estimate ?? null,
      amazon_fee_estimate_basis_price: feeEstimate?.listing_price ?? null,
      referral_fee_estimate: feeEstimate?.referral_fee_estimate ?? null,
      non_referral_fee_estimate: feeEstimate?.non_referral_fee_estimate ?? null,
      referral_fee_rate: feeEstimate?.referral_fee_rate ?? null,
      fee_estimate_status: feeEstimate?.estimate_status ?? null,
      fee_cache_updated_at: feeEstimate?.updated_at ?? null,
      keepa_cache_updated_at: keepa?.updated_at ?? null,
      pricing_cache_updated_at: oldestDate(pricingDates),
      profit_per_unit: profitPerUnit,
      roi:
        profitPerUnit !== null && costPerUnit !== null && costPerUnit > 0
          ? profitPerUnit / costPerUnit
          : null,
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
      pricing_cache_oldest_at: oldestDate([
        sum.pricing_cache_oldest_at,
        row.pricing_cache_updated_at,
      ]),
    }),
    { units: 0, cost: 0, asins: 0, pricing_cache_oldest_at: null as string | null }
  );

  return { totals, rows: groupedRows };
}

async function fetchKeepaPrices(asins: string[]) {
  const prices = new Map<string, {
    buy_box_price_current: number | null;
    buy_box_price_avg90: number | null;
    low_fba_new_price_current: number | null;
    updated_at: string | null;
  }>();
  const chunkSize = 200;

  for (let index = 0; index < asins.length; index += chunkSize) {
    const chunk = asins.slice(index, index + chunkSize);
    const { data, error } = await supabase
      .from("vw_latest_keepa_product_snapshot")
      .select(
        "asin,captured_at,buy_box_price_current_cents,buy_box_price_avg90_cents,new_fba_price_current_cents"
      )
      .in("asin", chunk);

    if (error) {
      console.warn("FBA Keepa price lookup failed", error.message);
      continue;
    }

    for (const row of (data ?? []) as KeepaPriceRow[]) {
      const asin = normalizeAsin(row.asin);
      if (!asin) continue;
      prices.set(asin, {
        buy_box_price_current: centsToDollars(row.buy_box_price_current_cents),
        buy_box_price_avg90: centsToDollars(row.buy_box_price_avg90_cents),
        low_fba_new_price_current: centsToDollars(row.new_fba_price_current_cents),
        updated_at: row.captured_at,
      });
    }
  }

  return prices;
}

async function fetchFeeEstimates(
  candidates: Array<{ asin: string; sell_price: number | null }>
) {
  const sellPriceByAsin = new Map<string, number>();
  for (const candidate of candidates) {
    if (candidate.sell_price === null) continue;
    const current = sellPriceByAsin.get(candidate.asin);
    const sellPrice = Math.round(candidate.sell_price * 100) / 100;
    sellPriceByAsin.set(
      candidate.asin,
      current === undefined ? sellPrice : Math.max(current, sellPrice)
    );
  }

  const asins = Array.from(sellPriceByAsin.keys());
  const rowsByKey = new Map<string, {
    listing_price: number;
    total_fees_estimate: number | null;
    referral_fee_estimate: number | null;
    fba_fee_estimate: number | null;
    variable_closing_fee_estimate: number | null;
    adjusted_total_fees_estimate: number | null;
    referral_fee_rate: number | null;
    non_referral_fee_estimate: number | null;
    updated_at: string | null;
    estimate_status: string | null;
  }>();
  const chunkSize = 100;

  for (let index = 0; index < asins.length; index += chunkSize) {
    const chunk = asins.slice(index, index + chunkSize);
    const { data, error } = await supabase
      .from("amazon_fee_estimates")
      .select(
        "asin,listing_price,total_fees_estimate,referral_fee_estimate,fba_fee_estimate,variable_closing_fee_estimate,estimate_status,updated_at"
      )
      .in("asin", chunk)
      .eq("fulfillment_channel", "AFN")
      .order("updated_at", { ascending: false });

    if (error) {
      console.warn("FBA fee estimate lookup failed", error.message);
      continue;
    }

    for (const row of (data ?? []) as FeeEstimateRow[]) {
      const asin = normalizeAsin(row.asin);
      const listingPrice = toNumber(row.listing_price);
      if (!asin || listingPrice === null) continue;
      if (!sellPriceByAsin.has(asin)) continue;
      if (rowsByKey.has(asin)) continue;
      const totalFees = toNumber(row.total_fees_estimate);
      const referralFee = toNumber(row.referral_fee_estimate);
      const sellPrice = sellPriceByAsin.get(asin) ?? listingPrice;
      const referralRate =
        referralFee !== null && listingPrice > 0 ? referralFee / listingPrice : null;
      const nonReferralFees =
        totalFees !== null && referralFee !== null ? totalFees - referralFee : null;
      const adjustedReferralFee =
        referralRate !== null ? roundMoney(sellPrice * referralRate) : null;
      const adjustedTotalFees =
        nonReferralFees !== null && adjustedReferralFee !== null
          ? roundMoney(nonReferralFees + adjustedReferralFee)
          : totalFees;

      rowsByKey.set(asin, {
        listing_price: listingPrice,
        total_fees_estimate: totalFees,
        referral_fee_estimate: referralFee,
        fba_fee_estimate: toNumber(row.fba_fee_estimate),
        variable_closing_fee_estimate: toNumber(row.variable_closing_fee_estimate),
        adjusted_total_fees_estimate: adjustedTotalFees,
        referral_fee_rate: referralRate,
        non_referral_fee_estimate: nonReferralFees,
        updated_at: row.updated_at,
        estimate_status: row.estimate_status,
      });
    }
  }

  return rowsByKey;
}

async function fetchLastSoldPrices(asins: string[]) {
  const byAsin = new Map<string, LastSoldRow>();
  const chunkSize = 100;

  for (let index = 0; index < asins.length; index += chunkSize) {
    const chunk = asins.slice(index, index + chunkSize);
    const { data: profitRows, error: profitError } = await supabase
      .from("amazon_sales_profitability")
      .select("amazon_order_id,asin,quantity,sale_price,data_status")
      .in("asin", chunk)
      .eq("data_status", "complete")
      .not("sale_price", "is", null)
      .gt("quantity", 0)
      .limit(1000);

    if (profitError) {
      console.warn("FBA last sold profitability lookup failed", profitError.message);
      continue;
    }

    const rows = (profitRows ?? []) as Array<{
      amazon_order_id: string;
      asin: string | null;
      quantity: number | null;
      sale_price: number | null;
    }>;
    const orderIds = Array.from(new Set(rows.map((row) => row.amazon_order_id).filter(Boolean)));
    const purchaseDateByOrder = new Map<string, string | null>();

    for (let orderIndex = 0; orderIndex < orderIds.length; orderIndex += 200) {
      const orderChunk = orderIds.slice(orderIndex, orderIndex + 200);
      const { data: orderRows, error: orderError } = await supabase
        .from("amazon_sales_orders")
        .select("amazon_order_id,purchase_date")
        .in("amazon_order_id", orderChunk);

      if (orderError) {
        console.warn("FBA last sold order lookup failed", orderError.message);
        continue;
      }

      for (const order of orderRows ?? []) {
        purchaseDateByOrder.set(order.amazon_order_id, order.purchase_date ?? null);
      }
    }

    for (const row of rows) {
      const asin = normalizeAsin(row.asin);
      const salePrice = toNumber(row.sale_price);
      const quantity = toNumber(row.quantity) ?? 0;
      if (!asin || salePrice === null || quantity <= 0) continue;

      const soldAt = purchaseDateByOrder.get(row.amazon_order_id) ?? null;
      const existing = byAsin.get(asin);
      if (
        existing &&
        soldAt &&
        existing.sold_at &&
        new Date(existing.sold_at).getTime() >= new Date(soldAt).getTime()
      ) {
        continue;
      }

      byAsin.set(asin, {
        asin,
        price: Math.round((salePrice / quantity) * 100) / 100,
        sold_at: soldAt,
      });
    }
  }

  return byAsin;
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

function normalizePriceUpdateItems(items: unknown[]): PriceUpdateItem[] {
  return items.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const value = item as Record<string, unknown>;
    const itemId = typeof value.item_id === "string" ? value.item_id : "";
    const targetPrice = Number(value.target_price);

    if (!itemId || !Number.isFinite(targetPrice) || targetPrice < 0) {
      return [];
    }

    return [{ item_id: itemId, target_price: Math.round(targetPrice * 100) / 100 }];
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

function centsToDollars(value?: number | string | null) {
  const cents = toNumber(value);
  return cents === null ? null : Math.round(cents) / 100;
}

function roundMoney(value: number) {
  return Math.round(value * 100) / 100;
}

function oldestDate(values: Array<string | null | undefined>) {
  const timestamps = values
    .filter((value): value is string => Boolean(value))
    .sort((left, right) => Date.parse(left) - Date.parse(right));
  return timestamps[0] ?? null;
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
