"use client";
import { useEffect, useRef, useState } from "react";
import { mutationHeaders } from "../mutationHeaders";
import { BUSINESS_TIMEZONE, businessLocalNow, formatInventoryLabInput, mfReference, parseInventoryLabInput } from "./listingBatch";
export type ListingBatch = {
    id: string;
    fulfillment_method: "FBA" | "MF";
    external_reference: string;
    il_batch_local: string;
    status: string;
    recovery_evidence?: { source_url: string };
    total_cost?: number | null;
    selection: Record<string, string>;
    export_csv?: string;
    exported_at?: string;
    completed_at?: string;
    allocations?: Allocation[];
    lots?: {
        external_reference: string;
        completed_at: string;
        lots: {
            seller_sku: string | null;
            quantity: number;
            unit_cost: number;
            source_item_id: string;
        }[];
    }[];
};
type Allocation = {
    suggested_sku?: string | null;
    id: string;
    source_key: string;
    quantity: number;
    listed_quantity: number;
    transferred_quantity?: number;
    recovery_batch_id?: string | null;
    recovery_source_allocation_id?: string | null;
    snapshot: {
        asin: string;
        condition?: string;
        unit_cost: number;
        supplier_order_id?: string;
        received_date?: string;
    };
};
const input = "rounded border border-slate-300 px-2 py-1";
const button = "rounded border border-slate-300 bg-white px-3 py-2 text-sm disabled:opacity-50";
export function ListingBatches({ quantities, method, setMethod, onRestore, onBatch, onCompleted, batch, shipmentId }: {
    quantities: Record<string, string>;
    method: "FBA" | "MF";
    setMethod: (method: "FBA" | "MF") => void;
    onRestore: (quantities: Record<string, string>) => void;
    onBatch: (batch: ListingBatch | null) => void;
    onCompleted: (reset?: boolean) => Promise<void>;
    batch: ListingBatch | null;
    shipmentId: string;
}) {
    const [draftId, setId] = useState(() => crypto.randomUUID());
    const id = batch?.id || draftId;
    const [local, setLocal] = useState(() => batch?.il_batch_local.slice(0, 16) || businessLocalNow());
    const [localText, setLocalText] = useState(() => formatInventoryLabInput(batch?.il_batch_local.slice(0, 16) || businessLocalNow()));
    const [history, setHistory] = useState<ListingBatch[]>([]);
    const [pending, setPending] = useState<Record<string, {
        quantity: string;
        sku: string;
    }>>({});
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const [confirming, setConfirming] = useState(false);
    const attempt = useRef<{
        id: string;
        payload: string;
    } | null>(null);
    useEffect(() => { void loadHistory(); }, []);
    useEffect(() => { if (batch?.status === "completed")
        void loadHistory(); }, [batch?.status]);
    async function loadHistory() { try {
        const r = await fetch("/api/amazon-listing-batches");
        const p = await r.json();
        if (!r.ok)
            throw Error(p.error);
        setHistory(p.rows);
    }
    catch (e) {
        setError(String(e));
    } }
    async function post(body: object) {
        const r = await fetch("/api/amazon-listing-batches", { method: "POST", headers: mutationHeaders({ "Content-Type": "application/json" }), body: JSON.stringify(body) });
        const p = await r.json();
        if (!r.ok)
            throw Error(p.error);
        return p as ListingBatch;
    }
    async function open(batchId: string) { setBusy(true); setError(""); try {
        const r = await fetch(`/api/amazon-listing-batches?id=${batchId}`);
        const b = await r.json();
        if (!r.ok)
            throw Error(b.error);
        setId(b.id);
        setMethod(b.fulfillment_method);
        setLocal(b.il_batch_local.slice(0, 16));
        setLocalText(formatInventoryLabInput(b.il_batch_local.slice(0, 16)));
        onRestore(b.selection);
        onBatch(b);
        setConfirming(false);
        attempt.current = null;
    }
    catch (e) {
        setError(String(e));
    }
    finally {
        setBusy(false);
    } }
    async function save(action: "draft" | "export" | "reference") {
        setBusy(true);
        setError("");
        try {
            const parsedLocal = parseInventoryLabInput(localText);
            if (!parsedLocal)
                throw Error("Enter a valid InventoryLab date/time, such as 11/09/2026 08:26 PM.");
            setLocal(parsedLocal);
            const b = await post({ id, action, method, local: parsedLocal, reference: shipmentId, quantities });
            onBatch(b);
            await loadHistory();
            if (action === "export")
                download(b);
        }
        catch (e) {
            setError(String(e));
        }
        finally {
            setBusy(false);
        }
    }
    function download(b: ListingBatch) { const url = URL.createObjectURL(new Blob([b.export_csv!], { type: "text/csv;charset=utf-8" })); const a = document.createElement("a"); a.href = url; a.download = `mbop-${b.fulfillment_method.toLowerCase()}-${b.id}.csv`; a.click(); URL.revokeObjectURL(url); }
    async function startConfirmation() {
        setBusy(true);
        setError("");
        try {
            const r = await fetch(`/api/amazon-listing-batches?id=${id}`);
            const b = await r.json();
            if (!r.ok)
                throw Error(b.error);
            onBatch(b);
            setPending(Object.fromEntries(b.allocations.map((a: Allocation) => [a.id, { quantity: String(a.quantity - a.listed_quantity - (a.transferred_quantity || 0)), sku: a.suggested_sku || "" }])));
            setConfirming(true);
            attempt.current = null;
        }
        catch (e) {
            setError(String(e));
        }
        finally {
            setBusy(false);
        }
    }
    async function complete() {
        setBusy(true);
        setError("");
        try {
            const items = Object.entries(pending).filter(([, p]) => Number(p.quantity) > 0).map(([allocation_id, p]) => ({ allocation_id, quantity: Number(p.quantity), seller_sku: null }));
            if (!items.length || items.some(p => !Number.isInteger(p.quantity)))
                throw Error("Select valid whole quantities for the listed allocations.");
            const payload = JSON.stringify({ items, local });
            if (attempt.current && attempt.current.payload !== payload)
                throw Error("A prior completion may have succeeded. Reopen this batch before changing a retry.");
            attempt.current ??= { id: crypto.randomUUID(), payload };
            const parsedLocal = parseInventoryLabInput(localText);
            if (!parsedLocal)
                throw Error("Enter a valid InventoryLab date/time, such as 11/09/2026 08:26 PM.");
            const b = await post({ id, action: "complete", local: parsedLocal, items, request_id: attempt.current.id });
            onBatch(b);
            setConfirming(false);
            await onCompleted();
            await loadHistory();
        }
        catch (e) {
            setError(String(e));
        }
        finally {
            setBusy(false);
        }
    }
    let preview = "Enter a valid batch date/time";
    try {
        preview = mfReference(local);
    }
    catch { }
    const canComplete = !!batch && ["exported", "partially_listed"].includes(batch.status);
    const moved = batch?.allocations?.reduce((n, a) => n + (a.transferred_quantity || 0), 0) || 0;
    const frozen = !!batch && batch.status !== "draft";
    return <section className="mb-4 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
    <div className="flex flex-wrap items-end gap-3">
      <label className="grid gap-1 text-sm">Fulfillment method<select className={input} value={method} disabled={frozen || busy} onChange={e => {
        const nextMethod = e.target.value as "FBA" | "MF";
        setMethod(nextMethod);
        if (batch) onBatch({ ...batch, id: crypto.randomUUID(), fulfillment_method: nextMethod, status: "draft", export_csv: undefined, exported_at: undefined, completed_at: undefined, allocations: [], lots: [] });
      }} required><option>FBA</option><option>MF</option></select></label>
      <label className="grid gap-1 text-sm">InventoryLab batch date/time<input className={input} type="text" value={localText} placeholder="MM/DD/YYYY h:mm AM/PM" aria-invalid={!parseInventoryLabInput(localText)} onChange={e => { setLocalText(e.target.value); const parsed = parseInventoryLabInput(e.target.value); if (parsed) setLocal(parsed); }} disabled={busy || (frozen && !canComplete)} required/><span className="text-xs text-slate-500">Paste date/time or batch reference · {BUSINESS_TIMEZONE} · {method === "MF" ? preview : "FBA shipment reference entered below"}</span></label>
      {!frozen && <button className={button} disabled={busy || !id || !parseInventoryLabInput(localText)} onClick={() => save("draft")}>Save draft</button>}
      {(!frozen || batch?.export_csv) && <button className={button} disabled={busy || !id || (!frozen && !parseInventoryLabInput(localText))} onClick={() => save("export")}>{frozen ? "Download saved export" : "Export selected CSV"}</button>}
      {canComplete && <button className={button} disabled={busy || !parseInventoryLabInput(localText)} onClick={() => save("reference")}>Correct IL reference</button>}
      {method === "MF" && canComplete && <button className={button} disabled={busy} onClick={startConfirmation}>Mark listed</button>}
      <button className={button} disabled={busy} onClick={() => { onBatch(null); setId(crypto.randomUUID()); const now = businessLocalNow(); setLocal(now); setLocalText(formatInventoryLabInput(now)); setConfirming(false); attempt.current = null; void onCompleted(true); }}>New selection</button>
    </div>
    {batch && <p className="mt-2 text-sm">{batch.external_reference} · {batch.fulfillment_method} · {batch.status.replaceAll("_", " ")} <span className="text-xs text-slate-500">Internal ID {batch.id}</span></p>}
    {moved > 0 && <p className="mt-2 text-sm text-amber-800">{moved} units moved to a recovery batch and excluded from this batch active quantities and cost. The saved original export is historical; use the recovery batch to resubmit those units.</p>}
    {batch?.recovery_evidence && <p className="mt-2 text-sm">Recovery batch: these units already exist in merchant inventory. Mark listed confirms the new submission using the same stock. <a className="underline" href={batch.recovery_evidence.source_url} target="_blank" rel="noreferrer">Source reconciliation</a></p>}
    {method === "MF" && !batch?.recovery_evidence && <p className="mt-2 text-xs text-slate-600">Export leaves inventory in Received. Mark listed confirms merchant-held stock manually; Amazon acceptance and availability are unverified. MSKU is not required here. MBOP will reconcile it from a later Amazon synchronization; unresolved stock remains visible as pending reconciliation.</p>}
    {error && <p role="alert" className="mt-2 text-sm text-red-700">{error}</p>}
    {confirming && <div className="mt-3 border-t pt-3"><div className="flex justify-between"><strong>Confirm exported allocations actually listed</strong><button className={button} onClick={() => setConfirming(false)}>Close without saving</button></div>
      <table className="my-3 w-full text-left text-sm"><thead><tr><th>Listed</th><th>ASIN / source order / condition</th><th>Cost / unit</th><th>Pending</th><th>Listed quantity</th></tr></thead><tbody>{batch?.allocations?.map(a => { const p = pending[a.id]; const remaining = a.quantity - a.listed_quantity - (a.transferred_quantity || 0); return <tr key={a.id} className="border-t"><td><input type="checkbox" aria-label={`List allocation ${a.source_key}`} disabled={!remaining || busy} checked={Number(p?.quantity) > 0} onChange={e => setPending(v => ({ ...v, [a.id]: { ...v[a.id], quantity: e.target.checked ? String(remaining) : "0" } }))}/></td><td>{a.snapshot.asin} / {a.snapshot.supplier_order_id} / {a.snapshot.condition || "unspecified"}<div className="text-xs text-slate-500">Purchase item {a.source_key} · received {a.snapshot.received_date || "—"}</div></td><td>{a.snapshot.unit_cost}</td><td>{remaining}</td><td><input className={input} aria-label={`Listed quantity ${a.source_key}`} type="number" min="0" max={remaining} value={p?.quantity || "0"} disabled={!remaining || busy || !!a.recovery_source_allocation_id} onChange={e => setPending(v => ({ ...v, [a.id]: { ...v[a.id], quantity: e.target.value } }))}/></td></tr>; })}</tbody></table><button className={button} disabled={busy} onClick={complete}>Confirm Mark listed</button></div>}
    {!!batch?.lots?.length && <div className="mt-3 text-sm">{batch.lots.map(c => <div key={c.completed_at}>{c.external_reference} · manually listed {new Date(c.completed_at).toLocaleString()} · {c.lots.map(l => `${l.quantity} × ${l.seller_sku || "MSKU pending Amazon reconciliation"} @ ${l.unit_cost}`).join("; ")}</div>)}</div>}
    <details className="mt-3"><summary className="cursor-pointer text-sm font-medium" onClick={() => void loadHistory()}>Listing batch history (latest 100; historical FBA shipments remain in Shipments)</summary><table className="mt-2 w-full text-left text-sm"><thead><tr><th>Method / reference</th><th>Status</th><th>Selected / exported / listed units</th><th>Exported</th><th>Last listing completion</th><th /></tr></thead><tbody>{history.map(b => <tr key={b.id} className="border-t"><td>{b.fulfillment_method} · {b.external_reference}</td><td>{b.status}</td><td>{b.allocations?.length ? b.allocations.reduce((n, a) => n + a.quantity - (a.transferred_quantity || 0), 0) : Object.values(b.selection).reduce((n, v) => n + Number(v || 0), 0)} / {b.allocations?.reduce((n, a) => n + a.quantity - (a.transferred_quantity || 0), 0) || 0} / {b.allocations?.reduce((n, a) => n + a.listed_quantity, 0) || 0}</td><td>{b.exported_at ? new Date(b.exported_at).toLocaleString() : "—"}</td><td>{b.completed_at ? new Date(b.completed_at).toLocaleString() : "—"}</td><td><button className={button} disabled={busy} onClick={() => open(b.id)}>Open</button></td></tr>)}</tbody></table></details>
  </section>;
}
