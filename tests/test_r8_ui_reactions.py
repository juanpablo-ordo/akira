"""Actual Tk regressions for key persistence, stable tables and state sprites."""
import hashlib,json,os,tempfile,tkinter as tk,unittest,threading
from pathlib import Path
from unittest.mock import patch

from avatar_animation import StateSprites
from akira_live2d import AkiraLive2D,AvatarDirector
from akira_expressions import get_catalog
from desktop import Desktop
from desktop_layout import PanelLayout,_descendants
from native_ui_check import settle_layout
from settings import DEFAULT,load_config

ROOT=Path(__file__).resolve().parents[1]


class StateAnimation(unittest.TestCase):
    def test_clock_blinks_without_switching_the_selected_expression(self):
        now=[0.0];director=AvatarDirector(get_catalog(ROOT),clock=lambda:now[0])
        selected=director.selected.id;director._next_blink=1
        now[0]=1;director.refresh();self.assertEqual(director.blink_frame,1)
        now[0]=1.07;director.refresh();self.assertEqual(director.blink_frame,2)
        now[0]=1.22;director.refresh();self.assertIsNone(director.blink_frame)
        now[0]=30;director.refresh()
        self.assertEqual(director.selected.id,selected);self.assertEqual(director.sequence,0)

    def test_eight_state_sprites_are_distinct_transparent_images(self):
        sprites=StateSprites(ROOT);seen=set()
        for index in range(8):
            image=sprites.image(index,170,125)
            self.assertIsNotNone(image.getbbox());self.assertEqual(image.getextrema()[3],(0,255))
            seen.add(hashlib.sha256(image.tobytes()).hexdigest())
        self.assertEqual(len(seen),8)

    def test_loading_ring_has_twelve_phases_without_creating_new_photos(self):
        root=tk.Tk();self.addCleanup(root.destroy);now=[0.0]
        director=AvatarDirector(get_catalog(ROOT),clock=lambda:now[0])
        avatar=AkiraLive2D(root,width=170,height=125,director=director);avatar.pack();root.update()
        director.busy(True);phases=set()
        with patch.object(avatar,'_paint',wraps=avatar._paint) as paint:
            for frame in range(12):
                now[0]=frame*.08+.001;avatar._loading_ring();phases.add(avatar.canvas.itemcget(avatar._spinner,'start'))
            paint.assert_not_called()
        self.assertEqual(len(phases),12)
        director.network(False);avatar._loading_ring()
        self.assertEqual(avatar._state_frame(),5);self.assertEqual(avatar.canvas.itemcget(avatar._spinner,'state'),'hidden')

    def test_a_destroyed_auxiliary_pane_cannot_break_future_resize_callbacks(self):
        root=tk.Tk();self.addCleanup(root.destroy)
        with tempfile.TemporaryDirectory() as temporary:
            layout=PanelLayout(root,Path(temporary)/'layout.json');pane=layout.pane(root,'closed');pane.destroy()
            layout.queue_restore('closed');layout.restore('closed')
            self.assertFalse(layout._restoring)


