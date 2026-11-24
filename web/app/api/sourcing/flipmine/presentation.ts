/** Qualification/ranking remain in the normal Opportunities list builder. */
export async function presentationCounts(tabId: string, read: (url: string) => Promise<Response>) {
  const counts: Record<string, number> = {};
  for (const [name, scope, status] of [['buyList', 'all_open', 'open'], ['closestExcluded', 'closest_excluded', 'all']]) {
    const query = new URLSearchParams({ flipmineTabId: tabId, scope, status, sourceMode: 'all', limit: '250', fresh: '1', format: 'list' });
    const response = await read(`/api/sourcing/opportunities?${query}`);
    const body = await response.json();
    if (!response.ok || !Number.isFinite(body.summary?.total)) throw new Error('Opportunity presentation is not ready; evaluation is retained for retry.');
    counts[name] = body.summary.total;
  }
  return counts;
}
