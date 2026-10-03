"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowRight, ExternalLink, RefreshCw, ShoppingCart, X } from "lucide-react";
import { mutationHeaders } from "../mutationHeaders";

type Tab = "ready" | "temporary" | "added" | "pending" | "unqualified" | "hard";
type Row = {
  opportunityId: string; evaluationId: string | null; supplierProductId: string; status: string;
  supplier: string; supplierTitle: string; system: string; rawIdentifier: string; availabilityRaw: string | null;
  supplierCost: number | null; previousSupplierPrice: number | null; supplierHistoricalLow: number | null;
  supplierPriceChange30d: number | null; supplierPriceChange90d: number | null; asin: string | null;
  amazonTitle: string | null; amazonPlatform: string | null; imageUrl: string | null; eligibilityStatus: string | null;
  evaluatedAt: string | null; currentBuyBox: number | null; keepaAvg30: number | null; keepaAvg90: number | null;
  keepaVelocity90: number | null; currentFees: number | null; avg90Fees: number | null; inboundAllowance: number | null;
  returnAllowance: number | null; storageAllowance: number | null; allowanceStatus: string | null;
  currentProfit: number | null; currentRoi: number | null; avg90Profit: number | null; avg90Roi: number | null;
  qualificationBasis: string; roiFloor: number | null; avg90RoiFloor: number | null; priceHeadroom: number | null;
  expectedMonthlySales: number | null; fbaUnits: number; inboundUnits: number; draftUnits: number;
  targetUnits: number | null; purchaseCapacity: number | null; offerCount: number | null; fbaSellerCount: number | null;
  riskSignals: Record<string, unknown>; incompleteReasons: string[]; matchSources: string[]; priorAccountSale: boolean;
  selectionSource: string | null; rankingRationale: Record<string, unknown>; compatibilityStatus: string | null;
  compatibilityReasonCodes: string[]; evaluationRequested: boolean;
  draft: { id: string; quantity: number; extendedCost: number | null; revision: number } | null;
};
type Candidate = {
  candidate_id: string; asin: string; title: string | null; image_url: string | null; platform: string | null;
  edition: string | null; region: string | null; format: string | null; product_type: string | null;
  current_buy_box: number | null; keepa_avg90: number | null; match_sources: string[]; compatibility_status: string;
  compatibility_reason_codes: string[]; prior_account_sale: boolean; keepa_sales_rank_drops90: number | null;
  eligibility_status: string | null; rank_position: number | null; ranking_rationale: Record<string, unknown>;
};

const tabs: Array<[Tab, string]> = [["ready", "Ready for Review"], ["temporary", "Temporary Passes"],
  ["added", "Added to Order"], ["pending", "Pending Match / Eligibility"],
  ["unqualified", "Not Qualified"], ["hard", "Hard Passes"]];

