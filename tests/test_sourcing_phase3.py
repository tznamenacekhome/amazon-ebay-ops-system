"""Phase 3 candidate policy tests. Legacy remains the production default."""
import sys
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations'))
from video_game_identity import build_identity_comparison, general_product_fields
from sourcing_match_rules import evaluate_static_match_rules, normalize_candidate_evidence
from score_sourcing_opportunities import score_candidate
from matching_feedback import apply_scoped_reviews


def inputs(amazon, ebay, asin='B000TEST00', game_name=None, system='PS 3'):
    seed = dict(asin=asin, amazon_title=amazon, system=system, target_sale_price=100,
                inventory_need_level='high', raw_context_json={})
    candidate = dict(asin=asin, ebay_title=ebay, ebay_item_id='v1|123456789|0', candidate_id='test-candidate',
                     seed_id='test-seed', sourcing_run_id='test-run', condition='Brand New', condition_id='1000',
                     item_location_country='US', landed_cost=10, price=10, shipping_cost=0,
                     buying_options=['FIXED_PRICE'], available_quantity=1,
                     raw_ebay_json={'localizedAspects': [{'name':'Game Name','value':game_name}] if game_name else [],
                                   'categories':[{'categoryId':'139973','categoryName':'Video Games'}]})
    return seed, candidate


SETTINGS = SimpleNamespace(excluded_keywords=[],item_location_countries=['US'],min_profit_dollars=5,min_roi_percent=40,best_offer_min_ask_percent=60)


def compare(amazon, ebay, **kwargs):
    seed, candidate = inputs(amazon, ebay, **kwargs)
    return build_identity_comparison(amazon_title=amazon, ebay_title=ebay, seed=seed,
                                    evidence=normalize_candidate_evidence(candidate), policy='phase3_shadow')


def review(seed, candidate, verdict='correct', created='2026-09-12T12:00:00+00:00', action='a', corrections=None):
    return {'action_id':action,'created_at':created,'asin':seed['asin'],'ebay_item_id':candidate['ebay_item_id'],
            'raw_action_context':{'matchingFeedback':{'version':'matching_feedback_v3','evidenceProvenance':'explicit',
                                  'pairVerdict':verdict,'corrections':corrections or []}},
            'snapshot':{'action_id':action,'listing_snapshot_id':'snapshot-'+action,'asin':seed['asin'],
                        'ebay_item_id':candidate['ebay_item_id'],'amazon_title':seed['amazon_title'],'amazon_system':seed['system'],
                        'ebay_title':candidate['ebay_title'],'ebay_condition':candidate['condition'],
                        'raw_ebay_json':deepcopy(candidate['raw_ebay_json'])}}


