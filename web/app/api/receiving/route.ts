import { NextResponse } from "next/server";
import { spawn } from "child_process";
import path from "path";
import { createServerSupabaseClient, isCloudDeployment, isLocalJobExecutionEnabled, requireAdminApiToken } from "../_server";
import { runSchedulerGroupTask } from "../_awsScheduler";

const supabase = createServerSupabaseClient();
const RECEIVING_CONFIRMATION_TOKEN = "operator_receive_v2";
const ROOT_DIR = path.resolve(process.cwd(), "..");

type ReceivingUpdate = {
  item_id: string;
  package_link_id?: string | null;
  quantity_received: number;
  return_pending: boolean;
  marketplace: "Amazon" | "eBay" | null;
  asin?: string | null;
  sell_price?: number | null;
  receiving_outcome?: string | null;
  condition_issue?: string | null;
  image_clues?: string[] | null;
  receiving_notes?: string | null;
};

export async function GET() {
  const excludedItemIds = await fetchExcludedItemIds();
  let request = supabase
    .from("vw_purchases_dashboard")
    .select("*")
    .in("current_status", ["delivered", "partially_delivered", "shipped_no_tracking"])
    .order("order_date", { ascending: false });

  if (excludedItemIds.length > 0) {
    request = request.not("item_id", "in", `(${excludedItemIds.join(",")})`);
  }

  const { data, error } = await request.limit(1000);

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  const dashboardRows = (data ?? []).map((row) => ({
    ...row,
    ebay_title: row.title,
  }));
  const packageRows = await fetchReceivingPackageRows(excludedItemIds);
  const packageItemIds = new Set(packageRows.map((row) => row.item_id).filter(Boolean));
  const rows = [
    ...dashboardRows.filter((row) => !packageItemIds.has(row.item_id)),
    ...packageRows,
  ];
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
  const packages = await fetchInboundPackages(itemIds);

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
    rows.flatMap((row) => {
      const item = itemMetaById.get(row.item_id);
      const ebayListingUrl = getEbayListingUrl(item);
      const inboundPackages = packages.get(row.item_id) ?? [];

      return [{
        ...row,
        inbound_packages: inboundPackages,
        package_count: inboundPackages.length,
        packages_delivered: inboundPackages.filter((pkg) => normalizeText(pkg.normalized_status) === "delivered" || pkg.delivered_date).length,
        packages_open: inboundPackages.filter((pkg) => normalizeText(pkg.resolution_status) === "open").length,
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
      }];
    })
  );
}

async function fetchReceivingPackageRows(excludedItemIds: string[]) {
  let request = supabase
    .from("inbound_shipment_items")
    .select(
      [
        "inbound_shipment_item_id",
        "quantity_expected_in_package",
        "quantity_received_from_package",
        "received_verified",
        "resolution_status",
        "inbound_shipments(inbound_shipment_id,purchase_id,tracking_number,carrier,carrier_status,normalized_status,shipment_status,estimated_delivery_date,delivered_date,tracking_url)",
        "purchase_items(item_id,purchase_id,title,amazon_title,quantity,unit_cost,asin,target_price,system,current_status,condition,supplier_sku,supplier_listing_url,raw_import_json,marketplace,received_date,purchases(supplier_order_id,order_date,total_order_cost,order_status,raw_import_json))",
      ].join(",")
    )
    .eq("resolution_status", "open")
    .not("inbound_shipments.delivered_date", "is", null)
    .limit(1000);

  if (excludedItemIds.length > 0) {
    request = request.not("item_id", "in", `(${excludedItemIds.join(",")})`);
  }

  const { data, error } = await request;
  if (error) {
    console.warn("Receiving package lookup failed", error.message);
    return [];
  }

  return (data ?? []).flatMap((link: any) => {
    const item = link.purchase_items;
    const shipment = link.inbound_shipments;
    if (!item || !shipment) return [];
    const purchase = item.purchases ?? {};

    return [{
      purchase_id: item.purchase_id,
      item_id: item.item_id,
      supplier_order_id: purchase.supplier_order_id ?? null,
      order_date: purchase.order_date ?? null,
      supplier: "eBay",
      order_status: purchase.order_status ?? null,
      title: item.title,
      ebay_title: item.title,
      amazon_title: item.amazon_title,
      asin: item.asin,
      system: item.system,
      quantity: item.quantity,
      unit_cost: item.unit_cost,
      sell_price: item.target_price,
      target_price: item.target_price,
      current_status:
        normalizeText(shipment.normalized_status) === "delivered"
          ? "delivered"
          : item.current_status,
      tracking_number: shipment.tracking_number,
      original_tracking_number: null,
      package_tracking_number: shipment.tracking_number,
      package_link_id: link.inbound_shipment_item_id,
      package_status: shipment.normalized_status ?? shipment.shipment_status,
      package_delivered_date: shipment.delivered_date,
      package_quantity_expected: link.quantity_expected_in_package,
      package_quantity_received: link.quantity_received_from_package,
      package_resolution_status: link.resolution_status,
      carrier: shipment.carrier,
      carrier_status: shipment.carrier_status,
      normalized_status: shipment.normalized_status,
      shipment_status: shipment.shipment_status,
      delivery_status: shipment.normalized_status,
      estimated_delivery_date: shipment.estimated_delivery_date,
      delivered_date: shipment.delivered_date,
      marketplace: item.marketplace,
      received_date: item.received_date,
      supplier_sku: item.supplier_sku,
      supplier_listing_url: item.supplier_listing_url,
    }];
  });
}

