"use client";
import { useEffect, useState, type ReactNode } from "react";
import type { SourcingOpportunity } from "./types";

export function LazySourcingReview({ row, children, onClose }: {
  row: SourcingOpportunity; children: (loaded: SourcingOpportunity) => ReactNode; onClose: () => void;
}) {
  const [loaded, setLoaded] = useState<SourcingOpportunity | null>(row.reviewEvidenceLoaded === false ? null : row);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (row.reviewEvidenceLoaded !== false) return;
    const controller = new AbortController();
    fetch(`/api/sourcing/opportunities/${row.opportunityId}/evidence`, { cache: "no-store", signal: controller.signal })
      .then(async response => {
        const evidence = await response.json();
        if (!response.ok) throw new Error(evidence.error ?? "Unable to load review evidence.");
        if (evidence.asin !== row.asin || evidence.candidateId !== row.candidateId || evidence.ebayItemId !== row.ebayItemId ||
          (evidence.diagnosticComparison?.evaluation?.id ?? null) !== (row.diagnosticComparison?.evaluation?.id ?? null)) {
          throw new Error("This pair or evaluation changed. Close this dialog and refresh the list before reviewing.");
        }
        if (!controller.signal.aborted) setLoaded({ ...row, ...evidence });
      })
      .catch(error => { if (!controller.signal.aborted) setError(error instanceof Error ? error.message : "Unable to load review evidence."); });
    return () => controller.abort();
  }, [row, attempt]);
  if (loaded) return children(loaded);
  return <div className="fixed inset-0 z-40 flex items-center justify-center bg-slate-950/20">
    <div role="dialog" aria-label="Loading review evidence" className="rounded border bg-white p-5 shadow-lg">
      <p role={error ? "alert" : "status"}>{error ?? "Loading review evidence?"}</p>
      {error ? <button className="mr-3 mt-3 rounded border px-3 py-1" onClick={() => { setError(null); setAttempt(value => value + 1); }}>Retry</button> : null}
      <button className="mt-3 rounded border px-3 py-1" onClick={onClose}>Close</button>
    </div>
  </div>;
}
