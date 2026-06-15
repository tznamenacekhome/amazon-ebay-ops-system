import { promises as fs } from "fs";
import path from "path";
import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

export const runtime = "nodejs";

const supabaseUrl = process.env.SUPABASE_URL!;
const supabaseServiceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY!;

const supabase = createClient(supabaseUrl, supabaseServiceRoleKey);

type HealthStatus = "ok" | "delayed" | "failed" | "unknown" | "skipped" | "running" | "blocked";

type JobConfig = {
  id: string;
  name: string;
  command: string;
  group: "core" | "daily" | "catalog" | "monthly" | "disabled";
  blocking: boolean;
  enabled?: boolean;
  disabledReason?: string;
  expectedEveryHours: number;
  criticalAfterHours: number;
  signal: () => Promise<JobSignal>;
};

type JobSignal = {
  lastRunAt: string | null;
  source: string;
  stats: Array<{ label: string; value: string }>;
  statusOverride?: HealthStatus;
  message?: string | null;
};

type SchedulerFailure = {
  command: string;
  failedAt: string | null;
  message: string;
};

type LocalRunRecord = {
  command: string;
  job_name?: string | null;
  group?: string | null;
  blocking?: boolean | null;
  enabled?: boolean | null;
  status: "ok" | "failed" | "skipped" | "running" | "blocked";
  started_at?: string | null;
  finished_at?: string | null;
  message?: string | null;
};

type DynamicQueryResult = {
  data?: Array<Record<string, unknown>> | null;
  count?: number | null;
  error?: { message: string } | null;
};

type DynamicQuery = PromiseLike<DynamicQueryResult> & {
  select: (columns: string, options?: { count?: "exact"; head?: boolean }) => DynamicQuery;
  order: (column: string, options?: { ascending?: boolean; nullsFirst?: boolean }) => DynamicQuery;
  limit: (count: number) => DynamicQuery;
  eq: (column: string, value: unknown) => DynamicQuery;
  neq: (column: string, value: unknown) => DynamicQuery;
  gte: (column: string, value: unknown) => DynamicQuery;
  is: (column: string, value: unknown) => DynamicQuery;
  not: (column: string, operator: string, value: string) => DynamicQuery;
};

