import { NextResponse } from "next/server";
import { spawn } from "child_process";
import path from "path";
import { createServerSupabaseClient, isLocalJobExecutionEnabled, requireAdminApiToken } from "../_server";

const supabase = createServerSupabaseClient();
const RECEIVING_CONFIRMATION_TOKEN = "operator_receive_v2";
const ROOT_DIR = path.resolve(process.cwd(), "..");

type ReceivingUpdate = {
  item_id: string;
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
    .in("current_status", ["delivered", "shipped_no_tracking"])
    .order("order_date", { ascending: false });

  if (excludedItemIds.length > 0) {
    request = request.not("item_id", "in", `(${excludedItemIds.join(",")})`);
  }

  const { data, error } = await request.limit(1000);

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
    rows.flatMap((row) => {
      const item = itemMetaById.get(row.item_id);
      const ebayListingUrl = getEbayListingUrl(item);

      return [{
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
      }];
    })
  );
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
    const pricingRefresh = startReceivedPricingRefresh(results);

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
        "system,condition,supplier_listing_url,import_batch_id,raw_import_json," +
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

  if (
    !requiresReturnEpisode &&
    quantityReceived > 0 &&
    marketplace === "Amazon" &&
    (!asin || sellPrice === null)
  ) {
    throw new Error("ASIN and sell price are required for Amazon received items");
  }

  await updateShipmentReceipt(source.item_id, quantityReceived, !requiresReturnEpisode);

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

function startReceivedPricingRefresh(results: unknown[]) {
  if (!isLocalJobExecutionEnabled()) {
    console.info("Skipped receiving pricing refresh because local job execution is disabled in cloud deployment.");
    return {
      started: false,
      status: "local_job_execution_disabled",
      message: "Local Keepa/Amazon fee refresh is disabled in cloud deployment.",
    };
  }

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
