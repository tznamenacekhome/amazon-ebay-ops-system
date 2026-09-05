import { NextRequest, NextResponse } from "next/server";
import { createServerSupabaseClient, requireAdminApiToken } from "../_server";
import { normalizeAsin as normalizeCatalogAsin, resolveAsinMetadata } from "../_asinMetadata";

const supabase = createServerSupabaseClient();

export const dynamic = "force-dynamic";

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
  new_price_current_cents: number | null;
  raw_keepa_json: unknown;
};

type AmazonSkuListingRow = {
  asin: string | null;
  seller_sku: string | null;
  fulfillment_channel: string | null;
  listing_status: string | null;
  item_status: string | null;
  listing_price: number | null;
  landed_price: number | null;
  total_quantity: number | null;
  fulfillable_quantity: number | null;
  inbound_working_quantity: number | null;
  inbound_shipped_quantity: number | null;
  inbound_receiving_quantity: number | null;
  reserved_quantity: number | null;
  unfulfillable_quantity: number | null;
  updated_at: string | null;
};

type KeepaSystemRow = {
  asin: string | null;
  title: string | null;
  category_tree_json: unknown;
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

type SkippedSaveItem = {
  item_id: string;
  reason: "already_saved" | "ebay_marketplace";
};

type ReturnRecoveryCaseRow = {
  amazon_return_recovery_case_id: string;
  workflow_state: string | null;
  decision: string | null;
  asin: string | null;
  seller_sku: string | null;
  sku: string | null;
  fnsku: string | null;
  title: string | null;
  quantity: number | null;
  amazon_order_id: string | null;
  lpn: string | null;
  return_date: string | null;
  raw_evidence_json: unknown;
};

type ReturnRecoverySalesProfitRow = {
  amazon_order_id: string;
  asin: string | null;
  seller_sku: string | null;
  title: string | null;
  quantity: number | null;
  sale_price: number | null;
  cogs: number | null;
};

type FbaPrepCandidate = {
  item_id: string;
  purchase_id: string | null;
  supplier_order_id: string | null;
  order_date: string | null;
  amazon_title: string | null;
  asin: string;
  seller_sku: string | null;
  fnsku: string | null;
  system: string | null;
  quantity: number;
  unit_cost: number | null;
  sell_price: number | null;
  supplier: string | null;
  source_type: "purchase_item" | "amazon_return_recovery";
  source_status: string | null;
};

type PriceUpdateItem = {
  item_id: string;
  asin?: string | null;
  target_price?: number | null;
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

type ShipmentSourceItemRow = {
  fba_shipment_source_item_id: string;
  fba_shipment_id: string;
  source_type: "amazon_return_recovery";
  source_row_id: string;
  amazon_return_recovery_case_id: string | null;
  quantity: number | null;
  asin: string | null;
  amazon_title: string | null;
  seller_sku: string | null;
  fnsku: string | null;
  observed_condition: string | null;
  unit_cost: number | null;
  target_price: number | null;
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

type ShipmentSummaryItem = {
  quantity: number | string | null;
  unit_cost: number | string | null;
  expected_quantity?: number | string | null;
  received_quantity?: number | string | null;
  available_quantity?: number | string | null;
  reserved_quantity?: number | string | null;
  unfulfillable_quantity?: number | string | null;
  missing_quantity?: number | string | null;
  outbound_remaining_quantity?: number | string | null;
  cost_sent?: number | string | null;
  outbound_remaining_cost?: number | string | null;
  amazon_received_cost?: number | string | null;
  amazon_available_cost?: number | string | null;
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
  source: "mbop" | "amazon_return_recovery" | "amazon_v2024_box";
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
    const [itemMeta, purchaseMeta, returnCandidates] = await Promise.all([
      fetchItemMeta(itemIds),
      fetchPurchaseMeta(purchaseIds),
      fetchReturnRecoveryFbaCandidates(),
    ]);

    const metaByItemId = new Map(itemMeta.map((item) => [item.item_id, item]));
    const supplierByPurchaseId = new Map(
      purchaseMeta.map((purchase) => [purchase.purchase_id, purchase.supplier])
    );

    const purchaseCandidates = rows.flatMap((row) => {
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
          seller_sku: null,
          fnsku: null,
          system: row.system,
          quantity,
          unit_cost: toNumber(row.unit_cost),
          sell_price: toNumber(row.sell_price ?? row.target_price),
          supplier: supplierByPurchaseId.get(row.purchase_id) ?? null,
          source_type: "purchase_item" as const,
          source_status: null,
        },
      ];
    });
    const candidates = [...purchaseCandidates, ...returnCandidates];

    const asins = Array.from(new Set(candidates.map((candidate) => candidate.asin)));
    const [
      titleFallbacks,
      systemFallbacks,
      preferredMskus,
      keepaPrices,
      myListings,
      lastSoldPrices,
      skuPrices,
    ] = await Promise.all([
      fetchAmazonTitleFallbacks(asins),
      fetchSystemFallbacks(asins),
      fetchPreferredFbaMskus(asins),
      fetchKeepaPrices(asins),
      fetchMyListings(asins),
      fetchLastSoldPrices(asins),
      fetchSkuPrices(asins),
    ]);
    const feeEstimates = await fetchFeeEstimates(candidates, myListings, skuPrices);
    const candidatesWithFallbacks = candidates.map((candidate) => ({
      ...candidate,
      system: candidate.system || systemFallbacks.get(candidate.asin) || null,
    }));

    return NextResponse.json(
      groupCandidates(
        candidatesWithFallbacks,
        titleFallbacks,
        preferredMskus,
        keepaPrices,
        myListings,
        skuPrices,
        lastSoldPrices,
        feeEstimates
      )
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
        { error: "At least one item update is required." },
        { status: 400 }
      );
    }

    for (const item of items) {
      const update: Record<string, unknown> = {};
      if (item.asin !== undefined) {
        const metadata = item.asin ? await resolveAsinMetadata(supabase, item.asin) : null;
        update.asin = item.asin;
        update.amazon_title = metadata?.amazonTitle ?? null;
        update.target_price =
          item.target_price !== undefined
            ? item.target_price
            : metadata?.targetPrice ?? null;
      } else if (item.target_price !== undefined) {
        update.target_price = item.target_price;
      }
      if (!Object.keys(update).length) continue;

      const { error } = await supabase
        .from("purchase_items")
        .update(update)
        .eq("item_id", item.item_id)
        .eq("current_status", "received");

      if (error) throw new Error(error.message);
    }

    return NextResponse.json({ success: true, updated: items.length });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Failed to update FBA item" },
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
    const sourceItemResult = await fetchShipmentSourceItems(shipmentIds);
    const allSourceItems = sourceItemResult.bridgeAvailable
      ? sourceItemResult.rows
      : await fetchRoutedReturnRecoverySourceItems(shipmentIds);
    const itemsByShipment = new Map<string, ShipmentItemRow[]>();
    for (const item of items) {
      const rows = itemsByShipment.get(item.fba_shipment_id) ?? [];
      rows.push(item);
      itemsByShipment.set(item.fba_shipment_id, rows);
    }
    const sourceItemsByShipment = new Map<string, ShipmentSourceItemRow[]>();
    for (const item of allSourceItems) {
      const rows = sourceItemsByShipment.get(item.fba_shipment_id) ?? [];
      rows.push(item);
      sourceItemsByShipment.set(item.fba_shipment_id, rows);
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
      const sourceDetailRows = sourceItemsByShipment.get(shipment.fba_shipment_id) ?? [];
      const hasStoredDetailRows = detailRows.length > 0 || sourceDetailRows.length > 0;
      const hasTrackedItemRows = detailRows.length > 0;
      const computed = summarizeShipmentFromItems([...detailRows, ...sourceDetailRows]);
      const details: ShipmentDetailApiRow[] = hasStoredDetailRows
        ? [
            ...detailRows.map((item) => ({
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
            })),
            ...sourceDetailRows.map((item) => ({
              id: item.fba_shipment_source_item_id,
              item_id: `amazon-return:${item.amazon_return_recovery_case_id ?? item.source_row_id}`,
              asin: item.asin,
              amazon_title: item.amazon_title,
              system: item.observed_condition ? `Condition: ${formatStatus(item.observed_condition)}` : null,
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
              source: "amazon_return_recovery" as const,
            })),
          ].sort((left, right) => compareStrings(left.asin, right.asin))
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
        detail_source: hasStoredDetailRows ? "mbop" : "amazon_v2024_box",
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

async function fetchShipmentSourceItems(shipmentIds: string[]) {
  const rows: ShipmentSourceItemRow[] = [];
  if (!shipmentIds.length) return { rows, bridgeAvailable: true };

  const chunkSize = 250;
  for (let index = 0; index < shipmentIds.length; index += chunkSize) {
    const chunk = shipmentIds.slice(index, index + chunkSize);
    const { data, error } = await supabase
      .from("fba_shipment_source_items")
      .select("*")
      .in("fba_shipment_id", chunk)
      .eq("included", true);

    if (error) {
      if (error.message.toLowerCase().includes("fba_shipment_source_items")) {
        console.warn("FBA source item bridge table is not available yet", error.message);
        return { rows, bridgeAvailable: false };
      }
      throw new Error(error.message);
    }
    rows.push(...((data ?? []) as ShipmentSourceItemRow[]));
  }
  return { rows, bridgeAvailable: true };
}

async function fetchRoutedReturnRecoverySourceItems(shipmentIds: string[]) {
  const shipmentIdSet = new Set(shipmentIds);
  if (!shipmentIdSet.size) return [] as ShipmentSourceItemRow[];

  const { data, error } = await supabase
    .from("amazon_return_recovery_cases")
    .select(
      "amazon_return_recovery_case_id,workflow_state,decision,asin,seller_sku,sku,fnsku,title," +
        "quantity,amazon_order_id,lpn,return_date,raw_evidence_json"
    )
    .eq("workflow_state", "closed")
    .eq("decision", "send_back_to_amazon")
    .limit(1000);

  if (error) {
    console.warn("FBA routed return recovery lookup failed", error.message);
    return [];
  }

  const cases = ((data ?? []) as unknown as ReturnRecoveryCaseRow[]).filter((row) => {
    const routing = fbaRoutingFromRaw(row.raw_evidence_json);
    return Boolean(routing.fba_shipment_id && shipmentIdSet.has(routing.fba_shipment_id));
  });
  const orderIds = Array.from(
    new Set(cases.map((row) => cleanString(row.amazon_order_id)).filter((value): value is string => Boolean(value)))
  );
  const profitRows = await fetchReturnRecoveryProfitRows(orderIds);

  return cases.flatMap((row): ShipmentSourceItemRow[] => {
    const routing = fbaRoutingFromRaw(row.raw_evidence_json);
    if (!routing.fba_shipment_id) return [];
    const asin = normalizeAsin(row.asin);
    if (!asin) return [];

    const quantity = toNumber(routing.quantity) ?? toNumber(row.quantity) ?? 1;
    const profit = findReturnProfitRow(row, profitRows);
    const cogs = toNumber(profit?.cogs);
    const profitQuantity = toNumber(profit?.quantity) ?? quantity;
    const unitCost = cogs === null ? null : perUnit(cogs, profitQuantity);
    const targetPrice =
      profit?.sale_price !== null && profit?.sale_price !== undefined
        ? perUnit(toNumber(profit.sale_price), profitQuantity)
        : null;
    const costSent = unitCost === null ? null : roundMoney(unitCost * quantity);

    return [
      {
        fba_shipment_source_item_id: `amazon-return-route:${row.amazon_return_recovery_case_id}`,
        fba_shipment_id: routing.fba_shipment_id,
        source_type: "amazon_return_recovery",
        source_row_id: row.amazon_return_recovery_case_id,
        amazon_return_recovery_case_id: row.amazon_return_recovery_case_id,
        quantity,
        asin,
        amazon_title: row.title ?? profit?.title ?? null,
        seller_sku: row.seller_sku ?? row.sku ?? null,
        fnsku: row.fnsku,
        observed_condition: cleanString(routing.observed_condition) ?? observedConditionFromRaw(row.raw_evidence_json),
        unit_cost: unitCost,
        target_price: targetPrice,
        expected_quantity: quantity,
        received_quantity: null,
        available_quantity: null,
        reserved_quantity: null,
        unfulfillable_quantity: null,
        missing_quantity: null,
        outbound_remaining_quantity: quantity,
        cost_sent: costSent,
        outbound_remaining_cost: costSent,
        amazon_received_cost: null,
        amazon_available_cost: null,
      },
    ];
  });
}

function summarizeShipmentFromItems(items: ShipmentSummaryItem[]) {
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
    const existingShipment = await fetchShipmentByCode(shipmentCode);
    const existingLinked = existingShipment
      ? await fetchExistingShipmentLinks(existingShipment.fba_shipment_id)
      : { purchaseItemIds: new Set<string>(), returnCaseIds: new Set<string>() };
    const {
      itemsToSave,
      skippedItems,
      returnCasesById,
    } = await prepareSaveItems(requestedItems, existingLinked);

    if (itemsToSave.length === 0) {
      if (existingShipment && skippedItems.some((item) => item.reason === "already_saved")) {
        return NextResponse.json({
          success: true,
          shipment: existingShipment,
          items: [],
          skipped_items: skippedItems,
        });
      }
      return NextResponse.json(
        { error: "At least one eligible unit must be included in the shipment", skipped_items: skippedItems },
        { status: 400 }
      );
    }

    const shipment = existingShipment ?? (await createFbaShipment(shipmentCode));

    const savedItems = [];

    for (const requestedItem of itemsToSave) {
      const returnCaseId = parseReturnRecoveryItemId(requestedItem.item_id);
      const savedItem = returnCaseId
        ? await listReturnRecoveryItem(
            shipment.fba_shipment_id,
            shipment.shipment_code,
            returnCasesById.get(returnCaseId),
            requestedItem.quantity_to_send
          )
        : await listPurchaseItem(
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
      skipped_items: skippedItems,
    });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Failed to save FBA shipment" },
      { status: 500 }
    );
  }
}

