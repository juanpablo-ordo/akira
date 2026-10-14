"""Regresiones del bloqueo conjunto; únicamente servidor MT5 sintético."""
import copy
import json
import unittest
from dataclasses import replace

from assistant_akira import AkiraAssistant
from engine import Engine
from execution import Blocked
from settings import DEFAULT,load_config
from tests.fixtures import PendingCase


class Reservation151Tests(PendingCase,unittest.TestCase):
    def old_cancel(self,p=None):
        p=p or self.plan();order=self.api.add_pending(p)
        before=self.g.fingerprint(order,'order');self.api.orders.remove(order)
        intent={'operation':'cancel','request':{'action':8,'order':order.ticket,'symbol':p.symbol},
                'before':before,'plan':None,'created':self.clock(),'retcode':None}
        self.g.journal.data['intents'][p.symbol]=intent
        return p,order,intent

    def test_old_cancel_missing_money_reserves_original_sl_risk_not_full_account(self):
        p,_,_=self.old_cancel();snap=self.g.snapshot()
        self.assertAlmostEqual(self.g.exposure_risk(snap),self.g.plan_money(p)[0])
        self.assertAlmostEqual(self.g.reserved_pending_margin(snap),1.0)
        self.assertIn('reconstruida',self.g.reservation_ledger(snap)['rows'][0]['reason'])

    def test_missing_money_cancel_survives_restart_and_does_not_block_other_symbol(self):
        p,_,_=self.old_cancel();self.cfg['risk']['portfolio_money_cap']=5.0
        self.g.journal.save()
        from execution import Gateway,Journal
        self.g=Gateway(self.api,self.cfg,Journal(self.root/'state.json'),self.g.log,self.clock)
        self.g.reconcile(self.g.snapshot())
        self.assertIn(p.symbol,self.g.journal.data['intents'])
        self.assertTrue(self.g.send_immediate_plan(self.plan('XAUUSDm')))
        self.assertEqual([r['symbol'] for r in self.api.sent],['XAUUSDm'])
        self.assertIn('BTCUSDm',self.g.journal.data['intents'])

    def test_unknown_cancel_is_not_released_by_time_or_empty_history(self):
        p,_,_=self.old_cancel();self.clock.advance(86400)
        self.g.reconcile(self.g.snapshot())
        self.assertIn(p.symbol,self.g.journal.data['intents'])
        self.assertGreater(self.g.exposure_risk(self.g.snapshot()),0)
        self.assertFalse(self.api.sent)

    def test_definitively_cancelled_old_ticket_releases_its_reservation(self):
        p,order,_=self.old_cancel()
        from types import SimpleNamespace as NS
        self.api.history_orders.append(NS(ticket=order.ticket,symbol=p.symbol,state=2))
        self.g.reconcile(self.g.snapshot())
        self.assertNotIn(p.symbol,self.g.journal.data['intents'])
        self.assertEqual(self.g.exposure_risk(self.g.snapshot()),0)

    def test_old_open_request_can_recover_its_sl_and_volume(self):
        p=self.plan()
        self.g.journal.data['intents'][p.symbol]={'operation':'open','created':self.clock(),'request':{
            'action':5,'symbol':p.symbol,'type':2,'price':p.entry,'sl':p.sl,'tp':p.tp,'volume':.01,'comment':'old-open'}}
        self.assertAlmostEqual(self.g.exposure_risk(self.g.snapshot()),self.g.plan_money(p)[0])

    def test_no_evidence_or_sl_still_blocks_but_names_the_request(self):
        self.g.journal.data['intents']['BTCUSDm']={'operation':'open','request':{'type':2},'created':self.clock()}
        ledger=self.g.reservation_ledger(self.g.snapshot());reason=self.g.reservation_reason(ledger)
        self.assertEqual(ledger['available_usd'],0);self.assertFalse(ledger['risk_known'])
        self.assertIn('Solicitud sin confirmar',reason);self.assertIn('BTCUSDm',reason)
        self.assert_blocked(self.plan('XAUUSDm'))

    def test_unknown_or_negative_saved_money_cannot_release_risk(self):
        snap=self.g.snapshot()
        for value in (float('nan'),float('inf'),-2,None):
            with self.subTest(value=value):
                self.g.journal.data['intents']['BTCUSDm']={'operation':'open','risk':value,'request':{},'created':self.clock()}
                ledger=self.g.reservation_ledger(snap)
                self.assertEqual(ledger['available_usd'],0);json.dumps(ledger,allow_nan=False)

    def test_returned_order_id_prevents_double_reserving_rewritten_comment(self):
        p=self.plan();self.g.send_immediate_plan(p);order=self.api.orders[0];order.comment='broker-normalized'
        snap=self.g.snapshot()
        from execution import order_plan
        self.assertAlmostEqual(self.g.exposure_risk(snap),self.g.plan_money(order_plan(order))[0])
        self.assertAlmostEqual(self.g.reserved_pending_margin(snap),1)

    def test_known_broker_ticket_cannot_match_another_order_by_comment(self):
        p=self.plan();order=self.api.add_pending(p);order.comment='reused'
        self.g.journal.data['intents'][p.symbol]={'operation':'open','order':999999,
            'created':self.clock(),'risk':2,'margin':3,'request':{'comment':'reused','volume':.01}}
        snap=self.g.snapshot()
        self.assertAlmostEqual(self.g.exposure_risk(snap),self.g.plan_money(p)[0]+2)
        self.g.reconcile(snap)
        self.assertIn(p.symbol,self.g.journal.data['intents'])

    def test_blank_comment_manual_order_does_not_hide_unknown_open(self):
        p=self.plan();self.api.add_pending(p,magic=0).comment=''
        self.g.journal.data['intents'][p.symbol]={'operation':'open','request':{'comment':''},'risk':2,'margin':3}
        snap=self.g.snapshot()
        self.assertAlmostEqual(self.g.exposure_risk(snap),self.g.plan_money(p)[0]+2)
        self.assertAlmostEqual(self.g.reserved_pending_margin(snap),4)

    def test_comment_in_another_symbol_does_not_hide_open_risk_or_margin(self):
        self.api.add_pending(self.plan('XAUUSDm')).comment='same'
        self.g.journal.data['intents']['BTCUSDm']={'operation':'open','request':{'comment':'same'},'risk':2,'margin':3}
        snap=self.g.snapshot()
        self.assertAlmostEqual(self.g.reserved_pending_margin(snap),4)
        self.assertAlmostEqual(self.g.exposure_risk(snap),self.g.plan_money(self.plan('XAUUSDm'))[0]+2)

    def test_modification_reserves_worst_of_old_and_new_sl_until_confirmed(self):
        p=self.plan();order=self.api.add_pending(p)
        new=replace(p,sl=p.sl-50,tp=p.tp+150)
        self.g.journal.data['intents'][p.symbol]={'operation':'modify_order','request':{
            'order':order.ticket,'price':new.entry,'sl':new.sl,'tp':new.tp},
            'before':self.g.fingerprint(order,'order'),'created':self.clock()}
        self.assertAlmostEqual(self.g.exposure_risk(self.g.snapshot()),self.g.plan_money(new)[0])
        self.assertAlmostEqual(self.g.reserved_pending_margin(self.g.snapshot()),1)

    def test_ignored_order_still_has_uncertain_cancel_reservation(self):
        p=self.plan();order=self.api.add_pending(p)
        self.g.journal.data['intents'][p.symbol]={'operation':'cancel','request':{'order':order.ticket},
            'before':self.g.fingerprint(order,'order'),'created':self.clock()}
        self.assertAlmostEqual(self.g.exposure_risk(self.g.snapshot(),(order.ticket,)),self.g.plan_money(p)[0])

    def test_manual_position_without_sl_names_ticket_and_retains_other_risks(self):
        p=self.plan();order=self.api.add_pending(p,magic=0);position=self.api.add_position('XAUUSDm',magic=0,sl=0,tp=0)
        ledger=self.g.reservation_ledger(self.g.snapshot());reason=self.g.reservation_reason(ledger)
        self.assertEqual({r['ticket'] for r in ledger['rows']},{order.ticket,position.ticket})
        self.assertGreater(ledger['reserved_usd'],ledger['cap_usd'])
        self.assertIn(str(position.ticket),reason);self.assertIn('manual/externa XAUUSDm',reason);self.assertIn('sin SL',reason)
        self.assertFalse(self.api.sent)

    def test_stop_limit_manual_order_uses_real_limit_execution_price(self):
        for side,typ in ((1,6),(-1,7)):
            with self.subTest(side=side):
                self.api.orders.clear();p=self.plan(side=side);order=self.api.add_pending(p,magic=0)
                order.type=typ;order.price_stoplimit=p.entry;order.price_open=p.entry+side*100
                self.assertAlmostEqual(self.g.exposure_risk(self.g.snapshot()),self.g.plan_money(p)[0])
                self.assertEqual(self.g.reservation_ledger(self.g.snapshot())['rows'][0]['entry'],p.entry)
                self.assertFalse(self.api.sent)

    def test_inconsistent_symbol_cannot_recover_a_fictitious_low_reservation(self):
        p,_,intent=self.old_cancel();intent['before']['symbol']='XAUUSDm'
        ledger=self.g.reservation_ledger(self.g.snapshot())
        self.assertEqual(ledger['available_usd'],0);self.assertFalse(ledger['risk_known'])

    def test_partial_visible_open_does_not_erase_unseen_volume_reservation(self):
        p=self.plan();order=self.api.add_pending(p);order.volume_current=.005
        self.g.journal.data['intents'][p.symbol]={'operation':'open','order':order.ticket,
            'risk':self.g.plan_money(p)[0],'margin':1,
            'request':{'type':2,'price':p.entry,'sl':p.sl,'volume':.01,'comment':'rewritten'}}
        ledger=self.g.reservation_ledger(self.g.snapshot())
        self.assertAlmostEqual(ledger['reserved_usd'],self.g.plan_money(p)[0])
        self.assertAlmostEqual(ledger['future_margin_usd'],1)

    def test_reconcile_partial_visibility_keeps_the_full_commitment(self):
        p=self.plan();self.g.send_immediate_plan(p);order=self.api.orders[0];order.volume_current=.005
        self.g.reconcile(self.g.snapshot())
        self.assertIn(p.symbol,self.g.journal.data['intents'])
        self.assertAlmostEqual(self.g.exposure_risk(self.g.snapshot()),self.g.journal.data['intents'][p.symbol]['risk'])

    def test_terminal_fill_history_resolves_partial_execution_with_visible_position(self):
        p=self.plan();self.g.send_immediate_plan(p);order=self.api.orders[0];order.volume_current=.005
        self.api.fill_order(order);self.g.reconcile(self.g.snapshot())
        self.assertNotIn(p.symbol,self.g.journal.data['intents'])
        self.assertEqual(len(self.api.positions),1)

    def test_no_sl_original_order_is_not_freed_by_uncertain_new_sl(self):
        p,_,intent=self.old_cancel();intent['operation']='modify_order';intent['before']['sl']=0
        intent['request'].update(price=p.entry,sl=p.sl,tp=p.tp)
        ledger=self.g.reservation_ledger(self.g.snapshot())
        self.assertFalse(ledger['risk_known']);self.assertEqual(ledger['available_usd'],0)

    def test_snapshot_and_budget_readout_cannot_mutate_journal_or_broker(self):
        self.old_cancel();snap=self.g.snapshot();before=copy.deepcopy(self.g.journal.data)
        self.g.reservation_ledger(snap);self.g.reserved_pending_margin(snap)
        self.assertEqual(before,self.g.journal.data);self.assertFalse(self.api.sent)


