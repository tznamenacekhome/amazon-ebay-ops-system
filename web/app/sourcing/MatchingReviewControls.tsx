"use client";
import type { MatchingFeedback } from "../api/sourcing/matchingFeedback";
import type { SourcingOpportunity } from "./types";
import { openingCell, reviewFieldKeys, type SavedCorrection } from "./reviewFields";

export type Corrections = MatchingFeedback["corrections"];
function sourceText(evidence?: Record<string,unknown>) {
  return Array.isArray(evidence?.sources) ? evidence.sources.map(source=>{
    const record=source as Record<string,unknown>; return [record.field,record.span].filter(Boolean).join(": ");
  }).filter(Boolean).join("; ") : "";
}
const sources = ["amazon_title","ebay_title","ebay_game_name","ebay_item_specifics","amazon_catalog_metadata","ebay_description","primary_image","additional_images","category","platform_metadata","other"];

export function ReviewEvidence({verdict,onVerdict,evidence,onEvidence}: {
  verdict: MatchingFeedback["pairVerdict"]; onVerdict:(v:MatchingFeedback["pairVerdict"])=>void;
  evidence:string[];onEvidence:(v:string[])=>void;
}) {
  return <div className="space-y-2 text-xs text-slate-700">
    <label>Optional pair verdict <select aria-label="Product pair verdict" value={verdict} onChange={e=>onVerdict(e.target.value as MatchingFeedback["pairVerdict"])} className="rounded border p-1">
      <option value="not_provided">Leave unchanged</option><option value="correct">Correct match</option><option value="incorrect">Incorrect match</option><option value="unsure">Not Sure</option>
    </select></label>
    <details><summary>Evidence I used</summary><div className="grid grid-cols-2 gap-1 py-2">{sources.map(source=><label key={source}><input type="checkbox" checked={evidence.includes(source)} onChange={e=>onEvidence(e.target.checked?[...evidence,source]:evidence.filter(x=>x!==source))}/> {source.replaceAll("_"," ")}</label>)}</div></details>
  </div>;
}

