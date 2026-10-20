"""Synthetic causal replays only; these checks do not measure profitability."""
import copy
import tempfile
import unittest
from concurrent.futures import Future
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

from entry_momentum import adverse_impulse
from trade_quality_gate import evaluate, owned_outcomes
from tests.fixtures import PendingCase
from tests import test_studio_rev8_assets as rev8


def impulse_frames(now, entry=100, side=-1, scale=1):
    # Mirrors long/short and rescales the same shape across instruments.
    def price(x):return entry-side*x*scale
    def bar(stamp,o,c):
        a,b=price(o),price(c)
        return NS(time=stamp,open=a,close=b,high=max(a,b)+.2*scale,low=min(a,b)-.2*scale)
    return {'M1':NS(atr=2*scale,bars=[bar(now-120,-6,-3.5),bar(now-60,-3.5,-.2)]),
        'M15':NS(atr=10*scale,trend=side*.5,bars=[bar(now-900,.1,-.2)]),
        'H1':NS(trend=side*.5,bars=[bar(now-3600,.1,-.2)])}


class MomentumReplayTests(unittest.TestCase):
    def setUp(self):
        self.now=1800000000
        self.plan=NS(symbol='BTCUSDm',key='SYNTHETIC_LIMIT',kind='LIMIT',lane='PENDING',side=-1,
            entry=100,sl=110,tp=80,horizon_atr=10)
        self.frames=impulse_frames(self.now)
    def test_mirrored_bitcoin_and_gold_limits_suspend_on_two_strong_closed_bars(self):
        for symbol,entry,scale in [('BTCUSDm',70000,20),('XAUUSDm',3000,.5)]:
            for side in (-1,1):
                with self.subTest(symbol=symbol,side=side):
                    p=NS(**{**vars(self.plan),'symbol':symbol,'entry':entry,'sl':entry-side*10*scale,'tp':entry+side*20*scale,'side':side})
                    result=adverse_impulse(p,impulse_frames(self.now,entry,side,scale),self.now)
                    self.assertIsNotNone(result);self.assertEqual(result['closed_bar_time'],self.now-60)
    def test_entry_gate_uses_the_same_impulse_without_changing_levels(self):
        before=copy.deepcopy(vars(self.plan))
        result=evaluate(self.plan,self.frames,[],self.now)
        self.assertFalse(result['allowed']);self.assertIn('impulso fuerte',result['reason'])
        self.assertEqual(vars(self.plan),before)
    def test_future_candle_cannot_supply_the_second_confirmation(self):
        self.frames['M1'].bars[-1].time=self.now
        self.assertIsNone(adverse_impulse(self.plan,self.frames,self.now))
    def test_stale_gap_and_invalid_ohlc_cannot_invalidate_a_zone(self):
        for change in ('stale','gap','invalid'):
            frames=copy.deepcopy(self.frames)
            if change=='stale':
                for b in frames['M1'].bars:b.time-=180
            elif change=='gap':frames['M1'].bars[0].time-=60
            else:frames['M1'].bars[-1].high=1
            with self.subTest(change=change):self.assertIsNone(adverse_impulse(self.plan,frames,self.now))
    def test_one_bar_and_weak_opposite_body_preserve_a_valid_zone(self):
        self.frames['M1'].bars[0].close=self.frames['M1'].bars[0].open+.1
        self.assertIsNone(adverse_impulse(self.plan,self.frames,self.now))
        self.frames['M1'].bars=self.frames['M1'].bars[-1:]
        self.assertIsNone(adverse_impulse(self.plan,self.frames,self.now))
    def test_distant_entry_and_stop_entry_are_not_treated_as_fading_limits(self):
        self.plan.entry=120;self.plan.sl=130
        self.assertIsNone(adverse_impulse(self.plan,self.frames,self.now))
        self.plan.entry=100;self.plan.sl=110;self.plan.kind='STOP'
        self.assertIsNone(adverse_impulse(self.plan,self.frames,self.now))
    def test_rejection_already_observed_by_live_quote_clears_the_impulse(self):
        self.assertIsNone(adverse_impulse(self.plan,self.frames,self.now,NS(bid=98,ask=98.1)))
    def test_two_losses_require_a_recovery_body_even_with_positive_emas(self):
        self.plan.side=1;self.plan.sl=90;self.plan.tp=120
        self.frames.pop('M1');self.frames['M15'].trend=self.frames['H1'].trend=.5
        bar=self.frames['M15'].bars[-1];bar.open=100;bar.close=99.5
        losses=[{'position_id':i,'symbol':'BTCUSDm','side':1,'pnl':-1,'closed_at':self.now-t} for i,t in [(1,2100),(2,1000)]]
        result=evaluate(self.plan,self.frames,losses,self.now)
        self.assertFalse(result['allowed']);self.assertIn('recuperación',result['reason'])
        bar.close=103;bar.high=104
        self.assertTrue(evaluate(self.plan,self.frames,losses,self.now)['allowed'])


