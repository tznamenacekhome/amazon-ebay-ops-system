"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { RefreshCw, X } from "lucide-react";
import { runOnDemandRefresh, type RefreshNotice } from "../syncRefresh";
import {
  CompactStatusTable,
  DashboardSection,
  DashboardTabs,
  DrilldownLink,
  FreshnessBadge,
  MetricCard,
  MetricGrid,
  type DashboardView,
} from "./components";

type OverviewData = {
  refreshedAt: string | null;
  metrics: {
    preAmazonInventoryValue: number | null;
  };
  attention: Array<{
    label: string;
    value: number | null;
    detail: string;
    severity: "green" | "yellow" | "red" | "unknown";
    href: string;
  }>;
  warnings?: string[];
};

type OperationsData = {
  refreshedAt: string | null;
  receiving: {
    deliveredNotReceived: number;
    deliveredNotReceivedUnits: number;
    shippedWithNoTracking: number;
    arrivingToday: number;
    arrivingThisWeek: number;
    oldestDeliveredNotReceivedDays: number | null;
    href: string;
  };
  fbaPrep: {
    readyRows: number;
    readyUnits: number;
    distinctAsins: number;
    estimatedCostReady: number;
    blockedRows: number;
    blockedUnits: number;
    oldestReceivedNotListedDays: number | null;
    href: string;
  };
  purchaseCleanup: {
    missingAsin: number;
    missingSellPrice: number;
    missingAmazonTitle: number;
    missingSystem: number;
    href: string;
  };
  orderProblems: {
    lateDeliveryCandidates: number;
    staleTrackingCandidates: number;
    carrierExceptions: number;
    returnPending: number;
    returnOpened: number;
    refundPending: number;
    replacementFollowUp: number;
    href: string;
  };
  workflowAging: {
    purchaseToDelivered: AgingBucket[];
    deliveredToReceived: AgingBucket[];
    receivedToListed: AgingBucket[];
  };
  attentionRows: Array<{
    itemId: string | null;
    orderId: string | null;
    title: string;
    status: string;
    issue: string;
    ageDays: number | null;
  }>;
};

type AgingBucket = {
  label: string;
  rows: number;
  units: number;
};

// Dashboard tabs intentionally render different API-provided JSON shapes.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type DashboardPayload = Record<string, any>;

const implementedViews = new Set<DashboardView>([
  "overview",
  "operations",
  "inventory",
  "amazon",
  "sourcing",
  "loss-prevention",
  "system-health",
]);
const allViews = new Set<DashboardView>([
  "overview",
  "operations",
  "inventory",
  "amazon",
  "sourcing",
  "loss-prevention",
  "system-health",
]);

export default function DashboardPage() {
  return (
    <Suspense fallback={<DashboardShellFallback />}>
      <DashboardClient />
    </Suspense>
  );
}

