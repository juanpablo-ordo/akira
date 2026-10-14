import unittest
from datetime import datetime, timezone

from engine import Engine
from strategy import Setup
from tests.fixtures import PendingCase


class QualityFirstV121Tests(PendingCase, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.cfg['execution']['require_primary_structural_engine']=True
        self.cfg['execution']['require_observed_target']=True
        self.cfg['execution']['minimum_structural_grade']='A'
        self.cfg['symbol_profiles']['BTCUSDm']['pending_structural_quality_min']=85
        self.cfg['symbol_profiles']['BTCUSDm']['pending_structural_activation_min']=16
        self.cfg['symbol_profiles']['XAUUSDm']['pending_structural_quality_min']=86
        self.cfg['symbol_profiles']['XAUUSDm']['pending_structural_activation_min']=18
        self.e = Engine(self.g, self.cfg, self.g.log)
        self.addCleanup(self.e.close)
        self.e.warmup()

    def test_executable_candidates_are_primary_structural_only_and_weak_map_is_never_forced(self):
        for symbol, cache in self.e.planner.caches.items():
            q = self.g.quote(symbol)
            plans = self.e.planner.proposed_pending_plans(symbol, cache.setups, q, all_candidates=True)
            for p in plans:
                self.assertTrue(p.key.startswith('SWING:'), (symbol, p.key, p.reason))
            audit=self.e.planner.pending_candidate_audit[symbol]
            self.assertTrue(any(x.get('reject_code')=='unobserved_structural_origin' for x in audit), symbol)

    def test_xau_structural_stop_cannot_be_short_range_disguised_as_pending(self):
        symbol='XAUUSDm';cache=self.e.planner.caches[symbol];q=self.g.quote(symbol)
        h1=cache.frames['H1'];m1=cache.frames['M1'];side=1
        level=q.bid-h1.atr*.55
        setup=Setup('SWING:REGRESSION:XAU:H1:TIGHT',side,'PENDING','LIMIT',level,
                    level-h1.atr*.35,level+h1.atr*1.5,m1.atr,99,self.g.clock(),
                    'PENDIENTE FINAL OPT · H1 swing HTF; confluencias HTF 4; target swing H1; niveles nacen de estructura',
                    'H1',h1.atr)
        plans=self.e.planner.proposed_pending_plans(symbol,[setup],q,all_candidates=True)
        self.assertFalse(any(p.key==setup.key for p in plans))
        audit=next(x for x in self.e.planner.pending_candidate_audit[symbol] if x['key']==setup.key)
        self.assertIn(audit['reject_code'],{'stop_noise_floor','structural_stop_too_tight','stop_structure_floor'})

    def test_budget_never_moves_entry_toward_stop_to_force_a_trade(self):
        symbol='XAUUSDm';cache=self.e.planner.caches[symbol];q=self.g.quote(symbol)
        h1=cache.frames['H1'];m1=cache.frames['M1'];side=1
        level=q.bid-h1.atr*.70
        setup=Setup('SWING:REGRESSION:XAU:H1:OVERBUDGET',side,'PENDING','LIMIT',level,
                    level-h1.atr*.95,level+h1.atr*2.5,m1.atr,99,self.g.clock(),
                    'PENDIENTE FINAL OPT · H1 order block HTF no mitigado; confluencias HTF 5; target swing H1; niveles nacen de estructura',
                    'H1',h1.atr)
        original=level+q.spread
        self.e.planner.proposed_pending_plans(symbol,[setup],q,all_candidates=True)
        audit=next(x for x in self.e.planner.pending_candidate_audit[symbol] if x['key']==setup.key)
        self.assertAlmostEqual(audit['entry'],original,places=6)
        self.assertFalse(audit.get('budget_fit',False))

    def test_two_independent_external_sources_against_side_reduce_quality(self):
        p=self.plan();symbol=p.symbol
        self.e.planner.research_context={}
        local=self.e.planner.fuse_pending_context(symbol,[p])[0]
        self.e.planner.research_context={
            'updated':datetime.now(timezone.utc).isoformat(),
            'fusion':{symbol:{
                'bias':-.45,'confidence':.55,
                'components':[
                    {'name':'coinglass','bias':-.8,'weight':.32},
                    {'name':'technical:web','bias':-.6,'weight':.24},
                    {'name':'youtube','bias':.1,'weight':.08},
                ],
                'label':'dos fuentes independientes contradicen BUY'
            }}
        }
        opposed=self.e.planner.fuse_pending_context(symbol,[p])[0]
        self.assertLess(opposed.quality_score,local.quality_score)

    def test_duplicate_news_do_not_count_as_independent_opposition(self):
        p=self.plan();symbol=p.symbol
        fresh=datetime.now(timezone.utc).isoformat()
        def evaluate(components):
            self.e.planner.research_context={'updated':fresh,'fusion':{symbol:{
                'bias':0.0,'confidence':.55,'components':components,'label':'noticias duplicadas'}}}
            return self.e.planner.fuse_pending_context(symbol,[p])[0]
        single=evaluate([{'name':'global_news:agency','bias':-.8,'weight':.35}])
        duplicate=evaluate([{'name':'global_news:agency','bias':-.8,'weight':.35},
                            {'name':'search:reprint','bias':-.8,'weight':.25}])
        self.assertAlmostEqual(duplicate.quality_score,single.quality_score,places=5)

    def test_default_portfolio_is_one_best_pending_per_direction(self):
        self.assertTrue(self.cfg['pending']['one_order_per_direction'])
        self.assertEqual(self.cfg['pending']['max_same_side_orders'],1)
        self.assertEqual(self.cfg['pending']['max_own_map_orders'],2)
        self.assertTrue(self.cfg['execution']['pending_budget_fit_entry'])
        self.assertTrue(self.cfg['execution']['always_keep_pending_map'])


if __name__=='__main__':
    unittest.main()