class ActorMomentumTests(PendingCase,unittest.TestCase):
    def setUp(self):
        super().setUp()
        from engine import Engine
        self.engine=Engine(self.g,self.cfg,self.g.log);self.addCleanup(self.engine.close)
        self.engine.warmup()
    def scenario(self):
        p=replace(self.plan(side=-1),bar_time=int(self.clock()-900))
        frames=impulse_frames(self.clock(),p.entry,-1,10)
        self.engine.planner.caches[p.symbol].frames=frames
        tick=self.api.ticks[p.symbol];tick.bid=p.entry-2;tick.ask=tick.bid+.1
        return p
    def test_actual_send_is_blocked_before_any_broker_request(self):
        from execution import Blocked
        p=self.scenario();before=len(self.api.sent)
        with self.assertRaisesRegex(Blocked,'impulso fuerte'):self.g.send_immediate_plan(p)
        self.assertEqual(len(self.api.sent),before)
    def test_pending_edit_is_checked_again_before_its_broker_request(self):
        from execution import Blocked
        p=self.scenario();order=self.api.add_pending(p)
        self.g.journal.data['orders'][str(order.ticket)]={'plan':p.to_dict(),'created':self.clock()-600}
        before=len(self.api.sent)
        with self.assertRaisesRegex(Blocked,'impulso fuerte'):self.g.modify_pending(order,replace(p,entry=p.entry+1),'synthetic edit')
        self.assertEqual(len(self.api.sent),before)
        self.assertEqual(order.sl,p.sl);self.assertEqual(order.tp,p.tp)
    def test_equal_scenario_keys_on_two_assets_keep_separate_entry_evidence(self):
        a=self.plan(symbol='BTCUSDm',key='SAME_KEY');b=self.plan(symbol='XAUUSDm',key='SAME_KEY')
        self.engine.evaluate_entry_quality(a);self.engine.evaluate_entry_quality(b)
        self.assertEqual({row['symbol'] for row in self.engine.entry_checks.values()},{a.symbol,b.symbol})
    def test_resting_own_limit_is_cancelled_only_after_two_fresh_quotes(self):
        p=self.scenario();order=self.api.add_pending(p)
        self.g.journal.data['orders'][str(order.ticket)]={'plan':p.to_dict(),'created':self.clock()-600}
        manual=copy.copy(order);manual.ticket=888;manual.magic=0;self.api.orders.append(manual)
        self.engine.lifecycle_action(p.symbol,[p],self.g.quote(p.symbol))
        self.assertTrue(any(o.ticket==order.ticket for o in self.api.orders))
        self.clock.advance(1);tick=self.api.ticks[p.symbol];tick.time=self.clock();tick.time_msc=int(self.clock()*1000)
        self.engine.lifecycle_action(p.symbol,[p],self.g.quote(p.symbol))
        self.assertFalse(any(o.ticket==order.ticket for o in self.api.orders))
        self.assertTrue(any(o.ticket==888 for o in self.api.orders))


