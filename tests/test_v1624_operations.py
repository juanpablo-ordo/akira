"""Observed UI confusion and premature exits, using complete broker evidence."""
import copy,json,unittest
from dataclasses import replace
from unittest.mock import patch
from types import SimpleNamespace as NS
import desktop
from engine import Engine
from execution import OWN_PENDING,Journal,DEAL
from strategy import Bar
from runner import runner_exit
from settings import DEFAULT,load_config
from operation_verifier import verification
from position_events import summarize_closure
from notification_center import NotificationCenter
from tests.fixtures import PendingCase
from tests import test_v1621_startup as ui_fixture

class ExitsTests(PendingCase,unittest.TestCase):
    def setUp(self):
        super().setUp();self.e=Engine(self.g,self.cfg,self.g.log);self.e.warmup();self.addCleanup(self.e.close)
    def position(self,symbol='BTCUSDm',side=1):
        p=self.plan(symbol,side);p=replace(p,bar_time=int(self.clock())-7200)
        pos=self.api.add_position(symbol,0 if side==1 else 1,entry=p.entry,sl=p.sl,tp=p.tp,magic=OWN_PENDING)
        self.api.record_deal(pos,0,pos.volume);self.g.register_position(pos,p.to_dict())
        return p,pos
    def broken_frame(self,p,entry_time):
        f=self.e.planner.caches[p.symbol].frames['M15'];base=p.entry;side=p.side
        bars=tuple(Bar(int(entry_time)-3600+i*900,base,base+2,base-2,base+side*(1 if i<3 else -3),100) for i in range(4))
        return replace(f,bars=bars,atr=10)
    def close(self,reason=3):
        p,pos=self.position();self.clock.advance(2)
        self.api.set_quote(p.symbol,p.entry-7,fill=False);self.api.deals[0].commission=-.03
        self.g.close_runner(pos,'Ruptura M15 posterior a la activación');self.g.reconcile(self.g.snapshot())
        self.api.deals[-1].reason=reason
        self.g.closure_monitor.poll()
        return p,pos
    def test_old_m15_candle_cannot_close_a_new_pending_fill_for_either_asset_and_side(self):
        for symbol in ('BTCUSDm','XAUUSDm'):
            for side in (1,-1):
                with self.subTest(symbol=symbol,side=side):
                    p,pos=self.position(symbol,side);entered=self.clock();f=self.broken_frame(p,entered)
                    self.e.planner.caches[symbol].frames['M15']=f
                    self.clock.advance(61)
                    for s in self.cfg['symbols']:self.api.set_quote(s,self.api.ticks[s].bid,fill=False)
                    before=len(self.api.sent);self.e.positions.step(self.g.snapshot())
                    self.assertIn(pos,self.api.positions);self.assertEqual(len(self.api.sent),before)
                    self.assertEqual(runner_exit(p.to_dict(),{'M15':f},side,-.1,self.cfg,entry_time=entered,now=self.clock()),'')
                    self.api.positions.remove(pos)
    def test_new_closed_m15_can_exit_a_genuinely_broken_structure(self):
        p,pos=self.position();entered=self.clock();f=self.broken_frame(p,entered)
        shifted=replace(f,bars=tuple(replace(b,time=b.time+2700) for b in f.bars))
        direct={**p.to_dict(),'lane':'RUNNER','signal_timeframe':'M15'}
        self.assertIn('rompió',runner_exit(direct,{'M15':shifted},1,-.1,self.cfg,entry_time=entered,now=entered+2700))
        self.assertEqual(runner_exit(p.to_dict(),{'M15':shifted},1,-.1,self.cfg,entry_time=entered,now=entered+2700),'')
    def test_forming_m15_is_not_exit_evidence(self):
        p,pos=self.position();entered=self.clock();f=self.broken_frame(p,entered)
        shifted=replace(f,bars=tuple(replace(b,time=b.time+2700) for b in f.bars))
        self.assertEqual(runner_exit(p.to_dict(),{'M15':shifted},1,-.1,self.cfg,entry_time=entered,now=entered+2690),'')
    def test_post_entry_rule_never_removes_the_broker_stop(self):
        p,pos=self.position();f=self.broken_frame(p,self.clock());self.e.planner.caches[p.symbol].frames['M15']=f
        self.clock.advance(61);self.api.set_quote(p.symbol,p.entry-.1,fill=False);self.e.positions.step(self.g.snapshot())
        self.assertEqual(pos.sl,p.sl);self.assertEqual(pos.tp,p.tp)
    def test_pre_entry_pivot_cannot_tighten_runner_stop_even_after_a_large_gain(self):
        p,pos=self.position();entered=self.clock();f=self.e.planner.caches[p.symbol].frames['M15']
        self.e.planner.caches[p.symbol].frames['M15']=replace(f,atr=10,lows=((p.entry+150,int(entered)-100),))
        self.clock.advance(70);self.api.set_quote(p.symbol,p.entry+230,fill=False)
        with patch('position_manager.runner_exit',return_value=''):
            self.e.positions.step(self.g.snapshot())
        self.assertEqual(pos.sl,p.sl);self.assertFalse(self.api.sent)
    def test_ten_cent_loss_is_confirmed_with_costs_and_decision_reason(self):
        p,pos=self.close();row=self.g.closure_monitor.rows()[0]
        self.assertAlmostEqual(row['net'],-.10);self.assertEqual(row['initiator'],'AKIRA')
        self.assertIn('Ruptura M15',row['cause']);self.assertEqual(row['currency'],'USD')
        self.assertEqual(row['state'],'CONFIRMADO MT5');self.assertTrue(row['deal_ids'])
        self.assertEqual(Journal(self.root/'state.json').data['positions'][str(pos.ticket)]['closure']['id'],row['id'])
    def test_broker_sl_is_not_mislabeled_as_an_ai_decision(self):
        self.close(reason=4);row=self.g.closure_monitor.rows()[0]
        self.assertEqual(row['initiator'],'MT5');self.assertIn('Stop Loss',row['cause'])
        self.assertNotIn('AKIRA:',row['cause'])
    def test_python_close_matches_its_receipt_even_if_broker_labels_terminal(self):
        self.close(reason=0);row=self.g.closure_monitor.rows()[0]
        self.assertEqual(row['initiator'],'AKIRA');self.assertTrue(row['request_matched_to_exit'])
        self.assertIn('Ruptura M15',row['cause'])
    def test_unrelated_ea_exit_does_not_borrow_a_saved_ai_decision(self):
        p,pos=self.position();self.api.record_deal(pos,1,pos.volume,-.1);self.api.deals[-1].reason=3
        meta=self.g.journal.data['positions'][str(pos.ticket)]
        meta['management_events']=[{'operation':'close','time':self.clock(),'reason':'Una solicitud distinta','deal':999999}]
        row=summarize_closure(pos.ticket,meta,self.api.deals)
        self.assertEqual(row['initiator'],'MT5');self.assertFalse(row['request_matched_to_exit'])
        self.assertNotIn('AKIRA:',row['cause'])
    def test_tp_and_mobile_causes_remain_distinct(self):
        p,pos=self.position();self.api.record_deal(pos,1,pos.volume,3)
        for reason,word in ((1,'móvil'),(5,'Take Profit'),(6,'Stop Out')):
            self.api.deals[-1].reason=reason
            self.assertIn(word,summarize_closure(pos.ticket,self.g.journal.data['positions'][str(pos.ticket)],self.api.deals)['cause'])
    def test_disappearance_without_exit_deals_is_not_a_confirmed_loss(self):
        p,pos=self.position();self.api.positions.remove(pos);self.g.reconcile(self.g.snapshot())
        self.g.closure_monitor.poll();self.assertFalse(self.g.closure_monitor.rows())
        self.assertIn('Esperando evidencia',self.g.journal.data['positions'][str(pos.ticket)]['closure_history_state'])
    def test_partial_close_is_not_reported_as_full_close(self):
        p,pos=self.position();self.api.partial_close=True;self.g.close_runner(pos,'Cierre parcial de prueba');self.g.reconcile(self.g.snapshot())
        self.g.closure_monitor.poll();self.assertTrue(self.api.positions);self.assertFalse(self.g.closure_monitor.rows())
    def test_delayed_ack_does_not_create_a_confirmed_closure(self):
        p,pos=self.position();self.api.no_effect=True;self.g.close_runner(pos,'Decisión sin acuse')
        self.g.reconcile(self.g.snapshot());self.g.closure_monitor.poll()
        self.assertTrue(self.api.positions);self.assertFalse(self.g.closure_monitor.rows());self.assertTrue(self.g.journal.data['intents'])
    def test_failed_history_is_retried_without_new_order_requests(self):
        p,pos=self.position();self.api.positions.remove(pos);self.g.reconcile(self.g.snapshot());self.api.fail_history=True
        before=len(self.api.sent);self.g.closure_monitor.poll();self.assertEqual(len(self.api.sent),before)
        self.assertFalse(self.g.closure_monitor.rows());self.assertIn('Esperando',self.g.journal.data['positions'][str(pos.ticket)]['closure_history_state'])
    def test_only_one_history_lookup_per_cycle_and_no_duplicate_confirmations(self):
        self.close();before=len(self.g.log.recent_events)
        with patch.object(self.api,'history_deals_get',wraps=self.api.history_deals_get) as calls:
            self.g.closure_monitor.poll();calls.assert_not_called()
        self.assertEqual(len(self.g.log.recent_events),before)

