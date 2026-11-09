"use client";

import { useState } from "react";
import { mutationHeaders } from "../mutationHeaders";
import { SYSTEM_OPTIONS } from "./systemOptions";
import { blankReceiptItem, editableReceipt, receiptButton, receiptField, type ReceiptCosts, type ReceiptData, type ReceiptDraft, type ReceiptItem } from "./receiptTypes";

export function ReceiptReview({ draft, onSaved, onClose, onRetry }: { draft: ReceiptDraft; onSaved: () => void; onClose: () => void; onRetry: () => void }) {
  const [data, setData] = useState<ReceiptData>(() => editableReceipt(draft));
  const [costs, setCosts] = useState<ReceiptCosts | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  function edit(field: keyof ReceiptData, value: string) {
    setData((current) => ({ ...current, [field]: value })); setCosts(null); setConfirmed(false); setNotice("");
  }
  function editItem(index: number, field: keyof ReceiptItem, value: string | boolean) {
    setData((current) => ({ ...current, items: current.items.map((item, i) => i === index ? { ...item, [field]: value } : item) }));
    setCosts(null); setConfirmed(false); setNotice("");
  }
  async function action(action: "preview" | "draft" | "save") {
    setBusy(true); setError(""); setNotice("");
    try {
      const response = await fetch(`/api/purchase-intake/${draft.id}`, { method: "POST", headers: mutationHeaders({ "Content-Type": "application/json" }), body: JSON.stringify({ action, data }) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Receipt action failed.");
      if (action === "preview") setCosts(result.costs);
      if (action === "draft") setNotice("Draft saved. You can close and reopen it later.");
      if (action === "save") onSaved();
    } catch (error) { setError(error instanceof Error ? error.message : "Receipt action failed."); }
    finally { setBusy(false); }
  }
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4" role="dialog" aria-modal="true" aria-labelledby="receipt-review-title" onKeyDown={(event) => { if (event.key === "Escape") onClose(); }}>
    <section className="flex max-h-[94vh] w-full max-w-[1500px] flex-col rounded-lg border border-slate-300 bg-slate-100 shadow-xl">
      <header className="flex items-center justify-between border-b border-slate-300 px-4 py-3">
        <div><h2 id="receipt-review-title" className="text-lg font-semibold">Review non-eBay purchase</h2><a className="text-sm text-blue-700 underline" href={`/api/purchase-intake/${draft.id}?document=1`} target="_blank" rel="noreferrer">Original receipt: {draft.original_filename}</a></div>
        <button type="button" className={receiptButton} onClick={onClose}>Close without saving</button>
      </header>
      <div className="overflow-auto p-4">
        <p className="mb-3 text-sm text-slate-600">Confirm the source and purchase date. Enter each merchandise line total after its own discounts, before order-wide discount, shipping and tax. Unknown amounts stay blank until you verify them; enter 0 only when confirmed.</p>
        {draft.extraction_error && <div className="mb-3 rounded border border-amber-300 bg-amber-50 p-2 text-sm"><p>{draft.extraction_error} You can enter the receipt manually.</p><button type="button" className={`${receiptButton} mt-2`} onClick={onRetry}>Retry extraction</button></div>}
        {!!data.warnings?.length && <ul className="mb-3 list-disc rounded border border-amber-300 bg-amber-50 py-2 pl-7 text-sm">{data.warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul>}
        <label className="mb-3 flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1" checked={data.cost_basis === 'total_only'} disabled={busy || (data.items.length !== 1 && data.cost_basis !== 'total_only')} onChange={(event) => edit('cost_basis', event.target.checked ? 'total_only' : 'itemized')} />This receipt has one product and only a grand total. Use that total as its landed cost; leave the merchandise/tax/shipping breakdown unknown.</label>
        <div className="mb-4 grid grid-cols-4 gap-3">
          {([['supplier', 'Source / supplier', 'text'], ['order_id', 'Order / invoice reference', 'text'], ['order_date', 'Purchase date', 'date'], ['currency', 'Currency (USD only)', 'text'], ['shipping', 'Shipping ($)', 'number'], ['tax', 'Tax ($)', 'number'], ['discount', 'Order-wide discount ($)', 'number'], ['order_total', 'Receipt grand total ($)', 'number']] as const).map(([field, label, type]) => <label key={field} className="text-sm font-medium">{label}<input aria-label={label} className={receiptField} type={type} step={type === 'number' ? '0.01' : undefined} min={type === 'number' ? '0' : undefined} value={data[field]} onChange={(e) => edit(field, e.target.value)} disabled={busy || (data.cost_basis === 'total_only' && ['shipping', 'tax', 'discount'].includes(field))} /></label>)}
        </div>
        <div className="overflow-x-auto rounded border border-slate-300 bg-white">
          <table className="w-full text-left text-sm"><thead className="bg-slate-200"><tr>{['Product / supplier SKU', 'Platform', 'Condition', 'Qty', 'Merchandise line ($)', 'Resale', 'Landed total / unit', ''].map((heading, i) => <th key={i} className="p-2">{heading}</th>)}</tr></thead>
            <tbody>{data.items.map((item, i) => <tr key={i} className="border-t border-slate-200">
              <td className="min-w-64 p-2"><input aria-label={`Item ${i + 1} title`} className={receiptField} value={item.title} onChange={(e) => editItem(i, 'title', e.target.value)} disabled={busy} /><input aria-label={`Item ${i + 1} supplier SKU`} placeholder="Supplier SKU (optional)" className={`${receiptField} mt-1`} value={item.supplier_sku} onChange={(e) => editItem(i, 'supplier_sku', e.target.value)} disabled={busy} /></td>
              <td className="p-2"><select aria-label={`Item ${i + 1} platform`} className={receiptField} value={item.system} onChange={(e) => editItem(i, 'system', e.target.value)} disabled={busy}><option value="">Unspecified / N/A</option>{SYSTEM_OPTIONS.map((system) => <option key={system}>{system}</option>)}</select></td>
              <td className="p-2"><select aria-label={`Item ${i + 1} condition`} className={receiptField} value={item.condition} onChange={(e) => editItem(i, 'condition', e.target.value)} disabled={busy}><option value="new">New</option><option value="used">Used</option></select></td>
              <td className="w-20 p-2"><input aria-label={`Item ${i + 1} quantity`} className={receiptField} type="number" min="1" step="1" value={item.quantity} onChange={(e) => editItem(i, 'quantity', e.target.value)} disabled={busy} /></td>
              <td className="w-36 p-2"><input aria-label={`Item ${i + 1} merchandise line total`} className={receiptField} type="number" min="0" step="0.01" value={item.line_total} onChange={(e) => editItem(i, 'line_total', e.target.value)} disabled={busy || data.cost_basis === 'total_only'} /></td>
              <td className="p-2"><input aria-label={`Item ${i + 1} is resale inventory`} type="checkbox" checked={!item.exclude_from_purchase_reporting} onChange={(e) => editItem(i, 'exclude_from_purchase_reporting', !e.target.checked)} disabled={busy} /></td>
              <td className="min-w-36 p-2">{costs?.items[i] ? <><div>${Number(costs.items[i].landed_total).toFixed(2)}</div><div className="text-xs text-slate-600">${Number(costs.items[i].average_unit_cost).toFixed(4)} avg / unit</div></> : <span className="text-slate-500">Preview costs</span>}</td>
              <td className="p-2"><button type="button" className={receiptButton} disabled={busy || data.items.length === 1} onClick={() => { setData((current) => ({ ...current, items: current.items.filter((_, index) => index !== i) })); setCosts(null); setConfirmed(false); }}>Remove</button></td>
            </tr>)}</tbody></table>
        </div>
        <button type="button" className={`${receiptButton} my-3`} disabled={busy || data.items.length >= 100 || data.cost_basis === 'total_only'} onClick={() => { setData((current) => ({ ...current, items: [...current.items, blankReceiptItem()] })); setCosts(null); setConfirmed(false); }}>Add item</button>
        <label className="block text-sm font-medium">Notes (optional)<textarea className={receiptField} rows={2} value={data.notes} onChange={(event) => edit('notes', event.target.value)} disabled={busy} /></label>
        {costs && <div className="my-3 rounded border border-blue-200 bg-blue-50 p-2 text-sm">Backend-verified receipt total: <strong>${Number(costs.order_total).toFixed(2)}</strong>. {data.cost_basis === 'total_only' ? 'The total is allocated to the single product; charge breakdowns remain unknown.' : 'Shipping, tax and order discounts are allocated by merchandise value.'} When cents do not divide evenly, separate cost allocations preserve the exact total.</div>}
        <label className="mt-3 flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1" checked={confirmed} disabled={!costs || busy} onChange={(event) => setConfirmed(event.target.checked)} />I reviewed the source, date, quantities, condition and costs, and checked that this purchase is not already recorded. Saving creates Ordered items for the existing Receiving workflow.</label>
        {error && <p role="alert" className="mt-3 rounded border border-red-200 bg-red-50 p-2 text-sm text-red-800">{error}</p>}
        {notice && <p role="status" className="mt-3 text-sm text-green-800">{notice}</p>}
      </div>
      <footer className="flex justify-end gap-2 border-t border-slate-300 p-3"><button type="button" className={receiptButton} disabled={busy} onClick={() => void action('draft')}>Save draft</button><button type="button" className={receiptButton} disabled={busy} onClick={() => void action('preview')}>{busy ? 'Working...' : 'Preview landed costs'}</button><button type="button" className="rounded bg-slate-900 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" disabled={busy || !confirmed || !costs} onClick={() => void action('save')}>Save purchase</button></footer>
    </section>
  </div>;
}
