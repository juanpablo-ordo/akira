"""ASTRA 13.2: microphone is not PowerShell; Ollama HTTP request can be aborted."""
import os,sys,time,threading,unittest
from unittest.mock import patch
from akira_version import BUILD_ID
from voice_akira import microphone_devices,listen_once
from akira_local_ai import _post

class FakeResponse:
    def __init__(self):self.closed=threading.Event()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
    def close(self):self.closed.set()
    def __iter__(self):
        while not self.closed.wait(.02):
            # An unresponsive model waiting to send a token.
            continue
        raise OSError('Socket closed')

class Tests(unittest.TestCase):
    def test_new_version_and_no_powershell_voice(self):
        self.assertIn('16_3',BUILD_ID)
        from pathlib import Path
        voice=(Path(__file__).resolve().parents[1]/'voice_akira.py').read_text(encoding='utf-8')
        self.assertNotIn('powershell.exe',voice.lower())
        self.assertIn('sounddevice',voice)
        self.assertIn('faster_whisper',voice)
    def test_mic_capture_uses_native_api_and_no_continuous_worker(self):
        import types
        import numpy as np
        fake_sd=types.ModuleType('sounddevice')
        fake_sd.query_devices=lambda:[{'name':'USB Microphone','max_input_channels':1}]
        fake_sd.rec=lambda length,**kwargs:np.ones((length,1),dtype=np.float32)*.08
        fake_sd.wait=lambda:None
        fake_whisper=types.ModuleType('faster_whisper')
        class W:
            def __init__(self,*a,**kw):pass
            def transcribe(self,*a,**kw):return [types.SimpleNamespace(text='Hola Akira')],None
        fake_whisper.WhisperModel=W
        with patch.dict(sys.modules,{'sounddevice':fake_sd,'faster_whisper':fake_whisper}), patch('voice_akira.os.name','nt'),patch('voice_akira._MODEL',None):
            self.assertEqual(microphone_devices(),[(0,'USB Microphone')])
            self.assertEqual(listen_once(timeout_seconds=3),'Hola Akira')
    def test_cancel_closes_ollama_response(self):
        response=FakeResponse();cancel=threading.Event();observed={}
        def run():
            try:_post('http://127.0.0.1:11434/api/chat',{'model':'qwen3:8b'},timeout=10,cancel_event=cancel)
            except Exception as exc:observed['error']=str(exc)
        with patch('akira_local_ai.urlopen',return_value=response):
            t=threading.Thread(target=run,daemon=True);t.start();time.sleep(.12);cancel.set();t.join(timeout=1.5)
        self.assertFalse(t.is_alive(),'Detener debe cancelar pronto la conexión')
        self.assertTrue(response.closed.is_set())
        self.assertIn('detenido',observed.get('error','').lower())
