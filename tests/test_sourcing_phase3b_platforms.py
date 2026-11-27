import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations'))
from sourcing_platform_policy import platform_eligibility
class Phase3BPlatforms(unittest.TestCase):
 def test_operator_exclusions(self):
  for name in ['PS','PS1','PSX','Original PlayStation','PlayStation 1','Dreamcast','Sega CD','Mega-CD','Mega CD','GameCube','DS','GBA']:
   with self.subTest(name=name):self.assertEqual(platform_eligibility({'system':name})['result'],'blocked')
 def test_unchanged_eligible_platforms(self):
  for name in ['PS 2','PS 3','PS 4','PS 5','PSP','PS Vita','3DS','Switch','Switch 2','Wii','Wii U','Xbox','Xbox 360','Xbox One','Xbox Series X','Xbox Series S','PC','Sega Saturn']:
   with self.subTest(name=name):self.assertEqual(platform_eligibility({'system':name})['result'],'pass')
 def test_historical_references_are_not_offered_platforms(self):
  seed={'asin':'B000TEST00','system':'PS 4','amazon_title':'A PS4 remake of original PlayStation classic'}
  c={'ebay_title':'PS4 game','raw_ebay_json':{'description':'Originally released on PS1 and Dreamcast.','localizedAspects':[{'name':'Platform','value':'PlayStation 4'}]}}
  self.assertEqual(platform_eligibility(seed,c)['result'],'pass')
  self.assertEqual(platform_eligibility({'system':'PC','amazon_title':'PC CD-ROM'}, {'raw_ebay_json':{'description':'Physical CD-ROM software'}})['result'],'pass')
if __name__=='__main__':unittest.main()
