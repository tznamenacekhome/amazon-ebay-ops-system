"use client";

import { useEffect, useMemo, useState } from "react";
import { RefreshCw } from "lucide-react";

type RecommendationTier =
  | "Healthy"
  | "Watch"
  | "Reprice"
  | "Liquidate"
  | "Remove / eBay"
  | "Needs Data";

type AdvisorBucket =
  | "Pricing"
  | "Inventory / Listing Issue"
  | "Missing Data";

type AmazonAgeBucket =
  | "0-90"
  | "91-180"
  | "181-270"
  | "271-365"
  | "365+";

type AdvisorRow = {
  asin: string | null;
  seller_sku: string;
  title: string;
  condition: string | null;
  fba_sellable_quantity: number;
  inbound_quantity: number;
  reserved_quantity: number;
  reserved_customer_order_quantity: number;
  reserved_fc_transfer_quantity: number;
  reserved_fc_processing_quantity: number;
  future_supply_buyable_quantity: number;
  reserved_future_supply_quantity: number;
  inventory_detail_status: string;
  unsellable_quantity: number;
  unfulfillable_customer_damaged_quantity: number;
  unfulfillable_warehouse_damaged_quantity: number;
  unfulfillable_distributor_damaged_quantity: number;
  unfulfillable_carrier_damaged_quantity: number;
  unfulfillable_defective_quantity: number;
  unfulfillable_expired_quantity: number;
  total_quantity: number;
  listing_status: string | null;
  listing_issue_status: string;
  listing_issue_count: number;
  cost_basis: number | null;
  cost_source: string | null;
  oldest_known_purchase_date: string | null;
  inventory_age_days: number | null;
  amazon_age_bucket: AmazonAgeBucket | null;
  amazon_age_source: "Amazon Inventory Planning" | "InventoryLab/MBOP fallback" | "Missing";
  inv_age_0_to_90_days: number;
  inv_age_91_to_180_days: number;
  inv_age_181_to_270_days: number;
  inv_age_271_to_365_days: number;
  inv_age_365_plus_days: number;
  planning_snapshot_date: string | null;
  planning_recommended_action: string | null;
  planning_alert: string | null;
  sales_shipped_last_30_days: number | null;
  sales_shipped_last_90_days: number | null;
  informed_rule_name: string | null;
  informed_current_price: number | null;
  informed_min_price: number | null;
  informed_max_price: number | null;
  informed_buy_box_price: number | null;
  informed_buy_box_status: string | null;
  informed_repricing_enabled: boolean | null;
  informed_missing_data: boolean;
  informed_price_gap_to_buy_box_pct: number | null;
  informed_min_price_gap_to_buy_box_pct: number | null;
  informed_repricing_note: string;
  current_list_price: number | null;
  keepa_buy_box_price: number | null;
  keepa_buy_box_avg30: number | null;
  keepa_buy_box_avg90: number | null;
  keepa_sales_rank_current: number | null;
  keepa_sales_rank_avg90: number | null;
  keepa_sales_rank_drops30: number | null;
  keepa_sales_rank_drops90: number | null;
  offer_count: number | null;
  review_count: number | null;
  rating: number | null;
  keepa_captured_at: string | null;
  has_keepa_data: boolean;
  estimated_capital_tied_up: number | null;
  advisor_bucket: AdvisorBucket;
  recommended_target_price: number | null;
  target_price_basis: string | null;
  recommendation_tier: RecommendationTier;
  recommended_manual_action: string;
  reason: string;
};

type AdvisorData = {
  generated_at: string;
  summary: {
    total_rows: number;
    total_units: number;
    total_estimated_capital_tied_up: number;
    aged_capital_over_90_days: number;
    aged_capital_over_180_days: number;
    rows_needing_data: number;
    unsellable_or_suppressed_rows: number;
    by_tier: Record<RecommendationTier, number>;
    by_bucket: Record<AdvisorBucket, number>;
  };
  rows: AdvisorRow[];
};

const TIERS: Array<"All" | RecommendationTier> = [
  "All",
  "Remove / eBay",
  "Liquidate",
  "Reprice",
  "Needs Data",
  "Watch",
  "Healthy",
];

const AGE_BUCKETS = [
  "All",
  "0-90",
  "91-180",
  "181-270",
  "271-365",
  "365+",
  "Missing",
] as const;

const BUCKETS: Array<"All" | AdvisorBucket> = [
  "All",
  "Pricing",
  "Inventory / Listing Issue",
  "Missing Data",
];

