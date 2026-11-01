import copy,unittest
from datetime import datetime,timezone
from types import SimpleNamespace as NS
from unittest.mock import patch,Mock
from tests.fixtures import PendingCase
from tests.fake_mt5 import FakeMT5
from execution import OWN_PENDING
from engine import Engine
from market_preparation import build_preopen_plan,preopen_text
from market_events import event_alerts
from market_calendar import xau_state
from market_state import MarketStateResolver
from execution_review import fingerprint,facts
from research import ContextWorker


def utc(s):return datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()


class ClosedHistoryMT5(FakeMT5):
    def copy_rates_from_pos(self,symbol,tf,start,count):
        if start==0:
            self.rate_calls.append((symbol,tf,start,count))
            return self.rates.get((symbol,tf),[])[-count:]
        return super().copy_rates_from_pos(symbol,tf,start,count)


class WeekendIndependence(PendingCase,unittest.TestCase):
    def setUp(self):
        super().setUp();self.clock.now=utc('2026-10-30T20:57:00Z')
        self.api=ClosedHistoryMT5(self.clock);self.g.api=self.api;self.cfg['mode']='observe'
        self.e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(self.e.close);self.e.step()
        self.position=self.api.add_position('XAUUSDm',magic=OWN_PENDING,entry=2498,sl=2490,tp=2520)
        self.g.reconcile(self.g.snapshot())
        self.clock.now=utc('2026-10-31T12:00:00Z')
        btc=FakeMT5(self.clock)
        for (symbol,tf),rows in btc.rates.items():
            if symbol.startswith('BTC'):self.api.rates[symbol,tf]=rows
        self.api.set_quote('BTCUSDm',60000,fill=False)
        self.e.initialized=False;self.e.deep_initialized=False
        for cache in self.e.planner.caches.values():cache.analysis_executor=None
    def prepare(self):
        for _ in range(4):view=self.e.step()
        return view
    def test_gold_position_and_weekend_do_not_stop_bitcoin_evaluation(self):
        view=self.prepare()
        self.assertEqual(view['markets']['XAUUSDm']['session'],'CLOSED')
        self.assertEqual(view['markets']['BTCUSDm']['session'],'OPEN')
        self.assertEqual(view['status']['BTCUSDm']['state'],'OBSERVAR')
        self.assertEqual(view['symbols']['BTCUSDm']['last_analysis_at'],self.clock())
        self.assertIn(self.position,self.api.positions);self.assertFalse(self.api.sent)
    def test_closed_start_fetches_structural_history_instead_of_skipping_it(self):
        for tf in ('H1','H4','D1','W1'):self.e.planner.caches['XAUUSDm'].frames.pop(tf,None)
        view=self.prepare();plan=view['symbols']['XAUUSDm']['preopen_plan']
        self.assertIn('H1',plan['evidence']);self.assertIn('H4',plan['evidence']);self.assertIn('D1',plan['evidence'])
        self.assertTrue(plan['weekly']);self.assertFalse(plan['execution_allowed']);self.assertTrue(plan['requires_revalidation'])
        self.assertEqual([s['side'] for s in plan['scenarios']],['BUY','SELL','WAIT'])
        self.assertIn('Semana observada',preopen_text(plan));self.assertTrue(plan['positions'])
        self.assertIn('XAUUSDm',self.g.journal.data['preopen_plans'])
        before=len([r for r in self.api.rate_calls if r[0]=='XAUUSDm'])
        for _ in range(10):self.e.step()
        self.assertEqual(before,len([r for r in self.api.rate_calls if r[0]=='XAUUSDm']))
    def test_closed_gold_does_not_prevent_bitcoin_execution_path(self):
        self.prepare();self.cfg['mode']='trade'
        with patch.object(self.e,'execute_pending_map') as execute,patch.object(self.e,'try_runner') as runner:
            self.e.step()
        self.assertEqual([r.args[0] for r in execute.call_args_list],['BTCUSDm'])
        self.assertEqual([r.args[0] for r in runner.call_args_list],['BTCUSDm'])
    def test_reopening_never_promotes_preopen_plan_to_an_approved_order(self):
        self.prepare();self.clock.now=utc('2026-11-01T23:10:00Z')
        new=ClosedHistoryMT5(self.clock);self.api.rates.update(new.rates)
        for s in self.cfg['symbols']:self.api.set_quote(s,new.ticks[s].bid,fill=False)
        view=self.e.step();plan=view['symbols']['XAUUSDm']['preopen_plan']
        self.assertEqual(plan['state'],'REVALIDATING');self.assertFalse(plan['execution_allowed'])
        self.assertEqual(view['markets']['XAUUSDm']['session'],'OPEN');self.assertFalse(self.api.sent)
    def test_weekend_neural_job_is_read_only_and_keeps_actual_session(self):
        self.prepare();snapshot=self.e.research_snapshot();self.cfg['assistant']['local_runtime_enabled']=True
        worker=ContextWorker(self.cfg,self.root,self.clock);self.addCleanup(worker.close)
        jobs=worker.jobs_for(snapshot,{})
        self.assertIn('local_ai:BTCUSDm',jobs);self.assertIn('preopen_ai:XAUUSDm',jobs)
        with patch.object(worker,'_summary',return_value={'XAUUSDm':{'note':'fixture'},'_meta':{}}) as summary:
            result=jobs['preopen_ai:XAUUSDm'][1]()
        payload=summary.call_args.args[0]
        self.assertEqual(payload['analysis_mode'],'PREOPEN')
        self.assertEqual(payload['markets']['XAUUSDm']['session'],'CLOSED')
        self.assertFalse(result['_meta']['execution_allowed'])
    def test_event_for_bitcoin_is_reviewed_even_with_gold_closed(self):
        event=event_alerts([{'title':'Binance security incident update','url':'https://www.binance.com/en/support/announcement/example',
                            'published_utc':self.clock()-60}],self.clock())[0]
        self.e.context=NS(read=lambda:{'events':[event]},submit=lambda x:None)
        view=self.e.step();row=view['event_reviews'][0]
        self.assertIn('BTCUSDm',row['symbols_reviewed']);self.assertNotIn('XAUUSDm',row['symbols_reviewed'])
        self.assertEqual(row['symbols_reviewed']['BTCUSDm']['cycle'],view['cycle']);self.assertFalse(self.api.sent)


