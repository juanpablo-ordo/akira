"""Estabilidad de pendientes y espacio de protección del runner normal."""
import copy,unittest
from dataclasses import replace
from unittest.mock import patch
from engine import Engine
from execution import Journal,OWN_RUNNER
from tests.fixtures import PendingCase
from settings import load_config


class ManagementTests(PendingCase,unittest.TestCase):
    def setUp(self):
        super().setUp();self.cfg['execution']['pending_only']=False;self.e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(self.e.close);self.e.warmup()
    def runner(self,side=1):
        p=self.plan(side=side);q=self.g.quote(p.symbol);entry=q.ask if side==1 else q.bid
        return replace(p,key='RUN:M15:'+str(side),lane='RUNNER',kind='MARKET',entry=entry,sl=entry-side*50,tp=entry+side*200,
            atr=50,horizon_atr=50,score=86,quality_score=86,bar_time=int(self.clock()//900)*900-900,signal_timeframe='M15',trigger=entry)
    def position(self,side=1):
        p=self.runner(side);self.g.send_runner(p);self.g.reconcile(self.g.snapshot())
        self.clock.advance(900);self.api.set_quote(p.symbol,p.entry+side*120,fill=False)
        return p,self.api.positions[0]
    def test_recent_abandoned_zone_waits_for_new_evidence(self):
        p=self.plan();meta={'recent_zones':[{'entry':p.entry,'horizon_atr':p.horizon_atr,'bar_time':p.bar_time,'quality_score':p.quality_score,'abandoned_at':self.clock()}]}
        self.assertIn('abandonada',self.e.pending_return_reason(meta,p,self.clock()+20))
        self.assertEqual(self.e.pending_return_reason(meta,p,self.clock()+91),'')
    def test_confirmation_does_not_combine_different_zones_or_reset_for_feed_noise(self):
        p=self.plan();a=self.e.improvement_signature('Mejora',p)
        close=replace(p,entry=p.entry+.001,sl=p.sl+.001,tp=p.tp+.001)
        far=replace(p,entry=p.entry+100,sl=p.sl+100,tp=p.tp+100)
        self.assertEqual(a,self.e.improvement_signature('Mejora',close))
        self.assertNotEqual(a,self.e.improvement_signature('Mejora',far))
        key=('BTCUSDm',1);q=self.g.quote(p.symbol);self.assertFalse(self.e.confirm(key,q,a))
        self.clock.advance(20);self.api.set_quote(p.symbol,q.bid+1,fill=False)
        self.assertFalse(self.e.confirm(key,self.g.quote(p.symbol),self.e.improvement_signature('Mejora',far)))
    def test_material_new_closed_bar_can_improve_without_waiting_full_cooldown(self):
        p=self.plan();meta={'recent_zones':[{'entry':p.entry,'bar_time':p.bar_time,'quality_score':p.quality_score,'abandoned_at':self.clock()}]}
        better=replace(p,bar_time=p.bar_time+900,quality_score=p.quality_score+4)
        self.assertEqual(self.e.pending_return_reason(meta,better,self.clock()+5),'')
        self.assertTrue(self.e.pending_return_reason(meta,replace(better,bar_time=p.bar_time),self.clock()+5))
    def test_accepted_modify_persists_abandoned_zone_across_restart(self):
        p=self.plan();self.g.send_immediate_plan(p);self.g.reconcile(self.g.snapshot());o=self.api.orders[0]
        new=replace(p,key=p.key+':new',entry=p.entry-80,sl=p.sl-80,tp=p.tp-80)
        self.clock.advance(20);self.api.set_quote(p.symbol,self.api.ticks[p.symbol].bid,fill=False)
        self.g.modify_pending(o,new,'Mejor zona');self.g.reconcile(self.g.snapshot())
        meta=Journal(self.root/'state.json').data['orders'][str(o.ticket)]
        self.assertAlmostEqual(meta['recent_zones'][-1]['entry'],p.entry,places=2)
        self.assertTrue(self.e.pending_return_reason(meta,p,self.clock()))
    def test_runner_does_not_move_sl_to_entry_without_new_m15_swing(self):
        self.cfg['management']['protect_progress']=False  # Explicit opt-out preserves pivot-only policy.
        p,pos=self.position();cache=self.e.planner.caches[p.symbol]
        cache.frames['M15']=replace(cache.frames['M15'],lows=(),highs=())
        with patch('position_manager.runner_exit',return_value=''),patch.object(self.g,'update_stop') as update:self.e.positions.step(self.g.snapshot())
        update.assert_not_called();self.assertAlmostEqual(pos.sl,p.sl,delta=.011)
        self.assertIn('falta pivote',self.g.journal.data['positions'][str(pos.ticket)]['protection_state'])
    def test_runner_never_uses_m5_fallback_to_tighten_m15_protection(self):
        self.cfg['management']['protect_progress']=False
        p,pos=self.position();self.e.planner.caches[p.symbol].frames.pop('M15')
        with patch.object(self.g,'update_stop') as update:self.e.positions.step(self.g.snapshot())
        update.assert_not_called();self.assertAlmostEqual(pos.sl,p.sl,delta=.011)
    def test_long_and_short_trail_confirmed_new_swing_with_atr_room(self):
        for side in (1,-1):
            with self.subTest(side=side):
                p,pos=self.position(side);cache=self.e.planner.caches[p.symbol];f=cache.frames['M15'];swing=p.entry+side*80
                cache.frames['M15']=replace(f,atr=50,lows=((swing,p.bar_time+900),) if side==1 else (),highs=((swing,p.bar_time+900),) if side==-1 else ())
                with patch('position_manager.runner_exit',return_value=''):self.e.positions.step(self.g.snapshot())
                self.g.reconcile(self.g.snapshot())
                self.assertAlmostEqual(pos.sl,swing-side*50*self.cfg['management']['trail_atr'],places=2)
                row=self.g.journal.data['positions'][str(pos.ticket)]
                self.assertGreaterEqual(row['max_favorable_r'],2.3)
                self.assertTrue(row['management_events']);self.assertIn('M15',row['management_events'][-1]['reason'])
                self.g.close_runner(pos,'Fin de prueba');self.g.reconcile(self.g.snapshot());self.g.closure_monitor.poll()
    def test_manual_position_is_not_tracked_or_modified(self):
        manual=self.api.add_position(magic=0);before=copy.deepcopy(self.api.sent)
        self.e.positions.step(self.g.snapshot());self.assertEqual(self.api.sent,before)
        self.assertNotIn(str(manual.ticket),self.g.journal.data['positions'])
    def test_migration_keeps_user_risk_and_observation_mode(self):
        old=copy.deepcopy(self.cfg);old['schema_version']=1501;old['mode']='observe';old['risk']['max_trade_money']=2.17
        old['management'].pop('runner_structure_only',None)
        new=load_config(old)
        self.assertEqual(new['risk'],old['risk']);self.assertEqual(new['mode'],'observe')
        self.assertTrue(new['management']['runner_structure_only']);self.assertEqual(new['schema_version'],1600)
    def test_operational_log_records_actual_broker_retcode_ticket_and_reason(self):
        p=self.plan();self.g.send_immediate_plan(p)
        event=list(self.g.log.recent_events)[-1]
        self.assertEqual(event['retcode'],10008);self.assertGreater(event['order'],0);self.assertIn('reason',event)
        self.assertEqual(event['lane'],'PENDING')
    def test_final_send_rechecks_spread_after_local_preparation_cache(self):
        p=self.plan('XAUUSDm');self.cfg['risk']['max_trade_money']=2.17;check=self.api.order_check
        def change(request):
            self.api.set_quote(p.symbol,self.api.ticks[p.symbol].bid,spread=5,fill=False)
            return check(request)
        with patch.object(self.api,'order_check',side_effect=change):
            from execution import Blocked
            with self.assertRaises(Blocked):self.g.send_immediate_plan(p)
        self.assertFalse(self.api.sent)
    def test_final_send_rechecks_manual_reservation_added_during_prepare(self):
        p=self.plan();self.cfg['risk']['portfolio_money_cap']=2.5;check=self.api.order_check
        def change(request):
            manual=self.plan('XAUUSDm');manual=replace(manual,sl=manual.entry-10,tp=manual.entry+20)
            self.api.add_pending(manual,magic=0);return check(request)
        with patch.object(self.api,'order_check',side_effect=change):
            from execution import Blocked
            with self.assertRaises(Blocked):self.g.send_immediate_plan(p)
        self.assertFalse(self.api.sent)
