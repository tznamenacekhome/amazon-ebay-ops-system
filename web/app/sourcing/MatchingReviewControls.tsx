"use client";
import { useState } from "react";
import type { MatchingFeedback } from "../api/sourcing/matchingFeedback";

export type Corrections = MatchingFeedback["corrections"];
const fields = ["coreGame","installment","generation","theme","platform","edition","region","packageType","completeness","digitalPhysical"];
const sources = ["amazon_title","ebay_title","ebay_game_name","ebay_item_specifics","amazon_catalog_metadata","ebay_description","primary_image","additional_images","category","platform_metadata","other"];

export function MatchingReviewControls({verdict,onVerdict,corrections,onCorrections,evidence,onEvidence}: {
  verdict: MatchingFeedback["pairVerdict"]; onVerdict:(v:MatchingFeedback["pairVerdict"])=>void;
  corrections:Corrections;onCorrections:(v:Corrections)=>void;evidence:string[];onEvidence:(v:string[])=>void;
}) {
  const [field,setField]=useState("edition");
  const [side,setSide]=useState<"amazon"|"ebay">("ebay");
  const [scope,setScope]=useState<"pair"|"asin">("pair");
  const [state,setState]=useState("value");
  const [value,setValue]=useState("");
  const [note,setNote]=useState("");
  return <div className="space-y-2 text-xs text-slate-700">
    <label className="block">Product pair verdict
      <select aria-label="Product pair verdict" value={verdict} onChange={e=>onVerdict(e.target.value as MatchingFeedback["pairVerdict"])} className="ml-2 rounded border p-1">
        <option value="not_provided">Not provided</option><option value="correct">Correct match</option><option value="incorrect">Incorrect match</option><option value="unsure">Not Sure</option>
      </select>
    </label>
    <details><summary>Evidence I used</summary><div className="grid grid-cols-2 gap-1 py-2">{sources.map(source=><label key={source}><input type="checkbox" checked={evidence.includes(source)} onChange={e=>onEvidence(e.target.checked?[...evidence,source]:evidence.filter(x=>x!==source))}/> {source.replaceAll("_"," ")}</label>)}</div></details>
    <details><summary>Correct Details</summary>
      <p className="my-2">Corrections are saved with this review, separately from original source values.</p>
      <div className="flex flex-wrap gap-1">
        <select aria-label="Correction field" value={field} onChange={e=>setField(e.target.value)}>{fields.map(f=><option key={f}>{f}</option>)}</select>
        <select aria-label="Correction side" value={side} onChange={e=>{setSide(e.target.value as "amazon"|"ebay");setScope("pair");}}><option value="amazon">Amazon</option><option value="ebay">eBay</option></select>
        <select aria-label="Correction state" value={state} onChange={e=>setState(e.target.value)}><option value="value">Corrected value</option><option value="unknown">Unknown</option><option value="explicitly_absent">Known absent</option><option value="not_applicable">Not applicable</option></select>
        {state==="value"?<input aria-label="Corrected value" value={value} onChange={e=>setValue(e.target.value)} className="w-full rounded border p-1"/>:null}
        <input aria-label="Correction note or source" placeholder="Optional note/source" value={note} onChange={e=>setNote(e.target.value)} className="w-full rounded border p-1"/>
        {side==="amazon"?<label><input type="checkbox" checked={scope==="asin"} onChange={e=>setScope(e.target.checked?"asin":"pair")}/> Apply to this ASIN</label>:<span>This eBay listing/pair only</span>}
        <button type="button" disabled={state==="value"&&!value.trim()} onClick={()=>{onCorrections([...corrections,{field,side,scope,state,value:state==="value"?value:null,note:note||null}]);setValue("");setNote("");}} className="rounded border px-2">Add correction to review</button>
      </div>
      {corrections.map((c,i)=><div key={i} className="mt-1">{c.side} {c.field}: {c.value??c.state} ({c.scope}) <button onClick={()=>onCorrections(corrections.filter((_,n)=>n!==i))}>Remove</button></div>)}
    </details>
  </div>;
}