const JOBS: JobConfig[] = [
  {
    id: "ebay-buyer-purchases",
    name: "eBay buyer purchases",
    command: "integrations/ebay_sync_buyer_purchases.py",
    group: "core",
    blocking: true,
    expectedEveryHours: 12,
    criticalAfterHours: 24,
    signal: async () => {
      const batch = await latestRow("import_batches", "imported_at", "source_name,imported_at,import_batch_id", {
        source_name: "eBay Trading API Buyer Purchase Sync",
      });
      const importBatchId = stringValue(batch?.import_batch_id);
      const purchases = importBatchId
        ? await exactCount("purchases", { import_batch_id: importBatchId })
        : null;
      const items = importBatchId
        ? await exactCount("purchase_items", { import_batch_id: importBatchId })
        : null;

      return {
        lastRunAt: stringValue(batch?.imported_at),
        source: "import_batches",
        stats: [
          { label: "Purchases", value: formatCount(purchases) },
          { label: "Items", value: formatCount(items) },
        ],
      };
    },
  },
  {
    id: "easypost-shipments",
    name: "EasyPost shipments",
    command: "integrations/easypost_sync_shipments.py",
    group: "core",
    blocking: true,
    expectedEveryHours: 12,
    criticalAfterHours: 24,
    signal: async () => latestTimestampSignal("inbound_shipments", "last_tracking_sync", "Shipments"),
  },
  {
    id: "order-problem-returns",
    name: "eBay order problem returns/inquiries",
    command: "integrations/ebay_sync_order_problem_returns.py --lookback-days 60 --limit 100 --apply",
    group: "core",
    blocking: false,
    expectedEveryHours: 12,
    criticalAfterHours: 24,
    signal: async () => latestTimestampSignal("order_problem_events", "created_at", "Events"),
  },
  {
    id: "easypost-order-problem-returns",
    name: "EasyPost order problem returns",
    command: "integrations/easypost_sync_order_problem_returns.py --limit 100",
    group: "core",
    blocking: false,
    expectedEveryHours: 12,
    criticalAfterHours: 24,
    signal: async () => latestTimestampSignal("order_problem_cases", "return_tracking_last_sync_at", "Return tracking"),
  },
  {
    id: "sourcing-purchase-matching",
    name: "Sourcing purchase matching",
    command: "integrations/match_sourcing_purchases.py",
    group: "core",
    blocking: true,
    expectedEveryHours: 12,
    criticalAfterHours: 24,
    signal: async () => latestTimestampSignal("sourcing_purchase_matches", "matched_at", "Matches"),
  },
  {
    id: "revseller-enrichment",
    name: "RevSeller enrichment",
    command: "integrations/sync_revseller_sheet.py --ai-review --ai-review-limit 25",
    group: "core",
    blocking: true,
    expectedEveryHours: 12,
    criticalAfterHours: 24,
    signal: async () => latestRevsellerDiagnosticsSignal(),
  },
  {
    id: "keepa-missing-purchase-titles",
    name: "Keepa missing purchase titles",
    command:
      "integrations/backfill_amazon_titles_from_keepa.py --limit 25 --fetch-missing --min-tokens 25 --apply",
    group: "core",
    blocking: false,
    expectedEveryHours: 12,
    criticalAfterHours: 24,
    signal: async () => missingPurchaseTitleSignal(),
  },
  {
    id: "amazon-fba-inventory",
    name: "Amazon FBA inventory",
    command: "integrations/amazon_sync_fba_inventory.py",
    group: "daily",
    blocking: true,
    expectedEveryHours: 24,
    criticalAfterHours: 36,
    signal: async () => snapshotSignal("amazon_fba_inventory_snapshots", "captured_at", "Snapshot rows"),
  },
  {
    id: "amazon-fba-shipments",
    name: "Amazon FBA shipments",
    command: "integrations/amazon_sync_fba_shipments.py",
    group: "daily",
    blocking: true,
    expectedEveryHours: 24,
    criticalAfterHours: 36,
    signal: async () => {
      const row = await latestRow(
        "fba_shipments",
        "last_amazon_sync_at",
        "last_amazon_sync_at,shipment_code,amazon_status_normalized,units_sent,units_received,units_available,outbound_remaining_cost",
      );
      return {
        lastRunAt: stringValue(row?.last_amazon_sync_at),
        source: "fba_shipments",
        stats: [
          { label: "Shipment", value: stringValue(row?.shipment_code) || "--" },
          { label: "Status", value: stringValue(row?.amazon_status_normalized) || "--" },
          { label: "Sent", value: formatCount(row?.units_sent) },
          { label: "Received", value: formatCount(row?.units_received) },
          { label: "Available", value: formatCount(row?.units_available) },
          { label: "Outbound", value: formatCurrency(row?.outbound_remaining_cost) },
        ],
      };
    },
  },
  {
    id: "fba-easypost-carrier-tracking",
    name: "FBA EasyPost carrier tracking",
    command: "integrations/easypost_sync_fba_shipments.py",
    group: "daily",
    blocking: true,
    expectedEveryHours: 24,
    criticalAfterHours: 36,
    signal: async () => {
      const event = await latestRow(
        "fba_shipment_events",
        "created_at",
        "created_at,event_at,event_type",
        { event_source: "easypost" },
      );
      const shipment = await latestRow(
        "fba_shipments",
        "updated_at",
        "updated_at,shipment_code,tracking_number,carrier_pickup_at,carrier_delivered_at,carrier_delivery_eta",
      );
      return {
        lastRunAt: stringValue(event?.created_at) || stringValue(shipment?.updated_at),
        source: "fba_shipment_events",
        stats: [
          { label: "Shipment", value: stringValue(shipment?.shipment_code) || "--" },
          { label: "Tracking", value: stringValue(shipment?.tracking_number) || "--" },
          { label: "Latest event", value: stringValue(event?.event_type) || "--" },
          { label: "ETA", value: stringValue(shipment?.carrier_delivery_eta) || "--" },
        ],
      };
    },
  },
  {
    id: "amazon-listing-status",
    name: "Amazon listing status",
    command: "integrations/amazon_sync_listing_status.py",
    group: "daily",
    blocking: true,
    expectedEveryHours: 24,
    criticalAfterHours: 36,
    signal: async () => snapshotSignal("amazon_listing_snapshots", "captured_at", "Snapshot rows"),
  },
  {
    id: "amazon-inventory-planning",
    name: "Amazon inventory planning",
    command: "integrations/amazon_sync_inventory_planning.py",
    group: "daily",
    blocking: true,
    expectedEveryHours: 24,
    criticalAfterHours: 36,
    signal: async () => {
      const row = await latestRow(
        "amazon_report_runs",
        "requested_at",
        "report_type,processing_status,requested_at,completed_at,rows_imported,failure_reason",
        { report_type: "GET_FBA_INVENTORY_PLANNING_DATA" },
      );

      const status = stringValue(row?.processing_status);
      return {
        lastRunAt: stringValue(row?.completed_at) || stringValue(row?.requested_at),
        source: "amazon_report_runs",
        statusOverride: status === "error" ? "failed" : undefined,
        message: stringValue(row?.failure_reason),
        stats: [
          { label: "Rows imported", value: formatCount(row?.rows_imported) },
          { label: "Report status", value: status || "--" },
        ],
      };
    },
  },
  {
    id: "amazon-finance-balances",
    name: "Amazon finance balances",
    command: "integrations/amazon_sync_finance_balances.py",
    group: "daily",
    blocking: true,
    expectedEveryHours: 24,
    criticalAfterHours: 36,
    signal: async () => {
      const row = await latestRow(
        "amazon_finance_balance_snapshots",
        "captured_at",
        "captured_at,total_amazon_cash,in_transit_to_bank,transaction_count,financial_event_group_count",
      );
      return {
        lastRunAt: stringValue(row?.captured_at),
        source: "amazon_finance_balance_snapshots",
        stats: [
          { label: "Amazon cash", value: formatCurrency(row?.total_amazon_cash) },
          { label: "In transit", value: formatCurrency(row?.in_transit_to_bank) },
          { label: "Transactions", value: formatCount(row?.transaction_count) },
        ],
      };
    },
  },
  {
    id: "amazon-sales-orders",
    name: "Amazon sales orders",
    command: "integrations/amazon_sync_sales_orders.py",
    group: "core",
    blocking: false,
    expectedEveryHours: 12,
    criticalAfterHours: 24,
    signal: async () => latestTimestampSignal("amazon_sales_orders", "updated_at", "Orders updated"),
  },
  {
    id: "veeqo-sales-labels",
    name: "Veeqo MF label costs",
    command: "integrations/veeqo_sync_sales_labels.py",
    group: "core",
    blocking: false,
    expectedEveryHours: 12,
    criticalAfterHours: 24,
    signal: async () => latestTimestampSignal("veeqo_sales_orders", "updated_at", "Veeqo orders"),
  },
  {
    id: "recent-amazon-sales-finances",
    name: "Recent Amazon sales finances",
    command: "integrations/amazon_sync_sales_finances.py --order-finance-delay-seconds 1.5 --apply",
    group: "core",
    blocking: false,
    expectedEveryHours: 12,
    criticalAfterHours: 24,
    signal: async () => latestTimestampSignal("amazon_sales_financial_events", "created_at", "Financial rows"),
  },
  {
    id: "amazon-missing-fee-sales-finances",
    name: "Amazon missing-fee sales finances",
    command: "integrations/amazon_sync_sales_finances.py --order-finance-delay-seconds 1.5 --missing-fees-only --apply",
    group: "daily",
    blocking: false,
    expectedEveryHours: 24,
    criticalAfterHours: 36,
    signal: async () => latestTimestampSignal("amazon_sales_financial_events", "created_at", "Financial rows"),
  },
  {
    id: "recent-sales-profitability",
    name: "Recent sales profitability",
    command: "integrations/amazon_sales_profitability.py --apply",
    group: "core",
    blocking: false,
    expectedEveryHours: 12,
    criticalAfterHours: 24,
    signal: async () => latestTimestampSignal("amazon_sales_profitability", "updated_at", "Profit rows"),
  },
  {
    id: "daily-missing-fee-sales-profitability",
    name: "Daily missing-fee sales profitability",
    command: "integrations/amazon_sales_profitability.py --missing-fees-only --apply",
    group: "daily",
    blocking: false,
    expectedEveryHours: 24,
    criticalAfterHours: 36,
    signal: async () => latestTimestampSignal("amazon_sales_profitability", "updated_at", "Profit rows"),
  },
  {
    id: "informed-repricing",
    name: "Informed repricing reports",
    command: "integrations/informed_sync_reports.py",
    group: "daily",
    blocking: true,
    expectedEveryHours: 24,
    criticalAfterHours: 36,
    signal: async () => {
      const row = await latestRow(
        "informed_report_runs",
        "requested_at",
        "processing_status,requested_at,completed_at,imported_at,rows_read,rows_inserted,rows_skipped,failure_reason",
      );
      const status = stringValue(row?.processing_status);

      return {
        lastRunAt: stringValue(row?.imported_at) || stringValue(row?.completed_at) || stringValue(row?.requested_at),
        source: "informed_report_runs",
        statusOverride: status === "error" ? "failed" : undefined,
        message: stringValue(row?.failure_reason),
        stats: [
          { label: "Read", value: formatCount(row?.rows_read) },
          { label: "Inserted", value: formatCount(row?.rows_inserted) },
          { label: "Skipped", value: formatCount(row?.rows_skipped) },
        ],
      };
    },
  },
  {
    id: "ynab-cash-balance",
    name: "YNAB cash balance",
    command: "integrations/ynab_sync_cash_balance.py",
    group: "daily",
    blocking: true,
    expectedEveryHours: 24,
    criticalAfterHours: 36,
    signal: async () => {
      const row = await latestRow(
        "ynab_category_balance_snapshots",
        "captured_at",
        "captured_at,balance_currency,category_name",
      );
      return {
        lastRunAt: stringValue(row?.captured_at),
        source: "ynab_category_balance_snapshots",
        stats: [
          { label: "Balance", value: formatCurrency(row?.balance_currency) },
          { label: "Category", value: stringValue(row?.category_name) || "--" },
        ],
      };
    },
  },
  {
    id: "ynab-business-transactions",
    name: "YNAB Business transactions",
    command: "integrations/ynab_sync_business_transactions.py",
    group: "daily",
    blocking: true,
    expectedEveryHours: 24,
    criticalAfterHours: 36,
    signal: async () => {
      const [latestSynced, latestTransaction, countRow] = await Promise.all([
        latestRow(
          "ynab_business_transactions",
          "synced_at",
          "synced_at",
        ),
        latestRow(
          "ynab_business_transactions",
          "transaction_date",
          "transaction_date,amount_currency,payee_name",
        ),
        exactCount("ynab_business_transactions", {}),
      ]);

      return {
        lastRunAt: stringValue(latestSynced?.synced_at),
        source: "ynab_business_transactions",
        stats: [
          { label: "Rows", value: formatCount(countRow) },
          { label: "Latest txn", value: stringValue(latestTransaction?.transaction_date) || "--" },
          { label: "Latest amount", value: formatCurrency(latestTransaction?.amount_currency) },
        ],
      };
    },
  },
  {
    id: "keepa-products",
    name: "Keepa active products",
    command: "integrations/keepa_sync_products.py",
    group: "catalog",
    blocking: true,
    expectedEveryHours: 24,
    criticalAfterHours: 48,
    signal: async () => {
      const row = await latestRow(
        "keepa_product_snapshots",
        "captured_at",
        "captured_at,tokens_left,token_cost",
      );
      const rows = stringValue(row?.captured_at)
        ? await exactCount("keepa_product_snapshots", { captured_at: stringValue(row?.captured_at) })
        : null;

      return {
        lastRunAt: stringValue(row?.captured_at),
        source: "keepa_product_snapshots",
        stats: [
          { label: "Snapshot rows", value: formatCount(rows) },
          { label: "Tokens left", value: formatCount(row?.tokens_left) },
        ],
      };
    },
  },
  {
    id: "business-value",
    name: "Business value snapshot",
    command: "integrations/business_value_snapshot.py",
    group: "daily",
    blocking: true,
    expectedEveryHours: 24,
    criticalAfterHours: 36,
    signal: async () => {
      const row = await latestRow(
        "business_value_snapshots",
        "captured_at",
        "captured_at,snapshot_date,total_business_value",
      );
      return {
        lastRunAt: stringValue(row?.captured_at),
        source: "business_value_snapshots",
        stats: [
          { label: "Snapshot date", value: stringValue(row?.snapshot_date) || "--" },
          { label: "Business value", value: formatCurrency(row?.total_business_value) },
        ],
      };
    },
  },
  {
    id: "inventory-reconciliation",
    name: "Inventory reconciliation",
    command: "integrations/inventory_reconcile.py",
    group: "core",
    blocking: true,
    expectedEveryHours: 12,
    criticalAfterHours: 24,
    signal: async () => {
      const row = await latestRow(
        "inventory_reconciliation_events",
        "started_at",
        "status,started_at,completed_at,matched_count,mismatch_count,missing_internal_count,missing_external_count,needs_review_count",
      );
      const status = stringValue(row?.status);
      return {
        lastRunAt: stringValue(row?.completed_at) || stringValue(row?.started_at),
        source: "inventory_reconciliation_events",
        statusOverride: status === "failed" ? "failed" : undefined,
        stats: [
          { label: "Matched", value: formatCount(row?.matched_count) },
          { label: "Mismatches", value: formatCount(row?.mismatch_count) },
          { label: "Needs review", value: formatCount(row?.needs_review_count) },
        ],
      };
    },
  },
  {
    id: "inventory-source-balance-audit",
    name: "Inventory source balance audit",
    command: "inventory_source_balance_audit.bat",
    group: "monthly",
    blocking: true,
    expectedEveryHours: 31 * 24,
    criticalAfterHours: 45 * 24,
    signal: async () => inventorySourceBalanceAuditSignal(),
  },
];

