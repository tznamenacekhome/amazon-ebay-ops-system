"use client";

import { useEffect, useMemo, useState } from "react";
import { RefreshCw, X } from "lucide-react";
import { runOnDemandRefresh, type RefreshNotice } from "../syncRefresh";
import { DataFreshness } from "../DataFreshness";
import { mutationHeaders } from "../mutationHeaders";

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

type SalesVelocitySignal =
  | "Strong"
  | "Moving"
  | "Slow"
  | "No recent sales"
  | "Unknown";

type AmazonAgeBucket =
  | "0-90"
  | "91-180"
  | "181-270"
  | "271-365"
  | "365+";

type CompetitionOffer = {
  seller_id: string | null;
  seller_name: string | null;
  fulfillment: "FBA" | "MFN" | "Unknown";
  landed_price: number | null;
  item_price: number | null;
  shipping_price: number | null;
  stock_quantity: number | null;
  condition: string | null;
  is_buy_box_winner: boolean;
  is_my_offer: boolean;
  is_synthetic: boolean;
  is_amazon: boolean;
  is_prime: boolean | null;
  last_seen: string | null;
};

type CompetitionSummary = {
  source: "Keepa offers" | "Keepa summary" | "Missing";
  note: string;
  condition_filter: string | null;
  offer_count: number | null;
  fba_offer_count: number;
  mfn_offer_count: number;
  lowest_fba_price: number | null;
  lowest_mfn_price: number | null;
  buy_box_seller_id: string | null;
  buy_box_price: number | null;
  total_observed_stock: number | null;
};

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
  informed_sales_last_30_days: number | null;
  sales_velocity_source: "Informed" | "Amazon Inventory Planning" | "Missing";
  sales_velocity_signal: SalesVelocitySignal;
  informed_rule_name: string | null;
  informed_rule_id: string | null;
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
  competition_summary: CompetitionSummary;
  competition_offers: CompetitionOffer[];
  estimated_capital_tied_up: number | null;
  advisor_bucket: AdvisorBucket;
  recommended_target_price: number | null;
  target_price_basis: string | null;
  recommendation_tier: RecommendationTier;
  recommended_manual_action: string;
  reason: string;
  snoozed_until: string | null;
  is_snoozed: boolean;
};

type AdvisorData = {
  generated_at: string;
  summary: AdvisorSummary;
  rows: AdvisorRow[];
};

