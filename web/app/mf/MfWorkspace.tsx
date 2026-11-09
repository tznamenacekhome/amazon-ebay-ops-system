"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { mutationHeaders } from "../mutationHeaders";
import { runOnDemandRefresh, type RefreshNotice } from "../syncRefresh";
type Row = Record<string, unknown> & {
    id?: string;
    seller_sku: string;
    condition: string;
    asin?: string;
    title?: string;
    keep_mf?: boolean;
    stale_sync?: boolean;
    unmatched_sku?: boolean;
    verification_state?: string;
    anomaly?: string;
    replacement_for?: {
        order_id: string;
    }[];
};
type Account = {
    stale: boolean;
    id: string;
    seller_id: string;
    marketplace_id: string;
    revision: number;
    last_success_at: string | null;
    last_attempt_at: string | null;
    last_error: string | null;
};
type Payload = {
    account: Account | null;
    rows: Row[];
    total: number;
    runs: {
        id: string;
        status: string;
        started_at: string;
        error: string | null;
    }[];
    error?: string;
};
const button = "rounded border border-slate-300 bg-white px-3 py-2 text-sm disabled:opacity-50", input = "rounded border border-slate-300 px-2 py-2", td = "border-t border-slate-100 px-3 py-2 align-top";
const val = (v: unknown) => v === null || v === undefined ? "Unknown" : String(v);
const date = (v: unknown) => typeof v === "string" ? new Date(v).toLocaleString() : "Never";
const inventoryColumns: [
    [
        string,
        string
    ],
    ...[
        string,
        string
    ][]
] = [["amazon_listed_quantity", "Amazon listed"], ["on_hand", "MBOP on hand"], ["order_reserved", "Order reserved"], ["inspection_held", "Inspection held"], ["fba_transfer_allocation", "FBA allocated"], ["available", "Available"], ["quantity_difference", "Difference"]];
const orderColumns: [
    [
        string,
        string
    ],
    ...[
        string,
        string
    ][]
] = [["ordered", "Ordered"], ["shipped", "Shipped"], ["baseline_shipped", "Before tracking"], ["reserved", "Reserved"], ["reservation_demand", "Reserve demand"], ["stock_removed", "Physical removed"], ["reservation_shortage", "Reserve shortage"], ["shipment_shortage", "Shipment shortage"]];
export function MfWorkspace({ view }: {
    view: "inventory" | "orders";
}) {
    const [data, setData] = useState<Payload | null>(null), [error, setError] = useState(""), [search, setSearch] = useState(""), [page, setPage] = useState(0), [busy, setBusy] = useState(false), [notice, setNotice] = useState<RefreshNotice | null>(null);
    const [stock, setStock] = useState("in_stock");
    const [opening, setOpening] = useState<Row | null>(null), [count, setCount] = useState(""), [cost, setCost] = useState(""), [notes, setNotes] = useState("");
    const [lots, setLots] = useState<Row[] | null>(null), [detailSku, setDetailSku] = useState("");
    const readVersion = useRef(0);
    const attempt = useRef<{
        id: string;
        payload: string;
    } | null>(null);
    const load = useCallback(async () => { const version = ++readVersion.current; try {
        const r = await fetch(`/api/mf?view=${view}&page=${page}&q=${encodeURIComponent(search)}&stock=${view === "inventory" ? stock : "all"}`, { cache: "no-store" });
        const p = await r.json();
        if (!r.ok)
            throw Error(p.error);
        if (version === readVersion.current) {
            setData(p);
            setError(p.error || "");
        }
    }
    catch (e) {
        if (version === readVersion.current)
            setError(String(e));
    } }, [view, page, search, stock]);
    useEffect(() => { const timer = window.setTimeout(() => void load(), 150); return () => { window.clearTimeout(timer); }; }, [load]);
    async function post(body: object) { const r = await fetch("/api/mf", { method: "POST", headers: mutationHeaders({ "Content-Type": "application/json" }), body: JSON.stringify(body) }); const p = await r.json(); if (!r.ok)
        throw Error(p.error); return p; }
    async function refresh() { setBusy(true); setError(""); try {
        await runOnDemandRefresh("mf", load, notice => setNotice(notice ? {...notice, text: notice.text.replaceAll("Pricing refresh", "MF synchronization").replaceAll("pricing job", "synchronization job")} : null));
    }
    catch (e) {
        setError(String(e));
    }
    finally {
        setBusy(false);
    } }
    async function keep(row: Row, value: boolean) { setBusy(true); try {
        await post({ action: "keep-mf", sku: row.seller_sku, keep_mf: value });
        await load();
    }
    catch (e) {
        setError(String(e));
    }
    finally {
        setBusy(false);
    } }
    async function showLots(sku: string) { setError(""); try {
        const r = await fetch(`/api/mf?view=lots&sku=${encodeURIComponent(sku)}`);
        const p = await r.json();
        if (!r.ok)
            throw Error(p.error);
        setDetailSku(sku);
        setLots(p.rows);
    }
    catch (e) {
        setError(String(e));
    } }
    async function confirmOpening() {
        setBusy(true);
        setError("");
        try {
            if (!opening || count.trim() === "" || !Number.isInteger(Number(count)) || Number(count) < 0 || !notes.trim())
                throw Error("Enter the actual total physical count and reconciliation notes.");
            const body = { action: "opening", sku: opening.seller_sku, condition: opening.condition, count: Number(count), cost: cost.trim() === "" ? null : Number(cost), notes, revision: data?.account?.revision };
            const payload = JSON.stringify(body);
            if (attempt.current && attempt.current.payload !== payload)
                throw Error("A previous request may have succeeded. Close and refresh the preview before changing a retry.");
            attempt.current ??= { id: crypto.randomUUID(), payload };
            await post({ ...body, request_id: attempt.current.id });
            setOpening(null);
            await load();
        }
        catch (e) {
            setError(String(e));
        }
        finally {
            setBusy(false);
        }
    }
    const a = data?.account, stale = !a || a.stale, columns = view === "inventory" ? inventoryColumns : orderColumns;
    return <main className="min-w-0 flex-1 bg-slate-100 p-4 text-slate-900"><header className="mb-4 flex flex-wrap justify-between gap-3 pr-40"><div><h1 className="text-2xl font-semibold">MF {view === "inventory" ? "Inventory" : "Orders"}</h1><p className="text-sm text-slate-600">{a ? `${a.seller_id} / ${a.marketplace_id} / merchant fulfilled` : "Amazon account not initialized"}</p></div><button className={button} disabled={busy} onClick={refresh}>{busy ? "Refreshing..." : "Refresh from Amazon"}</button></header>
 <nav className="mb-3 flex gap-3 text-sm"><a className="text-blue-700 underline" href="/mf-inventory">MF Inventory</a><a className="text-blue-700 underline" href="/mf-orders">MF Orders</a><a className="text-blue-700 underline" href="/fba">List on Amazon</a></nav>
 <div className={`mb-3 border px-3 py-2 text-sm ${stale || a?.last_error ? "border-amber-300 bg-amber-50" : "border-slate-200 bg-white"}`}>Last successful synchronization: {date(a?.last_success_at)}  |  Last attempt: {date(a?.last_attempt_at)} {stale && "  |  STALE / never synchronized"}{a?.last_error && <div className="text-red-700">Sync failure: {a.last_error}</div>}</div>
 <p className="mb-3 text-xs text-slate-600">Physical stock comes from MBOP lots and explicit counted opening balances. Amazon-listed quantity is a separate offer observation. Refunds never restock inventory. Returns receiving and FBA transfer execution remain separate workflows. Before-tracking shipped quantities are historical baselines, not removals from newly counted stock.</p>
 {notice && <p className="mb-3 border bg-white p-3 text-sm">{notice.text}</p>}{error && <p role="alert" className="mb-3 bg-red-50 p-3 text-red-700">{error}</p>}
 {!!data?.runs?.some(r => r.status === "failed") && <details className="mb-3 text-sm"><summary className="text-red-700">Recent synchronization failures</summary>{data.runs.filter(r => r.status === "failed").map(r => <p key={r.id}>{date(r.started_at)}  |  {r.error}</p>)}</details>}
 <div className="mb-3 flex flex-wrap items-center gap-4 text-sm">{view === "inventory" && <label className="flex items-center gap-2">MF listings<select className={input} value={stock} onChange={e => { setStock(e.target.value); setPage(0); }}><option value="in_stock">In stock</option><option value="out_of_stock">Out of stock</option><option value="all">All</option></select></label>}<label className="flex items-center gap-2">Search title / ASIN / MSKU<input className={input} placeholder="Title, ASIN or MSKU" value={search} onChange={e => { setSearch(e.target.value); setPage(0); }}/></label></div>
 {view === "inventory" && <p className="mb-3 text-xs text-slate-600">Stock filters use live Amazon MF offer quantity. All includes retained out-of-stock listings; inactive, deleted and FBA-only listings are excluded. MBOP physical counts remain separate.</p>}
 <div className="max-h-[calc(100vh-22rem)] min-h-60 overflow-auto rounded-lg border border-slate-200 bg-white"><table className="w-full whitespace-nowrap text-left text-sm"><thead className="sticky top-0 z-10 bg-slate-50 text-xs uppercase text-slate-500"><tr>{view === "orders" && <th className="px-3 py-2">Amazon customer order / item</th>}<th className="px-3 py-2">Product / ASIN / MSKU / condition</th>{columns.map(([key, label]) => <th className="px-3 py-2" key={key}>{label}</th>)}{view === "inventory" && <th className="px-3 py-2">Keep MF</th>}<th className="px-3 py-2">Reconciliation / timestamps</th></tr></thead><tbody>{data?.rows.map((r, i) => <tr key={r.id || `${r.seller_sku}:${r.condition}:${i}`}>
 {view === "orders" && <td className={td}>{val(r.amazon_order_id)}<div className="text-xs text-slate-500">Item {val(r.amazon_order_item_id)}</div><div>{val(r.order_status)}</div>{r.replacement_for?.map(x => <div key={x.order_id}>Replacement of {x.order_id}</div>)}</td>}
 <td className={td}><div className="max-w-xs whitespace-normal font-medium">{r.title || "Unmatched product"}</div>{r.asin && <a target="_blank" rel="noreferrer" className="text-blue-700" href={`https://www.amazon.com/dp/${r.asin}`}>{r.asin}</a>}<div>{r.seller_sku || "MISSING MSKU"}  |  {r.condition}</div>{r.seller_sku && <button className="text-xs text-blue-700 underline" onClick={() => showLots(r.seller_sku)}>Stock lots / lineage</button>}</td>
 {columns.map(([key]) => <td className={`${td} text-right ${Number(r[key]) < 0 || key.includes("shortage") && Number(r[key]) > 0 ? "font-semibold text-red-700" : ""}`} key={key}>{val(r[key])}</td>)}
 {view === "inventory" && <td className={td}><input aria-label={`Keep MF ${r.seller_sku}`} type="checkbox" checked={!!r.keep_mf} disabled={busy || !r.seller_sku} onChange={e => keep(r, e.target.checked)}/></td>}
 <td className={`${td} max-w-sm whitespace-normal`}>{view === "inventory" ? <><div>{r.verification_state}</div>{Number(r.lot_count) === 0 && !r.opening_reconciled && <div className="text-amber-700">Physical balance unconfirmed; enter a counted opening.</div>}{Number(r.shortage) > 0 && <strong className="text-red-700">Shortage: {val(r.shortage)}. </strong>}{r.unmatched_sku && <span className="text-red-700">Unmatched SKU. </span>}{r.stale_sync && <span className="text-amber-700">Stale offer/sync. </span>}{r.quantity_difference !== null && Number(r.quantity_difference) !== 0 && <span className="text-amber-700">Physical/offer difference. </span>}<div className="text-xs text-slate-500">Offer observed {date(r.offer_observed_at)}</div><button className="mt-1 text-blue-700 underline disabled:text-slate-400" disabled={busy || r.unmatched_sku || r.stale_sync || !!r.opening_reconciled} onClick={() => { setOpening(r); setCount(""); setCost(""); setNotes(""); attempt.current = null; }}>{r.opening_reconciled ? "Opening already reconciled" : "Reconcile opening balance"}</button></> : <><div className="text-red-700">{r.anomaly}</div><div>Source {date(r.source_updated_at)}</div><div className="text-xs text-slate-500">Observed {date(r.observed_at)}</div></>}</td></tr>)}{!data?.rows.length && <tr><td className="p-6 text-slate-500" colSpan={12}>No MF records match this search or stock filter. Refresh from Amazon to update listings and customer orders.</td></tr>}</tbody></table></div>
 <div className="mt-3 flex items-center gap-3 text-sm"><button className={button} disabled={page === 0} onClick={() => setPage(p => p - 1)}>Previous</button><span>{data?.total || 0} records  |  Page {page + 1}</span><button className={button} disabled={(page + 1) * 100 >= (data?.total || 0)} onClick={() => setPage(p => p + 1)}>Next</button></div>
 {opening && <div role="dialog" aria-modal="true" aria-label="Opening balance reconciliation" className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"><section className="max-h-[90vh] w-full max-w-xl overflow-auto rounded-lg bg-white p-5"><div className="flex justify-between"><h2 className="font-semibold">Count existing MF stock</h2><button className={button} onClick={() => setOpening(null)}>Close</button></div><p className="my-3 text-sm">{opening.seller_sku}  |  {opening.condition}<br />Amazon offer quantity: {val(opening.amazon_listed_quantity)}. Existing MBOP on hand: {val(opening.on_hand)}. Count existing MF stock physically held, including those MBOP units. Exclude unlisted Received preparation inventory that will be listed separately. Only the surplus is added. Amazon offer quantity is not a verified physical count.</p><div className="grid gap-3"><label className="grid text-sm">Actual total physical count<input className={input} type="number" min="0" value={count} onChange={e => setCount(e.target.value)}/></label><label className="grid text-sm">Acquisition cost per added unit (blank = unknown)<input className={input} type="number" min="0" step="0.01" value={cost} onChange={e => setCost(e.target.value)}/></label><label className="grid text-sm">Count evidence / reconciliation notes<textarea className={input} value={notes} onChange={e => setNotes(e.target.value)}/></label>{error && <p className="text-sm text-red-700">{error}</p>}<button className={button} disabled={busy} onClick={confirmOpening}>Confirm counted opening balance</button></div></section></div>}
 {lots && <div role="dialog" aria-modal="true" aria-label="MF stock lots" className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"><section className="max-h-[90vh] w-full max-w-4xl overflow-auto rounded-lg bg-white p-5"><div className="mb-3 flex justify-between"><h2 className="font-semibold">Stock lineage  |  {detailSku}</h2><button className={button} onClick={() => setLots(null)}>Close</button></div>{!lots.length && <p>No MBOP lots match this SKU. Investigate unmatched orders or reconcile a counted opening balance.</p>}{lots.map(l => <div className="border-t py-3 text-sm" key={l.id}><strong>Lot {l.id}</strong><div>{val(l.quantity)} original units  |  {val(l.on_hand)} on hand  |  {val(l.order_reserved)} reserved  |  {val(l.shipped)} shipped  |  Acquisition cost/unit {val(l.unit_cost)}</div><div>Acquired {date(l.acquired_at)}  |  Stock basis {date(l.stock_start_at)}</div><div className="mt-1 break-all text-xs">{Object.entries((l.lineage as Record<string, unknown>) || {}).filter(([, v]) => v !== null && v !== undefined).map(([key, v]) => <div key={key}><span className="text-slate-500">{key.replaceAll("_", " ")}: </span>{val(v)}</div>)}</div></div>)}</section></div>}
 </main>;
}
