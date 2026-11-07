"""User regressions with real controller/engine paths and synthetic devices only."""
import copy,json,queue,subprocess,sys,tempfile,threading,time,unittest,wave
from concurrent.futures import Future
from dataclasses import replace
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch

from settings import DEFAULT,load_config,save_config
from tests.fixtures import PendingCase
from tests.review_fixture import approve_exact
from tests.test_studio_rev12_mt5_reconnect import Terminal,wait_for


class StableExactReviews(PendingCase,unittest.TestCase):
    live_review_guard=True
    def setUp(self):
        super().setUp()
        from engine import Engine
        self.cfg['mode']='observe';self.e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(self.e.close)
        self.e.step();self.cfg['mode']='trade';self.p=self.plan()
    def test_floating_pnl_and_spread_estimate_do_not_cancel_running_review(self):
        from execution_review import fingerprint
        row,plan,snapshot=approve_exact(self.e,self.p,.01)
        changed=copy.deepcopy(snapshot);changed['account'].update(equity=9.2,balance=10,margin_free=8)
        reestimated={**plan,'risk_usd':plan['risk_usd']+.13,'reward_usd':plan['reward_usd']-.1,'net_rr':1.1}
        self.assertEqual(fingerprint(plan,snapshot),fingerprint(reestimated,changed))
        self.api.account.equity-=.1
        self.assertEqual(self.e.pending_review_guard(self.p,self.g.snapshot(),.01)['data']['verdict'],'APPROVE')
    def test_approval_never_overrides_actual_financial_budget(self):
        from execution import Blocked
        prepared=self.g.prepare(self.p);approve_exact(self.e,prepared.plan,prepared.request['volume'])
        self.api.account.equity=.001;self.api.account.margin_free=.001
        with self.assertRaises(Blocked):self.g.send_immediate_plan(self.p)
        self.assertFalse(self.api.sent)
    def test_background_live_source_refresh_does_not_replace_inflight_exact_request(self):
        from execution_review import fingerprint
        from research import ContextWorker
        _,plan,snapshot=approve_exact(self.e,self.p,.01)
        snapshot['required_pending_reviews']=[__import__('execution_review').request_id(plan)]
        worker=ContextWorker(self.cfg,self.root,clock=self.clock);self.addCleanup(worker.close)
        self.assertTrue(worker.request_pending_reviews([plan],snapshot))
        pid=__import__('execution_review').request_id(plan);attempt=worker.pending_reviews[pid]['attempt_id']
        changed=copy.deepcopy(snapshot)
        changed['research']['sources']={'venue:Binance':{'fresh':True,'content_digest':'another tick'},
            'derivatives:BTCUSDm':{'fresh':True,'content_digest':'new book and provider timestamp'}}
        self.assertEqual(fingerprint(plan,snapshot),fingerprint(plan,changed))
        self.assertEqual(worker.request_pending_reviews([plan],changed),[])
        self.assertEqual(worker.pending_reviews[pid]['attempt_id'],attempt)
    def test_new_closed_evidence_still_requires_new_verdict(self):
        from execution import Blocked
        approve_exact(self.e,self.p,.01)
        f=self.e.planner.caches[self.p.symbol].frames['H1']
        self.e.planner.caches[self.p.symbol].frames['H1']=replace(f,rsi=f.rsi+2)
        with self.assertRaises(Blocked):self.e.pending_review_guard(self.p,self.g.snapshot(),.01)
    def test_execution_error_does_not_wait_for_auxiliary_five_minute_backoff(self):
        from research import ContextWorker
        from pending_verification import identity,fingerprint
        now=self.clock();worker=ContextWorker(self.cfg,self.root,clock=self.clock);self.addCleanup(worker.close)
        _,plan,snapshot=approve_exact(self.e,self.p,.01);pid=identity(plan);fp=fingerprint(snapshot,plan)
        request={'plan':plan,'snapshot':snapshot,'fingerprint':fp,'attempt_id':1,'priority':0}
        worker.pending_batch=[request];worker.pending_reviews[pid]={'fingerprint':fp,'state':'RUNNING','attempt_id':1}
        worker.pending_future=Future();worker.pending_future.set_exception(TimeoutError('modelo ocupado'))
        worker._pending_tick(now,{})
        self.assertEqual(worker.pending_reviews[pid]['retry_at'],now+5)
        snapshot['required_pending_reviews']=[pid];worker._pending_retry_due[plan['symbol']]=now+300
        self.assertEqual(worker.request_pending_reviews([plan],snapshot),[])
        self.clock.advance(6)
        self.assertEqual(worker.request_pending_reviews([plan],snapshot),[pid])


