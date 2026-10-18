"""Cases from the owner's low-resource laptop and SSL/sprite recording."""
import copy,json,ssl,tempfile,time,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from concurrent.futures import Future
from contextlib import contextmanager
from settings import load_config,DEFAULT

ROOT=Path(__file__).resolve().parents[1]


class TLSFieldTests(unittest.TestCase):
    def test_real_https_accepts_trusted_certificate_and_rejects_wrong_host_and_chain(self):
        from installer.check_https import run
        result=run()
        self.assertEqual(result['status'],'PASSED');self.assertTrue(result['bad_host_rejected']);self.assertTrue(result['bad_chain_rejected'])
    def test_roots_are_cached_with_chain_and_hostname_validation_enabled(self):
        from network_tls import https_context
        context=https_context();self.assertIs(context,https_context());self.assertEqual(context.verify_mode,ssl.CERT_REQUIRED);self.assertTrue(context.check_hostname);self.assertGreater(context.cert_store_stats()['x509_ca'],100)
    def test_news_certificate_failure_is_readable_and_distinct_from_missing_optional_key(self):
        from cyber_ui import source_presentation
        title,state,detail=source_presentation('global_news:BLS',{'error':'URLError: [SSL: CERTIFICATE_VERIFY_FAILED] unable to get local issuer certificate','retry_after_seconds':90})
        self.assertIn('SEGURA',state);self.assertIn('certificado',detail);self.assertNotIn('URLError',detail);self.assertNotIn('_ssl',detail)
        self.assertEqual(source_presentation('coinglass:BTCUSDm',{'state':'CONFIG_REQUIRED'})[1],'CLAVE OPCIONAL')
    def test_unknown_error_does_not_expose_traceback_in_source_tooltip(self):
        from cyber_ui import source_presentation
        self.assertNotIn('RuntimeError',source_presentation('local_ai',{'error':'RuntimeError: llama.cpp no disponible','inflight':True})[2])


class ModelDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        from research import ContextWorker
        self.cfg=load_config(DEFAULT);self.cfg['assistant'].update(local_runtime_enabled=True,local_endpoint='http://127.0.0.1:18987/v1/chat/completions');self.cfg['research']['local_ai_double_check']=False
        self.worker=ContextWorker(self.cfg,self.tmp.name);self.addCleanup(self.worker.close)
    def test_summary_refreshes_pre_start_unavailable_cache_after_owned_session_starts(self):
        from akira_local_ai import _STATUS,_STATUS_LOCK
        import research
        endpoint=self.cfg['assistant']['local_endpoint'];view={'symbols':{'BTCUSDm':{'frames':{'M1':{'rsi':50}}}}}
        with _STATUS_LOCK:_STATUS.update(when=time.monotonic(),endpoint=endpoint,ok=False,models=[])
        reply=json.dumps({'BTCUSDm':{'bias':0,'confidence':0,'preferred':[],'avoid':[],'thesis':'Sin confirmación','note':'Datos limitados'}})
        @contextmanager
        def started(*args):yield
        response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False);response.read.return_value=b'{"data":[{"id":"Qwen3-4B-Q4_K_M.gguf"}]}'
        with patch.object(self.worker,'_local_session',started),patch('akira_local_ai.urlopen',return_value=response),patch.object(research,'ollama_chat',return_value=reply):
            result=self.worker._summary(view,{})
        self.assertIn('BTCUSDm',result);self.assertEqual(result['_meta']['model'],'Qwen3-4B-Q4_K_M.gguf')
    def test_chat_refreshes_the_same_pre_start_negative_cache(self):
        from akira_local_ai import _STATUS,_STATUS_LOCK
        from assistant_akira import AkiraAssistant
        self.cfg['assistant'].update(auto_research=False,auto_youtube_research=False,self_review=False)
        bot=AkiraAssistant(self.cfg,Path(self.tmp.name)/'chat',auto_prepare=False);self.addCleanup(bot._managed_model.shutdown)
        with _STATUS_LOCK:_STATUS.update(when=time.monotonic(),endpoint=self.cfg['assistant']['local_endpoint'],ok=False,models=[])
        @contextmanager
        def started(*args,**kwargs):yield
        response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False);response.read.return_value=b'{"data":[{"id":"Qwen3-4B-Q4_K_M.gguf"}]}'
        with patch.object(bot._managed_model,'session',started),patch('akira_local_ai.urlopen',return_value=response),patch('assistant_akira.ollama_agent',return_value='Podemos organizar tus ideas en tres pasos.'):
            answer=bot.local_llm_reply('Ayúdame a organizar mis ideas',{})
        self.assertIn('organizar tus ideas',answer);self.assertTrue(bot._model_inference_verified)
    def test_unchanged_research_snapshot_is_not_repeatedly_copied_into_evolution(self):
        self.worker.pool=Mock();self.worker.jobs_for=Mock(return_value={});self.worker._evolution_started=True;self.worker.evolution.submit=Mock()
        self.worker.submit({'symbols':{}})
        for _ in range(8):self.worker.tick()
        self.assertEqual(self.worker.evolution.submit.call_count,1)
        self.worker.submit({'symbols':{'BTCUSDm':{}}});self.worker.tick();self.assertEqual(self.worker.evolution.submit.call_count,2)
    def test_complete_assets_are_reviewed_separately_without_dropping_indicators(self):
        view={'symbols':{s:{'frames':{'M15':{'rsi':50,'rare_indicator':1.2345},'H4':{'rsi':40,'rare_indicator':3.4567}}} for s in ('BTCUSDm','XAUUSDm')}};seen=[]
        def answer(messages,**kwargs):
            text=messages[-1]['content'];payload=json.loads(text[text.index('{"as_of_utc"'):]);self.assertEqual(len(payload['symbols']),1);self.assertIn('rare_indicator',payload['indicator_columns']);seen.extend(payload['symbols'])
            return json.dumps({s:{'bias':0,'confidence':0,'preferred':[],'avoid':[],'thesis':'Sin evidencia','note':'Sin confirmación'} for s in payload['symbols']})
        with patch('research.ollama_status',return_value={'ok':True,'models':['Qwen3-4B-Q4_K_M.gguf']}),patch('research.ollama_chat',side_effect=answer):result=self.worker._summary(view,{})
        self.assertEqual(seen,['BTCUSDm','XAUUSDm']);self.assertEqual(result['_meta']['active_symbols'],seen)
    def test_small_context_digest_preserves_timeframes_and_does_not_change_engine_data(self):
        self.cfg['desktop'].update(model_context_tokens=2048,performance_profile='Ahorro de energía')
        view={'symbols':{'BTCUSDm':{'frames':{'M1':{'rsi':50,'atr':2,'rare_indicator':3},'H4':{'rsi':40,'atr':8,'rare_indicator':4}}}}};original=copy.deepcopy(view)
        payload,meta=self.worker._review_input(view,{})
        data=json.loads(payload);self.assertEqual(set(data['symbols']['BTCUSDm']['frames']),{'M1','H4'});self.assertEqual(view,original)
        self.assertEqual(self.cfg['desktop']['model_context_tokens'],2048);self.assertEqual(meta['input_scope'],'COMPACT_INDICATORS_COMPLETE_TIMEFRAMES');self.assertEqual(meta['omitted_raw_indicator_values'],2)
    def test_required_queue_is_serviced_even_when_optional_scheduler_is_waiting(self):
        from pending_verification import identity
        plan={'symbol':'BTCUSDm','key':'live','side':1,'kind':'LIMIT','entry':100,'sl':90,'tp':120}
        self.worker.pool=Mock();self.worker.pool.submit.return_value=Future();self.worker.jobs_for=Mock(return_value={});self.worker.tick()
        self.worker.request_pending_reviews([plan],{'symbols':{},'required_pending_reviews':[identity(plan)]});self.worker.tick()
        self.assertEqual(self.worker.pending_batch[0]['plan']['key'],'live')