async function fetchShipmentByCode(shipmentCode: string) {
  const { data, error } = await supabase
    .from("fba_shipments")
    .select("fba_shipment_id,shipment_code")
    .eq("shipment_code", shipmentCode)
    .maybeSingle();

  if (error) throw new Error(error.message);
  return data as { fba_shipment_id: string; shipment_code: string } | null;
}

async function createFbaShipment(shipmentCode: string) {
  const { data, error } = await supabase
    .from("fba_shipments")
    .insert({
      shipment_code: shipmentCode,
      workflow_status: "finalized",
      finalized_at: new Date().toISOString(),
    })
    .select("fba_shipment_id,shipment_code")
    .single();

  if (error) {
    if (error.message.toLowerCase().includes("duplicate")) {
      const existing = await fetchShipmentByCode(shipmentCode);
      if (existing) return existing;
    }
    throw new Error(error.message);
  }
  return data as { fba_shipment_id: string; shipment_code: string };
}

async function fetchExistingShipmentLinks(fbaShipmentId: string) {
  const [itemsResponse, sourcesResponse] = await Promise.all([
    supabase
      .from("fba_shipment_items")
      .select("item_id")
      .eq("fba_shipment_id", fbaShipmentId)
      .eq("included", true),
    supabase
      .from("fba_shipment_source_items")
      .select("source_row_id")
      .eq("fba_shipment_id", fbaShipmentId)
      .eq("included", true),
  ]);

  if (itemsResponse.error) throw new Error(itemsResponse.error.message);
  if (
    sourcesResponse.error &&
    !isMissingBridgeTableError(sourcesResponse.error.message)
  ) {
    throw new Error(sourcesResponse.error.message);
  }

  return {
    purchaseItemIds: new Set(
      ((itemsResponse.data ?? []) as Array<{ item_id: string | null }>)
        .map((row) => row.item_id)
        .filter((value): value is string => Boolean(value))
    ),
    returnCaseIds: new Set(
      ((sourcesResponse.data ?? []) as Array<{ source_row_id: string | null }>)
        .map((row) => row.source_row_id)
        .filter((value): value is string => Boolean(value))
    ),
  };
}

