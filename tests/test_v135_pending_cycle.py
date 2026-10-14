"""Regresiones de revisión, alternativas y colocación; sin cuenta ni red reales."""
import copy
import unittest
from dataclasses import replace
from types import SimpleNamespace as NS
from unittest.mock import patch

from engine import Engine
from execution import PENDING,REMOVE,MODIFY,Blocked,BrokerRejected
from settings import DEFAULT,load_config
from tests.fixtures import PendingCase


class PendingCycle135Tests(PendingCase,unittest.TestCase):
    def setUp(self):
        super().setUp();self.e=Engine(self.g,self.cfg,self.g.log)
        self.addCleanup(self.e.close);self.e.warmup()

    def fresh(self,seconds=.3):
        self.clock.advance(seconds)
        for symbol in self.cfg['symbols']:
            self.api.set_quote(symbol,self.api.ticks[symbol].bid,fill=False)

    def own_order(self,p):
        o=self.api.add_pending(p)
        self.g.journal.data['orders'][str(o.ticket)]={'plan':p.to_dict(),'created':self.clock(),'last_modify':self.clock()}
        return o

    def alternatives(self):
        bad=replace(self.plan(key='FIRST_LIMIT'),score=99,quality_score=99,activation_score=90)
        good=self.plan(kind='STOP',key='NEXT_STOP')
        return bad,good

    def test_definitive_send_rejection_tries_next_same_direction_in_same_cycle(self):
        bad,good=self.alternatives();send=self.api.order_send
        def broker(req):
            if req['action']==PENDING and req['type']==2:
                self.api.sent.append(dict(req));return NS(retcode=10016,comment='stops rechazados',order=0,deal=0)
            return send(req)
        with patch.object(self.api,'order_send',side_effect=broker):
            row=self.e.execute_pending_map(bad.symbol,[bad,good],self.g.quote(bad.symbol))
        self.assertEqual([r['type'] for r in self.api.sent],[2,4])
        self.assertEqual((row['sent'],row['attempts'],row['unconfirmed']),(1,2,False))
        self.assertEqual(self.api.orders[0].price_open,round(good.entry,2))
        self.assertNotIn(bad.symbol,self.g.cooldowns)

    def test_order_check_rejection_uses_alternative_without_sending_rejected_levels(self):
        bad,good=self.alternatives();check=self.api.order_check
        def broker(req):
            return NS(retcode=10015,comment='precio inválido') if req['type']==2 else check(req)
        with patch.object(self.api,'order_check',side_effect=broker):
            row=self.e.execute_pending_map(bad.symbol,[bad,good],self.g.quote(bad.symbol))
        self.assertEqual(row['attempts'],2);self.assertEqual([r['type'] for r in self.api.sent],[4])
        self.assertEqual(len(row['levels']),1)

    def test_unchanged_rejected_levels_are_not_retried_on_every_tick(self):
        p=self.plan();self.api.send_retcode=10016
        self.g.send_immediate_plan(p)
        self.fresh()
        row=self.e.execute_pending_map(p.symbol,[p],self.g.quote(p.symbol))
        self.assertEqual(len(self.api.sent),1);self.assertEqual(row['attempts'],0)
        self.assertIn('10016',row['detail'])

    def test_rejection_quarantine_expires_and_new_levels_do_not_inherit_it(self):
        p=self.plan();self.api.send_retcode=10016;self.g.send_immediate_plan(p)
        self.assertTrue(self.g.pending_rejection_reason(p))
        different=replace(p,entry=p.entry-8,sl=p.sl-8,tp=p.tp-8)
        self.assertFalse(self.g.pending_rejection_reason(different))
        self.fresh(16)
        self.assertFalse(self.g.pending_rejection_reason(p))

    def test_unknown_send_stops_alternatives_and_survives_next_cycle(self):
        bad,good=self.alternatives();self.api.no_effect=True
        row=self.e.execute_pending_map(bad.symbol,[bad,good],self.g.quote(bad.symbol))
        self.assertEqual(len(self.api.sent),1);self.assertTrue(row['unconfirmed'])
        self.fresh();self.e.execute_pending_map(bad.symbol,[bad,good],self.g.quote(bad.symbol))
        self.assertEqual(len(self.api.sent),1)

    def test_server_rate_limit_stops_the_symbol_instead_of_hammering_alternatives(self):
        bad,good=self.alternatives();self.api.send_retcode=10024
        row=self.e.execute_pending_map(bad.symbol,[bad,good],self.g.quote(bad.symbol))
        self.assertEqual(len(self.api.sent),1);self.assertIn('10024',row['detail'])
        self.assertGreater(self.g.cooldowns[bad.symbol],self.clock())

    def test_rate_limit_in_order_check_also_stops_alternatives(self):
        bad,good=self.alternatives();self.api.fail_check=10024
        with patch.object(self.api,'order_check',wraps=self.api.order_check) as check:
            row=self.e.execute_pending_map(bad.symbol,[bad,good],self.g.quote(bad.symbol))
        self.assertEqual(check.call_count,1);self.assertFalse(self.api.sent)
        self.assertIn('10024',row['detail'])

    def test_cached_analysis_cannot_bypass_fresh_risk_calculation_at_send(self):
        p=self.plan();evaluation={}
        self.assertTrue(self.g.pending_budget_status(p,self.g.snapshot(),evaluation=evaluation)[0])
        calc=self.api.order_calc_profit
        with patch.object(self.api,'order_calc_profit',side_effect=lambda *a:calc(*a)*10):
            with self.assertRaises(Blocked):self.g.send_immediate_plan(p)
        self.assertFalse(self.api.sent);self.assertFalse(self.g.journal.data['intents'])

    def test_cached_analysis_cannot_bypass_new_terminal_permissions(self):
        p=self.plan()
        self.assertTrue(self.g.pending_budget_status(p,self.g.snapshot(),evaluation={})[0])
        self.api.terminal.trade_allowed=False
        with self.assertRaises(Blocked):self.g.send_immediate_plan(p)
        self.assertFalse(self.api.sent)

    def test_attempt_budget_bounds_many_different_rejected_candidates(self):
        self.cfg['execution']['pending_attempts_per_cycle']=3;self.api.send_retcode=10016
        p=self.plan()
        plans=[replace(p,key=f'ZONE_{i}',entry=p.entry-8*i,sl=p.sl-8*i,tp=p.tp-8*i) for i in range(7)]
        row=self.e.execute_pending_map(p.symbol,plans,self.g.quote(p.symbol))
        self.assertEqual(row['attempts'],3);self.assertEqual(len(self.api.sent),3)
        self.assertFalse(self.g.journal.data['intents'])

    def test_button_edits_better_existing_pending_after_confirmation(self):
        p=self.plan();o=self.own_order(p);self.fresh(2)
        better=replace(p,key='BETTER_LIMIT',entry=p.entry-8,sl=p.sl-8,tp=p.tp-8,score=98,quality_score=98,activation_score=90)
        with patch.object(self.e,'scan_plans',return_value=[better]):
            self.e.handle_command({'action':'assistant_best_pending','symbol':p.symbol})
            self.assertFalse(self.api.sent)
            self.fresh()
            result=self.e.handle_command({'action':'assistant_best_pending','symbol':p.symbol})
        self.assertTrue(result['ok']);self.assertEqual([r['action'] for r in self.api.sent],[MODIFY])
        self.assertEqual(o.price_open,round(better.entry,2));self.assertIn('1 edición',result['results'][0]['detail'])

    def test_valid_pending_is_not_retired_to_chase_breakout_score(self):
        p=self.plan();o=self.own_order(p);self.fresh(2)
        better=replace(self.plan(kind='STOP',key='NEW_BREAKOUT'),score=99,quality_score=99,activation_score=95)
        with patch.object(self.e,'scan_plans',return_value=[better]):
            for _ in range(8):
                self.e.handle_command({'action':'assistant_best_pending','symbol':p.symbol})
                self.fresh()
        self.assertFalse(self.api.sent)
        self.assertIn(o,self.api.orders)

    def test_no_retirement_even_if_fill_might_occur_during_cancellation(self):
        p=self.plan();o=self.own_order(p);self.fresh(2)
        better=replace(self.plan(kind='STOP',key='NEW_BREAKOUT'),score=99,quality_score=99,activation_score=95)
        self.api.fill_on_cancel=True
        for _ in range(7):
            self.e.execute_pending_map(p.symbol,[better],self.g.quote(p.symbol))
            self.fresh()
        self.assertFalse(self.api.sent)
        self.assertIn(o,self.api.orders)

    def test_lower_budget_alone_does_not_orphan_a_still_valid_pending(self):
        p=replace(self.plan(),bar_time=int(self.clock()-10000));o=self.own_order(p)
        self.e.planner.pending_candidate_audit[p.symbol]=[{'key':p.key,'reject_code':'over_risk_budget'}]
        for _ in range(12):
            self.e.lifecycle_action(p.symbol,[],self.g.quote(p.symbol));self.fresh(1)
        self.assertIn(o,self.api.orders);self.assertFalse(self.api.sent)

    def test_new_closed_structure_and_sustained_missing_zone_retires_obsolete_pending(self):
        p=replace(self.plan(),bar_time=int(self.clock()-10000));o=self.own_order(p)
        # An old structural bar alone is not enough to cancel a brand-new order.
        self.e.lifecycle_action(p.symbol,[],self.g.quote(p.symbol))
        self.assertFalse(self.api.sent)
        o.time_setup=self.clock()-1100
        self.g.journal.data['orders'][str(o.ticket)]['created']=self.clock()-1100
        self.e.lifecycle_action(p.symbol,[],self.g.quote(p.symbol))
        self.fresh(121)
        for _ in range(4):
            if self.e.lifecycle_action(p.symbol,[],self.g.quote(p.symbol)):break
            self.fresh(1)
        self.assertEqual([r['action'] for r in self.api.sent],[REMOVE]);self.assertNotIn(o,self.api.orders)

    def test_far_unmatched_zone_requires_sustained_confirmation(self):
        p=self.plan();o=self.own_order(p)
        self.api.set_quote(p.symbol,p.entry+p.horizon_atr*7,fill=False)
        for _ in range(10):
            self.e.lifecycle_action(p.symbol,[],self.g.quote(p.symbol));self.fresh(1)
        self.assertIn(o,self.api.orders);self.assertFalse(self.api.sent)
        o.time_setup=self.clock()-200
        self.g.journal.data['orders'][str(o.ticket)]['created']=self.clock()-200
        self.api.set_quote(p.symbol,p.entry+p.horizon_atr*7,fill=False)
        self.e.lifecycle_action(p.symbol,[],self.g.quote(p.symbol))
        self.clock.advance(121)
        for _ in range(4):
            self.api.set_quote(p.symbol,p.entry+p.horizon_atr*7,fill=False)
            if self.e.lifecycle_action(p.symbol,[],self.g.quote(p.symbol)):break
            self.clock.advance(1)
        self.assertEqual([r['action'] for r in self.api.sent],[REMOVE]);self.assertNotIn(o,self.api.orders)

    def test_button_in_observation_returns_four_scenarios_without_mutating_mt5(self):
        self.cfg['mode']='observe'
        result=self.e.handle_command({'action':'assistant_best_pending','symbol':'ALL'})
        self.assertFalse(result['ok']);self.assertFalse(self.api.sent)
        self.assertEqual(len(result['results']),2)
        for r in result['results']:
            self.assertEqual(len(r['scenarios']),4);self.assertIn('observación',r['detail'])

    def test_automatic_risk_block_is_explicit_and_keeps_parameters_visible(self):
        self.cfg['risk']['max_trade_money']=.01;self.cfg['risk']['max_trade_pct']=.01
        self.e.planner.pending_candidate_audit['BTCUSDm']=[{'reject_code':'over_risk_budget','risk_usd':7.45}]
        row=self.e.execute_pending_map('BTCUSDm',[],self.g.quote('BTCUSDm'))
        self.assertEqual(row['state'],'BLOQUEO DE RIESGO');self.assertIn('7.45',row['detail'])
        self.assertFalse(self.api.sent);self.assertEqual(self.cfg['risk']['max_trade_money'],.01)

    def test_strict_and_presence_share_valuation_only_inside_current_scan(self):
        api=self.api.order_calc_profit
        with patch.object(self.api,'order_calc_profit',wraps=api) as calc:
            self.e.scan_plans('BTCUSDm',self.g.quote('BTCUSDm'),force=True)
            first=calc.call_count
            self.e.scan_plans('BTCUSDm',self.g.quote('BTCUSDm'),force=True)
            self.assertGreater(first,0);self.assertEqual(calc.call_count,2*first)

    def test_shortlist_keeps_limit_and_stop_when_only_one_per_quadrant_is_allowed(self):
        self.cfg['execution']['pending_candidates_per_quadrant']=1
        cache=self.e.planner.caches['BTCUSDm']
        plans=self.e.planner.proposed_pending_plans('BTCUSDm',cache.setups,self.g.quote('BTCUSDm'),all_candidates=True,presence=True)
        self.assertIn((1,'LIMIT'),{(p.side,p.kind) for p in plans})
        self.assertIn((1,'STOP'),{(p.side,p.kind) for p in plans})

    def test_migration_accelerates_scan_without_changing_user_risk_or_mode(self):
        raw=copy.deepcopy(DEFAULT);raw['schema_version']=1340;raw['mode']='observe'
        raw['risk']['max_trade_money']=2.17;raw['risk']['max_trade_pct']=4
        raw['poll_seconds']=.35;raw['execution']['rapid_parameter_map_refresh_seconds']=.4
        cfg=load_config(raw)
        self.assertEqual(cfg['risk'],raw['risk']);self.assertEqual(cfg['mode'],'observe')
        self.assertEqual(cfg['poll_seconds'],.2);self.assertEqual(cfg['execution']['rapid_parameter_map_refresh_seconds'],.2)

    def test_invalid_attempt_budget_is_rejected_at_config_loading(self):
        for value in (0,17,2.5,True):
            raw=copy.deepcopy(DEFAULT);raw['execution']['pending_attempts_per_cycle']=value
            with self.subTest(value=value),self.assertRaises(ValueError):load_config(raw)

    def test_rejected_check_reports_real_return_code_and_has_no_intent(self):
        p=self.plan();self.api.fail_check=10016
        with self.assertRaises(BrokerRejected) as caught:self.g.send_immediate_plan(p)
        self.assertEqual(caught.exception.code,10016);self.assertIn('10016',str(caught.exception))
        self.assertFalse(self.g.journal.data['intents']);self.assertFalse(self.api.sent)
