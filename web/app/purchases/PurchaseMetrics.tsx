import type { PurchaseStats } from "./types";

type PurchaseMetricsProps = {
  stats: PurchaseStats;
};

export function PurchaseMetrics({ stats }: PurchaseMetricsProps) {
  return (
    <>
    <div className="mb-3 flex flex-wrap gap-x-8 gap-y-2 rounded-md border border-slate-200 bg-white px-4 py-3" title="All active resale purchases, independent of page filters. Uses stored quantity and unit cost. Partially delivered purchase items remain in Not delivered yet until fully delivered; received, listed, cancelled and returns are excluded.">
      <DeliveryMetric label="Not delivered yet" value={stats.delivery?.notDelivered} unavailable={Boolean(stats.deliveryError)} />
      <DeliveryMetric label="Delivered and not received" value={stats.delivery?.deliveredNotReceived} unavailable={Boolean(stats.deliveryError)} />
      {stats.deliveryError ? <p role="alert" className="w-full text-xs text-red-700">Delivery totals unavailable: {stats.deliveryError}</p> : null}
    </div>
    <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-5">
      <Metric label="Total Rows" value={stats.total} />
      <Metric label="Visible" value={stats.visible} />
      <Metric label="Missing Data" value={stats.needsReview} />
      <Metric label="Order Problems" value={stats.orderProblems} />
      <Metric label="Delivered" value={stats.delivered} />
    </div>
    </>
  );
}

function DeliveryMetric({ label, value, unavailable }: { label: string; value: NonNullable<PurchaseStats["delivery"]>["notDelivered"] | undefined; unavailable: boolean }) {
  return <div>
    <div className="text-xs text-slate-500">{label}</div>
    <div className="text-lg font-semibold tabular-nums">{value ? <>{value.units.toLocaleString()} units <span className="mx-2 text-slate-300">|</span> {value.purchaseDollars.toLocaleString("en-US", { style: "currency", currency: "USD" })}</> : unavailable ? "Unavailable" : "Loading totals..."}</div>
    {value && value.unpricedUnits > 0 ? <div className="text-xs text-amber-700">{value.unpricedUnits} units have no recorded cost</div> : null}
  </div>;
}

function Metric({
  label,
  value,
}: {
  label: string;
  value: number;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
      <div className="text-xs uppercase tracking-wide text-slate-500">
        {label}
      </div>

      <div className="text-2xl font-semibold">{value}</div>
    </div>
  );
}
