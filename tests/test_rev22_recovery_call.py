"""Field regressions: occupied local port, playback lifecycle, and truthful UI."""
import copy,json,socket,subprocess,sys,tempfile,threading,time,unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch
from settings import DEFAULT


SERVER = '''import json,sys
from http.server import BaseHTTPRequestHandler,HTTPServer
class H(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def answer(self,obj):
  data=json.dumps(obj).encode();self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
 def do_GET(self):self.answer({'data':[{'id':'fixture'}]} if self.path.endswith('/models') else {'status':'ok'})
 def do_POST(self):
  self.rfile.read(int(self.headers['Content-Length']))
  self.answer({'prompt':'fixture'} if self.path=='/apply-template' else {'tokens':[1,2]} if self.path=='/tokenize' else {'choices':[{'message':{'content':'Respuesta del servidor propio.'},'finish_reason':'stop'}]})
HTTPServer(('127.0.0.1',int(sys.argv[sys.argv.index('--port')+1])),H).serve_forever()
'''


class LocalRecovery(unittest.TestCase):
    def test_external_ollama_remains_supported_and_owned_port_changes_share_runtime(self):
        from akira_model_runtime import shared_runtime
        with tempfile.TemporaryDirectory() as tmp:
            external=shared_runtime({'local_runtime_enabled':False,'local_endpoint':'http://127.0.0.1:11434/api/chat'},tmp)
            self.assertFalse(external.enabled())
            own=shared_runtime({'local_runtime_enabled':True,'local_endpoint':'http://127.0.0.1:18987/v1/chat/completions'},tmp)
            self.assertIs(own,shared_runtime({'local_runtime_enabled':True,'local_endpoint':'http://localhost:18988/v1/chat/completions'},tmp))

    def test_occupied_port_uses_owned_server_and_records_real_generation(self):
        from akira_model_runtime import ManagedLlamaProcess,hardware_profile
        from akira_local_ai import chat,owned_endpoint
        real_popen=subprocess.Popen
        with tempfile.TemporaryDirectory() as tmp,socket.socket() as foreign:
            foreign.bind(('127.0.0.1',0));foreign.listen();port=foreign.getsockname()[1]
            root=Path(tmp);script=root/'server.py';script.write_text(SERVER)
            exe=root/'llama-server.exe';exe.touch();model=root/'test.gguf';model.touch()
            endpoint=f'http://127.0.0.1:{port}/v1/chat/completions'
            cfg={'local_runtime_enabled':True,'local_runtime_exe':str(exe),'local_runtime_model':str(model),'prepare_timeout_seconds':8}
            runtime=ManagedLlamaProcess(cfg,profile=hardware_profile(32,8,8),log_root=root)
            def launch(command,**kwargs):return real_popen([sys.executable,str(script),*command[1:]],**kwargs)
            try:
                with patch('akira_model_runtime.subprocess.Popen',side_effect=launch):
                    with runtime.session(endpoint,{'model_keep_alive_seconds':60}):
                        self.assertNotEqual(owned_endpoint(endpoint),endpoint)
                        self.assertEqual(chat([{'role':'user','content':'Hola'}],endpoint=endpoint),'Respuesta del servidor propio.')
                        self.assertEqual(runtime.generation_count,1);self.assertIsNotNone(runtime.generated_at)
                        self.assertNotEqual(runtime.proc.pid,0)
                self.assertEqual(owned_endpoint(endpoint),endpoint)
                self.assertEqual(foreign.getsockname()[1],port)
                self.assertTrue((root/'state/local_model_owner.json').is_file())
            finally:runtime.shutdown()

    def test_almost_eight_gb_card_does_not_silently_select_cpu(self):
        from akira_model_runtime import hardware_profile
        self.assertGreater(hardware_profile(32,7.99,20)['gpu_layers'],0)

    def test_pid_file_cannot_claim_a_process_from_a_live_parent(self):
        from akira_model_runtime import ManagedLlamaProcess
        with tempfile.TemporaryDirectory() as tmp:
            runtime=ManagedLlamaProcess({},log_root=tmp);runtime.owner_path.parent.mkdir()
            runtime.owner_path.write_text(json.dumps({'parent_pid':123,'parent_created':42,'pid':456}))
            parent=Mock();parent.create_time.return_value=42
            with patch('psutil.pid_exists',return_value=True),patch('psutil.Process',return_value=parent) as process:
                runtime._recover_owned_orphan()
            process.assert_called_once_with(123);parent.terminate.assert_not_called()


