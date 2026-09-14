"use client";
import { useEffect,useState } from "react";
import Link from "next/link";
import { amazonListingUrl, ebayListingUrl, type PlatformRelationship } from "./evidence";
import { MatchingReviewControls,type Corrections } from "../MatchingReviewControls";
import { reviewFieldKeys } from "../reviewFields";
import type { loadQueue } from "../../api/sourcing/adjudication/service";

type Row=Awaited<ReturnType<typeof loadQueue>>[number];
const labels:Record<string,string>={correct:"Confirmed Match",incorrect:"Incorrect Match",unsure:"Not Sure"};
export function ListingLinks({asin,ebayItemId}:{asin?:string|null;ebayItemId?:string|null}) {
  const amazon=amazonListingUrl(asin),ebay=ebayListingUrl(ebayItemId);
  return <div className="my-2 grid gap-2 text-sm md:grid-cols-2">
    <div><strong>Amazon</strong><p>ASIN: {asin??"Unknown"}</p>{amazon?<a className="text-blue-700 underline" href={amazon} target="_blank" rel="noopener noreferrer">Open Amazon Listing {"\u2197"}</a>:<span>Amazon link unavailable</span>}</div>
    <div><strong>eBay</strong><p>Item: {ebayItemId??"Unknown"}</p>{ebay?<a className="text-blue-700 underline" href={ebay} target="_blank" rel="noopener noreferrer">Open eBay Listing {"\u2197"}</a>:<span>eBay link unavailable</span>}</div>
  </div>;
}
export function AdjudicationEditor({row,onClose,onSaved}:{row:Row;onClose:()=>void;onSaved:()=>Promise<void>}) {
  const [corrections,setCorrections]=useState<Corrections>([]),[wrong,setWrong]=useState<string[]>(()=>row.latestReview.platformRelationship?.operatorRelationship==="wrong"?["platform_system"]:[]);
  const [notes,setNotes]=useState(""),[attested,setAttested]=useState(false),[variation,setVariation]=useState(false);
  const [busy,setBusy]=useState(false),[error,setError]=useState<string|null>(null);
  const [pending,setPending]=useState<Record<string,unknown>|null>(null);
  const [relationship,setRelationship]=useState<PlatformRelationship|"">(row.latestReview.platformRelationship?.operatorRelationship??"");
  const [amazonSupports,setAmazonSupports]=useState((row.latestReview.platformRelationship?.compatiblePlatforms?.amazon??[]).join(", "));
  const [ebaySupports,setEbaySupports]=useState((row.latestReview.platformRelationship?.compatiblePlatforms?.ebay??[]).join(", "));
  const supportList=(value:string)=>value.split(",").map(v=>v.trim()).filter(Boolean);
  const platformReview=<div className="mt-2 font-normal">
    <label>Relationship<select aria-label="Platform relationship" className="block w-full rounded border p-1" value={relationship} onChange={e=>{const next=e.target.value as PlatformRelationship|"";setRelationship(next);setWrong(next==="wrong"?[...new Set([...wrong,"platform_system"])]:wrong.filter(k=>k!=="platform_system"));}}>
      <option value="" disabled={Boolean(row.latestReview.platformRelationship)}>Not specified</option>{["match","compatible","wrong","unknown"].map(v=><option key={v} value={v}>{v[0].toUpperCase()+v.slice(1)}</option>)}
    </select></label>
    <p className="mt-1 text-xs">Relationship is separate from corrections and the overall pair verdict. Changing it retains pending corrections.</p>
    <details className="mt-1"><summary>Optional supported platforms</summary><p>Operator evidence only; comma-separated names. Does not change parsed values.</p>
      <label>Amazon<input disabled={!relationship} aria-label="Amazon supported platforms" className="w-full border p-1" value={amazonSupports} onChange={e=>setAmazonSupports(e.target.value)}/></label>
      <label>eBay<input disabled={!relationship} aria-label="eBay supported platforms" className="w-full border p-1" value={ebaySupports} onChange={e=>setEbaySupports(e.target.value)}/></label>
    </details>
  </div>;
  async function save(verdict:string) {
    setBusy(true);setError(null);
    const previousRelationship=row.latestReview.platformRelationship;
    const relationshipChanged=relationship!==(previousRelationship?.operatorRelationship??"")
      || JSON.stringify(supportList(amazonSupports))!==JSON.stringify(previousRelationship?.compatiblePlatforms?.amazon??[])
      || JSON.stringify(supportList(ebaySupports))!==JSON.stringify(previousRelationship?.compatiblePlatforms?.ebay??[]);
    const payload=pending??{queueId:row.queueId,requestId:crypto.randomUUID(),expectedAsin:row.asin,
      expectedEbayItemId:row.ebayItemId,expectedSnapshotHash:row.snapshotHash,expectedRevision:row.revision,
      identityAttested:attested,variationVerified:variation,notes,
      feedback:{pairVerdict:verdict,corrections,flaggedFields:[...new Set([...wrong.map(k=>reviewFieldKeys[k]),...corrections.map(c=>c.field)])],
        ...(relationship&&relationshipChanged?{fieldRelationships:[{field:"platform",operatorRelationship:relationship,compatiblePlatforms:{amazon:supportList(amazonSupports),ebay:supportList(ebaySupports)}}]}:{}),
        failedRuleFamilies:[...new Set(row.diagnosticComparison.rows.filter(r=>wrong.includes(r.key)).map(r=>r.ruleFamily).filter(Boolean))]}};
    setPending(payload);
    try {
      const response=await fetch("/api/sourcing/adjudication",{method:"POST",headers:{"Content-Type":"application/json","x-mbop-csrf":"1"},body:JSON.stringify(payload)});
      const data=await response.json();if(!response.ok){if(response.status===409)setPending(null);throw new Error(data.error??"Save failed");}
      await onSaved();onClose();
    }catch(e){setError(e instanceof Error?e.message:"Save failed");}finally{setBusy(false);}
  }
  return <div role="dialog" aria-modal="true" aria-label="Exact-pair identity adjudication" className="fixed inset-0 z-50 overflow-auto bg-slate-950/50 p-6"><div className="mx-auto max-w-6xl bg-white p-5 text-slate-900">
    <div className="flex justify-between"><h1 className="text-xl font-semibold">Identity Adjudication · {row.asin}</h1><button onClick={onClose} disabled={busy}>Close</button></div>
    <ListingLinks asin={row.asin} ebayItemId={row.ebayItemId}/>
    {!row.adjudicationEligible?<p className="my-2 bg-amber-50 p-2">Excluded from adjudication / informational only: {row.adjudicationExclusionReason}</p>:null}
    <p className="my-2">Reviewing frozen historical evidence. Saving records identity evidence only; it does not change buying eligibility, status or holds.</p>
    <p className="text-sm">eBay item {row.ebayItemId} · variation {row.variationId??"Unknown"} · source {row.sourceKind} · {row.sourceTimestamp}</p>
    <p className="text-sm">Reference ASIN {row.reference.asin}; snapshot {row.sourceSnapshotId??"frozen receipt assertion"}; evaluation {row.snapshotHash}</p>
    {row.currentPurchaseAsin!==row.asin?<p className="my-2 bg-amber-50 p-2">Current purchase ASIN is {row.currentPurchaseAsin}. You are reviewing the original {row.asin} pair; no assignment will be changed.</p>:null}
    <p className="my-2 text-sm">{row.adjudicationExclusionReason??row.auditReason}</p>
    <fieldset disabled={busy||Boolean(pending)||!row.adjudicationEligible}>
      <MatchingReviewControls row={{diagnosticComparison:row.diagnosticComparison,latestReview:row.latestReview,amazonTitle:row.reference.amazon_title,ebayTitle:row.candidate.ebay_title}} corrections={corrections} onCorrections={setCorrections} wrongRows={wrong} onWrongRows={setWrong} additionalRows={row.additionalRows} platformReview={platformReview}/>
      <details className="my-3"><summary>Stored parser token treatment</summary>{["amazon","ebay"].map(side=><pre key={side} className="whitespace-pre-wrap text-xs">{side}: {Object.keys(row.identity[side as "amazon"|"ebay"].tokenHandling??{}).length?JSON.stringify(row.identity[side as "amazon"|"ebay"].tokenHandling,null,2):"Token breakdown unavailable for this evaluation."}</pre>)}</details>
      <p className="text-xs">Derived base product, included contents and assigned year corrections are stored as separate v3 evidence. The frozen parser output is preserved.</p>
      <label className="my-3 block">Notes<textarea aria-label="Adjudication notes" className="block w-full rounded border p-2" value={notes} onChange={e=>setNotes(e.target.value)}/></label>
      <label className="block"><input type="checkbox" checked={attested} onChange={e=>setAttested(e.target.checked)}/> I explicitly verified this exact listing represents this exact ASIN product.</label>
      <label className="block"><input type="checkbox" checked={variation} onChange={e=>setVariation(e.target.checked)}/> {row.variationId && row.variationId!=="0" ? `I verified the exact stored variation ${row.variationId}.` : "I verified that variation selection is not applicable to this exact listing."}</label>
    </fieldset>
    {error?<p role="alert" className="my-3 text-red-800">{error} {error.includes("Reload")?"Close and reopen the queue after reloading. Unsaved edits remain visible here.":"Retry uses the same request; edits are locked until resolved."}</p>:null}
    {row.adjudicationEligible?<div className="mt-4 flex gap-3">
      {pending?<button disabled={busy} onClick={()=>save(String((pending.feedback as {pairVerdict:string}).pairVerdict))}>Retry save</button>:<>
        <button className="rounded bg-green-700 px-3 py-2 text-white" disabled={busy||!attested} onClick={()=>save("correct")}>Confirm Match</button>
        <button className="rounded bg-red-700 px-3 py-2 text-white" disabled={busy} onClick={()=>save("incorrect")}>Incorrect Match</button>
        <button disabled={busy} onClick={()=>save("unsure")}>Not Sure</button>
        <button disabled={busy} onClick={()=>save("not_provided")}>Save corrections only</button>
      </>}
    </div>:null}<p className="mt-2 text-xs">Confirm Match without verified variation scope is retained as evidence but does not qualify as Tier A. Unedited fields are not certified. Recheck is deferred; these are recorded evaluations.</p>
  </div></div>;
}
export default function AdjudicationPage() {
  const [rows,setRows]=useState<Row[]>([]),[error,setError]=useState<string|null>(null),[selected,setSelected]=useState<Row|null>(null);
  async function reload(){const response=await fetch("/api/sourcing/adjudication",{cache:"no-store"});const data=await response.json();if(!response.ok)throw new Error(data.error??"Queue unavailable");setRows(data.rows);setError(null);}
  useEffect(()=>{let active=true;fetch("/api/sourcing/adjudication",{cache:"no-store"}).then(async response=>{const data=await response.json();if(!response.ok)throw new Error(data.error??"Queue unavailable");if(active)setRows(data.rows);}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[]);
  return <main className="p-6 text-slate-900"><Link href="/sourcing" className="text-blue-700 underline">Back to Sourcing</Link><h1 className="my-4 text-2xl font-semibold">Identity Adjudication</h1>
    <p>{rows.filter(r=>r.adjudicationEligible&&r.latestReview.pairVerdict).length} of {rows.filter(r=>r.adjudicationEligible).length} reviewed (1 informational row excluded) · Evidence only · Phase 3 remains shadow-only</p>
    <div className="my-3 flex gap-4"><button onClick={()=>reload().catch(e=>setError(e.message))}>Reload queue</button><a href="/api/sourcing/adjudication?report=1" target="_blank" rel="noopener noreferrer">Export Tier A / negatives / unresolved</a></div>
    {error?<p role="alert">{error}. The frozen queue has not been replaced; reload when evidence storage is available.</p>:null}
    <table className="w-full text-sm"><thead><tr>{["ASIN / item","Amazon","eBay","Shadow","Why selected","Review"].map(x=><th className="border p-2 text-left" key={x}>{x}</th>)}</tr></thead><tbody>{rows.map(row=><tr key={row.queueId}>
      <td className="border p-2"><ListingLinks asin={row.asin} ebayItemId={row.ebayItemId}/></td><td className="border p-2">{row.reference.amazon_title}</td><td className="border p-2">{row.candidate.ebay_title}</td><td className="border p-2">{row.diagnosticComparison.productIdentityVerdict}</td><td className="max-w-lg border p-2">{row.adjudicationExclusionReason??row.auditReason}</td><td className="border p-2"><button className="text-blue-700 underline" disabled={!row.available} onClick={()=>setSelected(row)}>{!row.available ? "Unavailable" : !row.adjudicationEligible ? "Excluded from adjudication / informational only" : labels[row.latestReview.pairVerdict??""]??"Unreviewed"}</button>{row.unavailableReason?<p>{row.unavailableReason}</p>:null}{row.latestReview.requiresReReview?<p>Newer evidence: review again</p>:null}</td>
    </tr>)}</tbody></table>{selected?<AdjudicationEditor key={selected.queueId} row={selected} onClose={()=>setSelected(null)} onSaved={reload}/>:null}
  </main>;
}
