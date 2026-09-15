"use client";

import { useEffect, useState } from "react";
import type { PurchaseDeliveryStats } from "../purchases/types";

type Metric = PurchaseDeliveryStats["deliveredNotReceived"];

export function ReceivingMetrics({ refreshKey }: { refreshKey: number }) {
  const [value, setValue] = useState<Metric | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!refreshKey) return;
    const controller = new AbortController();
    async function load() {
      setValue(null);
      setError(null);
      try {
        const response = await fetch("/api/receiving/stats", { cache: "no-store", signal: controller.signal });
        const result = await response.json();
        if (!response.ok || result.deliveryError) {
          throw new Error(result.deliveryError || `Failed to load receiving totals: ${response.status}`);
        }
        if (!controller.signal.aborted) setValue(result.delivery.deliveredNotReceived);
      } catch (err) {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : "Receiving totals unavailable.");
      }
    }
    void load();
    return () => controller.abort();
  }, [refreshKey]);

  return <div className="mb-4 rounded-lg border border-slate-200 bg-white px-4 py-3" aria-live="polite">
    <div className="text-xs text-slate-500">Delivered and not received</div>
    <div className="text-lg font-semibold tabular-nums">
      {value ? <>{value.units.toLocaleString()} units <span className="mx-2 text-slate-300">|</span> {value.purchaseDollars.toLocaleString("en-US", { style: "currency", currency: "USD" })} purchase value</> : error ? "Unavailable" : "Loading totals..."}
    </div>
    <div className="text-xs text-slate-500">All fully delivered resale purchases; independent of search. Same totals as Purchases.</div>
    {value && value.unpricedUnits > 0 ? <div className="text-xs text-amber-700">{value.unpricedUnits} units have no recorded cost</div> : null}
    {error ? <div role="alert" className="text-xs text-red-700">{error}</div> : null}
  </div>;
}