async function fetchInboundPackages(itemIds: string[]) {
  const byItem = new Map<string, any[]>();
  const uniqueItemIds = Array.from(new Set(itemIds));
  for (let index = 0; index < uniqueItemIds.length; index += 100) {
    const chunk = uniqueItemIds.slice(index, index + 100);
    const { data, error } = await supabase
      .from("inbound_shipment_items")
      .select(
        "inbound_shipment_item_id,item_id,quantity_expected_in_package,quantity_received_from_package,received_verified,resolution_status,resolution_reason," +
          "inbound_shipments(inbound_shipment_id,tracking_number,carrier,normalized_status,carrier_status,estimated_delivery_date,delivered_date,tracking_url)"
      )
      .in("item_id", chunk);

    if (error) {
      console.warn("Receiving package summary lookup failed", error.message);
      continue;
    }

    for (const link of data ?? []) {
      const shipment = (link as any).inbound_shipments ?? {};
      const itemId = (link as any).item_id;
      if (!itemId || !shipment) continue;
      const rows = byItem.get(itemId) ?? [];
      rows.push({
        inbound_shipment_id: shipment.inbound_shipment_id,
        inbound_shipment_item_id: (link as any).inbound_shipment_item_id,
        tracking_number: shipment.tracking_number,
        carrier: shipment.carrier,
        normalized_status: shipment.normalized_status,
        carrier_status: shipment.carrier_status,
        estimated_delivery_date: shipment.estimated_delivery_date,
        delivered_date: shipment.delivered_date,
        tracking_url: shipment.tracking_url,
        quantity_expected_in_package: (link as any).quantity_expected_in_package,
        quantity_received_from_package: (link as any).quantity_received_from_package,
        received_verified: (link as any).received_verified,
        resolution_status: (link as any).resolution_status,
        resolution_reason: (link as any).resolution_reason,
      });
      byItem.set(itemId, rows);
    }
  }
  return byItem;
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
      console.warn("Receiving exclusion lookup failed", error.message);
      return excludedItemIds;
    }

    excludedItemIds.push(
      ...((data ?? []) as { item_id: string }[]).map((item) => item.item_id)
    );

    if ((data ?? []).length < pageSize) return excludedItemIds;

    offset += pageSize;
  }
}

