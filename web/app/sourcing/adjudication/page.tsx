"use client";
import { useEffect,useState } from "react";
import Link from "next/link";
import { amazonListingUrl, ebayListingUrl, variationFollowup, type VariationResolution, type PlatformRelationship } from "./evidence";
import { MatchingReviewControls,type Corrections } from "../MatchingReviewControls";
import { reviewFieldKeys } from "../reviewFields";
import type { loadQueue } from "../../api/sourcing/adjudication/service";

type Row=Awaited<ReturnType<typeof loadQueue>>[number];
const labels:Record<string,string>={correct:"Confirmed Match",incorrect:"Incorrect Match",unsure:"Not Sure",variation_scope:"Variation scope"};
export function ListingLinks({asin,ebayItemId,compact=false}:{asin?:string|null;ebayItemId?:string|null;compact?:boolean}) {
  const amazon=amazonListingUrl(asin),ebay=ebayListingUrl(ebayItemId);
  return <div className={`my-2 text-sm ${compact?"space-y-2":"grid gap-2 md:grid-cols-2"}`}>
    <div><strong>Amazon</strong><p className="break-all">ASIN: {asin??"Unknown"}</p>{amazon?<a className="text-blue-700 underline" href={amazon} target="_blank" rel="noopener noreferrer">Open Amazon Listing {"\u2197"}</a>:<span>Amazon link unavailable</span>}</div>
    <div><strong>eBay</strong><p className="break-all">Item: {ebayItemId??"Unknown"}</p>{ebay?<a className="text-blue-700 underline" href={ebay} target="_blank" rel="noopener noreferrer">Open eBay Listing {"\u2197"}</a>:<span>eBay link unavailable</span>}</div>
  </div>;
}
export function AdjudicationEditor({row,onClose,onSaved,variationOnly=false}:{row:Row;variationOnly?:boolean;onClose:()=>void;onSaved:(verdict:string,reviewState?:Pick<Row,"revision"|"latestReview">)=>Promise<void>}) {
  const [corrections,setCorrections]=useState<Corrections>([]);
  const [wrong,setWrong]=useState<string[]>(()=>[...new Set([
    ...Object.entries(reviewFieldKeys).filter(([,field])=>((row.latestReview.feedback?.flaggedFields??[]) as string[]).includes(field)).map(([key])=>key),
    ...(row.latestReview.platformRelationship?.operatorRelationship==="wrong"?["platform_system"]:[])
  ])]);
  const [notes,setNotes]=useState(row.latestReview.notes),[attested,setAttested]=useState(row.latestReview.identityAttested),[variation,setVariation]=useState<VariationResolution>(row.latestReview.variationResolution);
  const [busy,setBusy]=useState(false),[error,setError]=useState<string|null>(null);
  const [pending,setPending]=useState<Record<string,unknown>|null>(null);
  const [savedVerdict,setSavedVerdict]=useState<string|null>(null);
  const [relationship,setRelationship]=useState<PlatformRelationship|"">(row.latestReview.platformRelationship?.operatorRelationship??"");
  const [amazonSupports,setAmazonSupports]=useState((row.latestReview.platformRelationship?.compatiblePlatforms?.amazon??[]).join(", "));
  const [ebaySupports,setEbaySupports]=useState((row.latestReview.platformRelationship?.compatiblePlatforms?.ebay??[]).join(", "));
  const [savedState,setSavedState]=useState<Pick<Row,"revision"|"latestReview">|null>(null);
  const [scopeSuccess,setScopeSuccess]=useState(false);
  const [scopeAttempt,setScopeAttempt]=useState(false);
  const latestReview=savedState?.latestReview??row.latestReview;
  const pendingScope=pending?.reviewKind==="variation_scope";
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
  async function save(verdict:string,scopeOnly=false) {
    const isScope=pending?pending.reviewKind==="variation_scope":scopeOnly;
    setBusy(true);setError(null);setScopeSuccess(false);setScopeAttempt(isScope);
    try {
    const previousRelationship=row.latestReview.platformRelationship;
    const relationshipChanged=relationship!==(previousRelationship?.operatorRelationship??"")
      || JSON.stringify(supportList(amazonSupports))!==JSON.stringify(previousRelationship?.compatiblePlatforms?.amazon??[])
      || JSON.stringify(supportList(ebaySupports))!==JSON.stringify(previousRelationship?.compatiblePlatforms?.ebay??[]);
    const payload=pending??{queueId:row.queueId,requestId:crypto.randomUUID(),expectedAsin:row.asin,
      expectedEbayItemId:row.ebayItemId,expectedSnapshotHash:row.snapshotHash,expectedRevision:savedState?.revision??row.revision,
      ...(isScope?{reviewKind:"variation_scope",variationTargetActionId:latestReview.actionId,variationResolution:variation}:{
      identityAttested:verdict==="correct"&&attested,...(verdict==="correct"?{variationResolution:variation}:{}),notes,
      feedback:{pairVerdict:verdict,corrections,flaggedFields:[...new Set([...wrong.map(k=>reviewFieldKeys[k]),...corrections.map(c=>c.field)])],
        ...(relationship&&relationshipChanged?{fieldRelationships:[{field:"platform",operatorRelationship:relationship,compatiblePlatforms:{amazon:supportList(amazonSupports),ebay:supportList(ebaySupports)}}]}:{}),
        failedRuleFamilies:[...new Set(row.diagnosticComparison.rows.filter(r=>wrong.includes(r.key)).map(r=>r.ruleFamily).filter(Boolean))]}})};
    setPending(payload);
      const response=await fetch("/api/sourcing/adjudication",{method:"POST",headers:{"Content-Type":"application/json","x-mbop-csrf":"1"},body:JSON.stringify(payload),signal:AbortSignal.timeout(30000)});
      const data=await response.json().catch(()=>{throw new Error(`Save returned HTTP ${response.status} without a JSON response. Your session may need reauthentication.`);});
      if(!response.ok){if(response.status===409)setPending(null);throw new Error(data.error??`Save failed (HTTP ${response.status})`);}
      setPending(null);
      if(isScope) {
        setScopeSuccess(true);
        if(data.reviewState)setSavedState(data.reviewState);
        if(data.refreshError||!data.reviewState) {
          setSavedVerdict("variation_scope");
          throw new Error(`Variation scope saved, but queue readback failed: ${data.refreshError??"No saved qualification returned."}`);
        }
        await onSaved("variation_scope",data.reviewState);
        return;
      }
      setSavedVerdict(verdict);
      if(data.refreshError)throw new Error(`Review saved, but queue readback failed: ${data.refreshError}`);
      await onSaved(verdict,data.reviewState);onClose();
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
    <fieldset disabled={busy||savedVerdict!==null||!row.adjudicationEligible}>
      <section className="my-4 border-t pt-3" aria-labelledby="variation-heading">
        <h2 id="variation-heading" className="font-semibold">Variation scope</h2>
        <p className="my-2 text-sm">This is only about whether the exact eBay listing/variation identity has been verified. It does not affect profitability or business rules.</p>
        <select disabled={Boolean(pending)} required aria-label="Variation scope" className="w-full rounded border p-2" value={variation} onChange={e=>{setVariation(e.target.value as VariationResolution);setScopeSuccess(false);}}>
          <option value="not_applicable">Not applicable — single-product listing</option>
          <option value="verified">Exact variation verified</option>
          <option value="unknown">Unknown</option>
        </select>
        {row.adjudicationEligible&&latestReview.pairVerdict==="correct"?<button className="mt-2 rounded bg-blue-700 px-3 py-2 text-white disabled:opacity-50"
          disabled={busy||savedVerdict!==null||Boolean(pending&&!pendingScope)||latestReview.requiresReReview||(!pendingScope&&variation===latestReview.variationResolution)}
          onClick={()=>save("variation_scope",true)}>Save variation scope</button>:null}
        {scopeSuccess?<p role="status" className="my-2 text-green-800">Variation scope saved</p>:null}
        {pendingScope&&!busy?<p className="my-2 text-sm">The save has not been confirmed. Save variation scope retries the same request.</p>:null}
        {error&&scopeAttempt?<p role="alert" className="my-2 text-red-800">{error} Your selected value is retained.</p>:null}
        {variation==="verified"?<p className="my-2 text-sm">{latestReview.exactVariationId?`Exact stored variation: ${latestReview.exactVariationId}`:"No exact variation identifier is stored. You may save this selection, but it cannot qualify for Tier A. No identifier will be invented."}</p>:null}
        {variation==="unknown"?<p className="my-2 text-sm">Unknown can be saved. Confirm Match remains evidence but does not qualify for Tier A.</p>:null}
        <p className="my-2 text-sm">Current saved qualification: {latestReview.tierA?"Tier A":"Not Tier A"}. {variationOnly?"Only variation scope will be saved; existing review evidence is preserved.":"Unedited fields are not certified by Tier A."}</p>
      </section>
      <fieldset disabled={variationOnly||Boolean(pending)}>
      <MatchingReviewControls row={{diagnosticComparison:row.diagnosticComparison,latestReview:row.latestReview,amazonTitle:row.reference.amazon_title,ebayTitle:row.candidate.ebay_title}} corrections={corrections} onCorrections={setCorrections} wrongRows={wrong} onWrongRows={setWrong} additionalRows={row.additionalRows} platformReview={platformReview}/>
      <details className="my-3"><summary>Stored parser token treatment</summary>{["amazon","ebay"].map(side=><pre key={side} className="whitespace-pre-wrap text-xs">{side}: {Object.keys(row.identity[side as "amazon"|"ebay"].tokenHandling??{}).length?JSON.stringify(row.identity[side as "amazon"|"ebay"].tokenHandling,null,2):"Token breakdown unavailable for this evaluation."}</pre>)}</details>
      <p className="text-xs">Derived base product, included contents and assigned year corrections are stored as separate v3 evidence. The frozen parser output is preserved.</p>
      <label className="my-3 block">Notes<textarea aria-label="Adjudication notes" className="block w-full rounded border p-2" value={notes} onChange={e=>setNotes(e.target.value)}/></label>
      <label className="block"><input type="checkbox" checked={attested} onChange={e=>setAttested(e.target.checked)}/> I explicitly verified this exact listing represents this exact ASIN product.</label>
      </fieldset>

    </fieldset>
    <div className="sticky bottom-0 border-t bg-white py-3">
    {busy?<p role="status">{savedVerdict!==null?`${variationOnly?"Variation scope":labels[savedVerdict]??"Corrections"} saved. Updating queue…`:"Saving review…"}</p>:null}
    {savedVerdict!==null&&!busy?<p role="status">{variationOnly?"Variation scope":labels[savedVerdict]??"Corrections"} saved. The evidence is recorded.</p>:null}
    {error&&!scopeAttempt?<p role="alert" className="my-3 text-red-800">{error} {savedVerdict!==null?"Close and reload the queue to see the saved review. Do not resubmit it.":error.includes("Reload")?"Close and reopen the queue after reloading. Unsaved edits remain visible here.":pending?"Retry uses the same request; your unsaved edits are retained.":"Your unsaved edits are retained."}</p>:null}
    {row.adjudicationEligible?<div className="mt-4 flex gap-3">
      {savedVerdict!==null?<button disabled={busy} onClick={onClose}>Close saved review</button>:pending&&!pendingScope?<button disabled={busy} onClick={()=>save(String((pending.feedback as {pairVerdict:string}).pairVerdict))}>{busy?"Saving…":"Retry save"}</button>:variationOnly||pendingScope?null:<>
        <button className="rounded bg-green-700 px-3 py-2 text-white" disabled={busy||!attested} onClick={()=>save("correct")}>Confirm Match</button>
        <button className="rounded bg-red-700 px-3 py-2 text-white" disabled={busy} onClick={()=>save("incorrect")}>Incorrect Match</button>
        <button disabled={busy} onClick={()=>save("unsure")}>Not Sure</button>
        <button disabled={busy} onClick={()=>save("not_provided")}>Save corrections only</button>
      </>}
    </div>:null}<p className="mt-2 text-xs">Incorrect Match rejects this exact pair without Wrong fields, corrections or variation verification. Confirm Match requires identity verification; verified variation scope is required only for Tier A. Recheck is deferred; these are recorded evaluations.</p>
    </div>
  </div></div>;
}
export default function AdjudicationPage() {
  const [rows,setRows]=useState<Row[]>([]),[error,setError]=useState<string|null>(null),[selected,setSelected]=useState<Row|null>(null);
  const [success,setSuccess]=useState<string|null>(null);
  const [followupOnly,setFollowupOnly]=useState(false);
  const followup=variationFollowup(rows);
  const visibleRows=followupOnly?followup.rows:rows;
  async function reload(){const response=await fetch("/api/sourcing/adjudication",{cache:"no-store"});const data=await response.json();if(!response.ok)throw new Error(data.error??"Queue unavailable");setRows(data.rows);setError(null);}
  useEffect(()=>{let active=true;fetch("/api/sourcing/adjudication",{cache:"no-store"}).then(async response=>{const data=await response.json();if(!response.ok)throw new Error(data.error??"Queue unavailable");if(active)setRows(data.rows);}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[]);
  return <main className="bg-white p-6 text-slate-900"><Link href="/sourcing" className="text-blue-700 underline">Back to Sourcing</Link><h1 className="my-4 text-2xl font-semibold">Identity Adjudication</h1>
    <p>{rows.filter(r=>r.adjudicationEligible&&r.latestReview.pairVerdict).length} of {rows.filter(r=>r.adjudicationEligible).length} reviewed (1 informational row excluded) · Evidence only · Phase 3 remains shadow-only</p>
    <p className="my-2">{followup.reviewed} of {followup.total} variation scope reviewed. {followup.rows.length} confirmations remain unqualified.</p>
    <div className="my-3 flex gap-4"><button aria-pressed={followupOnly} onClick={()=>setFollowupOnly(!followupOnly)}>{followupOnly?"Show all adjudication rows":"Review confirmation variation scope"}</button><button onClick={()=>reload().catch(e=>setError(e.message))}>Reload queue</button><a href="/api/sourcing/adjudication?report=1" target="_blank" rel="noopener noreferrer">Export adjudicated corpus</a></div>
    {error?<p role="alert">{error}. The frozen queue has not been replaced; reload when evidence storage is available.</p>:null}
    {success?<p role="status" className="my-3 rounded bg-green-50 p-3 text-green-900">{success}</p>:null}
    <table className="w-full text-sm"><thead><tr>{["ASIN / item","Amazon","eBay","Shadow","Why selected","Review"].map(x=><th className="border p-2 text-left" key={x}>{x}</th>)}</tr></thead><tbody>{visibleRows.map(row=><tr key={row.queueId}>
      <td className="border p-2"><ListingLinks compact asin={row.asin} ebayItemId={row.ebayItemId}/></td><td className="border p-2">{row.reference.amazon_title}</td><td className="border p-2">{row.candidate.ebay_title}</td><td className="border p-2">{row.diagnosticComparison.productIdentityVerdict}</td><td className="max-w-lg border p-2">{row.adjudicationExclusionReason??row.auditReason}</td><td className="border p-2"><button className="text-blue-700 underline" disabled={!row.available} onClick={()=>setSelected(row)}>{!row.available ? "Unavailable" : !row.adjudicationEligible ? "Excluded from adjudication / informational only" : labels[row.latestReview.pairVerdict??""]??"Unreviewed"}</button>{row.unavailableReason?<p>{row.unavailableReason}</p>:null}<p>{row.latestReview.tierA?"Tier A":row.latestReview.pairVerdict==="correct"?`Not Tier A: ${row.latestReview.variationResolution}`:""}</p>{row.latestReview.requiresReReview?<p>Newer evidence: review again</p>:null}</td>
    </tr>)}</tbody></table>{selected?<AdjudicationEditor variationOnly={followupOnly} key={selected.queueId} row={selected} onClose={()=>setSelected(null)} onSaved={async(verdict,reviewState)=>{setSuccess(`${labels[verdict]??"Corrections"} saved for ${selected.asin} / ${selected.ebayItemId}.`);if(reviewState)setRows(current=>current.map(r=>r.queueId===selected.queueId?{...r,...reviewState}:r));else await reload();}}/>:null}
  </main>;
}
