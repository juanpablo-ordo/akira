"""Regression checks for visible chat and durable, independent panel layout."""
from pathlib import Path
import json,tempfile,tkinter as tk,unittest
from unittest.mock import patch
from desktop_layout import PanelLayout,valid_ratios,fitted_geometry

class Root:
    def __init__(self):self.callbacks={};self.cancelled=[]
    def after(self,delay,callback):
        key=len(self.callbacks)+1;self.callbacks[key]=callback;return key
    def after_idle(self,callback):return self.after(0,callback)
    def after_cancel(self,key):self.cancelled.append(key)

class Pane:
    def __init__(self,parent,**kw):self.options=kw;self.bindings={};self.children=[];self.coords={0:(500,300),1:(750,400)};self.width=1000;self.height=600
    def bind(self,event,callback,**kw):self.bindings[event]=callback
    def panes(self):return self.children
    def winfo_width(self):return self.width
    def winfo_height(self):return self.height
    def sash_coord(self,i):return self.coords[i]
    def sash_place(self,i,x,y):self.coords[i]=(x,y)

class PanelLayoutTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.folder=Path(t.name);self.root=Root();self.path=self.folder/'state/desktop_layout.json'
        self.layout=PanelLayout(self.root,self.path)
        p=patch('desktop_layout.tk.PanedWindow',Pane);p.start();self.addCleanup(p.stop)
    def pane(self,key='chat',orient=tk.HORIZONTAL,ratios=(.3,)):
        p=self.layout.pane(None,key,orient,ratios);p.children=['left','right'];return p
    def test_invalid_ratio_data_cannot_hide_or_reverse_panes(self):
        for v in (None,'0.5',[],[float('nan')],[float('inf')],[0],[1],[.7,.2],[.5,.51]):self.assertIsNone(valid_ratios(v,3 if isinstance(v,list) and len(v)==2 else 2))
        self.assertEqual(valid_ratios([.2,.7],3),(.2,.7))
    def test_window_fits_small_and_large_monitors(self):
        for sw,sh in ((1280,720),(1366,768),(1920,1080),(1024,600)):
            w,h,mw,mh=fitted_geometry(1600,1050,sw,sh)
            self.assertLessEqual(w,sw-32);self.assertLessEqual(h,sh-80);self.assertLessEqual(mw,w);self.assertLessEqual(mh,h)
    def test_initial_dividers_restore_without_user_file(self):
        p=self.pane();self.layout.restore('chat');self.assertEqual(p.coords[0][0],300)
        self.assertEqual(p.options['sashwidth'],10);self.assertTrue(p.options['opaqueresize']);self.assertTrue(p.options['showhandle'])
    def test_drag_is_debounced_and_persists_ratio_across_window_sizes(self):
        p=self.pane();p.coords[0]=(400,300);p.bindings['<ButtonRelease-1>'](None)
        first=self.layout.pending;p.coords[0]=(600,300);p.bindings['<ButtonRelease-1>'](None)
        self.assertIn(first,self.root.cancelled);self.layout.save()
        data=json.loads(self.path.read_text());self.assertEqual(data['panels']['chat'],[.6])
        restored=PanelLayout(self.root,self.path);q=restored.pane(None,'chat',tk.HORIZONTAL,(.3,));q.children=['left','right'];q.width=1500
        restored.restore('chat');self.assertEqual(q.coords[0][0],900)
    def test_vertical_divider_uses_height_and_keeps_horizontal_coordinate(self):
        p=self.pane('analysis',tk.VERTICAL,(.4,));self.layout.restore('analysis');self.assertEqual(p.coords[0],(500,240))
        p.coords[0]=(500,420);self.layout.changed('analysis');self.assertEqual(self.layout.saved['analysis'],[.7])
    def test_corrupt_or_old_file_recovers_to_defaults(self):
        self.path.parent.mkdir();self.path.write_text('{broken')
        for contents in ('{broken',json.dumps({'schema':0,'panels':{'chat':[.8]}})):
            self.path.write_text(contents);layout=PanelLayout(self.root,self.path);self.assertFalse(layout.saved)
    def test_reset_removes_saved_ratios_and_never_touches_trading_settings(self):
        cfg=self.folder/'akira_config.json';cfg.write_text('{"risk":{"max_trade_money":2.17}}')
        before=cfg.read_bytes();p=self.pane();self.layout.saved={'chat':[.8]};self.layout.reset()
        self.assertEqual(p.coords[0][0],300);self.assertEqual(cfg.read_bytes(),before);self.assertEqual(json.loads(self.path.read_text())['panels'],{})
    def test_toggling_detail_count_uses_valid_fallback(self):
        p=self.pane('sources',tk.VERTICAL,(.5,.78));self.layout.restore('sources');self.assertEqual(p.coords[0][1],300)
        p.children.append('detail');self.layout.restore('sources');self.assertEqual(p.coords[1][1],468)
    def test_too_small_unmapped_pane_does_not_replace_saved_layout(self):
        p=self.pane();self.layout.saved={'chat':[.4]};p.width=1;self.layout.changed('chat');self.assertEqual(self.layout.saved['chat'],[.4])

if __name__=='__main__':unittest.main()