export async function GET() {
  try {
    const [failures, localRuns] = await Promise.all([readSchedulerFailures(), readLocalRunRecords()]);
    const jobs = await Promise.all(
      JOBS.map(async (job) => {
        if (job.enabled === false) {
          return {
            id: job.id,
            name: job.name,
            command: job.command,
            group: job.group,
            blocking: job.blocking,
            enabled: false,
            status: "skipped" as HealthStatus,
            lastRunAt: null,
            hoursSinceLastRun: null,
            expectedEveryHours: job.expectedEveryHours,
            criticalAfterHours: job.criticalAfterHours,
            schedule: scheduleForGroup(job.group),
            source: "run_all_syncs.py",
            stats: [],
            message: job.disabledReason || null,
          };
        }
        const signal = await safeSignal(job);
        const failure = latestFailureForCommand(failures, job.command);
        const localRun = latestLocalRunForJob(localRuns, job);
        const localRunAt = stringValue(localRun?.finished_at) || stringValue(localRun?.started_at);
        const hasNewerLocalRun = localRunAt && isTimestampNewer(localRunAt, signal.lastRunAt);
        const lastRunAt = hasNewerLocalRun ? localRunAt : signal.lastRunAt;
        const hoursSinceLastRun = lastRunAt ? hoursSince(lastRunAt) : null;
        let status = statusForSignal(signal, hoursSinceLastRun, job);
        let message = signal.message || null;
        let source = signal.source;

        if (hasNewerLocalRun) {
          source = `${source} + logs/sync_health.json`;
          if (localRun?.status === "skipped") {
            status = "skipped";
            message = localRun.message || message;
          } else if (localRun?.status === "running") {
            status = "running";
            message = localRun.message || "Job is currently running.";
          } else if (localRun?.status === "blocked") {
            status = "blocked";
            message = localRun.message || "Run was blocked by another active sync.";
          } else if (localRun?.status === "failed") {
            status = "failed";
            message = localRun.message || `${job.command} failed in the latest local orchestrator run.`;
          } else {
            status = statusForSignal({ ...signal, statusOverride: undefined, lastRunAt }, hoursSinceLastRun, job);
          }
        }

        if (failure && isFailureNewerThanSignal(failure, lastRunAt)) {
          status = "failed";
          message = failure.message;
        }

        return {
          id: job.id,
          name: job.name,
          command: job.command,
          group: job.group,
          blocking: job.blocking,
          enabled: true,
          status,
          lastRunAt,
          hoursSinceLastRun,
          expectedEveryHours: job.expectedEveryHours,
          criticalAfterHours: job.criticalAfterHours,
          schedule: scheduleForGroup(job.group),
          source,
          stats: signal.stats,
          message,
        };
      }),
    );

    return NextResponse.json({
      generatedAt: new Date().toISOString(),
      jobs,
      summary: {
        total: jobs.length,
        ok: jobs.filter((job) => job.status === "ok").length,
        delayed: jobs.filter((job) => job.status === "delayed").length,
        failed: jobs.filter((job) => job.status === "failed").length,
        running: jobs.filter((job) => job.status === "running").length,
        blocked: jobs.filter((job) => job.status === "blocked").length,
        unknown: jobs.filter((job) => job.status === "unknown").length,
        skipped: jobs.filter((job) => job.status === "skipped").length,
      },
    });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Failed to load system health." },
      { status: 500 },
    );
  }
}

