import unittest
from dataclasses import replace
from datetime import datetime,timezone
from types import SimpleNamespace
from unittest.mock import patch
from execution import OWN_PENDING,PENDING,REMOVE,SLTP
from engine import Engine
from strategy import build_setups
from tests.fixtures import PendingCase

class EngineTests(PendingCase,unittest.TestCase):
    # Execution tests are supplied by the separate class, not repeated here.
    def setUp(self):
        super().setUp();self.e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(self.e.close)
    def fresh(self):
        self.clock.advance(1)
        for s in self.cfg['symbols']:self.api.set_quote(s,self.api.ticks[s].bid,fill=False)
    def test_startup_analyses_both_symbols_and_places_valid_pendings(self):
        view=self.e.step();self.assertEqual({r['symbol'] for r in self.api.sent},{'BTCUSDm','XAUUSDm'})
        self.assertTrue(all(r['action']==PENDING for r in self.api.sent))
        for s in self.cfg['symbols']:self.assertGreater(len(view['candidates'][s]),0)
        for s,evidence in view['analysis'].items():
            self.assertEqual(evidence['first_request_cycle'],1)
            self.assertEqual(evidence['timeframes'],['M1','M5','M15','M30','H1','H4','D1'])
            self.assertEqual(evidence['context_sources'],[])

    def test_unavailable_external_sources_do_not_block_first_valid_cycle(self):
        snapshots=[]
        self.e.context=SimpleNamespace(read=lambda:{'fusion':{},'sources':{'youtube':{'inflight':True,'fresh':False}}},submit=snapshots.append)
        view=self.e.step()
        self.assertEqual(len(self.api.sent),4);self.assertEqual(len(snapshots),2)
        for s in self.cfg['symbols']:
            self.assertIn('H1',snapshots[0]['symbols'][s]['frames'])
            self.assertEqual(view['analysis'][s]['context_sources'],[])

    def test_available_ia_and_news_change_ranking_without_changing_levels(self):
        self.e.warmup();p=self.plan();self.e.planner.research_context={}
        local=self.e.planner.fuse_pending_context(p.symbol,[p])[0]
        self.e.planner.research_context={'updated':datetime.now(timezone.utc).isoformat(),
            'fusion':{p.symbol:{'bias':1,'confidence':.6,'components':[
                {'name':'local_ai','weight':.35},{'name':'news','weight':.2}],
                'label':'IA local y noticias vigentes'}}}
        context=self.e.planner.fuse_pending_context(p.symbol,[p])[0]
        self.assertGreater(context.quality_score,local.quality_score)
        self.assertEqual((context.entry,context.sl,context.tp),(p.entry,p.sl,p.tp))
        self.assertEqual(self.e.analysis_evidence(p.symbol)['context_sources'],['local_ai','news'])

    def test_mt5_permission_block_is_visible_instead_of_an_empty_map(self):
        self.api.terminal.trade_allowed=False
        view=self.e.step();self.assertFalse(self.api.sent)
        for s in self.cfg['symbols']:
            self.assertIn('Trading algorítmico',view['status'][s]['detail'])

    def test_observe_mode_does_not_claim_it_sent_a_pending(self):
        self.cfg['mode']='observe'
        view=self.e.step();self.assertFalse(self.api.sent)
        for s in self.cfg['symbols']:
            self.assertEqual(view['status'][s]['state'],'OBSERVAR')
            self.assertIsNone(view['analysis'][s]['first_request_cycle'])
    def test_repeated_cycles_never_create_market_entries(self):
        for _ in range(15):self.e.step();self.fresh()
        self.assertTrue(self.api.sent);self.assertTrue(all(r['action'] in (PENDING,REMOVE,7,SLTP) for r in self.api.sent))
        for s in self.cfg['symbols']:self.assertLessEqual(sum(o.symbol==s for o in self.api.orders),6)
    def test_setups_are_pending_only(self):
        self.e.warmup()
        for s,c in self.e.planner.caches.items():
            setups,_=build_setups(c.frames,self.cfg['strategy'])
            self.assertTrue(setups);self.assertEqual({p.lane for p in setups},{'PENDING'});self.assertTrue(all(p.kind in ('LIMIT','STOP') for p in setups))
    def test_no_order_when_structural_evidence_is_missing(self):
        self.e.warmup();self.e.initialized=True
        for c in self.e.planner.caches.values():c.frames.pop('H1');c.due['H1']=self.clock()+1000
        self.e.step();self.assertFalse(self.api.sent)
    def test_no_external_confidence_can_rescue_invalid_geometry(self):
        p=self.plan();setup=self.e.planner.caches['BTCUSDm'];self.e.warmup()
        self.e.planner.research_context={'fusion':{'BTCUSDm':{'bias':1,'confidence':1,'pending_key':p.key}}}
        self.assert_blocked(replace(p,sl=p.entry+1))
    def test_paused_engine_does_not_mutate(self):
        self.e.paused=True;self.e.step();self.assertFalse(self.api.sent)
    def test_invalidated_pending_requires_multiple_fresh_quotes(self):
        p=self.plan();o=self.api.add_pending(p);self.g.journal.data['orders'][str(o.ticket)]={'plan':p.to_dict(),'created':self.clock()}
        self.e.warmup();self.api.set_quote(p.symbol,p.sl-2,fill=False);q=self.g.quote(p.symbol)
        for _ in range(5):self.e.lifecycle_action(p.symbol,[],q);self.clock.advance(1)
        self.assertFalse(self.api.sent)
        for _ in range(3):self.api.set_quote(p.symbol,p.sl-2,fill=False);self.e.lifecycle_action(p.symbol,[],self.g.quote(p.symbol));self.clock.advance(1)
        self.assertEqual(self.api.sent[-1]['action'],REMOVE)
    def test_transient_missing_map_does_not_delete_order(self):
        p=self.plan();o=self.api.add_pending(p);self.g.journal.data['orders'][str(o.ticket)]={'plan':p.to_dict()}
        self.e.warmup()
        for _ in range(5):self.e.lifecycle_action(p.symbol,[],self.g.quote(p.symbol));self.fresh()
        self.assertFalse(self.api.sent);self.assertIn(o,self.api.orders)
    def test_unchanged_pending_is_not_edited_every_second(self):
        p=self.plan();o=self.api.add_pending(p);self.g.journal.data['orders'][str(o.ticket)]={'plan':p.to_dict()};self.e.warmup()
        for _ in range(8):self.e.lifecycle_action(p.symbol,[p],self.g.quote(p.symbol));self.fresh()
        self.assertFalse(self.api.sent)
    def test_better_confirmed_pending_is_modified_without_recreation(self):
        p=self.plan();o=self.api.add_pending(p);self.g.journal.data['orders'][str(o.ticket)]={'plan':p.to_dict()};self.e.warmup()
        new=replace(p,entry=p.entry-8,sl=p.sl-8,tp=p.tp-8,score=98,quality_score=98,activation_score=90)
        self.clock.advance(6)
        for _ in range(4):
            self.api.set_quote(p.symbol,self.api.ticks[p.symbol].bid,fill=False);self.e.lifecycle_action(p.symbol,[new],self.g.quote(p.symbol));self.clock.advance(1)
            if self.api.sent:break
        self.assertEqual(self.api.sent[-1]['action'],7);self.assertEqual(len(self.api.orders),1)
    def test_pending_fills_are_not_closed_for_cents(self):
        p=self.api.add_position('XAUUSDm',entry=2500,sl=2499,tp=2503,magic=OWN_PENDING)
        self.g.journal.data['positions'][str(p.ticket)]={'entry':2500,'initial_sl':2499,'time':self.clock()-80,'plan':{'sl':2499,'tp':2503}}
        self.e.warmup();self.api.set_quote('XAUUSDm',2500.08,fill=False);self.e.positions.step(self.g.snapshot())
        self.assertFalse(self.api.sent)
    def test_gain_can_tighten_stop_without_closing_position(self):
        p=self.api.add_position('XAUUSDm',entry=2500,sl=2499,tp=2504,magic=OWN_PENDING)
        self.g.journal.data['positions'][str(p.ticket)]={'entry':2500,'initial_sl':2499,'time':self.clock()-80,'plan':{'sl':2499,'tp':2504}}
        self.e.warmup();self.api.set_quote('XAUUSDm',2501.4,fill=False);self.e.positions.step(self.g.snapshot())
        self.assertEqual(self.api.sent[-1]['action'],SLTP);self.assertEqual(len(self.api.positions),1);self.assertEqual(p.tp,2504)
    def test_poor_model_output_is_not_a_probability_of_tp(self):
        from providers import model_component
        report={'model_output':.99,'test_accuracy':.6,'baseline':.6,'advantage':0,'usable_signal':False}
        self.assertIsNone(model_component(report,'M5'))