class ComparableLearningTests(PendingCase,unittest.TestCase):
    def setUp(self):
        super().setUp()
        from learning import PendingLearner
        self.learner=PendingLearner(self.g)
        from strategy_choice import tag
        self.p=tag(self.plan(),self.cfg)
    def record(self,pid=1,pnl=-2,**changes):
        from trade_quality_gate import family
        row={'position_id':pid,'symbol':self.p.symbol,'side':self.p.side,'pnl':pnl,'closed_at':self.clock(),
            'deal_ids':[pid*2,pid*2+1],'strategy_id':family(self.p),'strategy_version':self.p.strategy_version,
            'selector_id':self.p.selector_id,'selector_version':self.p.selector_version,'execution_build':self.p.execution_build}
        row.update(changes);self.learner.records[str(pid)]=row
    def test_legacy_other_family_version_and_build_are_excluded_only_from_ranking(self):
        for pid,fields in enumerate([{'strategy_id':'SIN_TESIS_REGISTRADA'},{'strategy_id':'PENDIENTE_RUPTURA'},
                {'strategy_version':1},{'selector_version':1},{'execution_build':'OLD_BUILD'}],1):self.record(pid,**fields)
        self.record(6,pnl=1)
        self.assertEqual(self.learner.metrics(self.p.symbol)['samples'],6)
        scoped=self.learner.metrics(self.p.symbol,self.p)
        self.assertEqual(scoped['samples'],1);self.assertEqual(scoped['expectancy'],1)
        self.assertEqual(scoped['excluded_samples'],5)
        self.assertEqual(len(owned_outcomes(self.g)),6)
    def test_comparable_samples_are_selected_before_the_200_trade_window(self):
        self.record(1,pnl=1,closed_at=self.clock()-1000)
        for pid in range(2,205):self.record(pid,strategy_version=1)
        self.assertEqual(self.learner.metrics(self.p.symbol,self.p)['samples'],1)
    def test_new_confirmed_close_retains_original_provenance_and_actual_fees(self):
        from execution import OWN_PENDING
        p=self.api.add_position(magic=OWN_PENDING);entry=self.api.record_deal(p,0,p.volume);entry.commission=-.5
        self.api.record_deal(p,1,p.volume,2);self.api.positions.remove(p)
        self.g.journal.data['positions'][str(p.identifier)]={'plan':self.p.to_dict()}
        self.learner.update();row=next(iter(self.learner.records.values()))
        self.assertEqual(row['execution_build'],self.p.execution_build);self.assertEqual(row['strategy_version'],2)
        self.assertAlmostEqual(self.learner.metrics(self.p.symbol,self.p)['expectancy'],1.5)
    def test_daily_models_do_not_reuse_archived_champions_or_mix_families(self):
        from evolution import DailyLearner
        daily=DailyLearner(self.root)
        daily.state={'champions':{'BTCUSDm':{'promoted':True,'weights':[9]}}}
        self.record(1);self.record(2,strategy_id='PENDIENTE_RUPTURA');self.record(3,execution_build='OLD')
        out=daily.run_by_family(list(self.learner.records.values()),[123,'demo'],self.p.selector_id,now=self.clock())
        self.assertEqual(out['excluded_campaigns'],1);self.assertFalse(out['family_champions'])
        self.assertEqual(set(out['family_reports']['BTCUSDm']),{'PENDIENTE_RETROCESO','PENDIENTE_RUPTURA'})
        self.assertTrue(daily.state['champions']['BTCUSDm']['promoted'])


class QueueOwnershipTests(unittest.TestCase):
    setUp=rev8.AssetReviewTests.setUp
    plan=rev8.AssetReviewTests.plan
    restrict_to_reviews=rev8.AssetReviewTests.restrict_to_reviews
    def test_running_summary_is_included_in_a_new_individual_queue_budget(self):
        self.restrict_to_reviews();self.worker.tick()
        p=self.plan('XAUUSDm','waiting-for-summary')
        self.worker.request_pending_reviews([p],{'symbols':{}})
        from pending_verification import identity
        row=self.worker.pending_reviews[identity(p)]
        self.assertGreaterEqual(row['queue_budget_seconds'],300)
        self.now+=110
        self.assertEqual(self.worker.expire_pending_reviews(),[])
        self.pool.calls[0][0].set_exception(TimeoutError('synthetic summary limit'))
        self.worker.tick()
        self.assertEqual(row['state'],'RUNNING')
    def test_waiting_cannot_renew_itself_forever_after_chat_deferral(self):
        p=self.plan('XAUUSDm','bounded');self.worker.pool=rev8.ControlledPool()
        self.worker.request_pending_reviews([p],{'symbols':{}})
        from pending_verification import identity
        row=self.worker.pending_reviews[identity(p)]
        row.update(started=self.now+80,phase='REVIEWING')
        self.now+=row['queue_budget_seconds']+1
        self.assertEqual(self.worker.expire_pending_reviews(),[identity(p)])
    def test_no_successful_asset_cannot_be_presented_as_a_completed_combined_review(self):
        self.worker.sources['local_ai:XAUUSDm']={'data':{},'updated':0,'error':'TimeoutError'}
        self.worker._merge_local_ai_sources();combined=self.worker.read()['sources']['local_ai']
        self.assertFalse(combined['usable']);self.assertNotIn('una revisión completada',combined['detail'])
    def test_after_waiting_the_review_receives_fresh_indicators_and_new_fingerprint(self):
        from pending_verification import identity,fingerprint
        self.worker.pool=rev8.ControlledPool();p=self.plan('XAUUSDm','fresh')
        old={'symbols':{'XAUUSDm':{'quote_time':self.now,'frames':{'M15':{'rsi':70}}}}}
        self.worker.request_pending_reviews([p],old)
        latest={'updated':self.now,'symbols':{'XAUUSDm':{'quote_time':self.now,'frames':{'M15':{'rsi':30}}}}}
        self.worker.submit(latest);self.worker._pending_tick(self.now,{})
        request=self.worker.pending_batch[0]
        self.assertEqual(request['snapshot']['symbols']['XAUUSDm']['frames']['M15']['rsi'],30)
        self.assertNotEqual(request['fingerprint'],fingerprint(old,p))
        self.assertEqual(request['fingerprint'],self.worker.pending_reviews[identity(p)]['fingerprint'])
    def test_a_closed_gold_session_cannot_receive_an_old_queued_approval(self):
        from pending_verification import identity
        self.worker.pool=rev8.ControlledPool();p=self.plan('XAUUSDm','closed-while-waiting')
        self.worker.request_pending_reviews([p],{'symbols':{}})
        self.worker.submit({'symbols':{'XAUUSDm':{'quote_time':self.now}},'markets':{'XAUUSDm':{'scheduled_closed':True}}})
        self.worker._pending_tick(self.now,{})
        self.assertEqual(self.worker.pending_reviews[identity(p)]['state'],'ERROR')
        self.assertIsNone(self.worker.pending_future)


