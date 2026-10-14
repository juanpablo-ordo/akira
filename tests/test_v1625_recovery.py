"""Recovery, complete market context and truthful UI evidence; no live service."""
import io,json,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import subprocess
from assistant_startup import AssistantStartup
from assistant_akira import AkiraAssistant
import akira_local_ai
from research import ContextWorker,review_input
from settings import DEFAULT,load_config
from engine import Engine
from tests.fixtures import PendingCase
from tests import test_v1621_startup as ui_fixture
from cyber_ui import source_presentation,public_status

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        (self.root/'PREPARAR_OLLAMA.ps1').touch();self.cfg=load_config(DEFAULT)
        self.process=Mock(pid=123);self.process.poll.return_value=None
        self.new=Mock(pid=789);self.new.poll.return_value=None
        self.launch=Mock(return_value=self.new)
        self.s=AssistantStartup(self.root,self.cfg,platform='nt',launch=self.launch,clock=lambda:1000,alive=lambda p:True)
        self.s.shared_profile=self.s.local_profile;self.s.output_log=self.root/'process.log'
    def profile(self,**row):
        self.s.local_profile.parent.mkdir(parents=True,exist_ok=True)
        self.s.local_profile.write_text(json.dumps(row))
    def own(self):self.s.process=self.process;self.s.started=10;self.s.attempted=True
    def test_failed_live_owned_process_is_restarted(self):
        self.own();self.profile(phase='FAILED',pid=123,heartbeat=999)
        result=self.s.retry();self.assertTrue(result['accepted']);self.process.terminate.assert_called_once()
        self.launch.assert_called_once();self.assertIs(self.s.process,self.new)
    def test_stalled_owned_process_is_restarted(self):
        self.own();self.profile(phase='DOWNLOADING',pid=123,heartbeat=10)
        self.assertEqual(self.s.retry()['action'],'STARTED');self.process.terminate.assert_called_once()
    def test_healthy_download_is_retained(self):
        self.own();self.profile(phase='DOWNLOADING',pid=123,heartbeat=999)
        self.assertEqual(self.s.retry()['action'],'SHARED');self.process.terminate.assert_not_called();self.launch.assert_not_called()
    def test_other_fresh_owner_is_never_terminated(self):
        self.own();self.profile(phase='DOWNLOADING',pid=456,heartbeat=999)
        self.assertEqual(self.s.retry()['action'],'SHARED');self.process.terminate.assert_not_called();self.launch.assert_not_called()
    def test_missing_preparation_component_returns_actionable_failure(self):
        (self.root/'PREPARAR_OLLAMA.ps1').unlink()
        result=self.s.retry();self.assertFalse(result['accepted']);self.assertIn('Falta',result['detail']);self.launch.assert_not_called()
    def test_launch_exception_preserves_actual_cause(self):
        self.launch.side_effect=OSError('Acceso denegado al servicio')
        result=self.s.retry();self.assertFalse(result['accepted']);self.assertIn('Acceso denegado',result['error'])
    def test_installed_tags_do_not_hide_failed_inference(self):
        self.profile(phase='FAILED',text_model='qwen3:4b',inference_checked=True,inference_ok=False,error='memoria insuficiente')
        result=self.s.observe({'ok':True,'ready':True,'models':['qwen3:4b']})
        self.assertFalse(result['ready']);self.assertEqual(result['phase'],'FAILED');self.assertIn('memoria insuficiente',result['detail'])
        # Installed tags and yesterday's successful profile cannot finish a new repair.
        self.profile(phase='READY',pid=456,heartbeat=999,text_model='qwen3:4b',inference_ok=True)
        self.s.process=self.process;self.s.started=1000
        result=self.s.observe({'ok':True,'ready':True,'models':['qwen3:4b']})
        self.assertFalse(result['ready']);self.assertEqual(result['phase'],'STARTING')
    def test_successfully_verified_lighter_model_is_reused(self):
        self.profile(text_model='qwen3:4b',inference_ok=True,endpoint='http://127.0.0.1:11434/api/chat')
        self.assertEqual(self.s.preferred_model(['qwen3:14b','qwen3:4b']),'qwen3:4b')
        self.assertIsNone(self.s.preferred_model(['qwen3:4b'],'https://other.example/api/chat'))
    def test_disabled_assistant_cannot_be_reported_ready(self):
        self.cfg['assistant']['enabled']=False
        self.assertEqual(self.s.observe({'ok':True,'ready':True,'models':['qwen3:4b']})['phase'],'DISABLED')
        self.assertFalse(self.s.observe({'ok':True,'ready':True,'models':['qwen3:4b']})['ready'])