export default function WholesalePage() {
  const [tab, setTab] = useState<Tab>("ready");
  const [rows, setRows] = useState<Row[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [orderRow, setOrderRow] = useState<Row | null>(null);
  const [candidateRow, setCandidateRow] = useState<Row | null>(null);
  const [evaluationRow, setEvaluationRow] = useState<Row | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const response = await fetch(`/api/wholesale/opportunities?status=${tab}&pageSize=100`, { cache: "no-store" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Failed to load wholesale opportunities.");
      const nextRows = payload.rows as Row[];
      setRows(nextRows); setCounts(payload.counts || {});
      return nextRows;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Failed to load wholesale opportunities.");
      return [] as Row[];
    } finally { setLoading(false); }
  }, [tab]);
  useEffect(() => { void load(); }, [load]);

  async function decide(row: Row, action: string, reason?: string) {
    if (!row.evaluationId) return [] as Row[];
    setError(null);
    const response = await fetch(`/api/wholesale/opportunities/${row.opportunityId}/actions`, {
      method: "POST", headers: mutationHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ action, evaluationId: row.evaluationId, reason }),
    });
    const payload = await response.json();
    if (!response.ok) { setError(payload.error || "Decision failed."); return [] as Row[]; }
    return load();
  }

  async function advance(row: Row, action: string, reason?: string) {
    const nextRows = await decide(row, action, reason);
    setEvaluationRow(nextRows.find(item => item.opportunityId !== row.opportunityId) ?? null);
  }

  return <main className="min-h-screen bg-slate-100 px-5 py-5 text-slate-950">
    <div className="mb-4 flex items-start justify-between pr-28">
      <div><h1 className="text-2xl font-semibold">Wholesale Review</h1>
        <p className="text-sm text-slate-600">Review one opportunity at a time, with supplier evidence beside the selected Amazon listing.</p></div>
      <button onClick={() => void load()} className="inline-flex items-center gap-2 rounded border border-slate-300 bg-white px-3 py-2 text-sm"><RefreshCw className="h-4 w-4"/>Reload</button>
    </div>
    <div className="mb-4 flex gap-1 overflow-x-auto border-b border-slate-300">
      {tabs.map(([key, text]) => <button key={key} onClick={() => { setTab(key); setEvaluationRow(null); }} className={`whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium ${tab === key ? "border-slate-950 text-slate-950" : "border-transparent text-slate-500"}`}>{text} <span className="ml-1 rounded bg-slate-200 px-1.5 py-0.5 text-xs">{counts[key] ?? 0}</span></button>)}
    </div>
    {error ? <div className="mb-3 rounded border border-red-200 bg-red-50 p-2 text-sm text-red-700">{error}</div> : null}
    {tab === "ready" && rows.length ? <button onClick={() => setEvaluationRow(rows[0])} className="mb-3 inline-flex items-center gap-2 rounded bg-slate-900 px-4 py-2 text-sm font-medium text-white">Start review queue <ArrowRight className="h-4 w-4"/></button> : null}
    <div className="overflow-x-auto rounded border border-slate-300 bg-white shadow-sm">
      <table className="min-w-[1900px] w-full text-left text-xs">
        <thead className="sticky top-0 bg-slate-100 text-slate-600"><tr><Th>Supplier item</Th><Th>Amazon match</Th><Th>Supplier history</Th><Th>Current Buy Box</Th><Th>90-day average</Th><Th>Costs / floor</Th><Th>Inventory / capacity</Th><Th>Risk signals</Th><Th>Actions</Th></tr></thead>
        <tbody>{loading ? <tr><td colSpan={9} className="p-8 text-center text-slate-500">Loading...</td></tr> : rows.length === 0 ? <tr><td colSpan={9} className="p-8 text-center text-slate-500">No opportunities in this queue.</td></tr> : rows.map(row =>
          <tr key={row.opportunityId} className="border-t border-slate-200 align-top hover:bg-slate-50">
            <Td><div className="font-semibold">{row.supplierTitle}</div><div>{row.supplier} · {row.system}</div><div className="font-mono text-slate-500">{row.rawIdentifier}</div><div>Available: {row.availabilityRaw ?? "unknown"}</div></Td>
            <Td><AmazonIdentity row={row}/><button className="mt-1 text-blue-700 underline" onClick={() => setCandidateRow(row)}>Review candidates</button></Td>
            <Td><SupplierHistory row={row}/></Td><Td><RoiPanel row={row} basis="current"/></Td><Td><RoiPanel row={row} basis="average"/></Td>
            <Td><CostPanel row={row}/></Td><Td><InventoryPanel row={row}/></Td><Td><RiskPanel row={row}/></Td>
            <Td><button onClick={() => setEvaluationRow(row)} className="mb-2 block rounded bg-blue-700 px-2 py-1 text-white">Evaluate</button><Actions row={row} tab={tab} onOrder={() => setOrderRow(row)} onDecision={decide}/></Td>
          </tr>)}</tbody>
      </table>
    </div>
    {evaluationRow ? <EvaluationDialog row={evaluationRow} position={Math.max(rows.findIndex(item => item.opportunityId === evaluationRow.opportunityId), 0) + 1} total={rows.length} onClose={() => setEvaluationRow(null)} onCandidates={() => setCandidateRow(evaluationRow)} onOrder={() => setOrderRow(evaluationRow)} onDecision={advance}/> : null}
    {orderRow ? <OrderDialog row={orderRow} onClose={() => setOrderRow(null)} onSaved={async () => { const current = orderRow; setOrderRow(null); const nextRows = await load(); if (evaluationRow?.opportunityId === current.opportunityId) setEvaluationRow(nextRows.find(item => item.opportunityId !== current.opportunityId) ?? null); }} setError={setError}/> : null}
    {candidateRow ? <CandidateDialog row={candidateRow} onClose={() => setCandidateRow(null)} onSaved={async () => { const current = candidateRow; setCandidateRow(null); const nextRows = await load(); setEvaluationRow(nextRows.find(item => item.opportunityId === current.opportunityId) ?? null); }} setError={setError}/> : null}
  </main>;
}