function DashboardClient() {
  const searchParams = useSearchParams();
  const view = normalizeView(searchParams.get("view"));
  const [overviewData, setOverviewData] = useState<OverviewData | null>(null);
  const [operationsData, setOperationsData] = useState<OperationsData | null>(null);
  const [dashboardData, setDashboardData] = useState<Record<string, DashboardPayload>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshNotice, setRefreshNotice] = useState<RefreshNotice | null>(null);

  useEffect(() => {
    if (!implementedViews.has(view)) return;
    void loadView(view);
  }, [view]);

  const refreshedAt = useMemo(() => {
    if (view === "overview") return overviewData?.refreshedAt ?? null;
    if (view === "operations") return operationsData?.refreshedAt ?? null;
    return dashboardData[view]?.refreshedAt ?? null;
  }, [dashboardData, operationsData?.refreshedAt, overviewData?.refreshedAt, view]);

  async function loadView(nextView: DashboardView) {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/dashboard/${nextView}`, { cache: "no-store" });
      if (!response.ok) throw new Error(`Failed to load ${nextView}: ${response.status}`);
      const payload = await response.json();
      if (nextView === "overview") setOverviewData(payload);
      else if (nextView === "operations") setOperationsData(payload);
      else setDashboardData((current) => ({ ...current, [nextView]: payload }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard.");
    } finally {
      setLoading(false);
    }
  }

  async function refreshDashboard() {
    setRefreshing(true);
    setError(null);
    try {
      await runOnDemandRefresh("dashboard", () => implementedViews.has(view) ? loadView(view) : Promise.resolve(), setRefreshNotice);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Refresh failed.");
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <main className="min-h-screen bg-slate-100 p-4 text-slate-900">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
          <p className="text-sm text-slate-600">Focused MBOP monitoring views with drill-downs to the work queues.</p>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <FreshnessBadge refreshedAt={refreshedAt} />
          <button
            onClick={refreshDashboard}
            disabled={refreshing}
            className="inline-flex items-center gap-2 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
            type="button"
          >
            <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
            {refreshing ? "Refreshing" : "Refresh"}
          </button>
        </div>
      </div>

      <div className="mb-4">
        <DashboardTabs activeView={view} />
      </div>

      {refreshNotice ? (
        <div className={`mb-4 rounded-md border px-3 py-2 text-sm ${noticeClass(refreshNotice.tone)}`}>
          {refreshNotice.text}
        </div>
      ) : null}

      {error ? (
        <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      ) : null}

      {view === "overview" ? <OverviewPanel data={overviewData} loading={loading} /> : null}
      {view === "operations" ? <OperationsPanel data={operationsData} loading={loading} /> : null}
      {view === "inventory" ? <InventoryPanel data={dashboardData.inventory} loading={loading} /> : null}
      {view === "amazon" ? <AmazonPanel data={dashboardData.amazon} loading={loading} /> : null}
      {view === "sourcing" ? <SourcingPanel data={dashboardData.sourcing} loading={loading} /> : null}
      {view === "loss-prevention" ? <LossPreventionPanel data={dashboardData["loss-prevention"]} loading={loading} /> : null}
      {view === "system-health" ? <SystemHealthPanel data={dashboardData["system-health"]} loading={loading} /> : null}
      {!implementedViews.has(view) ? <StagedPanel view={view} /> : null}
    </main>
  );
}

function OverviewPanel({ data, loading }: { data: OverviewData | null; loading: boolean }) {
  return (
    <div className="space-y-4">
      <DashboardSection title="Inventory Snapshot" eyebrow="Overview">
        <MetricGrid>
          <MetricCard label="Pre-Amazon Inventory" value={loading ? "--" : formatMoney(data?.metrics.preAmazonInventoryValue)} href="/dashboard?view=inventory" />
        </MetricGrid>
      </DashboardSection>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
        <DashboardSection title="Current Attention Summary" eyebrow="One-minute check">
          <CompactStatusTable
            columns={["Area", "Count", "Severity", "Drill-down"]}
            rows={(data?.attention ?? []).map((row) => ({
              id: row.label,
              href: row.href,
              cells: [
                <div key="area">
                  <div className="font-medium">{row.label}</div>
                  <div className="text-xs text-slate-500">{row.detail}</div>
                </div>,
                formatNumber(row.value),
                <SeverityPill key="severity" severity={row.severity} />,
                <span key="link" className="text-blue-700">Open</span>,
              ],
            }))}
            emptyText={loading ? "Loading attention summary..." : "No attention rows."}
          />
        </DashboardSection>

        <OperationsQuickLinks />
      </div>

      {data?.warnings?.length ? (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
          {data.warnings.join(" ")}
        </div>
      ) : null}
    </div>
  );
}

function OperationsQuickLinks() {
  return (
    <DashboardSection title="Operational Dashboards" eyebrow="Drill-downs">
      <CompactStatusTable
        columns={["Area", "Purpose"]}
        rows={[
          { id: "operations", href: "/dashboard?view=operations", cells: ["Operations", "Receiving, FBA prep, purchase cleanup, and workflow aging"] },
          { id: "inventory", href: "/dashboard?view=inventory", cells: ["Inventory", "Inventory value by state, capital at risk, and reconciliation"] },
          { id: "amazon", href: "/dashboard?view=amazon", cells: ["Amazon", "Seller account, listing health, FBA inventory, and repricing signals"] },
          { id: "sourcing", href: "/dashboard?view=sourcing", cells: ["Sourcing", "Replenishment research and sourcing candidates"] },
        ]}
      />
    </DashboardSection>
  );
}

function OperationsPanel({ data, loading }: { data: OperationsData | null; loading: boolean }) {
  return (
    <div className="space-y-4">
      <MetricGrid>
        <MetricCard
          label="Delivered Not Received"
          value={loading ? "--" : formatNumber(data?.receiving.deliveredNotReceivedUnits)}
          detail={`${formatNumber(data?.receiving.deliveredNotReceived)} row(s), oldest ${formatDays(data?.receiving.oldestDeliveredNotReceivedDays)}`}
          href="/receiving"
          tone={toneFor(data?.receiving.deliveredNotReceivedUnits ?? 0, 0, 10)}
        />
        <MetricCard
          label="Arriving Today"
          value={loading ? "--" : formatNumber(data?.receiving.arrivingToday)}
          detail={`${formatNumber(data?.receiving.arrivingThisWeek)} arriving this week`}
          href="/receiving"
        />
        <MetricCard
          label="FBA Ready Units"
          value={loading ? "--" : formatNumber(data?.fbaPrep.readyUnits)}
          detail={`${formatNumber(data?.fbaPrep.distinctAsins)} ASINs, ${formatMoney(data?.fbaPrep.estimatedCostReady)} cost`}
          href="/fba"
          tone={toneFor(data?.fbaPrep.readyUnits ?? 0, 0, 40)}
        />
        <MetricCard
          label="FBA Blocked Rows"
          value={loading ? "--" : formatNumber(data?.fbaPrep.blockedRows)}
          detail={`${formatNumber(data?.fbaPrep.blockedUnits)} unit(s) missing required FBA data`}
          href="/fba"
          tone={toneFor(data?.fbaPrep.blockedRows ?? 0, 0, 8)}
        />
        <MetricCard
          label="Purchase Cleanup"
          value={loading ? "--" : formatNumber(cleanupTotal(data))}
          detail="ASIN, sell price, Amazon title, or system missing"
          href="/?tab=missing-data"
          tone={toneFor(cleanupTotal(data), 0, 25)}
        />
        <MetricCard
          label="Order Problems"
          value={loading ? "--" : formatNumber(orderProblemTotal(data))}
          detail="Candidates, returns, refunds, and replacement follow-up"
          href="/?tab=order-problems"
          tone={toneFor(orderProblemTotal(data), 0, 8)}
        />
      </MetricGrid>

      <div className="grid gap-4 xl:grid-cols-2">
        <DashboardSection title="Purchase Cleanup" eyebrow="Missing data" action={<DrilldownLink href="/?tab=missing-data">Open Purchases</DrilldownLink>}>
          <CompactStatusTable
            columns={["Issue", "Rows"]}
            rows={[
              { id: "asin", cells: ["Missing ASIN", formatNumber(data?.purchaseCleanup.missingAsin)] },
              { id: "sell-price", cells: ["Missing Sell Price", formatNumber(data?.purchaseCleanup.missingSellPrice)] },
              { id: "amazon-title", cells: ["Missing Amazon Title", formatNumber(data?.purchaseCleanup.missingAmazonTitle)] },
              { id: "system", cells: ["Missing System", formatNumber(data?.purchaseCleanup.missingSystem)] },
            ]}
          />
        </DashboardSection>

        <DashboardSection title="Order Problems" eyebrow="Work queue summary" action={<DrilldownLink href="/?tab=order-problems">Open Problems</DrilldownLink>}>
          <CompactStatusTable
            columns={["Bucket", "Open"]}
            rows={[
              { id: "late", cells: ["Late Delivery Candidates", formatNumber(data?.orderProblems.lateDeliveryCandidates)] },
              { id: "stale", cells: ["Stale / No Tracking", formatNumber(data?.orderProblems.staleTrackingCandidates)] },
              { id: "carrier", cells: ["Carrier Exceptions", formatNumber(data?.orderProblems.carrierExceptions)] },
              { id: "return-pending", cells: ["Return Pending", formatNumber(data?.orderProblems.returnPending)] },
              { id: "return-opened", cells: ["Return Opened", formatNumber(data?.orderProblems.returnOpened)] },
              { id: "refund", cells: ["Refund Pending", formatNumber(data?.orderProblems.refundPending)] },
              { id: "replacement", cells: ["Missing Item / Replacement", formatNumber(data?.orderProblems.replacementFollowUp)] },
            ]}
          />
        </DashboardSection>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <DashboardSection title="Workflow Aging" eyebrow="Bottlenecks">
          <div className="grid gap-3 md:grid-cols-3">
            <AgingTable title="Purchase to Delivered" rows={data?.workflowAging.purchaseToDelivered ?? []} />
            <AgingTable title="Delivered to Received" rows={data?.workflowAging.deliveredToReceived ?? []} />
            <AgingTable title="Received to Listed" rows={data?.workflowAging.receivedToListed ?? []} />
          </div>
        </DashboardSection>

        <DashboardSection title="Oldest Attention Rows" eyebrow="Top 10">
          <CompactStatusTable
            columns={["Issue", "Order", "Title", "Age"]}
            rows={(data?.attentionRows ?? []).map((row, index) => ({
              id: `${row.itemId ?? row.orderId ?? "row"}-${index}`,
              href: "/",
              cells: [
                row.issue,
                row.orderId || "--",
                <span key="title" className="block max-w-[360px] truncate">{row.title}</span>,
                formatDays(row.ageDays),
              ],
            }))}
            emptyText={loading ? "Loading attention rows..." : "No attention rows."}
          />
        </DashboardSection>
      </div>
    </div>
  );
}

function AgingTable({ title, rows }: { title: string; rows: AgingBucket[] }) {
  return (
    <div>
      <div className="mb-1 text-sm font-semibold">{title}</div>
      <CompactStatusTable
        columns={["Age", "Rows", "Units"]}
        rows={rows.map((row) => ({
          id: `${title}-${row.label}`,
          cells: [row.label, formatNumber(row.rows), formatNumber(row.units)],
        }))}
      />
    </div>
  );
}

function InventoryPanel({ data, loading }: { data: DashboardPayload | null; loading: boolean }) {
  return (
    <div className="space-y-4">
      <MetricGrid>
        <MetricCard label="Total Inventory Value" value={loading ? "--" : formatMoney(data?.summary?.totalInventoryValue)} />
        <MetricCard label="Total Units" value={loading ? "--" : formatNumber(data?.summary?.totalUnits)} />
        <MetricCard label="Amazon FBA Sellable" value={loading ? "--" : formatNumber(data?.summary?.amazonFbaSellableUnits)} detail={formatMoney(data?.summary?.amazonFbaValue)} href="/inventory-reconciliation" />
        <MetricCard label="Outbound To Amazon" value={loading ? "--" : formatNumber(data?.summary?.outboundToAmazonUnits)} detail={formatMoney(data?.summary?.outboundToAmazonValue)} href="/fba" />
        <MetricCard label="Received / Ready" value={loading ? "--" : formatNumber(data?.summary?.receivedUnits)} detail={formatMoney(data?.summary?.receivedValue)} href="/fba" />
        <MetricCard label="Ordered Not Received" value={loading ? "--" : formatNumber(data?.summary?.orderedNotReceivedUnits)} detail={formatMoney(data?.summary?.orderedNotReceivedValue)} href="/" />
      </MetricGrid>
      <div className="grid gap-4 xl:grid-cols-2">
        <DashboardSection title="Inventory Value By Location" eyebrow="Capital location">
          <CompactStatusTable
            columns={["Location", "Units", "Value", "%", "Action"]}
            rows={asRows(data?.byLocation).map((row) => ({
              id: row.locationKey,
              href: row.drilldownUrl,
              cells: [row.label, formatNumber(row.units), formatMoney(row.value), formatPercent(row.percentOfTotal / 100), "Open"],
            }))}
            emptyText={loading ? "Loading inventory locations..." : "No inventory locations."}
          />
        </DashboardSection>
        <DashboardSection title="Inventory Age Buckets" eyebrow="Aging">
          <CompactStatusTable
            columns={["Age", "Units", "Value", "%"]}
            rows={asRows(data?.ageBuckets).map((row) => ({
              id: row.bucket,
              href: row.drilldownUrl,
              cells: [row.bucket, formatNumber(row.units), formatMoney(row.value), formatPercent(row.percentOfValue / 100)],
            }))}
          />
        </DashboardSection>
      </div>
      <div className="grid gap-4 xl:grid-cols-[0.8fr_1.2fr]">
        <DashboardSection title="Capital At Risk" eyebrow="Aged/unknown value">
          <MetricGrid>
            <MetricCard label="Over 90 Days" value={formatMoney(data?.capitalAtRisk?.over90DaysValue)} href="/repricing" tone={toneFor(data?.capitalAtRisk?.over90DaysValue ?? 0, 1, 1000)} />
            <MetricCard label="Over 180 Days" value={formatMoney(data?.capitalAtRisk?.over180DaysValue)} href="/repricing" tone={toneFor(data?.capitalAtRisk?.over180DaysValue ?? 0, 1, 500)} />
            <MetricCard label="365+ Days" value={formatMoney(data?.capitalAtRisk?.over365DaysValue)} href="/repricing" tone={toneFor(data?.capitalAtRisk?.over365DaysValue ?? 0, 1, 250)} />
            <MetricCard label="Unknown Age" value={formatMoney(data?.capitalAtRisk?.unknownAgeValue)} href="/inventory-reconciliation" tone={toneFor(data?.capitalAtRisk?.unknownAgeValue ?? 0, 1, 250)} />
          </MetricGrid>
        </DashboardSection>
        <DashboardSection title="Inventory Attention" eyebrow="Top issues">
          <CompactStatusTable
            columns={["Severity", "Issue", "Count", "Value", "Reason"]}
            rows={asRows(data?.attention).map((row) => ({
              id: row.label,
              href: row.drilldownUrl,
              cells: [row.severity, row.label, formatNumber(row.count), formatMoney(row.valueAtRisk), row.reason],
            }))}
          />
        </DashboardSection>
      </div>
      <DashboardSection title="Top Inventory Concentration" eyebrow="Top 10 by value">
        <CompactStatusTable
          columns={["ASIN", "Title", "System", "Units", "Value", "Location", "Action"]}
          rows={asRows(data?.concentration).map((row) => ({
            id: row.asin || row.sellerSku || row.title,
            href: row.drilldownUrl,
            cells: [row.asin || row.sellerSku || "--", <span key="title" className="block max-w-[420px] truncate">{row.title}</span>, row.system || "--", formatNumber(row.units), formatMoney(row.value), row.locationSummary, "Open"],
          }))}
        />
      </DashboardSection>
    </div>
  );
}

function AmazonPanel({ data, loading }: { data: DashboardPayload | null; loading: boolean }) {
  return (
    <div className="space-y-4">
      <MetricGrid>
        <MetricCard label="30-Day Units Sold" value={loading ? "--" : formatNumber(data?.salesSummary?.unitsSold30d)} />
        <MetricCard label="FBA Sellable Units" value={loading ? "--" : formatNumber(data?.inventorySummary?.sellableUnits)} />
        <MetricCard label="Listing Issues" value={loading ? "--" : formatNumber(data?.inventorySummary?.strandedOrSuppressedCount)} href="/inventory-reconciliation" tone={toneFor(data?.inventorySummary?.strandedOrSuppressedCount ?? 0, 0, 5)} />
        <MetricCard label="Repricing Capital" value={loading ? "--" : formatMoney(data?.repricingSummary?.pricingCapital)} href="/repricing" />
      </MetricGrid>
      <DashboardSection title="Seller Account Health" eyebrow="Seller Central">
        <MetricGrid>
          <MetricCard
            label="Account Health Rating"
            value={loading ? "--" : formatNumber(data?.sellerAccount?.accountHealthScore)}
            detail={`Updated ${formatDateOnly(data?.sellerAccount?.accountHealthUpdatedAt)}`}
            href={href(data?.sellerAccount?.accountHealthUrl) ?? undefined}
            external={Boolean(data?.sellerAccount?.accountHealthUrl)}
            tone={toneForAccountHealth(data?.sellerAccount?.accountHealthScore)}
          />
          <MetricCard
            label="Feedback Rating"
            value={loading ? "--" : `${formatDecimal(data?.sellerAccount?.feedbackStarRating, 1)} stars`}
            detail={`${formatNumber(data?.sellerAccount?.feedbackRatingCount)} ratings`}
            href={href(data?.sellerAccount?.feedbackUrl) ?? undefined}
            external={Boolean(data?.sellerAccount?.feedbackUrl)}
          />
          <MetricCard
            label="1-3 Star Feedback"
            value={loading ? "--" : formatNumber(data?.sellerAccount?.lowRatingFeedbackCount)}
            detail="Neutral/negative feedback imported from SP-API"
            href={href(data?.sellerAccount?.feedbackUrl) ?? undefined}
            external={Boolean(data?.sellerAccount?.feedbackUrl)}
            tone={toneForAlertCount(data?.sellerAccount?.lowRatingFeedbackCount)}
          />
        </MetricGrid>
        <div className="mt-3 grid gap-4 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
          <div>
            <h3 className="mb-2 text-sm font-semibold text-slate-900">Account Health Changes</h3>
            <CompactStatusTable
              columns={["Changed", "Score", "Change", "Notes"]}
              rows={asRows(data?.sellerAccount?.accountHealthChanges).map((row) => ({
                id: `${text(row.date)}-${text(row.value)}`,
                href: href(data?.sellerAccount?.accountHealthUrl),
                external: Boolean(data?.sellerAccount?.accountHealthUrl),
                cells: [
                  formatDateOnly(row.date),
                  formatNumber(row.value),
                  formatSignedNumber(row.change),
                  text(row.notes) || "--",
                ],
              }))}
              emptyText={loading ? "Loading account health history..." : "No account health history yet."}
            />
          </div>
          <div>
            <h3 className="mb-2 text-sm font-semibold text-slate-900">1-3 Star Feedback Alerts</h3>
            <CompactStatusTable
              columns={["Date", "Rating", "Order", "Comment"]}
              rows={asRows(data?.sellerAccount?.lowRatingFeedback).map((row) => ({
                id: `${text(row.feedback_date)}-${text(row.amazon_order_id)}-${text(row.comment)}`,
                href: href(data?.sellerAccount?.feedbackUrl),
                external: Boolean(data?.sellerAccount?.feedbackUrl),
                cells: [
                  formatDateOnly(row.feedback_date),
                  `${formatNumber(row.rating)} stars`,
                  text(row.amazon_order_id) || "--",
                  <span key="comment" className="block max-w-[460px] truncate">{text(row.comment) || "--"}</span>,
                ],
              }))}
              emptyText={loading ? "Loading feedback alerts..." : "No 1-3 star seller feedback captured."}
            />
          </div>
        </div>
      </DashboardSection>
      <DashboardSection title="Listing / Inventory Health" eyebrow="Issues">
        <CompactStatusTable columns={["Issue", "Count", "Units", "Value", "Action"]} rows={asRows(data?.listingHealth).map((row) => ({ id: text(row.issueType), href: href(row.drilldownUrl), cells: [text(row.issueType), formatNumber(row.count), formatNumber(row.units), formatMoney(row.value), "Open"] }))} />
      </DashboardSection>
      <DashboardSection title="Repricing Summary" eyebrow="Advisor rollup" action={<DrilldownLink href="/repricing">Open Repricing</DrilldownLink>}>
        <MetricGrid>
          <MetricCard label="Pricing Candidates" value={formatNumber(data?.repricingSummary?.pricingRows)} />
          <MetricCard label="Liquidate" value={formatNumber(data?.repricingSummary?.liquidateRows)} />
          <MetricCard label="Remove / eBay" value={formatNumber(data?.repricingSummary?.removeOrEbayRows)} />
          <MetricCard label="Missing Data" value={formatNumber(data?.repricingSummary?.missingDataRows)} />
          <MetricCard label="Snoozed" value={formatNumber(data?.repricingSummary?.snoozedRows)} />
        </MetricGrid>
      </DashboardSection>
      <DashboardSection title="Stale High-Capital Inventory" eyebrow="Repricing feed">
        <CompactStatusTable columns={["ASIN", "Title", "Units", "Value", "Age", "Velocity", "Recommendation"]} rows={asRows(data?.staleInventory).map((row) => ({ id: text(row.asin || row.sellerSku), href: href(row.drilldownUrl), cells: [text(row.asin), <span key="title" className="block max-w-[260px] truncate">{text(row.title)}</span>, formatNumber(row.units), formatMoney(row.value), text(row.ageBucket) || "--", formatNumber(row.currentVelocity), text(row.recommendation)] }))} />
      </DashboardSection>
    </div>
  );
}

function SourcingPanel({ data, loading }: { data: DashboardPayload | null; loading: boolean }) {
  return (
    <div className="space-y-4">
      <MetricGrid>
        <MetricCard label="Replenishment Candidates" value={loading ? "--" : formatNumber(data?.summary?.replenishmentCandidates)} />
        <MetricCard label="Out of Stock Sellers" value={loading ? "--" : formatNumber(data?.summary?.outOfStockRecentSellers)} />
        <MetricCard label="Low Stock / High ROI" value={loading ? "--" : formatNumber(data?.summary?.lowStockHighRoi)} />
        <MetricCard label="Repeat Winners" value={loading ? "--" : formatNumber(data?.summary?.highProfitRepeatBuys)} />
        <MetricCard label="Research Queue Value" value={loading ? "--" : formatMoney(data?.summary?.researchQueueValue)} />
      </MetricGrid>
      <DashboardSection title="Priority Buy Research Queue" eyebrow="Manual sourcing">
        <CompactStatusTable columns={["Priority", "ASIN / Title", "System", "Sold 30d", "Current", "Avg Profit", "ROI", "Max Buy", "Reason"]} rows={asRows(data?.candidates).map((row) => ({ id: text(row.asin), cells: [text(row.priority), <a key="asin" className="text-blue-700" href={href(row.ebaySearchUrl) ?? "#"}>{text(row.asin)} - {text(row.title)}</a>, text(row.system) || "--", formatNumber(row.unitsSold30d), formatNumber(Number(row.currentAmazonUnits ?? 0) + Number(row.currentMbopPreAmazonUnits ?? 0)), formatMoney(row.averageProfit90d), formatPercent(row.averageRoi90d), formatMoney(row.suggestedMaxBuyCost), text(row.reason)] }))} />
      </DashboardSection>
      <div className="grid gap-4 xl:grid-cols-2">
        <DashboardSection title="Recently Out Of Stock" eyebrow="Sold recently, no supply">
          <CompactStatusTable columns={["ASIN", "Title", "Sold 90d", "Avg Profit", "Reason"]} rows={asRows(data?.recentlyOutOfStock).map((row) => ({ id: text(row.asin), cells: [text(row.asin), text(row.title), formatNumber(row.unitsSold90d), formatMoney(row.averageProfit90d), text(row.reason)] }))} />
        </DashboardSection>
        <DashboardSection title="Repeat Winners" eyebrow="Purchased and sold repeatedly">
          <CompactStatusTable columns={["ASIN", "Title", "Sold", "Profit", "ROI", "Buys"]} rows={asRows(data?.repeatWinners).map((row) => ({ id: text(row.asin), cells: [text(row.asin), text(row.title), formatNumber(row.totalUnitsSold), formatMoney(row.totalProfit), formatPercent(row.averageRoi), formatNumber(row.timesPurchased)] }))} />
        </DashboardSection>
      </div>
    </div>
  );
}

function LossPreventionPanel({ data, loading }: { data: DashboardPayload | null; loading: boolean }) {
  return (
    <div className="space-y-4">
      <MetricGrid>
        <MetricCard label="Open Problem Episodes" value={loading ? "--" : formatNumber(data?.summary?.openProblemCases)} href="/?tab=order-problems" />
        <MetricCard label="Estimated Value At Risk" value={loading ? "--" : formatMoney(data?.summary?.estimatedValueAtRisk)} />
        <MetricCard label="Refund Pending" value={loading ? "--" : formatMoney(data?.summary?.refundPendingValue)} href="/?tab=order-problems&stage=refund_pending" />
        <MetricCard label="Return Pending" value={loading ? "--" : formatNumber(data?.summary?.returnPendingCount)} href="/?tab=order-problems&stage=return_needed" />
        <MetricCard label="Late / Stale Shipments" value={loading ? "--" : formatNumber(data?.summary?.lateShipmentCount)} href="/?tab=order-problems" />
        <MetricCard label="Amazon Discrepancies" value={loading ? "--" : formatNumber(data?.summary?.amazonDiscrepancyCount)} href="/inventory-reconciliation" />
      </MetricGrid>
      <div className="grid gap-4 xl:grid-cols-2">
        <DashboardSection title="Risk Type Summary" eyebrow="Value at risk">
          <CompactStatusTable columns={["Risk Type", "Count", "Value", "Oldest", "Action"]} rows={asRows(data?.byRiskType).map((row) => ({ id: text(row.riskType), href: href(row.drilldownUrl), cells: [text(row.riskType), formatNumber(row.count), formatMoney(row.valueAtRisk), formatDays(row.oldestAgeDays), "Open"] }))} />
        </DashboardSection>
        <DashboardSection title="Urgent Episodes" eyebrow="Top 10">
          <CompactStatusTable columns={["Severity", "Order", "Item", "Stage", "Age", "Value", "Next Action"]} rows={asRows(data?.urgentCases).map((row) => ({ id: text(row.caseId), href: href(row.drilldownUrl), cells: [text(row.severity), text(row.orderNumber) || "--", <span key="title" className="block max-w-[220px] truncate">{text(row.title)}</span>, text(row.stage), formatDays(row.ageDays), formatMoney(row.valueAtRisk), text(row.nextAction) || "--"] }))} />
        </DashboardSection>
      </div>
      <DashboardSection title="Loss / Recovery Trend" eyebrow="Monthly">
        <CompactStatusTable columns={["Month", "Refunds Received", "Closed No Refund", "Returns", "Cancelled", "Episodes"]} rows={asRows(data?.lossTrend).map((row) => ({ id: text(row.yearMonth), cells: [text(row.yearMonth), formatMoney(row.refundsReceived), formatMoney(row.closedNoRefundValue), formatNumber(row.returnCount), formatNumber(row.cancelledCount), formatNumber(row.problemCaseCount)] }))} />
      </DashboardSection>
    </div>
  );
}

function SystemHealthPanel({ data, loading }: { data: DashboardPayload | null; loading: boolean }) {
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(null);
  const groups = asRows(data?.schedulerGroups);
  const selectedGroup = groups.find((group) => text(group.group) === selectedGroupId) ?? null;

  return (
    <div className="space-y-4">
      <MetricGrid>
        <MetricCard label="Overall Status" value={loading ? "--" : data?.summary?.overallStatus ?? "--"} />
        <MetricCard label="AWS Groups" value={loading ? "--" : formatNumber(data?.summary?.schedulerGroups)} />
        <MetricCard label="Healthy Groups" value={loading ? "--" : formatNumber(data?.summary?.healthyGroups)} tone="green" />
        <MetricCard label="Failed Jobs" value={loading ? "--" : formatNumber(data?.summary?.failedJobsLastRun)} tone={toneFor(data?.summary?.failedJobsLastRun ?? 0, 0, 1)} />
        <MetricCard label="Delayed Groups" value={loading ? "--" : formatNumber(data?.summary?.delayedGroups)} tone={toneFor(data?.summary?.delayedGroups ?? 0, 0, 3)} />
      </MetricGrid>
      <DashboardSection title="AWS Scheduler Groups" eyebrow="EventBridge / ECS">
        <SchedulerGroupTable
          groups={groups}
          loading={loading}
          onSelect={(group) => setSelectedGroupId(text(group.group))}
        />
      </DashboardSection>
      <div className="grid gap-4 xl:grid-cols-2">
        <DashboardSection title="Recent Runs" eyebrow="Orchestrator">
          <CompactStatusTable columns={["Run", "Group", "Status", "Finished", "Failed", "Summary"]} rows={asRows(data?.recentRuns).map((row) => ({ id: text(row.runId), cells: [text(row.runId), text(row.group) || "--", text(row.status), formatDateShort(text(row.finishedAt)), formatNumber(row.failedJobs), text(row.summary) || "--"] }))} />
        </DashboardSection>
        <DashboardSection title="Guardrails" eyebrow="Capacity / limits">
          <CompactStatusTable columns={["Area", "Status", "Message"]} rows={[
            { id: "capacity", cells: ["Supabase", data?.capacity?.supabaseStatus ?? "unknown", data?.capacity?.message ?? "--"] },
            { id: "keepa", cells: ["Keepa", `${data?.externalLimits?.keepaTokenStatus ?? "unknown"} (${formatNumber(data?.externalLimits?.keepaTokens)} tokens)`, data?.externalLimits?.message ?? "--"] },
            { id: "easypost", cells: ["EasyPost errors", formatNumber(data?.externalLimits?.easyPostErrors), "From sync health summary"] },
          ]} />
        </DashboardSection>
      </div>
      {selectedGroup ? (
        <DashboardSchedulerGroupDrawer group={selectedGroup} onClose={() => setSelectedGroupId(null)} />
      ) : null}
    </div>
  );
}

function SchedulerGroupTable({
  groups,
  loading,
  onSelect,
}: {
  groups: DashboardPayload[];
  loading: boolean;
  onSelect: (group: DashboardPayload) => void;
}) {
  if (!groups.length) {
    return (
      <div className="rounded-md border border-slate-200 px-3 py-6 text-center text-sm text-slate-500">
        {loading ? "Loading scheduler groups..." : "No scheduler group telemetry found."}
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-md border border-slate-200">
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-50 text-[11px] uppercase tracking-wide text-slate-500">
          <tr>
            {["Group", "Status", "Since Success", "Last Success", "Runtime", "Cadence", "Jobs", "Trigger"].map((column) => (
              <th key={column} className="px-3 py-2 font-semibold">{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {groups.map((group) => (
            <tr key={text(group.group)} className="border-t border-slate-100 hover:bg-slate-50">
              {[
                text(group.label),
                text(group.status),
                formatAgeHours(group.ageHours),
                formatDateShort(text(group.lastSuccessAt)),
                formatDurationShort(group.runtimeSeconds),
                text(group.cadence),
                `${formatNumber(group.jobsOk)}/${formatNumber(group.jobsTotal)} ok`,
                text(group.trigger) || "--",
              ].map((cell, index) => (
                <td key={index} className="p-0">
                  <button
                    className="block h-full w-full px-3 py-2 text-left"
                    onClick={() => onSelect(group)}
                    type="button"
                  >
                    {cell}
                  </button>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DashboardSchedulerGroupDrawer({ group, onClose }: { group: DashboardPayload; onClose: () => void }) {
  const jobs = asRows(group.jobs);
  const runs = asRows(group.recentRuns).slice(0, 10);
  const features = Array.isArray(group.features) ? group.features.map(text).filter(Boolean) : [];
  const scheduleNames = Array.isArray(group.scheduleNames) ? group.scheduleNames.map(text).filter(Boolean) : [];
  const successfulRuns = runs.filter((run) => text(run.status) === "ok").length;
  const topStats = asRows(group.latestRun?.stats).length ? asRows(group.latestRun?.stats) : asRows(group.stats);

  return (
    <div className="fixed inset-0 z-50">
      <button aria-label="Close scheduler group details" className="absolute inset-0 cursor-default bg-slate-950/30" onClick={onClose} type="button" />
      <aside className="absolute right-0 top-0 flex h-full w-full max-w-3xl flex-col border-l border-slate-200 bg-white shadow-2xl">
        <div className="flex items-start justify-between gap-3 border-b border-slate-200 px-5 py-4">
          <div>
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">{text(group.domain)}</div>
            <h2 className="mt-1 text-xl font-semibold text-slate-950">{text(group.label)}</h2>
            <div className="mt-2 flex flex-wrap gap-2 text-xs">
              <span className="rounded-md bg-slate-100 px-2 py-1 text-slate-700">{text(group.status)}</span>
              <span className="rounded-md bg-slate-100 px-2 py-1 text-slate-700">{text(group.cadence)}</span>
              <span className="rounded-md bg-slate-100 px-2 py-1 text-slate-700">Last 10: {successfulRuns}/{runs.length} successful</span>
            </div>
          </div>
          <button className="rounded-md border border-slate-200 p-2 text-slate-500 hover:bg-slate-50 hover:text-slate-800" onClick={onClose} type="button">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          <div className="grid gap-3 md:grid-cols-3">
            <DrawerMetric label="Last Success" value={formatDateShort(text(group.lastSuccessAt))} />
            <DrawerMetric label="Last Attempt" value={formatDateShort(text(group.lastRunAt))} />
            <DrawerMetric label="Latest Runtime" value={formatDurationShort(group.runtimeSeconds)} />
          </div>

          <section className="mt-5">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">What This Updates</h3>
            <p className="mt-2 text-sm leading-6 text-slate-700">{text(group.description) || "No description recorded."}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {features.length ? features.map((feature) => (
                <span key={feature} className="rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-xs text-slate-700">{feature}</span>
              )) : <span className="text-xs text-slate-500">No feature mapping recorded.</span>}
            </div>
          </section>

          <section className="mt-5 grid gap-4 md:grid-cols-2">
            <div>
              <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Schedule</h3>
              <div className="mt-2 rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">{text(group.schedule) || "--"}</div>
              <div className="mt-2 flex flex-wrap gap-1">
                {scheduleNames.length ? scheduleNames.map((name) => (
                  <span key={name} className="rounded-md border border-slate-200 bg-white px-2 py-1 font-mono text-[11px] text-slate-600">{name}</span>
                )) : <span className="rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] text-slate-500">manual/on-demand</span>}
              </div>
            </div>
            <div>
              <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Guardrails</h3>
              <div className="mt-2 grid grid-cols-2 gap-2">
                <DrawerMetric label="Expected Every" value={Number(group.expectedEveryHours) > 0 ? `${formatNumber(group.expectedEveryHours)}h` : "manual"} compact />
                <DrawerMetric label="Critical After" value={Number(group.criticalAfterHours) > 0 ? `${formatNumber(group.criticalAfterHours)}h` : "manual"} compact />
              </div>
            </div>
          </section>

          <section className="mt-5">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Jobs In This Group</h3>
            <CompactStatusTable
              columns={["Job", "Status", "Last Run", "Runtime"]}
              rows={jobs.map((job) => ({
                id: text(job.name),
                cells: [
                  <div key="job">
                    <div className="font-medium">{text(job.name)}</div>
                    <div className="text-xs text-slate-500">{job.blocking ? "blocking" : "nonblocking"}</div>
                  </div>,
                  text(job.status),
                  formatDateShort(text(job.lastRunAt)),
                  formatDurationShort(job.runtimeSeconds),
                ],
              }))}
              emptyText="No job telemetry recorded."
            />
          </section>

          <section className="mt-5">
            <div className="flex items-center justify-between gap-3">
              <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Last 10 Runs</h3>
              <DrawerPills stats={topStats} empty="No counters" />
            </div>
            <div className="mt-2">
              <CompactStatusTable
                columns={["Run", "Status", "Finished", "Runtime", "Changed"]}
                rows={runs.map((run) => ({
                  id: text(run.runId),
                  cells: [
                    <div key="run">
                      <div className="font-mono text-xs">{shortId(text(run.runId))}</div>
                      <div className="text-xs text-slate-500">{text(run.eventbridgeScheduleName) || text(run.triggerSource) || "manual"}</div>
                    </div>,
                    text(run.status),
                    formatDateShort(text(run.finishedAt) || text(run.startedAt)),
                    formatDurationShort(run.runtimeSeconds),
                    <DrawerPills key="stats" stats={asRows(run.stats)} empty="No counters" />,
                  ],
                }))}
                emptyText="No run history recorded."
              />
            </div>
          </section>
        </div>
      </aside>
    </div>
  );
}

function DrawerMetric({ label, value, compact = false }: { label: string; value: string; compact?: boolean }) {
  return (
    <div className={`rounded-lg border border-slate-200 bg-slate-50 ${compact ? "p-2" : "p-3"}`}>
      <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`mt-1 font-semibold text-slate-900 ${compact ? "text-sm" : "text-base"}`}>{value}</div>
    </div>
  );
}

function DrawerPills({ stats, empty }: { stats: DashboardPayload[]; empty: string }) {
  if (!stats.length) return <span className="text-xs text-slate-500">{empty}</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {stats.map((stat) => (
        <span key={`${text(stat.label)}-${text(stat.value)}`} className="rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-xs">
          <span className="text-slate-500">{text(stat.label)}</span>{" "}
          <span className="font-medium text-slate-900">{text(stat.value)}</span>
        </span>
      ))}
    </div>
  );
}

function StagedPanel({ view }: { view: DashboardView }) {
  const copy: Record<DashboardView, { title: string; detail: string }> = {
    overview: { title: "Overview", detail: "" },
    operations: { title: "Operations", detail: "" },
    inventory: {
      title: "Inventory Dashboard",
      detail: "Phase 2 will add inventory value by location, age, capital at risk, concentration risk, and reconciliation summary counts.",
    },
    amazon: {
      title: "Amazon Dashboard",
      detail: "Phase 3 will add Amazon sales, listing health, repricing summary, and inventory planning summaries.",
    },
    sourcing: {
      title: "Sourcing Dashboard",
      detail: "Sourcing dashboard is loading or unavailable.",
    },
    "loss-prevention": {
      title: "Loss Prevention Dashboard",
      detail: "Loss Prevention dashboard is loading or unavailable.",
    },
    "system-health": {
      title: "System Health Dashboard",
      detail: "Phase 3 will move technical freshness, scheduler, API guardrail, and Supabase health summaries into this dashboard tab.",
    },
  };
  const panel = copy[view];

  return (
    <DashboardSection title={panel.title} eyebrow="Staged">
      <p className="text-sm text-slate-600">{panel.detail}</p>
    </DashboardSection>
  );
}

function SeverityPill({ severity }: { severity: "green" | "yellow" | "red" | "unknown" }) {
  const labels = {
    green: "Normal",
    yellow: "Attention",
    red: "Urgent",
    unknown: "Pending",
  };
  const classes = {
    green: "border-emerald-200 bg-emerald-50 text-emerald-800",
    yellow: "border-amber-200 bg-amber-50 text-amber-800",
    red: "border-rose-200 bg-rose-50 text-rose-800",
    unknown: "border-slate-200 bg-slate-50 text-slate-600",
  };
  return <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${classes[severity]}`}>{labels[severity]}</span>;
}

