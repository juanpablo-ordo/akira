"""Default native Studio: real rendering, owned media IO and financial isolation."""
import copy,json,os,subprocess,tempfile,time,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from contextlib import nullcontext
from PIL import Image
from settings import DEFAULT,load_config,save_config

ROOT=Path(__file__).resolve().parents[1]
_APP=None

def wait_for(predicate,timeout=4):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if predicate():return True
        time.sleep(.01)
    return False

class NativeStudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global _APP
        from PySide6.QtWidgets import QApplication
        _APP=QApplication.instance() or QApplication([])
    def test_actual_default_frontend_passes_the_executable_contract(self):
        from native_studio_check import run_studio_check,require_studio_check
        check=run_studio_check();self.assertIs(check['eight_pages'],True);require_studio_check({'studio_check':check})
    def test_missing_qt_render_check_cannot_activate_a_legacy_only_executable(self):
        from native_studio_check import require_studio_check,REQUIRED
        with self.assertRaises(RuntimeError):require_studio_check({'render_check':{'status':'PASSED'}})
        for name in REQUIRED:
            check={'version':1,'status':'PASSED',**dict.fromkeys(REQUIRED,True)};check[name]=1
            with self.subTest(name=name),self.assertRaises(RuntimeError):require_studio_check({'studio_check':check})
    def test_age_updates_reuse_rows_and_preserve_user_selection_and_scroll(self):
        from studio_widgets import DataTable
        table=DataTable(['Fuente','Edad']);table.resize(500,200);table.show()
        try:
            rows=[(str(i),['Source '+str(i),'0 s'],{'age':0}) for i in range(80)];table.update_rows(rows);_APP.processEvents();table.selectRow(27);table.verticalScrollBar().setValue(21)
            item=table.item(27,0);scroll=table.verticalScrollBar().value()
            for age in range(40):table.update_rows([(str(i),['Source '+str(i),str(age)+' s'],{'age':age}) for i in range(80)])
            self.assertIs(table.item(27,0),item);self.assertEqual(table.selected_key(),'27');self.assertEqual(table.verticalScrollBar().value(),scroll)
        finally:table.close()
    def test_form_keeps_64bit_account_and_applies_every_profile_budget(self):
        from desktop_qt import StudioWindow
        from resource_optimizer import profile_budget
        with tempfile.TemporaryDirectory() as tmp:
            window=StudioWindow(tmp,preview=True,start_actor=False)
            try:
                panel=window.settings_panel;panel.fields['expected_login'][0].setText(str(2**40));panel.apply_profile('Ahorro de energía');draft=panel.draft()
                self.assertEqual(draft['expected_login'],2**40)
                for key,value in profile_budget('Ahorro de energía').items():self.assertEqual(draft['desktop'][key],value)
                self.assertNotIn('assistant.local_runtime_idle_seconds',panel.fields)
                self.assertIsNone(window.controller.actor)
            finally:window.close();_APP.processEvents()
    def test_default_entrypoint_uses_studio_and_preserves_explicit_pending_only_choice(self):
        source=(ROOT/'Akira.py').read_text(encoding='utf-8');self.assertIn('from desktop_qt import main',source)
        self.assertFalse(load_config(DEFAULT)['execution']['pending_only'])
        cfg=copy.deepcopy(DEFAULT);cfg['execution']['pending_only']=True;self.assertTrue(load_config(cfg)['execution']['pending_only'])