export function MatchingReviewControls({row,corrections,onCorrections,wrongRows,onWrongRows}: {
  row:SourcingOpportunity;corrections:Corrections;onCorrections:(v:Corrections)=>void;
  wrongRows:string[];onWrongRows:(v:string[])=>void;
}) {
  const comparison=row.diagnosticComparison;
  const saved=(row.latestReview?.corrections ?? []) as SavedCorrection[];
  const rows=(comparison?.rows ?? []).filter(r=>reviewFieldKeys[r.key]);
  function undo(key:string) { onCorrections(corrections.filter(c=>c.field!==reviewFieldKeys[key])); }
  function toggle(key:string,checked:boolean) {
    if(!checked && corrections.some(c=>c.field===reviewFieldKeys[key]) && !window.confirm("Discard the unsaved edits in this row?")) return;
    if(!checked) undo(key);
    onWrongRows(checked?[...wrongRows,key]:wrongRows.filter(k=>k!==key));
  }
  return <section className="border-l border-slate-200 p-4 text-sm text-slate-800">
    <h2 className="font-semibold text-slate-950">Product Comparison</h2>
    <p className="my-2 text-xs text-slate-600">Recorded evaluation: {comparison?.productIdentityVerdict ?? "unknown"}. Operator verdict: {row.latestReview?.pairVerdict ?? "not provided"}. Corrections are separate and have not been reevaluated.</p>
    <div className="mb-3 space-y-1 select-text text-xs">
      <p><strong>Amazon source title:</strong> {comparison?.rows.find(r=>r.key==="amazon_title")?.ebay ?? row.amazonTitle ?? "Unavailable"}</p>
      <p><strong>eBay source title:</strong> {row.ebayTitle ?? "Unavailable"}</p>
    </div>
    <table className="w-full table-fixed border-collapse text-xs"><thead><tr className="bg-slate-100 text-left"><th className="w-1/5 p-2">Field</th><th className="p-2">Amazon</th><th className="p-2">eBay</th><th className="w-14 p-2">Wrong</th></tr></thead><tbody>
      {rows.map(item=><tr key={item.key} className="border-b align-top"><th className="p-2 text-left font-medium">{item.label}
        <details className="mt-1 font-normal text-slate-500"><summary>Original / source</summary>{(["amazon","ebay"] as const).map(side=><p key={side}>{side}: {item[side] ?? "Unknown"} ({String((side==="amazon"?item.amazonEvidence:item.ebayEvidence)?.state ?? "unknown")}); {String((side==="amazon"?item.amazonEvidence:item.ebayEvidence)?.reason ?? "Source provenance unavailable")} {sourceText(side==="amazon"?item.amazonEvidence:item.ebayEvidence)}</p>)}</details>
        {corrections.some(c=>c.field===reviewFieldKeys[item.key])?<button type="button" className="mt-1 text-blue-700 underline" onClick={()=>undo(item.key)}>Undo row</button>:null}
      </th>{(["amazon","ebay"] as const).map(side=>{
        const original=openingCell(item,side,saved);
        const pending=corrections.find(c=>c.field===reviewFieldKeys[item.key]&&c.side===side);
        const value=pending?pending.value:original.value;
        const state=pending?.state ?? original.state;
        function edit(nextValue:string|null,nextState:string,scope:"pair"|"asin"=pending?.scope ?? "pair") {
          const rest=corrections.filter(c=>!(c.field===reviewFieldKeys[item.key]&&c.side===side));
          const same=(nextValue??"")===(original.value??"") && (nextValue ? !["unknown","not_applicable","explicitly_absent"].includes(original.state) : nextState===original.state);
          onCorrections(same?rest:[...rest,{field:reviewFieldKeys[item.key],side,scope,state:nextState,value:nextValue,note:null,before:{value:original.value,state:original.state,actionId:original.correction?.actionId??null}}]);
        }
        return <td key={side} className="break-words p-2">
          {wrongRows.includes(item.key)?<>
            <textarea aria-label={`${item.label} ${side} value`} className="min-h-14 w-full rounded border p-1" value={value??""} onChange={e=>edit(e.target.value||null,e.target.value?"value":"unknown")}/>
            <select aria-label={`${item.label} ${side} state`} className="w-full rounded border" value={["value","unknown","not_applicable","explicitly_absent"].includes(state)?state:"value"} onChange={e=>edit(e.target.value==="value"?value:null,e.target.value)}>
              <option value="value">Known value</option><option value="unknown">Unknown / cleared</option><option value="not_applicable">Not applicable</option><option value="explicitly_absent">Known absent</option>
            </select>
            {side==="amazon"&&pending?<label className="block"><input type="checkbox" checked={pending.scope==="asin"} onChange={e=>onCorrections(corrections.map(c=>c===pending?{...c,scope:e.target.checked?"asin":"pair"}:c))}/> Apply to this ASIN</label>:null}
          </>:<span>{value??state.replaceAll("_"," ")}</span>}
          {pending?<div className="text-amber-800">Corrected · pending</div>:original.correction?<div className="text-blue-700">Operator correction · {original.correction.scope} · {original.correction.recordedAt}</div>:null}
        </td>;
      })}<td className="p-2"><input type="checkbox" aria-label={`${item.label} Wrong`} checked={wrongRows.includes(item.key)} onChange={e=>toggle(item.key,e.target.checked)}/></td></tr>)}
    </tbody></table>
    <p className="mt-2 text-xs text-slate-500">Wrong flags an unreliable field; it does not judge the pair. Unedited fields are not certified.</p>
    <details className="mt-3 text-xs"><summary>Source details</summary>{comparison?.rows.filter(r=>["ebay_description","ebay_item_specifics","ebay_game_name"].includes(r.key)).map(r=><p className="my-2 whitespace-pre-wrap" key={r.key}><strong>{r.label}:</strong> {r.ebay??"Unavailable"}</p>)}</details>
    <div className="mt-2 text-xs text-slate-500"><p>Ignored wording: {comparison?.tokenHandling?.ignored.join(", ") || "Unavailable"}</p><p>Unclassified wording: {comparison?.tokenHandling?.unclassified.join(", ") || "Unavailable"}</p><p>Assigned tokens (excluded from installment comparison): {comparison?.tokenHandling?.assigned.join("; ") || "Unavailable"}</p></div>
  </section>;
}
