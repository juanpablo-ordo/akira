import unittest
from datetime import datetime,timezone
from types import SimpleNamespace as NS
from unittest.mock import patch
from market_state import MarketStateResolver,MarketDataFreshnessValidator,CandleGapRecovery
from settings import DEFAULT,load_config
from tests.fixtures import PendingCase
from tests.fake_mt5 import FakeMT5
from engine import Engine

def utc(text):return datetime.fromisoformat(text.replace('Z','+00:00')).timestamp()

class MarketFacts(unittest.TestCase):
    def setUp(self):
        self.cfg=load_config(DEFAULT);self.now=utc('2026-10-29T22:35:00Z')
        self.terminal=NS(connected=True,trade_allowed=True,tradeapi_disabled=False)
        self.account=NS(trade_allowed=True,trade_expert=True)
        self.info=NS(trade_mode=4)
        self.tick=NS(time=self.now,time_msc=self.now*1000,bid=4000,ask=4000.2)
    def resolve(self,**extra):
        return MarketStateResolver.resolve('XAUUSDm',self.now,self.cfg,self.terminal,self.account,self.info,self.tick,**extra)
    def test_open_quote_and_permissions_are_separate_from_analysis(self):
        r=self.resolve();self.assertEqual(r['session'],'OPEN');self.assertEqual(r['quote']['state'],'FRESH')
        self.assertFalse(r['execution_confirmed'])
    def test_old_tick_does_not_assert_market_closed_when_schedule_is_open(self):
        self.tick.time_msc=(self.now-60)*1000
        r=self.resolve();self.assertEqual(r['quote']['state'],'STALE');self.assertEqual(r['session'],'UNKNOWN')
    def test_broker_rejection_is_real_closure_even_with_ticks(self):
        r=self.resolve(rejection={'code':10018,'at':self.now-1})
        self.assertEqual(r['session'],'CLOSED')
    def test_close_only_and_disabled_are_distinct(self):
        for mode,state in [(0,'DISABLED'),(3,'CLOSE_ONLY')]:
            with self.subTest(mode=mode):self.info.trade_mode=mode;self.assertEqual(self.resolve()['session'],state)
    def test_terminal_outage_is_not_a_claim_about_market_hours(self):
        self.terminal.connected=False;r=self.resolve();self.assertEqual(r['session'],'UNKNOWN');self.assertEqual(r['execution'],'BROKER_UNAVAILABLE')
    def test_no_missing_gold_h1_is_invented_during_rollover(self):
        f=NS(bars=[NS(time=utc('2026-10-29T20:00:00Z'))])
        r=MarketDataFreshnessValidator.inspect('XAUUSDm','H1',f,self.now,self.cfg)
        self.assertTrue(r['ready']);self.assertEqual(r['expected_open_utc'],f.bars[-1].time)
    def test_same_h1_is_missing_for_bitcoin_without_that_session_gap(self):
        f=NS(bars=[NS(time=utc('2026-10-29T20:00:00Z'))])
        self.assertFalse(MarketDataFreshnessValidator.inspect('BTCUSDm','H1',f,self.now,self.cfg)['ready'])
    def test_gold_really_missing_h1_after_next_close_is_stale(self):
        f=NS(bars=[NS(time=utc('2026-10-29T20:00:00Z'))])
        r=MarketDataFreshnessValidator.inspect('XAUUSDm','H1',f,utc('2026-10-29T23:10:00Z'),self.cfg)
        self.assertEqual(r['state'],'STALE');self.assertIn('DESACTUALIZADOS',r['reason'])
    def test_future_or_live_bar_is_never_accepted(self):
        f=NS(bars=[NS(time=utc('2026-10-29T22:00:00Z'))])
        self.assertEqual(MarketDataFreshnessValidator.inspect('XAUUSDm','H1',f,self.now,self.cfg)['state'],'INVALID')
    def test_recovery_uses_utc_range_discards_live_bar_and_backs_off(self):
        calls=[]
        def get(symbol,tf,start,end):
            calls.append((start,end));return [{'time':self.now-7200},{'time':self.now-3600},{'time':self.now}]
        api=NS(copy_rates_range=get);r=CandleGapRecovery()
        rows=r.recover(api,'XAUUSDm',16385,'H1',self.now,self.cfg)
        self.assertEqual(len(rows),2);self.assertEqual(calls[0][0].tzinfo,timezone.utc)
        self.assertIsNone(r.recover(api,'XAUUSDm',16385,'H1',self.now+1,self.cfg));self.assertEqual(len(calls),1)

class EngineMarketRecovery(PendingCase,unittest.TestCase):
    def setUp(self):
        super().setUp();self.cfg['mode']='observe';self.clock.now=utc('2026-10-29T22:35:00Z')
        self.api=FakeMT5(self.clock);self.g.api=self.api
        self.e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(self.e.close)
    def test_old_runner_closed_state_is_cleared_even_when_h1_is_missing(self):
        self.api.rates['XAUUSDm',16385]=[r for r in self.api.rates['XAUUSDm',16385] if r['time']<=utc('2026-10-29T19:00:00Z')]
        self.e.runner_views['XAUUSDm']={'state':'MERCADO CERRADO'}
        v=self.e.step()
        self.assertEqual(v['markets']['XAUUSDm']['session'],'OPEN')
        self.assertEqual(v['symbols']['XAUUSDm']['runner']['state'],'DATOS PENDIENTES')
        self.assertEqual(v['status']['BTCUSDm']['state'],'OBSERVAR')
    def test_rollover_h1_no_longer_leaves_gold_stuck(self):
        self.api.rates['XAUUSDm',16385]=[r for r in self.api.rates['XAUUSDm',16385] if r['time']!=utc('2026-10-29T21:00:00Z')]
        v=self.e.step();self.assertEqual(v['status']['XAUUSDm']['state'],'OBSERVAR');self.assertFalse(self.api.sent)

if __name__=='__main__':unittest.main()