async function fetchItemMeta(itemIds: string[]) {
  const rows = [];
  const chunkSize = 100;

  for (let index = 0; index < itemIds.length; index += chunkSize) {
    const chunk = itemIds.slice(index, index + chunkSize);
    const { data, error } = await supabase
      .from("purchase_items")
      .select(
        "item_id,amazon_title,marketplace,received_date,supplier_sku,supplier_listing_url,raw_import_json,exclude_from_purchase_reporting"
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
  const adminError = requireAdminApiToken(request);
  if (adminError) return adminError;

  const body = await request.json();
  const updates = Array.isArray(body.items) ? body.items : [];
  const confirmation = typeof body.confirmation === "string" ? body.confirmation : "";
  const confirmationSource =
    typeof body.confirmation_source === "string" ? body.confirmation_source : "unknown";
  const receivedDate =
    typeof body.received_date === "string" && body.received_date.trim()
      ? body.received_date.trim()
      : localDateString();

  if (confirmation !== RECEIVING_CONFIRMATION_TOKEN) {
    console.warn("Rejected receiving save without current operator confirmation", {
      itemCount: updates.length,
      confirmationSource,
      userAgent: request.headers.get("user-agent"),
    });
    return NextResponse.json(
      { error: "Refresh the Receiving page and use the Received button to save." },
      { status: 409 }
    );
  }

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

    console.info("Receiving save applied", {
      itemCount: updates.length,
      itemIds: updates.map((update: ReceivingUpdate) => update.item_id).filter(Boolean),
      confirmationSource,
      receivedDate,
    });
    const pricingRefresh = await startReceivedPricingRefresh(results);

    return NextResponse.json({ success: true, items: results, pricingRefresh });
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
  const marketplace = update.marketplace || "Amazon";
  const asin = update.asin ? String(update.asin).trim().toUpperCase() : null;
  const sellPrice =
    update.sell_price === null || update.sell_price === undefined
      ? null
      : Number(update.sell_price);

  if (!Number.isFinite(quantityReceived) || quantityReceived < 0) {
    throw new Error("quantity_received must be zero or greater");
  }

  if (sellPrice !== null && !Number.isFinite(sellPrice)) {
    throw new Error("sell_price must be a valid number");
  }

  const { data: sourceData, error: sourceError } = await supabase
    .from("purchase_items")
    .select(
      "item_id,purchase_id,title,amazon_title,quantity,unit_cost,asin,target_price," +
        "system,condition,supplier_listing_url,import_batch_id,raw_import_json,tracking_number," +
        "manual_title_override,manual_unit_cost_override,purchases(supplier_order_id)"
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
    tracking_number: string | null;
    manual_title_override: boolean | null;
    manual_unit_cost_override: boolean | null;
    purchases?: { supplier_order_id?: string | null } | null;
  };

  const expectedQuantity = Number(source.quantity ?? 1);
  const requiresReturnEpisode = shouldOpenReceivingProblemEpisode(
    update,
    quantityReceived,
    expectedQuantity,
  );

  if (quantityReceived > expectedQuantity) {
    throw new Error("quantity_received cannot exceed quantity expected");
  }

  const isPartialMissingEpisode =
    requiresReturnEpisode &&
    quantityReceived > 0 &&
    quantityReceived < expectedQuantity &&
    !hasReceivedItemException(update);
  const hasOtherOpenPackages =
    update.package_link_id && quantityReceived > 0 && quantityReceived < expectedQuantity
      ? await hasOpenPackageLinksForItem(source.item_id, update.package_link_id)
      : false;

  if (
    (!requiresReturnEpisode || isPartialMissingEpisode || hasOtherOpenPackages) &&
    quantityReceived > 0 &&
    marketplace === "Amazon" &&
    (!asin || sellPrice === null)
  ) {
    throw new Error("ASIN and sell price are required for Amazon received items");
  }

  if (hasOtherOpenPackages) {
    const remainingQuantity = expectedQuantity - quantityReceived;

    const { data, error } = await supabase
      .from("purchase_items")
      .update({
        quantity: quantityReceived,
        current_status: "received",
        marketplace,
        asin: marketplace === "Amazon" ? asin : source.asin,
        target_price: marketplace === "Amazon" ? sellPrice : source.target_price,
        received_date: receivedDate,
      })
      .eq("item_id", source.item_id)
      .select()
      .single();

    if (error) throw new Error(error.message);

    const packageSplit = await createPackageQuantitySplit(
      {
        ...source,
        asin: marketplace === "Amazon" ? asin : source.asin,
        target_price: marketplace === "Amazon" ? sellPrice : source.target_price,
      },
      remainingQuantity,
      await deriveOpenPackageStatusForItem(source.item_id, update.package_link_id)
    );
    await moveOpenPackageLinksToSplit(source.item_id, packageSplit.item_id, update.package_link_id);
    await updateShipmentReceipt(source.item_id, quantityReceived, true, update.package_link_id);
    await closeExtraTrackingIfPurchaseFullyAccounted(source.purchase_id);
    await recordReceivingOutcome(source, update, quantityReceived, marketplace, asin, sellPrice);
    return data;
  }

  if (isPartialMissingEpisode) {
    const remainingQuantity = expectedQuantity - quantityReceived;

    const { data, error } = await supabase
      .from("purchase_items")
      .update({
        quantity: quantityReceived,
        current_status: "received",
        marketplace,
        asin: marketplace === "Amazon" ? asin : source.asin,
        target_price: marketplace === "Amazon" ? sellPrice : source.target_price,
        received_date: receivedDate,
      })
      .eq("item_id", source.item_id)
      .select()
      .single();

    if (error) throw new Error(error.message);

    const problemSplit = await createProblemQuantitySplit(
      {
        ...source,
        asin: marketplace === "Amazon" ? asin : source.asin,
        target_price: marketplace === "Amazon" ? sellPrice : source.target_price,
      },
      remainingQuantity
    );

    await splitShipmentReceipt(source.item_id, problemSplit.item_id, quantityReceived, remainingQuantity, update.package_link_id);
    await recordReceivingOutcome(source, update, quantityReceived, marketplace, asin, sellPrice);
    await openReceivingProblemEpisode(
      {
        item_id: problemSplit.item_id,
        purchase_id: source.purchase_id,
        title: source.title,
        quantity: remainingQuantity,
        purchases: source.purchases,
      },
      update,
      0
    );
    return data;
  }

  await updateShipmentReceipt(source.item_id, quantityReceived, !requiresReturnEpisode, update.package_link_id);

  if (requiresReturnEpisode) {
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
    await recordReceivingOutcome(source, update, quantityReceived, marketplace, asin, sellPrice);
    await openReceivingProblemEpisode(source, update, quantityReceived);
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
    await recordReceivingOutcome(source, update, quantityReceived, marketplace, asin, sellPrice);
    return data;
  }

  const remainingQuantity = expectedQuantity - quantityReceived;

  const { data, error } = await supabase
    .from("purchase_items")
    .update({
      quantity: quantityReceived,
      current_status: "received",
      marketplace,
      asin: marketplace === "Amazon" ? asin : source.asin,
      target_price: marketplace === "Amazon" ? sellPrice : source.target_price,
      received_date: receivedDate,
    })
    .eq("item_id", source.item_id)
    .select()
    .single();

  if (error) throw new Error(error.message);

  if (remainingQuantity > 0) {
    await createMissingQuantitySplit(
      {
        ...source,
        asin: marketplace === "Amazon" ? asin : source.asin,
        target_price: marketplace === "Amazon" ? sellPrice : source.target_price,
      },
      remainingQuantity
    );
  }

  await closeExtraTrackingIfPurchaseFullyAccounted(source.purchase_id);
  await recordReceivingOutcome(source, update, quantityReceived, marketplace, asin, sellPrice);
  return data;
}

async function recordReceivingOutcome(
  source: {
    item_id: string;
    purchase_id: string;
    title: string | null;
    amazon_title: string | null;
    quantity: number | null;
    asin: string | null;
    target_price: number | null;
    system: string | null;
    supplier_listing_url: string | null;
    raw_import_json: unknown;
    purchases?: { supplier_order_id?: string | null } | null;
  },
  update: ReceivingUpdate,
  quantityReceived: number,
  marketplace: "Amazon" | "eBay",
  asin: string | null,
  sellPrice: number | null
) {
  const outcome = normalizeReceivingOutcome(update.receiving_outcome, update.return_pending);
  const conditionIssue = normalizeConditionIssue(update.condition_issue);
  const imageClues = Array.isArray(update.image_clues)
    ? update.image_clues.map((value) => String(value)).filter(Boolean)
    : [];
  const notes =
    typeof update.receiving_notes === "string" && update.receiving_notes.trim()
      ? update.receiving_notes.trim()
      : null;

  const { error } = await supabase
    .from("matching_intelligence_receiving_outcomes")
    .upsert(
      {
        purchase_item_id: source.item_id,
        purchase_id: source.purchase_id,
        outcome,
        condition_issue: conditionIssue,
        image_clues: imageClues,
        notes,
        quantity_expected: Number(source.quantity ?? 1),
        quantity_received: quantityReceived,
        marketplace,
        asin: asin ?? source.asin,
        amazon_title: source.amazon_title,
        ebay_title: source.title,
        system: source.system,
        supplier_order_id: source.purchases?.supplier_order_id ?? null,
        ebay_item_id: ebayItemIdFromSource(source),
        ebay_listing_url: source.supplier_listing_url ?? getEbayListingUrl({
          supplier_listing_url: source.supplier_listing_url,
          raw_import_json: source.raw_import_json,
        }),
        raw_context_json: {
          targetPrice: sellPrice ?? source.target_price,
          returnPending: update.return_pending,
          rawImportJson: source.raw_import_json,
        },
        updated_at: new Date().toISOString(),
      },
      { onConflict: "purchase_item_id" },
    );

  if (error) {
    console.warn("Failed to record receiving outcome", error.message);
  }
}

async function startReceivedPricingRefresh(results: unknown[]) {
  const asins = Array.from(
    new Set(
      results
        .map((result) => {
          if (!result || typeof result !== "object") return "";
          const row = result as { current_status?: string | null; asin?: string | null };
          return row.current_status === "received"
            ? String(row.asin || "").trim().toUpperCase()
            : "";
        })
        .filter(Boolean)
    )
  );

  if (!asins.length) {
    return {
      started: false,
      status: "no_received_asins",
      message: "No received ASINs required a pricing refresh.",
    };
  }

  if (isCloudDeployment()) {
    try {
      const task = await runSchedulerGroupTask({
        group: "fba-pricing",
        source: "mbop-web-receiving-pricing",
        job: "receiving-pricing",
      });
      console.info("Started receiving pricing refresh in AWS", { asins, taskArn: task.taskArn });
      return {
        started: true,
        status: "started",
        executionMode: "aws-ecs",
        taskArn: task.taskArn,
        asins,
      };
    } catch (error) {
      console.warn("Failed to start AWS receiving pricing refresh", error);
      return {
        started: false,
        status: "failed_to_start",
        executionMode: "aws-ecs",
        message: error instanceof Error ? error.message : "Failed to start AWS receiving pricing refresh.",
        asins,
      };
    }
  }

  if (!isLocalJobExecutionEnabled()) {
    console.info("Skipped receiving pricing refresh because job execution is disabled.");
    return {
      started: false,
      status: "job_execution_disabled",
      message: "Keepa/Amazon fee refresh is disabled.",
      asins,
    };
  }

  const asinArgs = asins.flatMap((asin) => ["--asin", asin]);
  const keepaCommand = [
    ".venv\\Scripts\\python.exe",
    "integrations\\keepa_sync_products.py",
    "--source",
    "explicit",
    ...asinArgs,
    "--batch-size",
    "20",
    "--min-tokens",
    "1",
    "--offers",
    "20",
    "--stock",
    "--no-history",
    "--write",
  ].join(" ");
  const feeCommand = [
    ".venv\\Scripts\\python.exe",
    "integrations\\amazon_sync_fee_estimates.py",
    "--source",
    "explicit",
    ...asinArgs,
  ].join(" ");
  const shellCommand = `(${keepaCommand}) >> logs\\on_demand_sync.log 2>&1 & (${feeCommand}) >> logs\\on_demand_sync.log 2>&1`;

  try {
    const child = spawn("cmd.exe", ["/c", shellCommand], {
      cwd: ROOT_DIR,
      detached: true,
      stdio: "ignore",
      windowsHide: true,
    });
    child.unref();
    console.info("Started receiving pricing refresh", { asins });
    return {
      started: true,
      status: "started",
      asins,
    };
  } catch (error) {
    console.warn("Failed to start receiving pricing refresh", error);
    return {
      started: false,
      status: "failed_to_start",
      message: error instanceof Error ? error.message : "Failed to start receiving pricing refresh.",
    };
  }
}

async function openReceivingProblemEpisode(
  source: {
    item_id: string;
    purchase_id: string;
    title: string | null;
    quantity: number | null;
    purchases?: { supplier_order_id?: string | null } | null;
  },
  update: ReceivingUpdate,
  quantityReceived: number,
) {
  const now = new Date().toISOString();
  const expectedQuantity = Number(source.quantity ?? 1);
  const problemType = receivingProblemType(update);
  const episodeKind = receivingEpisodeKind(update, quantityReceived, expectedQuantity);
  const nextAction = "Open or continue return/refund follow-up.";
  const notes =
    typeof update.receiving_notes === "string" && update.receiving_notes.trim()
      ? update.receiving_notes.trim()
      : null;

  const { data: existingRows, error: existingError } = await supabase
    .from("order_problem_cases")
    .select("problem_case_id,notes")
    .eq("purchase_item_id", source.item_id)
    .eq("is_open", true)
    .limit(1);
  if (existingError) {
    console.warn("Receiving order problem lookup failed", existingError.message);
    return;
  }

  const existing = (existingRows ?? [])[0] as { problem_case_id: string; notes: string | null } | undefined;
  if (existing) {
    const { error } = await supabase
      .from("order_problem_cases")
      .update({
        problem_source: "receiving_return_pending",
        problem_type: problemType,
        workflow_state: "return_needed",
        priority: "normal",
        is_open: true,
        needs_response: false,
        next_action: nextAction,
        return_needed_at: now,
        last_detected_at: now,
        updated_at: now,
        episode_kind: episodeKind,
        opened_reason: "receiving_exception",
        source_artifact_type: "receiving_exception",
        notes: appendCaseNotes(existing.notes, notes),
      })
      .eq("problem_case_id", existing.problem_case_id);
    if (error) console.warn("Receiving order problem update failed", error.message);
    await insertOrderProblemEvent(existing.problem_case_id, "receiving_return_pending", "Receiving marked item return pending.", update);
    return;
  }

  const episodeSequence = await nextOrderProblemEpisodeSequence(source.item_id);
  const { data, error } = await supabase
    .from("order_problem_cases")
    .insert({
      purchase_item_id: source.item_id,
      purchase_id: source.purchase_id,
      supplier: "eBay",
      supplier_order_id: source.purchases?.supplier_order_id ?? null,
      problem_source: "receiving_return_pending",
      problem_type: problemType,
      workflow_state: "return_needed",
      priority: "normal",
      is_open: true,
      needs_response: false,
      next_action: nextAction,
      first_detected_at: now,
      last_detected_at: now,
      return_needed_at: now,
      episode_sequence: episodeSequence,
      episode_kind: episodeKind,
      opened_reason: "receiving_exception",
      source_artifact_type: "receiving_exception",
      notes,
    })
    .select("problem_case_id")
    .limit(1);
  if (error) {
    console.warn("Receiving order problem insert failed", error.message);
    return;
  }

  const caseId = (data ?? [])[0]?.problem_case_id as string | undefined;
  if (caseId) {
    await insertOrderProblemEvent(caseId, "receiving_return_pending", "Receiving marked item return pending.", update);
  }
}

function receivingProblemType(update: ReceivingUpdate) {
  const outcome = normalizeReceivingOutcome(update.receiving_outcome, update.return_pending);
  const issue = normalizeConditionIssue(update.condition_issue);
  if (outcome === "incomplete_item" || issue === "incomplete_product") return "missing_items";
  return "not_as_listed";
}

function receivingEpisodeKind(update: ReceivingUpdate, quantityReceived: number, expectedQuantity: number) {
  const outcome = normalizeReceivingOutcome(update.receiving_outcome, update.return_pending);
  const issue = normalizeConditionIssue(update.condition_issue);
  if (outcome === "incomplete_item" || issue === "incomplete_product" || quantityReceived < expectedQuantity) {
    return "incomplete_item";
  }
  if (
    outcome === "wrong_item" ||
    ["wrong_product", "wrong_platform", "wrong_edition_version", "non_north_american_version"].includes(issue || "")
  ) {
    return "return_request";
  }
  return "damaged_item";
}

function shouldOpenReceivingProblemEpisode(
  update: ReceivingUpdate,
  quantityReceived: number,
  expectedQuantity: number,
) {
  if (update.return_pending) return true;
  const outcome = normalizeReceivingOutcome(update.receiving_outcome, false);
  const issue = normalizeConditionIssue(update.condition_issue);
  if (quantityReceived < expectedQuantity) return true;
  if (["wrong_item", "wrong_condition", "packaging_issue", "incomplete_item"].includes(outcome)) return true;
  return Boolean(issue);
}

function hasReceivedItemException(update: ReceivingUpdate) {
  if (update.return_pending) return true;
  const outcome = normalizeReceivingOutcome(update.receiving_outcome, false);
  const issue = normalizeConditionIssue(update.condition_issue);
  if (["wrong_item", "wrong_condition", "packaging_issue", "incomplete_item"].includes(outcome)) {
    return true;
  }
  return Boolean(issue);
}

async function nextOrderProblemEpisodeSequence(itemId: string) {
  const { data, error } = await supabase
    .from("order_problem_cases")
    .select("episode_sequence")
    .eq("purchase_item_id", itemId)
    .order("episode_sequence", { ascending: false, nullsFirst: false })
    .limit(1);
  if (error) {
    console.warn("Receiving episode sequence lookup failed", error.message);
    return 1;
  }
  const current = Number((data ?? [])[0]?.episode_sequence ?? 0);
  return Number.isFinite(current) ? current + 1 : 1;
}

async function insertOrderProblemEvent(
  problemCaseId: string,
  eventType: string,
  message: string,
  rawJson: unknown,
) {
  const { error } = await supabase.from("order_problem_events").insert({
    problem_case_id: problemCaseId,
    event_type: eventType,
    event_source: "operator",
    message,
    raw_json: rawJson,
  });
  if (error) console.warn("Receiving order problem event insert failed", error.message);
}

function appendCaseNotes(existing: string | null, next: string | null) {
  if (!next) return existing;
  if (!existing) return next;
  return `${existing}\n${next}`;
}

function normalizeReceivingOutcome(value: unknown, returnPending: boolean) {
  const normalized = String(value || "").trim();
  if (
    [
      "correct_item",
      "wrong_item",
      "wrong_condition",
      "packaging_issue",
      "incomplete_item",
      "listed_successfully",
    ].includes(normalized)
  ) {
    return normalized;
  }
  return returnPending ? "wrong_condition" : "correct_item";
}

function normalizeConditionIssue(value: unknown) {
  const normalized = String(value || "").trim();
  return [
    "wrong_product",
    "wrong_platform",
    "wrong_edition_version",
    "non_north_american_version",
    "incomplete_product",
    "missing_shrink_wrap",
    "suspected_reseal",
    "packaging_damage",
    "other",
  ].includes(normalized)
    ? normalized
    : null;
}

function ebayItemIdFromSource(source: { supplier_listing_url?: string | null; raw_import_json?: unknown }) {
  const urlId = source.supplier_listing_url?.match(/\/itm\/(\d{9,15})/)?.[1];
  return urlId || findNestedString(source.raw_import_json, "ItemID");
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
    tracking_number: string | null;
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

async function createProblemQuantitySplit(
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
    tracking_number: string | null;
  },
  quantity: number
) {
  const { data, error } = await supabase
    .from("purchase_items")
    .insert({
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
      current_status: "return_pending",
      tracking_number: source.tracking_number,
      marketplace: null,
      received_date: null,
      manual_title_override: source.manual_title_override ?? false,
      manual_unit_cost_override: source.manual_unit_cost_override ?? false,
      manual_split_child: true,
      manual_split_parent_item_id: source.item_id,
    })
    .select("item_id")
    .single();

  if (error) throw new Error(error.message);
  return data as { item_id: string };
}

async function createPackageQuantitySplit(
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
    tracking_number: string | null;
  },
  quantity: number,
  status: string
) {
  const { data, error } = await supabase
    .from("purchase_items")
    .insert({
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
      current_status: status,
      tracking_number: source.tracking_number,
      marketplace: null,
      received_date: null,
      manual_title_override: source.manual_title_override ?? false,
      manual_unit_cost_override: source.manual_unit_cost_override ?? false,
      manual_split_child: true,
      manual_split_parent_item_id: source.item_id,
    })
    .select("item_id")
    .single();

  if (error) throw new Error(error.message);
  return data as { item_id: string };
}

async function hasOpenPackageLinksForItem(itemId: string, excludePackageLinkId?: string | null) {
  let request: any = supabase
    .from("inbound_shipment_items")
    .select("inbound_shipment_item_id")
    .eq("item_id", itemId)
    .eq("resolution_status", "open")
    .limit(1);

  if (excludePackageLinkId) {
    request = request.neq("inbound_shipment_item_id", excludePackageLinkId);
  }

  const { data, error } = await request;
  if (error) {
    console.warn("Failed to check open package links", error.message);
    return false;
  }

  return (data ?? []).length > 0;
}

async function deriveOpenPackageStatusForItem(itemId: string, excludePackageLinkId?: string | null) {
  let request: any = supabase
    .from("inbound_shipment_items")
    .select("inbound_shipment_item_id,inbound_shipments(normalized_status,shipment_status,delivered_date)")
    .eq("item_id", itemId)
    .eq("resolution_status", "open");

  if (excludePackageLinkId) {
    request = request.neq("inbound_shipment_item_id", excludePackageLinkId);
  }

  const { data, error } = await request;
  if (error) {
    console.warn("Failed to derive open package status", error.message);
    return "multi_package_in_transit";
  }

  const statuses: string[] = (data ?? []).map((link: any) => normalizeText(
    link.inbound_shipments?.normalized_status ?? link.inbound_shipments?.shipment_status
  ));
  if (statuses.some((status) => status === "delivered")) return "partially_delivered";
  if (statuses.some((status) => status === "out_for_delivery")) return "out_for_delivery";
  if (statuses.some((status) => status === "available_for_pickup")) return "available_for_pickup";
  if (statuses.some((status) => status === "in_transit")) return "multi_package_in_transit";
  return "multi_package_in_transit";
}

async function moveOpenPackageLinksToSplit(
  sourceItemId: string,
  splitItemId: string,
  excludePackageLinkId?: string | null
) {
  let request: any = supabase
    .from("inbound_shipment_items")
    .update({
      item_id: splitItemId,
      notes: "Moved to remaining package split after partial package receipt",
    })
    .eq("item_id", sourceItemId)
    .eq("resolution_status", "open");

  if (excludePackageLinkId) {
    request = request.neq("inbound_shipment_item_id", excludePackageLinkId);
  }

  const { error } = await request;
  if (error) {
    console.warn("Failed to move open package links to split item", error.message);
  }
}

async function splitShipmentReceipt(
  sourceItemId: string,
  splitItemId: string,
  quantityReceived: number,
  problemQuantity: number,
  packageLinkId?: string | null
) {
  let lookup: any = supabase
    .from("inbound_shipment_items")
    .select("inbound_shipment_item_id,inbound_shipment_id,notes")
    .eq("item_id", sourceItemId);

  lookup = packageLinkId
    ? lookup.eq("inbound_shipment_item_id", packageLinkId)
    : lookup.limit(1);

  const { data, error } = await lookup;

  if (error) {
    console.warn("Failed to look up inbound shipment split", error.message);
    return;
  }

  const existing = (data ?? [])[0] as
    | {
        inbound_shipment_item_id: string;
        inbound_shipment_id: string;
        notes: string | null;
      }
    | undefined;

  if (!existing) return;

  const { error: updateError } = await supabase
    .from("inbound_shipment_items")
    .update({
      quantity_expected_in_package: quantityReceived,
      quantity_received_from_package: quantityReceived,
      received_verified: true,
      resolution_status: "received",
      resolved_at: new Date().toISOString(),
      resolution_reason: "Partial quantity received from package",
      resolved_by: "operator",
    })
    .eq("inbound_shipment_item_id", existing.inbound_shipment_item_id);

  if (updateError) {
    console.warn("Failed to update inbound shipment receipt split", updateError.message);
    return;
  }

  const { error: insertError } = await supabase.from("inbound_shipment_items").insert({
    inbound_shipment_id: existing.inbound_shipment_id,
    item_id: splitItemId,
    quantity_expected_in_package: problemQuantity,
    quantity_received_from_package: 0,
    received_verified: false,
    resolution_status: "return_pending",
    resolved_at: new Date().toISOString(),
    resolution_reason: "Split from partial receiving exception",
    resolved_by: "operator",
    notes: existing.notes || "Split from partial receiving exception",
  });

  if (insertError) {
    console.warn("Failed to insert inbound shipment receipt split", insertError.message);
  }
}

async function updateShipmentReceipt(
  itemId: string,
  quantityReceived: number,
  receivedVerified: boolean,
  packageLinkId?: string | null
) {
  let request: any = supabase
    .from("inbound_shipment_items")
    .update({
      quantity_received_from_package: quantityReceived,
      received_verified: receivedVerified,
      resolution_status: receivedVerified ? "received" : "open",
      resolved_at: receivedVerified ? new Date().toISOString() : null,
      resolution_reason: receivedVerified ? "Received by operator" : null,
      resolved_by: receivedVerified ? "operator" : null,
    });

  request = packageLinkId
    ? request.eq("inbound_shipment_item_id", packageLinkId)
    : request.eq("item_id", itemId);

  const { error } = await request;

  if (error) {
    console.warn("Failed to update inbound shipment receipt", error.message);
  }
}

async function closeExtraTrackingIfPurchaseFullyAccounted(purchaseId: string) {
  const { data: items, error: itemError } = await supabase
    .from("purchase_items")
    .select("item_id,current_status,quantity")
    .eq("purchase_id", purchaseId);

  if (itemError) {
    console.warn("Failed to check purchase receiving completion", itemError.message);
    return;
  }

  const activeItems = (items ?? []).filter((item: any) =>
    !["cancelled", "return_pending", "return_opened"].includes(normalizeText(item.current_status))
  );
  const allAccounted = activeItems.length > 0 && activeItems.every((item: any) =>
    ["received", "listed"].includes(normalizeText(item.current_status))
  );

  if (!allAccounted) return;

  const itemIds = activeItems.map((item: any) => item.item_id).filter(Boolean);
  if (!itemIds.length) return;

  const { error: closeError } = await supabase
    .from("inbound_shipment_items")
    .update({
      resolution_status: "closed_fully_received_elsewhere",
      resolved_at: new Date().toISOString(),
      resolution_reason: "All ordered units for purchase were received elsewhere",
      resolved_by: "system",
    })
    .in("item_id", itemIds)
    .eq("resolution_status", "open")
    .or("received_verified.is.null,received_verified.eq.false");

  if (closeError) {
    console.warn("Failed to close extra package links", closeError.message);
  }

  await resolvePackageProblemCasesForFullyReceivedPurchase(purchaseId);
}

async function resolvePackageProblemCasesForFullyReceivedPurchase(purchaseId: string) {
  const now = new Date().toISOString();
  const { data: cases, error } = await supabase
    .from("order_problem_cases")
    .select("problem_case_id,notes")
    .eq("purchase_id", purchaseId)
    .eq("is_open", true)
    .eq("problem_type", "missing_items");

  if (error) {
    console.warn("Failed to look up package problem cases for closure", error.message);
    return;
  }

  for (const problemCase of cases ?? []) {
    const { error: updateError } = await supabase
      .from("order_problem_cases")
      .update({
        workflow_state: "closed_no_action",
        is_open: false,
        needs_response: false,
        resolved_reason: "no_action",
        closed_at: now,
        notes: appendCaseNotes((problemCase as any).notes, "Closed automatically because all ordered units were received elsewhere."),
      })
      .eq("problem_case_id", (problemCase as any).problem_case_id);
    if (updateError) console.warn("Failed to close fully received package problem", updateError.message);
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