class MediaIsolationTests(unittest.TestCase):
    def test_video_frames_advance_pause_and_stop_only_the_owned_decoder(self):
        from studio_background import WallpaperWorker
        import imageio_ffmpeg
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'fixture.mp4'
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-f','lavfi','-i','testsrc2=size=160x100:rate=12','-t','1','-c:v','mpeg4','-threads','1',str(path)],check=True,capture_output=True,timeout=20)
            worker=WallpaperWorker({'file':str(path),'fps':12,'quality':50,'fit':'contain','max_memory_mb':256,'max_cpu_percent':30},(320,200));worker.start()
            try:
                self.assertTrue(wait_for(lambda:worker.status.get('state') in ('PLAYING','ERROR')),worker.status);self.assertEqual(worker.status['state'],'PLAYING',worker.status)
                first=worker.frames[-1][0];self.assertTrue(wait_for(lambda:worker.frames and worker.frames[-1][0]!=first));self.assertLessEqual(len(worker.frames),1)
                self.assertEqual(worker.status['scope'],'owned wallpaper decoder');self.assertFalse(worker.status['gpu_decode'])
                worker.visible.clear();time.sleep(.2);stamp=worker.status['last_frame'];time.sleep(.3);self.assertEqual(stamp,worker.status['last_frame'])
                worker.visible.set();self.assertTrue(wait_for(lambda:worker.status['last_frame']>stamp))
                proc=worker.process
            finally:worker.close()
            self.assertFalse(worker.thread.is_alive());self.assertIsNotNone(proc.poll())
            self.assertTrue(worker.finished.is_set());self.assertTrue(proc.stdout.closed)
            from tests.media_fixture import remove_closed_media
            remove_closed_media(path)
            self.assertFalse(path.exists())
    def test_transform_crop_rotation_and_buffers_respect_resource_selection(self):
        from studio_background import frame_geometry,video_filter
        cfg={'quality':100,'max_memory_mb':32,'rotation':90,'crop_left':10,'fit':'cover','offset_x':100,'fps':144}
        w,h=frame_geometry((7680,4320),cfg);self.assertLessEqual(w*h*12,32*1048576*.5)
        filters=video_filter((w,h),cfg);self.assertIn('crop=iw*0.9000',filters);self.assertIn('transpose=1',filters);self.assertIn('fps=144',filters);self.assertIn('crop='+str(w)+':'+str(h)+':(iw-ow)*0.0000',filters)

class PersistentCredentialTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.path=Path(tmp.name)/'secrets.json'
        for ctx in (patch('akira_secrets.canonical_path',return_value=self.path),patch('akira_secrets._legacy_paths',return_value=[]),patch.dict(os.environ,{'COINGLASS_API_KEY':'inherited-example'},clear=False)):
            ctx.start();self.addCleanup(ctx.stop)
    def test_explicit_delete_survives_restart_without_resurrecting_environment_key(self):
        import akira_secrets as store
        store.save_secrets({'COINGLASS_API_KEY':'saved-example'});self.assertEqual(store.load_secrets()['COINGLASS_API_KEY'],'saved-example')
        store.save_secrets({'COINGLASS_API_KEY':''});self.assertNotIn('COINGLASS_API_KEY',store.load_secrets());self.assertEqual(store.secret_source('COINGLASS_API_KEY'),'eliminada por el usuario')
        store.save_secrets({'YOUTUBE_API_KEY':'another-example'});self.assertNotIn('COINGLASS_API_KEY',store.load_secrets())
    def test_unreadable_saved_store_cannot_be_overwritten_by_a_general_save(self):
        import akira_secrets as store
        self.path.write_bytes(b'{corrupt');before=self.path.read_bytes();self.assertFalse(store.credential_health()['readable'])
        with self.assertRaisesRegex(RuntimeError,'conserva'):store.save_secrets({'COINGLASS_API_KEY':'replacement'})
        self.assertEqual(self.path.read_bytes(),before)

class SpriteBehaviorTests(unittest.TestCase):
    def test_custom_voice_animation_keeps_frame_durations_and_nonlooping_last_frame(self):
        from akira_studio import UserCatalog
        from akira_expressions import get_catalog
        with tempfile.TemporaryDirectory() as tmp:
            rows=[]
            for i in range(2):
                file=Path(tmp)/(str(i)+'.png');Image.new('RGBA',(20,20),(i*255,20,30,255)).save(file);rows.append({'id':str(i),'path':str(file),'state':'talking','order':i})
            catalog=UserCatalog(get_catalog(ROOT),{'entries':[{},*rows],'sequences':{'talking':{'frames':['0','1'],'durations_ms':[50,200],'loop':False}}})
            self.assertEqual(catalog.choose('AKIRA_047').state,'talking');first=catalog.by_id['0'];self.assertEqual(catalog.next_in_sequence('talking',1,first).id,'0');second=catalog.next_in_sequence('talking',1.06,first)
            self.assertEqual(second.id,'1');self.assertIsNone(catalog.next_in_sequence('talking',1.1,second));self.assertEqual(catalog.next_in_sequence('talking',1.3,second).id,'1')
    def test_unavailable_visual_model_cannot_claim_semantic_recognition(self):
        from sprite_recognition import annotate,SpriteRecognizer
        with tempfile.TemporaryDirectory() as tmp:
            rows=annotate([{'id':'1','path':'unused','state':'idle','confidence':0}],recognizer=SpriteRecognizer(tmp))
            self.assertEqual(rows[0]['state'],'idle');self.assertIn('no disponible',rows[0]['recognition_note']);self.assertNotIn('visual_recognition',rows[0])

