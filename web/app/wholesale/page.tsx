"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ExternalLink, RefreshCw, ShoppingCart, X } from "lucide-react";
import { mutationHeaders } from "../mutationHeaders";

type Tab = "ready" | "order" | "full";
type Row = {
  opportunityId: string; evaluationId: string | null; supplierProductId: string; status: string;
  supplier: string; supplierTitle: string; system: string; rawIdentifier: string; availabilityRaw: string | null;
  supplierCost: number | null; previousSupplierPrice: number | null; supplierHistoricalLow: number | null;
  supplierPriceChange30d: number | null; supplierPriceChange90d: number | null; asin: string | null;
  amazonTitle: string | null; amazonPlatform: string | null; imageUrl: string | null; eligibilityStatus: string | null;
  currentBuyBox: number | null; keepaAvg30: number | null; keepaAvg90: number | null; keepaVelocity90: number | null;
  currentRoi: number | null; avg90Roi: number | null; expectedMonthlySales: number | null;
  fbaUnits: number; inboundUnits: number; draftUnits: number; targetUnits: number | null; purchaseCapacity: number | null;
  offerCount: number | null; fbaSellerCount: number | null; riskSignals: Record<string, unknown>;
  draft: { id: string; quantity: number; extendedCost: number | null; revision: number } | null;
};
type FullRow = {
  supplierProductId: string; opportunityId: string | null; evaluationId: string | null; supplier: string;
  supplierTitle: string; system: string; rawIdentifier: string; supplierCost: number | null; availabilityRaw: string | null;
  statusKey: string; statusLabel: string; statusDetail: string | null; asin: string | null; amazonTitle: string | null;
  currentBuyBox: number | null; keepaAvg90: number | null; currentRoi: number | null; avg90Roi: number | null;
  eligibilityStatus: string | null; purchaseCapacity: number | null; fbaUnits: number; inboundUnits: number;
  draft: { id: string; quantity: number; extendedCost: number | null } | null; passedAt: string | null; passReason: string | null;
};
type CandidateContext = { supplierProductId: string; opportunityId: string | null; supplier: string; supplierTitle: string; asin: string | null };
type MatchEvidence = { type: string; label: string; supplier_identifier?: string; amazon_identifiers?: string[];
  title_terms?: string; platform_term?: string; variant_label?: string; query?: string; amazon_title?: string; amazon_platform?: string };
type Candidate = {
  candidate_id: string; asin: string; title: string | null; image_url: string | null; platform: string | null;
  edition: string | null; region: string | null; format: string | null; product_type: string | null;
  current_buy_box: number | null; keepa_avg90: number | null; match_sources: string[]; compatibility_status: string;
  compatibility_reason_codes: string[]; compatibility_details: Record<string, unknown>; prior_account_sale: boolean;
  keepa_sales_rank_drops90: number | null; eligibility_status: string | null; eligibility_reason_codes: string[];
  rank_position: number | null; ranking_rationale: Record<string, unknown>; match_evidence: MatchEvidence[];
};
type ImportInfo = { importId: string; supplierId: string; supplier: string; effectiveDate: string; importedAt: string; productCount: number; revision?: number };

const tabs: Array<[Tab, string]> = [["ready", "Ready to Review"], ["order", "Order List"], ["full", "Full Import"]];
const fullFilters = [
  ["all", "All"], ["ready", "Ready to Review"], ["order_list", "Order List"], ["restricted", "Restricted"],
  ["unmatched", "Unmatched"], ["match_review", "Match Review Needed"], ["eligibility_pending", "Eligibility Pending"],
  ["pricing_pending", "Pricing / Keepa Pending"], ["roi_too_low", "ROI Too Low"], ["non_na", "Non-North-American Version"],
  ["listing_issue", "Listing / ASIN Issue"], ["unsupported_economics", "Unsupported Product Economics"],
  ["passed_too_much_inventory", "Passed — Too Much Inventory"], ["passed_price_risk", "Passed — Price Risk"],
  ["passed_competition", "Passed — Competition"], ["passed_other", "Passed — Other"],
];