class StartupReservation151Tests(PendingCase,unittest.TestCase):
    def setUp(self):
        super().setUp();self.cfg=load_config(DEFAULT);self.g.cfg=self.cfg
        self.e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(self.e.close)

    def test_old_cancel_without_money_does_not_lock_gold_at_startup(self):
        self.cfg['risk']['portfolio_money_cap']=5
        p=self.plan();order=self.api.add_pending(p);before=self.g.fingerprint(order,'order');self.api.orders.clear()
        self.g.journal.data['intents'][p.symbol]={'operation':'cancel','request':{'order':order.ticket},
            'created':self.clock(),'before':before}
        view=self.e.step()
        self.assertTrue(any(r['symbol']=='XAUUSDm' for r in self.api.sent))
        self.assertFalse(any(r['symbol']=='BTCUSDm' for r in self.api.sent))
        self.assertIn('BTCUSDm',view['unconfirmed']);self.assertTrue(view['portfolio_risk']['rows'])

    def test_default_empty_book_sends_btc_and_gold_and_exports_ledger(self):
        view=self.e.step()
        self.assertEqual({r['symbol'] for r in self.api.sent},{'BTCUSDm','XAUUSDm'})
        self.assertEqual(len(self.api.orders),2)
        self.assertEqual(view['reserved_risk'],view['portfolio_risk']['reserved_usd'])
        self.assertEqual(view['portfolio_risk']['pending_orders'],2)
        export=self.e.diagnostic_snapshot();json.dumps(export,allow_nan=False)
        self.assertEqual(export['diagnostic']['version'],2)

    def test_allocation_budget_exhaustion_is_not_waiting_for_send(self):
        position=self.api.add_position('XAUUSDm',magic=0,sl=0,tp=0)
        view=self.e.step()
        self.assertFalse(self.api.sent)
        for symbol in ('BTCUSDm','XAUUSDm'):
            self.assertTrue(self.e.candidates[symbol])
            self.assertEqual(view['status'][symbol]['state'],'BLOQUEO DE RIESGO')
            self.assertIn(str(position.ticket),view['status'][symbol]['detail'])
            self.assertIn('sin SL',view['status'][symbol]['detail'])

    def test_assistant_gets_current_per_ticket_risk_explanation(self):
        position=self.api.add_position('XAUUSDm',magic=0,sl=0,tp=0);view=self.e.step()
        state=AkiraAssistant.compact(view)
        self.assertIn('portfolio_risk',state)
        self.assertEqual(state['portfolio_risk']['rows'][0]['ticket'],position.ticket)


if __name__=='__main__':unittest.main()
