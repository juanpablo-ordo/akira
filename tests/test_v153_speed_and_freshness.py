"""Menos IPC sin reutilizar reservas o autorizaciones de envío antiguas."""
import copy,unittest
from dataclasses import asdict,replace
from unittest.mock import patch
from engine import Engine
from execution import Blocked
from settings import DEFAULT,load_config
from strategy import Bar,normalize
from tests.fixtures import PendingCase


class SpeedFreshnessTests(PendingCase,unittest.TestCase):
    def setUp(self):
        super().setUp();self.e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(self.e.close)

    def seed(self,symbol='BTCUSDm'):
        self.e.quotes[symbol]=self.g.quote(symbol);snap=self.g.snapshot()
        evaluation=self.e.analysis_evaluation(symbol,snap)
        p=self.plan(symbol)
        self.g.plan_money(p,evaluation=evaluation)
        return p,snap,evaluation

    def test_new_confirmed_order_reuses_geometry_but_rebuilds_reservations(self):
        p,snap,evaluation=self.seed()
        self.assertEqual(self.g.reservation_ledger(snap,evaluation=evaluation)['reserved_usd'],0)
        self.api.add_pending(p,magic=0)
        current=self.g.snapshot();fresh=self.e.analysis_evaluation(p.symbol,current)
        self.assertIsNot(fresh,evaluation)
        with patch.object(self.api,'order_calc_profit',wraps=self.api.order_calc_profit) as calc:
            self.g.plan_money(p,evaluation=fresh)
            self.assertEqual(calc.call_count,0)
        ledger=self.g.reservation_ledger(current,evaluation=fresh)
        self.assertGreater(ledger['reserved_usd'],0);self.assertFalse(ledger['rows'][0]['owned'])
        self.assertFalse(self.api.sent)

    def test_mutated_sl_in_same_snapshot_does_not_reuse_old_ledger(self):
        p=self.plan();o=self.api.add_pending(p,magic=0);snap=self.g.snapshot();evaluation={}
        old=self.g.reservation_ledger(snap,evaluation=evaluation)
        o.sl-=80
        new=self.g.reservation_ledger(snap,evaluation=evaluation)
        self.assertGreater(new['reserved_usd'],old['reserved_usd']+.7)
        self.assertEqual(new['rows'][0]['sl'],o.sl)

    def test_swap_change_updates_position_reservation_with_same_quote(self):
        pos=self.api.add_position(magic=0);snap=self.g.snapshot();evaluation={}
        old=self.g.reservation_ledger(snap,evaluation=evaluation)
        pos.swap=-3
        new=self.g.reservation_ledger(snap,evaluation=evaluation)
        self.assertAlmostEqual(new['reserved_usd']-old['reserved_usd'],3)

    def test_new_unknown_intent_reserves_capacity_without_new_snapshot(self):
        snap=self.g.snapshot();evaluation={}
        self.assertEqual(self.g.reservation_ledger(snap,evaluation=evaluation)['unconfirmed_requests'],0)
        self.g.journal.data['intents']['BTCUSDm']={'operation':'open','request':{},'risk':None}
        new=self.g.reservation_ledger(snap,evaluation=evaluation)
        self.assertEqual(new['available_usd'],0);self.assertFalse(new['risk_known'])

    def test_account_cap_change_is_reflected_in_same_snapshot(self):
        snap=self.g.snapshot();evaluation={}
        old=self.g.reservation_ledger(snap,evaluation=evaluation)
        snap.account.balance=50;snap.account.equity=50
        new=self.g.reservation_ledger(snap,evaluation=evaluation)
        self.assertLess(new['cap_usd'],old['cap_usd'])

    def test_explicit_cap_change_is_reflected_without_broker_mutation(self):
        snap=self.g.snapshot();evaluation={}
        self.g.reservation_ledger(snap,evaluation=evaluation)
        self.cfg['risk']['portfolio_money_cap']=7
        self.assertEqual(self.g.reservation_ledger(snap,evaluation=evaluation)['cap_usd'],7)
        self.assertFalse(self.api.sent)

    def test_ticket_owner_change_updates_reported_manual_reservation(self):
        o=self.api.add_pending(self.plan());snap=self.g.snapshot();evaluation={}
        self.assertTrue(self.g.reservation_ledger(snap,evaluation=evaluation)['rows'][0]['owned'])
        o.magic=0
        self.assertFalse(self.g.reservation_ledger(snap,evaluation=evaluation)['rows'][0]['owned'])

    def test_ignored_order_scope_cannot_hide_reservation_from_next_check(self):
        o=self.api.add_pending(self.plan());snap=self.g.snapshot();evaluation={}
        self.assertEqual(self.g.reservation_ledger(snap,(o.ticket,),evaluation)['reserved_usd'],0)
        self.assertGreater(self.g.reservation_ledger(snap,evaluation=evaluation)['reserved_usd'],0)

    def test_same_tick_timestamp_different_price_invalidates_analysis_valuation(self):
        p,snap,evaluation=self.seed();previous=self.api.ticks[p.symbol].time_msc
        self.api.set_quote(p.symbol,self.api.ticks[p.symbol].bid+1,spread=2,fill=False)
        self.assertEqual(self.api.ticks[p.symbol].time_msc,previous)
        self.e.quotes[p.symbol]=self.g.quote(p.symbol)
        fresh=self.e.analysis_evaluation(p.symbol,snap)
        self.assertIsNot(fresh,evaluation)
        self.assertFalse(any(isinstance(k,tuple) and k[0]=='order_calc_profit' for k in fresh))

    def test_new_cycle_never_inherits_old_money_calculations(self):
        p,snap,evaluation=self.seed();self.e.cycle+=1
        fresh=self.e.analysis_evaluation(p.symbol,snap)
        with patch.object(self.api,'order_calc_profit',wraps=self.api.order_calc_profit) as calc:
            self.g.plan_money(p,evaluation=fresh);self.assertEqual(calc.call_count,2)

    def test_advanced_clock_with_unchanged_book_invalidates_scope(self):
        p,snap,evaluation=self.seed();self.clock.advance(1)
        fresh=self.e.analysis_evaluation(p.symbol,snap)
        self.assertIsNot(fresh,evaluation)
        self.assertFalse(any(isinstance(k,tuple) and k[0]=='order_calc_profit' for k in fresh))

    def test_continuously_advancing_clock_reuses_recent_money_without_renewing_age(self):
        p,snap,evaluation=self.seed();initial_age=evaluation['_valued_at']
        self.clock.advance(.03);self.api.add_pending(p,magic=0)
        fresh=self.e.analysis_evaluation(p.symbol,self.g.snapshot())
        self.assertEqual(fresh['_valued_at'],initial_age)
        with patch.object(self.api,'order_calc_profit',wraps=self.api.order_calc_profit) as calc:
            self.g.plan_money(p,evaluation=fresh);self.assertEqual(calc.call_count,0)
        self.clock.advance(.48)
        expired=self.e.analysis_evaluation(p.symbol,self.g.snapshot())
        self.assertFalse(any(isinstance(k,tuple) and k[0]=='order_calc_profit' for k in expired))

    def test_account_currency_change_invalidates_converted_money(self):
        p,snap,evaluation=self.seed();snap.account.currency='EUR'
        fresh=self.e.analysis_evaluation(p.symbol,snap)
        self.assertFalse(any(isinstance(k,tuple) and k[0]=='order_calc_profit' for k in fresh))

    def test_commission_setting_change_invalidates_money_scope(self):
        p,snap,evaluation=self.seed();self.cfg['risk']['round_turn_commission_per_lot']+=2
        fresh=self.e.analysis_evaluation(p.symbol,snap)
        self.assertFalse(any(isinstance(k,tuple) and k[0]=='order_calc_profit' for k in fresh))

    def test_sizing_uses_outward_normalized_stop_instead_of_cheaper_raw_stop(self):
        p=self.plan('XAUUSDm');p=replace(p,entry=round(p.entry,2),sl=round(p.entry,2)-1.005,tp=round(p.entry,2)+2)
        normalized=normalize(p,.01);raw_risk=self.g.plan_money(p)[0];real_risk=self.g.plan_money(normalized)[0]
        self.assertGreater(real_risk,raw_risk)
        self.cfg['risk']['max_trade_pct']=100;self.cfg['risk']['max_trade_money']=(raw_risk+real_risk)/2
        with self.assertRaises(Blocked):self.g.volume_for_plan(p,self.g.snapshot(),evaluation={})
        self.assertFalse(self.api.sent)

    def test_fresh_validation_uses_one_ledger_then_next_validation_recalculates(self):
        self.api.add_pending(self.plan('XAUUSDm'),magic=0);p=self.plan();snap=self.g.snapshot()
        with patch.object(self.api,'order_calc_profit',wraps=self.api.order_calc_profit) as calc:
            self.g.validate_plan(p,snap)
            self.assertEqual(calc.call_count,3) # SL, TP y ticket manual una sola vez.
            self.g.validate_plan(p,snap);self.assertEqual(calc.call_count,6)

    def test_changed_broker_money_after_analysis_is_rejected_at_actual_send(self):
        p,snap,evaluation=self.seed();self.assertTrue(self.g.pending_budget_status(p,snap,evaluation=evaluation)[0])
        profit=self.api.order_calc_profit
        with patch.object(self.api,'order_calc_profit',side_effect=lambda *a:profit(*a)*100):
            with self.assertRaises(Blocked):self.g.send_immediate_plan(p)
        self.assertFalse(self.api.sent)

    def test_scalar_bar_serialization_keeps_values_and_cannot_mutate_bar(self):
        bar=Bar(123,1.2,2.3,.8,1.8,99)
        data=bar.to_dict();self.assertEqual(data,asdict(bar));data['close']=100
        self.assertEqual(bar.close,1.8);self.assertIsNot(data,bar.to_dict())

    def test_production_first_cycle_sends_qualified_sides_and_reduces_ipc(self):
        self.cfg=load_config(DEFAULT);self.cfg['mode']='trade';self.g.cfg=self.cfg;self.e.close()
        self.e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(self.e.close)
        from contextlib import ExitStack
        with ExitStack() as stack:
            methods=('account_info','terminal_info','positions_get','orders_get','symbol_info','symbol_info_tick',
                'symbol_select','copy_rates_from_pos','order_calc_profit','order_calc_margin','order_check','order_send')
            mocks=[stack.enter_context(patch.object(self.api,n,wraps=getattr(self.api,n))) for n in methods]
            view=self.e.step()
            self.assertLess(sum(m.call_count for m in mocks),310)
        self.assertEqual(len(self.api.orders),2)
        self.assertEqual({o.symbol for o in self.api.orders},{'BTCUSDm','XAUUSDm'})
        self.assertTrue(all(row['state']=='PENDIENTES CONFIRMADAS' for row in view['status'].values()))
        before=copy.deepcopy(self.api.sent);self.clock.advance(.2)
        for s in self.cfg['symbols']:self.api.set_quote(s,self.api.ticks[s].bid,fill=False)
        self.e.step();self.assertEqual(self.api.sent,before)
