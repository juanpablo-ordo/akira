"""Análisis independiente del presupuesto y runners normales; sin MT5 real."""
import copy
import json
import queue
import sys
import threading
import unittest
from dataclasses import replace
from unittest.mock import patch

from akira_version import BUILD_ID
from engine import Engine
from execution import Blocked,PENDING
from runner import runner_plan
from runtime import run_session
from settings import DEFAULT,load_config
from strategy import Bar
from tests.fixtures import PendingCase


class TechnicalFunding136Tests(PendingCase,unittest.TestCase):
    def setUp(self):
        super().setUp()
        # Funding cases isolate admission from technical quality. The production
        # strict policy is exercised separately below and in Rev18 admission tests.
        self.cfg=load_config(DEFAULT);self.cfg['mode']='trade';self.g.cfg=self.cfg
        self.cfg['capital_protection']['strict_pending_quality']=False
        # La vía MARKET sigue disponible por configuración explícita; 16.2 usa pendientes por defecto.
        self.cfg['execution']['pending_only']=False
        self.e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(self.e.close)

    def signal(self,side=1,continuation=False):
        self.e.warmup();f=self.e.planner.caches['BTCUSDm'].frames['M15']
        stamp=int(self.clock()//900)*900-900
        bars=[Bar(stamp-(13-i)*900,100,102,98,101,100) for i in range(14)]
        bars[-1]=Bar(stamp,100.5,104,100,103.5,160)
        if continuation:
            bars[:9]=[replace(b,high=115,low=103,open=107,close=108) for b in bars[:9]]
            bars[-5]=replace(bars[-5],high=110,low=105,open=107,close=108)
            bars[-4]=replace(bars[-4],high=103,low=99.5,open=102,close=101)
            bars[-3]=replace(bars[-3],high=104,low=100,open=101,close=102)
            bars[-2]=replace(bars[-2],high=104,low=100.5,open=102,close=103)
            bars[-1]=Bar(stamp,100.5,106.5,100,106,160)
        if side==-1:bars=[Bar(b.time,200-b.open,200-b.low,200-b.high,200-b.close,b.volume) for b in bars]
        m=replace(f,bars=tuple(bars),atr=5,slow=100,trend=.8*side,
                  rsi=60 if side==1 else 40,volume_ratio=1.6,highs=(),lows=())
        frames={'M15':m,'H1':replace(m,name='H1')}
        self.api.set_quote('BTCUSDm',bars[-1].close,spread=.1,fill=False)
        return frames

    def test_technical_map_is_scored_when_minimum_lot_exceeds_budget(self):
        self.cfg['risk']['max_trade_money']=.01
        view=self.e.step()
        self.assertFalse(self.api.sent)
        for symbol in ('BTCUSDm','XAUUSDm'):
            self.assertTrue(self.e.candidates[symbol])
            self.assertEqual(view['status'][symbol]['state'],'BLOQUEO DE RIESGO')
            self.assertTrue(any(r.get('financially_blocked') and r.get('quality_score') is not None
                                for r in view['audit'][symbol]))
            self.assertIn('presupuesto disponible',view['status'][symbol]['detail'])

    def test_small_account_with_wide_gold_volatility_remains_blocked_with_real_reason(self):
        # Serie sintética de mayor rango; NO se presenta como replay del mercado.
        self.api.account.balance=30.47;self.api.revalue()
        base=self.api.ticks['XAUUSDm'].bid
        for (symbol,tf),bars in self.api.rates.items():
            if symbol=='XAUUSDm':
                for b in bars:
                    for key in ('open','high','low','close'):b[key]=4152+(b[key]-base)*20
        self.api.set_quote('XAUUSDm',4152,spread=.24,fill=False)
        view=self.e.step();gold=view['symbols']['XAUUSDm']
        self.assertFalse(any(r['symbol']=='XAUUSDm' for r in self.api.sent))
        self.assertTrue(gold['allocation_checks'])
        self.assertTrue(all(not r['funding']['minimum_fits'] for r in gold['allocation_checks']))
        self.assertEqual(view['status']['XAUUSDm']['state'],'BLOQUEO DE RIESGO')
        self.assertAlmostEqual(view['trade_risk_cap'],30.47*.02)

    def test_default_startup_rejects_weak_tactical_map_instead_of_forcing_two_orders(self):
        self.cfg['capital_protection']['strict_pending_quality']=True
        view=self.e.step()
        self.assertFalse(self.api.sent);self.assertFalse(self.api.orders)
        for symbol in ('BTCUSDm','XAUUSDm'):
            self.assertTrue(view['audit'][symbol])
            self.assertTrue(any(r.get('reject_code') in ('grade_below_required','strict_pending_admission') for r in view['audit'][symbol]))
            self.assertTrue(all(not r.get('sendable') for r in view['symbols'][symbol]['scenario_book']))

    def test_visible_winner_prefers_valid_alternative_to_unfunded_highest_score(self):
        self.e.warmup();good=self.plan('XAUUSDm',key='GOOD')
        bad=replace(good,key='EXPENSIVE',sl=good.entry-7.45,tp=good.entry+18,score=99,quality_score=99)
        self.cfg['risk']['max_trade_money']=2.17;self.e.candidates[good.symbol]=[bad,good]
        row=next(r for r in self.e.directional_scenarios(good.symbol) if r['side']==1 and r['kind']=='LIMIT')
        self.assertEqual(row['key'],'GOOD');self.assertTrue(row['sendable'])
        self.assertFalse(self.api.sent)

    def test_execution_skips_unfunded_best_and_sends_valid_alternative_same_cycle(self):
        self.e.warmup();good=self.plan('XAUUSDm',key='GOOD')
        bad=replace(good,key='EXPENSIVE',sl=good.entry-7.45,tp=good.entry+18,score=99,quality_score=99)
        self.cfg['risk']['max_trade_money']=2.17
        result=self.e.execute_pending_map(good.symbol,[bad,good],self.g.quote(good.symbol))
        self.assertEqual(result['sent'],1)
        self.assertAlmostEqual(self.api.sent[0]['sl'],good.sl,places=2)

    def test_unfunded_upgrade_does_not_block_filling_other_direction_or_remove_live_zone(self):
        self.e.warmup();p=self.plan('XAUUSDm',key='LIVE')
        order=self.api.add_pending(p)
        self.g.journal.data['orders'][str(order.ticket)]={'plan':p.to_dict(),'last_modify':self.clock()-100}
        self.cfg['risk']['max_trade_money']=2.17
        bad=replace(p,key='UPGRADE',sl=p.entry-7.45,tp=p.entry+18,score=99,quality_score=99)
        opposite=self.plan('XAUUSDm',side=-1,key='SELL')
        f=self.e.planner.caches['XAUUSDm'].frames['M15'];bars=list(f.bars)
        for i in (-2,-1):bars[i]=replace(bars[i],open=bars[i].close+f.atr*.3,high=max(bars[i].high,bars[i].close+f.atr*.3))
        self.e.planner.caches['XAUUSDm'].frames['M15']=replace(f,bars=tuple(bars),trend=-.8)
        row=self.e.execute_pending_map(p.symbol,[bad,opposite],self.g.quote(p.symbol))
        self.assertEqual(row['sent'],1);self.assertEqual(row['changed'],0)
        self.assertTrue(any(o.ticket==order.ticket and o.sl==p.sl for o in self.api.orders))
        self.assertEqual([r['type'] for r in self.api.sent],[3])

    def test_portfolio_replacement_skips_unfunded_top_ranked_zone(self):
        self.e.warmup();p=self.plan('XAUUSDm',key='OLD')
        order=self.api.add_pending(p);order.time_setup=self.clock()-100
        self.g.journal.data['orders'][str(order.ticket)]={'plan':p.to_dict()}
        self.cfg['risk']['max_trade_money']=2.17
        good=replace(self.plan('XAUUSDm',kind='STOP',key='GOOD_BREAK'),score=97,quality_score=97)
        bad=replace(good,key='EXPENSIVE_BREAK',sl=good.entry-7.45,tp=good.entry+18,score=99,quality_score=99)
        # No permitir cancelar una tesis válida por una puntuación heurística.
        for _ in range(15):
            self.assertFalse(self.e.replace_for_better_portfolio(p.symbol,[bad,good],self.g.quote(p.symbol)))
            self.clock.advance(1)
            self.api.set_quote(p.symbol,self.api.ticks[p.symbol].bid,fill=False)
        self.assertEqual(len(self.api.orders),1)
        self.assertEqual(self.api.orders[0].ticket,order.ticket)
        self.assertFalse(self.api.sent)

    def test_aggregate_history_without_family_calibration_does_not_veto_all_new_zones(self):
        self.e.warmup()
        history={'usable':False,'side_samples':{1:40,-1:40},'side_win_rate':{1:.1,-1:.1},'side_expectancy':{1:0,-1:0}}
        with patch.object(self.e.planner,'recent_pending_performance',return_value=history):
            plans=self.e.scan_plans('BTCUSDm',self.g.quote('BTCUSDm'),force=True)
        self.assertTrue(plans)
        rows=self.e.planner.pending_candidate_audit['BTCUSDm']
        self.assertTrue(any(r.get('historical_warning') for r in rows))
        self.assertFalse(any(r.get('reject_code')=='nonpositive_empirical_ev' for r in rows))

    def test_early_geometry_rejection_is_not_given_invented_quality(self):
        self.e.warmup();p=self.plan();self.e.candidates[p.symbol]=[]
        self.e.planner.pending_candidate_audit[p.symbol]=[dict(key=p.key,side='BUY',kind='LIMIT',
            entry=p.entry,sl=p.sl,tp=p.tp,timeframe='H1',rr=2,quality_score=None,activation_score=None,
            status='PENDING_REJECTED',reject_code='too_close',reason='Zona no válida')]
        row=next(r for r in self.e.directional_scenarios(p.symbol) if r['side']==1 and r['kind']=='LIMIT')
        self.assertIsNone(row['quality_score']);self.assertIsNone(row['activation_score'])
        self.assertFalse(row['sendable'])

    def test_export_is_read_only_and_contains_full_frames_limits_and_broker_rules(self):
        self.e.step();sent=copy.deepcopy(self.api.sent);orders=copy.deepcopy(self.api.orders)
        result=self.e.handle_command({'action':'export_diagnostic'});data=result['snapshot']
        self.assertTrue(result['ok']);self.assertEqual(data['build'],BUILD_ID)
        self.assertEqual(self.api.sent,sent);self.assertEqual(self.api.orders,orders)
        for symbol in self.cfg['symbols']:
            self.assertEqual(len(data['symbols'][symbol]['bars_by_timeframe']['M15']),180)
            self.assertEqual(data['symbols'][symbol]['broker_rules']['volume_min'],.01)
        self.assertEqual(data['configured_execution']['risk'],self.cfg['risk'])
        self.assertNotIn('assistant',data['configured_execution'])
        json.dumps(data,allow_nan=False)

    def test_export_in_observation_does_not_trigger_trading(self):
        self.cfg['mode']='observe';self.e.step()
        self.assertTrue(self.e.handle_command({'action':'export_diagnostic'})['ok'])
        self.assertFalse(self.api.sent)

    def test_continuation_long_and_short_do_not_require_ten_bar_breakout(self):
        for side in (1,-1):
            frames=self.signal(side,continuation=True)
            plan,detail=runner_plan('BTCUSDm',frames,self.g.quote('BTCUSDm'),self.cfg)
            self.assertIsNotNone(plan,detail);self.assertEqual(plan.side,side)
            self.assertIn('continuación',detail)

    def test_continuation_requires_observed_pullback(self):
        frames=self.signal(continuation=True);m=frames['M15']
        bars=list(m.bars)
        for i in (-4,-3,-2):bars[i]=replace(bars[i],low=101.1)
        frames['M15']=replace(m,bars=tuple(bars))
        self.assertIsNone(runner_plan('BTCUSDm',frames,self.g.quote('BTCUSDm'),self.cfg)[0])

    def test_continuation_h1_contradiction_prevents_market_entry(self):
        frames=self.signal(continuation=True);frames['H1']=replace(frames['H1'],trend=-.8)
        self.assertIsNone(runner_plan('BTCUSDm',frames,self.g.quote('BTCUSDm'),self.cfg)[0])

    def test_continuation_can_be_disabled_without_enabling_other_paths(self):
        frames=self.signal(continuation=True);self.cfg['runner']['allow_continuation']=False
        self.assertIsNone(runner_plan('BTCUSDm',frames,self.g.quote('BTCUSDm'),self.cfg)[0])

    def test_runner_remains_valid_after_five_minutes_when_price_has_not_drifted(self):
        frames=self.signal();self.clock.advance(600)
        self.api.set_quote('BTCUSDm',frames['M15'].bars[-1].close,spread=.1,fill=False)
        plan,detail=runner_plan('BTCUSDm',frames,self.g.quote('BTCUSDm'),self.cfg)
        self.assertIsNotNone(plan,detail);self.assertTrue(self.g.send_runner(plan))

    def test_older_than_one_m15_period_is_still_rejected(self):
        frames=self.signal()
        plan,detail=runner_plan('BTCUSDm',frames,self.g.quote('BTCUSDm'),self.cfg)
        self.assertIsNotNone(plan,detail)
        self.clock.advance(901)
        self.api.set_quote('BTCUSDm',frames['M15'].bars[-1].close,spread=.1,fill=False)
        current,detail=runner_plan('BTCUSDm',frames,self.g.quote('BTCUSDm'),self.cfg)
        self.assertIsNone(current);self.assertIn('caducada',detail)
        with self.assertRaisesRegex(Blocked,'caducada'):self.g.send_runner(plan)
        self.assertFalse(self.api.sent)

    def test_bad_external_timestamp_and_numeric_fusion_do_not_block_technical_signal(self):
        frames=self.signal();q=self.g.quote('BTCUSDm')
        base=runner_plan('BTCUSDm',frames,q,self.cfg)[0]
        for stamp,bias in (('malformed',1),(q.time,'bad'),(q.time,float('nan'))):
            context={'sources':{'coinglass':{'fresh':True,'updated':stamp}},'fusion':{'BTCUSDm':{'bias':bias,'confidence':1}}}
            plan,detail=runner_plan('BTCUSDm',frames,q,self.cfg,context)
            self.assertIsNotNone(plan,detail);self.assertEqual(plan.score,base.score)

    def test_migration_expands_only_old_default_runner_window_and_preserves_caps(self):
        raw=copy.deepcopy(DEFAULT);raw['schema_version']=1350
        raw['runner']['max_signal_age_seconds']=300;raw['risk']['max_trade_money']=2.17
        migrated=load_config(raw)
        self.assertEqual(migrated['runner']['max_signal_age_seconds'],900)
        self.assertEqual(migrated['risk'],raw['risk'])
        raw['runner']['max_signal_age_seconds']=120
        self.assertEqual(load_config(raw)['runner']['max_signal_age_seconds'],120)

    def test_runtime_publication_identifies_running_build_and_path(self):
        stop=threading.Event();views=[]
        def publish(row):views.append(row);stop.set()
        run_session(self.cfg,self.root,self.g.log,stop,queue.Queue(),publish,preview=True)
        row=views[-1]
        self.assertEqual(row['build'],BUILD_ID)
        self.assertEqual(row['runtime']['application_root'],str(self.root.resolve()))
        self.assertEqual(row['runtime']['python_executable'],sys.executable)
        self.assertTrue(row['runtime']['preview']);self.assertEqual(row['configured_execution']['mode'],'observe')

    def test_disconnected_runtime_still_reports_build_and_failed_stage(self):
        rows=[]
        with patch('runtime.Engine',side_effect=Blocked('Inicialización bloqueada en la prueba')):
            run_session(self.cfg,self.root,self.g.log,threading.Event(),queue.Queue(),rows.append,preview=True)
        self.assertFalse(rows[-1]['connected']);self.assertEqual(rows[-1]['build'],BUILD_ID)
        self.assertEqual(rows[-1]['runtime']['stage'],'CONECTANDO MT5')

    def test_funding_diagnostic_never_mutates_saved_risk_or_stop(self):
        p=self.plan('XAUUSDm');p=replace(p,sl=p.entry-7.45)
        self.cfg['risk']['max_trade_money']=2.17;before=copy.deepcopy(self.cfg)
        row=self.g.funding_diagnostic(p,self.g.snapshot())
        self.assertFalse(row['minimum_fits']);self.assertGreater(row['minimum_risk_usd'],7.45)
        self.assertEqual(self.cfg,before);self.assertAlmostEqual(p.entry-p.sl,7.45)
        self.assertFalse(self.api.sent)