function EvaluationDialog({ row, position, total, onClose, onCandidates, onOrder, onDecision }: { row: Row; position: number; total: number; onClose: () => void; onCandidates: () => void; onOrder: () => void; onDecision: (row: Row, action: string, reason?: string) => Promise<void> }) {
  const [reason, setReason] = useState("low_profitability");
  const pending = pendingExplanation(row);
  return <Modal title={`Opportunity evaluation · ${position} of ${total}`} onClose={onClose} wide>
    <div className="max-h-[78vh] overflow-y-auto pr-1">
      {pending ? <div className="mb-4 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900"><div className="font-semibold">Evaluation pending</div>{pending}</div> : null}
      <div className="grid gap-4 lg:grid-cols-2">
        <section className="rounded border border-slate-300 p-4"><h3 className="mb-3 font-semibold">Supplier evidence</h3><div className="text-lg font-semibold">{row.supplierTitle}</div><div className="text-sm text-slate-600">{row.supplier} · {row.system} · {row.rawIdentifier}</div><div className="mt-4 grid grid-cols-2 gap-2 text-sm"><Metric label="Unit cost" value={money(row.supplierCost)}/><Metric label="Availability" value={row.availabilityRaw ?? "Unknown"}/><SupplierHistory row={row}/></div></section>
        <section className="rounded border border-slate-300 p-4"><h3 className="mb-3 font-semibold">Selected Amazon listing</h3><AmazonIdentity row={row}/><div className="mt-3 rounded bg-slate-100 p-3 text-sm"><Metric label="Selected by" value={label(row.selectionSource)}/><Metric label="Match evidence" value={row.matchSources.length ? row.matchSources.join(", ") : "No source recorded"}/><Metric label="Compatibility" value={`${label(row.compatibilityStatus)}${row.compatibilityReasonCodes.length ? ` · ${row.compatibilityReasonCodes.join(", ")}` : ""}`}/><Metric label="Prior account sale" value={row.priorAccountSale ? "Yes" : "No"}/><Metric label="Rank rationale" value={rationale(row.rankingRationale)}/></div><button onClick={onCandidates} className="mt-3 rounded border border-slate-400 px-3 py-2 text-sm">Compare alternative candidates</button></section>
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-2"><section className="rounded border border-slate-300 p-4"><h3 className="mb-2 font-semibold">Current Buy Box economics</h3><RoiPanel row={row} basis="current"/></section><section className="rounded border border-slate-300 p-4"><h3 className="mb-2 font-semibold">90-day average economics</h3><RoiPanel row={row} basis="average"/></section></div>
      <div className="mt-4 grid gap-4 lg:grid-cols-3"><section className="rounded border border-slate-300 p-4"><h3 className="mb-2 font-semibold">Cost assumptions</h3><CostPanel row={row}/></section><section className="rounded border border-slate-300 p-4"><h3 className="mb-2 font-semibold">Inventory and capacity</h3><InventoryPanel row={row}/></section><section className="rounded border border-slate-300 p-4"><h3 className="mb-2 font-semibold">Risk signals</h3><RiskPanel row={row}/></section></div>
      <div className="sticky bottom-0 mt-4 flex flex-wrap items-end gap-2 border-t bg-white py-4"><button disabled={!row.evaluationId || row.status !== "ready_for_review"} onClick={onOrder} className="inline-flex items-center gap-2 rounded bg-slate-900 px-4 py-2 text-white disabled:bg-slate-300"><ShoppingCart className="h-4 w-4"/>Add to Order</button><label className="text-xs text-slate-600">Pass reason<select value={reason} onChange={event => setReason(event.target.value)} className="mt-1 block rounded border p-2 text-sm text-slate-950"><PassOptions/></select></label><button disabled={!row.evaluationId} onClick={() => void onDecision(row, hardReason(reason) ? "hard_pass" : "temporary_pass", reason)} className="rounded border px-4 py-2 disabled:text-slate-400">Pass and open next</button><button onClick={onClose} className="ml-auto rounded border px-4 py-2">Close</button></div>
    </div>
  </Modal>;
}

