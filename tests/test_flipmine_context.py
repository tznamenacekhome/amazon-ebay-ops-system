import copy
import datetime as dt
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations'))
from flipmine_context import SourcingContext
from test_ebay_sourcing_search import settings

class Query:
    def __init__(self, rows): self.rows=copy.deepcopy(rows)
    def select(self,*a,**kw): return self
    def in_(self,key,values): self.rows=[r for r in self.rows if r.get(key) in values];return self
    def eq(self,key,value): return self.in_(key,[value])
    def order(self,key,desc=False): self.rows.sort(key=lambda r:str(r.get(key) or ''),reverse=desc);return self
    def range(self,start,end): self.rows=self.rows[start:end+1];return self
    def limit(self,n): self.rows=self.rows[:n];return self
    def __getattr__(self,key): return lambda *a,**kw:self
    def execute(self): return SimpleNamespace(data=self.rows)
class DB:
    def __init__(self):
        now=dt.datetime.now(dt.UTC).isoformat()
        self.rows={'amazon_sales_profitability':[dict(asin='B000000001',amazon_order_id='order',quantity=3,sale_price=120,amazon_fees_excluding_fulfillment=15,fulfillment_cost=3,title='Mario Kart 8 Deluxe Nintendo Switch')],
            'amazon_sales_orders':[dict(amazon_order_id='order',purchase_date=now)],
            'vw_latest_keepa_product_snapshot':[dict(asin='B000000001',title='Mario Kart 8 Deluxe Nintendo Switch',product_group='Video Games',buy_box_price_avg90_cents=4000)],
            'amazon_catalog_item_identity_snapshots':[dict(asin='B000000001',normalized_platform='Switch',relevant_attributes_json={'title':'Mario Kart 8 Deluxe Nintendo Switch'})]}
    def table(self,name): return Query(self.rows.get(name,[]))
    def rpc(self,*a,**kw): return Query([])

class ContextTests(unittest.TestCase):
    def context(self,db):
        config=settings();config.min_amazon_price=20.99;config.sales_lookback_days=90;config.inventory_need_months_threshold=2
        return SourcingContext(db,config)
    def test_real_recent_seed_builder_retains_velocity_fees_and_authoritative_title(self):
        db=DB();ctx=self.context(db)
        with patch.object(ctx,'ensure_sources',return_value=True): result=ctx.seed('B000000001')
        self.assertEqual(result['source_mode'],'flipmine');self.assertEqual(result['units_sold_90d'],3)
        self.assertEqual(result['target_sale_price'],40);self.assertEqual(result['raw_context_json']['estimated_fee_cost'],6)
        self.assertIn('Nintendo Switch',result['amazon_title'])
        self.assertIs(ctx.seed('B000000001'),result)
    def test_discovery_only_asin_uses_real_common_seed_finalizer(self):
        db=DB();db.rows['amazon_sales_profitability']=[];ctx=self.context(db)
        with patch.object(ctx,'ensure_sources',return_value=True): result=ctx.seed('B000000001')
        self.assertIsNotNone(result);self.assertEqual(result['source_mode'],'flipmine')
        self.assertEqual(result['units_sold_90d'],0);self.assertEqual(result['target_sale_price'],40)
    def test_blocked_or_ineligible_seed_is_terminal_exclusion(self):
        ctx=self.context(DB())
        with patch.object(ctx,'ensure_sources',return_value=False): self.assertIsNone(ctx.seed('B000000001'))

if __name__=='__main__':unittest.main()