class TranslationRaceTests(unittest.TestCase):
    def test_switching_locale_during_generation_cannot_save_old_text_as_new_language(self):
        from studio_translations import Translator
        with tempfile.TemporaryDirectory() as tmp:
            tr=Translator(tmp,'ru');tr.sources={'AJUSTES'};assistant=Mock();assistant.cfg=load_config(DEFAULT);assistant._managed_model.session=lambda *a,**kw:nullcontext()
            def changed(*args,**kwargs):tr.change('ja');return '{"0":"Настройки"}'
            with patch('akira_local_ai.chat',side_effect=changed):tr.translate_missing(assistant,lambda e:None)
            self.assertFalse((Path(tmp)/'studio/languages/ja.json').exists());self.assertFalse((Path(tmp)/'studio/languages/ru.json').exists())

class OwnedModelContextTests(unittest.TestCase):
    def test_history_is_reduced_using_server_tokens_while_current_message_and_system_remain(self):
        from akira_local_ai import owned_context,fit_owned_request
        system={'role':'system','content':'RULES'};current={'role':'user','content':'Do not send any orders'}
        payload={'messages':[system,{'role':'user','content':'x'*700},{'role':'assistant','content':'y'*700},current],'max_tokens':200,'tools':[{'type':'function','function':{'name':'read_only'}}]}
        def server(url,data,**kwargs):
            if url.endswith('/apply-template'):return {'prompt':' '.join(r['content'] for r in data['messages'])}
            return {'tokens':[1]*len(data['content'])}
        with patch('akira_local_ai._post',side_effect=server),owned_context(512):result=fit_owned_request('http://127.0.0.1:18987/v1/chat/completions',payload,5,None)
        self.assertEqual(result['messages'],[system,current]);self.assertEqual(result['tools'],payload['tools']);self.assertEqual(len(payload['messages']),4)
    def test_essential_data_too_large_fails_before_inference_without_shortening_the_question(self):
        from akira_local_ai import owned_context,fit_owned_request
        payload={'messages':[{'role':'system','content':'essential'},{'role':'user','content':'do not execute'}],'max_tokens':200}
        def server(url,data,**kwargs):return {'prompt':'large'} if url.endswith('/apply-template') else {'tokens':[1]*900}
        with patch('akira_local_ai._post',side_effect=server),owned_context(512),self.assertRaisesRegex(RuntimeError,'datos esenciales'):fit_owned_request('http://127.0.0.1:18987/v1/chat/completions',payload,5,None)
        self.assertEqual(payload['messages'][-1]['content'],'do not execute')
    def test_context_limit_is_thread_local_and_does_not_leak_to_external_servers(self):
        from akira_local_ai import owned_context,fit_owned_request
        import threading
        payload={'messages':[{'role':'user','content':'test'}],'max_tokens':200};result=[]
        with owned_context(512):
            thread=threading.Thread(target=lambda:result.append(fit_owned_request('http://127.0.0.1:18987/v1/chat/completions',payload,5,None)));thread.start();thread.join(1)
        self.assertIs(result[0],payload);self.assertIs(fit_owned_request('http://127.0.0.1:18987/v1/chat/completions',payload,5,None),payload)

class ControllerTransactions(unittest.TestCase):
    def test_failed_actor_ack_restores_the_prior_configuration_file(self):
        from studio_controller import StudioController
        with tempfile.TemporaryDirectory() as tmp:
            controller=StudioController(tmp,preview=True,start_actor=False)
            try:
                before=copy.deepcopy(controller.cfg);draft=copy.deepcopy(before);draft['studio']['brand_name']='Persistencia';controller.bridge.connected=True;controller.bridge.request=Mock(return_value={'ok':False,'error':'rejected fixture'})
                self.assertTrue(controller.save(draft));self.assertTrue(wait_for(lambda:not controller._jobs));self.assertEqual(load_config(Path(tmp)/'akira_config.json')['studio']['brand_name'],before['studio']['brand_name']);self.assertEqual(controller.cfg,before)
            finally:controller.close()
    def test_general_save_includes_keys_and_survives_a_new_controller(self):
        from studio_controller import StudioController
        with tempfile.TemporaryDirectory() as tmp,patch('akira_secrets.canonical_path',return_value=Path(tmp)/'keys.json'),patch('akira_secrets._legacy_paths',return_value=[]):
            controller=StudioController(tmp,preview=True,start_actor=False);draft=copy.deepcopy(controller.cfg);draft['studio']['brand_name']='Mi Akira'
            try:self.assertTrue(controller.save(draft,{'COINGLASS_API_KEY':'test-key'}));self.assertTrue(wait_for(lambda:not controller._jobs))
            finally:controller.close()
            next_controller=StudioController(tmp,preview=True,start_actor=False)
            try:
                from akira_secrets import load_secrets
                self.assertEqual(next_controller.cfg['studio']['brand_name'],'Mi Akira');self.assertEqual(load_secrets()['COINGLASS_API_KEY'],'test-key');self.assertIsNone(next_controller.actor)
            finally:next_controller.close()

