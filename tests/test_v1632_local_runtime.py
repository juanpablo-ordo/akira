import sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
from akira_model_runtime import ManagedLlamaProcess, hardware_profile

class HardwareAndRuntimeTests(unittest.TestCase):
    def test_5060ti_profile_leaves_headroom(self):
        p=hardware_profile(ram_gb=32,gpu_vram_gb=8,cpu_cores=12)
        self.assertLessEqual(p['target_model_vram_gb'],5)
        self.assertLessEqual(p['gpu_layers'],20)
        self.assertEqual(p['context_tokens'],4096)
        self.assertEqual(p['parallel_requests'],1)
    def test_no_implicit_model_download_or_launch(self):
        mgr=ManagedLlamaProcess({'local_runtime_enabled':True})
        with self.assertRaises(FileNotFoundError):mgr.command('http://127.0.0.1:8080/v1/chat/completions')
        self.assertIsNone(mgr.proc)
    def test_external_network_disallowed(self):
        mgr=ManagedLlamaProcess({'local_runtime_enabled':True})
        with self.assertRaises(ValueError):mgr._port('https://public.example/v1/chat/completions')
        with self.assertRaises(ValueError):mgr._port('http://1.2.3.4:8080/v1/chat/completions')
    def test_command_partial_gpu_and_cpu_toggle(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe=Path(tmp)/'llama-server.exe';exe.write_bytes(b'synthetic')
            model=Path(tmp)/'qwen3-4b-q4.gguf';model.write_bytes(b'synthetic')
            mgr=ManagedLlamaProcess({'local_runtime_enabled':True,'local_runtime_exe':str(exe),'local_runtime_model':str(model)})
            cmd=mgr.command('http://127.0.0.1:8080/v1/chat/completions',{'model_use_gpu':False,'model_context_tokens':3072})
            self.assertEqual(cmd[cmd.index('--n-gpu-layers')+1],'0')
            self.assertEqual(cmd[cmd.index('--ctx-size')+1],'3072')
            self.assertEqual(cmd[cmd.index('--host')+1],'127.0.0.1')
    def test_stop_does_not_terminate_unowned_process(self):
        mgr=ManagedLlamaProcess({'local_runtime_enabled':False})
        with patch('subprocess.Popen') as started:
            with mgr.session('http://127.0.0.1:8080/v1/chat/completions'):
                pass
            mgr.stop()
            started.assert_not_called()

if __name__=='__main__':unittest.main()
