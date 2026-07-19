import { NextResponse } from "next/server";
import { supabase, toNumber } from "../_summary";

const PROVIDERS = [
  { key: "aws", label: "AWS" },
  { key: "supabase", label: "Supabase" },
  { key: "easypost", label: "EasyPost" },
] as const;

type ProviderKey = (typeof PROVIDERS)[number]["key"];

type PeriodRow = {
  provider_billing_period_id: string;
  provider: ProviderKey;
  external_account_id: string | null;
  period_start: string | null;
  period_end: string | null;
  billing_cycle_type: string | null;
  period_status: string | null;
  currency: string | null;
  source: string | null;
  coverage_status: string | null;
  provider_reported_total: number | null;
  calculated_total: number | null;
  forecast_total: number | null;
  finalized_total: number | null;
  last_synchronized_at: string | null;
  metadata: Record<string, unknown> | null;
};

type LineItemRow = {
  provider: ProviderKey;
  provider_billing_period_id: string;
  category: string | null;
  subcategory: string | null;
  service: string | null;
  quantity: number | null;
  unit: string | null;
  unit_price: number | null;
  cost: number | null;
  credits_or_adjustments: number | null;
  source: string | null;
};

type UsageSnapshotRow = {
  provider: ProviderKey;
  metric_name: string | null;
  metric_value: number | null;
  metric_unit: string | null;
  captured_at: string | null;
  project_or_resource_id: string | null;
  raw_metadata: Record<string, unknown> | null;
};

type SyncRunRow = {
  provider: ProviderKey;
  status: string | null;
  started_at: string | null;
  finished_at: string | null;
  error_summary: string | null;
};

export async function GET() {
  const [periods, lineItems, usageSnapshots, syncRuns] = await Promise.all([
    fetchPeriods(),
    fetchLineItems(),
    fetchUsageSnapshots(),
    fetchSyncRuns(),
  ]);

  const providers = PROVIDERS.map((provider) => buildProvider(provider.key, provider.label, periods, lineItems, usageSnapshots, syncRuns));

  return NextResponse.json({
    refreshedAt: newest(providers.map((provider) => provider.lastSynchronizedAt)),
    providers,
    summary: providers.map((provider) => ({
      provider: provider.label,
      period: provider.currentPeriod?.periodLabel ?? "Unavailable",
      currentCycleCost: provider.currentPeriod?.currentCycleCost ?? null,
      forecastTotal: provider.currentPeriod?.forecastTotal ?? null,
      previousCompletedCost: provider.previousPeriod?.totalCost ?? null,
      dollarVariance: provider.dollarVariance,
      varianceLabel: provider.varianceLabel,
      currency: provider.currentPeriod?.currency ?? provider.previousPeriod?.currency ?? null,
      source: provider.currentPeriod?.source ?? "api",
      lastUpdated: provider.lastSynchronizedAt,
      coverageStatus: provider.currentPeriod?.coverageStatus ?? "unavailable",
      status: provider.syncStatus,
    })),
    notes: [
      "Provider periods are independent; no combined current-cycle total is calculated.",
      "No banking, credit-card, manual invoice, or manual cost-entry data is used.",
    ],
  });
}

async function fetchPeriods() {
  const { data, error } = await supabase
    .from("provider_billing_periods")
    .select("*")
    .order("period_start", { ascending: false })
    .limit(60);
  if (error) {
    console.warn("Provider cost period lookup failed", error.message);
    return [] as PeriodRow[];
  }
  return (data ?? []) as unknown as PeriodRow[];
}

async function fetchLineItems() {
  const { data, error } = await supabase
    .from("provider_cost_line_items")
    .select("provider,provider_billing_period_id,category,subcategory,service,quantity,unit,unit_price,cost,credits_or_adjustments,source")
    .order("cost", { ascending: false, nullsFirst: false })
    .limit(500);
  if (error) {
    console.warn("Provider cost line item lookup failed", error.message);
    return [] as LineItemRow[];
  }
  return (data ?? []) as unknown as LineItemRow[];
}

async function fetchUsageSnapshots() {
  const { data, error } = await supabase
    .from("provider_usage_snapshots")
    .select("provider,metric_name,metric_value,metric_unit,captured_at,project_or_resource_id,raw_metadata")
    .order("captured_at", { ascending: false })
    .limit(200);
  if (error) {
    console.warn("Provider usage snapshot lookup failed", error.message);
    return [] as UsageSnapshotRow[];
  }
  return (data ?? []) as unknown as UsageSnapshotRow[];
}

async function fetchSyncRuns() {
  const { data, error } = await supabase
    .from("provider_cost_sync_runs")
    .select("provider,status,started_at,finished_at,error_summary")
    .order("started_at", { ascending: false })
    .limit(30);
  if (error) {
    console.warn("Provider cost sync run lookup failed", error.message);
    return [] as SyncRunRow[];
  }
  return (data ?? []) as unknown as SyncRunRow[];
}