function Actions({ row, tab, onOrder, onDecision }: { row: Row; tab: Tab; onOrder: () => void; onDecision: (row: Row, action: string, reason?: string) => Promise<Row[]> }) {
  const [reason, setReason] = useState("low_profitability");
  if (tab === "temporary" || tab === "hard") return <button onClick={() => void onDecision(row, "reverse_pass")} className="rounded border px-2 py-1">Reverse pass</button>;
  if (tab === "added" && row.draft) return <div><button onClick={onOrder} className="mb-2 rounded bg-slate-900 px-2 py-1 text-white">Edit quantity</button><button onClick={async () => { const response = await fetch(`/api/wholesale/opportunities/${row.opportunityId}/actions`, { method: "POST", headers: mutationHeaders({ "Content-Type": "application/json" }), body: JSON.stringify({ action: "remove_draft", orderCandidateId: row.draft?.id }) }); if (response.ok) location.reload(); }} className="block text-red-700 underline">Remove draft</button></div>;
  return <div className="space-y-2"><button disabled={!row.evaluationId || row.status !== "ready_for_review"} onClick={onOrder} className="inline-flex items-center gap-1 rounded bg-slate-900 px-2 py-1 text-white disabled:bg-slate-300"><ShoppingCart className="h-3 w-3"/>Add to Order</button><select value={reason} onChange={event => setReason(event.target.value)} className="block w-40 rounded border p-1"><PassOptions/></select><button onClick={() => void onDecision(row, hardReason(reason) ? "hard_pass" : "temporary_pass", reason)} className="rounded border px-2 py-1">Pass</button></div>;
}

function PassOptions() { return <><option value="low_profitability">Low Profitability</option><option value="price_risk">Price Risk</option><option value="too_much_inventory">Too Much Inventory</option><option value="competition">Competition</option><option value="other">Other</option><option value="listing_asin_issue">Listing/ASIN Issue</option><option value="restricted_cant_sell">Restricted / Can&apos;t Sell</option></>; }

function OrderDialog({ row, onClose, onSaved, setError }: { row: Row; onClose: () => void; onSaved: () => Promise<void>; setError: (value: string | null) => void }) {
  const [quantity, setQuantity] = useState(row.draft?.quantity ?? Math.max(1, Math.floor(row.purchaseCapacity ?? 1)));
  const resultingSupply = row.expectedMonthlySales && row.expectedMonthlySales > 0 ? ((row.fbaUnits + row.inboundUnits + quantity) / row.expectedMonthlySales) * 30 : null;
  async function save() { const response = await fetch(`/api/wholesale/opportunities/${row.opportunityId}/actions`, { method: "POST", headers: mutationHeaders({ "Content-Type": "application/json" }), body: JSON.stringify({ action: "add_to_order", evaluationId: row.evaluationId, quantity, requestId: crypto.randomUUID() }) }); const payload = await response.json(); if (!response.ok) { setError(payload.error || "Could not save draft commitment."); return; } await onSaved(); }
  return <Modal title="Add to Order" onClose={onClose}><div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm"><Metric label="Supplier availability" value={row.availabilityRaw ?? "Unknown"}/><Metric label="Unit cost" value={money(row.supplierCost)}/><Metric label="Monthly velocity" value={units(row.expectedMonthlySales)}/><Metric label="30-day target" value={units(row.targetUnits)}/><Metric label="FBA / inbound" value={`${row.fbaUnits} / ${row.inboundUnits}`}/><Metric label="Existing draft" value={units(row.draftUnits)}/><Metric label="30-day capacity" value={units(row.purchaseCapacity)}/></div><label className="mt-4 block text-sm font-medium">Quantity to order<input autoFocus type="number" min={1} step={1} value={quantity} onChange={event => setQuantity(Number(event.target.value))} className="mt-1 block w-full rounded border border-slate-300 p-2"/></label><div className="mt-3 rounded bg-slate-100 p-3 text-sm"><Metric label="Extended supplier cost" value={row.supplierCost === null ? "Unknown" : money(row.supplierCost * quantity)}/><Metric label="Resulting approximate supply" value={resultingSupply === null ? "Unknown" : `${resultingSupply.toFixed(0)} days`}/><p className="mt-2 text-xs text-slate-500">Capacity is guidance. Exact supplier availability is enforced by the server; “144+” is a lower bound.</p></div><div className="mt-4 flex justify-end gap-2"><button onClick={onClose} className="rounded border px-3 py-2">Cancel</button><button disabled={!Number.isInteger(quantity) || quantity <= 0} onClick={() => void save()} className="rounded bg-slate-900 px-3 py-2 text-white disabled:bg-slate-300">Save draft commitment</button></div></Modal>;
}

