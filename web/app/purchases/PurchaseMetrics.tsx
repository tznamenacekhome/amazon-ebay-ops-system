import type { PurchaseStats } from "./types";

type PurchaseMetricsProps = {
  stats: PurchaseStats;
};

export function PurchaseMetrics({ stats }: PurchaseMetricsProps) {
  return (
    <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-4">
      <Metric label="Total Rows" value={stats.total} />
      <Metric label="Visible" value={stats.visible} />
      <Metric label="Needs Review" value={stats.needsReview} />
      <Metric label="Delivered" value={stats.delivered} />
    </div>
  );
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
