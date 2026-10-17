"""Real widgets: chart bars must survive short panes and larger native fonts."""
import json
from pathlib import Path
import tempfile
import tkinter as tk
import time
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
        from desktop import Desktop
        from native_ui_check import chart_layout
        from settings import DEFAULT,load_config,save_config
        from engine import Engine
        from execution import Gateway,Journal,Reporter
        from tests.fake_mt5 import Clock,FakeMT5
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);cfg=load_config(DEFAULT);cfg['mode']='observe'
            cfg['assistant']['auto_install_local_ai']=False
            cfg['desktop'].update(privacy=False,notifications=False,notification_popup=False,notification_sound=False)
            save_config(cfg,folder/'akira_config.json')
            root=tk.Tk();scale=float(root.tk.call('tk','scaling'));root.tk.call('tk','scaling',2.0)
            app=None;engine=None
            try:
                app=Desktop(root,folder,preview=True,start_actor=False)
                changes=[]
                for chart,title,caption,tf in app.charts.values():
                    caption.bind('<Configure>',lambda event:changes.append((event.width,event.height)),add='+')
                def settle_layout(window):
                    # Keep a Configure feedback regression finite: update()
                    # cannot return while an idle handler keeps resizing.
                    import _tkinter
                    deadline=time.monotonic()+.35
                    while time.monotonic()<deadline:
                        window.tk.dooneevent(_tkinter.ALL_EVENTS|_tkinter.DONT_WAIT)
                        time.sleep(.001)
                app.assistant.local_ai_status=lambda:{'ready':False,'phase':'DISABLED','detail':'Prueba sintética'}
                clock=Clock();api=FakeMT5(clock);log=Reporter(folder/'proof_logs',console=False)
                gateway=Gateway(api,cfg,Journal(folder/'journal.json'),log,clock)
                engine=Engine(gateway,cfg,log);view=engine.step();view['preview']=True
                app.view=view;app.navigate(0)
                for width,height in ((1366,768),(1024,640)):
                    root.geometry(f'{width}x{height}+0+0');settle_layout(root)
                    app.render(view);settle_layout(root)
                    for symbol,state in chart_layout(app).items():
                        self.assertGreaterEqual(state['height'],70,(symbol,state))
                        self.assertGreater(state['bars'],0,(symbol,state))
                        self.assertGreater(state['items'],20,(symbol,state))
                # Reproduce a divider dragged until the coverage panel is short.
                app.layout.dragging.add('dashboard_neon_lower')
                pane=app.layout.widgets['dashboard_neon_lower'][0]
                pane.sash_place(0,0,115);settle_layout(root)
                scroll=app.dashboard_market_scroll
                scroll._sync_content()
                region=tuple(float(v) for v in root.tk.splitlist(scroll.cget('scrollregion')))
                self.assertGreater(region[3]-region[1],scroll.winfo_height())
                for state in chart_layout(app).values():
                    self.assertGreaterEqual(state['height'],70,state)
                    self.assertGreater(state['items'],20,state)
                self.assertFalse(api.sent)
                self.assertLess(len(changes),100,'Caption Configure handlers did not converge')
            finally:
                if engine:engine.close()
                root.tk.call('tk','scaling',scale)
                if app:app.close()
                else:root.destroy()


if __name__=='__main__':unittest.main()