function DashboardShellFallback() {
  return (
    <main className="min-h-screen bg-slate-100 p-4 text-slate-900">
      <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-500 shadow-sm">Loading dashboard...</div>
    </main>
  );
}

function normalizeView(value: string | null): DashboardView {
  if (value && allViews.has(value as DashboardView)) return value as DashboardView;
  return "overview";
}

function cleanupTotal(data: OperationsData | null) {
  if (!data) return 0;
  return (
    data.purchaseCleanup.missingAsin +
    data.purchaseCleanup.missingSellPrice +
    data.purchaseCleanup.missingAmazonTitle +
    data.purchaseCleanup.missingSystem
  );
}

function orderProblemTotal(data: OperationsData | null) {
  if (!data) return 0;
  if (!data.orderProblems) return 0;
  return Object.entries(data.orderProblems).reduce((total, [key, value]) => {
    if (key === "href") return total;
    return total + Number(value ?? 0);
  }, 0);
}

function toneFor(value: number, warningAt: number, urgentAt: number) {
  if (value > urgentAt) return "red";
  if (value > warningAt) return "yellow";
  return "green";
}

function toneForAlertCount(value: unknown) {
  const count = Number(value ?? 0);
  if (!Number.isFinite(count)) return "unknown";
  return count > 0 ? "red" : "green";
}