class Phase3IdentityTests(unittest.TestCase):
    def test_required_wrong_products(self):
        pairs = [
            ('Dirt - PlayStation 3','DiRT 3 PS3'),
            ('Nickelodeon Dance Wii','Nickelodeon Dance 2 Wii'),
            ('Gears of War Ultimate Edition Xbox One','Gears of War Ultimate Edition Rare Replay Xbox One'),
            ('Dragon Age Origins Xbox 360','Dragon Age Origins Awakening Expansion Pack Xbox 360'),
            *[('Rock Band 3 PS3',x+' PS3') for x in ('The Beatles Rock Band','Rock Band Metal Track Pack','Rock Band Country Track Pack','Rock Band Classic Rock Track Pack')],
            ('Shrek 2 Wii','Shrek the Third Wii'),('Shrek 2 Wii',"Shrek Smash N Crash Racing Wii"),
            ('Disney Infinity 2.0 Marvel Starter Pack PS3','Disney Infinity 3.0 Star Wars Starter Pack PS3'),
            ('Wii Play Motion Wii','Tiger Woods PGA Tour Wii'),
            ('New Carnival Games Wii',"Cookie's Counting Carnival Wii"),
            ('New Carnival Games Wii',"Shrek's Carnival Craze Wii"),
        ]
        for amazon, ebay in pairs:
            with self.subTest(amazon=amazon,ebay=ebay):
                self.assertEqual('non-match',compare(amazon,ebay)['evidenceDecision']['productIdentityVerdict'])

    def test_verified_dead_rising_base_reference_stays_base(self):
        # Exact-ASIN titles reconciled from frozen seed and purchase metadata.
        # B01JCV1QGE is the captured Dead Rising target, never Dead Rising 4.
        for ebay in ('Dead Rising 3 Xbox One','Dead Rising 4 Xbox One'):
            result=compare('Dead Rising [Xbox One]',ebay,asin='B01JCV1QGE',system='Xbox One')
            self.assertEqual('dead rising',result['amazon']['coreGame'])
            self.assertIsNone(result['amazon']['installment'])
            self.assertEqual('non-match',result['evidenceDecision']['productIdentityVerdict'])

    def test_omission_and_explicit_edition_contradiction(self):
        omitted=compare('Some Game Deluxe Edition PS3','Some Game PS3')
        self.assertEqual('unknown',omitted['comparisons']['edition']['result'])
        resolved=compare('Some Game Deluxe Edition PS3','Some Game PS3',game_name='Some Game Deluxe Edition')
        self.assertEqual('match',resolved['comparisons']['edition']['result'])
        conflict=compare('Some Game GOTY PS3','Some Game Complete Edition PS3')
        self.assertEqual('conflict',conflict['comparisons']['edition']['result'])
        self.assertIsNone(general_product_fields('Some Game complete with case/manual PS3')['edition'])

    def test_general_name_and_numbers(self):
        for title, expected in [('Nickelodeon Dance 2 PS3','2'),('Shrek the Third Wii','3'),('Final Fantasy XIV Online PS4','14'),('Disney Infinity 2.0 PS3','2.0'),('FIFA 2011 PS3','2011')]:
            with self.subTest(title=title): self.assertEqual(expected,general_product_fields(title)['installment'])
        for title in ['Rock Band PlayStation 3','Rock Band Xbox 360','New Super Mario Bros Wii 25th Anniversary','Dirt (Sony PlayStation 3, 2011) SKU 1234 lot of 2']:
            with self.subTest(title=title): self.assertIsNone(general_product_fields(title)['installment'])
        self.assertEqual('new super mario bros',general_product_fields('New Super Mario Bros Wii')['coreGame'])
        self.assertEqual('wii play motion',general_product_fields('Wii Play Motion Wii')['coreGame'])
        self.assertIsNone(general_product_fields('Disney Infinity')['generation'])
        self.assertEqual('country',general_product_fields('Rock Band Country Track Pack')['theme'])
        self.assertIsNone(general_product_fields('Rock Band Track Pack')['theme'])
        self.assertIn('rare replay',general_product_fields('Gears of War Ultimate Edition Rare Replay Xbox One')['coreGame'])
        self.assertEqual('20',general_product_fields('NBA 2K20 PS4')['installment'])

    def test_strong_conflicts_and_no_region_from_origin(self):
        result=compare('Dirt PS3','Dirt PS3',game_name='Dirt 3')
        self.assertEqual('review',result['comparisons']['coreGame']['result'])
        self.assertEqual('match',compare('Dirt PS3','Dirt PS3',game_name='Game')['comparisons']['coreGame']['result'])
        result=build_identity_comparison(amazon_title='Dirt',ebay_title='Dirt',seed={'asin':'B000QL0T36'},evidence={'country_of_origin_values':['Japan','China']},policy='phase3_shadow')
        self.assertIsNone(result['ebay']['region'])
        for key in ('edition','completeness','digitalPhysical','packageType','installment'):
            self.assertIsNone(result['amazon'][key])

    def test_exact_asin_catalog_isolation(self):
        seed={'asin':'B000QL0T36','raw_context_json':{'amazon_catalog_identity':{'asin':'B00ZMBLKPG','normalized_edition':'Deluxe Edition'}}}
        result=build_identity_comparison(amazon_title='Dirt PS3',ebay_title='Dirt PS3',seed=seed,policy='phase3_shadow')
        self.assertTrue(result['reference']['catalogRejected'])
        self.assertIsNone(result['amazon']['edition'])
        result['amazon']['fields']['edition']['value']='mutated'
        again=build_identity_comparison(amazon_title='Dirt PS3',ebay_title='Dirt PS3',seed=seed,policy='phase3_shadow')
        self.assertIsNone(again['amazon']['fields']['edition']['value'])
        seed,candidate=inputs('Dirt PS3','Dirt PS3')
        candidate['asin']='B00ZMBLKPG'
        result=evaluate_static_match_rules(candidate,seed,identity_policy='phase3_shadow')
        self.assertIsNone(result['identity_comparison']['amazon']['coreGame'])
        self.assertNotEqual('Probable Match',result['recommendation'])

    def test_populated_buy_list_retained_and_omission_recovered(self):
        pairs=[('Rock Band PlayStation 3','Rock Band PS3'),
               ('Final Fantasy XIV Online Complete Edition PS4','Final Fantasy 14 Online Complete Edition PS4')]
        for amazon,ebay in pairs:
            with self.subTest(amazon=amazon):
                seed,candidate=inputs(amazon,ebay,system=None)
                before=score_candidate(candidate,seed,SETTINGS)
                after=score_candidate(candidate,seed,SETTINGS,matching_context={'offline_identity_policy':'phase3_shadow'})
                self.assertEqual('open',before['status']);self.assertEqual('open',after['status'])
        seed,candidate=inputs('Some Game Deluxe Edition PS3','Some Game PS3',game_name='Some Game Deluxe Edition')
        self.assertEqual('rejected',score_candidate(candidate,seed,SETTINGS)['status'])
        self.assertEqual('open',score_candidate(candidate,seed,SETTINGS,matching_context={'offline_identity_policy':'phase3_shadow'})['status'])

    def test_review_loss_is_not_reported_as_profitability_failure(self):
        seed,candidate=inputs('Dirt PS3','Dirt PS3',game_name='Dirt 3')
        scored=score_candidate(candidate,seed,SETTINGS,matching_context={'offline_identity_policy':'phase3_shadow'})
        self.assertEqual('rejected',scored['status'])
        self.assertEqual('review_threshold',scored['matching_diagnostics_json']['presentationDecision']['primaryReason']['code'])
        self.assertFalse(any(row.get('reasonCode')=='profitability' for row in scored['matching_diagnostics_json']['decisionTrace']))

    def test_operator_dismissal_not_invented_from_equal_titles(self):
        result=compare('Mario Kart Live Home Circuit Mario Set','Mario Kart Live Home Circuit Mario Set',asin='B08H9KGMWK',system=None)
        self.assertEqual('match',result['evidenceDecision']['productIdentityVerdict'])
        # Textual agreement does not disprove the unresolved physical-version label.