async function safeSignal(job: JobConfig): Promise<JobSignal> {
  try {
    return await job.signal();
  } catch (error) {
    return {
      lastRunAt: null,
      source: "unavailable",
      statusOverride: "unknown",
      message: error instanceof Error ? error.message : `Could not read ${job.name}.`,
      stats: [],
    };
  }
}

function statusForSignal(signal: JobSignal, hoursSinceLastRun: number | null, job: JobConfig): HealthStatus {
  if (signal.statusOverride) return signal.statusOverride;
  if (!signal.lastRunAt || hoursSinceLastRun === null) return "unknown";
  if (hoursSinceLastRun >= job.criticalAfterHours) return "failed";
  if (hoursSinceLastRun >= job.expectedEveryHours) return "delayed";
  return "ok";
}

function scheduleForGroup(group: JobConfig["group"]) {
  if (group === "core") return "Daily at 6:00 AM and 4:00 PM PT";
  if (group === "daily") return "Daily at 8:00 PM PT";
  if (group === "catalog") return "Daily at 9:30 PM PT";
  if (group === "monthly") return "Monthly on the 1st at 6:30 AM PT";
  return "Not scheduled";
}

async function latestTimestampSignal(table: string, column: string, countLabel: string): Promise<JobSignal> {
  const row = await latestNonNullRow(table, column, column);
  const lastRunAt = stringValue(row?.[column]);
  const count = lastRunAt ? await countSince(table, column, lastRunAt) : null;

  return {
    lastRunAt,
    source: table,
    stats: [{ label: countLabel, value: formatCount(count) }],
  };
}

