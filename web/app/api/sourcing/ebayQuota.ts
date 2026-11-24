import { supabase } from './_supabase';
export async function ebayQuotaOverview() {
  const day = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Los_Angeles', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
  const [limits, usage] = await Promise.all([
    supabase.from('ebay_api_resource_limits').select('resource,quota_limit,calls_used,remaining,observed_count,observed_remaining,reset_at,window_seconds,observed_at,blocked_until,reason').order('resource').limit(20),
    supabase.from('ebay_api_usage').select('resource,job_name,day,attempts').eq('day', day).order('attempts', { ascending: false }).limit(50),
  ]);
  if (limits.error || usage.error) return { available: false, resources: [], jobs: [] };
  return { available: true, resources: limits.data ?? [], jobs: usage.data ?? [] };
}
