export type EbayQuotaOverview = {
  available: boolean;
  resources: Array<{ resource: string; quota_limit: number; calls_used: number; remaining: number;
    locallyReserved: number; utilization: number | null; reset_at: string | null;
    observed_at: string | null; blocked_until: string | null; reason: string | null; status: string }>;
  jobs: Array<{ resource: string; job_name: string; attempts: number }>;
  events?: Array<{ resource: string; job_name: string; event: string; total: number }>;
};

const pacific = (value: string | null) => value ? new Date(value).toLocaleString('en-US', {
  timeZone: 'America/Los_Angeles', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short',
}) : 'Unknown';

export function EbayApiQuota({ data }: { data?: EbayQuotaOverview }) {
  return <section className="mt-4 overflow-x-auto rounded-lg border border-slate-200 bg-white p-4">
    <h2 className="font-semibold">eBay API capacity</h2>
    <p className="mt-1 text-xs text-slate-500">Trading is one shared allowance across listing enrichment and operational jobs. Local reservations are already deducted from remaining capacity; Analytics can report late.</p>
    {!data?.available ? <p className="mt-2 text-sm">Quota telemetry unavailable.</p> : <>
      <table className="mt-3 w-full text-left text-sm"><thead><tr>
        {['Resource', 'Daily limit', 'Used / reserved', 'Remaining', 'Utilized', 'Reset (Pacific)', 'Status'].map(v => <th key={v} className="p-2">{v}</th>)}
      </tr></thead><tbody>{data.resources.map(q => <tr key={q.resource} className="border-t">
        <td className="p-2">{q.resource === 'trading' ? 'Trading — shared' : q.resource}</td>
        <td className="p-2">{q.quota_limit.toLocaleString()}</td><td className="p-2">{q.calls_used.toLocaleString()} / {q.locallyReserved.toLocaleString()}</td>
        <td className="p-2">{q.remaining.toLocaleString()}</td><td className="p-2">{q.utilization ?? '—'}%</td><td className="p-2">{pacific(q.reset_at)}</td>
        <td className="p-2">{q.status}{q.reason ? ` · ${q.reason}` : ''}{q.blocked_until ? ` · retry ${pacific(q.blocked_until)}` : ''}</td>
      </tr>)}</tbody></table>
      <details className="mt-2 text-xs"><summary className="cursor-pointer">Usage by job and operation today</summary>
        {data.jobs.map(j => <div key={`${j.resource}:${j.job_name}`} className="mt-1">{j.job_name}: {j.attempts} {j.resource} requests</div>)}
        {data.events?.map(e => <div key={`${e.resource}:${e.job_name}:${e.event}`} className="mt-1">{e.job_name} · {e.resource} · {e.event}: {e.total}</div>)}
      </details>
    </>}
  </section>;
}