async function snapshotSignal(table: string, column: string, countLabel: string): Promise<JobSignal> {
  const row = await latestNonNullRow(table, column, column);
  const lastRunAt = stringValue(row?.[column]);
  const count = lastRunAt ? await exactCount(table, { [column]: lastRunAt }) : null;

  return {
    lastRunAt,
    source: table,
    stats: [{ label: countLabel, value: formatCount(count) }],
  };
}

async function latestRow(
  table: string,
  orderColumn: string,
  select: string,
  equals?: Record<string, string>,
): Promise<Record<string, unknown> | null> {
  let query = dynamicFrom(table)
    .select(select)
    .order(orderColumn, { ascending: false, nullsFirst: false })
    .limit(1);

  for (const [column, value] of Object.entries(equals ?? {})) {
    query = query.eq(column, value);
  }

  const { data, error } = await query;
  if (error) throw new Error(`${table}: ${error.message}`);
  return data?.[0] ?? null;
}

async function latestNonNullRow(
  table: string,
  orderColumn: string,
  select: string,
  equals?: Record<string, string>,
): Promise<Record<string, unknown> | null> {
  let query = dynamicFrom(table)
    .select(select)
    .not(orderColumn, "is", "null")
    .order(orderColumn, { ascending: false, nullsFirst: false })
    .limit(1);

  for (const [column, value] of Object.entries(equals ?? {})) {
    query = query.eq(column, value);
  }

  const { data, error } = await query;
  if (error) throw new Error(`${table}: ${error.message}`);
  return data?.[0] ?? null;
}

