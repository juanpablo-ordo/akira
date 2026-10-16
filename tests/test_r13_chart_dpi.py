"""Regression for the Windows frozen UI chart drawing failure at high DPI."""
import tkinter as tk
import unittest

from native_ui_check import run_ui_check, chart_geometry, charts_drawn


class ChartDpiTests(unittest.TestCase):
    def test_dashboard_charts_render_at_150_percent(self):
        root = tk.Tk()
        root.tk.call('tk', 'scaling', 1.5)
        try:
            report = run_ui_check(root)
            self.assertEqual(report['status'], 'PASSED')
            self.assertTrue(report['charts'])
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass

    def test_dashboard_charts_render_at_200_percent(self):
        # 200% chart-only check: the full native check additionally shrinks
        # the unrelated chat page to 1024x640, smaller than a 200% UI needs.
        import json
        import tempfile
        import time
        from pathlib import Path
        from desktop import Desktop
        from settings import DEFAULT, load_config
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            cfg=load_config(DEFAULT)
            cfg['assistant']['auto_install_local_ai']=False
            cfg['desktop'].update(notifications=False, notification_popup=False)
            (folder/'akira_config.json').write_text(json.dumps(cfg),encoding='utf-8')
            root=tk.Tk()
            root.tk.call('tk', 'scaling', 2.0)
            app=None
            try:
                app=Desktop(root, folder, preview=True, start_actor=False)
                root.geometry('1600x900+0+0')
                app.navigate(0)
                root.update()
                now=int(time.time())
                for symbol,(chart,_,_,_) in app.charts.items():
                    base=60000.0 if symbol.startswith('BTC') else 4000.0
                    bars=[{'time':now-(80-i)*300, 'open':base+i, 'close':base+i+.4,
                           'low':base+i-1, 'high':base+i+1.8, 'volume':10}
                          for i in range(80)]
                    chart.update_data({'bars':bars, 'timeframe':'M5',
                                       'indicator':'Precio','bid':bars[-1]['close']})
                deadline=time.monotonic()+2.0
                while time.monotonic()<deadline and not charts_drawn(app.charts):
                    root.update()
                self.assertTrue(charts_drawn(app.charts), chart_geometry(app.charts))
            finally:
                if app:
                    app.close()
                else:
                    root.destroy()

    def test_chart_diagnostics_reject_clipped_canvas(self):
        root = tk.Tk()
        try:
            canvas = tk.Canvas(root, width=180, height=30)
            canvas.pack()
            canvas.data = {'bars': [{'time': 1}]}
            root.update_idletasks()
            charts = {'BTCUSDm': (canvas, None, None, None)}
            self.assertEqual(chart_geometry(charts)['BTCUSDm']['bars'], 1)
            self.assertFalse(charts_drawn(charts))
            canvas.configure(height=100)
            canvas.create_line(1,1,180,80)
            root.update_idletasks()
            self.assertFalse(charts_drawn(charts))
        finally:
            root.destroy()


if __name__ == '__main__':
    unittest.main()
