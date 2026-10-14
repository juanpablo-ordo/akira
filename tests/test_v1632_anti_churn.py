"""October 12/13 duplicate pending storm regression. No MT5 real account."""
import unittest
from dataclasses import replace
from engine import Engine
from tests.fixtures import PendingCase
from execution import REMOVE
from settings import load_config

class AntiChurnTests(PendingCase,unittest.TestCase):
    def setUp(self):
        super().setUp();self.e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(self.e.close)
    def test_replacement_off_by_default_in_existing_configuration(self):
        cfg=load_config({'pending':{'replace_confirm_seconds':.2,'sticky_min_seconds':.75}})
        self.assertFalse(cfg['pending']['auto_replace_valid_pending'])
        with self.assertRaises(ValueError):load_config({'pending':{'auto_replace_valid_pending':'yes'}})
    def test_identical_pending_survives_100_replacement_cycles(self):
        self.e.warmup();p=self.plan('XAUUSDm',key='LIVE');o=self.api.add_pending(p)
        self.g.journal.data['orders'][str(o.ticket)]={'plan':p.to_dict(),'created':self.clock()-800}
        newcomer=replace(self.plan('XAUUSDm',kind='STOP',key='NEW'),score=99,quality_score=99)
        for n in range(100):
            self.e.replace_for_better_portfolio(p.symbol,[newcomer],self.g.quote(p.symbol))
            self.clock.advance(.6);self.api.set_quote(p.symbol,self.api.ticks[p.symbol].bid,fill=False)
        self.assertEqual(len(self.api.orders),1)
        self.assertFalse(any(x.get('action')==REMOVE for x in self.api.sent))
    def test_orphan_not_canceled_for_missing_ranked_map(self):
        self.e.warmup();p=self.plan('BTCUSDm',key='OLD');o=self.api.add_pending(p)
        self.g.journal.data['orders'][str(o.ticket)]={'plan':p.to_dict(),'created':self.clock()-10}
        for _ in range(40):
            self.e.lifecycle_action(p.symbol,[],self.g.quote(p.symbol))
            self.clock.advance(1);self.api.set_quote(p.symbol,self.api.ticks[p.symbol].bid,fill=False)
        self.assertEqual(len(self.api.orders),1)
        self.assertFalse(any(x.get('action')==REMOVE for x in self.api.sent))
    def test_genuine_invalidation_remains_allowed(self):
        self.e.warmup();p=self.plan('BTCUSDm',key='INVALID');o=self.api.add_pending(p)
        self.g.journal.data['orders'][str(o.ticket)]={'plan':p.to_dict(),'created':self.clock()-100}
        for _ in range(10):
            self.api.set_quote(p.symbol,p.sl-3,fill=False)
            self.e.lifecycle_action(p.symbol,[],self.g.quote(p.symbol))
            self.clock.advance(1)
            if not self.api.orders:break
        self.assertFalse(self.api.orders)
        self.assertTrue(any(x.get('action')==REMOVE for x in self.api.sent))