class DecisionExplanationTests(unittest.TestCase):
    def status(self,audit,checks):
        from decision_status import decision_status
        return decision_status('XAUUSDm',[],audit,[],checks,[],{},
            {'state':'ESPERANDO ENVÍO','detail':'Primera zona demasiado cara'},2)
    def test_affordable_btc_quality_wait_is_not_hidden_by_an_expensive_first_candidate(self):
        result=self.status([], [{'risk_usd':5,'allowed':False,'funding':{'minimum_risk_usd':5}},
            {'risk_usd':1.5,'allowed':False,'quality_reason':'Esperando vela M15 completa'}])
        self.assertEqual(result['minimum_evaluated_risk_usd'],1.5)
        self.assertEqual(result['budget_compatible_checks'],1);self.assertIn('vela M15',result['reason'])
    def test_gold_explains_the_budget_without_changing_risk_or_shortening_the_stop(self):
        audit=[{'risk_usd':5.5},{'risk_usd':8.1}];before=copy.deepcopy(audit)
        result=self.status(audit,[])
        self.assertIn('5.50 USD',result['reason']);self.assertIn('2.00 USD',result['reason'])
        self.assertEqual(audit,before);self.assertIn('PRESUPUESTO',result['state'])


class ReviewPresentationTests(unittest.TestCase):
    def test_ui_waits_for_its_actual_bounded_queue_instead_of_expiring_at_125_seconds(self):
        from operation_health import verification_job
        pid='XAUUSDm / synthetic'
        job={'targets':[pid],'fingerprints':{pid:'abc'},'requested':1000,'deep':True}
        reports={pid:{'fingerprint':'abc'}}
        reviews={pid:{'fingerprint':'abc','state':'QUEUED','updated':1000,'queue_budget_seconds':400}}
        out=verification_job(job,reports,{},reviews,1150,True)
        self.assertEqual(out['phase'],'REVISANDO');self.assertFalse(out['authorizes_orders'])
        out=verification_job(job,reports,{},reviews,2200,True)
        self.assertEqual(out['phase'],'TIEMPO AGOTADO')
    def test_cancel_youtube_guide_does_not_open_a_file_picker(self):
        from PySide6.QtWidgets import QApplication,QDialog
        from desktop_qt import StudioWindow
        app=QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp:
            window=StudioWindow(Path(tmp),preview=True,start_actor=False)
            try:
                with patch('desktop_qt.QDialog.exec',return_value=QDialog.DialogCode.Rejected),patch('desktop_qt.QFileDialog.getOpenFileName') as picker:
                    window.import_youtube_session()
                picker.assert_not_called()
            finally:window.close();app.processEvents()


if __name__=='__main__':unittest.main()