class DesktopBehavior(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.folder=Path(temporary.name)
        environment=patch.dict(os.environ,{'LOCALAPPDATA':str(self.folder/'profile')});environment.start();self.addCleanup(environment.stop)
        cfg=load_config(DEFAULT);cfg['desktop'].update(notifications=False,notification_popup=False,notification_sound=False)
        (self.folder/'akira_config.json').write_text(json.dumps(cfg),encoding='utf-8')
        self.app=None;self.addCleanup(lambda:self.app.close() if self.app else None)
        self.open()

    def open(self):
        self.root=tk.Tk();self.app=Desktop(self.root,self.folder,preview=True,start_actor=False)
        self.app.assistant.local_ai_status=lambda:{'ready':False,'phase':'DISABLED','detail':'Fixture sin modelo'}
        self.root.geometry('1024x640+0+0');self.root.update()

    def test_global_save_persists_masked_source_keys_across_application_restart(self):
        values={'COINGLASS_API_KEY':'CG-synthetic-r8-key','YOUTUBE_API_KEY':'AIzaSyntheticR8Key'}
        for key,value in values.items():
            entry=self.app.source_key_entries[key];entry.delete(0,'end');entry.insert(0,value)
        self.app.save_settings();self.app.close();self.app=None;self.open()
        for key,value in values.items():
            self.assertEqual(self.app.source_key_entries[key].get(),value)
            self.assertTrue(self.app.source_key_entries[key].cget('show'))
            self.assertIn('guardada',self.app.source_key_labels[key][0].cget('text'))

    def test_source_rows_keep_their_order_selection_and_scroll_as_age_changes(self):
        self.app.navigate(3);self.root.update()
        sources={f'feed:{i:02d}':{'fresh':True,'usable':True,'age_seconds':1} for i in range(40)}
        self.app.render_source_cards({'research':{'sources':sources}});self.root.update()
        tree=self.app.analysis_sources;tree.selection_set('feed:20');tree.yview_moveto(.5);self.root.update()
        order=tree.get_children();top=tree.yview()[0]
        changed={key:{**row,'age_seconds':2} for key,row in reversed(list(sources.items()))}
        with patch.object(tree,'delete',wraps=tree.delete) as delete:
            self.app.render_source_cards({'research':{'sources':changed}});self.root.update();delete.assert_not_called()
        self.assertEqual(tree.get_children(),order);self.assertEqual(tree.selection(),('feed:20',));self.assertAlmostEqual(tree.yview()[0],top,places=3)

    def test_moving_a_window_does_not_rebuild_its_layout(self):
        settle_layout(self.root)
        with patch.object(self.app,'_apply_responsive_shell',wraps=self.app._apply_responsive_shell) as layout:
            for offset in range(10):self.root.geometry(f'+{offset+10}+{offset+10}');self.root.update()
            settle_layout(self.root);layout.assert_not_called()

    def test_settings_sections_are_reachable_and_resource_close_leaves_no_empty_tail(self):
        self.app.open_resource_panel();self.root.update()
        self.assertEqual(str(self.app.settings_resources_tab),str(self.app.settings_notebook.select()))
        self.app.open_resource_panel();self.root.update()
        canvas=self.app.settings_resources_tab._scroll_canvas;canvas._sync_content();self.root.update()
        region=tuple(float(v) for v in str(canvas.cget('scrollregion')).split())
        self.assertAlmostEqual(region[-1],max(canvas.winfo_height(),canvas._content.winfo_reqheight()),delta=2)
        for tab in self.app.settings_notebook.tabs():
            self.app.settings_notebook.select(tab);self.root.update()
            self.assertEqual(self.app.settings_section.get(),self.app.settings_notebook.tab(tab,'text'))
        self.assertEqual(len(self.app.settings_notebook.tabs()),11)

    def test_resource_measurement_runs_outside_the_tk_thread(self):
        measured=threading.Event();observed=[];main=threading.get_ident()
        def sample():observed.append(threading.get_ident());measured.set();return {'akira_mb':12}
        with patch('resource_optimizer.process_usage',side_effect=sample):
            self.app.open_resource_panel();self.assertTrue(measured.wait(1))
        self.assertNotEqual(observed,[main])

    def test_avatar_reacts_to_typing_and_network_recovery_without_a_public_gallery(self):
        self.app.chat_input.set('hola Akira');self.assertEqual(self.app.avatars[0].director.expression,'listening')
        self.app.handle_service_reply({'connectivity_event':{'online':False}})
        self.assertEqual(self.app.avatars[0]._state_frame(),5)
        self.app.handle_service_reply({'connectivity_event':{'online':True}})
        self.assertTrue(self.app.avatars[0].director.online);self.assertEqual(self.app.avatars[0].director.expression,'waking')
        texts=[str(w.cget('text')).lower() for w in _descendants(self.root) if 'text' in w.keys()]
        self.assertFalse(any('108 caras' in text or 'ver las 108' in text for text in texts))

    def test_activating_real_execution_requires_confirmation_and_keeps_risk(self):
        risk=dict(self.app.cfg['risk']);self.app.preview=False;self.app.view={'connected':True,'account':{'login':123}}
        self.app.setting_vars['mode'].set('Operativa automática')
        with patch('cyber_ui.confirm_dialog',return_value=False):self.assertFalse(self.app.apply_settings_form())
        self.assertEqual(self.app.cfg['mode'],'observe');self.assertEqual(self.app.cfg['risk'],risk)
        self.app.preview=True


if __name__=='__main__':unittest.main()