class PlaybackLifecycle(unittest.TestCase):
    def test_bluetooth_native_format_preserves_duration_channels_and_signal(self):
        import numpy as np
        from voice_session import playback_format,convert_playback
        sd=Mock();sd.query_devices.return_value={'max_output_channels':2,'default_samplerate':48000}
        def supported(**kw):
            if (kw['samplerate'],kw['channels'])!=(48000,2):raise ValueError('unsupported')
        sd.check_output_settings.side_effect=supported
        self.assertEqual(playback_format(sd,7,22050,1,'int16'),(48000,2))
        raw=(np.sin(np.arange(2205)*.1)*5000).astype('int16').tobytes()
        result=np.frombuffer(convert_playback(raw,'int16',22050,48000,1,2),dtype='int16').reshape((-1,2))
        self.assertEqual(result.shape,(4800,2));self.assertTrue(np.array_equal(result[:,0],result[:,1]))
        self.assertGreater(float(np.std(result)),1000)

    def test_final_sentence_keeps_microphone_closed_until_synthesis_finishes(self):
        from voice_session import VoiceSession
        voice=VoiceSession('.',lambda e:None,{},{});entered=threading.Event();release=threading.Event()
        def speak(*args,**kw):entered.set();release.wait(2)
        voice.speak=speak
        try:
            voice.start_response();voice.enqueue_speech('Respuesta.');self.assertTrue(entered.wait(1))
            voice.finish_response();self.assertTrue(voice.awaiting.is_set())
            release.set();deadline=time.monotonic()+1
            while voice.awaiting.is_set() and time.monotonic()<deadline:time.sleep(.01)
            self.assertFalse(voice.awaiting.is_set())
        finally:release.set();voice.stop()

    def test_interrupt_resets_pending_audio_without_consuming_next_turn(self):
        from voice_session import VoiceSession
        voice=VoiceSession('.',lambda e:None,{},{});entered=threading.Event();release=threading.Event();spoken=[]
        def speak(text,**kw):
            spoken.append(text)
            if text=='old':entered.set();release.wait(2)
        voice.speak=speak
        try:
            voice.start_response();voice.enqueue_speech('old');self.assertTrue(entered.wait(1))
            voice.enqueue_speech('stale');voice.interrupt();voice.start_response();voice.enqueue_speech('new');voice.finish_response()
            release.set();deadline=time.monotonic()+1
            while voice.awaiting.is_set() and time.monotonic()<deadline:time.sleep(.01)
            self.assertEqual(spoken,['old','new']);self.assertEqual(voice._speech_pending,0)
            self.assertFalse(voice.awaiting.is_set())
        finally:release.set();voice.stop()