async function prepareSaveItems(
  requestedItems: SaveItem[],
  existingLinked: { purchaseItemIds: Set<string>; returnCaseIds: Set<string> }
) {
  const skippedItems: SkippedSaveItem[] = [];
  const purchaseItems: SaveItem[] = [];
  const returnItems: SaveItem[] = [];

  for (const item of requestedItems) {
    const returnCaseId = parseReturnRecoveryItemId(item.item_id);
    if (returnCaseId) {
      if (existingLinked.returnCaseIds.has(returnCaseId)) {
        skippedItems.push({ item_id: item.item_id, reason: "already_saved" });
      } else {
        returnItems.push(item);
      }
      continue;
    }

    if (existingLinked.purchaseItemIds.has(item.item_id)) {
      skippedItems.push({ item_id: item.item_id, reason: "already_saved" });
    } else {
      purchaseItems.push(item);
    }
  }

  const filteredPurchaseItems = await filterEligiblePurchaseSaveItems(purchaseItems, skippedItems);
  const returnCasesById = await validateReturnRecoverySaveItems(returnItems);

  return {
    itemsToSave: [...filteredPurchaseItems, ...returnItems],
    skippedItems,
    returnCasesById,
  };
}

async function filterEligiblePurchaseSaveItems(
  requestedItems: SaveItem[],
  skippedItems: SkippedSaveItem[]
) {
  if (!requestedItems.length) return [];

  const itemIds = Array.from(new Set(requestedItems.map((item) => item.item_id)));
  const { data, error } = await supabase
    .from("purchase_items")
    .select("item_id,current_status,marketplace")
    .in("item_id", itemIds);

  if (error) throw new Error(error.message);

  const rowsByItemId = new Map(
    ((data ?? []) as Array<{
      item_id: string;
      current_status: string | null;
      marketplace: "Amazon" | "eBay" | null;
    }>).map((row) => [row.item_id, row])
  );

  return requestedItems.flatMap((item) => {
    const row = rowsByItemId.get(item.item_id);
    if (!row) throw new Error("Purchase item was not found for FBA shipment.");
    if (row.marketplace === "eBay") {
      skippedItems.push({ item_id: item.item_id, reason: "ebay_marketplace" });
      return [];
    }
    return [item];
  });
}

async function validateReturnRecoverySaveItems(requestedItems: SaveItem[]) {
  const returnItems = requestedItems
    .map((item) => ({
      ...item,
      returnCaseId: parseReturnRecoveryItemId(item.item_id),
    }))
    .filter((item): item is SaveItem & { returnCaseId: string } => Boolean(item.returnCaseId));

  const returnCasesById = new Map<string, ReturnRecoveryCaseRow>();
  if (!returnItems.length) return returnCasesById;

  const caseIds = Array.from(new Set(returnItems.map((item) => item.returnCaseId)));
  const { data, error } = await supabase
    .from("amazon_return_recovery_cases")
    .select(
      "amazon_return_recovery_case_id,workflow_state,decision,asin,seller_sku,sku,fnsku,title," +
        "quantity,amazon_order_id,lpn,return_date,raw_evidence_json"
    )
    .in("amazon_return_recovery_case_id", caseIds);

  if (error) throw new Error(`amazon_return_recovery_cases: ${error.message}`);

  for (const row of (data ?? []) as unknown as ReturnRecoveryCaseRow[]) {
    returnCasesById.set(row.amazon_return_recovery_case_id, row);
  }

  for (const item of returnItems) {
    const recoveryCase = returnCasesById.get(item.returnCaseId);
    if (!recoveryCase) {
      throw new Error("Amazon Return Recovery case was not found for FBA routing.");
    }

    if (
      recoveryCase.workflow_state !== "ready_to_send_back_to_amazon" ||
      recoveryCase.decision !== "send_back_to_amazon"
    ) {
      throw new Error("Only Return Recovery items marked Ready for Send to Amazon can be saved to an FBA shipment.");
    }

    const asin = normalizeAsin(recoveryCase.asin);
    if (!asin) {
      throw new Error("ASIN is required before routing an Amazon return to FBA.");
    }

    const observedCondition = observedConditionFromRaw(recoveryCase.raw_evidence_json);
    if (observedCondition !== "new") {
      throw new Error(
        `Amazon Return Recovery item ${asin} is blocked from Send to Amazon because observed condition is ${formatStatus(observedCondition)}. Only observed condition New can be routed to FBA in this workflow.`
      );
    }

    const caseQuantity = Math.max(1, toNumber(recoveryCase.quantity) ?? 1);
    if (item.quantity_to_send !== caseQuantity) {
      throw new Error("Partial Amazon Return Recovery FBA routing is not supported yet; send the full inspected quantity or leave it unselected.");
    }
  }

  return returnCasesById;
}

