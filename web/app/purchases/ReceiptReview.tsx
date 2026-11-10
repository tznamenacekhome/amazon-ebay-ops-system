"use client";

import { useEffect, useState } from "react";
import { mutationHeaders } from "../mutationHeaders";
import { cleanMarketplaceTitleForSearch } from "./titleCleaning";
import { blankReceiptItem, editableReceipt, receiptButton, receiptField, type ReceiptCosts, type ReceiptData, type ReceiptDraft, type ReceiptItem } from "./receiptTypes";

export function ReceiptReview({ draft, onSaved, onClose, onRetry }: { draft: ReceiptDraft; onSaved: () => void; onClose: () => void; onRetry: () => void }) {
  const [data, setData] = useState<ReceiptData>(() => editableReceipt(draft));
  const [costs, setCosts] = useState<ReceiptCosts | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [calculating, setCalculating] = useState(false);
  const [preparing, setPreparing] = useState(true);
  function edit(field: keyof ReceiptData, value: string) {
    setData((current) => ({ ...current, [field]: value })); setCosts(null); setNotice("");
  }
  function editItem(index: number, field: keyof ReceiptItem, value: string | boolean) {
    setData((current) => ({ ...current, items: current.items.map((item, i) => i === index ? { ...item, [field]: value, ...(field === "asin" ? { amazon_title: "", match_note: "" } : {}) } : item) }));
    setCosts(null); setNotice("");
  }
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setCalculating(true);
      try {
        const response = await fetch(`/api/purchase-intake/${draft.id}`, {
          method: "POST", headers: mutationHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({ action: preparing ? "prepare" : "preview", data }), signal: controller.signal,
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Unable to calculate landed costs.");
        if (controller.signal.aborted) return;
        if (result.data && JSON.stringify(result.data) !== JSON.stringify(data)) setData(result.data);
        setCosts(result.costs); setError(result.costError || "");
        if (result.matchWarning) setNotice(result.matchWarning);
        setPreparing(false);
      } catch (error) {
        if (!controller.signal.aborted) { setError(error instanceof Error ? error.message : "Unable to calculate landed costs."); setPreparing(false); }
      } finally { if (!controller.signal.aborted) setCalculating(false); }
    }, 450);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [data, draft.id, preparing]);

  async function action(action: "preview" | "draft" | "save" | "match") {
    setBusy(true); setError(""); setNotice("");
    try {
      const response = await fetch(`/api/purchase-intake/${draft.id}`, { method: "POST", headers: mutationHeaders({ "Content-Type": "application/json" }), body: JSON.stringify({ action, data }) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Receipt action failed.");
      if (result.data) setData(result.data);
      if (action === "preview" || action === "match") { setCosts(result.costs); setError(result.costError || ""); }
      if (result.matchWarning) setNotice(result.matchWarning);
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
        <p className="mb-3 text-sm text-slate-600">Confirm the source and purchase date. Enter each merchandise line total after its own discounts, before order-wide discount, shipping, packing/other charges and tax. Unknown amounts stay blank until you verify them; enter 0 only when confirmed.</p>
        {draft.extraction_error && <div className="mb-3 rounded border border-amber-300 bg-amber-50 p-2 text-sm"><p>{draft.extraction_error} You can enter the receipt manually.</p><button type="button" className={`${receiptButton} mt-2`} onClick={onRetry}>Retry extraction</button></div>}
        {!!data.warnings?.length && <ul className="mb-3 list-disc rounded border border-amber-300 bg-amber-50 py-2 pl-7 text-sm">{data.warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul>}
        <label className="mb-3 flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1" checked={data.cost_basis === 'total_only'} disabled={busy || (data.items.length !== 1 && data.cost_basis !== 'total_only')} onChange={(event) => edit('cost_basis', event.target.checked ? 'total_only' : 'itemized')} />This receipt has one product and only a grand total. Use that total as its landed cost; leave the merchandise/tax/shipping breakdown unknown.</label>
        <div className="mb-4 grid grid-cols-4 gap-3">
          {([['supplier', 'Source / supplier', 'text'], ['order_id', 'Order / invoice reference', 'text'], ['order_date', 'Purchase date', 'date'], ['shipping', 'Shipping ($)', 'number'], ['tax', 'Tax ($)', 'number'], ['other_charges', 'Other charges / packing ($)', 'number'], ['discount', 'Order-wide discount ($)', 'number'], ['order_total', 'Receipt grand total ($)', 'number']] as const).map(([field, label, type]) => <label key={field} className="text-sm font-medium">{label}<input aria-label={label} className={receiptField} type={type} step={type === 'number' ? '0.01' : undefined} min={type === 'number' ? '0' : undefined} value={data[field]} onChange={(e) => edit(field, e.target.value)} disabled={busy || (data.cost_basis === 'total_only' && ['shipping', 'tax', 'discount', 'other_charges'].includes(field))} /></label>)}
        </div>
        {!!data.charge_lines?.length && <p className="mb-3 text-sm text-slate-600">Included in Other charges: {data.charge_lines.map((charge) => `${charge.title}: $${charge.amount}`).join("; ")}. These charges are allocated to product costs.</p>}
        <div className="overflow-x-auto rounded border border-slate-300 bg-white">
          <table className="w-full text-left text-sm"><thead className="bg-slate-200"><tr>{['Product / supplier SKU', 'ASIN', 'Sell price ($)', 'Qty', 'Merchandise line ($)', 'Resale', 'Landed total / unit', ''].map((heading, i) => <th key={i} className="p-2">{heading}</th>)}</tr></thead>
            <tbody>{data.items.map((item, i) => <tr key={i} className="border-t border-slate-200">
              <td className="min-w-64 p-2"><input aria-label={`Item ${i + 1} title`} className={receiptField} value={item.title} onChange={(e) => editItem(i, 'title', e.target.value)} disabled={busy || preparing} /><input aria-label={`Item ${i + 1} supplier SKU`} placeholder="Supplier SKU (optional)" className={`${receiptField} mt-1`} value={item.supplier_sku} onChange={(e) => editItem(i, 'supplier_sku', e.target.value)} disabled={busy || preparing} /></td>
              <td className="min-w-52 p-2"><input aria-label={`Item ${i + 1} ASIN`} className={receiptField} value={item.asin} placeholder="ASIN" maxLength={10} onChange={(e) => editItem(i, 'asin', e.target.value.toUpperCase())} disabled={busy || preparing} />
                {item.amazon_title && <div className="mt-1 max-w-64 text-xs text-slate-600">{item.amazon_title}</div>}
                {item.match_note && <div className="mt-1 max-w-64 text-xs text-slate-600">{item.match_note}</div>}
                <a className="text-xs text-blue-700 underline" href={`https://www.amazon.com/s?k=${encodeURIComponent(cleanMarketplaceTitleForSearch(item.title))}`} target="_blank" rel="noreferrer">Search Amazon</a>
              </td>
              <td className="w-28 p-2"><input aria-label={`Item ${i + 1} sell price`} className={receiptField} type="number" min="0" step="0.01" value={item.sell_price} onChange={(e) => editItem(i, 'sell_price', e.target.value)} disabled={busy || preparing} /></td>
              <td className="w-20 p-2"><input aria-label={`Item ${i + 1} quantity`} className={receiptField} type="number" min="1" step="1" value={item.quantity} onChange={(e) => editItem(i, 'quantity', e.target.value)} disabled={busy || preparing} /></td>
              <td className="w-36 p-2"><input aria-label={`Item ${i + 1} merchandise line total`} className={receiptField} type="number" min="0" step="0.01" value={item.line_total} onChange={(e) => editItem(i, 'line_total', e.target.value)} disabled={busy || data.cost_basis === 'total_only'} /></td>
              <td className="p-2"><input aria-label={`Item ${i + 1} is resale inventory`} type="checkbox" checked={!item.exclude_from_purchase_reporting} onChange={(e) => editItem(i, 'exclude_from_purchase_reporting', !e.target.checked)} disabled={busy || preparing} /></td>
              <td className="min-w-36 p-2">{costs?.items[i] ? <><div>${Number(costs.items[i].landed_total).toFixed(2)}</div><div className="text-xs text-slate-600">${Number(costs.items[i].average_unit_cost).toFixed(4)} avg / unit</div></> : <span className="text-slate-500">{calculating || preparing ? "Calculating..." : "Complete receipt totals"}</span>}</td>
              <td className="p-2"><button type="button" className={receiptButton} disabled={busy || data.items.length === 1} onClick={() => { setData((current) => ({ ...current, items: current.items.filter((_, index) => index !== i) })); setCosts(null); }}>Remove</button></td>
            </tr>)}</tbody></table>
        </div>
        <button type="button" className={`${receiptButton} my-3`} disabled={busy || data.items.length >= 100 || data.cost_basis === 'total_only'} onClick={() => { setData((current) => ({ ...current, items: [...current.items, blankReceiptItem()] })); setCosts(null); }}>Add item</button>
        <label className="block text-sm font-medium">Notes (optional)<textarea className={receiptField} rows={2} value={data.notes} onChange={(event) => edit('notes', event.target.value)} disabled={busy || preparing} /></label>
        {costs && <div className="my-3 rounded border border-blue-200 bg-blue-50 p-2 text-sm">Backend-verified receipt total: <strong>${Number(costs.order_total).toFixed(2)}</strong>. {data.cost_basis === 'total_only' ? 'The total is allocated to the single product; charge breakdowns remain unknown.' : 'Shipping, packing/other charges, tax and order discounts are allocated by merchandise value.'} When cents do not divide evenly, separate cost allocations preserve the exact total.</div>}
        {error && <p role="alert" className="mt-3 rounded border border-red-200 bg-red-50 p-2 text-sm text-red-800">{error}</p>}
        {notice && <p role="status" className="mt-3 text-sm text-green-800">{notice}</p>}
      </div>
      <footer className="flex justify-end gap-2 border-t border-slate-300 p-3"><button type="button" className={receiptButton} disabled={busy || preparing} onClick={() => void action('match')}>Find ASINs</button><button type="button" className={receiptButton} disabled={busy || preparing} onClick={() => void action('draft')}>Save draft</button><button type="button" className={receiptButton} disabled={busy || preparing} onClick={() => void action('preview')}>{busy ? 'Working...' : 'Preview landed costs'}</button><button type="button" className="rounded bg-slate-900 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" disabled={busy || preparing || calculating || !costs} onClick={() => void action('save')}>Save purchase</button></footer>
    </section>
  </div>;
}
