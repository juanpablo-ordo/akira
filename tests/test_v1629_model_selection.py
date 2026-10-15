from tests.fixtures import optional_ollama_fixture
"""Conversation selection with real profile files and isolated installer state."""
import contextlib,io,json,os,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from assistant_akira import AkiraAssistant
from assistant_startup import AssistantStartup
from settings import DEFAULT,load_config
import offline_test_runner


class ConversationProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.appdata=self.root/'Windows/LocalAppData'
        self.profile=self.appdata/'AKIRA/assistant_startup.json';self.profile.parent.mkdir(parents=True)
        self.cfg=optional_ollama_fixture(load_config(DEFAULT));self.cfg['assistant'].update(auto_research=False,auto_youtube_research=False,self_review=False)
        with patch.dict(os.environ,{'LOCALAPPDATA':str(self.appdata)}):
            self.bot=AkiraAssistant(self.cfg,self.root/'app')
            self.bot.startup=AssistantStartup(self.bot.root,self.cfg,platform='nt')

    def saved(self,model='qwen3:14b',**extra):
        self.profile.write_text(json.dumps({'phase':'READY','ready':True,'inference_ok':True,
            'text_model':model,'heartbeat':time.time(),'endpoint':'http://127.0.0.1:11434/api/chat',**extra}))

    def conversation(self,models,message='Ayúdame a organizar mis ideas para mañana',deep=False):
        with patch('assistant_akira.ollama_status',return_value={'models':models,'ok':True}), \
                patch.object(self.bot,'_source_tool',side_effect=AssertionError('Unrequested source work')), \
                patch('assistant_akira.ollama_agent',return_value='Podemos organizarlo así.') as call:
            answer=self.bot.local_llm_reply(message,{}) if deep else self.bot.reply(message,{},use_cloud=False)
        self.assertIn('Podemos',answer);self.assertEqual(call.call_count,1)
        return call.call_args.kwargs

    def test_saved_large_windows_model_cannot_override_single_pass_fast_conversation(self):
        self.saved();kw=self.conversation(['qwen3:8b','qwen3:14b'])
        self.assertEqual(kw['model'],'qwen3:8b');self.assertEqual(kw['max_rounds'],1)
        self.assertFalse(kw['reasoning']);self.assertEqual(kw['timeout'],25)

    def test_verified_smaller_repair_model_is_preserved_when_larger_models_are_installed(self):
        self.saved('qwen3:4b');self.assertEqual(self.conversation(['qwen3:4b','qwen3:8b','qwen3:14b'])['model'],'qwen3:4b')

    def test_verified_fractional_size_and_quantized_tags_keep_lightweight_fallback(self):
        self.saved('qwen3:0.6b-q4_K_M')
        self.assertEqual(self.conversation(['qwen3:0.6b-q4_K_M','qwen3:8b','qwen3:14b'])['model'],'qwen3:0.6b-q4_K_M')

    def test_a_different_endpoint_cannot_borrow_the_shared_inference_proof(self):
        self.saved('qwen3:4b',endpoint='http://other.invalid:11434/api/chat')
        self.assertEqual(self.conversation(['qwen3:4b','qwen3:8b'])['model'],'qwen3:8b')

    def test_failed_inference_cannot_override_fast_model_selection(self):
        self.saved('qwen3:4b',inference_ok=False)
        self.assertEqual(self.conversation(['qwen3:4b','qwen3:8b'])['model'],'qwen3:8b')

    def test_only_installed_larger_model_remains_usable_without_download(self):
        self.saved();self.assertEqual(self.conversation(['qwen3:14b'])['model'],'qwen3:14b')

    def test_deep_work_keeps_its_calibrated_model_and_reasoning_route(self):
        self.saved();kw=self.conversation(['qwen3:8b','qwen3:14b'],'Ayúdame a organizar a fondo mis ideas',deep=True)
        self.assertEqual(kw['model'],'qwen3:14b');self.assertGreater(kw['max_rounds'],1);self.assertTrue(kw['reasoning'])

    def test_background_status_reports_the_same_model_as_fast_conversation(self):
        self.saved()
        with patch('assistant_akira.ollama_status',return_value={'ok':True,'models':['qwen3:8b','qwen3:14b']}):self.bot._probe_local_status()
        self.assertEqual(self.bot._status['selected_model'],'qwen3:8b');self.assertTrue(self.bot._status['ready'])


class InstallerIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.host=self.root/'HostAppData';self.host.mkdir()
        self.profile=self.host/'AKIRA/assistant_startup.json';self.profile.parent.mkdir()
        self.original=b'{"text_model":"qwen3:14b","inference_ok":true}'
        self.profile.write_bytes(self.original)

    def run_nested(self,suite=None,error=None):
        seen=[]
        def discover(*args,**kw):
            folder=Path(os.environ['LOCALAPPDATA']);seen.append(folder)
            self.assertNotEqual(folder,self.host);self.assertTrue(folder.is_dir())
            startup=AssistantStartup(self.root/'nested',{},platform='nt')
            self.assertEqual(startup._profile(),{})
            if error:raise error
            return suite or unittest.TestSuite([unittest.FunctionTestCase(lambda:None)])
        report=self.root/'nested_report.json';out=io.StringIO()
        with patch.dict(os.environ,{'LOCALAPPDATA':str(self.host)}), \
                patch.object(sys,'argv',['offline_test_runner.py','--report',str(report)]), \
                patch.object(offline_test_runner.unittest.defaultTestLoader,'discover',side_effect=discover), \
                contextlib.redirect_stdout(out),contextlib.redirect_stderr(out):
            if error:
                with self.assertRaisesRegex(RuntimeError,'discovery failed'):offline_test_runner.main()
                code=None
            else:code=offline_test_runner.main()
            self.assertEqual(os.environ['LOCALAPPDATA'],str(self.host))
        self.assertEqual(self.profile.read_bytes(),self.original);self.assertTrue(seen)
        self.assertFalse(seen[0].exists());return code,report

    def test_installer_discovery_and_tests_do_not_read_or_modify_user_appdata(self):
        code,report=self.run_nested();self.assertEqual(code,0)
        self.assertTrue(json.loads(report.read_text())['successful'])

    def test_isolation_restores_environment_even_if_discovery_fails(self):
        self.run_nested(error=RuntimeError('discovery failed'))

    def test_isolation_does_not_turn_a_failed_test_into_an_installation_success(self):
        def fail():raise AssertionError('deliberate nested test failure')
        code,report=self.run_nested(unittest.TestSuite([unittest.FunctionTestCase(fail)]))
        self.assertEqual(code,1);data=json.loads(report.read_text())
        self.assertFalse(data['successful']);self.assertEqual(data['failures'],1)