function CandidateDialog({ row, onClose, onSaved, setError }: { row: Row; onClose: () => void; onSaved: () => Promise<void>; setError: (value: string | null) => void }) {
  const [candidates, setCandidates] = useState<Candidate[]>([]); const [loading, setLoading] = useState(true); const [recalculating, setRecalculating] = useState(false);
  useEffect(() => { fetch(`/api/wholesale/products/${row.supplierProductId}/matching?marketplaceId=ATVPDKIKX0DER`, { cache: "no-store" }).then(async response => { const payload = await response.json(); if (!response.ok) throw new Error(payload.error); setCandidates(payload.candidates || []); }).catch(reason => setError(String(reason))).finally(() => setLoading(false)); }, [row.supplierProductId, setError]);
  async function choose(asin: string) {
    setRecalculating(true);
    const response = await fetch(`/api/wholesale/products/${row.supplierProductId}/matching`, { method: "POST", headers: mutationHeaders({ "Content-Type": "application/json" }), body: JSON.stringify({ action: "select_candidate", marketplaceId: "ATVPDKIKX0DER", asin }) });
    const payload = await response.json();
    if (!response.ok) { setError(payload.error || "Candidate selection failed."); setRecalculating(false); return; }
    for (let attempt = 0; attempt < 15; attempt += 1) {
      await new Promise(resolve => setTimeout(resolve, 3000));
      const statusResponse = await fetch(`/api/wholesale/opportunities/${row.opportunityId}`, { cache: "no-store" });
      const status = await statusResponse.json();
      if (statusResponse.ok && status.opportunity?.evaluation_requested === false && status.evaluation?.asin === asin) { await onSaved(); return; }
    }
    setError("The candidate was selected, but recalculation is still running. Reload the queue shortly to see the new economics.");
    setRecalculating(false);
  }
  return <Modal title="Compare Amazon candidates" onClose={onClose} wide>{recalculating ? <div className="mb-3 rounded border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900">The candidate was selected. Recalculating economics from cached evidence...</div> : null}{loading ? <div>Loading...</div> : <div className="max-h-[70vh] overflow-auto"><table className="min-w-[1300px] w-full text-left text-sm"><thead><tr><Th>Listing</Th><Th>Identity</Th><Th>Prices</Th><Th>Match evidence</Th><Th>Prior sales</Th><Th>Velocity</Th><Th>Eligibility</Th><Th></Th></tr></thead><tbody>{candidates.map(candidate => <tr key={candidate.candidate_id} className={`border-t align-top ${candidate.asin === row.asin ? "bg-emerald-50" : ""}`}><Td><div className="flex gap-2">{candidate.image_url ? <img src={candidate.image_url} alt="" className="h-16 w-16 object-contain"/> : null}<div><div className="font-semibold">{candidate.title ?? "Amazon title unavailable"}</div><a className="text-blue-700 underline" target="_blank" href={`https://www.amazon.com/dp/${candidate.asin}`}>{candidate.asin}</a>{candidate.asin === row.asin ? <div className="font-semibold text-emerald-700">Currently selected</div> : null}</div></div></Td><Td>{[candidate.platform, candidate.edition, candidate.region, candidate.format, candidate.product_type].filter(Boolean).join(" · ") || "Unknown"}<div className="mt-1 text-xs text-slate-500">{label(candidate.compatibility_status)} · {candidate.compatibility_reason_codes.join(", ") || "no reason codes"}</div></Td><Td><Metric label="Current" value={money(candidate.current_buy_box)}/><Metric label="90-day avg" value={money(candidate.keepa_avg90)}/></Td><Td>{candidate.match_sources.join(", ") || "Unknown"}<div className="mt-1 text-xs text-slate-500">Rank {candidate.rank_position ?? "?"} · {rationale(candidate.ranking_rationale)}</div></Td><Td>{candidate.prior_account_sale ? "Yes" : "No"}</Td><Td>{candidate.keepa_sales_rank_drops90 ?? "Unknown"}</Td><Td>{label(candidate.eligibility_status)}</Td><Td><button disabled={recalculating || candidate.compatibility_status !== "compatible" || candidate.eligibility_status !== "eligible" || candidate.asin === row.asin} onClick={() => void choose(candidate.asin)} className="rounded bg-slate-900 px-2 py-1 text-white disabled:bg-slate-300">Select and recalculate</button></Td></tr>)}</tbody></table></div>}<div className="mt-4 flex justify-end"><button onClick={onClose} className="rounded border px-3 py-2">Close</button></div></Modal>;
}

