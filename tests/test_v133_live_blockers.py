"""Regression tests based on real terminal observations, not profit claims."""
import json
import unittest
from execution import Blocked,MarketPaused,PENDING
from engine import Engine
from tests.fixtures import PendingCase

class LiveBlockersV133(PendingCase,unittest.TestCase):
    def test_stale_gold_quote_is_a_market_pause_and_does_not_stop_btc(self):
        # Exness daily metal rollover may leave a valid but stale last tick.
        self.clock.advance(60)
        self.api.set_quote('BTCUSDm',self.api.ticks['BTCUSDm'].bid,fill=False)
        e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(e.close)
        view=e.step()
        self.assertEqual(view['status']['XAUUSDm']['state'],'SESIÓN POR COMPROBAR')
        self.assertIn('Cotización desactualizada',view['status']['XAUUSDm']['detail'])
        self.assertFalse(any(x['symbol']=='XAUUSDm' for x in self.api.sent))
        self.assertTrue(all(x['action']==PENDING for x in self.api.sent))
        self.assertTrue(any(x['symbol']=='BTCUSDm' for x in self.api.sent))

    def test_gold_resumes_only_after_a_fresh_tick(self):
        self.clock.advance(60)
        self.api.set_quote('BTCUSDm',self.api.ticks['BTCUSDm'].bid,fill=False)
        e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(e.close)
        self.assertEqual(e.step()['status']['XAUUSDm']['state'],'SESIÓN POR COMPROBAR')
        self.api.set_quote('XAUUSDm',self.api.ticks['XAUUSDm'].bid,fill=False)
        # Closed M1 candles may still be behind after reopening: no unsafe send.
        view=e.step()
        self.assertNotEqual(view['status']['XAUUSDm']['state'],'SESIÓN POR COMPROBAR')

    def test_heartbeat_writes_estado_json_with_real_symbol_states(self):
        e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(e.close)
        e.step()
        path=self.root/'logs'/'estado.json'
        self.assertTrue(path.exists())
        info=json.loads(path.read_text(encoding='utf-8'))
        self.assertIn('BTCUSDm',info)
        self.assertIn('XAUUSDm',info)
        self.assertIn('state',info['BTCUSDm']) if 'BTCUSDm' in info else None

    def test_risk_not_silently_widened_when_every_scenario_exceeds_cap(self):
        self.cfg['risk']['max_trade_money']=.01
        self.cfg['risk']['max_trade_pct']=.01
        e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(e.close)
        view=e.step()
        self.assertFalse(self.api.sent)
        self.assertEqual(len(view['symbols']['BTCUSDm']['scenario_book']),4)
        self.assertTrue(any('Riesgo' in v or 'límite' in v for v in
                            e.planner.pending_filter_reasons['BTCUSDm'].values()))

    def test_negative_quote_age_really_is_clock_skew(self):
        self.api.ticks['XAUUSDm'].time_msc=int((self.clock()+90)*1000)
        with self.assertRaises(Blocked) as ctx:self.g.quote('XAUUSDm')
        self.assertNotIsInstance(ctx.exception,MarketPaused)
        self.assertIn('desincronizado',str(ctx.exception))
