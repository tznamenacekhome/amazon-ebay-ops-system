"""Read-only deployed planning RPC/cache check; no eBay calls or workflow writes."""
from build_sourcing_seed_asins import latest_inventory_planning_by_asin
from sourcing_common import get_supabase_client


def main():
    client = get_supabase_client()
    # Select a small indexed ASIN slice, not a sorted history scan.
    sample = client.table('amazon_inventory_planning_snapshots').select('asin').order('asin').limit(100).execute().data
    asins = sorted({r['asin'] for r in sample if r.get('asin')})
    if not asins:
        raise RuntimeError('No planning ASINs available for the check')
    cache = {}
    rows = latest_inventory_planning_by_asin(client, asins, cache=cache)
    if set(rows) != set(asins):
        raise RuntimeError('Planning check did not return every sampled ASIN')
    allowed_raw = {'inv-age-31-to-60-days', 'inv-age-61-to-90-days', 'sales-shipped-last-30-days'}
    if any(set(r['raw_planning_json']) != allowed_raw for r in rows.values()):
        raise RuntimeError('Unexpected planning raw projection')
    class NoDatabase:
        def rpc(self, *args, **kwargs):
            raise RuntimeError('Shared cache unexpectedly queried the database')
    if latest_inventory_planning_by_asin(NoDatabase(), asins, cache=cache) != rows:
        raise RuntimeError('Cache changed planning results')
    print(f'PLANNING_LOOKUP_CHECK passed: {len(asins)} ASINs; compact projection and shared cache verified', flush=True)


if __name__ == '__main__':
    main()