export default function WholesalePage() {
  const [tab, setTab] = useState<Tab>("ready");
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [candidateRow, setCandidateRow] = useState<CandidateContext | null>(null);
  const [orderRow, setOrderRow] = useState<Row | null>(null);

  const load = useCallback(async () => {
    if (tab === "full") return;
    setLoading(true); setError(null);
    try {
      const response = await fetch(`/api/wholesale/opportunities?status=${tab}&pageSize=200`, { cache: "no-store" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Could not load wholesale workflow.");
      setRows(payload.rows ?? []);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not load wholesale workflow."); }
    finally { setLoading(false); }
  }, [tab]);
  useEffect(() => { void load(); }, [load]);

  async function decide(row: Row, reason: string, notes?: string) {
    if (!row.evaluationId) return;
    const action = reason === "listing_asin_issue" ? "hard_pass" : "temporary_pass";
    const response = await fetch(`/api/wholesale/opportunities/${row.opportunityId}/actions`, {
      method: "POST", headers: mutationHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ action, evaluationId: row.evaluationId, reason, notes: notes || null }),
    });
    const payload = await response.json();
    if (!response.ok) return setError(payload.error || "Decision could not be saved.");
    await load();
  }

  return <main className="p-5">
    <div className="mb-4 flex items-end justify-between"><div><h1 className="text-2xl font-semibold">Wholesale Purchasing</h1><p className="text-sm text-slate-600">Review qualified products, stage draft quantities, and audit complete supplier lists.</p></div><button onClick={() => void load()} className="inline-flex items-center gap-2 rounded border px-3 py-2 text-sm"><RefreshCw className="h-4 w-4"/>Refresh</button></div>
    <nav className="mb-4 flex gap-1 border-b">{tabs.map(([key, title]) => <button key={key} onClick={() => setTab(key)} className={`border-b-2 px-4 py-2 text-sm font-medium ${tab === key ? "border-slate-950 text-slate-950" : "border-transparent text-slate-500"}`}>{title}</button>)}</nav>
    {error ? <div className="mb-4 rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800">{error}</div> : null}
    {tab === "full" ? <FullImport onCandidates={setCandidateRow} setError={setError}/> : loading ? <div className="p-8 text-slate-500">Loading…</div> : <OpportunityTable rows={rows} tab={tab} onCandidates={setCandidateRow} onOrder={setOrderRow} onPass={decide} reload={load}/>}
    {candidateRow ? <CandidateDialog row={candidateRow} onClose={() => setCandidateRow(null)} onSaved={async () => { setCandidateRow(null); await load(); }} setError={setError}/> : null}
    {orderRow ? <OrderDialog row={orderRow} onClose={() => setOrderRow(null)} onSaved={async () => { setOrderRow(null); await load(); }} setError={setError}/> : null}
  </main>;
}

function OpportunityTable({ rows, tab, onCandidates, onOrder, onPass, reload }: { rows: Row[]; tab: "ready" | "order";
  onCandidates: (row: CandidateContext) => void; onOrder: (row: Row) => void; onPass: (row: Row, reason: string, notes?: string) => Promise<void>; reload: () => Promise<void> | void }) {
  if (!rows.length) return <div className="rounded border bg-white p-10 text-center text-slate-500">No products in {tab === "ready" ? "Ready to Review" : "Order List"}.</div>;
  return <div className="overflow-auto rounded border bg-white"><table className="min-w-[1750px] w-full text-left text-xs">
    <thead className="sticky top-0 bg-slate-100 text-slate-600"><tr><Th>Supplier Item</Th><Th>Amazon Match</Th><Th>Supplier Price</Th><Th>Current Buy Box</Th><Th>90-Day Average</Th><Th>Supplier History</Th><Th>Inventory / Capacity</Th><Th>Risk Signals</Th><Th>Actions</Th></tr></thead>
    <tbody>{rows.map(row => <tr key={row.opportunityId} className="border-t align-top">
      <Td><div className="font-semibold">{row.supplierTitle}</div><div>{row.supplier} · {row.system}</div><div className="text-slate-500">{row.rawIdentifier} · Available {row.availabilityRaw ?? "unknown"}</div></Td>
      <Td><AmazonMatch row={row}/><button className="mt-1 text-blue-700 underline" onClick={() => onCandidates(row)}>Review candidates</button></Td>
      <Td><div className="text-base font-semibold">{money(row.supplierCost)}</div>{tab === "order" && row.draft ? <><div>Qty {row.draft.quantity}</div><div>Extended {money(row.draft.extendedCost)}</div></> : null}</Td>
      <Td><div className="font-semibold">{money(row.currentBuyBox)}</div><div className={qualifies(row.currentRoi) ? "text-emerald-700" : ""}>ROI {percent(row.currentRoi)}</div></Td>
      <Td><div className="font-semibold">{money(row.keepaAvg90)}</div><div className={qualifies(row.avg90Roi) ? "text-emerald-700" : ""}>ROI {percent(row.avg90Roi)}</div><div className="text-slate-500">30d {money(row.keepaAvg30)}</div></Td>
      <Td><Metric label="Previous" value={money(row.previousSupplierPrice)}/><Metric label="Low" value={money(row.supplierHistoricalLow)}/><Metric label="30d" value={percent(row.supplierPriceChange30d)}/><Metric label="90d" value={percent(row.supplierPriceChange90d)}/></Td>
      <Td><Metric label="FBA / inbound / draft" value={`${row.fbaUnits} / ${row.inboundUnits} / ${row.draftUnits}`}/><Metric label="Velocity 90d" value={units(row.keepaVelocity90)}/><Metric label="Target" value={units(row.targetUnits)}/><strong>Capacity {units(row.purchaseCapacity)}</strong></Td>
      <Td><Metric label="Offers" value={row.offerCount === null ? "Unknown" : String(row.offerCount)}/><Metric label="FBA sellers" value={row.fbaSellerCount === null ? "Not available" : String(row.fbaSellerCount)}/><Metric label="Trend" value={String(row.riskSignals?.amazon_price_trend ?? "Unknown")}/></Td>
      <Td>{tab === "ready" ? <ReadyActions row={row} onOrder={() => onOrder(row)} onPass={onPass}/> : <OrderActions row={row} onEdit={() => onOrder(row)} reload={reload}/>}</Td>
    </tr>)}</tbody>
  </table></div>;
}

function FullImport({ onCandidates, setError }: { onCandidates: (row: CandidateContext) => void; setError: (value: string | null) => void }) {
  const [rows, setRows] = useState<FullRow[]>([]); const [imports, setImports] = useState<ImportInfo[]>([]);
  const [selected, setSelected] = useState<ImportInfo | null>(null); const [supplierId, setSupplierId] = useState("");
  const [importId, setImportId] = useState(""); const [filter, setFilter] = useState("all"); const [system, setSystem] = useState("");
  const [search, setSearch] = useState(""); const [searchInput, setSearchInput] = useState(""); const [systems, setSystems] = useState<string[]>([]); const [total, setTotal] = useState(0); const [page, setPage] = useState(1); const [loading, setLoading] = useState(true);
  const activeRequest = useRef<AbortController | null>(null);
  const load = useCallback(async () => {
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    setLoading(true); const params = new URLSearchParams({ pageSize: "200", filter, page: String(page) });
    if (supplierId) params.set("supplierId", supplierId); if (importId) params.set("importId", importId);
    if (system) params.set("system", system); if (search) params.set("search", search);
    try { const response = await fetch(`/api/wholesale/full-import?${params}`, { cache: "no-store", signal: controller.signal }); const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Could not load supplier list.");
      if (controller.signal.aborted) return;
      setRows(payload.rows ?? []); setImports(payload.imports ?? []); setSelected(payload.selectedImport ?? null); setSystems(payload.systems ?? []); setTotal(payload.total ?? 0);
      if (!importId && payload.selectedImport?.importId) setImportId(payload.selectedImport.importId);
    } catch (reason) {
      if (!(reason instanceof DOMException && reason.name === "AbortError")) setError(reason instanceof Error ? reason.message : "Could not load supplier list.");
    } finally {
      if (activeRequest.current === controller) { activeRequest.current = null; setLoading(false); }
    }
  }, [filter, importId, page, search, setError, supplierId, system]);
  useEffect(() => { void load(); return () => activeRequest.current?.abort(); }, [load]);
  const suppliers = Array.from(new Map(imports.map(item => [item.supplierId, item.supplier])).entries());
  return <div className="space-y-4">
    <div className="rounded border bg-white p-4"><div className="grid gap-3 lg:grid-cols-5">
      <label className="text-xs font-medium">Supplier<select value={supplierId} onChange={event => { setSupplierId(event.target.value); setImportId(""); setPage(1); }} className="mt-1 block w-full rounded border p-2 text-sm"><option value="">All suppliers</option>{suppliers.map(([id,name]) => <option key={id} value={id}>{name}</option>)}</select></label>
      <label className="text-xs font-medium">Supplier list date<select value={importId} onChange={event => { setImportId(event.target.value); setPage(1); }} className="mt-1 block w-full rounded border p-2 text-sm">{imports.map(item => <option key={item.importId} value={item.importId}>{item.effectiveDate} · {item.supplier}{item.revision && item.revision > 1 ? ` · rev ${item.revision}` : ""}</option>)}</select></label>
      <label className="text-xs font-medium">Status<select value={filter} onChange={event => { setFilter(event.target.value); setPage(1); }} className="mt-1 block w-full rounded border p-2 text-sm">{fullFilters.map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <label className="text-xs font-medium">System<select value={system} onChange={event => { setSystem(event.target.value); setPage(1); }} className="mt-1 block w-full rounded border p-2 text-sm"><option value="">All systems</option>{systems.map(value => <option key={value}>{value}</option>)}</select></label>
      <label className="text-xs font-medium">Search<div className="mt-1 flex"><input value={searchInput} onChange={event => setSearchInput(event.target.value)} onKeyDown={event => { if (event.key === "Enter") { setSearch(searchInput); setPage(1); } }} placeholder="Title, UPC, ASIN" className="block min-w-0 flex-1 rounded-l border p-2 text-sm"/><button onClick={() => { setSearch(searchInput); setPage(1); }} className="rounded-r border border-l-0 px-2 text-sm">Go</button></div></label>
    </div>{selected ? <div className="mt-3 flex flex-wrap gap-5 text-sm"><strong>{selected.supplier}</strong><span>Effective list date: {dateValue(selected.effectiveDate)}</span><span>Imported: {dateTime(selected.importedAt)}</span><span>Products: {selected.productCount}</span><span>Filtered results: {total}</span>{loading ? <span role="status" className="text-blue-700">Updating results...</span> : null}</div> : null}</div>
    {loading && !selected ? <div className="p-8 text-slate-500">Loading complete import...</div> : <><div aria-busy={loading} className={`overflow-auto rounded border bg-white ${loading ? "opacity-70" : ""}`}> <table className="min-w-[1450px] w-full text-left text-xs"><thead className="bg-slate-100"><tr><Th>Supplier Item</Th><Th>Current Status / Reason</Th><Th>Amazon Match</Th><Th>Supplier Price</Th><Th>Current Buy Box</Th><Th>90-Day Average</Th><Th>Inventory / Capacity</Th><Th>Actions</Th></tr></thead><tbody>{rows.map(row => <tr key={row.supplierProductId} className="border-t align-top"><Td><strong>{row.supplierTitle}</strong><div>{row.supplier} · {row.system}</div><div className="text-slate-500">{row.rawIdentifier} · Available {row.availabilityRaw ?? "unknown"}</div></Td><Td><div className="font-semibold">{row.statusLabel}</div>{row.passedAt ? <div>Passed {dateOnly(row.passedAt)}</div> : null}{row.statusDetail ? <div className="text-slate-500">{row.statusDetail}</div> : null}</Td><Td><div className="font-semibold">{row.amazonTitle ?? "No selected Amazon listing"}</div>{row.asin ? <AmazonLink asin={row.asin}/> : null}<div>Eligibility: {humanLabel(row.eligibilityStatus)}</div></Td><Td>{money(row.supplierCost)}</Td><Td>{money(row.currentBuyBox)}<div>ROI {percent(row.currentRoi)}</div></Td><Td>{money(row.keepaAvg90)}<div>ROI {percent(row.avg90Roi)}</div></Td><Td><Metric label="FBA / inbound" value={`${row.fbaUnits} / ${row.inboundUnits}`}/><Metric label="Capacity" value={units(row.purchaseCapacity)}/>{row.draft ? <Metric label="Order List qty" value={String(row.draft.quantity)}/> : null}</Td><Td><button className="text-blue-700 underline" onClick={() => onCandidates(row)}>Review candidates</button>{row.opportunityId && row.evaluationId && (row.statusKey.startsWith("passed_") || row.statusKey === "listing_issue") ? <button className="mt-2 block rounded border px-2 py-1" onClick={() => void reconsider(row, load, setError)}>Reconsider</button> : null}</Td></tr>)}</tbody></table></div><div className="flex items-center justify-end gap-3 text-sm"><button disabled={loading || page === 1} onClick={() => setPage(value => value - 1)} className="rounded border px-3 py-1 disabled:text-slate-300">Previous</button><span>Page {page} of {Math.max(1, Math.ceil(total / 200))}</span><button disabled={loading || page * 200 >= total} onClick={() => setPage(value => value + 1)} className="rounded border px-3 py-1 disabled:text-slate-300">Next</button></div></>}
  </div>;
}

async function reconsider(row: FullRow, reload: () => Promise<void>, setError: (value: string | null) => void) {
  const response = await fetch(`/api/wholesale/opportunities/${row.opportunityId}/actions`, { method: "POST", headers: mutationHeaders({ "Content-Type": "application/json" }), body: JSON.stringify({ action: "reverse_pass", evaluationId: row.evaluationId }) });
  const payload = await response.json(); if (!response.ok) return setError(payload.error || "Could not reconsider product."); await reload();
}

function ReadyActions({ row, onOrder, onPass }: { row: Row; onOrder: () => void; onPass: (row: Row, reason: string, notes?: string) => Promise<void> }) {
  const [reason, setReason] = useState("too_much_inventory"); const [notes, setNotes] = useState("");
  return <div className="space-y-2"><button onClick={onOrder} className="inline-flex items-center gap-1 rounded bg-slate-900 px-2 py-1 text-white"><ShoppingCart className="h-3 w-3"/>Add to Order List</button><select value={reason} onChange={event => setReason(event.target.value)} className="block w-44 rounded border p-1"><option value="too_much_inventory">Too Much Inventory</option><option value="price_risk">Price Risk</option><option value="competition">Competition</option><option value="listing_asin_issue">Listing / ASIN Issue</option><option value="other">Other</option></select>{reason === "other" ? <input value={notes} onChange={event => setNotes(event.target.value)} placeholder="Optional note" className="block w-44 rounded border p-1"/> : null}<button onClick={() => void onPass(row, reason, notes)} className="rounded border px-2 py-1">Pass</button></div>;
}
function OrderActions({ row, onEdit, reload }: { row: Row; onEdit: () => void; reload: () => Promise<void> | void }) {
  return <div><button onClick={onEdit} className="mb-2 rounded bg-slate-900 px-2 py-1 text-white">Edit quantity</button><button onClick={async () => { const response = await fetch(`/api/wholesale/opportunities/${row.opportunityId}/actions`, { method: "POST", headers: mutationHeaders({ "Content-Type": "application/json" }), body: JSON.stringify({ action: "remove_draft", orderCandidateId: row.draft?.id }) }); if (response.ok) await reload(); }} className="block text-red-700 underline">Remove from Order List</button></div>;
}
function OrderDialog({ row, onClose, onSaved, setError }: { row: Row; onClose: () => void; onSaved: () => Promise<void>; setError: (value: string | null) => void }) {
  const [quantity, setQuantity] = useState(row.draft?.quantity ?? Math.max(1, Math.floor(row.purchaseCapacity ?? 1)));
  async function save() { const response = await fetch(`/api/wholesale/opportunities/${row.opportunityId}/actions`, { method: "POST", headers: mutationHeaders({ "Content-Type": "application/json" }), body: JSON.stringify({ action: "add_to_order", evaluationId: row.evaluationId, quantity, requestId: crypto.randomUUID() }) }); const payload = await response.json(); if (!response.ok) return setError(payload.error || "Could not save Order List quantity."); await onSaved(); }
  return <Modal title="Order List quantity" onClose={onClose}><div className="mb-3 font-semibold">{row.supplier} · {row.supplierTitle}</div><div className="grid grid-cols-2 gap-2 text-sm"><Metric label="ASIN" value={row.asin ?? "Unknown"}/><Metric label="Unit price" value={money(row.supplierCost)}/><Metric label="Available" value={row.availabilityRaw ?? "Unknown"}/><Metric label="Capacity" value={units(row.purchaseCapacity)}/></div><label className="mt-4 block text-sm font-medium">Requested quantity<input autoFocus type="number" min={1} step={1} value={quantity} onChange={event => setQuantity(Number(event.target.value))} className="mt-1 block w-full rounded border p-2"/></label><div className="mt-3">Extended cost: {row.supplierCost === null ? "Unknown" : money(row.supplierCost * quantity)}</div><p className="mt-2 text-xs text-slate-500">This saves a draft commitment only. It does not create a supplier purchase order.</p><div className="mt-4 flex justify-end gap-2"><button onClick={onClose} className="rounded border px-3 py-2">Cancel</button><button disabled={!Number.isInteger(quantity) || quantity <= 0} onClick={() => void save()} className="rounded bg-slate-900 px-3 py-2 text-white disabled:bg-slate-300">Save to Order List</button></div></Modal>;
}

function CandidateDialog({ row, onClose, onSaved, setError }: { row: CandidateContext; onClose: () => void; onSaved: () => Promise<void>; setError: (value: string | null) => void }) {
  const [candidates, setCandidates] = useState<Candidate[]>([]); const [loading, setLoading] = useState(true); const [saving, setSaving] = useState(false);
  useEffect(() => { fetch(`/api/wholesale/products/${row.supplierProductId}/matching?marketplaceId=ATVPDKIKX0DER`, { cache: "no-store" }).then(async response => { const payload = await response.json(); if (!response.ok) throw new Error(payload.error); setCandidates(payload.candidates ?? []); }).catch(reason => setError(String(reason))).finally(() => setLoading(false)); }, [row.supplierProductId, setError]);
  async function choose(asin: string) { setSaving(true); const response = await fetch(`/api/wholesale/products/${row.supplierProductId}/matching`, { method: "POST", headers: mutationHeaders({ "Content-Type": "application/json" }), body: JSON.stringify({ action: "select_candidate", marketplaceId: "ATVPDKIKX0DER", asin }) }); const payload = await response.json(); if (!response.ok) { setSaving(false); return setError(payload.error || "Candidate selection failed."); } if (row.opportunityId) { for (let attempt = 0; attempt < 15; attempt += 1) { await new Promise(resolve => setTimeout(resolve, 3000)); const statusResponse = await fetch(`/api/wholesale/opportunities/${row.opportunityId}`, { cache: "no-store" }); const status = await statusResponse.json(); if (statusResponse.ok && status.opportunity?.evaluation_requested === false && status.evaluation?.asin === asin) break; } } await onSaved(); }
  return <Modal title="Compare Amazon candidates" onClose={onClose} wide><div className="mb-3 rounded bg-slate-100 p-3 text-sm"><strong>{row.supplier}</strong> · {row.supplierTitle}</div>{loading ? <div>Loading…</div> : <div className="max-h-[72vh] overflow-auto"><table className="min-w-[1650px] w-full text-left text-sm"><thead><tr><Th>Amazon Listing</Th><Th>Platform / Version</Th><Th>Match Evidence</Th><Th>Compatibility</Th><Th>Prior Sales</Th><Th>Velocity</Th><Th>Prices</Th><Th>Eligibility</Th><Th>Selection</Th></tr></thead><tbody>{candidates.map(candidate => <tr key={candidate.candidate_id} className={`border-t align-top ${candidate.asin === row.asin ? "bg-emerald-50" : ""}`}><Td><div className="flex gap-2">{candidate.image_url ? <img src={candidate.image_url} alt="" className="h-16 w-16 object-contain"/> : null}<div><strong>{candidate.title ?? "Amazon title unavailable"}</strong><div><AmazonLink asin={candidate.asin}/></div></div></div></Td><Td>{[candidate.platform, candidate.edition, candidate.region, candidate.format, candidate.product_type].filter(Boolean).join(" · ") || "Unknown"}</Td><Td><Evidence candidate={candidate}/></Td><Td>{compatibilityText(candidate)}</Td><Td>{candidate.prior_account_sale ? "Yes" : "No"}</Td><Td>{candidate.keepa_sales_rank_drops90 ?? "Unknown"}</Td><Td><Metric label="Current Buy Box" value={money(candidate.current_buy_box)}/><Metric label="90-day average" value={money(candidate.keepa_avg90)}/></Td><Td><strong>{eligibilityText(candidate.eligibility_status)}</strong>{candidate.eligibility_reason_codes?.length ? <div className="text-xs text-slate-500">{candidate.eligibility_reason_codes.map(humanLabel).join(", ")}</div> : null}</Td><Td>{candidate.asin === row.asin ? <strong className="text-emerald-700">Selected</strong> : <button disabled={saving || candidate.compatibility_status !== "compatible" || candidate.eligibility_status !== "eligible"} onClick={() => void choose(candidate.asin)} className="rounded bg-slate-900 px-2 py-1 text-white disabled:bg-slate-300">Select</button>}<div className="mt-1 text-xs text-slate-500">Rank {candidate.rank_position ?? "?"}</div></Td></tr>)}</tbody></table></div>}<div className="mt-4 flex justify-end"><button onClick={onClose} className="rounded border px-3 py-2">Close</button></div></Modal>;
}
function Evidence({ candidate }: { candidate: Candidate }) {
  const hasIdentifier = candidate.match_evidence.some(item => item.type === "identifier"); const hasTitlePlatform = candidate.match_evidence.some(item => item.type === "title_platform"); const hasTitle = candidate.match_evidence.some(item => item.type === "title");
  const heading = hasIdentifier && hasTitlePlatform ? "Matched by UPC + Title/Platform" : hasIdentifier && hasTitle ? "Matched by UPC + Title" : hasIdentifier ? candidate.match_evidence.find(item => item.type === "identifier")?.label : hasTitlePlatform ? "Matched by Title + Platform" : "Matched by Title";
  return <div><strong>{heading}</strong>{candidate.match_evidence.map((evidence, index) => evidence.type === "identifier" ? <div key={index} className="mt-1 text-xs"><div>Supplier identifier: {evidence.supplier_identifier ?? "Unknown"}</div><div>Amazon identifier: {evidence.amazon_identifiers?.join(", ") || "Not returned"}</div></div> : <div key={index} className="mt-1 text-xs"><div>Search title: {evidence.title_terms ?? evidence.query ?? "Unknown"}</div>{evidence.platform_term ? <div>Platform: {evidence.platform_term}</div> : null}<div>Search variant: {evidence.variant_label ?? "Legacy title search"}</div><div>Amazon result: {evidence.amazon_title ?? "Unknown"}</div><div>Amazon platform: {evidence.amazon_platform ?? "Unknown"}</div></div>)}</div>;
}
function compatibilityText(candidate: Candidate) {
  const codes = new Set(candidate.compatibility_reason_codes ?? []);
  if (candidate.compatibility_status === "compatible") return codes.has("identifier_and_platform_compatible") ? "Compatible — identifier and platform align" : "Compatible — title and platform align";
  if (codes.has("platform_mismatch")) return "Not compatible — different platform";
  if (codes.has("installment_mismatch")) return "Not compatible — different sequel or title number";
  if (codes.has("title_mismatch")) return "Not compatible — different title";
  if (codes.has("region_mismatch")) return "Not compatible — EU/non-NA version";
  if (codes.has("digital_physical_mismatch")) return "Not compatible — digital vs physical mismatch";
  if (codes.has("accessory_type_mismatch")) return "Not compatible — accessory vs game mismatch";
  if (codes.has("edition_mismatch")) return "Review needed — edition unclear";
  if (codes.has("region_evidence_incomplete")) return "Review needed — region unclear";
  return candidate.compatibility_status === "incompatible" ? "Not compatible — identity differs" : "Review needed — identity evidence is incomplete";
}
function eligibilityText(value: string | null) { if (value === "eligible") return "Eligible for New condition"; if (value === "restricted") return "Restricted for New condition"; if (value === "unknown" || value === "error") return "Eligibility unresolved"; return "Eligibility pending"; }
function AmazonMatch({ row }: { row: Row }) { return <div className="flex gap-2">{row.imageUrl ? <img src={row.imageUrl} alt="" className="h-14 w-14 object-contain"/> : null}<div><strong>{row.amazonTitle ?? "Pending match"}</strong>{row.asin ? <div><AmazonLink asin={row.asin}/></div> : null}<div>{row.amazonPlatform}</div><div>{eligibilityText(row.eligibilityStatus)}</div></div></div>; }
function AmazonLink({ asin }: { asin: string }) { return <a className="inline-flex items-center gap-1 text-blue-700 underline" target="_blank" href={`https://www.amazon.com/dp/${asin}`}>{asin}<ExternalLink className="h-3 w-3"/></a>; }
function Modal({ title, onClose, children, wide = false }: { title: string; onClose: () => void; children: React.ReactNode; wide?: boolean }) { return <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/40 p-6" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}><div className={`w-full ${wide ? "max-w-[1650px]" : "max-w-3xl"} rounded-lg bg-white p-5 shadow-xl`}><div className="mb-4 flex items-center justify-between"><h2 className="text-lg font-semibold">{title}</h2><button onClick={onClose} aria-label="Close"><X className="h-5 w-5"/></button></div>{children}</div></div>; }
function Th({ children }: { children?: React.ReactNode }) { return <th className="px-3 py-2 font-semibold">{children}</th>; }
function Td({ children }: { children: React.ReactNode }) { return <td className="px-3 py-3">{children}</td>; }
function Metric({ label, value }: { label: string; value: string }) { return <div><span className="text-slate-500">{label}: </span>{value}</div>; }
function money(value: number | null) { return value === null ? "Unknown" : new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value); }
function percent(value: number | null) { return value === null ? "Unknown" : `${(value * 100).toFixed(1)}%`; }
function units(value: number | null) { return value === null ? "Unknown" : Number(value).toFixed(value % 1 ? 1 : 0); }
function qualifies(value: number | null) { return value !== null && value >= .25; }
function humanLabel(value: string | null) { return value ? value.replaceAll("_", " ") : "Pending"; }
function dateOnly(value: string) { return new Intl.DateTimeFormat("en-US", { dateStyle: "medium" }).format(new Date(value)); }
function dateValue(value: string) { return new Intl.DateTimeFormat("en-US", { dateStyle: "medium", timeZone: "UTC" }).format(new Date(`${value.slice(0, 10)}T00:00:00Z`)); }
function dateTime(value: string) { return new Intl.DateTimeFormat("en-US", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)); }