class LiveUIOperationsTests(unittest.TestCase):
    setUp=ui_fixture.StartupUITests.setUp
    def snapshot(self):
        e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(e.close);return e.step()
    def test_explicit_visible_amounts_are_preserved_without_timer(self):
        self.app.cfg['desktop']['privacy']=False
        view=self.snapshot();self.app.view=view;self.app.render(view)
        self.assertIn('USD',self.app.metrics['balance'].options['text'])
        with patch.object(self.window,'after',wraps=self.window.after) as timers:
            self.app.toggle_account_privacy();self.assertTrue(load_config(self.root/'akira_config.json')['desktop']['privacy'])
            self.app.toggle_account_privacy();self.assertFalse(load_config(self.root/'akira_config.json')['desktop']['privacy'])
            self.assertFalse(any(call.args[0]==15000 for call in timers.call_args_list))
        self.assertIn('USD',self.app.metrics['balance'].options['text'])
    def test_hidden_preference_survives_migration_and_new_install_is_private(self):
        old=copy.deepcopy(DEFAULT);old['desktop'].pop('visibility_preference_saved');old['desktop']['privacy']=True
        self.assertTrue(load_config(old)['desktop']['privacy']);self.assertTrue(load_config({})['desktop']['privacy'])
        new=load_config(old);new['desktop']['privacy']=True;self.assertTrue(load_config(new)['desktop']['privacy'])
    def test_confirmed_pending_is_first_and_cycle_is_visible(self):
        view=self.snapshot();self.app.render(view);panel=self.app.panels['BTCUSDm']
        self.assertTrue(panel.rows[0]['confirmed']);self.assertIn('ciclo',panel.verify_label.options['text'])
        self.assertIn('COBERTURA',panel.verify_label.options['text'])
    def test_missing_statistical_study_is_not_presented_as_total_verification(self):
        view=self.snapshot();view['symbols']['BTCUSDm']['analysis_inflight']=False;check=verification(view,'BTCUSDm')
        self.assertLess(check['progress'],100);self.assertTrue(check['missing']);self.assertEqual(check['activity'],'REVISIÓN ACTIVA')
    def test_unknown_external_gold_risk_blocks_both_symbols_and_preserves_manual_ticket(self):
        p=self.api.add_position('XAUUSDm',magic=0,sl=0);view=self.snapshot();self.app.render(view)
        for symbol in ('BTCUSDm','XAUUSDm'):
            check=verification(view,symbol);self.assertIn('XAUUSDm',check['execution_block'])
            self.assertTrue(any(s['state']=='BLOQUEADO' for s in check['stages']))
        self.assertEqual(p.sl,0);self.assertIn('riesgo sin calcular',self.app.notice_center.list('entradas bloqueadas')[0]['body'])
    def test_stale_motor_is_visible_and_not_classed_as_current_quote(self):
        view=self.snapshot();view['ui_age_seconds']=12
        check=verification(view,'BTCUSDm');self.assertEqual(check['activity'],'SIN ACTUALIZACIÓN DEL MOTOR')
        self.assertEqual(check['stages'][0]['state'],'DESACTUALIZADA')
    def test_old_broker_receipt_and_old_tick_cannot_approve_a_new_candidate(self):
        view=self.snapshot();now=view['updated'];view['verification_receipts']={'old':{'symbol':'BTCUSDm','at':now-3600,'risk_passed':True,'broker_checked':True}}
        view['orders']=[];view['symbols']['BTCUSDm']['quote_time']=now-60
        check=verification(view,'BTCUSDm');self.assertEqual(check['stages'][0]['state'],'DESACTUALIZADA')
        self.assertNotEqual(next(s['state'] for s in check['stages'] if s['name']=='Restricciones MT5 / Exness'),'COMPROBADO')
    def test_gold_verification_does_not_borrow_bitcoin_derivatives(self):
        view=self.snapshot();view['research']['sources']={'coinglass:BTC':{'fresh':True,'usable':True},'venue:Binance':{'fresh':True,'usable':True}}
        result=verification(view,'XAUUSDm')
        self.assertEqual(next(s['state'] for s in result['stages'] if s['name']=='Exchanges y derivados'),'SIN APORTE')
    def test_closure_is_notified_once_even_when_muted_and_after_restart(self):
        view=self.snapshot();view['position_closures']=[{'id':'CLOSE:123:9:12','state':'CONFIRMADO MT5','symbol':'BTCUSDm','side':1,'ticket':9,'net':-.1,'currency':'USD','cause':'Stop Loss ejecutado por MT5','initiator':'MT5'}]
        self.app.cfg['desktop']['notifications']=False;self.app.view=view
        self.app.maybe_notify(view);self.app.maybe_notify(view)
        self.assertEqual(len(self.app.notice_center.list('operación cerrada')),1)
        self.assertIn('-0.10',self.app.notice_center.list('operación cerrada')[0]['body'])
        self.app._closure_notifications_seen=set();self.app.maybe_notify(view)
        self.assertEqual(len(NotificationCenter(self.root).list('operación cerrada')),1)

if __name__=='__main__':unittest.main()
