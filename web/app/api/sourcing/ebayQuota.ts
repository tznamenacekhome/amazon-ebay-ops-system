import { supabase } from './_supabase';
export async function ebayQuotaOverview() {
  const day = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Los_Angeles', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
  const [limits, usage, events] = await Promise.all([
    supabase.from('ebay_api_resource_limits').select('resource,quota_limit,calls_used,remaining,observed_count,observed_remaining,reset_at,window_seconds,observed_at,blocked_until,reason').order('resource').limit(20),
    supabase.from('ebay_api_usage').select('resource,job_name,day,attempts').eq('day', day).order('attempts', { ascending: false }).limit(50),
    supabase.from('ebay_api_events').select('resource,job_name,event,total').eq('day', day).order('total', { ascending: false }).limit(100),
  ]);
  if (limits.error || usage.error) return { available: false, resources: [], jobs: [] };
  return { available: true, resources: (limits.data ?? []).map(q => ({ ...q,
    locallyReserved: Math.max(Number(q.calls_used) - Number(q.observed_count ?? 0), 0),
    utilization: q.quota_limit ? Math.round(100 * (q.quota_limit - q.remaining) / q.quota_limit) : null,
    status: q.blocked_until && Date.parse(q.blocked_until) > Date.now() ? 'Paused' :
      !q.observed_at || Date.now() - Date.parse(q.observed_at) > 300_000 || !q.reset_at || Date.parse(q.reset_at) <= Date.now() ? 'Needs quota refresh' : q.remaining <= 0 ? 'Exhausted' : 'Available',
  })), jobs: usage.data ?? [], events: events.data ?? [], eventsAvailable: !events.error };
}