async function listReturnRecoveryItem(
  fbaShipmentId: string,
  shipmentCode: string,
  recoveryCase: ReturnRecoveryCaseRow | undefined,
  quantityToSend: number
) {
  if (!recoveryCase) {
    throw new Error("Amazon Return Recovery case was not loaded for FBA routing.");
  }

  const asin = normalizeAsin(recoveryCase.asin);
  const observedCondition = observedConditionFromRaw(recoveryCase.raw_evidence_json);
  const quantity = Math.max(1, toNumber(recoveryCase.quantity) ?? 1);
  if (!asin) throw new Error("ASIN is required before routing an Amazon return to FBA.");
  if (observedCondition !== "new") {
    throw new Error("Only Amazon returns with observed condition New can be routed to FBA.");
  }
  if (quantityToSend !== quantity) {
    throw new Error("Partial Amazon Return Recovery FBA routing is not supported yet.");
  }

  const amazonOrderId = cleanString(recoveryCase.amazon_order_id);
  const profitRows = await fetchReturnRecoveryProfitRows(amazonOrderId ? [amazonOrderId] : []);
  const profit = findReturnProfitRow(recoveryCase, profitRows);
  const cogs = toNumber(profit?.cogs);
  const profitQuantity = toNumber(profit?.quantity) ?? quantity;
  const unitCost = cogs === null ? null : perUnit(cogs, profitQuantity);
  const targetPrice =
    profit?.sale_price !== null && profit?.sale_price !== undefined
      ? perUnit(toNumber(profit.sale_price), profitQuantity)
      : null;
  const costSent = unitCost === null ? null : roundMoney(unitCost * quantityToSend);
  const now = new Date().toISOString();

  const sourceItemPayload = {
    fba_shipment_id: fbaShipmentId,
    source_type: "amazon_return_recovery",
    source_row_id: recoveryCase.amazon_return_recovery_case_id,
    amazon_return_recovery_case_id: recoveryCase.amazon_return_recovery_case_id,
    quantity: quantityToSend,
    asin,
    amazon_title: recoveryCase.title ?? profit?.title ?? null,
    seller_sku: recoveryCase.seller_sku ?? recoveryCase.sku ?? null,
    fnsku: recoveryCase.fnsku,
    observed_condition: observedCondition,
    workflow_state_at_save: recoveryCase.workflow_state,
    unit_cost: unitCost,
    target_price: targetPrice,
    included: true,
    expected_quantity: quantityToSend,
    outbound_remaining_quantity: quantityToSend,
    cost_sent: costSent,
    outbound_remaining_cost: costSent,
    raw_source_json: {
      amazon_return_recovery_case_id: recoveryCase.amazon_return_recovery_case_id,
      amazon_order_id: recoveryCase.amazon_order_id,
      lpn: recoveryCase.lpn,
      raw_evidence_json: recoveryCase.raw_evidence_json,
    },
  };

  const { data: shipmentItem, error: shipmentItemError } = await supabase
    .from("fba_shipment_source_items")
    .insert(sourceItemPayload)
    .select()
    .single();

  if (shipmentItemError && !isMissingBridgeTableError(shipmentItemError.message)) {
    throw new Error(shipmentItemError.message);
  }

  const rawEvidence = mergeRecord(recoveryCase.raw_evidence_json, {
    fba_routing: {
      status: "routed_to_fba_shipment",
      routed_at: now,
      fba_shipment_id: fbaShipmentId,
      shipment_code: shipmentCode,
      quantity: quantityToSend,
      asin,
      observed_condition: observedCondition,
    },
  });

  const { error: caseError } = await supabase
    .from("amazon_return_recovery_cases")
    .update({
      workflow_state: "closed",
      evidence_summary: `Routed to FBA shipment ${shipmentCode}; condition=${formatStatus(observedCondition)}.`,
      raw_evidence_json: rawEvidence,
      closed_at: now,
      updated_at: now,
    })
    .eq("amazon_return_recovery_case_id", recoveryCase.amazon_return_recovery_case_id);

  if (caseError) throw new Error(`amazon_return_recovery_cases update: ${caseError.message}`);

  const { error: eventError } = await supabase
    .from("amazon_return_recovery_events")
    .insert({
      amazon_return_recovery_case_id: recoveryCase.amazon_return_recovery_case_id,
      event_type: "routed_to_fba_shipment",
      event_source: "operator",
      message: `Routed to FBA shipment ${shipmentCode}.`,
      notes: null,
      raw_event_json: {
        fba_shipment_id: fbaShipmentId,
        shipment_code: shipmentCode,
        quantity: quantityToSend,
        asin,
        observed_condition: observedCondition,
      },
    });

  if (eventError) throw new Error(`amazon_return_recovery_events insert: ${eventError.message}`);

  return shipmentItem ?? sourceItemPayload;
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

async function fetchReturnRecoveryFbaCandidates(): Promise<FbaPrepCandidate[]> {
  const { data, error } = await supabase
    .from("amazon_return_recovery_cases")
    .select(
      "amazon_return_recovery_case_id,workflow_state,decision,asin,seller_sku,sku,fnsku,title," +
        "quantity,amazon_order_id,lpn,return_date,raw_evidence_json"
    )
    .eq("workflow_state", "ready_to_send_back_to_amazon")
    .eq("decision", "send_back_to_amazon")
    .limit(500);

  if (error) {
    console.warn("FBA Amazon return recovery lookup failed", error.message);
    return [];
  }

  const cases = (data ?? []) as unknown as ReturnRecoveryCaseRow[];
  const orderIds = Array.from(
    new Set(cases.map((row) => cleanString(row.amazon_order_id)).filter((value): value is string => Boolean(value)))
  );
  const profitRows = await fetchReturnRecoveryProfitRows(orderIds);

  return cases.flatMap((row) => {
    const asin = normalizeAsin(row.asin);
    if (!asin) return [];

    const quantity = toNumber(row.quantity) ?? 1;
    if (quantity <= 0) return [];
    const observedCondition = observedConditionFromRaw(row.raw_evidence_json);
    const sourceStatus =
      observedCondition === "new"
        ? "Ready for Send to Amazon"
        : `Blocked: observed condition ${formatStatus(observedCondition)}`;

    const profit = findReturnProfitRow(row, profitRows);
    const cogs = toNumber(profit?.cogs);
    const salePrice = profit?.sale_price !== null && profit?.sale_price !== undefined
      ? perUnit(toNumber(profit.sale_price), toNumber(profit.quantity) ?? quantity)
      : null;

    return [
      {
        item_id: `amazon-return:${row.amazon_return_recovery_case_id}`,
        purchase_id: null,
        supplier_order_id: row.amazon_order_id ?? row.lpn ?? null,
        order_date: row.return_date,
        amazon_title: row.title ?? profit?.title ?? null,
        asin,
        seller_sku: cleanString(row.seller_sku ?? row.sku),
        fnsku: cleanString(row.fnsku),
        system: null,
        quantity,
        unit_cost: cogs === null ? null : perUnit(cogs, toNumber(profit?.quantity) ?? quantity),
        sell_price: salePrice,
        supplier: "Amazon Return Recovery",
        source_type: "amazon_return_recovery" as const,
        source_status: sourceStatus,
      },
    ];
  });
}

async function fetchReturnRecoveryProfitRows(orderIds: string[]) {
  const rows: ReturnRecoverySalesProfitRow[] = [];
  for (let index = 0; index < orderIds.length; index += 100) {
    const chunk = orderIds.slice(index, index + 100);
    const { data, error } = await supabase
      .from("amazon_sales_profitability")
      .select("amazon_order_id,asin,seller_sku,title,quantity,sale_price,cogs")
      .in("amazon_order_id", chunk);
    if (error) {
      console.warn("FBA return recovery profitability lookup failed", error.message);
      continue;
    }
    rows.push(...((data ?? []) as unknown as ReturnRecoverySalesProfitRow[]));
  }
  return rows;
}

function findReturnProfitRow(
  row: ReturnRecoveryCaseRow,
  profitRows: ReturnRecoverySalesProfitRow[]
) {
  const orderId = cleanString(row.amazon_order_id);
  if (!orderId) return null;
  const asin = normalizeAsin(row.asin);
  const sellerSku = normalizeAsin(row.seller_sku ?? row.sku);
  const matches = profitRows.filter((profit) => profit.amazon_order_id === orderId);
  return matches.find((profit) => {
    const profitAsin = normalizeAsin(profit.asin);
    const profitSku = normalizeAsin(profit.seller_sku);
    return (asin && profitAsin === asin) || (sellerSku && profitSku === sellerSku);
  }) ?? (matches.length === 1 ? matches[0] : null);
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

async function fetchSystemFallbacks(asins: string[]) {
  const systemByAsin = new Map<string, string>();
  const chunkSize = 500;

  const setSystem = (asinValue: string | null | undefined, systemValue?: string | null) => {
    const asin = normalizeAsin(asinValue);
    const system = normalizeSystem(systemValue);
    if (asin && system && !systemByAsin.has(asin)) {
      systemByAsin.set(asin, system);
    }
  };

  for (let index = 0; index < asins.length; index += chunkSize) {
    const chunk = asins.slice(index, index + chunkSize);
    const { data, error } = await supabase
      .from("purchase_items")
      .select("asin,system")
      .in("asin", chunk)
      .not("system", "is", null);

    if (error) {
      console.warn("FBA system purchase fallback lookup failed", error.message);
      continue;
    }

    for (const item of data ?? []) {
      setSystem(item.asin, item.system);
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
      console.warn("FBA system Amazon SKU fallback lookup failed", error.message);
      continue;
    }

    for (const item of data ?? []) {
      setSystem(item.asin, item.product_name);
    }
  }

  for (let index = 0; index < asins.length; index += chunkSize) {
    const chunk = asins.slice(index, index + chunkSize);
    const { data, error } = await supabase
      .from("vw_latest_keepa_product_snapshot")
      .select("asin,title,category_tree_json")
      .in("asin", chunk);

    if (error) {
      console.warn("FBA system Keepa fallback lookup failed", error.message);
      continue;
    }

    for (const row of (data ?? []) as KeepaSystemRow[]) {
      const categoryNames = Array.isArray(row.category_tree_json)
        ? row.category_tree_json
            .map((category) =>
              category && typeof category === "object" && "name" in category
                ? String((category as { name?: unknown }).name ?? "")
                : ""
            )
            .filter(Boolean)
            .join(" ")
        : "";
      setSystem(row.asin, [row.title, categoryNames].filter(Boolean).join(" "));
    }
  }

  return systemByAsin;
}

async function fetchPreferredFbaMskus(asins: string[]) {
  const mskuByAsin = new Map<string, string>();
  const chunkSize = 500;

  for (let index = 0; index < asins.length; index += chunkSize) {
    const chunk = asins.slice(index, index + chunkSize);
    const { data, error } = await supabase
      .from("amazon_skus")
      .select(
        "asin,seller_sku,last_listing_sync_at,last_pricing_sync_at,updated_at,created_at"
      )
      .in("asin", chunk)
      .in("fulfillment_channel", ["Amazon", "AMAZON_NA"])
      .not("seller_sku", "is", null)
      .order("last_listing_sync_at", { ascending: false, nullsFirst: false })
      .order("last_pricing_sync_at", { ascending: false, nullsFirst: false })
      .order("updated_at", { ascending: false, nullsFirst: false })
      .order("created_at", { ascending: false, nullsFirst: false });

    if (error) {
      console.warn("FBA preferred MSKU lookup failed", error.message);
      continue;
    }

    for (const item of data ?? []) {
      const asin = normalizeAsin(item.asin);
      const sellerSku = cleanString(item.seller_sku);
      if (asin && sellerSku && !mskuByAsin.has(asin)) {
        mskuByAsin.set(asin, sellerSku);
      }
    }
  }

  return mskuByAsin;
}

function groupCandidates(
  candidates: FbaPrepCandidate[],
  titleFallbacks: Map<string, string>,
  preferredMskus: Map<string, string>,
  keepaPrices: Map<string, {
    buy_box_price_current: number | null;
    buy_box_price_avg90: number | null;
    buy_box_is_fba: boolean | null;
    buy_box_is_used: boolean | null;
    new_price_avg90: number | null;
    low_fba_new_price_current: number | null;
    new_price_current: number | null;
    low_fbm_new_price_current: number | null;
    used_price_current: number | null;
    updated_at: string | null;
  }>,
  myListings: Map<string, {
    price: number | null;
    quantity: number;
    fulfillment_channel: "fba" | "mf" | null;
    updated_at: string | null;
  }>,
  skuPrices: Map<string, number>,
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
    msku: string | null;
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
    current_price: number | null;
    current_price_source: "buy_box" | "fba" | "mf" | "used_only" | "no_data" | null;
    current_price_fulfillment: "fba" | "mf" | null;
    current_price_is_buy_box: boolean;
    low_fba_new_price_current: number | null;
    new_price_current: number | null;
    my_price: number | null;
    my_quantity: number;
    my_price_fulfillment: "fba" | "mf" | null;
    my_price_is_buy_box: boolean;
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
      msku: preferredMskus.get(candidate.asin) ?? candidate.seller_sku ?? null,
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
      current_price: null,
      current_price_source: null,
      current_price_fulfillment: null,
      current_price_is_buy_box: false,
      low_fba_new_price_current: null,
      new_price_current: null,
      my_price: null,
      my_quantity: 0,
      my_price_fulfillment: null,
      my_price_is_buy_box: false,
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
    group.msku = group.msku ?? candidate.seller_sku;
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
    const myListing = myListings.get(group.asin);
    const currentPrice = currentPriceContext(keepa);
    const lastSold = lastSoldPrices.get(group.asin);
    const hasReturnRecoveryDetail = group.details.some((detail) => detail.source_type === "amazon_return_recovery");
    const effectiveSellPrice = group.sell_price ?? (hasReturnRecoveryDetail ? myListing?.price ?? skuPrices.get(group.asin) ?? null : null);
    const feeEstimate =
      effectiveSellPrice === null ? undefined : feeEstimates.get(group.asin);
    const costPerUnit =
      group.cost_quantity > 0 ? group.total_cost / group.cost_quantity : null;
    const profitPerUnit =
      effectiveSellPrice !== null &&
      costPerUnit !== null &&
      feeEstimate?.adjusted_total_fees_estimate !== null &&
      feeEstimate?.adjusted_total_fees_estimate !== undefined
        ? effectiveSellPrice -
          costPerUnit -
          feeEstimate.adjusted_total_fees_estimate
        : null;
    const pricingDates = [keepa?.updated_at ?? null, feeEstimate?.updated_at ?? null].filter(
      (value): value is string => Boolean(value)
    );

    return {
      ...group,
      cost_per_unit: costPerUnit,
      sell_price: effectiveSellPrice,
      last_sold_price: lastSold?.price ?? null,
      last_sold_at: lastSold?.sold_at ?? null,
      current_buy_box_price: keepa?.buy_box_price_current ?? null,
      current_price: currentPrice.price,
      current_price_source: currentPrice.source,
      current_price_fulfillment: currentPrice.fulfillment,
      current_price_is_buy_box: currentPrice.is_buy_box,
      low_fba_new_price_current: keepa?.low_fba_new_price_current ?? null,
      new_price_current: keepa?.new_price_current ?? null,
      my_price: myListing?.price ?? null,
      my_quantity: myListing?.quantity ?? 0,
      my_price_fulfillment: myListing?.fulfillment_channel ?? null,
      my_price_is_buy_box:
        myListing?.price !== null &&
        myListing?.price !== undefined &&
        keepa?.buy_box_price_current !== null &&
        keepa?.buy_box_price_current !== undefined &&
        Math.abs(myListing.price - keepa.buy_box_price_current) < 0.01,
      buy_box_price_avg90: keepa?.buy_box_price_avg90 ?? keepa?.new_price_avg90 ?? null,
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
    buy_box_is_fba: boolean | null;
    buy_box_is_used: boolean | null;
    new_price_avg90: number | null;
    low_fba_new_price_current: number | null;
    new_price_current: number | null;
    low_fbm_new_price_current: number | null;
    used_price_current: number | null;
    updated_at: string | null;
  }>();
  const chunkSize = 200;

  for (let index = 0; index < asins.length; index += chunkSize) {
    const chunk = asins.slice(index, index + chunkSize);
    const { data, error } = await supabase
      .from("keepa_product_snapshots")
      .select(
        "asin,captured_at,buy_box_price_current_cents,buy_box_price_avg90_cents,new_fba_price_current_cents,new_price_current_cents,raw_keepa_json"
      )
      .in("asin", chunk)
      .order("captured_at", { ascending: false })
      .limit(1000);

    if (error) {
      console.warn("FBA Keepa price lookup failed", error.message);
      continue;
    }

    const latestByAsin = new Map<string, KeepaPriceRow>();
    const latestOfferByAsin = new Map<string, KeepaPriceRow>();
    for (const row of (data ?? []) as KeepaPriceRow[]) {
      const asin = normalizeAsin(row.asin);
      if (!asin) continue;
      if (!latestByAsin.has(asin)) latestByAsin.set(asin, row);
      if (!latestOfferByAsin.has(asin) && hasKeepaOfferData(row.raw_keepa_json)) {
        latestOfferByAsin.set(asin, row);
      }
    }

    for (const asin of chunk) {
      const row = latestOfferByAsin.get(asin) ?? latestByAsin.get(asin);
      if (!row) continue;
      prices.set(asin, {
        buy_box_price_current: centsToDollars(row.buy_box_price_current_cents),
        buy_box_price_avg90: centsToDollars(row.buy_box_price_avg90_cents),
        buy_box_is_fba: keepaBoolean(row.raw_keepa_json, "buyBoxIsFBA"),
        buy_box_is_used: keepaBoolean(row.raw_keepa_json, "buyBoxIsUsed"),
        new_price_avg90: keepaStatsCentsToDollars(row.raw_keepa_json, "avg90", 1),
        low_fba_new_price_current: centsToDollars(row.new_fba_price_current_cents),
        new_price_current: centsToDollars(row.new_price_current_cents),
        low_fbm_new_price_current: keepaStatsCentsToDollars(row.raw_keepa_json, "current", 7),
        used_price_current: keepaStatsCentsToDollars(row.raw_keepa_json, "current", 2),
        updated_at: row.captured_at,
      });
    }
  }

  return prices;
}

async function fetchMyListings(asins: string[]) {
  const inventoryQuantityByAsin = await fetchLatestFbaInventoryQuantityByAsin(asins);
  const listings = new Map<string, {
    price: number | null;
    quantity: number;
    fulfillment_channel: "fba" | "mf" | null;
    updated_at: string | null;
  }>();
  const chunkSize = 200;

  for (let index = 0; index < asins.length; index += chunkSize) {
    const chunk = asins.slice(index, index + chunkSize);
    const { data, error } = await supabase
      .from("amazon_skus")
      .select(
        [
          "asin",
          "seller_sku",
          "fulfillment_channel",
          "listing_status",
          "item_status",
          "listing_price",
          "landed_price",
          "updated_at",
        ].join(",")
      )
      .in("asin", chunk);

    if (error) {
      console.warn("FBA my listing lookup failed", error.message);
      continue;
    }

    for (const row of (data ?? []) as unknown as AmazonSkuListingRow[]) {
      const asin = normalizeAsin(row.asin);
      if (!asin || isInactiveListing(row)) continue;

      const quantity = inventoryQuantityByAsin.get(asin) ?? listingQuantity(row);
      const price = toNumber(row.landed_price) ?? toNumber(row.listing_price);
      if (quantity <= 0 && price === null) continue;
      const fulfillment = fulfillmentKind(row.fulfillment_channel);
      const existing = listings.get(asin);

      if (!existing) {
        listings.set(asin, {
          price,
          quantity,
          fulfillment_channel: fulfillment,
          updated_at: row.updated_at,
        });
        continue;
      }

      existing.quantity = Math.max(existing.quantity, quantity);
      if (
        price !== null &&
        (existing.price === null ||
          price < existing.price ||
          (Math.abs(price - existing.price) < 0.01 &&
            existing.fulfillment_channel !== "fba" &&
            fulfillment === "fba"))
      ) {
        existing.price = price;
        existing.fulfillment_channel = fulfillment;
        existing.updated_at = row.updated_at ?? existing.updated_at;
      }
    }
  }

  return listings;
}

async function fetchSkuPrices(asins: string[]) {
  const prices = new Map<string, number>();
  const chunkSize = 200;

  for (let index = 0; index < asins.length; index += chunkSize) {
    const chunk = asins.slice(index, index + chunkSize);
    const { data, error } = await supabase
      .from("amazon_skus")
      .select("asin,listing_price,landed_price,updated_at")
      .in("asin", chunk);

    if (error) {
      console.warn("FBA SKU price fallback lookup failed", error.message);
      continue;
    }

    for (const row of (data ?? []) as unknown as Array<{
      asin: string | null;
      listing_price: number | string | null;
      landed_price: number | string | null;
    }>) {
      const asin = normalizeAsin(row.asin);
      if (!asin) continue;
      const price = toNumber(row.landed_price) ?? toNumber(row.listing_price);
      if (price === null) continue;
      const current = prices.get(asin);
      prices.set(asin, current === undefined ? price : Math.min(current, price));
    }
  }

  return prices;
}

async function fetchLatestFbaInventoryQuantityByAsin(asins: string[]) {
  const quantityByAsin = new Map<string, number>();
  const latest = await supabase
    .from("amazon_fba_inventory_snapshots")
    .select("captured_at")
    .order("captured_at", { ascending: false })
    .limit(1);

  if (latest.error) {
    console.warn("FBA inventory quantity lookup failed", latest.error.message);
    return quantityByAsin;
  }

  const capturedAt = latest.data?.[0]?.captured_at;
  if (!capturedAt) return quantityByAsin;

  const chunkSize = 200;
  for (let index = 0; index < asins.length; index += chunkSize) {
    const chunk = asins.slice(index, index + chunkSize);
    const { data, error } = await supabase
      .from("amazon_fba_inventory_snapshots")
      .select(
        [
          "asin",
          "total_quantity",
          "fulfillable_quantity",
          "inbound_working_quantity",
          "inbound_shipped_quantity",
          "inbound_receiving_quantity",
          "reserved_quantity",
          "unfulfillable_quantity",
        ].join(",")
      )
      .eq("captured_at", capturedAt)
      .in("asin", chunk);

    if (error) {
      console.warn("FBA inventory quantity lookup failed", error.message);
      continue;
    }

    for (const row of (data ?? []) as unknown as Array<{
      asin: string | null;
      total_quantity: number | string | null;
      fulfillable_quantity: number | string | null;
      inbound_working_quantity: number | string | null;
      inbound_shipped_quantity: number | string | null;
      inbound_receiving_quantity: number | string | null;
      reserved_quantity: number | string | null;
      unfulfillable_quantity: number | string | null;
    }>) {
      const asin = normalizeAsin(row.asin);
      if (!asin) continue;
      quantityByAsin.set(asin, (quantityByAsin.get(asin) ?? 0) + inventoryQuantity(row));
    }
  }

  return quantityByAsin;
}

function currentPriceContext(
  keepa:
    | {
        buy_box_price_current: number | null;
        buy_box_is_fba: boolean | null;
        buy_box_is_used: boolean | null;
        low_fba_new_price_current: number | null;
        low_fbm_new_price_current: number | null;
        used_price_current: number | null;
      }
    | undefined
) {
  if (!keepa) {
    return {
      price: null,
      source: "no_data" as const,
      fulfillment: null,
      is_buy_box: false,
    };
  }

  const buyBox = keepa?.buy_box_is_used === true ? null : keepa?.buy_box_price_current ?? null;
  const fba = keepa?.low_fba_new_price_current ?? null;
  const mf = keepa?.low_fbm_new_price_current ?? null;

  if (buyBox !== null) {
    const buyBoxFulfillment =
      keepa?.buy_box_is_fba === true
        ? ("fba" as const)
        : keepa?.buy_box_is_fba === false
          ? ("mf" as const)
          : null;

    return {
      price: buyBox,
      source: "buy_box" as const,
      fulfillment: buyBoxFulfillment,
      is_buy_box: true,
    };
  }

  if (fba !== null) {
    return {
      price: fba,
      source: "fba" as const,
      fulfillment: "fba" as const,
      is_buy_box: false,
    };
  }

  if (mf !== null) {
    return {
      price: mf,
      source: "mf" as const,
      fulfillment: "mf" as const,
      is_buy_box: false,
    };
  }

  return {
    price: null,
    source:
      keepa.used_price_current !== null || keepa.buy_box_is_used === true
        ? ("used_only" as const)
        : ("no_data" as const),
    fulfillment: null,
    is_buy_box: false,
  };
}

function listingQuantity(row: AmazonSkuListingRow) {
  const fulfillable = toNumber(row.fulfillable_quantity);
  if (fulfillable !== null) return Math.max(0, Math.floor(fulfillable));
  const total = toNumber(row.total_quantity);
  return total === null ? 0 : Math.max(0, Math.floor(total));
}

function inventoryQuantity(row: {
  total_quantity?: number | string | null;
  fulfillable_quantity?: number | string | null;
  inbound_working_quantity?: number | string | null;
  inbound_shipped_quantity?: number | string | null;
  inbound_receiving_quantity?: number | string | null;
  reserved_quantity?: number | string | null;
  unfulfillable_quantity?: number | string | null;
}): number {
  const total = toNumber(row.total_quantity);
  if (total !== null) return Math.max(0, Math.floor(total));

  return [
    row.fulfillable_quantity,
    row.inbound_working_quantity,
    row.inbound_shipped_quantity,
    row.inbound_receiving_quantity,
    row.reserved_quantity,
    row.unfulfillable_quantity,
  ].reduce<number>((sum, value) => sum + Math.max(0, Math.floor(toNumber(value) ?? 0)), 0);
}

function hasKeepaOfferData(rawKeepa: unknown) {
  if (!rawKeepa || typeof rawKeepa !== "object") return false;
  const product = rawKeepa as { offers?: unknown; offersSuccessful?: unknown };
  if (Array.isArray(product.offers) && product.offers.length > 0) return true;
  if (product.offersSuccessful === true) return true;
  const stats = keepaStats(rawKeepa);
  const retrievedOfferCount = stats?.retrievedOfferCount;
  return typeof retrievedOfferCount === "number" && retrievedOfferCount >= 0;
}

function keepaBoolean(rawKeepa: unknown, key: string) {
  const stats = keepaStats(rawKeepa);
  const rawValue = stats?.[key];
  const value = Array.isArray(rawValue) ? lastValue(rawValue) : rawValue;
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value === 1;
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    if (["true", "1", "yes"].includes(normalized)) return true;
    if (["false", "0", "no"].includes(normalized)) return false;
  }
  return null;
}

function keepaStatsCentsToDollars(rawKeepa: unknown, statsKey: string, index: number) {
  const stats = keepaStats(rawKeepa);
  const values = stats?.[statsKey];
  if (!Array.isArray(values) || index >= values.length) return null;
  return centsToDollars(values[index]);
}

function keepaStats(rawKeepa: unknown): Record<string, unknown> | null {
  if (!rawKeepa || typeof rawKeepa !== "object" || !("stats" in rawKeepa)) return null;
  const stats = (rawKeepa as { stats?: unknown }).stats;
  return stats && typeof stats === "object" ? (stats as Record<string, unknown>) : null;
}

function lastValue(values: unknown[] | undefined) {
  if (!Array.isArray(values) || values.length === 0) return null;
  return values[values.length - 1];
}

function fulfillmentKind(value: string | null) {
  const normalized = cleanString(value)?.toLowerCase() ?? "";
  if (["amazon", "amazon_na", "afn", "fba"].includes(normalized)) return "fba" as const;
  if (["merchant", "merchant_na", "mfn", "mf"].includes(normalized)) return "mf" as const;
  return null;
}

function isInactiveListing(row: AmazonSkuListingRow) {
  const status = [row.listing_status, row.item_status]
    .map((value) => cleanString(value)?.toLowerCase() ?? "")
    .filter(Boolean);
  return status.some((value) =>
    ["inactive", "deleted", "closed", "suppressed", "incomplete"].includes(value)
  );
}

async function fetchFeeEstimates(
  candidates: Array<{ asin: string; sell_price: number | null; source_type?: string | null }>,
  myListings?: Map<string, { price: number | null }>,
  skuPrices?: Map<string, number>
) {
  const sellPriceByAsin = new Map<string, number>();
  for (const candidate of candidates) {
    const fallbackPrice =
      candidate.source_type === "amazon_return_recovery"
        ? myListings?.get(candidate.asin)?.price ?? skuPrices?.get(candidate.asin) ?? null
        : null;
    const candidatePrice = candidate.sell_price ?? fallbackPrice;
    if (candidatePrice === null) continue;
    const current = sellPriceByAsin.get(candidate.asin);
    const sellPrice = Math.round(candidatePrice * 100) / 100;
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

function parseReturnRecoveryItemId(itemId: string) {
  const prefix = "amazon-return:";
  return itemId.startsWith(prefix) ? itemId.slice(prefix.length).trim() : null;
}

function normalizePriceUpdateItems(items: unknown[]): PriceUpdateItem[] {
  return items.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const value = item as Record<string, unknown>;
    const itemId = typeof value.item_id === "string" ? value.item_id : "";
    const hasTargetPrice = "target_price" in value;
    const hasAsin = "asin" in value;
    const targetPrice =
      value.target_price === null || value.target_price === undefined || value.target_price === ""
        ? null
        : Number(value.target_price);
    const asin = hasAsin ? normalizeCatalogAsin(value.asin) : undefined;

    if (!itemId || (!hasTargetPrice && !hasAsin)) {
      return [];
    }
    if (hasTargetPrice && targetPrice !== null && (!Number.isFinite(targetPrice) || targetPrice < 0)) {
      return [];
    }
    if (hasAsin && !asin) return [];

    return [{
      item_id: itemId,
      asin,
      target_price:
        hasTargetPrice && targetPrice !== null
          ? Math.round(targetPrice * 100) / 100
          : hasTargetPrice
            ? null
            : undefined,
    }];
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

const SYSTEM_ALIASES: Record<string, string[]> = {
  "Switch 2": ["nintendo switch 2", "switch 2"],
  Switch: ["nintendo switch", "switch"],
  "3DS": ["nintendo 3ds", "3ds"],
  DS: ["nintendo ds", "ds"],
  "Wii U": ["nintendo wii u", "wii u", "wiiu"],
  Wii: ["nintendo wii", "wii"],
  Gamecube: ["gamecube", "game cube", "nintendo gamecube"],
  "Nintendo 64": ["nintendo 64", "n64"],
  "Super Nintendo": ["super nintendo", "snes"],
  NES: ["nes", "nintendo entertainment system"],
  "PS 5": ["playstation 5", "ps5", "ps 5"],
  "PS 4": ["playstation 4", "ps4", "ps 4"],
  "PS 3": ["playstation 3", "ps3", "ps 3"],
  "PS 2": ["playstation 2", "ps2", "ps 2"],
  PS: ["playstation", "ps1", "psx"],
  PSP: ["psp", "playstation portable"],
  "PS Vita": ["playstation vita", "ps vita", "vita"],
  "Xbox Series X": ["xbox series x", "series x"],
  "Xbox Series S": ["xbox series s", "series s"],
  "Xbox One": ["xbox one", "xbone", "xb1"],
  "Xbox 360": ["xbox 360", "360"],
  Xbox: ["original xbox", "xbox"],
  PC: ["pc", "windows pc", "windows", "mac"],
};

function normalizeSystem(value?: string | null) {
  if (!value) return null;
  const text = normalizeAlias(value);

  for (const [canonical, aliases] of Object.entries(SYSTEM_ALIASES)) {
    if (aliases.some((alias) => text === normalizeAlias(alias))) {
      return canonical;
    }
  }

  for (const [canonical, aliases] of Object.entries(SYSTEM_ALIASES)) {
    if (
      aliases.some((alias) =>
        new RegExp(`\\b${escapeRegExp(normalizeAlias(alias))}\\b`).test(text)
      )
    ) {
      return canonical;
    }
  }

  return null;
}

function normalizeAlias(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, " ").replace(/\s+/g, " ").trim();
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function observedConditionFromRaw(value: unknown) {
  const raw = isRecord(value) ? value : {};
  const inspection = isRecord(raw.inspection) ? raw.inspection : {};
  const condition = cleanString(inspection.observed_condition)
    ?.toLowerCase()
    .replace(/[\s-]+/g, "_");
  return condition || "not_recorded";
}

function fbaRoutingFromRaw(value: unknown) {
  const raw = isRecord(value) ? value : {};
  const routing = isRecord(raw.fba_routing) ? raw.fba_routing : {};
  return {
    fba_shipment_id: cleanString(routing.fba_shipment_id),
    quantity: toNumberFromUnknown(routing.quantity),
    observed_condition: cleanString(routing.observed_condition),
  };
}

function mergeRecord(existing: unknown, patch: Record<string, unknown>) {
  const base = isRecord(existing) ? existing : {};
  return { ...base, ...patch };
}

function isMissingBridgeTableError(message: string) {
  const normalized = message.toLowerCase();
  return (
    normalized.includes("fba_shipment_source_items") &&
    (normalized.includes("could not find") ||
      normalized.includes("does not exist") ||
      normalized.includes("schema cache"))
  );
}

function formatStatus(value?: string | null) {
  return (value || "not_recorded")
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function toNumber(value?: number | string | null) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function centsToDollars(value?: number | string | null) {
  const cents = toNumber(value);
  return cents === null || cents <= 0 ? null : Math.round(cents) / 100;
}

function roundMoney(value: number) {
  return Math.round(value * 100) / 100;
}

function perUnit(value: number | null, quantity: number | null) {
  if (value === null || quantity === null || quantity <= 0) return value;
  return roundMoney(value / quantity);
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