class StartupAndHardware(unittest.TestCase):
    def test_all_eight_gb_integrated_laptops_get_light_profile(self):
        from resource_optimizer import effective_desktop
        original=copy.deepcopy(DEFAULT['desktop'])
        hw={'ram_gb':8,'physical_cores':8,'logical_cores':16,'dedicated_gpu':False}
        result=effective_desktop(original,hw)
        self.assertTrue(result['low_resource_active']);self.assertFalse(result['model_use_gpu'])
        self.assertEqual(result['model_context_tokens'],2048);self.assertEqual(original,DEFAULT['desktop'])
        forced=effective_desktop({**original,'adaptive_resources':False,'low_resource_mode':'ultra'},{'ram_gb':32,'dedicated_gpu':True})
        self.assertTrue(forced['low_resource_active'])
        self.assertEqual(effective_desktop({**original,'low_resource_mode':'off'},hw)['performance_profile'],original['performance_profile'])
    def test_second_process_is_refused_and_lock_releases_cleanly(self):
        from startup_runtime import ApplicationLock
        namespace='AKIRA_TEST_'+str(time.time_ns());lock=ApplicationLock(namespace)
        program='from startup_runtime import ApplicationLock; ApplicationLock('+repr(namespace)+')'
        try:
            child=subprocess.run([sys.executable,'-c',program],capture_output=True,text=True,timeout=5)
            self.assertNotEqual(child.returncode,0);self.assertIn('AlreadyRunning',child.stderr)
        finally:lock.close()
        child=subprocess.run([sys.executable,'-c',program],capture_output=True,text=True,timeout=5)
        self.assertEqual(child.returncode,0,child.stderr)
    def test_inventory_is_written_before_frontend_import(self):
        from startup_runtime import prepare_hardware
        with tempfile.TemporaryDirectory() as tmp:
            with patch('resource_optimizer.desktop_hardware',return_value={'ram_gb':8,'gpus':[{'Name':'Intel UHD'}]}):
                self.assertEqual(prepare_hardware(tmp)['ram_gb'],8)
            self.assertEqual(json.loads((Path(tmp)/'state/hardware.json').read_text())['gpus'][0]['Name'],'Intel UHD')
        source=Path('Akira.py').read_text()
        self.assertLess(source.index('try:application_lock=ApplicationLock()'),source.index('from desktop_qt import main'))
        self.assertLess(source.index('prepare_hardware(Path(args.app_root)'),source.index('from desktop_qt import main'))


class ConfirmedLearning(PendingCase,unittest.TestCase):
    def test_runner_complete_outcome_is_persisted_with_its_lane_and_costs(self):
        from execution import OWN_RUNNER
        from learning import PendingLearner
        p=self.api.add_position(magic=OWN_RUNNER);entry=self.api.record_deal(p,0,p.volume)
        entry.commission=-.1
        self.api.record_deal(p,1,p.volume,2);self.api.positions.remove(p)
        self.g.journal.data['positions'][str(p.ticket)]={'identifier':p.identifier,'plan':{
            **self.plan().to_dict(),'lane':'RUNNER','learning_features':[0.0]*10,'learning_feature_version':'pending_entry_v1'}}
        learner=PendingLearner(self.g);self.assertTrue(learner.update());row=next(iter(learner.records.values()))
        self.assertEqual(row['lane'],'RUNNER');self.assertTrue(row['confirmed']);self.assertAlmostEqual(row['net'],1.9)
        self.assertTrue(row['campaign_complete']);self.assertFalse(learner.update())
    def test_account_models_survive_switch_away_and_restart(self):
        from evolution import DailyLearner
        from akira_version import BUILD_ID
        from strategy_choice import STRATEGY_VERSION,SELECTOR_VERSION,selected
        row={'symbol':'BTCUSDm','strategy_id':'TEST','lane':'PENDING','execution_build':BUILD_ID,
            'strategy_version':STRATEGY_VERSION,'selector_id':selected(self.cfg),'selector_version':SELECTOR_VERSION,
            'confirmed':True,'feature_version':'pending_entry_v1','features':[0.0]*10,'campaign_id':'1',
            'campaign_complete':True,'net':1,'opened_at':100,'closed_at':200}
        first=DailyLearner(self.root);first.run_by_family([row],[123,'A'],selected(self.cfg),now=500)
        files=list(self.root.rglob('family_models/*/state/pending_daily_learning.json'));self.assertEqual(len(files),1)
        state=json.loads(files[0].read_text());state['preserved_marker']='account A';files[0].write_text(json.dumps(state))
        DailyLearner(self.root).run_by_family([row],[456,'B'],selected(self.cfg),now=500)
        again=DailyLearner(self.root);again.run_by_family([row],[123,'A'],selected(self.cfg),now=501)
        self.assertEqual(len(list(self.root.rglob('family_models/*/state/pending_daily_learning.json'))),2)
        self.assertEqual(next(iter(again._family_learners.values())).state['preserved_marker'],'account A')
    def test_insufficient_samples_never_claim_a_trained_or_used_model(self):
        from learning_status import progress
        row=progress([{'confirmed':True,'campaign_complete':True,'features':[0]*10}],{},[123,'A'])
        self.assertEqual(row['stage'],'COLLECTING');self.assertEqual(row['validated_models'],0)
        self.assertFalse(row['base_language_model_training']);self.assertFalse(row['ranking_model_available'])


