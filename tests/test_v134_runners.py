"""Comportamiento y riesgo de runners; no prueba ni promesa de rentabilidad."""
import copy
import json
import unittest
from dataclasses import replace
from types import SimpleNamespace as NS
from unittest.mock import patch

from assistant_akira import AkiraAssistant
from engine import Engine
from execution import Blocked, DEAL, OWN_RUNNER, PENDING, REMOVE
from runner import runner_plan, runner_exit
from settings import load_config
from strategy import Bar
from tests.fixtures import PendingCase


class RunnerV134Tests(PendingCase, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.cfg['execution']['pending_only']=False
        self.e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(self.e.close)

    def runner(self,symbol='BTCUSDm',side=1,score=92):
        p=self.plan(symbol,side)
        q=self.g.quote(symbol);entry=q.ask if side==1 else q.bid
        distance=50 if symbol.startswith('BTC') else 1
        stamp=int(self.clock()//900)*900-900
        return replace(p,key=f'RUN:{symbol}:{side}:{stamp}',lane='RUNNER',kind='MARKET',
                       entry=entry,sl=entry-side*distance,tp=entry+side*distance*2.4,
                       atr=distance,bar_time=stamp,score=score,quality_score=score,
                       trigger=entry)

    def signal_frames(self,side=1):
        self.e.warmup()
        f=self.e.planner.caches['BTCUSDm'].frames['M15']
        end=int(self.clock()//900)*900-900
        bars=[Bar(end-(13-i)*900,100,102,98,101,100) for i in range(14)]
        bars[-1]=Bar(end,100.5,104,100,103.5,160)
        if side==-1:
            bars=[Bar(b.time,200-b.open,200-b.low,200-b.high,200-b.close,b.volume) for b in bars]
        m=replace(f,bars=tuple(bars),atr=5,trend=.8*side,rsi=60 if side==1 else 40,
                  volume_ratio=1.6,highs=(),lows=())
        h=replace(m,name='H1')
        return {'M15':m,'H1':h}

    def test_confirmed_long_and_short_use_m15_structure(self):
        for side,bid in ((1,103.5),(-1,96.5)):
            self.api.set_quote('BTCUSDm',bid,spread=.1,fill=False)
            p,detail=runner_plan('BTCUSDm',self.signal_frames(side),self.g.quote('BTCUSDm'),self.cfg)
            self.assertIsNotNone(p,detail);self.assertEqual((p.lane,p.side),('RUNNER',side))
            self.assertGreaterEqual(abs(p.entry-p.sl),p.atr*self.cfg['runner']['min_stop_atr'])

    def test_extended_candle_is_not_chased(self):
        frames=self.signal_frames();m=frames['M15'];last=m.bars[-1]
        frames['M15']=replace(m,bars=m.bars[:-1]+(replace(last,high=125,close=120),))
        p,detail=runner_plan('BTCUSDm',frames,self.g.quote('BTCUSDm'),self.cfg)
        self.assertIsNone(p);self.assertIn('extendida',detail)

    def test_misaligned_h1_prevents_runner(self):
        frames=self.signal_frames();frames['H1']=replace(frames['H1'],trend=-.8)
        self.assertIsNone(runner_plan('BTCUSDm',frames,self.g.quote('BTCUSDm'),self.cfg)[0])

    def test_runner_uses_market_filling_and_broker_sl_tp_from_open(self):
        p=self.runner();self.assertTrue(self.g.send_runner(p))
        r=self.api.sent[-1]
        self.assertEqual((r['action'],r['magic']),(DEAL,OWN_RUNNER));self.assertNotIn('price',r)
        self.assertIn(r['type_filling'],(0,1));self.assertLessEqual(abs(r['sl']-p.sl),.01);self.assertLessEqual(abs(r['tp']-p.tp),.01)
        self.g.reconcile(self.g.snapshot())
        meta=self.g.journal.data['positions'][str(self.api.positions[0].ticket)]
        self.assertEqual(meta['plan']['lane'],'RUNNER');self.assertGreater(meta['initial_sl'],0)

    def test_strong_signal_increases_lot_within_unchanged_risk_cap(self):
        self.cfg['runner']['allow_size_boost']=True  # explicit opt-in for this sizing contract
        before=copy.deepcopy(self.cfg['risk']);p=self.runner();self.g.send_runner(p)
        request=self.api.sent[-1]
        self.assertGreater(request['volume'],.01)
        self.assertLessEqual(self.g.plan_money(p,request['volume'])[0],self.g.trade_cap(self.g.snapshot()))
        self.assertEqual(before,self.cfg['risk'])

    def test_ordinary_signal_keeps_base_lot(self):
        self.g.send_runner(self.runner(score=86))
        self.assertEqual(self.api.sent[-1]['volume'],.01)

    def test_minimum_lot_cannot_be_raised_when_already_over_budget(self):
        p=self.runner('XAUUSDm');p=replace(p,sl=p.entry-7.44,tp=p.entry+18)
        self.cfg['risk']['max_trade_money']=2.17
        with self.assertRaisesRegex(Blocked,'Lote mínimo'):self.g.send_runner(p)
        self.assertFalse(self.api.sent)

    def test_smaller_broker_lot_can_fit_without_moving_sl(self):
        self.api.infos['XAUUSDm'].volume_min=.001;self.api.infos['XAUUSDm'].volume_step=.001
        p=self.runner('XAUUSDm',score=86);p=replace(p,sl=p.entry-7.44,tp=p.entry+18)
        self.cfg['risk']['max_trade_money']=2.17
        self.g.send_runner(p);r=self.api.sent[-1]
        self.assertLess(r['volume'],.01);self.assertLessEqual(abs(r['sl']-p.sl),.01)
        self.assertLessEqual(self.g.plan_money(p,r['volume'])[0],2.17)

    def test_pending_sizing_also_uses_smaller_broker_minimum(self):
        self.api.infos['XAUUSDm'].volume_min=.001;self.api.infos['XAUUSDm'].volume_step=.001
        p=self.plan('XAUUSDm');p=replace(p,sl=p.entry-7.44,tp=p.entry+18)
        self.cfg['risk']['max_trade_money']=2.17
        self.g.send_immediate_plan(p);r=self.api.sent[-1]
        self.assertEqual(r['action'],PENDING);self.assertLess(r['volume'],.01)
        self.assertLessEqual(abs(r['sl']-p.sl),.01)

    def test_portfolio_budget_limits_boost(self):
        self.cfg['risk']['portfolio_money_cap']=.8;p=self.runner();self.g.send_runner(p)
        self.assertLessEqual(self.g.plan_money(p,self.api.sent[-1]['volume'])[0],.8)

    def test_existing_manual_position_blocks_runner_without_modification(self):
        self.api.add_position(magic=0)
        with self.assertRaises(Blocked):self.g.send_runner(self.runner())
        self.assertFalse(self.api.sent)

    def test_existing_runner_blocks_second_market_entry(self):
        p=self.runner();self.g.send_runner(p);self.g.reconcile(self.g.snapshot())
        with self.assertRaises(Blocked):self.g.send_runner(replace(p,key=p.key+'next'))
        self.assertEqual(len(self.api.positions),1)

    def test_unknown_send_is_not_repeated(self):
        self.api.no_effect=True;p=self.runner();self.g.send_runner(p)
        with self.assertRaises(Blocked):self.g.send_runner(p)
        self.assertEqual(len(self.api.sent),1);self.assertIn(p.symbol,self.g.journal.data['intents'])

    def test_definitive_rejection_allows_safe_retry_after_cooldown(self):
        p=self.runner();self.api.send_retcode=10006
        self.assertFalse(self.g.send_runner(p))
        self.assertNotIn(p.key,self.g.journal.data.get('runner_entries',{}))
        self.clock.advance(3);self.api.set_quote(p.symbol,self.api.ticks[p.symbol].bid,fill=False)
        self.api.send_retcode=None
        self.assertTrue(self.g.send_runner(p));self.assertEqual(len(self.api.positions),1)

    def test_runner_is_not_reopened_on_the_same_closed_signal_after_exit(self):
        p=self.runner();self.g.send_runner(p);self.g.reconcile(self.g.snapshot())
        self.g.close_runner(self.api.positions[0],'test reversal');self.g.reconcile(self.g.snapshot())
        with self.assertRaises(Blocked):self.g.send_runner(p)
        self.assertFalse(self.api.positions)

    def test_stale_runner_signal_never_sends(self):
        p=replace(self.runner(),bar_time=int(self.clock())-2000)
        with self.assertRaisesRegex(Blocked,'caducada'):self.g.send_runner(p)
        self.assertFalse(self.api.sent)

    def test_price_drift_between_signal_and_send_is_rejected(self):
        p=self.runner();self.api.set_quote(p.symbol,p.entry+p.atr,fill=False)
        with self.assertRaisesRegex(Blocked,'ventana'):self.g.send_runner(p)
        self.assertFalse(self.api.sent)

    def test_malformed_market_lane_cannot_bypass_pending_channel(self):
        with self.assertRaises(Blocked):self.g.send_immediate_plan(self.runner())
        with self.assertRaises(Blocked):self.g.send_runner(replace(self.runner(),key='CHAT:unknown'))
        self.assertFalse(self.api.sent)

    def test_cancel_confirmation_precedes_market_entry(self):
        self.cfg['runner']['preserve_pending_orders']=False  # explicit legacy replacement policy
        self.e.warmup();p=self.runner();self.api.add_pending(self.plan(side=-1))
        with patch('engine.runner_plan',return_value=(p,'confirmed')):
            self.assertTrue(self.e.try_runner(p.symbol,self.g.quote(p.symbol)))
        self.assertEqual([r['action'] for r in self.api.sent],[REMOVE,DEAL]);self.assertFalse(self.api.orders)

    def test_fill_during_cancel_prevents_extra_runner(self):
        self.cfg['runner']['preserve_pending_orders']=False  # explicit legacy replacement policy
        self.e.warmup();p=self.runner();self.api.add_pending(self.plan(side=-1));self.api.fill_on_cancel=True
        with patch('engine.runner_plan',return_value=(p,'confirmed')):self.e.try_runner(p.symbol,self.g.quote(p.symbol))
        self.assertFalse(any(r['action']==DEAL for r in self.api.sent));self.assertEqual(len(self.api.positions),1)

    def test_rejected_cancel_prevents_market_entry(self):
        self.cfg['runner']['preserve_pending_orders']=False  # explicit legacy replacement policy
        self.e.warmup();p=self.runner();self.api.add_pending(self.plan(side=-1));self.api.send_retcode=10006
        with patch('engine.runner_plan',return_value=(p,'confirmed')):self.e.try_runner(p.symbol,self.g.quote(p.symbol))
        self.assertFalse(any(r['action']==DEAL for r in self.api.sent))

    def test_close_runner_never_touches_manual_or_pending_filled_position(self):
        for magic in (0,170002):
            p=self.api.add_position(magic=magic)
            with self.assertRaises(Blocked):self.g.close_runner(p,'reverse')
        self.assertFalse(self.api.sent)

    def test_no_cents_or_tick_reversal_closes_a_runner(self):
        frames=self.signal_frames();plan=self.runner().to_dict();plan['bar_time']=frames['M15'].bars[-1].time
        self.assertEqual(runner_exit(plan,frames,1,.02,self.cfg),'')

    def test_closed_structure_break_can_exit_runner(self):
        frames=self.signal_frames();m=frames['M15'];last=m.bars[-1]
        frames['M15']=replace(m,bars=m.bars[:-1]+(replace(last,close=90,low=89),))
        plan={'bar_time':last.time-900}
        self.assertIn('estructura',runner_exit(plan,frames,1,.5,self.cfg))

    def test_button_returns_parameters_even_when_risk_blocks_both_symbols(self):
        self.cfg['risk']['max_trade_money']=.01
        result=self.e.handle_command({'action':'assistant_best_pending','symbol':'ALL'})
        self.assertEqual({r['symbol'] for r in result['results']},{'BTCUSDm','XAUUSDm'})
        self.assertTrue(all(r['scenarios'] for r in result['results']))
        text=AkiraAssistant._trade_result_text(result)
        self.assertIn('Entry=',text);self.assertIn('SL=',text);self.assertIn('TP=',text)
        self.assertFalse(self.api.sent)

    def test_fast_attempts_precede_deep_history_loading_for_both_symbols(self):
        observed=[]
        def deep():
            observed.extend(r['symbol'] for r in self.api.sent)
        with patch.object(self.e,'complete_warmup',side_effect=deep):self.e.step()
        self.assertEqual(set(observed),{'BTCUSDm','XAUUSDm'})

    def test_migration_preserves_risk_and_explicit_observation_mode(self):
        old=copy.deepcopy(self.cfg);old['schema_version']=1300;old['mode']='observe'
        old.pop('runner');old.pop('sizing');old['risk']['max_trade_money']=2.17
        cfg=load_config(old)
        self.assertTrue(cfg['runner']['enabled']);self.assertTrue(cfg['sizing']['enabled'])
        self.assertEqual(cfg['mode'],'observe');self.assertEqual(cfg['risk']['max_trade_money'],2.17)

    def test_real_runner_selector_runs_inside_auto_cycle_for_both_symbols(self):
        frames=self.signal_frames()
        for symbol,scale,base,spread in (('BTCUSDm',10,60000,1),('XAUUSDm',.2,2500,.04)):
            def price(v):return base+(v-100)*scale
            cache=self.e.planner.caches[symbol]
            for tf in ('M15','H1'):
                f=frames[tf]
                bars=tuple(Bar(b.time,price(b.open),price(b.high),price(b.low),price(b.close),b.volume) for b in f.bars)
                cache.frames[tf]=replace(f,bars=bars,atr=f.atr*scale,name=tf,highs=(),lows=())
            for tf in cache.PERIODS:cache.due[tf]=self.clock()+60
            self.api.set_quote(symbol,price(103.5),spread=spread,fill=False)
        # Exercise a real runner when there is no qualifying pending map.
        with patch.object(self.e,'scan_plans',return_value=[]):view=self.e.step()
        self.assertEqual({r['symbol'] for r in self.api.sent if r['action']==DEAL},{'BTCUSDm','XAUUSDm'})
        self.assertEqual(len(self.api.positions),2)
        self.assertTrue(all(r['runner']['state']=='RUNNER CONFIRMADO' for r in view['symbols'].values()))

    def test_external_context_changes_score_only_after_technical_confirmation(self):
        self.api.set_quote('BTCUSDm',103.5,spread=.1,fill=False);frames=self.signal_frames();q=self.g.quote('BTCUSDm')
        context={'sources':{'coinglass':{'fresh':True,'updated':q.time}},'fusion':{'BTCUSDm':{'bias':1,'confidence':1}}}
        base=runner_plan('BTCUSDm',frames,q,self.cfg)[0]
        fresh=runner_plan('BTCUSDm',frames,q,self.cfg,context)[0]
        self.assertGreater(fresh.score,base.score)
        context['sources']['coinglass']['updated']=q.time-1000
        self.assertEqual(runner_plan('BTCUSDm',frames,q,self.cfg,context)[0].score,base.score)
        frames['H1']=replace(frames['H1'],trend=-.8)
        self.assertIsNone(runner_plan('BTCUSDm',frames,q,self.cfg,context)[0])

    def test_position_manager_closes_runner_on_confirmed_structure_break(self):
        p=self.runner();self.g.send_runner(p);self.g.reconcile(self.g.snapshot())
        self.clock.advance(900)
        for symbol in self.cfg['symbols']:self.api.set_quote(symbol,self.api.ticks[symbol].bid,fill=False)
        self.e.warmup();cache=self.e.planner.caches[p.symbol];f=cache.frames['M15']
        stamp=p.bar_time+900
        bars=tuple(Bar(stamp-(3-i)*900,p.entry+100,p.entry+150,p.entry+95,p.entry+120) for i in range(4))
        bars=bars[:-1]+(Bar(stamp,p.entry+120,p.entry+125,p.entry+78,p.entry+80),)
        cache.frames['M15']=replace(f,bars=bars,atr=50)
        self.api.set_quote(p.symbol,p.entry+80,fill=False)
        self.e.positions.step(self.g.snapshot())
        self.assertFalse(self.api.positions);self.assertEqual(self.api.sent[-1]['action'],DEAL)


