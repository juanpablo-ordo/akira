"""Offline contract checks for standalone Windows installer and llama.cpp backend."""
import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlsplit
from akira_model_runtime import ManagedLlamaProcess
from akira_local_ai import _direct_local_engine

ROOT=Path(__file__).resolve().parents[1]


class LlamaSetupTests(unittest.TestCase):
    def test_new_install_does_not_target_ollama(self):
        cfg=json.loads((ROOT/'default_config.json').read_text(encoding='utf8'))['assistant']
        self.assertTrue(cfg['local_runtime_enabled'])
        self.assertFalse(cfg['auto_install_local_ai'])
        self.assertTrue(_direct_local_engine(cfg['local_endpoint']))
        self.assertEqual(urlsplit(cfg['local_endpoint']).hostname,'127.0.0.1')
        self.assertIn('llama-server.exe',cfg['local_runtime_exe'])
        self.assertTrue(cfg['local_runtime_model'].endswith('.gguf'))

    def test_managed_command_stays_on_loopback_and_has_cpu_option(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            exe=folder/'bin'/'llama-server.exe'; exe.parent.mkdir();exe.write_bytes(b'MZ')
            cpu=folder/'cpu'/'llama-server.exe';cpu.parent.mkdir();cpu.write_bytes(b'MZ')
            model=folder/'models'/'model.gguf';model.parent.mkdir();model.write_bytes(b'GGUF')
            managed=ManagedLlamaProcess({'local_runtime_enabled':True,'local_runtime_exe':str(exe),
                                         'local_runtime_model':str(model)})
            endpoint='http://127.0.0.1:18987/v1/chat/completions'
            args=managed.command(endpoint,{'model_use_gpu':True})
            self.assertIn('127.0.0.1',args)
            self.assertIn('18987',args)
            self.assertEqual(args[0],str(exe))
            self.assertEqual(int(args[args.index('--n-gpu-layers')+1]),12)
            managed._force_cpu=True
            args=managed.command(endpoint,{'model_use_gpu':True})
            self.assertEqual(args[0],str(cpu))
            self.assertEqual(int(args[args.index('--n-gpu-layers')+1]),0)
            with self.assertRaises(ValueError):managed.command('http://remote.example/v1/chat/completions')

    def test_installer_has_safe_cancel_and_verified_model(self):
        installer=(ROOT/'installer'/'akira.iss').read_text(encoding='utf8')
        self.assertIn('NextButtonClick',installer)
        self.assertIn('AIPage.AbortedByUser',installer)
        self.assertIn('DeleteFile(',installer)
        self.assertIn('7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5',installer)
        self.assertIn('Flags: external',installer)
        self.assertIn('SetupIconFile=',installer)
        self.assertIn('UninstallDisplayIcon=',installer)
        self.assertNotIn('CloseApplicationsFilter=*.exe',installer)

    def test_ci_generates_actual_installer_artifact(self):
        workflow=(ROOT/'.github'/'workflows'/'build-windows.yml').read_text(encoding='utf8')
        self.assertIn('installer/akira.iss',workflow)
        self.assertIn('AKIRA-16.3.2-instalador-Windows',workflow)
        self.assertIn('Incorporar llama.cpp oficial',workflow)
        self.assertIn('tests/test_v1632_llama_setup.py',workflow)

if __name__=='__main__':unittest.main()
