"""Bounded provider adapter feeding MBOP's existing seed builders and scorer."""
from __future__ import annotations
import datetime as dt
import logging
import time
from types import SimpleNamespace

import build_sourcing_seed_asins as seeds
from sourcing_common import paginate_table, chunked

LOG = logging.getLogger('flipmine')
ASIN_TABLES = {'amazon_sales_profitability', 'amazon_skus', 'vw_latest_amazon_listing_snapshot',
               'vw_latest_keepa_product_snapshot', 'wholesale_amazon_candidates',
               'amazon_catalog_item_identity_snapshots', 'sourcing_blocked_asins',
               'sourcing_sales_velocity_suppressions', 'amazon_fba_inventory_snapshots'}


class LocalRows:
    def __init__(self, rows): self.rows, self.start, self.end = rows[:], 0, len(rows)
    def order(self, key, desc=False):
        self.rows.sort(key=lambda row: row.get(key) or '', reverse=desc)
        return self
    def range(self, start, end): self.start, self.end = start, end + 1; return self
    def execute(self): return SimpleNamespace(data=self.rows[self.start:self.end])


class ScopedTable:
    def __init__(self, owner, name): self.owner, self.name = owner, name
    def select(self, columns='*', **options):
        if self.name == 'amazon_sales_orders': return LocalRows(self.owner.orders)
        query = self.owner.db.table(self.name).select(columns, **options)
        if self.name in ASIN_TABLES and not (self.name == 'amazon_fba_inventory_snapshots' and columns == 'captured_at'):
            query = query.in_('asin', self.owner.asins)
        return query
    def __getattr__(self, key): return getattr(self.owner.db.table(self.name), key)


class ScopedSeedDB:
    """Keep shared builders unchanged while bounding their reads to this small ASIN batch."""
    def __init__(self, db, asins):
        self.db, self.asins, self.orders = db, sorted(set(asins)), []
        profits = paginate_table(self, 'amazon_sales_profitability', 'amazon_order_id', max_rows=20000)
        ids = sorted({r['amazon_order_id'] for r in profits if r.get('amazon_order_id')})
        for batch in chunked(ids, 100):
            self.orders.extend(db.table('amazon_sales_orders').select('amazon_order_id,purchase_date,order_status')
                               .in_('amazon_order_id', batch).execute().data or [])
    def table(self, name): return ScopedTable(self, name)
    def rpc(self, *args, **kwargs): return self.db.rpc(*args, **kwargs)


