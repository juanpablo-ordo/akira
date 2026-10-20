"""Version 13.1 regression checks: links, consent-controlled voice, Word and safe pending risk."""
import json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from akira_version import BUILD_ID
from assistant_akira import AkiraAssistant
from settings import DEFAULT,load_config
from voice_akira import listen_once,speak_async
from execution import Gateway

class Astra131Tests(unittest.TestCase):
    def test_version_and_optimized_intervals(self):
        self.assertIn('16_4',BUILD_ID)
        c=load_config(DEFAULT)
        self.assertGreaterEqual(c['execution']['rapid_parameter_map_refresh_seconds'],.15)
        self.assertGreaterEqual(c['poll_seconds'],.15)
    def test_source_links_are_named_not_raw(self):
        with tempfile.TemporaryDirectory() as td:
            a=AkiraAssistant(load_config(DEFAULT),Path(td))
            response=a._append_source_list('Investigación realizada.',[
                {'title':'Fuente oficial','url':'https://example.org/a/long/path?something=verylong'}])
            self.assertIn('[Fuente oficial](https://example.org/a/long/path',response)
    def test_word_document_is_valid(self):
        from docx import Document
        with tempfile.TemporaryDirectory() as td:
            a=AkiraAssistant(load_config(DEFAULT),Path(td))
            result=a._execute_local_tool('create_word_document',{'filename':'informe.docx','content':'# Informe de Akira\n## Resumen\n- Punto importante'})
            doc=Document(result['path'])
            self.assertIn('Informe de Akira',[p.text for p in doc.paragraphs])
    def test_voice_unsupported_does_not_launch_process(self):
        with patch('voice_akira.os.name','posix'):
            with self.assertRaises(RuntimeError):listen_once()
    def test_live_risk_gate_stays_in_execution_path(self):
        src=(Path(__file__).resolve().parents[1]/'execution.py').read_text(encoding='utf-8')
        self.assertIn('risk>self.entry_cap(plan,snap)',src)
        self.assertIn('total>self.total_cap(snap)',src)
    def test_voice_not_continuous(self):
        text=(Path(__file__).resolve().parents[1]/'desktop.py').read_text(encoding='utf-8')
        self.assertIn('self.start_voice',text)
        self.assertIn('messagebox.askyesno',text)
        self.assertIn('if self.chat_busy',text)