class EventEvidence(unittest.TestCase):
    def setUp(self):
        self.now=utc('2026-11-01T12:00:00Z')
        self.row={'title':'Binance reports a security incident','url':'https://www.binance.com/en/support/announcement/example','published_utc':self.now-60}
    def test_dated_event_is_not_a_sell_signal_or_verified_full_article(self):
        event=event_alerts([self.row,self.row],self.now)[0]
        self.assertEqual(event['action'],'REASSESS');self.assertIsNone(event['direction'])
        self.assertEqual(event['verification'],'PRIMARY_DOMAIN_HEADLINE')
        self.assertEqual(event['symbols'],['BTCUSDm']);self.assertEqual(len(event_alerts([self.row,self.row],self.now)),1)
    def test_undated_old_future_and_non_https_headlines_do_not_become_current_events(self):
        for changes in ({'published_utc':None},{'published_utc':self.now+1},{'published_utc':self.now-86401},{'url':'http://www.binance.com/x'}):
            with self.subTest(changes=changes):self.assertFalse(event_alerts([{**self.row,**changes}],self.now))
    def test_event_changes_invalidate_only_affected_order_evidence(self):
        event=event_alerts([self.row],self.now)[0];a={'research':{'events':[]}};b={'research':{'events':[event]}}
        btc={'symbol':'BTCUSDm'};gold={'symbol':'XAUUSDm'}
        self.assertNotEqual(fingerprint(btc,a),fingerprint(btc,b));self.assertEqual(fingerprint(gold,a),fingerprint(gold,b))
        self.assertIn('event.0.headline',facts(btc,b))
    def test_dst_reopening_uses_sundays_offset(self):
        state=xau_state(datetime.fromtimestamp(utc('2026-10-30T22:00:00Z'),timezone.utc))
        self.assertEqual(state.next_open_utc.timestamp(),utc('2026-11-01T23:05:00Z'))

if __name__=='__main__':unittest.main()
