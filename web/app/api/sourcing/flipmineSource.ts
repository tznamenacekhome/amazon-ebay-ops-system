import { supabase } from './_supabase';

/** Source membership only; qualification/ranking remain in the normal list builder. */
export async function flipmineOpportunityIds(tabId?: string | null): Promise<string[]> {
  if (tabId && !/^[0-9a-f-]{36}$/i.test(tabId)) throw new Error('Invalid Flipmine tab reference.');
  const ids = new Set<string>();
  for (let start = 0; start <= 10000; start += 500) {
    let query = supabase.from('sourcing_flipmine_rows')
      .select(tabId ? 'opportunity_id' : 'opportunity_id,sourcing_flipmine_tabs!inner(status)')
      .not('opportunity_id', 'is', null).order('tab_id').order('row_number').range(start, start + 499);
    query = tabId ? query.eq('tab_id', tabId) : query.in('sourcing_flipmine_tabs.status', ['running', 'paused', 'partial', 'evaluated', 'completed']);
    const { data, error } = await query;
    if (error) throw new Error(`Flipmine source membership unavailable: ${error.message}`);
    if (start === 10000 && data?.length) throw new Error('Flipmine presentation bound reached; narrow the source tab.');
    for (const row of (data ?? []) as unknown as { opportunity_id: string | null }[]) if (row.opportunity_id) ids.add(row.opportunity_id);
    if (!data || data.length < 500) return [...ids];
  }
  return [...ids];
}
