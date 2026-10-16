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
            # Windows can return the long path even when tempfile used an 8.3 alias.
            # Compare file identity instead of textual spellings of the same path.
            self.assertTrue(Path(args[0]).samefile(exe))
            self.assertEqual(int(args[args.index('--n-gpu-layers')+1]),12)
            managed._force_cpu=True
            args=managed.command(endpoint,{'model_use_gpu':True})
            self.assertTrue(Path(args[0]).samefile(cpu))
            self.assertEqual(int(args[args.index('--n-gpu-layers')+1]),0)
            with self.assertRaises(ValueError):managed.command('http://remote.example/v1/chat/completions')

    def test_installer_embeds_and_keeps_the_verified_model(self):
        installer=(ROOT/'installer'/'akira.iss').read_text(encoding='utf8')
        self.assertIn('7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5',installer)
        files=installer.split('[Files]',1)[1].split('[Icons]',1)[0]
        model=next(line for line in files.splitlines() if line.startswith('Source:') and '.gguf' in line)
        self.assertNotIn('external',model)
        self.assertNotIn('deleteafterinstall',model)
        self.assertIn('Hash:',model)
        self.assertNotIn('CreateDownloadPage',installer)
        self.assertIn('GetSHA256OfFile',installer)
        self.assertIn('SetupIconFile=',installer)
        self.assertIn('UninstallDisplayIcon=',installer)
        self.assertNotIn('CloseApplicationsFilter=*.exe',installer)

    def test_ci_generates_actual_installer_artifact(self):
        workflow=(ROOT/'.github'/'workflows'/'build-windows.yml').read_text(encoding='utf8')
        self.assertIn('installer/akira.iss',workflow)
        self.assertIn('AKIRA-16.3.5-R8-IA-fuentes-expresiones-instalador-Windows-IA-INCLUIDA',workflow)
        self.assertIn('installer.check_installed_ai',workflow)
        self.assertIn('Incorporar llama.cpp oficial',workflow)
        # CI executes every Tk module in its own Python process; requiring the
        # former monolithic command incorrectly rejects the safer full suite.
        self.assertIn('python ci_windows_tests.py',workflow)
        runner=(ROOT/'ci_windows_tests.py').read_text(encoding='utf8')
        self.assertIn('test_r12_theme_boot.py',runner)
        self.assertIn('test_r8_ui_reactions.py',runner)
        self.assertIn('tests',runner)
        self.assertIn('REGRESSION_TESTS.xml',runner)

if __name__=='__main__':unittest.main()
