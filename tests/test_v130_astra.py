import json
import unittest
from pathlib import Path
from unittest.mock import patch

import assistant_akira
import akira_local_ai
import desktop
from settings import load_config
from akira_version import BUILD_ID

ROOT=Path(__file__).resolve().parents[1]

class V130AstraTests(unittest.TestCase):
    def setUp(self):
        self.cfg=load_config(ROOT/'default_config.json')

    def test_build_schema_and_fast_human_defaults(self):
        self.assertEqual(BUILD_ID,'AKIRA_16_4_2_STUDIO_REV7')
        self.assertEqual(self.cfg['schema_version'],1600)
        self.assertTrue(self.cfg['desktop']['friendly_ui'])
        self.assertTrue(self.cfg['desktop']['chat_research_animation'])
        self.assertTrue(self.cfg['desktop']['chat_elapsed_timer'])
        self.assertTrue(self.cfg['desktop']['chat_stop_button'])
        self.assertGreaterEqual(float(self.cfg['execution']['rapid_parameter_map_refresh_seconds']),.15)

    def test_chat_has_progress_elapsed_sources_and_stop(self):
        src=(ROOT/'desktop.py').read_text(encoding='utf-8')
        for token in ('DETENER','chat_elapsed','chat_source_strip',"text='● '+name",'YouTube','cancel_current_reply'):
            self.assertIn(token,src)

    def test_sources_and_analysis_are_friendly_and_technical_details_hidden(self):
        src=(ROOT/'desktop.py').read_text(encoding='utf-8')
        self.assertIn('QUÉ ESTÁ HACIENDO AKIRA',src)
        self.assertIn('VER / OCULTAR DETALLE TÉCNICO',src)
        self.assertIn('ACTUALIZAR AHORA',src)
        self.assertNotIn("text='PREPARAR IA LOCAL'",src)

    def test_text_refresh_preserves_scroll_position(self):
        src=(ROOT/'desktop.py').read_text(encoding='utf-8')
        self.assertIn('yview()',src)
        self.assertIn('yview_moveto',src)

    def test_local_agent_supports_cancellation(self):
        src=(ROOT/'akira_local_ai.py').read_text(encoding='utf-8')
        self.assertIn('cancel_event',src)
        a=object.__new__(assistant_akira.AkiraAssistant)
        import threading
        a._cancel_event=threading.Event()
        self.assertFalse(a.cancelled())
        a.cancel_current_reply()
        self.assertTrue(a.cancelled())

    def test_min_lot_high_risk_override_is_explicit_not_silent(self):
        risk=self.cfg['risk']
        self.assertFalse(bool(risk.get('allow_min_lot_structural_override',False)))
        self.assertLessEqual(float(risk.get('min_lot_structural_override_max_pct',8.0)),8.0)
        src=(ROOT/'desktop.py').read_text(encoding='utf-8')
        self.assertIn('COBERTURA CON LOTE MÍNIMO',src)
        self.assertIn('riesgo',src.lower())

if __name__=='__main__':
    unittest.main()