async function latestRevsellerDiagnosticsSignal(): Promise<JobSignal> {
  const diagnosticsDir = path.resolve(process.cwd(), "..", "data");
  const files = await fs.readdir(diagnosticsDir);
  const diagnostics = await Promise.all(
    files
      .filter((fileName) => /^revseller_enrichment_diagnostics_\d{8}_\d{6}\.csv$/.test(fileName))
      .map(async (fileName) => {
        const filePath = path.join(diagnosticsDir, fileName);
        const stat = await fs.stat(filePath);
        return { fileName, filePath, stat };
      }),
  );

  const latest = diagnostics.sort((a, b) => b.stat.mtimeMs - a.stat.mtimeMs)[0];
  if (!latest) {
    return {
      lastRunAt: null,
      source: "data/revseller_enrichment_diagnostics_*.csv",
      stats: [],
      message: "No RevSeller diagnostics CSV found.",
    };
  }

  const text = await fs.readFile(latest.filePath, "utf8");
  const rows = Math.max(0, text.split(/\r?\n/).filter(Boolean).length - 1);

  return {
    lastRunAt: latest.stat.mtime.toISOString(),
    source: latest.fileName,
    stats: [{ label: "Unmatched diagnostics", value: formatCount(rows) }],
  };
}

async function inventorySourceBalanceAuditSignal(): Promise<JobSignal> {
  const filePath = path.resolve(process.cwd(), "..", "logs", "inventory_source_balance_audit_latest.json");
  try {
    const [stat, text] = await Promise.all([fs.stat(filePath), fs.readFile(filePath, "utf8")]);
    const parsed = JSON.parse(text) as Record<string, unknown>;
    return {
      lastRunAt: stringValue(parsed.captured_at) || stat.mtime.toISOString(),
      source: "logs/inventory_source_balance_audit_latest.json",
      stats: [
        { label: "ASINs", value: formatCount(parsed.asin_count) },
        { label: "Missing COGS units", value: formatCount(parsed.missing_cogs_units) },
      ],
    };
  } catch {
    return {
      lastRunAt: null,
      source: "logs/inventory_source_balance_audit_latest.json",
      stats: [],
      message: "No inventory source balance audit output found.",
    };
  }
}

