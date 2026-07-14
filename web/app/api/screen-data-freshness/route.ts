import { promises as fs } from "fs";
import path from "path";
import { NextRequest, NextResponse } from "next/server";
import { createServerSupabaseClient, isCloudDeployment } from "../_server";

export const runtime = "nodejs";

const supabase = createServerSupabaseClient();

type ScreenKey =
  | "purchases"
  | "dashboard"
  | "receiving"
  | "fba"
  | "repricing"
  | "sales-orders"
  | "inventory-reconciliation"
  | "system-health";

type FreshnessSource = {
  label: string;
  table?: string;
  column?: string;
  select?: string;
  equals?: Record<string, string>;
  filePattern?: RegExp;
};

type FreshnessResult = {
  screen: ScreenKey;
  lastUpdatedAt: string | null;
  source: string | null;
};

type FreshnessStrategy = "newest" | "oldest";

type DynamicQueryResult = {
  data?: Array<Record<string, unknown>> | null;
  error?: { message: string } | null;
};

type DynamicQuery = PromiseLike<DynamicQueryResult> & {
  select: (columns: string) => DynamicQuery;
  order: (column: string, options?: { ascending?: boolean; nullsFirst?: boolean }) => DynamicQuery;
  limit: (count: number) => DynamicQuery;
  eq: (column: string, value: string) => DynamicQuery;
  not: (column: string, operator: string, value: string) => DynamicQuery;
};

const SCREEN_SOURCES: Record<ScreenKey, FreshnessSource[]> = {
  purchases: [
    {
      label: "eBay purchases",
      table: "import_batches",
      column: "imported_at",
      select: "imported_at",
      equals: { source_name: "eBay Trading API Buyer Purchase Sync" },
    },
    { label: "tracking", table: "inbound_shipments", column: "last_tracking_sync" },
    { label: "order problems", table: "order_problem_cases", column: "updated_at" },
    { label: "order problem events", table: "order_problem_events", column: "created_at" },
    { label: "RevSeller", filePattern: /^revseller_enrichment_diagnostics_\d{8}_\d{6}\.csv$/ },
  ],
  dashboard: [
    { label: "Amazon cash", table: "amazon_finance_balance_snapshots", column: "captured_at" },
    { label: "Amazon sales profitability", table: "amazon_sales_profitability", column: "updated_at" },
    { label: "inventory positions", table: "inventory_positions", column: "updated_at" },
  ],
  receiving: [
    { label: "eBay purchases", table: "import_batches", column: "imported_at", equals: { source_name: "eBay Trading API Buyer Purchase Sync" } },
    { label: "tracking", table: "inbound_shipments", column: "last_tracking_sync" },
  ],
  fba: [
    { label: "FBA shipments", table: "fba_shipments", column: "updated_at" },
    { label: "FBA shipment items", table: "fba_shipment_items", column: "updated_at" },
    { label: "Amazon FBA inventory", table: "amazon_fba_inventory_snapshots", column: "captured_at" },
  ],
  repricing: [
    { label: "Informed reports", table: "informed_report_runs", column: "imported_at" },
    { label: "Keepa", table: "keepa_product_snapshots", column: "captured_at" },
    { label: "inventory planning", table: "amazon_inventory_planning_snapshots", column: "captured_at" },
  ],
  "sales-orders": [
    { label: "Amazon orders", table: "amazon_sales_orders", column: "updated_at" },
    { label: "profitability", table: "amazon_sales_profitability", column: "updated_at" },
    { label: "finance events", table: "amazon_sales_financial_events", column: "created_at" },
    { label: "finance transactions", table: "amazon_sales_finance_transactions", column: "updated_at" },
    { label: "MF labels", table: "veeqo_sales_shipments", column: "updated_at" },
  ],
  "inventory-reconciliation": [
    { label: "reconciliation", table: "inventory_reconciliation_events", column: "completed_at" },
    { label: "Amazon FBA inventory", table: "amazon_fba_inventory_snapshots", column: "captured_at" },
    { label: "MBOP inventory layers", table: "amazon_inventory_cogs_layers", column: "updated_at" },
  ],
  "system-health": [
    { label: "local sync runs", filePattern: /^sync_run_history\.json$/ },
    { label: "scheduler log", filePattern: /^scheduler\.log$/ },
  ],
};