function toneForAccountHealth(value: unknown) {
  const score = Number(value);
  if (!Number.isFinite(score)) return "unknown";
  if (score >= 200) return "green";
  if (score >= 100) return "yellow";
  return "red";
}

function formatNumber(value: unknown) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return new Intl.NumberFormat("en-US").format(Number(value));
}

function formatDecimal(value: unknown, maximumFractionDigits = 1) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: maximumFractionDigits,
    maximumFractionDigits,
  }).format(Number(value));
}

function formatSignedNumber(value: unknown) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  const numberValue = Number(value);
  const sign = numberValue > 0 ? "+" : "";
  return `${sign}${new Intl.NumberFormat("en-US").format(numberValue)}`;
}

function formatMoney(value: unknown) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(Number(value));
}

function formatPercent(value: unknown) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return new Intl.NumberFormat("en-US", {
    style: "percent",
    maximumFractionDigits: 0,
  }).format(Number(value));
}

function formatDays(value: unknown) {
  if (value === null || value === undefined) return "--";
  return `${formatNumber(value)}d`;
}

function formatDurationShort(value: unknown) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  const seconds = Number(value);
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  return `${(seconds / 3600).toFixed(1)}h`;
}

function formatAgeHours(value: unknown) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  const hours = Number(value);
  if (hours < 1) return "<1h";
  if (hours < 48) return `${Math.round(hours)}h`;
  return `${Math.round(hours / 24)}d`;
}

function formatDateShort(value: string | null | undefined) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "America/Los_Angeles",
  }).format(date);
}

function formatDateOnly(value: unknown) {
  if (!value) return "--";
  const textValue = String(value);
  const dateOnlyMatch = textValue.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (dateOnlyMatch) {
    const [, year, month, day] = dateOnlyMatch;
    return new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    }).format(new Date(Number(year), Number(month) - 1, Number(day)));
  }
  const date = new Date(textValue);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "America/Los_Angeles",
  }).format(date);
}

function asRows(value: unknown): DashboardPayload[] {
  return Array.isArray(value) ? (value as DashboardPayload[]) : [];
}

function text(value: unknown) {
  if (value === null || value === undefined) return "";
  return String(value);
}

function href(value: unknown) {
  const output = text(value);
  return output || undefined;
}

function shortId(value: string) {
  if (!value) return "--";
  return value.length > 8 ? value.slice(0, 8) : value;
}

function noticeClass(tone: RefreshNotice["tone"]) {
  if (tone === "success") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (tone === "warning") return "border-amber-200 bg-amber-50 text-amber-800";
  return "border-slate-200 bg-white text-slate-700";
}