type AdvisorSummary = {
  total_rows: number;
  total_units: number;
  total_estimated_capital_tied_up: number;
  aged_capital_over_90_days: number;
  aged_capital_over_180_days: number;
  rows_needing_data: number;
  unsellable_or_suppressed_rows: number;
  snoozed_rows: number;
  not_snoozed_rows: number;
  snoozed_estimated_capital_tied_up: number;
  not_snoozed_estimated_capital_tied_up: number;
  by_tier: Record<RecommendationTier, number>;
  by_bucket: Record<AdvisorBucket, number>;
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
  const [snoozeFilter, setSnoozeFilter] = useState<"not_snoozed" | "all">("not_snoozed");
  const [competitionRow, setCompetitionRow] = useState<AdvisorRow | null>(null);
  const [snoozingSku, setSnoozingSku] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshNotice, setRefreshNotice] = useState<RefreshNotice | null>(null);
  const [freshnessKey, setFreshnessKey] = useState(0);

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

  async function refreshAdvisor() {
    setRefreshing(true);
    setError(null);
    try {
      await runOnDemandRefresh("repricing", loadAdvisor, setRefreshNotice);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Refresh failed.");
    } finally {
      setRefreshing(false);
      setFreshnessKey((current) => current + 1);
    }
  }

  async function snoozeRow(row: AdvisorRow) {
    setSnoozingSku(row.seller_sku);
    setError(null);

    try {
      const response = await fetch("/api/amazon/repricing-advisor", {
        method: "POST",
        headers: mutationHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          seller_sku: row.seller_sku,
          asin: row.asin,
          snooze_days: 30,
        }),
      });
      if (!response.ok) {
        throw new Error(`Failed to snooze row: ${response.status}`);
      }
      const result = await response.json();
      const snoozedUntil = result?.snooze?.snoozed_until ?? new Date(Date.now() + 30 * 86_400_000).toISOString();
      setData((current) => {
        if (!current) return current;
        const updatedRows = current.rows.map((existingRow) =>
          existingRow.seller_sku === row.seller_sku
            ? {
                ...existingRow,
                is_snoozed: true,
                snoozed_until: snoozedUntil,
              }
            : existingRow
        );
        return {
          ...current,
          summary: summarizeAdvisorRows(updatedRows),
          rows: updatedRows,
        };
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to snooze row.");
    } finally {
      setSnoozingSku(null);
    }
  }

  const rows = useMemo(() => {
    return (data?.rows ?? []).filter((row) => {
      if (tier !== "All" && row.recommendation_tier !== tier) return false;
      if (snoozeFilter === "not_snoozed" && row.is_snoozed) return false;
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
  }, [advisorBucket, ageBucket, data, issueOnly, keepaFilter, missingOnly, snoozeFilter, tier]);

  return (
    <main className="min-h-screen bg-slate-100 p-4 text-slate-900">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Aged Amazon Inventory</h1>
          <p className="text-sm text-slate-600">
            Manual repricing advisor for active Amazon FBA inventory
          </p>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-3">
          <DataFreshness screen="repricing" refreshKey={freshnessKey} />
          <button
            onClick={refreshAdvisor}
            disabled={refreshing}
            className="inline-flex items-center gap-2 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium shadow-sm hover:bg-slate-50"
            type="button"
          >
            <RefreshCw className={`h-4 w-4 ${loading || refreshing ? "animate-spin" : ""}`} />
            {refreshing ? "Refreshing" : "Refresh"}
          </button>
        </div>
      </div>

      {refreshNotice ? (
        <div className={`mb-4 rounded-md border px-3 py-2 text-sm ${noticeClass(refreshNotice.tone)}`}>
          {refreshNotice.text}
        </div>
      ) : null}

      {error ? (
        <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      ) : null}

      <section className="mb-4 grid gap-3 xl:grid-cols-6">
        <Metric
          label="Not snoozed"
          value={formatNumber(data?.summary.not_snoozed_rows)}
          loading={loading}
        />
        <Metric
          label="Snoozed"
          value={formatNumber(data?.summary.snoozed_rows)}
          loading={loading}
        />
        <Metric
          label="Active capital"
          value={formatMoney(data?.summary.not_snoozed_estimated_capital_tied_up)}
          loading={loading}
        />
        <Metric
          label="Snoozed capital"
          value={formatMoney(data?.summary.snoozed_estimated_capital_tied_up)}
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
        <div className="grid gap-3 lg:grid-cols-[180px_180px_220px_160px_repeat(4,max-content)]">
          <label className="text-sm">
            <span className="mb-1 block text-xs font-medium uppercase text-slate-500">Snooze</span>
            <select
              value={snoozeFilter}
              onChange={(event) => setSnoozeFilter(event.target.value as typeof snoozeFilter)}
              className="w-full rounded-md border border-slate-300 bg-white px-2 py-2"
            >
              <option value="not_snoozed">Not Snoozed</option>
              <option value="all">All</option>
            </select>
          </label>
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
          <table className="min-w-[1500px] w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-3 py-2">ASIN / SKU</th>
                <th className="px-3 py-2">Title</th>
                <th className="px-3 py-2 text-right">Qty</th>
                <th className="px-3 py-2 text-right">Age</th>
                <th className="px-3 py-2 text-right">Capital</th>
                <th className="px-3 py-2">Pricing</th>
                <th className="px-3 py-2">Informed</th>
                <th className="px-3 py-2">Buy Box Status</th>
                <th className="px-3 py-2">Informed Note</th>
                <th className="px-3 py-2">Sales</th>
                <th className="px-3 py-2">Recommendation</th>
                <th className="px-3 py-2">Reason</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td className="px-3 py-8 text-center text-slate-500" colSpan={12}>
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
                      {row.asin ? (
                        <a
                          href={informedListingUrl(row.asin)}
                          target="_blank"
                          rel="noreferrer"
                          className="font-medium text-blue-700 hover:text-blue-900 hover:underline"
                        >
                          {row.asin}
                        </a>
                      ) : (
                        <div className="font-medium text-slate-500">--</div>
                      )}
                      <div className="text-xs text-slate-500">{row.seller_sku}</div>
                      <button
                        type="button"
                        onClick={() => setCompetitionRow(row)}
                        className="mt-2 rounded border border-slate-300 bg-white px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
                      >
                        Competition
                      </button>
                      <button
                        type="button"
                        onClick={() => snoozeRow(row)}
                        disabled={snoozingSku === row.seller_sku}
                        className="mt-2 ml-2 rounded border border-slate-300 bg-white px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {snoozingSku === row.seller_sku ? "Snoozing..." : "Snooze"}
                      </button>
                      {row.is_snoozed ? (
                        <div className="mt-2 text-xs font-medium text-slate-500">
                          Snoozed until {formatDate(row.snoozed_until)}
                        </div>
                      ) : null}
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
                    <td className="px-3 py-2 text-right">
                      <div className="font-semibold text-slate-950">
                        {formatMoney(row.estimated_capital_tied_up)}
                      </div>
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
                    </td>
                    <td className="w-[180px] px-3 py-2">
                      <div>{row.informed_rule_name ?? "--"}</div>
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
                      <div className="font-medium">{row.sales_velocity_signal}</div>
                      <div className="text-xs text-slate-500">{salesRankSignal(row)}</div>
                      <div className="text-xs text-slate-500">
                        Informed 30d sales {formatNumber(row.informed_sales_last_30_days)}
                      </div>
                      <div className="text-xs text-slate-500">
                        Source: {row.sales_velocity_source}
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
                  <td className="px-3 py-8 text-center text-slate-500" colSpan={12}>
                    No rows match the current filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
      {competitionRow ? (
        <CompetitionDrawer row={competitionRow} onClose={() => setCompetitionRow(null)} />
      ) : null}
    </main>
  );
}

function CompetitionDrawer({
  row,
  onClose,
}: {
  row: AdvisorRow;
  onClose: () => void;
}) {
  const summary = row.competition_summary;

  return (
    <div className="fixed inset-0 z-40" role="dialog" aria-modal="true">
      <button
        type="button"
        className="absolute inset-0 bg-slate-950/25"
        onClick={onClose}
        aria-label="Close competition drawer overlay"
      />
      <aside className="absolute right-0 top-0 flex h-full w-full max-w-5xl flex-col bg-white shadow-xl">
        <div className="border-b border-slate-200 p-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Competition
              </div>
              <h2 className="mt-1 text-xl font-semibold text-slate-950">{row.asin ?? "--"}</h2>
              <p className="mt-1 max-w-3xl text-sm text-slate-600">{row.title}</p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-slate-300 p-2 text-slate-600 hover:bg-slate-50"
              aria-label="Close competition drawer"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-4">
            <DrawerMetric label="Source" value={summary.source} />
            <DrawerMetric label="Offers" value={formatNumber(summary.offer_count)} />
            <DrawerMetric label="Condition" value={summary.condition_filter ?? "--"} />
            <DrawerMetric
              label="Lowest FBA / MFN"
              value={`${formatMoney(summary.lowest_fba_price)} / ${formatMoney(summary.lowest_mfn_price)}`}
            />
            <DrawerMetric label="Observed Stock" value={formatNumber(summary.total_observed_stock)} />
          </div>
          <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
            {summary.note}
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-auto p-4">
          <div className="mb-3 grid gap-3 text-sm md:grid-cols-4">
            <InfoPair label="Buy Box" value={formatMoney(summary.buy_box_price)} />
            <InfoPair label="Buy Box Seller" value={summary.buy_box_seller_id ?? "--"} />
            <InfoPair label="FBA Offers" value={formatNumber(summary.fba_offer_count)} />
            <InfoPair label="MFN Offers" value={formatNumber(summary.mfn_offer_count)} />
          </div>

          <div className="overflow-hidden rounded-md border border-slate-200">
            <table className="w-full min-w-[900px] text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-3 py-2">Seller</th>
                  <th className="px-3 py-2">Fulfillment</th>
                  <th className="px-3 py-2 text-right">Landed</th>
                  <th className="px-3 py-2 text-right">Item / Ship</th>
                  <th className="px-3 py-2 text-right">Stock</th>
                  <th className="px-3 py-2">Condition</th>
                  <th className="px-3 py-2">Signals</th>
                  <th className="px-3 py-2">Last Seen</th>
                </tr>
              </thead>
              <tbody>
                {row.competition_offers.length ? (
                  row.competition_offers.map((offer, index) => (
                    <tr
                      key={`${offer.seller_id ?? "seller"}-${index}`}
                      className={`border-t align-top ${
                        offer.is_my_offer
                          ? "border-blue-200 bg-blue-50/70"
                          : "border-slate-100"
                      }`}
                    >
                      <td className="px-3 py-2">
                        <div className="font-medium">{offer.seller_name ?? offer.seller_id ?? "--"}</div>
                        {offer.seller_name && offer.seller_id ? (
                          <div className="text-xs text-slate-500">{offer.seller_id}</div>
                        ) : null}
                      </td>
                      <td className="px-3 py-2">
                        <FulfillmentPill fulfillment={offer.fulfillment} />
                      </td>
                      <td className="px-3 py-2 text-right font-medium">
                        {formatMoney(offer.landed_price)}
                      </td>
                      <td className="px-3 py-2 text-right text-xs text-slate-600">
                        {formatMoney(offer.item_price)} / {formatMoney(offer.shipping_price)}
                      </td>
                      <td className="px-3 py-2 text-right">{formatNumber(offer.stock_quantity)}</td>
                      <td className="px-3 py-2">{offer.condition ?? "--"}</td>
                      <td className="px-3 py-2">
                        <div className="flex flex-wrap gap-1">
                          {offer.is_buy_box_winner ? <Pill label="Buy Box" tone="green" /> : null}
                          {offer.is_my_offer ? <Pill label="You" tone="blue" /> : null}
                          {offer.is_synthetic ? <Pill label="MBOP" tone="slate" /> : null}
                          {offer.is_amazon ? <Pill label="Amazon" tone="blue" /> : null}
                          {offer.is_prime ? <Pill label="Prime" tone="slate" /> : null}
                        </div>
                      </td>
                      <td className="px-3 py-2 text-slate-600">{formatDateTime(offer.last_seen)}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td className="px-3 py-8 text-center text-slate-500" colSpan={8}>
                      No offer-level competition rows are stored for this ASIN yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </aside>
    </div>
  );
}

function DrawerMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2">
      <div className="text-xs font-medium uppercase text-slate-500">{label}</div>
      <div className="mt-1 font-semibold text-slate-950">{value}</div>
    </div>
  );
}

function InfoPair({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="text-xs font-medium uppercase text-slate-500">{label}</span>
      <div className="font-semibold text-slate-950">{value}</div>
    </div>
  );
}

function Pill({ label, tone }: { label: string; tone: "green" | "blue" | "slate" }) {
  const toneClass =
    tone === "green"
      ? "border-green-200 bg-green-50 text-green-700"
      : tone === "blue"
        ? "border-blue-200 bg-blue-50 text-blue-700"
        : "border-slate-200 bg-slate-50 text-slate-700";
  return <span className={`rounded border px-1.5 py-0.5 text-xs ${toneClass}`}>{label}</span>;
}

function FulfillmentPill({ fulfillment }: { fulfillment: CompetitionOffer["fulfillment"] }) {
  const toneClass =
    fulfillment === "FBA"
      ? "border-indigo-200 bg-indigo-50 text-indigo-700"
      : fulfillment === "MFN"
        ? "border-amber-200 bg-amber-50 text-amber-800"
        : "border-slate-200 bg-slate-50 text-slate-700";
  return (
    <span className={`inline-flex rounded border px-2 py-0.5 text-xs font-semibold ${toneClass}`}>
      {fulfillment}
    </span>
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

function summarizeAdvisorRows(rows: AdvisorRow[]): AdvisorSummary {
  const byTier = Object.fromEntries(
    TIERS.filter((tier): tier is RecommendationTier => tier !== "All").map((tier) => [tier, 0])
  ) as Record<RecommendationTier, number>;
  const byBucket = {
    Pricing: 0,
    "Inventory / Listing Issue": 0,
    "Missing Data": 0,
  } as Record<AdvisorBucket, number>;

  let totalCapital = 0;
  let snoozedCapital = 0;
  let notSnoozedCapital = 0;
  let agedCapital90 = 0;
  let agedCapital180 = 0;
  let rowsNeedingData = 0;
  let unsellableOrSuppressedRows = 0;
  let snoozedRows = 0;

  for (const row of rows) {
    byTier[row.recommendation_tier] += 1;
    byBucket[row.advisor_bucket] += 1;

    const capital = row.estimated_capital_tied_up ?? 0;
    const costBasis = row.cost_basis ?? 0;
    const aged90Units =
      row.inv_age_91_to_180_days +
      row.inv_age_181_to_270_days +
      row.inv_age_271_to_365_days +
      row.inv_age_365_plus_days;
    const aged180Units =
      row.inv_age_181_to_270_days + row.inv_age_271_to_365_days + row.inv_age_365_plus_days;

    totalCapital += capital;
    if (row.is_snoozed) {
      snoozedRows += 1;
      snoozedCapital += capital;
    } else {
      notSnoozedCapital += capital;
    }

    if (row.amazon_age_bucket) {
      agedCapital90 += costBasis * aged90Units;
      agedCapital180 += costBasis * aged180Units;
    } else {
      if ((row.inventory_age_days ?? 0) >= 90) agedCapital90 += capital;
      if ((row.inventory_age_days ?? 0) >= 180) agedCapital180 += capital;
    }

    if (row.recommendation_tier === "Needs Data") rowsNeedingData += 1;
    if (row.unsellable_quantity > 0 || row.listing_issue_count > 0) {
      unsellableOrSuppressedRows += 1;
    }
  }

  return {
    total_rows: rows.length,
    total_units: rows.reduce((total, row) => total + row.total_quantity, 0),
    total_estimated_capital_tied_up: roundMoney(totalCapital),
    aged_capital_over_90_days: roundMoney(agedCapital90),
    aged_capital_over_180_days: roundMoney(agedCapital180),
    rows_needing_data: rowsNeedingData,
    unsellable_or_suppressed_rows: unsellableOrSuppressedRows,
    snoozed_rows: snoozedRows,
    not_snoozed_rows: rows.length - snoozedRows,
    snoozed_estimated_capital_tied_up: roundMoney(snoozedCapital),
    not_snoozed_estimated_capital_tied_up: roundMoney(notSnoozedCapital),
    by_tier: byTier,
    by_bucket: byBucket,
  };
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

function roundMoney(value: number) {
  return Math.round(value * 100) / 100;
}

function noticeClass(tone: RefreshNotice["tone"]) {
  if (tone === "success") return "border-green-200 bg-green-50 text-green-700";
  if (tone === "warning") return "border-amber-200 bg-amber-50 text-amber-800";
  return "border-blue-200 bg-blue-50 text-blue-700";
}

function formatDateTime(value?: string | null) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function informedListingUrl(asin: string) {
  const filter = encodeURIComponent(
    JSON.stringify({
      SearchTerm: asin,
      Deleted: null,
    })
  );
  const search = encodeURIComponent(asin);
  return `https://app.informedrepricer.com/r/listings?filter=${filter}&search=${search}&view=all_listings`;
}

function formatDate(value?: string | null) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(date);
}