class Phase3ReviewTests(unittest.TestCase):
    def setUp(self):
        self.seed,self.candidate=inputs('Some Game PS3','Some Game PS3')
        self.identity=compare('Some Game PS3','Some Game PS3')

    def apply(self, rows, candidate=None):
        return apply_scoped_reviews(self.identity,candidate or self.candidate,self.seed,rows,evaluated_at='2026-09-13T00:00:00+00:00')

    def test_latest_verdict_and_cutoff(self):
        positive=review(self.seed,self.candidate)
        negative=review(self.seed,self.candidate,'incorrect','2026-09-12T13:00:00+00:00','b')
        future=review(self.seed,self.candidate,'correct','2026-09-14T00:00:00+00:00','c')
        self.assertEqual('non-match',self.apply([positive,negative,future])['evidenceDecision']['productIdentityVerdict'])
        unsure=review(self.seed,self.candidate,'unsure','2026-09-12T14:00:00+00:00','d')
        self.assertEqual('needs_review',self.apply([positive,negative,unsure])['evidenceDecision']['productIdentityVerdict'])

    def test_new_material_evidence_requires_review(self):
        positive=review(self.seed,self.candidate)
        changed=deepcopy(self.candidate);changed['raw_ebay_json']['image']={'imageUrl':'new-picture'}
        self.assertEqual('needs_review',self.apply([positive],changed)['evidenceDecision']['productIdentityVerdict'])
        positive['snapshot']={}
        self.assertEqual('needs_review',self.apply([positive])['evidenceDecision']['productIdentityVerdict'])

    def test_corrections_provenance_and_scope(self):
        correction={'field':'edition','side':'amazon','scope':'asin','state':'supported','value':'Deluxe Edition','before':None}
        row=review(self.seed,self.candidate,corrections=[correction])
        row['ebay_item_id']='different';row['snapshot']['ebay_item_id']='different'
        result=self.apply([row]);self.assertEqual('applied',result['correctionApplication'][0]['result'])
        self.assertEqual('operator_correction',result['amazon']['fields']['edition']['sources'][0]['field'])
        self.assertIsNone(result['amazon']['fields']['edition']['before']['value'])
        correction['side']='ebay'
        row=review(self.seed,self.candidate,corrections=[correction]);self.assertEqual([],self.apply([row])['correctionApplication'])

    def test_confirm_match_keeps_business_and_lifecycle_guards(self):
        row=review(self.seed,self.candidate)
        context={'offline_identity_policy':'phase3_shadow','offline_scoped_reviews':[row],'offline_review_cutoff':'2026-09-13T00:00:00+00:00'}
        expensive=deepcopy(self.candidate);expensive.update(price=98,landed_cost=98)
        self.assertEqual('rejected',score_candidate(expensive,self.seed,SETTINGS,matching_context=context)['status'])
        history={(self.seed['asin'],self.candidate['ebay_item_id']):{'action_type':'dismissed','status':'dismissed'}}
        result=score_candidate(self.candidate,self.seed,SETTINGS,matching_context=context,historical_status_by_key=history)
        self.assertNotEqual('open',result['status'])

    def test_exact_positive_supersedes_older_memory_but_not_newer(self):
        row=review(self.seed,self.candidate)
        negative={'matching_intelligence_example_id':'negative','match_label':'non_match','reviewed_at':'2026-09-11T00:00:00+00:00'}
        context={'offline_identity_policy':'phase3_shadow','offline_scoped_reviews':[row],'offline_review_cutoff':'2026-09-13T00:00:00+00:00',
                 'examples_by_key':{(self.seed['asin'],self.candidate['ebay_item_id']):[negative]}}
        self.assertEqual('open',score_candidate(self.candidate,self.seed,SETTINGS,matching_context=context)['status'])
        negative['reviewed_at']='2026-09-12T15:00:00+00:00'
        changed=score_candidate(self.candidate,self.seed,SETTINGS,matching_context=context)
        self.assertEqual('rejected',changed['status'])
        self.assertEqual('needs_review',changed['matching_diagnostics_json']['static_rules']['identity_comparison']['evidenceDecision']['productIdentityVerdict'])

    def test_field_only_action_does_not_supersede_pair_verdict(self):
        negative=review(self.seed,self.candidate,'incorrect')
        correction=review(self.seed,self.candidate,'not_provided','2026-09-12T13:00:00+00:00','b',
                          [{'field':'platform','side':'ebay','scope':'pair','state':'supported','value':'PS 3'}])
        result=self.apply([negative,correction])
        self.assertEqual('non-match',result['evidenceDecision']['productIdentityVerdict'])
        self.assertEqual('PlayStation 3',result['ebay']['platform'])

    def test_correct_pair_does_not_certify_parsed_fields(self):
        self.identity['ebay']['fields']['edition'].update(value='Incorrect parsed edition',state='supported')
        result=self.apply([review(self.seed,self.candidate)])
        self.assertEqual('match',result['evidenceDecision']['productIdentityVerdict'])
        self.assertEqual('Incorrect parsed edition',result['ebay']['fields']['edition']['value'])
        self.assertEqual('unknown',result['comparisons']['edition']['result'])


if __name__=='__main__': unittest.main()