class SourcingContext:
    def __init__(self, db, settings):
        self.db, self.settings, self.cache = db, settings, {}
        self._amazon = self._keepa = None

    @property
    def amazon(self):
        if self._amazon is None:
            from amazon_spapi_client import AmazonSPAPIClient
            self._amazon = AmazonSPAPIClient.from_env()
        return self._amazon

    def ensure_sources(self, asin):
        if self.db.table('sourcing_blocked_asins').select('asin').eq('asin', asin).limit(1).execute().data:
            return False
        eligibility = seeds.fetch_fresh_new_eligibility_by_asin(self.db, [asin]).get(asin)
        if eligibility:
            if eligibility['eligibility_status'] != 'eligible': return False
        else:
            from amazon_check_listing_restrictions import classify_restriction_payload, apply_blocklist_results
            result = classify_restriction_payload(asin, self.amazon.get_listings_restrictions(asin, condition_type='new_new'))
            if result.status == 'unknown': raise RuntimeError('Amazon eligibility could not be verified')
            apply_blocklist_results(self.db, [result])
            if result.status != 'sellable': return False
            time.sleep(.5)
        catalog = self.db.table('amazon_catalog_item_identity_snapshots').select('asin,fetched_at').eq('asin', asin).limit(1).execute().data
        if not catalog or not recent(catalog[0].get('fetched_at')):
            from amazon_sync_catalog_items import normalize_catalog_item, INCLUDED_DATA
            row = normalize_catalog_item(asin, self.amazon.get_catalog_item(asin, included_data=INCLUDED_DATA), self.amazon.config.marketplace_id)
            self.db.table('amazon_catalog_item_identity_snapshots').upsert(row, on_conflict='asin').execute()
            time.sleep(.5)
        keepa = self.db.table('vw_latest_keepa_product_snapshot').select('asin,captured_at').eq('asin', asin).limit(1).execute().data
        if not keepa or not recent(keepa[0].get('captured_at')):
            from keepa_client import KeepaClient
            from keepa_sync_products import build_snapshot_row, insert_keepa_rows, print_plan_summary
            if self._keepa is None: self._keepa = KeepaClient.from_env()
            balance = self._keepa.get_token_status()
            print_plan_summary([asin], balance)
            # Same conservative per-ASIN estimate as the existing adaptive Keepa job.
            if (balance.get('tokens_left') or 0) < 10:
                raise RuntimeError('Keepa token budget unavailable; retry this tab after refill')
            payload = self._keepa.get_products([asin], stats_days=90, history=False, rating=False, wait=False)
            products = [p for p in payload.get('products', []) if p.get('asin') == asin]
            if not products: raise RuntimeError('Keepa product evidence missing')
            rows = [build_snapshot_row(product=products[0], captured_at=dt.datetime.now(dt.UTC).isoformat(),
                    domain_id=self._keepa.config.domain_id, token_cost=payload.get('tokensConsumed'),
                    tokens_left=payload.get('tokensLeft'), source='flipmine_discovery')]
            insert_keepa_rows(self.db, rows, build_history=False, domain_id=self._keepa.config.domain_id, max_points_per_metric=0)
        return True

    def seed(self, asin):
        if asin in self.cache: return self.cache[asin]
        if not self.ensure_sources(asin): self.cache[asin] = None; return None
        scoped = ScopedSeedDB(self.db, [asin])
        planning = {}
        recent_seeds = seeds.build_recent_sales_seeds(scoped, self.settings, 1, planning_cache=planning)
        full_seeds = [] if recent_seeds else seeds.build_full_listing_seeds(scoped, self.settings, 1, planning_cache=planning)
        candidates = recent_seeds or full_seeds
        if not candidates:
            # Discovery-only ASINs use the same seed finalizer as the existing catalog feed.
            context = seeds.latest_catalog_context_by_asin(scoped)
            keepa = scoped.table('vw_latest_keepa_product_snapshot').select('*').eq('asin', asin).limit(1).execute().data
            if not keepa: raise RuntimeError('Authoritative catalog pricing missing')
            price = seeds.keepa_catalog_price(keepa[0])
            if price < self.settings.min_amazon_price: self.cache[asin] = None; return None
            title = ((context.get(asin, {}).get('amazon_catalog_item') or {}).get('relevant_attributes_json') or {}).get('title') or keepa[0].get('title')
            if not title: raise RuntimeError('Authoritative Amazon title missing')
            candidates = seeds.finalize_seeds([{'asin': asin, 'amazon_title': title, 'seller_sku': None,
                'units_sold_lookback': 0, 'last_sold_at': None, 'target_sale_price': price,
                'units_sold_60d': 0, 'fee_samples': []}], seeds.latest_inventory_by_asin(scoped), self.settings, 1,
                seeds.latest_inventory_planning_by_asin(scoped, [asin], cache=planning), context, scoped,
                blocked_asins=seeds.fetch_blocked_asins(scoped))
        result = candidates[0] if candidates else None
        if result:
            result['source_mode'] = 'flipmine'
            result['raw_context_json']['source_modes'] = list(set(result['raw_context_json'].get('source_modes', [])) | {'flipmine'})
        self.cache[asin] = result
        return result


def recent(value):
    parsed = seeds.parse_datetime_utc(value)
    return parsed is not None and parsed >= dt.datetime.now(dt.UTC) - dt.timedelta(days=7)
