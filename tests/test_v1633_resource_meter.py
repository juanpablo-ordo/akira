"""Resource meter must disclose the heavy llama-server separately from Ollama."""
import sys,types,unittest
from unittest.mock import patch
from resource_optimizer import process_usage
class MeterTests(unittest.TestCase):
    def test_llama_server_ram_not_hidden_in_ollama(self):
        class Process:
            def memory_info(self): return types.SimpleNamespace(rss=188*1048576)
            def cpu_percent(self,interval=None):return 2.5
        fake=types.SimpleNamespace(Process=lambda pid:Process(),process_iter=lambda fields:[
            types.SimpleNamespace(info={'name':'llama-server.exe','memory_info':types.SimpleNamespace(rss=8311*1048576)}),
            types.SimpleNamespace(info={'name':'ollama.exe','memory_info':types.SimpleNamespace(rss=75*1048576)}),
        ],virtual_memory=lambda:types.SimpleNamespace(percent=53),cpu_percent=lambda interval=None:16)
        with patch.dict(sys.modules,{'psutil':fake}):
            row=process_usage()
        self.assertEqual(row['llama_server_mb'],8311)
        self.assertEqual(row['ollama_mb'],75)
        self.assertEqual(row['akira_mb'],188)
if __name__=='__main__':unittest.main()
