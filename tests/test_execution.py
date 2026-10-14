import copy,json,tempfile,unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from settings import load_config,DEFAULT
from strategy import Plan
from execution import Gateway,Journal,Reporter,Blocked,PENDING,REMOVE,MODIFY,SLTP,DEAL,OWN_PENDING
from tests.fake_mt5 import Clock,FakeMT5

from tests.fixtures import PendingCase

class ExecutionTests(PendingCase,unittest.TestCase):
    def test_four_pending_types_are_supported(self):
        for side,kind,typ in ((1,'LIMIT',2),(-1,'LIMIT',3),(1,'STOP',4),(-1,'STOP',5)):
            with self.subTest(side=side,kind=kind):
                self.api.orders.clear();self.g.journal.data['intents'].clear()
                self.g.send_immediate_plan(self.plan(side=side,kind=kind));r=self.api.sent[-1]
                self.assertEqual((r['action'],r['type'],r['type_filling']),(PENDING,typ,2))
                self.assertGreater(r['sl'],0);self.assertGreater(r['tp'],0)
    def test_gold_risk_is_structural_and_never_twenty(self):
        p=self.plan('XAUUSDm');prepared=self.g.prepare(p);self.assertLess(prepared.risk,3)
        self.g.send_immediate_plan(p);self.assertEqual(self.api.sent[-1]['sl'],round(p.sl,2))
    def test_market_entry_is_rejected(self):self.assert_blocked(replace(self.plan(),kind='MARKET'))
    def test_other_lane_is_rejected(self):self.assert_blocked(replace(self.plan(),lane='SCALP'))
    def test_low_level_market_entry_cannot_bypass_gate(self):
        with self.assertRaises(Blocked):self.g._send('BTCUSDm',{'action':DEAL},'open',self.plan())
        self.assertFalse(self.api.sent)
    def test_wrong_side_geometry_is_rejected(self):
        p=self.plan();self.assert_blocked(replace(p,sl=p.entry+1))
    def test_future_entry_cannot_be_on_wrong_side_of_market(self):
        p=self.plan();self.assert_blocked(replace(p,entry=self.api.ticks[p.symbol].ask+1))
    def test_nonfinite_prices_are_rejected(self):self.assert_blocked(replace(self.plan(),sl=float('nan')))
    def test_stale_tick_blocks_send(self):
        self.clock.advance(20);self.assert_blocked(self.plan())
    def test_spread_change_before_send_rechecks_plan(self):
        prepared=self.g.prepare(self.plan());self.api.set_quote('BTCUSDm',self.api.ticks['BTCUSDm'].bid,100,fill=False)
        with self.assertRaises(Blocked):self.g.send(prepared)
        self.assertFalse(self.api.sent)
    def test_tiny_stop_with_high_spread_is_rejected(self):
        p=self.plan();self.assert_blocked(replace(p,sl=p.entry-.5,tp=p.entry+2))
    def test_oversized_structural_loss_is_rejected_without_shrinking_stop(self):
        p=self.plan();bad=replace(p,sl=p.entry-500,tp=p.entry+1500);self.assert_blocked(bad);self.assertEqual(bad.sl,p.entry-500)
    def test_low_net_rr_is_rejected(self):
        p=self.plan();self.assert_blocked(replace(p,tp=p.entry+50))
    def test_missing_broker_permission_blocks_new_orders(self):
        self.api.terminal.trade_allowed=False;self.assert_blocked(self.plan())
    def test_observe_has_no_mutations(self):
        self.cfg['mode']='observe';self.assert_blocked(self.plan())
    def test_expected_account_is_enforced(self):
        self.cfg['expected_login']=999;self.assert_blocked(self.plan())
    def test_account_switch_is_blocked(self):
        self.g.snapshot();self.api.account.login=456
        with self.assertRaises(Blocked):self.g.snapshot()
    def test_journal_from_another_account_is_blocked_on_reopen(self):
        self.g.snapshot();self.api.account.login=456
        other=Gateway(self.api,self.cfg,Journal(self.root/'state.json'),self.g.log,self.clock)
        with self.assertRaises(Blocked):other.snapshot()
    def test_pending_reserves_full_risk_of_both_oco_sides(self):
        a=self.plan();b=self.plan(side=-1,kind='STOP');self.api.add_pending(a);self.api.add_pending(b)
        expected=sum(self.g.plan_money(p)[0] for p in (a,b));self.assertAlmostEqual(self.g.exposure_risk(self.g.snapshot()),expected,places=5)
    def test_manual_pending_reserves_full_risk(self):
        p=self.plan();self.api.add_pending(p,magic=0)
        self.assertAlmostEqual(self.g.exposure_risk(self.g.snapshot()),self.g.plan_money(p)[0],places=5)
    def test_unprotected_external_position_prevents_added_risk(self):
        self.api.add_position(magic=0,sl=0,tp=0);self.assert_blocked(self.plan())
    def test_protected_external_position_is_not_managed(self):
        p=self.api.add_position(magic=0)
        with self.assertRaises(Blocked):self.g.update_stop(p,p.sl+1)
        self.assertFalse(self.api.sent)
    def test_manual_order_is_never_auto_modified_or_deleted(self):
        p=self.plan();o=self.api.add_pending(p,magic=0)
        with self.assertRaises(Blocked):self.g.cancel(o,'invalidate')
        with self.assertRaises(Blocked):self.g.modify_pending(o,replace(p,entry=p.entry-2),'improve')
        self.assertFalse(self.api.sent)
    def test_owned_pending_can_be_deleted_automatically(self):
        o=self.api.add_pending(self.plan());self.g.cancel(o,'invalidated')
        self.assertEqual(self.api.sent[-1]['action'],REMOVE);self.assertEqual(len(self.api.orders),0)
    def test_owned_pending_modification_retains_structural_sl_tp(self):
        p=self.plan();o=self.api.add_pending(p);new=replace(p,entry=p.entry-2,sl=p.sl-2,tp=p.tp-2)
        self.g.modify_pending(o,new,'improve');r=self.api.sent[-1]
        self.assertEqual(r['action'],MODIFY);self.assertLessEqual(abs(r['sl']-new.sl),self.api.infos[p.symbol].trade_tick_size+1e-8)
        self.assertLessEqual(r['sl'],new.sl)
    def test_modification_cannot_change_kind(self):
        p=self.plan();o=self.api.add_pending(p)
        with self.assertRaises(Blocked):self.g.modify_pending(o,replace(p,kind='STOP'),'bad')
    def test_modification_cannot_increase_risk_past_limit(self):
        p=self.plan();o=self.api.add_pending(p)
        with self.assertRaises(Blocked):self.g.modify_pending(o,replace(p,sl=p.entry-600),'bad')
    def test_freeze_near_market_blocks_edit(self):
        p=self.plan();o=self.api.add_pending(p);self.api.infos[p.symbol].trade_freeze_level=100000
        with self.assertRaises(Blocked):self.g.modify_pending(o,p,'bad')
    def test_margin_reserves_all_future_orders(self):
        self.api.order_calc_margin=lambda *a:20
        self.api.add_pending(self.plan(side=-1))
        self.assert_blocked(self.plan())
    def test_total_risk_cannot_be_advisory(self):
        self.cfg['risk']['portfolio_money_cap']=.5;self.assert_blocked(self.plan())
    def test_duplicate_pending_thesis_is_not_added(self):
        p=self.plan();self.api.add_pending(p);self.assert_blocked(p)
    def test_own_map_count_is_enforced_at_transport(self):
        self.cfg['pending']['max_own_map_orders']=1;self.api.add_pending(self.plan(side=-1))
        self.assert_blocked(self.plan())
    def test_stop_and_target_order_mode_permissions_are_enforced(self):
        self.api.infos['BTCUSDm'].order_mode=3;self.assert_blocked(self.plan())
    def test_dropped_ack_is_reconciled_from_visible_order(self):
        self.api.drop_ack=True;self.g.send_immediate_plan(self.plan())
        self.assertIn('BTCUSDm',self.g.journal.data['intents']);self.g.reconcile(self.g.snapshot())
        self.assertNotIn('BTCUSDm',self.g.journal.data['intents']);self.assertEqual(len(self.api.sent),1)
    def test_accepted_reply_alone_is_not_confirmation(self):
        self.api.no_effect=True;self.g.send_immediate_plan(self.plan())
        self.g.reconcile(self.g.snapshot());self.assertIn('BTCUSDm',self.g.journal.data['intents'])
    def test_uncertain_send_is_not_retried_after_empty_history(self):
        self.api.no_effect=True;self.g.send_immediate_plan(self.plan());self.clock.advance(120)
        self.api.set_quote('BTCUSDm',self.api.ticks['BTCUSDm'].bid,fill=False);self.g.reconcile(self.g.snapshot())
        with self.assertRaises(Blocked):self.g.send_immediate_plan(self.plan())
        self.assertEqual(len(self.api.sent),1)
    def test_unknown_intent_survives_restart(self):
        self.api.no_effect=True;self.g.send_immediate_plan(self.plan())
        self.g=Gateway(self.api,self.cfg,Journal(self.root/'state.json'),self.g.log,self.clock)
        with self.assertRaises(Blocked):self.g.send_immediate_plan(self.plan())
    def test_definitive_rejection_releases_intent(self):
        self.api.send_retcode=10019;self.g.send_immediate_plan(self.plan())
        self.assertNotIn('BTCUSDm',self.g.journal.data['intents'])
    def test_uncertain_btc_does_not_lock_gold_but_reserves_its_risk(self):
        self.api.no_effect=True;self.g.send_immediate_plan(self.plan())
        self.api.no_effect=False;self.g.send_immediate_plan(self.plan('XAUUSDm'))
        self.assertEqual(len(self.api.sent),2);self.assertEqual(self.api.sent[-1]['symbol'],'XAUUSDm')
    def test_fill_during_cancel_is_not_an_extra_market_entry(self):
        o=self.api.add_pending(self.plan());self.api.fill_on_cancel=True;self.g.cancel(o,'invalid')
        self.g.reconcile(self.g.snapshot());self.assertEqual(len(self.api.positions),1)
        self.assertEqual([r['action'] for r in self.api.sent],[REMOVE])
    def test_filled_order_binds_original_plan_to_position(self):
        p=self.plan();self.g.send_immediate_plan(p);self.g.reconcile(self.g.snapshot());o=self.api.orders[0]
        self.api.fill_order(o);self.g.reconcile(self.g.snapshot())
        self.assertEqual(self.g.journal.data['positions'][str(o.ticket)]['plan']['key'],p.key)
    def test_sl_cannot_be_widened(self):
        p=self.api.add_position(magic=OWN_PENDING)
        self.assertFalse(self.g.update_stop(p,p.sl-10));self.assertFalse(self.api.sent)
    def test_order_check_rejection_has_no_send(self):
        self.api.fail_check=10016;self.assert_blocked(self.plan())
    def test_netting_external_position_blocks_pending_addition(self):
        self.api.account.margin_mode=0;self.api.add_position(magic=0);self.assert_blocked(self.plan())
    def test_secondary_closed_market_does_not_block_btc_risk_valuation(self):
        self.api.add_pending(self.plan('XAUUSDm'))
        self.clock.advance(60);self.api.set_quote('BTCUSDm',self.api.ticks['BTCUSDm'].bid,fill=False)
        self.g.send_immediate_plan(self.plan());self.assertEqual(self.api.sent[-1]['symbol'],'BTCUSDm')
    def test_same_thesis_is_not_added_after_its_pending_has_filled(self):
        p=self.plan();self.g.send_immediate_plan(p);self.g.reconcile(self.g.snapshot());o=self.api.orders[0]
        self.api.fill_order(o);self.g.reconcile(self.g.snapshot())
        with self.assertRaises(Blocked):self.g.send_immediate_plan(p)
        self.assertEqual(len(self.api.sent),1)
    def test_missing_order_during_uncertain_cancel_requires_evidence(self):
        o=self.api.add_pending(self.plan());self.api.drop_ack=True;self.g.cancel(o,'replace')
        self.api.history_orders.clear();self.g.reconcile(self.g.snapshot())
        self.assertIn(o.symbol,self.g.journal.data['intents']);self.assertGreater(self.g.exposure_risk(self.g.snapshot()),0)
    def test_order_that_filled_during_cancel_waits_for_position_visibility(self):
        o=self.api.add_pending(self.plan());self.api.fill_on_cancel=True;self.g.cancel(o,'replace')
        p=self.api.positions[0];self.api.positions.clear();self.g.reconcile(self.g.snapshot())
        self.assertIn(o.symbol,self.g.journal.data['intents'])
        self.api.positions.append(p);self.g.reconcile(self.g.snapshot());self.assertNotIn(o.symbol,self.g.journal.data['intents'])

if __name__=='__main__':unittest.main()