async function missingPurchaseTitleSignal(): Promise<JobSignal> {
  let query = dynamicFrom("purchase_items")
    .select("*", { count: "exact", head: true })
    .not("asin", "is", "null")
    .neq("asin", "N/A")
    .not("current_status", "in", "(listed,cancelled,return_opened,return_pending)")
    .eq("exclude_from_purchase_reporting", false)
    .not("amazon_title", "is", "null");

  const { count: titledCount } = await query;

  query = dynamicFrom("purchase_items")
    .select("*", { count: "exact", head: true })
    .not("asin", "is", "null")
    .neq("asin", "N/A")
    .not("current_status", "in", "(listed,cancelled,return_opened,return_pending)")
    .eq("exclude_from_purchase_reporting", false)
    .is("amazon_title", null);

  const { count, error } = await query;
  if (error) throw new Error(`purchase_items: ${error.message}`);

  return {
    lastRunAt: null,
    source: "purchase_items",
    stats: [
      { label: "Missing active titles", value: formatCount(count) },
      { label: "Active titled ASINs", value: formatCount(titledCount) },
    ],
    statusOverride: count && count > 0 ? "delayed" : undefined,
  };
}

async function exactCount(table: string, equals: Record<string, string>): Promise<number | null> {
  let query = dynamicFrom(table).select("*", { count: "exact", head: true });
  for (const [column, value] of Object.entries(equals)) {
    query = query.eq(column, value);
  }
  const { count, error } = await query;
  if (error) return null;
  return count ?? null;
}

async function countSince(table: string, column: string, since: string): Promise<number | null> {
  const { count, error } = await dynamicFrom(table)
    .select("*", { count: "exact", head: true })
    .gte(column, since);
  if (error) return null;
  return count ?? null;
}

function dynamicFrom(table: string): DynamicQuery {
  return supabase.from(table) as unknown as DynamicQuery;
}