from tests.fixtures import PendingCase

class FinancialStudioTests(PendingCase,unittest.TestCase):
    def setUp(self):
        PendingCase.setUp(self)
        from engine import Engine
        self.engine=Engine(self.g,self.cfg,self.g.log);self.addCleanup(self.engine.close);self.engine.warmup()
    def test_selected_family_filters_real_scanner_without_changing_risk(self):
        from trade_quality_gate import family
        before=copy.deepcopy(self.cfg['risk']);self.cfg['strategy_choice']['selected']='PENDIENTE_RUPTURA'
        plans=self.engine.scan_plans('BTCUSDm',self.g.quote('BTCUSDm'),force=True)
        self.assertTrue(plans);self.assertTrue(all(family(p)=='PENDIENTE_RUPTURA' for p in plans));self.assertTrue(all(p.selector_id=='PENDIENTE_RUPTURA' for p in plans));self.assertEqual(self.cfg['risk'],before)
    def test_selection_is_part_of_the_frozen_review_and_learning_configuration(self):
        first=self.engine.verification_configuration();self.cfg['strategy_choice']['selected']='RANGO_RECHAZO';second=self.engine.verification_configuration()
        self.assertNotEqual(first,second);self.assertEqual(first['risk'],second['risk'])
    def test_selected_candidate_keeps_its_identity_at_the_executor(self):
        from strategy_choice import tag
        from pending_verification import identity
        plan=tag(self.plan(),self.cfg);self.engine.candidates['BTCUSDm']=[plan]
        command={'action':'assistant_plan','symbol':plan.symbol,'side':'BUY','kind':plan.kind,'candidate_id':identity(plan.to_dict()),**{k:getattr(plan,k) for k in ('entry','sl','tp')}}
        with patch.object(self.engine,'evidence_ready',return_value=(True,'')),patch.object(self.engine,'with_learning_features',side_effect=lambda p,q:p),patch.object(self.g,'send_immediate_plan',return_value=True) as send:
            result=self.engine.handle_command(command)
        self.assertIs(send.call_args.args[0],plan);self.assertTrue(result['execution_confirmed'])
    def test_rejected_candidate_cannot_claim_success_from_other_existing_orders(self):
        from pending_verification import identity
        self.api.add_pending(self.plan());plan=self.plan();self.engine.candidates['BTCUSDm']=[plan]
        command={'action':'assistant_plan','symbol':plan.symbol,'side':'BUY','kind':plan.kind,'candidate_id':identity(plan.to_dict()),'entry':plan.entry+1,'sl':plan.sl,'tp':plan.tp}
        with patch.object(self.engine,'evidence_ready',return_value=(True,'')),patch.object(self.g,'send_immediate_plan') as send:result=self.engine.handle_command(command)
        self.assertFalse(result['ok']);self.assertFalse(result['execution_confirmed']);send.assert_not_called();self.assertIn('cambiaron',result['results'][0]['detail'])
    def test_visual_save_keeps_analysis_caches_and_existing_tickets(self):
        self.engine.map_cache['sentinel']='retained';before=copy.deepcopy(self.api.sent);draft=copy.deepcopy(self.cfg);draft['studio']['theme']='Océano'
        self.engine.handle_command({'action':'apply_settings','config':draft,'changed_paths':['studio.theme']})
        self.assertEqual(self.engine.map_cache['sentinel'],'retained');self.assertEqual(self.api.sent,before)

if __name__=='__main__':unittest.main()
