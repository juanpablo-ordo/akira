"""Lifecycle replay of the user's observed quotes; not a profitability backtest."""
import json
from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import patch

from engine import Engine
from tests.fixtures import PendingCase


class RecordedPendingContinuity(PendingCase,unittest.TestCase):
    def setUp(self):
        super().setUp();self.engine=Engine(self.g,self.cfg,self.g.log);self.addCleanup(self.engine.close)
        self.engine.warmup()
        self.plan=replace(self.plan(side=-1,kind='STOP'),key='RECORDED:SELL:STOP:H1:1',
            entry=83004.86,sl=83171.32,tp=82737.78,atr=166.46,horizon_atr=166.46,
            bar_time=int(self.clock())-7200,signal_timeframe='H1')
        self.order=self.api.add_pending(self.plan)
        self.g.journal.data['orders'][str(self.order.ticket)]={'plan':self.plan.to_dict(),'created':self.clock()-7200}

    def test_recorded_quotes_keep_one_ticket_across_candidate_key_and_small_zone_changes(self):
        fixture=json.loads((Path(__file__).parent/'data/recorded_pending_churn.json').read_text(encoding='utf-8'))
        initial=self.clock()
        # This replay isolates replacement continuity. Full structural
        # invalidation is tested separately; historical closed bars were not
        # supplied with this tick interval and are never fabricated here.
        with patch.object(self.engine,'invalidate_reason',return_value=None):
            for index,(second,bid,ask) in enumerate(fixture['quotes']):
                self.clock.now=initial+second
                tick=self.api.ticks['BTCUSDm'];tick.bid=bid;tick.ask=ask;tick.time=self.clock();tick.time_msc=int(self.clock()*1000)
                candidate=replace(self.plan,key='NEW_KEY_'+str(index),entry=(83004.86,82989.,82988.7)[index%3])
                self.engine.lifecycle_action('BTCUSDm',[candidate],self.g.quote('BTCUSDm'))
        self.assertGreater(len(fixture['quotes']),100)
        self.assertFalse(self.api.sent)
        self.assertEqual([o.ticket for o in self.api.orders],[self.order.ticket])

    def test_learned_filter_alone_cannot_cancel_but_structural_invalidation_keeps_precedence(self):
        self.engine.planner.pending_adaptation_rejections={'BTCUSDm':[self.plan]}
        q=self.g.quote('BTCUSDm')
        with patch.object(self.engine,'invalidate_reason',return_value=None):
            self.engine.lifecycle_action('BTCUSDm',[],q)
        self.assertEqual(self.engine.lifecycle[str(self.order.ticket)]['state'],'VALID')
        self.assertFalse(self.api.sent)
        with patch.object(self.engine,'invalidate_reason',return_value='Invalidación estructural confirmada'),patch.object(self.engine,'confirm',return_value=True),patch.object(self.g,'cancel',return_value=True) as cancel:
            self.engine.lifecycle_action('BTCUSDm',[],q)
        cancel.assert_called_once()


if __name__=='__main__':unittest.main()