class ModelStatusTests(unittest.TestCase):
    def setUp(self):
        self.old=dict(akira_local_ai._STATUS);akira_local_ai._STATUS.clear()
        self.addCleanup(lambda:(akira_local_ai._STATUS.clear(),akira_local_ai._STATUS.update(self.old)))
    def response(self,row):return io.BytesIO(json.dumps(row).encode())
    def test_endpoint_cache_never_claims_another_server_is_ready(self):
        with patch('akira_local_ai.urlopen',side_effect=[self.response({'models':[{'name':'qwen3:4b'}]}),self.response({'models':[]})]) as fetch:
            a=akira_local_ai.status('http://one.example/api/chat');b=akira_local_ai.status('http://two.example/api/chat')
        self.assertEqual(fetch.call_count,2);self.assertEqual(a['models'],['qwen3:4b']);self.assertEqual(b['models'],[])
    def test_malformed_model_inventory_is_not_successful(self):
        with patch('akira_local_ai.urlopen',return_value=self.response({'models':'not a list'})):
            self.assertFalse(akira_local_ai.status(force=True)['ok'])
    def test_installed_text_fallback_avoids_embeddings_and_vision(self):
        self.assertEqual(akira_local_ai.choose_text_model(['qwen3-embedding:8b','qwen3-vl:8b','mistral:7b'],prefer_fast=True),'mistral:7b')

class ReviewTests(PendingCase,unittest.TestCase):
    def setUp(self):
        super().setUp();self.e=Engine(self.g,self.cfg,self.g.log);self.addCleanup(self.e.close);self.view=self.e.step()
        self.worker=ContextWorker(self.cfg,self.root,clock=self.clock);self.addCleanup(self.worker.close)
        self.reply={s:{'bias':.1,'confidence':.2,'preferred':['BUY_LIMIT'],'avoid':[],'thesis':'estructura','note':'indicadores'} for s in self.view['symbols']}
    def summary(self,side_effect):
        with patch('research.ollama_status',return_value={'ok':True,'models':['qwen3:8b']}),patch('research.ollama_chat',side_effect=side_effect) as chat:
            result=self.worker._summary(self.view,{})
        return result,chat
    def test_all_computed_indicators_and_timeframes_reach_both_assets(self):
        text,meta=review_input(self.view,{},self.clock());data=json.loads(text)
        self.assertEqual(set(meta['active_symbols']),{'BTCUSDm','XAUUSDm'})
        for s,row in self.view['symbols'].items():
            self.assertEqual(set(data['symbols'][s]['frames']),set(row['frames']))
            for tf,frame in row['frames'].items():
                values=dict(zip(data['indicator_columns'],data['symbols'][s]['frames'][tf]))
                for k,v in frame.items():
                    self.assertEqual(values[k],round(v,4) if isinstance(v,float) else v)
    def test_large_news_and_candles_do_not_cut_off_gold_or_json(self):
        sources={'news':{'updated':self.clock(),'data':[{'title':'BTC oro','body':'x'*1000000} for _ in range(100)]}}
        text,meta=review_input(self.view,sources,self.clock());data=json.loads(text)
        self.assertLessEqual(len(text),18000);self.assertIn('XAUUSDm',data['symbols'])
        self.assertNotIn('bars_by_timeframe',text);self.assertNotIn('CONTEXTO TRUNCADO',text)
    def test_stale_source_retains_status_but_cannot_supply_evidence(self):
        text,meta=review_input(self.view,{'news':{'updated':self.clock()-601,'data':['old']}},self.clock())
        self.assertNotIn('data',json.loads(text)['sources']['news']);self.assertIn('news',meta['unavailable_sources'])
    def test_failed_source_old_data_is_not_reused_as_confirmation(self):
        text,_=review_input(self.view,{'news':{'updated':self.clock(),'data':['old'],'error':'403'}},self.clock())
        self.assertFalse(json.loads(text)['sources']['news']['available']);self.assertNotIn('data',json.loads(text)['sources']['news'])
    def test_scheduled_closed_gold_is_excluded_from_live_review(self):
        self.view.setdefault('markets',{}).setdefault('XAUUSDm',{})['scheduled_closed']=True
        text,meta=review_input(self.view,{},self.clock());self.assertEqual(meta['active_symbols'],['BTCUSDm']);self.assertNotIn('XAUUSDm',json.loads(text)['symbols'])
    def test_oversized_indicators_fail_explicitly_instead_of_truncating(self):
        with self.assertRaisesRegex(ValueError,'indicadores completos'):review_input(self.view,{},self.clock(),max_chars=100)
    def test_fast_review_disables_long_thinking_and_bounds_both_passes(self):
        result,chat=self.summary([json.dumps(self.reply),json.dumps(self.reply)])
        self.assertTrue(result['_meta']['verified_twice']);self.assertEqual(chat.call_count,2)
        self.assertEqual(chat.call_args_list[0].kwargs['timeout'],30)
        self.assertLessEqual(chat.call_args_list[1].kwargs['timeout'],12)
        for call in chat.call_args_list:self.assertFalse(call.kwargs['think']);self.assertEqual(call.kwargs['options']['num_predict'],700)
    def test_failed_verifier_is_not_labeled_double_checked(self):
        result,_=self.summary([json.dumps(self.reply),RuntimeError('verificador fuera de servicio')])
        self.assertFalse(result['_meta']['verified_twice']);self.assertIn('fuera de servicio',result['_meta']['verification_error'])
    def test_primary_response_missing_gold_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'Revisión incompleta'):self.summary([json.dumps({'BTCUSDm':self.reply['BTCUSDm']})])
    def test_partial_second_pass_does_not_replace_complete_first_pass(self):
        result,_=self.summary([json.dumps(self.reply),json.dumps({'BTCUSDm':self.reply['BTCUSDm']})])
        self.assertIn('XAUUSDm',result);self.assertFalse(result['_meta']['verified_twice'])
    def test_recovered_assistant_refresh_does_not_reset_all_provider_backoffs(self):
        self.worker.due={'news':1200,'local_ai':1400};self.worker.refresh(sources=['local_ai'])
        self.assertEqual(self.worker.due,{'news':1200})

