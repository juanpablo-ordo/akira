"""Startup regressions: authentic states and a live UI after callback failures."""
import json
from pathlib import Path
import tempfile
import threading
import time
from contextlib import ExitStack
import unittest
from unittest.mock import patch, Mock

import desktop
from desktop import CandleChart as NativeCandleChart
from cyber_ui import brand_status
from engine import Engine
from tests.fixtures import PendingCase
from tests.test_desktop_flow import Widget, Variable
from assistant_startup import AssistantStartup


class StartupUITests(unittest.TestCase):
    def setUp(self):
        PendingCase.setUp(self)
        (self.root / 'akira_config.json').write_text(json.dumps(self.cfg))
        stack = ExitStack(); self.addCleanup(stack.close)
        stack.enter_context(patch.multiple(desktop.tk, Frame=Widget, Label=Widget, Button=Widget,
            Entry=Widget, Text=Widget, Listbox=Widget, Checkbutton=Widget, PanedWindow=Widget,
            Canvas=Widget, Scrollbar=Widget, StringVar=Variable, BooleanVar=Variable))
        stack.enter_context(patch.multiple(desktop.ttk, Style=Widget, Notebook=Widget,
            Treeview=Widget, Combobox=Widget, Scrollbar=Widget, Progressbar=Widget))
        stack.enter_context(patch('desktop.AkiraLive2D', Widget))
        stack.enter_context(patch('desktop.CandleChart', Widget))
        bases = desktop.SymbolPanel.__bases__; desktop.SymbolPanel.__bases__ = (Widget,)
        stack.callback(setattr, desktop.SymbolPanel, '__bases__', bases)
        stack.enter_context(patch('desktop.run_session', return_value=None))
        stack.enter_context(patch('assistant_akira.ollama_status',return_value={'ok':False,'models':[]}))
        self.window = Widget(); self.app = desktop.Desktop(self.window, self.root, preview=True)

    def test_backend_failure_is_not_presented_as_endless_preparation(self):
        status = {'ok': False, 'ready': False, 'detail': 'Connection refused', 'models': []}
        self.assertNotIn('preparando', brand_status(status).lower())

    def test_installed_backend_without_models_is_not_presented_as_preparing(self):
        self.assertNotIn('preparando', brand_status({'ok': True, 'ready': False, 'models': []}).lower())

    def test_render_failure_does_not_kill_future_polls_or_conversation_result(self):
        engine = Engine(self.g, self.cfg, self.g.log); self.addCleanup(engine.close)
        view = engine.step(); self.app.messages.put(view)
        self.app.chat_busy = True
        self.app.replies.put({'answer': 'Respuesta final de prueba', 'conversation': True})
        with patch.object(self.app, 'render', side_effect=desktop.tk.TclError('render failure')):
            self.app.poll()
        self.assertFalse(self.app.chat_busy)
        self.assertIn('Respuesta final', self.app.chat.text)
        self.assertTrue(any(name == 'after' and args[1] == self.app.poll for name, args, kw in self.window.calls))
        self.assertTrue((self.root / 'logs' / 'INTERFAZ_ERRORES.log').is_file())

    def test_assistant_status_updates_before_first_mt5_snapshot(self):
        self.assertFalse(self.app.view)
        with patch.object(self.app.assistant, 'local_ai_status', return_value={
                'ok': True, 'ready': False, 'models': [], 'phase': 'MISSING',
                'detail': 'Falta preparar el asistente. Pulsa REPARAR ASISTENTE.'}):
            self.app.poll()
        self.assertNotIn('preparando', self.app.chat_model.options['text'].lower())
        self.assertIn('REPARAR', self.app.assistant_detail.options['text'])

    def test_one_symbol_panel_failure_does_not_stop_the_other_symbol_or_sources(self):
        engine = Engine(self.g, self.cfg, self.g.log); self.addCleanup(engine.close)
        view = engine.step()
        keys = list(self.app.panels)
        with patch.object(self.app.panels[keys[0]], 'render', side_effect=desktop.tk.TclError('broken panel')), \
                patch.object(self.app.panels[keys[1]], 'render', wraps=self.app.panels[keys[1]].render) as healthy:
            self.app.render(view)
        healthy.assert_called_once()
        self.assertIn('BTCUSDm', self.app.sources.text)

    def test_one_chart_failure_keeps_order_tables_and_sources_alive(self):
        engine = Engine(self.g, self.cfg, self.g.log); self.addCleanup(engine.close)
        view = engine.step(); chart = next(iter(self.app.charts.values()))[0]
        with patch.object(chart, 'update_data', side_effect=desktop.tk.TclError('broken chart')):
            self.app.render(view)
        self.assertEqual(len(self.app.orders.items), len(view['orders']))
        self.assertIn('BTCUSDm', self.app.sources.text)

    def test_closed_gold_dashboard_does_not_show_waiting_for_candles(self):
        engine = Engine(self.g, self.cfg, self.g.log); self.addCleanup(engine.close)
        view = engine.step(); view['markets'] = {'XAUUSDm': {'scheduled_closed': True}}
        self.app.render(view)
        self.assertTrue(self.app.charts['XAUUSDm'][0].data['market_closed'])

    def test_missing_m1_uses_real_m15_bars_and_updates_both_timeframe_selectors(self):
        engine=Engine(self.g,self.cfg,self.g.log);self.addCleanup(engine.close)
        view=engine.step();info=view['symbols']['BTCUSDm'];info['bars_by_timeframe']['M1']=[];info['bars']=[]
        chart,title,state,tf_var=self.app.charts['BTCUSDm'];tf_var.set('M1')
        panel=self.app.panels['BTCUSDm'];panel.tf_var.set('M1')
        self.app.render(view)
        self.assertEqual(tf_var.get(),'M15');self.assertEqual(panel.tf_var.get(),'M15')
        self.assertEqual(chart.data['bars'],info['bars_by_timeframe']['M15'])
        self.assertEqual(chart.data['engine_frame'],info['frames']['M15'])

    def test_legacy_m1_bars_are_never_labeled_as_h1(self):
        bars=[{'time':1,'close':100}]
        actual,used=desktop.available_chart_frame({'bars':bars},'H1')
        self.assertEqual(actual,'M1');self.assertIs(used,bars)

    def test_indicator_calculation_failure_is_retried_with_unchanged_bars(self):
        from types import SimpleNamespace
        from chart_indicators import indicator_chart
        from unittest.mock import Mock
        bars=[{'time':i*900,'open':100+i,'close':100.5+i,'high':101+i,'low':99+i,'volume':100} for i in range(60)]
        canvas=SimpleNamespace(data={'bars':bars,'timeframe':'M15'},signature='old',
            winfo_width=lambda:600,winfo_height=lambda:300,delete=Mock(),
            create_line=Mock(),create_text=Mock(),create_rectangle=Mock())
        with patch('chart_render.indicator_chart',side_effect=RuntimeError('temporary indicator failure')):
            with self.assertRaises(RuntimeError):NativeCandleChart.redraw(canvas)
        self.assertIsNone(canvas.signature);self.assertFalse(hasattr(canvas,'_indicator_signature'))
        with patch('chart_render.indicator_chart',wraps=indicator_chart) as recovered:
            NativeCandleChart.redraw(canvas)
        recovered.assert_called_once();self.assertTrue(canvas._indicator_data)


