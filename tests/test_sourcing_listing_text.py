import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations'))
from sourcing_listing_text import prepare_listing_description,readable_listing_text
from sourcing_match_rules import normalize_candidate_evidence,evaluate_static_match_rules
from video_game_identity import build_identity_comparison
CASES=json.loads(Path('tests/fixtures/phase3a_listing_captures_20261126.json').read_text())
BASE=next(r for r in CASES if r['row']==121)
class ListingTextTests(unittest.TestCase):
 def evaluate(self,description):
  c=copy.deepcopy(BASE['candidate']);c['raw_ebay_json']['description']=description;c['raw_ebay_json'].pop('shortDescription',None)
  return evaluate_static_match_rules(c,BASE['seed'],excluded_keywords=['promo','promotional'],identity_policy='phase3_shadow')
 def test_noncontent_attributes_styles_and_scripts(self):
  p=prepare_listing_description('<style>.promo-text {used:pre-owned}</style><script>"pre-owned demo"</script><p class="right-promo-block" title="used">Factory sealed.</p>')
  self.assertEqual(p['product_text'],'Factory sealed.');self.assertFalse(p['incomplete_markup'])
  r=self.evaluate('<style>used pre-owned promo</style><script>used promo</script><p class="promo-text">Factory sealed.</p>');self.assertEqual(r['condition_mismatch']['result'],'pass');self.assertEqual(r['excluded_keywords']['result'],'pass')
 def test_diagnostics_reuse_existing_raw_source_without_expanding_payload(self):
  r=self.evaluate('<style>used</style><p>Factory sealed.</p>')
  self.assertNotIn('raw_material_evidence',r['normalized_evidence'])
  self.assertNotIn('readable_text',r['normalized_evidence']['description_preparation'])
  self.assertEqual(r['normalized_evidence']['description'],'Factory sealed.')
 def test_entities_and_boundaries(self):
  text,_=readable_listing_text('<p>New &amp; sealed&nbsp;game.</p><table><tr><td>Case</td><td>has cracks.</td></tr></table>')
  self.assertIn('New & sealed game.',text);self.assertIn('Case\nhas cracks.',text)
  self.assertEqual(self.evaluate('<p>Case</p><p>has cracks.</p>')['condition_mismatch']['result'],'blocked')
 def test_malformed_markup_preserves_disclosures(self):
  self.assertIn('missing manual',prepare_listing_description('<div>New<p>missing manual')['product_text'])
  r=self.evaluate('Brand New.<style>used');self.assertEqual(r['condition_review']['result'],'review')
 def test_actual_six_templates(self):
  for row in [109,121,236,275,326,346]:
   with self.subTest(row=row):
    x=next(r for r in CASES if r['row']==row);before=copy.deepcopy(x);e=normalize_candidate_evidence(x['candidate']);r=evaluate_static_match_rules(x['candidate'],x['seed'],excluded_keywords=['promo'],identity_policy='phase3_shadow')
    self.assertNotIn('pre-owned',e['description'].lower());self.assertNotIn('promo-text',e['description']);self.assertEqual(r['condition_mismatch']['result'],'pass');self.assertNotIn('promo',r['excluded_keywords']['hits']);self.assertEqual(before,x)
    self.assertIn('pre-owned',e['raw_material_evidence']['description'].lower())
 def test_specific_used_opened_played_damage_and_seal_still_block(self):
  for text in ['This game is pre-owned.','This offered game is used.','Previously played game.','Opened to test this game.','Case has cracks.','Missing the plastic seal.','Visible cracks on case.']:
   with self.subTest(text=text):self.assertEqual(self.evaluate('<p>'+text+'</p>')['condition_mismatch']['result'],'blocked')
 def test_generic_ads_cannot_swallow_following_item_disclosure(self):
  self.assertEqual(self.evaluate('<p>Shop pre-owned tech. This game is used.</p>')['condition_mismatch']['result'],'blocked')
  self.assertEqual(self.evaluate('<p>Shop pre-owned tech</p><p>Factory sealed.</p>')['condition_mismatch']['result'],'pass')
 def test_categorical_policies_remain_material(self):
  for text in ['All our games are pre-owned.','Every item we sell is opened.','We only sell used games.']:
   with self.subTest(text=text):self.assertEqual(self.evaluate(text)['condition_mismatch']['result'],'blocked')
 def test_cosmetic_only_is_not_categorical_opened_policy(self):
  for text in ['The tear is cosmetic only - the item has not been opened and remains unopened/unused.', 'All our items have not been opened.']:
   with self.subTest(text=text):self.assertEqual(self.evaluate(text)['condition_mismatch']['result'],'pass')
 def test_testing_is_neutral(self):
  for text in ['Tested.','Tested and working.','All tested and working.']:
   with self.subTest(text=text):
    r=self.evaluate(text);self.assertEqual(r['condition_mismatch']['result'],'pass');self.assertEqual(r['condition_review']['result'],'pass')
 def test_mixed_inventory_and_missing_contents(self):
  self.assertEqual(self.evaluate('Mixed new and used games. Select your game.')['purchase_unit']['result'],'review')
  for text in ['This game has no manual.','Disc only.','Case only.']:
   self.assertEqual(self.evaluate(text)['incomplete_listing']['result'],'blocked')
 def test_promotional_demo_and_digital_products_remain_blocked(self):
  r=self.evaluate('This is a promotional demo disc, not for resale.');self.assertEqual(r['excluded_keywords']['result'],'blocked')
  self.assertEqual(self.evaluate('Digital download code. No physical disc.')['digital_download']['result'],'blocked')
 def test_categorical_policy_not_removed_inside_advertising(self):
  self.assertEqual(self.evaluate('Shop pre-owned tech. All our games are opened.')['condition_mismatch']['result'],'blocked')
 def test_no_new_evidence_manufactured(self):
  c=copy.deepcopy(BASE['candidate']);c['condition']=None;c['condition_id']=None;c['raw_ebay_json']['conditionId']=None;c['raw_ebay_json']['condition']=None;c['ebay_title']='Zoo Tycoon 2: Zookeeper Collection';c['raw_ebay_json']['shortDescription']=None;c['raw_ebay_json']['description']='Shop pre-owned tech.'
  r=evaluate_static_match_rules(c,BASE['seed'],identity_policy='phase3_shadow');self.assertEqual(r['condition_mismatch']['evidenceState'],'missing')
 def test_browse_trading_normalization_parity_and_raw_preservation(self):
  c=copy.deepcopy(BASE['candidate']);before=copy.deepcopy(c);e=normalize_candidate_evidence(c)
  def identity(c):return build_identity_comparison(amazon_title=BASE['seed']['amazon_title'],ebay_title=c['ebay_title'],seed=BASE['seed'],evidence=normalize_candidate_evidence(c),policy='phase3_shadow')
  a=identity(c);c['raw_ebay_json'].setdefault('mbopEvidence',{})['provider']='browse';b=identity(c)
  self.assertEqual(a['materialEvidenceHash'],b['materialEvidenceHash']);self.assertEqual(a['evidenceDecision'],b['evidenceDecision']);self.assertEqual(e['raw_material_evidence']['description'],' '.join(str(v or '')for v in [before['raw_ebay_json'].get('shortDescription'),before['raw_ebay_json']['description']]).strip())
if __name__=='__main__':unittest.main()
