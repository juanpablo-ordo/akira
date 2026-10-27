"""R5: regressions extracted from the user's real Windows recordings.

Offline tests deliberately cannot claim that the full GUI or MT5 trades work on Windows.
"""
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock,patch

from application_management import launch_uninstaller
from assistant_akira import AkiraAssistant
from desktop import Desktop


class NativeUninstall(unittest.TestCase):
    def test_inno_setup_unins000_exe_is_used_from_app_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            app=root/'Local'/'Programs'/'AKIRA';app.mkdir(parents=True)
            native=app/'unins000.exe';native.write_bytes(b'MZ')
            runner=Mock(return_value='created')
            result=launch_uninstaller(root/'Local'/'AKIRA',platform='nt',
                executable=app/'AKIRA.exe',localappdata=root/'Local',launch=runner)
            self.assertEqual(result,'created')
            self.assertEqual(runner.call_args.args[0],[str(native)])

    def test_missing_uninstall_file_points_to_windows_installed_apps(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError) as error:
                launch_uninstaller(Path(directory),platform='nt',
                    executable=Path(directory)/'AKIRA.exe',localappdata=Path(directory))
            self.assertIn('Aplicaciones instaladas',str(error.exception))


class AssistantStatusIsNotFaked(unittest.TestCase):
    @staticmethod
    def assistant():
        app=AkiraAssistant.__new__(AkiraAssistant)
        app.cfg={'assistant':{'local_model':'Qwen3-4B-Q4_K_M.gguf',
                              'local_endpoint':'http://127.0.0.1:18987/v1/chat/completions',
                              'local_runtime_start_on_launch':False},'desktop':{}}
        app._managed_model=Mock()
        app._managed_model.enabled.return_value=True
        app._managed_model._paths.return_value=(Path('llama-server.exe'),Path('Qwen.gguf'))
        app._managed_model_boot_attempted=False
        app._model_inference_verified=False
        app._model_inference_error='Sin respuesta aún'
        app._status_lock=threading.RLock()
        app._status_generation=0
        app._status_loading=True
        app._status_due=0
        app._status={}
        return app

    def test_models_list_alone_does_not_mark_assistant_active(self):
        app=self.assistant()
        with patch('assistant_akira.ollama_status',return_value={'ok':True,'models':['Qwen3-4B-Q4_K_M.gguf']}):
            app._probe_local_status(0)
        self.assertFalse(app._status['ready'])
        self.assertEqual(app._status['phase'],'CHECKING')

    def test_only_visible_inference_can_mark_assistant_active(self):
        app=self.assistant()
        with patch('akira_local_ai.chat',return_value='¡Hola!'):
            self.assertEqual(app._verify_local_generation(app.cfg['assistant']['local_endpoint']),'¡Hola!')
        with patch('assistant_akira.ollama_status',return_value={'ok':True,'models':['Qwen3-4B-Q4_K_M.gguf']}):
            app._probe_local_status(0)
        self.assertTrue(app._status['ready'])

    def test_empty_inference_does_not_mark_assistant_active(self):
        app=self.assistant()
        with patch('akira_local_ai.chat',return_value=''):
            with self.assertRaises(RuntimeError):app._verify_local_generation(app.cfg['assistant']['local_endpoint'])
        self.assertFalse(app._model_inference_verified)


class IndividualVoiceCancellation(unittest.TestCase):
    def test_cancel_selected_voice_uses_its_own_event_not_global_stop(self):
        app=Desktop.__new__(Desktop)
        app._voice_download_job=None
        app._voice_single_cancel=threading.Event()
        app._voice_download_busy=True
        app._voice_download_last={'state':'downloading_one'}
        app._render_voice_download=Mock()
        app.stop=threading.Event()
        app.cancel_voice_download()
        self.assertTrue(app._voice_single_cancel.is_set())
        self.assertFalse(app.stop.is_set())
        self.assertEqual(app._voice_download_last['state'],'cancelling')

    def test_individual_cancel_finish_restores_buttons(self):
        app=Desktop.__new__(Desktop)
        app._voice_single_cancel=threading.Event()
        app._voice_download_busy=True
        app._render_voice_download=Mock()
        app.load_voice_inventory=Mock()
        app.handle_voice_single_done({'kind':'cancelled'})
        self.assertFalse(app._voice_download_busy)
        self.assertIsNone(app._voice_single_cancel)
        app.load_voice_inventory.assert_not_called()


if __name__=='__main__':unittest.main()