class Process:
    pid = 123
    def __init__(self, code=None): self.code = code
    def poll(self): return self.code


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); (self.root/'PREPARAR_OLLAMA.ps1').touch()
        self.cfg = {'assistant': {'auto_install_local_ai': True}}
        self.process = Process(); self.calls = []
        def launch(*args, **kwargs): self.calls.append((args, kwargs)); return self.process
        self.simulated_alive=Mock(side_effect=lambda pid:pid in (123,456))
        self.startup = AssistantStartup(self.root, self.cfg, enabled=True, platform='nt',
            launch=launch, clock=lambda: 1000, alive=self.simulated_alive)
        self.startup.shared_profile = self.startup.local_profile
        self.startup.output_log = self.root/'state/ASISTENTE_PROCESO.log'
        self.down = {'ready': False, 'ok': False, 'models': []}

    def assistant(self):
        from assistant_akira import AkiraAssistant
        bot=AkiraAssistant(self.cfg,self.root)
        bot.startup.shared_profile=bot.startup.local_profile
        bot.startup.output_log=self.root/'state/ASISTENTE_PROCESO.log'
        return bot

    def profile(self, **kwargs):
        self.startup.local_profile.parent.mkdir(parents=True, exist_ok=True)
        self.startup.local_profile.write_text(json.dumps(kwargs), encoding='utf-8-sig')

    def test_automatic_preparation_launches_only_once_and_without_shell(self):
        for _ in range(3): self.assertEqual(self.startup.observe(self.down)['phase'], 'STARTING')
        self.assertEqual(len(self.calls), 1)
        self.assertNotIn('shell', self.calls[0][1]); self.assertIn('-NonInteractive', self.calls[0][0][0])

    def test_preview_and_disabled_autoinstall_do_not_start_installation(self):
        self.startup.enabled = False; self.startup.observe(self.down)
        self.startup.enabled = True; self.cfg['assistant']['auto_install_local_ai'] = False
        self.startup.observe(self.down); self.assertFalse(self.calls)

    def test_external_endpoint_is_never_changed_or_installed_locally(self):
        self.cfg['assistant']['local_endpoint'] = 'https://custom.example/api/chat'
        self.assertEqual(self.startup.observe(self.down)['phase'], 'UNAVAILABLE')
        self.startup.retry(); self.assertFalse(self.calls)

    def test_real_installed_model_skips_preparation_even_if_profile_failed(self):
        self.profile(phase='FAILED', ready=False, error='old error')
        row = self.startup.observe({'ready': True, 'ok': True, 'models': ['qwen3:4b']})
        self.assertEqual(row['phase'], 'READY'); self.assertFalse(self.calls)

    def test_profile_ready_flag_cannot_claim_readiness_without_a_real_model(self):
        self.profile(phase='READY', ready=True, heartbeat=999)
        self.assertFalse(self.startup.observe(self.down)['ready'])

    def test_optional_vision_download_does_not_block_ready_text_model(self):
        self.profile(phase='VISION', ready=True, heartbeat=999)
        row = self.startup.observe({'ready': True, 'ok': True, 'models': ['qwen3:4b']})
        self.assertEqual(row['phase'], 'READY'); self.assertIn('visión', row['detail'])

    def test_failed_process_is_visible_and_explicit_retry_launches_again(self):
        self.startup.observe(self.down); self.process.code = 1
        self.profile(phase='FAILED', error='download unavailable', pid=123, heartbeat=1000)
        row = self.startup.observe(self.down)
        self.assertEqual(row['phase'], 'FAILED'); self.assertIn('REPARAR', row['detail'])
        self.startup.retry(); self.assertEqual(len(self.calls), 2)

    def test_progress_from_another_fresh_preparation_is_shared_without_duplication(self):
        self.profile(phase='DOWNLOADING', pid=456, heartbeat=999, progress_pct=38,
            completed_bytes=380, total_bytes=1000, detail='Descargando capa 38%')
        row = self.startup.observe(self.down)
        self.assertEqual(row['progress_pct'], 38); self.assertFalse(self.calls)
        self.simulated_alive.assert_called_once_with(456)

    def test_stale_or_corrupt_progress_does_not_cause_endless_loading(self):
        for row in ({'phase':'DOWNLOADING','pid':456,'heartbeat':10}, {'heartbeat':'broken'}):
            with self.subTest(row=row):
                self.profile(**row); self.startup.observe(self.down)
        self.assertEqual(len(self.calls), 1)

    def test_waiting_launcher_prefers_progress_from_the_existing_owner(self):
        self.startup.shared_profile=self.root/'shared_progress.json'
        self.profile(phase='WAITING',pid=123,heartbeat=1000)
        self.startup.shared_profile.write_text(json.dumps({'phase':'DOWNLOADING','pid':456,
            'heartbeat':999,'progress_pct':41,'detail':'Descargando capa 41%'}))
        self.startup.process=self.process;self.process.code=0;self.startup.attempted=True
        row=self.startup.observe(self.down)
        self.assertEqual(row['phase'],'DOWNLOADING');self.assertEqual(row['progress_pct'],41)
        self.assertFalse(self.calls)
        self.simulated_alive.assert_called_once_with(456)

    def test_dead_preparation_owner_is_recovered_without_waiting_for_old_progress(self):
        self.profile(phase='DOWNLOADING',pid=456,heartbeat=999,detail='old progress')
        self.startup.alive=lambda pid:False
        row=self.startup.observe(self.down)
        self.assertEqual(row['phase'],'STARTING');self.assertEqual(len(self.calls),1)

    def test_worker_creation_failure_does_not_leave_status_permanently_loading(self):
        bot=self.assistant()
        with patch('assistant_akira.threading.Thread.start',side_effect=RuntimeError('worker unavailable')):
            row=bot.local_ai_status()
        self.assertFalse(bot._status_loading);self.assertEqual(row['phase'],'FAILED')
        self.assertIn('REPARAR',row['detail'])

    def test_available_model_variant_is_selected_by_its_actual_installed_name(self):
        from akira_local_ai import choose_text_model
        actual='qwen3:8b-q4_K_M'
        self.assertEqual(choose_text_model([actual]),actual)
        bot=self.assistant()
        with patch('assistant_akira.ollama_status',return_value={'ok':True,'models':[actual]}):bot._probe_local_status()
        self.assertTrue(bot._status['ready']);self.assertEqual(bot._status['selected_model'],actual)

    def test_status_probe_and_repair_are_nonblocking_and_do_not_call_mt5(self):
        bot = self.assistant()
        entered=threading.Event(); release=threading.Event()
        def slow(*args,**kwargs): entered.set(); release.wait(1); return dict(self.down)
        with patch('assistant_akira.ollama_status', side_effect=slow):
            at=time.monotonic(); bot.local_ai_status()
            self.assertLess(time.monotonic()-at,.15); self.assertTrue(entered.wait(.5))
            for _ in range(10): bot.local_ai_status()
            release.set()
            deadline=time.monotonic()+1
            while bot._status_loading and time.monotonic()<deadline: time.sleep(.005)
        self.assertEqual(bot.local_ai_status()['phase'], 'UNAVAILABLE')

    def test_simulated_owner_never_calls_windows_or_starts_a_real_process(self):
        import assistant_startup
        import ctypes
        from types import SimpleNamespace
        self.profile(phase='DOWNLOADING',pid=456,heartbeat=999,progress_pct=56)
        with patch.object(assistant_startup,'os',SimpleNamespace(name='nt')), \
                patch.object(ctypes,'WinDLL',side_effect=AssertionError('Real Windows API from simulation'),create=True), \
                patch('subprocess.Popen',side_effect=AssertionError('Real process from simulation')):
            row=self.startup.observe(self.down)
        self.assertEqual(row['progress_pct'],56);self.assertFalse(self.calls)

    def test_simulated_process_logs_never_use_the_host_appdata_folder(self):
        self.startup.observe(self.down)
        output=self.calls[0][1]['stdout']
        self.assertTrue(Path(output.name).is_relative_to(self.root))
        self.assertTrue(self.startup.shared_profile.is_relative_to(self.root))


if __name__ == '__main__': unittest.main()