class VisibleEvidence(unittest.TestCase):
    def test_deposit_does_not_recount_when_broker_history_window_changes(self):
        from capital_guard import status
        account=NS(balance=100,equity=100);snapshot=NS(account=account)
        gateway=NS(cfg=copy.deepcopy(DEFAULT),clock=lambda:100,history=[],history_time=100,
                   history_error='',history_revision=1,journal=NS(data={},save=Mock()))
        self.assertEqual(status(gateway,snapshot)['peak'],100)
        deposit={'ticket':1,'time':99,'type':2,'profit':100}
        account.balance=account.equity=200;gateway.history=[deposit];gateway.history_revision+=1
        self.assertEqual(status(gateway,snapshot)['peak'],200)
        gateway.history=[];gateway.history_revision+=1;status(gateway,snapshot)
        gateway.history=[deposit];gateway.history_revision+=1
        self.assertEqual(status(gateway,snapshot)['peak'],200)

    def test_preopen_plan_is_visible_in_home_and_assistant_evidence(self):
        from studio_presenter import market_activity
        from assistant_akira import AkiraAssistant
        plan={'state':'PREPARED','prepared_at':100,'detail':'Plan condicional preparado.',
              'weekly':{'low':2900,'high':3000},'next_open':'lunes','requires_revalidation':True}
        view={'connected':True,'markets':{'XAUUSDm':{'scheduled_closed':True}},'symbols':{'XAUUSDm':{'preopen_plan':plan}}}
        row=market_activity(view,'XAUUSDm')
        self.assertIn('plan preparado',row['state']);self.assertIn('2900',row['detail']);self.assertIn('gap',row['detail'])
        self.assertEqual(AkiraAssistant.compact(view)['symbols']['XAUUSDm']['preopen_plan'],plan)

    def test_capital_block_cannot_be_overwritten_by_quality_wait(self):
        from decision_status import decision_status
        row=decision_status('BTCUSDm',[],[],[],[{'risk_usd':1,'quality_reason':'Retest'}],[],{},
                            {'state':'ENTRADA BLOQUEADA','detail':'Protección de capital: caída 98%'},2)
        self.assertEqual(row['state'],'ENTRADA BLOQUEADA');self.assertIn('98%',row['reason'])

    def test_same_system_notice_is_deduplicated_but_distinct_deals_are_preserved(self):
        from notification_center import NotificationCenter
        with tempfile.TemporaryDirectory() as tmp:
            center=NotificationCenter(tmp,clock=lambda:100)
            self.assertTrue(center.add('Internet','Conexión disponible'))
            self.assertIsNone(center.add('Internet','Conexión disponible'))
            self.assertTrue(center.add('Internet','Sin conexión'))
            self.assertTrue(center.add_once('Cierre','neto 1','deal:1'))
            self.assertTrue(center.add_once('Cierre','neto 1','deal:2'))
            self.assertEqual(len(center.list()),4)


class ActualCallUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])
    def test_error_survives_listening_state_and_buttons_follow_real_session(self):
        from desktop_qt import StudioWindow
        from voice_session import VoiceSession
        with tempfile.TemporaryDirectory() as tmp:
            w=StudioWindow(tmp,preview=True,start_actor=False)
            try:
                with patch.object(w,'load_voices'):w.open_call()
                self.assertTrue(w.call_buttons['INICIAR LLAMADA'].isEnabled())
                self.assertFalse(w.call_buttons['SILENCIAR'].isEnabled())
                voice=VoiceSession(tmp,lambda e:None,{},{});w.controller.voice=voice;w.update_call_controls()
                self.assertFalse(w.call_buttons['INICIAR LLAMADA'].isEnabled())
                self.assertTrue(w.call_buttons['SILENCIAR'].isEnabled())
                w.voice_event({'session_id':voice.session_id,'kind':'error','text':'Salida desconectada'})
                w.voice_event({'session_id':voice.session_id,'kind':'state','text':'Escuchando'})
                self.assertEqual(w.voice_error.text(),'Salida desconectada');self.assertFalse(w.voice_error.isHidden())
                voice.pause();w.update_call_controls();self.assertTrue(w.call_buttons['REANUDAR'].isEnabled())
                w.voice_event({'session_id':voice.session_id,'kind':'playback_start'})
                w.voice_event({'session_id':voice.session_id,'kind':'playback_level','level':.03})
                self.assertEqual(w.voice_state.text(),'Hablando…');self.assertTrue(w.voice_error.isHidden())
            finally:w.close();self.app.processEvents()


if __name__=='__main__':unittest.main()