class AutomaticAccount(unittest.TestCase):
    def test_actor_attaches_new_terminal_account_in_observe_with_new_journal(self):
        from runtime import run_session
        from execution import Reporter
        with tempfile.TemporaryDirectory() as tmp:
            api=Terminal(tmp);cfg=load_config(DEFAULT);cfg.update(mode='observe',expected_login=123,expected_server='TEST',follow_terminal_account=True)
            cfg['poll_seconds']=.04;cfg['risk']['max_trade_money']=1.37
            stop=threading.Event();views=[];commands=queue.Queue()
            with patch('runtime._mt5_api',return_value=api),patch('runtime.ContextWorker',side_effect=RuntimeError('no external jobs in test')):
                thread=threading.Thread(target=run_session,args=(cfg,tmp,Reporter(Path(tmp)/'logs',console=False),stop,commands,views.append));thread.start()
                try:
                    self.assertTrue(wait_for(lambda:any(v.get('connected') for v in views)))
                    api.account.login=456;api.account.server='OTHER';api.account.balance=50;api.account.equity=50
                    self.assertTrue(wait_for(lambda:any((v.get('account') or {}).get('login')==456 for v in views)))
                    view=next(v for v in reversed(views) if (v.get('account') or {}).get('login')==456)
                    self.assertEqual(view['mode'],'observe');self.assertEqual(view['account']['equity'],50)
                    self.assertEqual(view['account_adaptation']['server'],'OTHER');self.assertEqual(cfg['risk']['max_trade_money'],1.37)
                    self.assertEqual(len(list((Path(tmp)/'state').glob('cuenta_*.json'))),2);self.assertFalse(api.sent)
                finally:stop.set();thread.join(3)
            self.assertFalse(thread.is_alive())


