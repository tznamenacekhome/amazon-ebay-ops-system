import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.SUPABASE_URL!;
const supabaseServiceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY!;
const supabase = createClient(supabaseUrl, supabaseServiceRoleKey);

const LOW_ROI_THRESHOLD = 0.4;
const SALES_DATA_START_DATE = "2025-01-01";
const FULFILLED_ORDER_STATUSES = ["PartiallyShipped", "Shipped", "InvoiceUnconfirmed"];
const NOT_YET_FULFILLED_ORDER_STATUSES = ["Pending", "PendingAvailability", "Unshipped"];

type SalesOrderRow = {
  purchase_date: string | null;
  amazon_order_id: string;
  amazon_order_item_id: string;
  asin: string | null;
  seller_sku: string | null;
  title: string | null;
  quantity: number | null;
  sale_price: number | null;
  fulfillment_channel: string | null;
  order_status: string | null;
  amazon_fees_excluding_fulfillment: number | null;
  fulfillment_cost: number | null;
  fulfillment_cost_source: string | null;
  cogs: number | null;
  cogs_source: string | null;
  net_profit: number | null;
  roi: number | null;
  data_status: string | null;
};

type SalesOrderQuery = {
  startDate: string;
  endDate: string;
  fulfillment: string;
  profitability: string;
  dataStatus: string;
  search: string;
  quickFilter: string;
  sortColumn: string;
  sortDirection: "asc" | "desc";
  page: number;
  pageSize: number;
};

export async function GET(request: Request) {
  const query = parseQuery(new URL(request.url));

  try {
    const [pageResult, summaryRows] = await Promise.all([
      fetchRows(query, true),
      fetchRows(query, false),
    ]);

    return NextResponse.json({
      rows: pageResult.rows.map(withDisplayStatus),
      total: pageResult.total,
      page: query.page,
      pageSize: query.pageSize,
      summary: summarizeRows(summaryRows.rows),
      lowRoiThreshold: LOW_ROI_THRESHOLD,
    });
  } catch (error) {
    return NextResponse.json(
      {
        error:
          error instanceof Error ? error.message : "Failed to load sales orders",
      },
      { status: 500 }
    );
  }
}

function parseQuery(url: URL): SalesOrderQuery {
  const range = url.searchParams.get("range") || "30";
  const endDate =
    url.searchParams.get("endDate") || new Date().toISOString().slice(0, 10);
  const requestedStartDate =
    url.searchParams.get("startDate") ||
    dateStringDaysAgo(range === "custom" ? 30 : Number(range || 30));
  const startDate =
    requestedStartDate < SALES_DATA_START_DATE
      ? SALES_DATA_START_DATE
      : requestedStartDate;

  return {
    startDate,
    endDate,
    fulfillment: url.searchParams.get("fulfillment") || "all",
    profitability: url.searchParams.get("profitability") || "all",
    dataStatus: url.searchParams.get("dataStatus") || "all",
    search: (url.searchParams.get("search") || "").trim(),
    quickFilter: url.searchParams.get("quickFilter") || "recent",
    sortColumn: url.searchParams.get("sortColumn") || "purchase_date",
    sortDirection: url.searchParams.get("sortDirection") === "asc" ? "asc" : "desc",
    page: Math.max(Number(url.searchParams.get("page") || "1"), 1),
    pageSize: Math.min(Math.max(Number(url.searchParams.get("pageSize") || "100"), 25), 500),
  };
}

async function fetchRows(query: SalesOrderQuery, paged: boolean) {
  const rangeStart = (query.page - 1) * query.pageSize;
  const rangeEnd = rangeStart + query.pageSize - 1;
  const sortColumn = salesSortColumn(query.sortColumn);
  const ascending = query.sortDirection === "asc";

  let request: any = supabase
    .from("vw_amazon_sales_orders_recent")
    .select("*", { count: paged ? "exact" : undefined });

  request = applyFilters(request, query);
  request = request.order(sortColumn, { ascending, nullsFirst: false });

  if (paged) {
    request = request.range(rangeStart, rangeEnd);
  } else {
    request = request.limit(10000);
  }

  const { data, error, count } = await request;
  if (error) throw new Error(error.message);

  return {
    rows: (data ?? []) as SalesOrderRow[],
    total: count ?? data?.length ?? 0,
  };
}

