"""Exercise the photographed filters and the actual Qt call workflow."""
import copy
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from activity_events import category_for_event
from activity_event_schema import normalize_event
from execution import Reporter
from risk_limits import configured_limits
from settings import DEFAULT
from voice_session import voice_matches_language


class ActivityAndRiskTests(unittest.TestCase):
    def test_actor_errors_identified_by_their_symbol_reach_the_error_category(self):
        row=normalize_event({'symbol':'ERROR','message':'Error interno del motor'})
        self.assertEqual(category_for_event(row),'ERROR')

    def test_real_engine_heartbeat_is_recorded_as_analysis(self):
        from engine import Engine
        with tempfile.TemporaryDirectory() as tmp:
            engine=Engine.__new__(Engine)
            engine.g=SimpleNamespace(clock=lambda:100)
            engine.cfg={'desktop':{}};engine._last_heartbeat=0;engine.cycle=4
            engine.planner=SimpleNamespace(caches={'BTCUSDm':object()})
            engine.market_state=lambda symbol:{'open':True}
            engine.candidates={};engine.status={'BTCUSDm':{'state':'BLOQUEO DE RIESGO','detail':'Límite insuficiente'}}
            engine.log=Reporter(Path(tmp),console=False)
            engine.heartbeat({'portfolio_risk':{},'orders':[],
                              'symbols':{'BTCUSDm':{'scenario_book':[],'runner':{}}}})
            self.assertEqual(category_for_event(engine.log.recent_events[0]),'ANÁLISIS')
            self.assertIn('BLOQUEO DE RIESGO',engine.log.recent_events[0]['message'])

    def test_demo_example_respects_both_the_percentage_and_existing_reservations(self):
        cfg=copy.deepcopy(DEFAULT);cfg['capital_protection']['enabled']=False
        cfg['risk'].update(max_trade_money=100000000,max_trade_pct=6,
                           portfolio_capital_pct=100,portfolio_money_cap=0)
        limits=configured_limits(cfg,{'balance':29,'equity':29,'currency':'USD'})
        self.assertAlmostEqual(limits['per_trade'],1.74)
        cfg['risk']['max_trade_pct']=100
        limits=configured_limits(cfg,{'balance':29,'equity':29,'currency':'USD'})
        self.assertEqual(limits['per_trade'],29)
        self.assertEqual(limits['portfolio'],29)

    def test_windows_system_voices_remain_selectable_when_locale_is_opaque(self):
        self.assertTrue(voice_matches_language({'engine':'system','language':"['\\x0c0a']"},'es'))
        self.assertTrue(voice_matches_language({'engine':'piper','language':'es_GT'},'es'))
        self.assertFalse(voice_matches_language({'engine':'piper','language':'en_US'},'es'))


class ActualQtWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        from desktop_qt import StudioWindow
        self.tmp=tempfile.TemporaryDirectory()
        self.window=StudioWindow(self.tmp.name,preview=True,start_actor=False)
        self.window.show();self.app.processEvents()

    def tearDown(self):
        self.window.close();self.app.processEvents();self.tmp.cleanup()

    def test_buttons_show_real_categories_even_with_a_terminal_search(self):
        w=self.window
        w.controller.log_rows.extendleft([
            normalize_event({'utc':'2026-11-06T12:00:00Z','state':'ANÁLISIS','message':'Analizando mercado'}),
            normalize_event({'utc':'2026-11-06T12:00:01Z','operation':'confirmed_open','message':'Orden confirmada'}),
            normalize_event({'utc':'2026-11-06T12:00:02Z','state':'ERROR','message':'Error de prueba'}),
        ])
        w.log_search.setText('texto que no coincide')
        for kind in ('ANÁLISIS','TRADING','ERROR'):
            next(b for b in w.activity_tabs if b.property('activity_filter')==kind).click()
            self.assertEqual(w.activity.rowCount(),1,kind)
            self.assertEqual(w.activity.item(0,1).text(),kind)
        w.controller.log_rows.clear();w.render_logs()
        self.assertIn('No hay errores',w.activity_empty.text())
        self.assertFalse(w.activity_empty.isHidden())

    def test_actual_download_completion_refreshes_the_selected_voice(self):
        from PySide6.QtWidgets import QPushButton
        w=self.window
        with patch.object(w,'load_voices'):
            w.open_call()
        self.app.processEvents()
        row={'id':'piper:es:0','name':'Español','engine':'piper','installed':False,'language':'es_GT'}
        devices={'inputs':[{'id':1,'name':'Micrófono'}],'outputs':[{'id':2,'name':'Altavoz'}]}
        w.populate_voices({'voices':[row],'devices':devices})
        def fake_install(root,voice,progress,cancel):
            progress('Descargando voz')
            row['installed']=True
        def direct_job(name,function,event=None,executor=None):
            value=function()
            if event:w.handle_event({'kind':event,'data':value})
            return True
        with patch('voice_session.install_voice',side_effect=fake_install), \
             patch('voice_session.voice_inventory',side_effect=lambda *args,**kw:[dict(row)]), \
             patch('voice_session.audio_inventory',return_value=devices), \
             patch.object(w.controller,'job',side_effect=direct_job):
            next(b for b in w.call_dialog.findChildren(QPushButton) if b.text()=='DESCARGAR VOZ').click()
        self.assertTrue(w.voice_selector.currentData()['installed'])
        self.assertIn('instalada',w.voice_selector.currentText())
        self.assertFalse(w._voice_single_active)
        session=Mock()
        with patch('voice_session.VoiceSession',return_value=session) as factory, \
             patch.object(w.controller,'save'):
            next(b for b in w.call_dialog.findChildren(QPushButton) if b.text()=='INICIAR LLAMADA').click()
        factory.assert_called_once();session.start.assert_called_once()
        self.assertEqual(factory.call_args.args[3]['id'],row['id'])
        w.controller.voice=None

    def test_installed_windows_voice_is_preselected_before_a_downloadable_voice(self):
        w=self.window
        with patch.object(w,'load_voices'):w.open_call()
        self.app.processEvents()
        online={'id':'piper:es:0','name':'Español','engine':'piper','installed':False,'language':'es_GT'}
        system={'id':'system:1','name':'Windows','engine':'system','installed':True,'language':'1034'}
        w.populate_voices({'voices':[online,system],'devices':{'inputs':[],'outputs':[]}})
        self.assertEqual(w.voice_selector.currentData()['id'],'system:1')

    def test_failed_or_cancelled_transcript_releases_the_microphone(self):
        w=self.window
        with patch.object(w,'load_voices'):w.open_call()
        voice=Mock();w.controller.voice=voice
        w.voice_transcript.setText('Hola Akira')
        with patch.object(w.controller,'ask',return_value=False):w.send_transcript()
        voice.cancel_message.assert_called_once()
        self.assertIn('ocupado',w.voice_state.text())
        w.controller.voice=None

    def test_background_failure_reaches_error_activity(self):
        w=self.window
        def fail():raise RuntimeError('fallo de prueba')
        self.assertTrue(w.controller.job('voice_test_failure',fail))
        end=time.monotonic()+3
        while time.monotonic()<end:
            w.controller.poll()
            if any(category_for_event(row)=='ERROR' for row in w.controller.log_rows):break
            time.sleep(.01)
        self.assertTrue(any('fallo de prueba' in row.get('detail','') and category_for_event(row)=='ERROR'
                            for row in w.controller.log_rows))


if __name__=='__main__':unittest.main()
