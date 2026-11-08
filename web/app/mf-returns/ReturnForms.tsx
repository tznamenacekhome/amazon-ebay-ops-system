"use client";
import { useState } from "react";
export type Row = Record<string, unknown> & { id: string };
export const button = "rounded border border-slate-300 bg-white px-3 py-2 text-sm disabled:opacity-50";
export const input = "rounded border border-slate-300 px-2 py-2 text-sm w-full";
export const localNow = () => { const d = new Date(); return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16); };
export const iso = (v: FormDataEntryValue | null) => v ? new Date(String(v)).toISOString() : null;
export const value = (v: unknown) => v == null ? "Unknown" : String(v);
export const date = (v: unknown) => v ? new Date(String(v)).toLocaleString() : "Unknown";
export function Field({ label, children }: { label: string; children: React.ReactNode }) { return <label className="block text-sm text-slate-700">{label}{children}</label>; }
export function Dialog({ title, close, children }: { title: string; close: () => void; children: React.ReactNode }) {
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-5"><section role="dialog" aria-modal="true" aria-label={title} className="max-h-[92vh] w-full max-w-6xl overflow-auto rounded bg-white p-5 shadow-xl"><div className="mb-4 flex justify-between gap-4"><h2 className="text-xl font-semibold">{title}</h2><button type="button" className={button} onClick={close}>Close without saving</button></div>{children}</section></div>;
}
export function InspectionForm({ row, packages, held, busy, save }: { row: Row; packages: Row[]; held: Row[]; busy: boolean; save: (data: Record<string, unknown>) => Promise<void> }) {
  const [release, setRelease] = useState("");
  const selected = held.find(x => x.id === release);
  return <form className="grid grid-cols-3 gap-3 border-t pt-4" onSubmit={async e => { e.preventDefault(); const f = new FormData(e.currentTarget); await save({ return_id: row.id, package_id: selected?.package_id || f.get("package"), quantity: Number(selected?.quantity || f.get("quantity")), product_scan: f.get("scan"), condition: f.get("condition"), disposition: f.get("disposition"), notes: f.get("notes"), missing_parts: f.get("missing_parts"), inspected_at: iso(f.get("inspected")), identity_confirmed: f.get("identity") === "on", uncertain_lineage_acknowledged: f.get("uncertain") === "on", ...(release ? { release_inspection: release } : {}) }); }}>
    <h3 className="col-span-3 font-semibold">Verify actual contents</h3>
    <p className="col-span-3 text-sm">A label scan only records package receipt. Scan the actual product identifier (ASIN, MSKU, UPC or serial), compare the product, count it and inspect its condition. Missing quantities are an explicit inspection finding. Saleable disposition alone restores available stock.</p>
    <Field label="Resolve inspection hold (optional)"><select className={input} value={release} onChange={e => setRelease(e.target.value)}><option value="">New inspection</option>{held.map(x => <option key={x.id} value={x.id}>{value(x.quantity)} held · {date(x.inspected_at)}</option>)}</select></Field>
    <Field label="Received package"><select name="package" className={input} required disabled={Boolean(selected)}>{packages.filter(p => p.received_at).map(p => <option value={p.id} key={p.id}>{value(p.tracking_number)}</option>)}</select></Field>
    <Field label="Count verified now"><input name="quantity" className={input} type="number" min="1" step="1" required disabled={Boolean(selected)} placeholder={selected ? value(selected.quantity) : "Explicit count"}/></Field>
    <Field label="Scan product identifier"><input autoComplete="off" name="scan" className={input} required/></Field>
    <Field label="Actual condition"><select name="condition" className={input} required><option value="">Select after inspection</option>{["new", "used_mint", "used_verygood", "used_good", "used_acceptable", "damaged", "wrong_item", "missing"].map(c => <option key={c}>{c}</option>)}</select></Field>
    <Field label="Disposition"><select name="disposition" className={input} required><option value="">Select explicitly</option><option value="saleable">Saleable MF stock</option><option value="inspection_hold">Inspection hold</option><option value="damaged">Damaged</option><option value="wrong_item">Wrong item</option><option value="missing">Missing item</option></select></Field>
    <Field label="Inspection time (your browser timezone)"><input name="inspected" className={input} type="datetime-local" defaultValue={localNow()} required/></Field>
    <Field label="Missing parts"><input name="missing_parts" className={input}/></Field>
    <Field label="Inspection notes"><textarea name="notes" className={input} required/></Field>
    <label className="col-span-3 text-sm"><input type="checkbox" name="identity"/> I verified this is the expected product. Required for saleable stock.</label>
    <label className="col-span-3 text-sm"><input type="checkbox" name="uncertain"/> If original shipment lots are unavailable, I explicitly accept unknown acquisition cost and flagged lineage.</label>
    <div className="col-span-3"><button className={button} disabled={busy || !packages.some(p => p.received_at)}>Save inspected quantities</button></div>
  </form>;
}
export function ClaimForm({ existing, busy, save }: { existing: Row | null; busy: boolean; save: (data: Record<string, unknown>, id?: string) => Promise<void> }) {
  const dt = (v: unknown) => v ? new Date(new Date(String(v)).getTime() - new Date(String(v)).getTimezoneOffset() * 60000).toISOString().slice(0, 16) : "";
  return <form key={existing?.id || "new"} className="grid grid-cols-3 gap-3 border-t pt-4" onSubmit={async e => { e.preventDefault(); const f = new FormData(e.currentTarget), d: Record<string, unknown> = {}; for (const key of ["claim_type", "case_id", "currency", "status", "resolution", "notes", "deadline_source"]) d[key] = f.get(key); for (const key of ["submitted_at", "next_follow_up", "resolved_at", "deadline_at"]) d[key] = iso(f.get(key)); for (const key of ["claimed_amount", "reimbursed_amount"]) d[key] = f.get(key) ? Number(f.get(key)) : null; await save(d, existing?.id); }}>
    <h3 className="col-span-3 font-semibold">{existing ? "Update manual claim" : "Manual reimbursement follow-up"}</h3>
    <p className="col-span-3 text-sm">Eligibility and filing deadline: Needs review. Verify the applicable program and current policy in Seller Central. This form records a case; it never submits a claim or refunds a customer.</p>
    {[['claim_type','Claim type'],['case_id','Case / claim ID'],['currency','Currency'],['claimed_amount','Claimed amount'],['reimbursed_amount','Reimbursed amount']].map(([key,label]) => <Field key={key} label={label}><input className={input} name={key} defaultValue={String(existing?.[key] ?? (key === 'currency' ? 'USD' : ''))} type={key.endsWith('amount') ? 'number' : 'text'} min="0" step="0.01" required={key === 'claim_type' || key === 'currency'}/></Field>)}
    <Field label="Status"><select name="status" className={input} defaultValue={String(existing?.status || "review")}>{["review","submitted","pending","appeal","resolved","denied","closed"].map(s => <option key={s}>{s}</option>)}</select></Field>
    {[["submitted_at","Submission"],["next_follow_up","Next follow-up"],["resolved_at","Resolution date"],["deadline_at","Reviewed applicable deadline"]].map(([key,label]) => <Field key={key} label={`${label} (browser timezone)`}><input className={input} name={key} type="datetime-local" defaultValue={dt(existing?.[key])}/></Field>)}
    <Field label="Deadline source (required if a deadline is entered)"><input name="deadline_source" className={input} defaultValue={String(existing?.deadline_source || "")}/></Field>
    <Field label="Resolution"><input name="resolution" className={input} defaultValue={String(existing?.resolution || "")}/></Field>
    <Field label="Notes / evidence references"><textarea name="notes" className={input} required defaultValue={String(existing?.notes || "")}/></Field>
    <div className="col-span-3"><button className={button} disabled={busy}>Save case tracking</button></div>
  </form>;
}
