"use client";

import { useCallback, useEffect, useRef, useState, type ClipboardEvent } from "react";
import { mutationHeaders } from "../mutationHeaders";
import { ReceiptReview } from "./ReceiptReview";
import { receiptButton, receiptField, type ReceiptDraft } from "./receiptTypes";

type Order = { purchase_id: string; supplier: string; supplier_order_id: string | null; order_date: string | null; total_order_cost: number | null; order_status: string };

export function NonEbayPurchases({ onPurchaseSaved }: { onPurchaseSaved: () => void }) {
  const [drafts, setDrafts] = useState<ReceiptDraft[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [selected, setSelected] = useState<ReceiptDraft | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const uploadVisible = useRef(false);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [retryAllowed, setRetryAllowed] = useState(false);
  const [loading, setLoading] = useState(false);
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch(`/api/purchase-intake?page=${page}&search=${encodeURIComponent(search)}`, { cache: "no-store" });
      const result = await response.json(); if (!response.ok) throw new Error(result.error || "Unable to load non-eBay purchases.");
      setDrafts(result.drafts); setOrders(result.purchases); setTotal(result.total); setError("");
    } catch (error) { setError(error instanceof Error ? error.message : "Unable to load non-eBay purchases."); }
    finally { setLoading(false); }
  }, [page, search]);
  useEffect(() => { const timer = setTimeout(() => void load(), 250); return () => clearTimeout(timer); }, [load]);
  useEffect(() => {
    if (!selected || !["uploaded", "extracting"].includes(selected.status)) return;
    let disposed = false;
    const timer = setInterval(async () => {
      try {
        const response = await fetch(`/api/purchase-intake/${selected.id}`, { cache: "no-store" });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Unable to read extraction progress.");
        if (!disposed) { setSelected(result.draft); setRetryAllowed(result.draft.status !== "extracting" || Date.now() - Date.parse(result.draft.extraction_started_at || "") >= 15 * 60 * 1000); setError(""); }
      } catch { if (!disposed) setError("Unable to read extraction progress. Your receipt is retained; reload to reconnect."); }
    }, 5000);
    return () => { disposed = true; clearInterval(timer); };
  }, [selected]);

  function showUpload(value: boolean) { uploadVisible.current = value; setUploadOpen(value); if (value) setFile(null); }
  function paste(event: ClipboardEvent) {
    const image = Array.from(event.clipboardData.files).find((file) => file.type.startsWith("image/"));
    if (image && !busy) { event.preventDefault(); setFile(image); }
  }
  async function upload() {
    if (!file) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const form = new FormData(); form.append("file", file);
      const response = await fetch("/api/purchase-intake", { method: "POST", headers: mutationHeaders(), body: form });
      const result = await response.json(); if (!response.ok) throw new Error(result.error || "Upload failed.");
      if (uploadVisible.current) { showUpload(false); setSelected(result.draft); }
      setNotice(result.warning || (result.duplicate ? "This file is already recorded. Open its existing draft or purchase below." : "Receipt uploaded. Extraction runs in the background; you can leave this screen and reopen the draft."));
      void load();
    } catch (error) { setError(error instanceof Error ? error.message : "Upload failed."); }
    finally { setBusy(false); }
  }
  async function retry() {
    if (!selected) return;
    setRetrying(true); setError("");
    try {
      const response = await fetch(`/api/purchase-intake/${selected.id}`, { method: "POST", headers: mutationHeaders({ "Content-Type": "application/json" }), body: JSON.stringify({ action: "retry" }) });
      const result = await response.json(); if (!response.ok) throw new Error(result.error || "Unable to start extraction.");
      setNotice("Extraction requested. Worker startup can take about a minute.");
      const current = await fetch(`/api/purchase-intake/${selected.id}`, { cache: "no-store" }).then((response) => response.json());
      if (current.draft) setSelected({ ...current.draft, status: current.draft.status === 'failed' ? 'uploaded' : current.draft.status });
    } catch (error) { setError(error instanceof Error ? error.message : "Unable to start extraction."); }
    finally { setRetrying(false); }
  }
  function saved() { setSelected(null); setNotice("Purchase saved. Its items are now Ordered and available in the existing Receiving workflow."); void load(); onPurchaseSaved(); }
  return <section>
    <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
      <div><h2 className="text-lg font-semibold">Non-eBay purchases</h2><p className="text-sm text-slate-600">Upload a supplier receipt, review its items and costs, then save the purchase.</p></div>
      <div className="flex gap-2"><button type="button" className={receiptButton} disabled={loading} onClick={() => void load()}>Reload</button><button type="button" className="rounded bg-slate-900 px-4 py-2 text-sm font-semibold text-white" onClick={() => showUpload(true)}>Upload receipt / paste screenshot</button></div>
    </div>
    {error && <p role="alert" className="mb-3 rounded border border-red-200 bg-red-50 p-2 text-sm text-red-800">{error}</p>}
    {notice && <p role="status" className="mb-3 rounded border border-blue-200 bg-blue-50 p-2 text-sm">{notice}</p>}
    <h3 className="mb-2 font-semibold">Receipt drafts and recent imports</h3>
    <div className="mb-5 overflow-auto rounded border border-slate-300 bg-white"><table className="w-full text-left text-sm"><thead className="bg-slate-200"><tr><th className="p-2">Uploaded</th><th className="p-2">Original document</th><th className="p-2">Status</th><th className="p-2">Source / order</th><th className="p-2">Action</th></tr></thead><tbody>
      {drafts.map((draft) => <tr key={draft.id} className="border-t border-slate-200"><td className="p-2">{new Date(draft.created_at).toLocaleString()}</td><td className="p-2"><a className="text-blue-700 underline" href={`/api/purchase-intake/${draft.id}?document=1`} target="_blank" rel="noreferrer">{draft.original_filename}</a></td><td className="p-2">{draft.status === 'review' ? 'Ready for review' : draft.status}</td><td className="p-2">{(draft.reviewed_data || draft.extracted_data)?.supplier || 'Unknown'} / {(draft.reviewed_data || draft.extracted_data)?.order_id || 'Unknown'}</td><td className="p-2">{draft.status === 'saved' ? <a className="text-blue-700 underline" href={`/receiving?search=${encodeURIComponent(draft.purchase_id || '')}`}>Open Receiving</a> : <button type="button" className={receiptButton} onClick={() => setSelected(draft)}>Open draft</button>}</td></tr>)}
      {!drafts.length && <tr><td colSpan={5} className="p-4 text-slate-500">{loading ? 'Loading...' : 'No receipt drafts yet.'}</td></tr>}
    </tbody></table></div>
    <div className="mb-2 flex items-center gap-4"><h3 className="font-semibold">Recorded non-eBay purchases</h3><input aria-label="Search non-eBay supplier or order" className={`${receiptField} max-w-md`} placeholder="Search supplier or order reference" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }} /></div>
    <div className="overflow-auto rounded border border-slate-300 bg-white"><table className="w-full text-left text-sm"><thead className="bg-slate-200"><tr>{['Purchase date', 'Source', 'Order / invoice', 'Landed total', 'Order status', ''].map((title, i) => <th className="p-2" key={i}>{title}</th>)}</tr></thead><tbody>
      {orders.map((order) => <tr key={order.purchase_id} className="border-t border-slate-200"><td className="p-2">{order.order_date || 'Unknown'}</td><td className="p-2">{order.supplier}</td><td className="p-2">{order.supplier_order_id || 'Not provided'}</td><td className="p-2">{order.total_order_cost == null ? 'Unknown' : `$${Number(order.total_order_cost).toFixed(2)}`}</td><td className="p-2">{order.order_status}</td><td className="p-2"><a href={`/receiving?search=${encodeURIComponent(order.purchase_id)}`} className="text-blue-700 underline">Receiving</a></td></tr>)}
      {!orders.length && <tr><td colSpan={6} className="p-4 text-slate-500">{loading ? 'Loading...' : 'No purchases in this filter.'}</td></tr>}
    </tbody></table></div>
    <div className="my-3 flex items-center justify-between text-sm text-slate-600"><span>Page {page} / {Math.max(1, Math.ceil(total / 50))} ({total} orders)</span><div className="flex gap-2"><button type="button" className={receiptButton} disabled={page <= 1 || loading} onClick={() => setPage((value) => value - 1)}>Previous</button><button type="button" className={receiptButton} disabled={page * 50 >= total || loading} onClick={() => setPage((value) => value + 1)}>Next</button></div></div>
    {uploadOpen && <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4" role="dialog" aria-modal="true" aria-labelledby="receipt-upload-title" onKeyDown={(event) => { if (event.key === 'Escape') showUpload(false); }}><section className="w-full max-w-2xl rounded-lg border border-slate-300 bg-slate-100 p-4 shadow-xl" onPaste={paste}>
      <header className="mb-3 flex items-center justify-between"><h2 id="receipt-upload-title" className="text-lg font-semibold">Upload purchase receipt</h2><button type="button" className={receiptButton} onClick={() => showUpload(false)}>Close</button></header>
      <p className="mb-3 text-sm text-slate-600">PDF, PNG, JPEG or WebP, up to 12 MB, one order per file. Original receipts are stored privately and sent to OpenAI for extraction. Review is required before creating a purchase.</p>
      <div tabIndex={0} role="region" aria-label="Paste screenshot here" className="mb-3 rounded border-2 border-dashed border-slate-400 bg-white p-8 text-center text-sm outline-offset-4" onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); if (!busy) setFile(event.dataTransfer.files[0] || null); }}>Click here and paste a screenshot (Ctrl+V), or drop a receipt file.</div>
      <input aria-label="Choose receipt PDF or image" type="file" accept="application/pdf,image/png,image/jpeg,image/webp" disabled={busy} onChange={(event) => setFile(event.target.files?.[0] || null)} />
      {file && <p className="mt-3 text-sm">Selected: {file.name} ({(file.size / 1024 / 1024).toFixed(2)} MB)</p>}
      {error && <p role="alert" className="mt-3 text-sm text-red-800">{error}</p>}
      <footer className="mt-4 flex justify-end"><button type="button" className={receiptButton} disabled={busy || !file || file.size > 12 * 1024 * 1024} onClick={() => void upload()}>{busy ? 'Uploading...' : 'Read receipt'}</button></footer>
    </section></div>}
    {selected && (selected.status === 'review' || selected.status === 'failed') && <ReceiptReview key={selected.id} draft={selected} onRetry={() => void retry()} onSaved={saved} onClose={() => { setSelected(null); void load(); }} />}
    {selected && !['review', 'failed', 'saved'].includes(selected.status) && <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4" role="dialog" aria-modal="true" aria-labelledby="receipt-progress-title"><section className="w-full max-w-xl rounded-lg bg-white p-5 shadow-xl"><h2 id="receipt-progress-title" className="text-lg font-semibold">Reading receipt</h2><p className="my-3 text-sm">{selected.original_filename}: {selected.status}. Extraction runs in the background and may take a few minutes. You can close this window and return later.</p><div className="flex justify-end gap-2"><button type="button" className={receiptButton} disabled={retrying || (selected.status === 'extracting' && !retryAllowed)} onClick={() => void retry()}>Retry extraction</button><button type="button" className={receiptButton} onClick={() => { setSelected(null); void load(); }}>Close</button></div></section></div>}
  </section>;
}
