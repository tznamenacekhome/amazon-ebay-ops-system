type Run = {status:string;next_retry_at?:string|null;paused_resource?:string|null;summary?:Record<string,unknown>};
type Tab = {rows_found:number;summary:Record<string,number>};
export function flipmineStatus(run:Run|null,tabs:Tab[]) {
  const total=tabs.reduce((n,t)=>n+t.rows_found,0);
  const completed=tabs.reduce((n,t)=>n+['evaluated','duplicates','excluded','invalid'].reduce((sum,key)=>sum+(t.summary[key]??0),0),0);
  const remaining=Math.max(total-completed,0);
  const phase=run?.summary?.phase;
  const label=!run?'':run.status==='paused'?(run.paused_resource==='checkpoint'?'Paused — saved checkpoint':'Paused — eBay API limit reached'):
    run.status==='completed'?'Complete':run.status==='running'?(phase==='resuming'?'Resuming':'Processing'):
    run.status==='evaluated'?'Processing — checking Buy List and Closest Excluded':'Failed — unresolved work retained';
  return {label,total,completed,remaining,nextRetry:run?.next_retry_at??null};
}
export const pacificTime=(value:string)=>new Date(value).toLocaleString('en-US',{timeZone:'America/Los_Angeles',month:'short',day:'numeric',hour:'numeric',minute:'2-digit',second:'2-digit',timeZoneName:'short'});
