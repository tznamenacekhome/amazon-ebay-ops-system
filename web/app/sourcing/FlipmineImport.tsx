'use client';
import { useEffect, useRef, useState } from 'react';
import { sourcingRequest } from './sourcingRequest';
import { mutationHeaders } from '../mutationHeaders';
import { flipmineStatus, pacificTime } from './flipmineStatus';
type Run = { run_id: string; status: string; started_at: string; error_summary?: string; next_retry_at?:string;paused_resource?:string;summary: Record<string, number | boolean | string> };
type Tab = { tab_id: string; tab_name: string; status: string; rows_found: number; error_summary?: string; summary: Record<string, number> };
type Quota={resource:string;remaining:number;quota_limit:number;observed_remaining:number;reset_at:string;reason?:string};
type State = { run: Run | null; tabs: Tab[]; history: Run[];quota?:{resources:Quota[];jobs:{job_name:string;resource:string;attempts:number}[]} };
export function FlipmineImport({ onComplete }: { onComplete: () => void }) {
  const [state, setState] = useState<State>({ run: null, tabs: [], history: [] });
  const [error, setError] = useState('');
  const [starting, setStarting] = useState(false);
  const callback = useRef(onComplete);
  useEffect(() => { callback.current = onComplete; }, [onComplete]);
  const notified = useRef('');
  const busy = starting || ['running', 'paused', 'evaluated'].includes(state.run?.status ?? '');
  const progress=flipmineStatus(state.run,state.tabs);
  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    async function read() {
      try {
        const response = await sourcingRequest('/api/sourcing/flipmine', { cache: 'no-store' });
        const body = await response.json();
        if (!response.ok) throw new Error(body.error);
        if (stopped) return;
        setState(body); setError('');
        if (body.run && ['completed', 'partial'].includes(body.run.status) && notified.current !== body.run.run_id) {
          notified.current = body.run.run_id; callback.current();
        }
        if (['running', 'paused', 'evaluated'].includes(body.run?.status)) timer = setTimeout(read, body.run.status==='paused'?30000:5000);
      } catch (e) { if (!stopped) { setError(e instanceof Error ? e.message : 'Status unavailable'); timer = setTimeout(read, 15000); } }
    }
    void read();
    return () => { stopped = true; clearTimeout(timer); };
  }, [starting]);
  async function start() {
    setStarting(true); setError('');
    try {
      const response = await sourcingRequest('/api/sourcing/flipmine', { method: 'POST', headers: mutationHeaders() });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error);
      setState(old => ({ ...old, run: { run_id: body.runId, status: body.status, started_at: new Date().toISOString(), summary: {} } }));
    } catch (e) { setError(e instanceof Error ? e.message : 'Import could not start'); }
    finally { setStarting(false); }
  }
  return <div className="mb-3 text-sm">
    <div className="flex flex-wrap items-center gap-3">
      <button disabled={busy} onClick={() => void start()} className="rounded border border-slate-400 bg-white px-3 py-1.5 font-medium disabled:opacity-50">{state.run?.status==='paused'?'Flipmine paused':busy ? 'Importing Flipmine…' : 'Import Flipmine'}</button>
      <span role="status">{state.run?.summary.no_new_tabs ? 'Nothing new to import. All discovered tabs were already completed.' : progress.label}{state.tabs.length?` · ${progress.completed} completed · ${progress.remaining} remaining`:''}</span>
    </div>
    {state.run?.status==='paused'&&progress.nextRetry?<p className="mt-1 text-amber-800">Retry eligible {pacificTime(progress.nextRetry)}. The saved import resumes at the next scheduled recovery check; no new tabs are discovered.</p>:null}
    {error || state.run?.error_summary ? <p className="mt-1 text-amber-800">{error || state.run?.error_summary}</p> : null}
    {state.tabs.length || state.history.length ? <details className="mt-1"><summary className="cursor-pointer text-slate-600">Flipmine progress / history</summary>
      {state.tabs.map(tab => <div key={tab.tab_id}>{tab.tab_name}: {tab.status} · {tab.rows_found} rows · evaluated {tab.summary.evaluated ?? 0} · duplicates {tab.summary.duplicates ?? 0} · invalid {tab.summary.invalid ?? 0} · failed {tab.summary.failed ?? 0} · Buy List {tab.summary.buyList ?? '—'} · Closest Excluded {tab.summary.closestExcluded ?? '—'}{tab.error_summary ? ` · ${tab.error_summary}` : ''}</div>)}
      {state.history.map(run => <div key={run.run_id} className="text-slate-500">{new Date(run.started_at).toLocaleString()}: {run.status}</div>)}
      {state.quota?.resources.map(q=><div key={q.resource}>{q.resource}: {q.remaining} available / {q.quota_limit}; API reported {q.observed_remaining} remaining; reset {q.reset_at?pacificTime(q.reset_at):'unknown'}{q.reason?` · ${q.reason}`:''}</div>)}
      {state.quota?.jobs.map(j=><div key={`${j.resource}:${j.job_name}`}>{j.job_name}: {j.attempts} {j.resource} requests today (since metering was enabled)</div>)}
    </details> : null}
  </div>;
}