function AmazonIdentity({ row }: { row: Row }) { return <div className="flex gap-2">{row.imageUrl ? <img src={row.imageUrl} alt="" className="h-16 w-16 object-contain"/> : null}<div><div className="font-semibold">{row.amazonTitle ?? "Pending match"}</div>{row.asin ? <a className="inline-flex items-center gap-1 text-blue-700 underline" href={`https://www.amazon.com/dp/${row.asin}`} target="_blank">{row.asin}<ExternalLink className="h-3 w-3"/></a> : null}<div>{row.amazonPlatform ?? ""}</div><div>Eligibility: {label(row.eligibilityStatus)}</div>{row.priorAccountSale ? <div className="font-semibold text-blue-700">Prior account sale</div> : null}</div></div>; }
function SupplierHistory({ row }: { row: Row }) { return <><Metric label="Current" value={money(row.supplierCost)}/><Metric label="Previous" value={money(row.previousSupplierPrice)}/><Metric label="Historical low" value={money(row.supplierHistoricalLow)}/><Metric label="30-day change" value={percent(row.supplierPriceChange30d)}/><Metric label="90-day change" value={percent(row.supplierPriceChange90d)}/></>; }
function RoiPanel({ row, basis }: { row: Row; basis: "current" | "average" }) { const average = basis === "average"; const price = average ? row.keepaAvg90 : row.currentBuyBox; const roi = average ? row.avg90Roi : row.currentRoi; return <><div className="text-base font-semibold">{money(price)}</div>{average ? <Metric label="30-day avg" value={money(row.keepaAvg30)}/> : null}<Metric label="Amazon fees" value={money(average ? row.avg90Fees : row.currentFees)}/><Metric label="True profit" value={money(average ? row.avg90Profit : row.currentProfit)}/><Metric label="True ROI" value={percent(roi)} strong={qualifies(roi)}/><Metric label="25% ROI floor" value={money(average ? row.avg90RoiFloor : row.roiFloor)}/>{average ? <div className="mt-1 font-semibold">Qualifies: {qualification(row.qualificationBasis)}</div> : null}</>; }
function CostPanel({ row }: { row: Row }) { return <><Metric label="Inbound" value={money(row.inboundAllowance)}/><Metric label="Returns" value={money(row.returnAllowance)}/><Metric label="30-day storage" value={money(row.storageAllowance)}/><Metric label="Current headroom" value={percent(row.priceHeadroom)}/>{row.allowanceStatus === "accessory_review_required" ? <div className="mt-1 text-amber-700">Accessory costs need review</div> : null}</>; }
function InventoryPanel({ row }: { row: Row }) { return <><Metric label="Monthly velocity" value={units(row.expectedMonthlySales)}/><Metric label="FBA" value={units(row.fbaUnits)}/><Metric label="Inbound" value={units(row.inboundUnits)}/><Metric label="Draft" value={units(row.draftUnits)}/><Metric label="30-day target" value={units(row.targetUnits)}/><div className="mt-1 font-semibold">Capacity: {units(row.purchaseCapacity)}</div></>; }
function RiskPanel({ row }: { row: Row }) { return <><Metric label="Amazon 30d" value={percent(asNumber(row.riskSignals.amazon_price_change_30d))}/><Metric label="Amazon 90d" value={percent(asNumber(row.riskSignals.amazon_price_change_90d))}/><Metric label="Direction" value={String(row.riskSignals.amazon_price_trend ?? "Unknown")}/><Metric label="Offers" value={row.offerCount === null ? "Unknown" : String(row.offerCount)}/><Metric label="FBA sellers" value={row.fbaSellerCount === null ? "Not available" : `${row.fbaSellerCount}*`}/>{row.riskSignals.supplier_amazon_divergence ? <div className="mt-2 rounded bg-amber-100 p-1.5 text-amber-800">Supplier price is declining substantially faster than Amazon market price.</div> : null}</>; }
function Modal({ title, onClose, children, wide = false }: { title: string; onClose: () => void; children: React.ReactNode; wide?: boolean }) { return <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/40 p-6" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}><div className={`w-full ${wide ? "max-w-[1500px]" : "max-w-4xl"} rounded-lg bg-white p-5 shadow-xl`}><div className="mb-4 flex items-center justify-between"><h2 className="text-lg font-semibold">{title}</h2><button onClick={onClose} aria-label="Close"><X className="h-5 w-5"/></button></div>{children}</div></div>; }
function Th({ children }: { children?: React.ReactNode }) { return <th className="px-3 py-2 font-semibold">{children}</th>; }
function Td({ children }: { children: React.ReactNode }) { return <td className="px-3 py-3">{children}</td>; }
function Metric({ label: name, value, strong = false }: { label: string; value: string; strong?: boolean }) { return <div className={strong ? "font-semibold text-emerald-700" : ""}><span className="text-slate-500">{name}: </span>{value}</div>; }
function money(value: number | null) { return value === null ? "Unknown" : new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value); }
function percent(value: number | null) { return value === null ? "Unknown" : `${(value * 100).toFixed(1)}%`; }
function units(value: number | null) { return value === null ? "Unknown" : Number(value).toFixed(value % 1 ? 1 : 0); }
function qualifies(value: number | null) { return value !== null && value >= .25; }
function qualification(value: string) { return ({ current_only: "Current Buy Box only", avg90_only: "90-day average only", both: "Both", neither: "Neither", incomplete: "Incomplete" } as Record<string, string>)[value] || value; }
function label(value: string | null) { return value ? value.replaceAll("_", " ") : "Pending"; }
function asNumber(value: unknown) { const parsed = Number(value); return value === null || value === undefined || !Number.isFinite(parsed) ? null : parsed; }
function hardReason(reason: string) { return reason.startsWith("listing_") || reason.startsWith("restricted_"); }
function rationale(value: Record<string, unknown>) { const entries = Object.entries(value ?? {}).filter(([, item]) => item !== null && item !== undefined && item !== false); return entries.length ? entries.map(([key, item]) => `${label(key)}: ${String(item)}`).join("; ") : "No ranking detail recorded"; }
function pendingExplanation(row: Row) { if (row.status === "pending_matching") return "Amazon matching is still running or needs manual candidate review."; if (row.status === "pending_eligibility") return "A candidate exists, but fresh Amazon listing eligibility evidence is not available yet."; if (row.status === "evaluation_incomplete") return `Economics are incomplete: ${row.incompleteReasons.map(label).join(", ") || "required evidence is missing"}.`; if (row.evaluationRequested) return "A newer evaluation has been requested and will replace these figures when the scheduler finishes."; return null; }