const SCREEN_STRATEGY: Partial<Record<ScreenKey, FreshnessStrategy>> = {
  dashboard: "oldest",
};

export async function GET(request: NextRequest) {
  const screen = request.nextUrl.searchParams.get("screen") as ScreenKey | null;
  const screens = screen && screen in SCREEN_SOURCES
    ? [screen]
    : (Object.keys(SCREEN_SOURCES) as ScreenKey[]);

  const results = await Promise.all(screens.map(getScreenFreshness));
  const payload = {
    generatedAt: new Date().toISOString(),
    screens: Object.fromEntries(results.map((result) => [result.screen, result])),
  };

  return NextResponse.json(payload);
}

async function getScreenFreshness(screen: ScreenKey): Promise<FreshnessResult> {
  const candidates = await Promise.all(SCREEN_SOURCES[screen].map(readSourceFreshness));
  const available = candidates
    .filter((candidate): candidate is { lastUpdatedAt: string; source: string } => !!candidate.lastUpdatedAt)
    .sort((left, right) => {
      if (SCREEN_STRATEGY[screen] === "oldest") {
        return Date.parse(left.lastUpdatedAt) - Date.parse(right.lastUpdatedAt);
      }
      return Date.parse(right.lastUpdatedAt) - Date.parse(left.lastUpdatedAt);
    });
  const selected = available[0];

  return {
    screen,
    lastUpdatedAt: selected?.lastUpdatedAt ?? null,
    source: selected?.source ?? null,
  };
}

async function readSourceFreshness(source: FreshnessSource): Promise<{ lastUpdatedAt: string | null; source: string }> {
  if (source.filePattern) {
    return latestFileTimestamp(source);
  }

  if (!source.table || !source.column) {
    return { lastUpdatedAt: null, source: source.label };
  }

  try {
    const row = await latestTableRow(source);
    return {
      lastUpdatedAt: stringValue(row?.[source.column]) ?? null,
      source: source.label,
    };
  } catch {
    return { lastUpdatedAt: null, source: source.label };
  }
}

async function latestTableRow(source: FreshnessSource): Promise<Record<string, unknown> | null> {
  const column = source.column!;
  let query = dynamicFrom(source.table!)
    .select(source.select ?? column)
    .not(column, "is", "null")
    .order(column, { ascending: false, nullsFirst: false })
    .limit(1);

  for (const [key, value] of Object.entries(source.equals ?? {})) {
    query = query.eq(key, value);
  }

  const { data, error } = await query;
  if (error) throw new Error(error.message);
  return data?.[0] ?? null;
}

async function latestFileTimestamp(source: FreshnessSource): Promise<{ lastUpdatedAt: string | null; source: string }> {
  if (isCloudDeployment()) {
    return {
      lastUpdatedAt: null,
      source: `${source.label}: local file signal unavailable in cloud deployment`,
    };
  }

  const workspaceRoot = path.resolve(/* turbopackIgnore: true */ process.cwd(), "..");
  const directories = [path.join(workspaceRoot, "data"), path.join(workspaceRoot, "logs")];

  for (const directory of directories) {
    try {
      const files = await fs.readdir(directory);
      const candidates = await Promise.all(
        files
          .filter((fileName) => source.filePattern!.test(fileName))
          .map(async (fileName) => {
            const filePath = path.join(directory, fileName);
            const stat = await fs.stat(filePath);
            return { fileName, stat };
          }),
      );

      const latest = candidates.sort((left, right) => right.stat.mtimeMs - left.stat.mtimeMs)[0];
      if (latest) {
        return { lastUpdatedAt: latest.stat.mtime.toISOString(), source: source.label };
      }
    } catch {
      // Try the next local signal directory.
    }
  }

  return { lastUpdatedAt: null, source: source.label };
}

function dynamicFrom(table: string): DynamicQuery {
  return supabase.from(table) as unknown as DynamicQuery;
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}