class SpokenChannel(unittest.TestCase):
    def test_streamed_network_turn_speaks_sentences_and_preserves_context_without_chat(self):
        from chat_store import ChatStore
        from voice_conversation import CallConversation
        from akira_model_runtime import ManagedLlamaProcess
        received=[];first=threading.Event();release=threading.Event()
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                received.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
                for index,piece in enumerate(('Hola. ','Estoy escuchando.')):
                    self.wfile.write(('data: '+json.dumps({'choices':[{'delta':{'content':piece}}]})+'\n\n').encode());self.wfile.flush()
                    if index==0:release.wait(2)
                self.wfile.write(b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n');self.wfile.flush()
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                cfg=load_config(DEFAULT);cfg['assistant'].update(provider_mode='cloud',cloud_endpoint='http://127.0.0.1:'+str(server.server_port)+'/v1/chat/completions',local_runtime_enabled=False)
                voice=Mock();spoken=[]
                def speak(text):spoken.append(text);first.set()
                voice.enqueue_speech.side_effect=speak
                assistant=NS(chats=ChatStore(tmp),_managed_model=ManagedLlamaProcess(cfg['assistant']))
                call=CallConversation(assistant,lambda:cfg,lambda:{},voice)
                try:
                    self.assertTrue(call.ask('Hola, Akira'));self.assertTrue(first.wait(2))
                    self.assertTrue(call.busy);self.assertEqual(spoken,['Hola.'])
                    release.set();self.assertTrue(wait_for(lambda:not call.busy))
                    self.assertEqual(spoken,['Hola.','Estoy escuchando.']);self.assertEqual(assistant.chats.history(),[])
                    self.assertTrue(call.ask('¿Sigues ahí?'));self.assertTrue(wait_for(lambda:not call.busy))
                    self.assertEqual(received[1]['messages'][-2]['role'],'assistant')
                    self.assertEqual(assistant.chats.history(),[])
                    self.assertTrue(call.ask('Recuerda que mi activo principal es el oro'));self.assertTrue(wait_for(lambda:not call.busy))
                    self.assertIn('oro',assistant.chats.memories()[0]['body']);self.assertEqual(assistant.chats.history(),[])
                finally:call.close();assistant._managed_model.stop()
        finally:release.set();server.shutdown();server.server_close();thread.join(2)
    def test_queue_remains_ready_between_response_chunks_and_interrupt_discards_old_audio(self):
        from voice_session import VoiceSession
        voice=VoiceSession('.',lambda x:None,{'streaming_call':True},{})
        spoken=[];voice.speak=lambda text,expected_epoch=None:spoken.append(text)
        try:
            voice.start_response();voice.enqueue_speech('Primera frase.');voice.finish_response()
            self.assertTrue(wait_for(lambda:len(spoken)==1));time.sleep(.25)
            voice.start_response();voice.enqueue_speech('Segunda frase.');voice.finish_response()
            self.assertTrue(wait_for(lambda:len(spoken)==2))
            voice.interrupt();voice.enqueue_speech('No debe escucharse.');time.sleep(.03)
            self.assertEqual(spoken,['Primera frase.','Segunda frase.'])
        finally:voice.stop()


class QtVoiceAndResources(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        from desktop_qt import StudioWindow
        self.tmp=tempfile.TemporaryDirectory();self.window=StudioWindow(self.tmp.name,preview=True,start_actor=False)
        self.window.show();self.app.processEvents()
        with patch.object(self.window,'load_voices'):self.window.open_call()
        self.app.processEvents()
    def tearDown(self):
        self.window.close();self.app.processEvents();self.tmp.cleanup()
    def test_recognition_goes_only_to_spoken_channel_and_never_echoes_in_ui(self):
        w=self.window;voice=Mock(session_id='current');w.controller.voice=voice
        before=w.controller.assistant.chats.history()
        with patch.object(w.controller,'ask_call',return_value=True) as spoken,patch.object(w.controller,'ask') as typed:
            w.voice_event({'session_id':'current','kind':'final','text':'Esto viene del micrófono'})
            spoken.assert_called_once_with('Esto viene del micrófono');typed.assert_not_called()
        self.assertEqual(w.controller.assistant.chats.history(),before)
        self.assertEqual(w.voice_transcript.text(),'');self.assertNotIn('micrófono',w.voice_state.text())
        w.controller.voice=None
    def test_preview_button_generates_audio_without_starting_microphone(self):
        from PySide6.QtWidgets import QPushButton
        w=self.window;w.populate_voices({'voices':[{'id':'system:1','name':'Prueba','installed':True,'engine':'system'}],
            'devices':{'inputs':[],'outputs':[{'id':7,'name':'Auriculares'}]}})
        w.voice_output.setCurrentIndex(w.voice_output.findData(7));voice=Mock()
        with patch('voice_session.VoiceSession',return_value=voice) as factory:
            next(b for b in w.call_dialog.findChildren(QPushButton) if b.text()=='PROBAR VOZ').click()
        voice.speak.assert_called_once();voice.start.assert_not_called();self.assertIsNone(w.controller.voice)
        self.assertEqual(factory.call_args.args[2]['output_device'],7)
    def test_late_event_from_previous_call_is_ignored(self):
        w=self.window;w.controller.voice=Mock(session_id='new')
        with patch.object(w.controller,'ask_call') as spoken:
            w.voice_event({'session_id':'old','kind':'final','text':'Una frase vieja'});spoken.assert_not_called()
        w.controller.voice=None
    def test_ultralight_pauses_video_without_deleting_wallpaper_preferences(self):
        w=self.window;studio=copy.deepcopy(w.controller.cfg['studio']);studio['wallpaper'].update(kind='video',enabled=True,file='existing.mp4')
        before=copy.deepcopy(studio)
        with patch.object(w.surface,'configure') as configure:
            w.apply_visual(studio,{**w.controller.cfg['desktop'],'low_resource_mode':'ultra'})
        self.assertFalse(configure.call_args.args[0]['enabled']);self.assertEqual(studio,before)


class ClosedHistoryRange(PendingCase,unittest.TestCase):
    def test_weekend_range_recovers_last_closed_bar_left_at_index_zero(self):
        from datetime import datetime,timezone
        from market_cache import MarketCache
        from market_state import MarketDataFreshnessValidator
        now=datetime(2026,11,7,12,tzinfo=timezone.utc).timestamp()
        expected=MarketDataFreshnessValidator.expected_closed('XAUUSDm','H1',now,self.cfg)
        rows=[{'time':expected-(319-i)*3600,'open':2500+i*.1,'high':2502+i*.1,'low':2498+i*.1,'close':2501+i*.1,'tick_volume':100} for i in range(320)]
        api=NS(copy_rates_range=Mock(return_value=rows),copy_rates_from_pos=Mock(return_value=rows[:-1]),last_error=lambda:(0,''))
        cache=MarketCache(api,'XAUUSDm',self.g.log,self.cfg);cache.advance(now,allowed=('H1',),closed_session=True)
        self.assertEqual(cache.frames['H1'].bars[-1].time,expected);api.copy_rates_from_pos.assert_not_called()
        self.assertTrue(MarketDataFreshnessValidator.inspect('XAUUSDm','H1',cache.frames['H1'],now,self.cfg)['ready'])


if __name__=='__main__':unittest.main()