export default function RepricingPage() {
  const [data, setData] = useState<AdvisorData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tier, setTier] = useState<(typeof TIERS)[number]>("All");
  const [ageBucket, setAgeBucket] = useState<(typeof AGE_BUCKETS)[number]>("All");
  const [advisorBucket, setAdvisorBucket] = useState<(typeof BUCKETS)[number]>("All");
  const [missingOnly, setMissingOnly] = useState(false);
  const [issueOnly, setIssueOnly] = useState(false);
  const [keepaFilter, setKeepaFilter] = useState<"all" | "has" | "missing">("all");

  useEffect(() => {
    loadAdvisor();
  }, []);

  async function loadAdvisor() {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch("/api/amazon/repricing-advisor", {
        cache: "no-store",
      });
      if (!response.ok) {
        throw new Error(`Failed to load repricing advisor: ${response.status}`);
      }
      setData(await response.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load repricing advisor.");
    } finally {
      setLoading(false);
    }
  }

  const rows = useMemo(() => {
    return (data?.rows ?? []).filter((row) => {
      if (tier !== "All" && row.recommendation_tier !== tier) return false;
      if (advisorBucket !== "All" && row.advisor_bucket !== advisorBucket) return false;
      if (!inAgeBucket(row, ageBucket)) return false;
      if (missingOnly && row.recommendation_tier !== "Needs Data") return false;
      if (issueOnly && row.unsellable_quantity <= 0 && row.listing_issue_count <= 0) {
        return false;
      }
      if (keepaFilter === "has" && !row.has_keepa_data) return false;
      if (keepaFilter === "missing" && row.has_keepa_data) return false;
      return true;
    });
  }, [advisorBucket, ageBucket, data, issueOnly, keepaFilter, missingOnly, tier]);

  return (
    <main className="min-h-screen bg-slate-100 p-4 text-slate-900">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Aged Amazon Inventory</h1>
          <p className="text-sm text-slate-600">
            Manual repricing advisor for active Amazon FBA inventory
          </p>
        </div>
        <button
          onClick={loadAdvisor}
          className="inline-flex items-center gap-2 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium shadow-sm hover:bg-slate-50"
          type="button"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      {error ? (
        <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      ) : null}

      <section className="mb-4 grid gap-3 xl:grid-cols-6">
        <Metric label="Rows" value={formatNumber(data?.summary.total_rows)} loading={loading} />
        <Metric label="Units" value={formatNumber(data?.summary.total_units)} loading={loading} />
        <Metric
          label="Capital"
          value={formatMoney(data?.summary.total_estimated_capital_tied_up)}
          loading={loading}
        />
        <Metric
          label="90+ day capital"
          value={formatMoney(data?.summary.aged_capital_over_90_days)}
          loading={loading}
        />
        <Metric
          label="180+ day capital"
          value={formatMoney(data?.summary.aged_capital_over_180_days)}
          loading={loading}
        />
        <Metric
          label="Needs data"
          value={formatNumber(data?.summary.rows_needing_data)}
          loading={loading}
        />
      </section>

      <section className="mb-4 rounded-md border border-slate-200 bg-white p-3 shadow-sm">
        <div className="grid gap-3 lg:grid-cols-[180px_220px_160px_repeat(4,max-content)]">
          <label className="text-sm">
            <span className="mb-1 block text-xs font-medium uppercase text-slate-500">Tier</span>
            <select
              value={tier}
              onChange={(event) => setTier(event.target.value as typeof tier)}
              className="w-full rounded-md border border-slate-300 bg-white px-2 py-2"
            >
              {TIERS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-xs font-medium uppercase text-slate-500">Bucket</span>
            <select
              value={advisorBucket}
              onChange={(event) => setAdvisorBucket(event.target.value as typeof advisorBucket)}
              className="w-full rounded-md border border-slate-300 bg-white px-2 py-2"
            >
              {BUCKETS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-xs font-medium uppercase text-slate-500">Age</span>
            <select
              value={ageBucket}
              onChange={(event) => setAgeBucket(event.target.value as typeof ageBucket)}
              className="w-full rounded-md border border-slate-300 bg-white px-2 py-2"
            >
              {AGE_BUCKETS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>
          <Toggle checked={missingOnly} onChange={setMissingOnly} label="Missing data" />
          <Toggle checked={issueOnly} onChange={setIssueOnly} label="Issue only" />
          <label className="text-sm">
            <span className="mb-1 block text-xs font-medium uppercase text-slate-500">Keepa</span>
            <select
              value={keepaFilter}
              onChange={(event) => setKeepaFilter(event.target.value as typeof keepaFilter)}
              className="w-36 rounded-md border border-slate-300 bg-white px-2 py-2"
            >
              <option value="all">All</option>
              <option value="has">Has data</option>
              <option value="missing">No data</option>
            </select>
          </label>
          <div className="self-end text-sm text-slate-600">
            Showing {formatNumber(rows.length)} of {formatNumber(data?.rows.length ?? 0)}
          </div>
        </div>
      </section>

      <section className="overflow-hidden rounded-md border border-slate-200 bg-white shadow-sm">
        <div className="overflow-x-auto">
          <table className="min-w-[1420px] w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-3 py-2">ASIN / SKU</th>
                <th className="px-3 py-2">Title</th>
                <th className="px-3 py-2 text-right">Qty</th>
                <th className="px-3 py-2 text-right">Age</th>
                <th className="px-3 py-2">Pricing</th>
                <th className="px-3 py-2">Informed</th>
                <th className="px-3 py-2">Buy Box Status</th>
                <th className="px-3 py-2">Informed Note</th>
                <th className="px-3 py-2">Sales Rank</th>
                <th className="px-3 py-2">Recommendation</th>
                <th className="px-3 py-2">Reason</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td className="px-3 py-8 text-center text-slate-500" colSpan={11}>
                    Loading repricing advisor...
                  </td>
                </tr>
              ) : rows.length ? (
                rows.map((row) => (
                  <tr
                    key={`${row.seller_sku}-${row.asin}`}
                    className={`border-t border-slate-100 align-top ${rowTone(row)}`}
                  >
                    <td className="px-3 py-2">
                      <div className="font-medium text-blue-700">{row.asin ?? "--"}</div>
                      <div className="text-xs text-slate-500">{row.seller_sku}</div>
                    </td>
                    <td className="w-[340px] px-3 py-2">
                      <div className="line-clamp-2 font-medium leading-snug">{row.title}</div>
                      <div className="text-xs text-slate-500">{row.condition ?? "--"}</div>
                    </td>
                    <td className="px-3 py-2 text-right">
                      <div className="font-semibold">{formatNumber(row.total_quantity)}</div>
                      <div className="text-xs text-slate-500">
                        FBA {formatNumber(row.fba_sellable_quantity)} / In {formatNumber(row.inbound_quantity)}
                      </div>
                      <div className="text-xs text-slate-500">
                        {row.inventory_detail_status}
                      </div>
                    </td>
                    <td className="px-3 py-2 text-right">
                      <div className="font-semibold">{ageDisplay(row)}</div>
                      <div className="text-xs text-slate-500">{row.amazon_age_source}</div>
                    </td>
                    <td className="w-[220px] px-3 py-2">
                      <PriceLine label="Cost" value={formatMoney(row.cost_basis)} detail={row.cost_source ?? "--"} />
                      <PriceLine label="Current" value={formatMoney(row.current_list_price)} />
                      <PriceLine label="Buy Box" value={formatMoney(row.keepa_buy_box_price)} />
                      <PriceLine label="90 avg" value={formatMoney(row.keepa_buy_box_avg90)} />
                      <div className="mt-2 rounded border border-blue-200 bg-blue-50 px-2 py-1">
                        <div className="flex items-baseline justify-between gap-3">
                          <span className="text-xs font-semibold uppercase text-blue-700">Target</span>
                          <span className="font-semibold text-blue-950">
                            {formatMoney(row.recommended_target_price)}
                          </span>
                        </div>
                        <div className="mt-0.5 text-right text-xs text-blue-700">
                          {row.target_price_basis ?? "--"}
                        </div>
                      </div>
                      <div className="mt-2 flex items-center justify-between gap-3 border-t border-slate-200 pt-1 text-xs">
                        <span className="font-medium text-slate-500">Capital</span>
                        <span className="font-semibold text-slate-800">
                          {formatMoney(row.estimated_capital_tied_up)}
                        </span>
                      </div>
                    </td>
                    <td className="w-[180px] px-3 py-2">
                      <div>{row.informed_rule_name ?? "--"}</div>
                      <div className="text-xs text-slate-500">
                        {row.informed_repricing_enabled === null
                          ? "--"
                          : row.informed_repricing_enabled
                            ? "enabled"
                            : "disabled"}
                      </div>
                      <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
                        <span className="text-slate-500">Min</span>
                        <span className="text-right font-medium">{formatMoney(row.informed_min_price)}</span>
                        <span className="text-slate-500">Max</span>
                        <span className="text-right font-medium">{formatMoney(row.informed_max_price)}</span>
                        <span className="text-slate-500">Min gap</span>
                        <span className="text-right font-medium">
                          {formatPct(row.informed_min_price_gap_to_buy_box_pct)}
                        </span>
                      </div>
                    </td>
                    <td className="px-3 py-2">
                      <div>{row.informed_buy_box_status ?? "--"}</div>
                      <div className="text-xs text-slate-500">
                        {formatMoney(row.informed_buy_box_price)}
                      </div>
                    </td>
                    <td className="w-[240px] px-3 py-2 text-slate-600">
                      {row.informed_repricing_note}
                    </td>
                    <td className="w-[150px] px-3 py-2">
                      <div>{salesRankSignal(row)}</div>
                      <div className="text-xs text-slate-500">
                        30/90d sales {formatNumber(row.sales_shipped_last_30_days)} /{" "}
                        {formatNumber(row.sales_shipped_last_90_days)}
                      </div>
                    </td>
                    <td className="w-[220px] px-3 py-2">
                      <div className="font-medium">{row.recommended_manual_action}</div>
                      <div className="mt-1 text-xs text-slate-500">
                        {row.advisor_bucket} / {row.recommendation_tier}
                      </div>
                    </td>
                    <td className="w-[360px] px-3 py-2 text-slate-600">{row.reason}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td className="px-3 py-8 text-center text-slate-500" colSpan={11}>
                    No rows match the current filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}

function PriceLine({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="mb-1 flex items-baseline justify-between gap-3">
      <span className="text-xs font-medium text-slate-500">{label}</span>
      <span className="text-right font-medium text-slate-900">
        {value}
        {detail ? <span className="ml-1 text-xs font-normal text-slate-500">({detail})</span> : null}
      </span>
    </div>
  );
}

function Metric({ label, value, loading }: { label: string; value: string; loading: boolean }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-3 shadow-sm">
      <div className="text-xs font-medium uppercase text-slate-500">{label}</div>
      <div className="mt-1 text-xl font-semibold">{loading ? "--" : value}</div>
    </div>
  );
}

function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
}) {
  return (
    <label className="flex items-end gap-2 pb-2 text-sm">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="h-4 w-4 rounded border-slate-300"
      />
      {label}
    </label>
  );
}

function inAgeBucket(row: AdvisorRow, bucket: (typeof AGE_BUCKETS)[number]) {
  if (bucket === "All") return true;
  if (bucket === "Missing") return !row.amazon_age_bucket && row.inventory_age_days === null;
  if (row.amazon_age_bucket) return row.amazon_age_bucket === bucket;
  const age = row.inventory_age_days;
  if (age === null) return false;
  if (bucket === "0-90") return age <= 90;
  if (bucket === "91-180") return age >= 91 && age <= 180;
  if (bucket === "181-270") return age >= 181 && age <= 270;
  if (bucket === "271-365") return age >= 271 && age <= 365;
  return age >= 366;
}

function salesRankSignal(row: AdvisorRow) {
  const drops = row.keepa_sales_rank_drops30 ?? row.keepa_sales_rank_drops90;
  const window = row.keepa_sales_rank_drops30 !== null ? "30d" : "90d";
  const rank = row.keepa_sales_rank_current ?? row.keepa_sales_rank_avg90;
  if (drops !== null && drops !== undefined) return `${formatNumber(drops)} drops/${window}`;
  if (rank !== null && rank !== undefined) return `Rank ${formatNumber(rank)}`;
  return "--";
}

function ageDisplay(row: AdvisorRow) {
  if (row.amazon_age_bucket) return row.amazon_age_bucket;
  if (row.inventory_age_days !== null) return `${row.inventory_age_days}d`;
  return "--";
}

function rowTone(row: AdvisorRow) {
  if (row.advisor_bucket === "Inventory / Listing Issue") return "bg-red-50/35";
  if (row.advisor_bucket === "Missing Data") return "bg-slate-50";
  if (row.recommendation_tier === "Liquidate") return "bg-orange-50/40";
  if (row.recommendation_tier === "Reprice") return "bg-amber-50/35";
  return "";
}

function formatMoney(value?: number | null) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "--";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(value));
}

function formatNumber(value?: number | null) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "--";
  return new Intl.NumberFormat("en-US").format(Number(value));
}

function formatPct(value?: number | null) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "--";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(1)}%`;
}
