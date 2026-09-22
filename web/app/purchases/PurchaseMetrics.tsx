import type { PurchaseStats } from "./types";

type PurchaseMetricsProps = {
  stats: PurchaseStats;
};

export function PurchaseMetrics({ stats }: PurchaseMetricsProps) {
  return (
    <>
    <div className="mb-3 flex flex-wrap gap-x-8 gap-y-3 rounded-md border border-slate-200 bg-white px-4 py-3" title="All active resale purchases, independent of page filters. Uses stored quantity and unit cost. Partially delivered purchase items remain in Not delivered yet until fully delivered; received, listed, cancelled and returns are excluded.">
      <DeliveryMetric label="Not delivered yet" value={stats.delivery?.notDelivered} unavailable={Boolean(stats.deliveryError)} />
      <DeliveryMetric label="Delivered and not received" value={stats.delivery?.deliveredNotReceived} unavailable={Boolean(stats.deliveryError)} />
      {(stats.delivery?.dueDays ?? Array.from({ length: 7 }, () => undefined)).map((day, index) => (
        <div key={day?.dueDate ?? index} title="Undelivered resale units due on this calendar date. Carrier ETA takes precedence over eBay ETA. Items without an ETA are excluded.">
          <DeliveryMetric
            label={dueDayLabel(day?.dueDate, index)}
            value={day}
            unavailable={Boolean(stats.deliveryDueError || stats.deliveryError)}
          />
        </div>
      ))}
      {stats.deliveryError ? <p role="alert" className="w-full text-xs text-red-700">Delivery totals unavailable: {stats.deliveryError}</p> : null}
      {stats.deliveryDueError ? <p role="alert" className="w-full text-xs text-red-700">Daily delivery totals unavailable: {stats.deliveryDueError}</p> : null}
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

function dueDayLabel(dueDate: string | undefined, index: number) {
  if (index === 0) return "Due today";
  if (index === 1) return "Due tomorrow";
  if (!dueDate) return "Due";
  const weekday = new Date(`${dueDate}T12:00:00Z`).toLocaleDateString("en-US", {
    weekday: "long",
    timeZone: "UTC",
  });
  return `Due ${weekday}`;
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