class SpriteIsolationTests(unittest.TestCase):
    def test_all_crops_fit_one_drawing_instead_of_crossing_into_a_neighbor(self):
        from akira_expressions import ExpressionCatalog
        from PIL import Image
        catalog=ExpressionCatalog(ROOT)
        for entry in catalog.entries:
            w,h=Image.open(catalog.folder/entry.atlas).size;left,top,right,bottom=entry.bounds
            self.assertLess(right-left,w*.36,entry.id);self.assertLess(bottom-top,h*.36,entry.id)
        self.assertEqual(catalog.validate_artwork()['distinct_cells'],108)
    def test_loading_and_blink_frames_share_visible_scale_and_foot_anchor(self):
        from avatar_animation import MotionSprites
        sprites=MotionSprites(ROOT);boxes=[sprites.image(i,200,200).getbbox() for i in range(15)]
        self.assertLess(max(b[3] for b in boxes)-min(b[3] for b in boxes),3)
        self.assertTrue(all(b[3]-b[1]>175 for b in boxes));self.assertNotEqual(sprites.image(8,200,200).tobytes(),sprites.image(10,200,200).tobytes())
    def test_snapshot_copy_detaches_nested_market_data_and_preserves_precision(self):
        from snapshot_copy import snapshot_copy
        source={'symbols':{'BTCUSDm':{'entry':81024.123456789,'bars':[{'close':81024.123456789}]}},'flags':(True,None)}
        result=snapshot_copy(source);self.assertEqual(result,copy.deepcopy(source));result['symbols']['BTCUSDm']['bars'][0]['close']=0;self.assertNotEqual(result,source)


class QtFieldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        from desktop_qt import StudioWindow
        self.tmp=tempfile.TemporaryDirectory();self.window=StudioWindow(self.tmp.name,preview=True,start_actor=False);self.window.show();self.app.processEvents()
    def tearDown(self):
        self.window.close();self.app.processEvents();self.tmp.cleanup()
    def test_changing_expression_clears_old_face_instead_of_overlaying_it(self):
        avatar=self.window.avatars[0];avatar.grab();self.window.director.publish('happy','Objetivo confirmado',force=True);self.app.processEvents();avatar.grab();self.assertIsNone(avatar._previous)
    def test_blink_changes_visible_pixels_without_changing_expression(self):
        avatar=self.window.avatars[0];self.window.director.publish('idle',force=True);self.app.processEvents();first=avatar.grab().toImage();selected=avatar.selected.id
        self.window.director.blink_frame=2;avatar.update();self.app.processEvents();second=avatar.grab().toImage();self.assertNotEqual(first,second);self.assertEqual(selected,avatar.selected.id)
    def test_continuous_resize_reuses_the_sprite_then_resamples_at_the_final_size(self):
        from studio_widgets import AvatarWidget
        avatar=AvatarWidget(self.window.director,ROOT);avatar.resize(180,180);avatar.show();self.app.processEvents();avatar.grab()
        try:
            with patch.object(avatar.states,'image',wraps=avatar.states.image) as decode:
                for n in range(30):avatar.resize(180+n*3,180+n*2);self.app.processEvents();avatar.grab()
                self.assertLessEqual(decode.call_count,2)
                deadline=time.monotonic()+.18
                while time.monotonic()<deadline:self.app.processEvents();time.sleep(.003)
                self.assertEqual(avatar._stable_dimensions,(avatar.width()-10,avatar.height()-10));self.assertEqual(avatar.selected.id,self.window.director.selected.id)
        finally:avatar.close();avatar.deleteLater();self.app.processEvents()
    def test_energy_saving_stops_decorative_refresh_and_keeps_financial_poll_setting(self):
        before=self.window.cfg['poll_seconds'];self.window.cfg['desktop']['performance_profile']='Ahorro de energía';self.window.apply_visual(self.window.cfg['studio']);self.assertGreaterEqual(self.window._render_interval,1);self.assertEqual(self.window.cfg['poll_seconds'],before)
        self.window.director.loading=False;self.window.director._next_blink=time.monotonic()+3;self.window.animate();self.assertGreaterEqual(self.window.animation_timer.interval(),400)
    def test_minimized_window_keeps_latest_snapshot_without_rendering_hidden_pages(self):
        self.window.showMinimized();self.app.processEvents();self.window._snapshot_pending={'connected':True};render=Mock();self.window.render=render;self.window.poll();render.assert_not_called();self.assertIsNotNone(self.window._snapshot_pending)