async function readSchedulerFailures(): Promise<SchedulerFailure[]> {
  const logPath = path.resolve(process.cwd(), "..", "logs", "scheduler.log");

  try {
    const stat = await fs.stat(logPath);
    const file = await fs.open(logPath, "r");
    try {
      const readSize = Math.min(stat.size, 200_000);
      const buffer = Buffer.alloc(readSize);
      await file.read(buffer, 0, readSize, Math.max(0, stat.size - readSize));
      return parseSchedulerFailures(buffer.toString("utf8"));
    } finally {
      await file.close();
    }
  } catch {
    return [];
  }
}

async function readLocalRunRecords(): Promise<LocalRunRecord[]> {
  const logPath = path.resolve(process.cwd(), "..", "logs", "sync_health.json");

  try {
    const parsed = JSON.parse(await fs.readFile(logPath, "utf8")) as unknown;
    if (!parsed || typeof parsed !== "object") return [];
    return Object.values(parsed as Record<string, unknown>).filter(isLocalRunRecord);
  } catch {
    return [];
  }
}

function parseSchedulerFailures(logText: string): SchedulerFailure[] {
  const lines = logText.split(/\r?\n/);
  const failures: SchedulerFailure[] = [];
  let currentCommand: string | null = null;
  let latestTimestamp: string | null = null;

  for (const line of lines) {
    const timestamp = parseLooseTimestamp(line);
    if (timestamp) latestTimestamp = timestamp;

    const runMatch = line.match(/--- Running (.+?) ---/);
    if (runMatch) currentCommand = runMatch[1];

    if (line.startsWith("ERROR:") && currentCommand) {
      failures.push({
        command: currentCommand,
        failedAt: latestTimestamp,
        message: line.replace(/^ERROR:\s*/, "").trim(),
      });
    }
  }

  return failures;
}

function parseLooseTimestamp(line: string): string | null {
  const isoMatch = line.match(/\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}/);
  if (!isoMatch) return null;

  const parsed = new Date(isoMatch[0].replace(" ", "T"));
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toISOString();
}

function latestFailureForCommand(failures: SchedulerFailure[], command: string) {
  return failures
    .filter((failure) => failure.command.includes(command))
    .sort((a, b) => (Date.parse(b.failedAt || "") || 0) - (Date.parse(a.failedAt || "") || 0))[0];
}

function latestLocalRunForJob(records: LocalRunRecord[], job: JobConfig) {
  return records
    .filter((record) => record.job_name === job.name || record.command.includes(job.command))
    .sort((a, b) => localRunTimestamp(b) - localRunTimestamp(a))[0];
}

function localRunTimestamp(record: LocalRunRecord) {
  return Date.parse(record.finished_at || record.started_at || "") || 0;
}

function isFailureNewerThanSignal(failure: SchedulerFailure, signalAt: string | null) {
  if (!failure.failedAt) return !signalAt;
  if (!signalAt) return true;
  return isTimestampNewer(failure.failedAt, signalAt);
}

function isTimestampNewer(candidate: string | null, baseline: string | null) {
  if (!candidate) return false;
  if (!baseline) return true;
  return Date.parse(candidate) > Date.parse(baseline);
}

function hoursSince(value: string) {
  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) return null;
  return Math.max(0, (Date.now() - timestamp) / 36e5);
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function isLocalRunRecord(value: unknown): value is LocalRunRecord {
  if (!value || typeof value !== "object") return false;
  const record = value as Record<string, unknown>;
  return (
    typeof record.command === "string" &&
    (
      record.status === "ok" ||
      record.status === "failed" ||
      record.status === "skipped" ||
      record.status === "running" ||
      record.status === "blocked"
    ) &&
    (record.finished_at === undefined || record.finished_at === null || typeof record.finished_at === "string")
  );
}

function formatCount(value: unknown): string {
  if (value === null || value === undefined || value === "") return "--";
  const number = Number(value);
  if (Number.isNaN(number)) return "--";
  return number.toLocaleString("en-US");
}

function formatCurrency(value: unknown): string {
  if (value === null || value === undefined || value === "") return "--";
  const number = Number(value);
  if (Number.isNaN(number)) return "--";
  return number.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });
}