class UserEvidenceTests(unittest.TestCase):
    setUp=ui_fixture.StartupUITests.setUp
    def wait_repair(self):
        until=time.monotonic()+1
        while self.app.assistant._repair_loading and time.monotonic()<until:time.sleep(.005)
        self.assertFalse(self.app.assistant._repair_loading)
    def test_repair_worker_exception_is_visible(self):
        bot=self.app.assistant
        with patch.object(bot.startup,'retry',side_effect=RuntimeError('Servicio denegado')):
            bot.retry_local_preparation();self.wait_repair()
        self.assertEqual(bot._status['phase'],'FAILED');self.assertIn('Servicio denegado',bot._status['detail'])
    def test_repair_thread_start_failure_releases_loading_state(self):
        bot=self.app.assistant
        with patch('assistant_akira.threading.Thread.start',side_effect=RuntimeError('No hay hilo')):
            result=bot.retry_local_preparation()
        self.assertFalse(result['accepted']);self.assertFalse(bot._repair_loading);self.assertIn('No hay hilo',bot._status['detail'])
    def test_old_probe_cannot_overwrite_new_repair_status(self):
        bot=self.app.assistant;bot._status_generation=1;bot._status={'phase':'FAILED','ready':False,'detail':'nuevo error'}
        with patch('assistant_akira.ollama_status',return_value={'ok':True,'models':['qwen3:4b']}):bot._probe_local_status(0)
        self.assertEqual(bot._status['detail'],'nuevo error');self.assertFalse(bot._status['ready'])
    def test_source_failure_and_branding_are_understandable(self):
        self.assertEqual(source_presentation('coinglass:BTCUSDm',{'error':'falta API_KEY','fresh':False})[1],'FALTA CLAVE')
        self.assertEqual(source_presentation('news',{'error':'plan 403','fresh':False})[1],'PLAN LIMITADO')
        self.assertEqual(public_status('Akira Local Core · qwen3:8b'),'AKIRA · AKIRA')
        self.assertEqual(public_status('Excepción al llamar a Replace · llama3.2:3b'),'Excepción al llamar a Replace · AKIRA')
    def test_stage_display_tracks_real_cycle_without_duplicate_hover_handlers(self):
        engine=Engine(self.g,self.cfg,self.g.log);self.addCleanup(engine.close);view=engine.step()
        panel=self.app.panels['XAUUSDm'];panel.render(view);bar=panel.verify_stages
        self.assertEqual(len(bar.cells),12);self.assertEqual(bar.last_cycle,view['cycle'])
        before=len(bar.cells[0].calls);panel.render(view)
        self.assertEqual(len(bar.cells[0].calls),before)
        self.assertIn('Cotización',bar.cells[0]._akira_tooltip_text)
    def test_google_news_wrapper_does_not_replace_title_or_claim_full_page(self):
        source={'title':'El oro reacciona a inflación','url':'https://news.google.com/rss/articles/example','text':'Extracto real del RSS'}
        with patch('assistant_akira.lookup_current_fact',return_value={'results':[source]}),patch('assistant_akira.read_web') as read:
            result=self.app.assistant._source_tool('research_public_web',{'query':'oro actual','force':True})
        read.assert_not_called();self.assertEqual(result['results'][0]['title'],source['title']);self.assertEqual(result['results'][0]['read_status'],'rss_excerpt')