function applyFilters(request: any, query: SalesOrderQuery) {
  request = request
    .gte("purchase_date", `${query.startDate}T00:00:00Z`)
    .lte("purchase_date", `${query.endDate}T23:59:59Z`);

  if (query.fulfillment === "fba") {
    request = request.in("fulfillment_channel", ["AFN", "Amazon", "AmazonFulfilled"]);
  } else if (query.fulfillment === "mf") {
    request = request.in("fulfillment_channel", ["MFN", "Merchant", "MerchantFulfilled"]);
  }

  if (query.profitability === "profitable") {
    request = request.gt("net_profit", 0);
  } else if (query.profitability === "low_roi") {
    request = request.lt("roi", LOW_ROI_THRESHOLD);
  } else if (query.profitability === "loss") {
    request = request.lt("net_profit", 0);
  }

  if (query.dataStatus !== "all") {
    if (query.dataStatus === "pending_fees") {
      request = request
        .eq("data_status", "missing_fees")
        .in("order_status", NOT_YET_FULFILLED_ORDER_STATUSES);
    } else if (query.dataStatus === "missing_fees") {
      request = request
        .eq("data_status", "missing_fees")
        .in("order_status", FULFILLED_ORDER_STATUSES);
    } else {
      request = request.eq("data_status", query.dataStatus);
    }
  }

  if (query.quickFilter === "profit_exceptions") {
    request = request.or(
      [
        `roi.lt.${LOW_ROI_THRESHOLD}`,
        "net_profit.lt.0",
        "data_status.eq.missing_cogs",
        "data_status.eq.missing_fulfillment_cost",
      ].join(",")
    );
  } else if (query.quickFilter === "missing_data") {
    request = request.in("data_status", [
      "missing_fees",
      "missing_cogs",
      "missing_fulfillment_cost",
    ]);
  } else if (query.quickFilter === "mf_label_missing") {
    request = request
      .in("fulfillment_channel", ["MFN", "Merchant", "MerchantFulfilled"])
      .eq("data_status", "missing_fulfillment_cost");
  } else if (query.quickFilter === "losses") {
    request = request.lt("net_profit", 0);
  }

  if (query.search) {
    const term = escapeIlike(query.search);
    request = request.or(
      [
        `amazon_order_id.ilike.%${term}%`,
        `asin.ilike.%${term}%`,
        `seller_sku.ilike.%${term}%`,
        `title.ilike.%${term}%`,
      ].join(",")
    );
  }

  return request;
}

function summarizeRows(rows: SalesOrderRow[]) {
  const summary = rows.reduce(
    (sum, row) => ({
      revenue: sum.revenue + Number(row.sale_price ?? 0),
      amazonFees: sum.amazonFees + Number(row.amazon_fees_excluding_fulfillment ?? 0),
      fulfillment: sum.fulfillment + Number(row.fulfillment_cost ?? 0),
      cogs: sum.cogs + Number(row.cogs ?? 0),
      netProfit: sum.netProfit + Number(row.net_profit ?? 0),
      roiTotal: sum.roiTotal + (row.roi === null || row.roi === undefined ? 0 : Number(row.roi)),
      roiCount: sum.roiCount + (row.roi === null || row.roi === undefined ? 0 : 1),
      orderIds: sum.orderIds.add(row.amazon_order_id),
      units: sum.units + Number(row.quantity ?? 0),
      pendingFees:
        sum.pendingFees +
        (row.data_status === "missing_fees" && !isFulfilledOrderStatus(row.order_status)
          ? 1
          : 0),
      missingFees:
        sum.missingFees +
        (row.data_status === "missing_fees" && isFulfilledOrderStatus(row.order_status)
          ? 1
          : 0),
      missingCogs: sum.missingCogs + (row.data_status === "missing_cogs" ? 1 : 0),
      missingFulfillment:
        sum.missingFulfillment +
        (row.data_status === "missing_fulfillment_cost" ? 1 : 0),
    }),
    {
      revenue: 0,
      amazonFees: 0,
      fulfillment: 0,
      cogs: 0,
      netProfit: 0,
      roiTotal: 0,
      roiCount: 0,
      orderIds: new Set<string>(),
      units: 0,
      missingFees: 0,
      pendingFees: 0,
      missingCogs: 0,
      missingFulfillment: 0,
    }
  );

  return {
    revenue: roundMoney(summary.revenue),
    amazonFees: roundMoney(summary.amazonFees),
    fulfillment: roundMoney(summary.fulfillment),
    cogs: roundMoney(summary.cogs),
    netProfit: roundMoney(summary.netProfit),
    averageRoi:
      summary.roiCount > 0 ? Number((summary.roiTotal / summary.roiCount).toFixed(4)) : null,
    orderCount: summary.orderIds.size,
    unitCount: summary.units,
    pendingFees: summary.pendingFees,
    missingFees: summary.missingFees,
    missingCogs: summary.missingCogs,
    missingFulfillment: summary.missingFulfillment,
  };
}

function withDisplayStatus(row: SalesOrderRow) {
  return {
    ...row,
    display_data_status:
      row.data_status === "missing_fees" && !isFulfilledOrderStatus(row.order_status)
        ? "pending_fees"
        : row.data_status,
  };
}

function isFulfilledOrderStatus(value?: string | null) {
  return FULFILLED_ORDER_STATUSES.includes(value || "");
}

function salesSortColumn(column: string) {
  const columns: Record<string, string> = {
    purchase_date: "purchase_date",
    amazon_order_id: "amazon_order_id",
    asin: "asin",
    title: "title",
    quantity: "quantity",
    sale_price: "sale_price",
    fulfillment_channel: "fulfillment_channel",
    amazon_fees_excluding_fulfillment: "amazon_fees_excluding_fulfillment",
    fulfillment_cost: "fulfillment_cost",
    cogs: "cogs",
    net_profit: "net_profit",
    roi: "roi",
    data_status: "data_status",
  };

  return columns[column] || "purchase_date";
}

function roundMoney(value: number) {
  return Number(value.toFixed(2));
}

function escapeIlike(value: string) {
  return value.replace(/[%_,]/g, "\\$&");
}

function dateStringDaysAgo(days: number) {
  const date = new Date();
  date.setUTCDate(date.getUTCDate() - days);
  return date.toISOString().slice(0, 10);
}