function buildProvider(
  provider: ProviderKey,
  label: string,
  periods: PeriodRow[],
  lineItems: LineItemRow[],
  usageSnapshots: UsageSnapshotRow[],
  syncRuns: SyncRunRow[],
) {
  const providerPeriods = periods.filter((period) => period.provider === provider);
  const current = providerPeriods.find((period) => period.period_status === "current") ?? providerPeriods[0] ?? null;
  const previous = providerPeriods.find((period) => period.period_status === "completed" || period.period_status === "finalized") ?? null;
  const latestRun = syncRuns.find((run) => run.provider === provider) ?? null;
  const currentLineItems = current
    ? lineItems.filter((lineItem) => lineItem.provider_billing_period_id === current.provider_billing_period_id)
    : [];
  const latestUsage = usageSnapshots.filter((snapshot) => snapshot.provider === provider).slice(0, 20);

  return {
    provider,
    label,
    currentPeriod: current ? serializePeriod(current) : unavailablePeriod(provider),
    previousPeriod: previous ? serializePeriod(previous) : null,
    dollarVariance: varianceFor(current, previous),
    varianceLabel: varianceLabelFor(current, previous),
    breakdown: aggregateLineItems(currentLineItems),
    history: providerPeriods.slice(0, 12).map(serializePeriod),
    usageSnapshots: latestUsage.map((snapshot) => ({
      metricName: snapshot.metric_name,
      metricValue: snapshot.metric_value,
      metricUnit: snapshot.metric_unit,
      capturedAt: snapshot.captured_at,
      resource: snapshot.project_or_resource_id,
      status: snapshot.raw_metadata?.reason ? String(snapshot.raw_metadata.reason) : null,
    })),
    lastSynchronizedAt: current?.last_synchronized_at ?? latestRun?.finished_at ?? null,
    syncStatus: latestRun?.status ?? (current ? "ok" : "unavailable"),
    errorSummary: latestRun?.status === "failed" ? latestRun.error_summary : null,
  };
}

function serializePeriod(period: PeriodRow) {
  const totalCost = period.finalized_total ?? period.provider_reported_total ?? period.calculated_total ?? null;
  const periodUnavailable = period.period_status === "unavailable" || period.billing_cycle_type === "unavailable";
  return {
    id: period.provider_billing_period_id,
    periodStart: period.period_start,
    periodEnd: period.period_end,
    periodLabel: periodUnavailable
      ? "Unavailable"
      : period.period_start && period.period_end
        ? `${formatShortDate(period.period_start)} - ${formatShortDate(period.period_end)} excl.`
        : "Unavailable",
    billingCycleType: period.billing_cycle_type,
    periodStatus: period.period_status,
    coverageStatus: period.coverage_status,
    currency: period.currency,
    source: period.source,
    totalCost,
    currentCycleCost: period.period_status === "current" ? totalCost : null,
    forecastTotal: period.forecast_total,
    lastSynchronizedAt: period.last_synchronized_at,
    unavailableReason: period.metadata?.cost_unavailable_reason ? String(period.metadata.cost_unavailable_reason) : null,
  };
}

function unavailablePeriod(provider: ProviderKey) {
  return {
    id: `${provider}-unavailable`,
    periodStart: null,
    periodEnd: null,
    periodLabel: "Unavailable",
    billingCycleType: "unavailable",
    periodStatus: "unavailable",
    coverageStatus: "unavailable",
    currency: null,
    source: "api",
    totalCost: null,
    currentCycleCost: null,
    forecastTotal: null,
    lastSynchronizedAt: null,
    unavailableReason: "No provider-cost synchronization data is stored yet.",
  };
}

function aggregateLineItems(rows: LineItemRow[]) {
  const byKey = new Map<string, { category: string; service: string; cost: number; quantity: number; unit: string | null; source: string | null }>();
  for (const row of rows) {
    const key = `${row.category ?? "uncategorized"}:${row.service ?? row.subcategory ?? "Other"}`;
    const current = byKey.get(key) ?? {
      category: row.category ?? "uncategorized",
      service: row.service ?? row.subcategory ?? "Other",
      cost: 0,
      quantity: 0,
      unit: row.unit,
      source: row.source,
    };
    current.cost += toNumber(row.cost);
    current.quantity += toNumber(row.quantity);
    byKey.set(key, current);
  }
  return [...byKey.values()]
    .filter((row) => Math.abs(row.cost) > 0 || row.quantity > 0)
    .sort((left, right) => Math.abs(right.cost) - Math.abs(left.cost))
    .slice(0, 20);
}

function varianceFor(current: PeriodRow | null, previous: PeriodRow | null) {
  if (!current || !previous) return null;
  const currentTotal = current.finalized_total ?? current.provider_reported_total ?? current.calculated_total;
  const previousTotal = previous.finalized_total ?? previous.provider_reported_total ?? previous.calculated_total;
  if (currentTotal === null || previousTotal === null) return null;
  return toNumber(currentTotal) - toNumber(previousTotal);
}

function varianceLabelFor(current: PeriodRow | null, previous: PeriodRow | null) {
  if (!current || !previous) return "Unavailable";
  if (current.period_status === "current" && current.coverage_status !== "complete") return "Current-cycle comparison";
  return "Dollar variance";
}

function formatShortDate(value: string) {
  const date = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  }).format(date);
}

function newest(values: Array<string | null | undefined>) {
  return values.filter(Boolean).sort().at(-1) ?? null;
}
