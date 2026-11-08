import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations'))
from inventory_reconcile import project_purchase_state, build_mbop_positions
class MerchantProjection(unittest.TestCase):
    def test_mf_remains_home_with_original_acquisition_cost(self):
        row={'item_id':'source','purchase_id':'purchase','asin':'B07RCCHQLD','quantity':2,'unit_cost':12.34,'current_status':'listed'}
        meta={'source':{'marketplace':'Amazon','raw_import_json':{'listing_fulfillment_method':'MF'}}}
        position=build_mbop_positions([row],meta,{},set())[0]
        self.assertEqual(position['inventory_state'],'home_amazon_mfn_listed')
        self.assertEqual(position['physical_location'],'home')
        self.assertEqual(position['unit_cost'],12.34)
        self.assertEqual(position['total_cost'],24.68)
        self.assertTrue(position['needs_reconciliation'])
    def test_existing_fba_projection_unchanged(self):
        row={'asin':'B07RCCHQLD','current_status':'listed'}
        self.assertEqual(project_purchase_state(row,{'marketplace':'Amazon'},True,set()).inventory_state,'outbound_to_amazon')
        self.assertEqual(project_purchase_state(row,{'marketplace':'Amazon'},False,set()).inventory_state,'sold_amazon')
    def test_shipped_mf_lot_is_not_projected_as_physically_present(self):
        row={'item_id':'source','asin':'B07RCCHQLD','quantity':2,'unit_cost':12.34,'current_status':'listed'}
        meta={'source':{'marketplace':'Amazon','raw_import_json':{'listing_fulfillment_method':'MF'},'mf_on_hand':0}}
        self.assertEqual(build_mbop_positions([row],meta,{},set()),[])

if __name__=='__main__':unittest.main()
