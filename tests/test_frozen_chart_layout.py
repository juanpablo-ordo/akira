"""Real widgets: chart bars must survive short panes and larger native fonts."""
import json
from pathlib import Path
import tempfile
import unittest

from build_windows import read_self_check_report


class ChartFailureDiagnostics(unittest.TestCase):
    def test_windowed_failure_exposes_canvas_dimensions_even_with_empty_stderr(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'NATIVE_SELF_CHECK.json'
            path.write_text(json.dumps({'status':'FAILED','error':'No se completó el dibujado de charts',
                'render_diagnostics':{'charts':{'XAUUSDm':{'height':21,'bars':80,'items':0}}}}),encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError,'"height": 21') as caught:
                read_self_check_report(path,1,'')
            self.assertIn('XAUUSDm',str(caught.exception))
            self.assertIn('"bars": 80',str(caught.exception))


class ChartViewportTests(unittest.TestCase):
    def test_high_dpi_short_dashboard_keeps_both_real_charts_drawn_and_scrollable(self):
        import os,sys
        from tests.ui_chart_probe import run_probe_process
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(os.environ.get('AKIRA_TEST_DIAGNOSTICS') or tmp)
            # A deadline inside dooneevent() cannot interrupt a nested native
            # event loop. The parent owns the real deadline and kills a stuck
            # probe, preserving its last geometry and Python stacks as failure.
            report=run_probe_process([sys.executable,'-u','-m','tests.ui_chart_probe',
                str(folder.resolve()/'CHART_VIEWPORT.json')],folder)
            self.assertEqual(report['status'],'PASSED',report)


class ProbeDeadlineTests(unittest.TestCase):
    def test_a_stuck_child_fails_and_preserves_its_last_state(self):
        import sys,time
        from tests.ui_chart_probe import run_probe_process
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);report=folder/'CHART_VIEWPORT.json'
            started=time.monotonic()
            code='import json,sys,time; from pathlib import Path; Path(sys.argv[1]).write_text(json.dumps({"status":"RUNNING","phase":"simulated_geometry"})); print("child active",flush=True); time.sleep(30)'
            with self.assertRaisesRegex(RuntimeError,'límite de 1.5 s') as caught:
                run_probe_process([sys.executable,'-u','-c',code,str(report)],folder,timeout=1.5)
            self.assertLess(time.monotonic()-started,10)
            self.assertIn('simulated_geometry',str(caught.exception))
            self.assertIn('child active',(folder/'CHART_VIEWPORT.stdout.log').read_text(encoding='utf-8'))

    def test_an_old_pass_cannot_authorize_a_child_without_a_new_report(self):
        import sys
        from tests.ui_chart_probe import run_probe_process
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            for code in (0,7):
                (folder/'CHART_VIEWPORT.json').write_text(json.dumps({'status':'PASSED'}),encoding='utf-8')
                with self.assertRaisesRegex(RuntimeError,'MISSING_REPORT'):
                    run_probe_process([sys.executable,'-c',f'raise SystemExit({code})'],folder)


if __name__=='__main__':unittest.main()
