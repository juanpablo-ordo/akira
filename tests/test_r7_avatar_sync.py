import tkinter as tk
import unittest
import tempfile,json,os
from unittest.mock import patch
from pathlib import Path
from akira_live2d import AkiraLive2D,AvatarDirector
from akira_expressions import get_catalog


class SharedExpression(unittest.TestCase):
    def test_all_panels_and_call_share_face_and_playback_priority(self):
        root=tk.Tk();self.addCleanup(root.destroy)
        first=AkiraLive2D(root,width=150,height=120);first.pack()
        second=AkiraLive2D(root,width=150,height=120);second.pack()
        call=tk.Toplevel(root);third=AkiraLive2D(call,width=150,height=120,director=first.director);third.pack()
        root.update()
        for avatar in (first,second,third):avatar.set_expression('thinking','same event')
        self.assertEqual(first.director.sequence,1)
        self.assertEqual(len({a.selected.id for a in (first,second,third)}),1)
        first.director.playback(True)
        first.set_expression('idle','delayed chat reset')
        self.assertTrue(first.director.playing)
        self.assertEqual(first.selected.id,'AKIRA_046')
        first.director.level(.2)
        self.assertEqual(len({a.selected.id for a in (first,second,third)}),1)
        self.assertEqual(first.selected.id,'AKIRA_047')
        first.director.playback(False)
        self.assertEqual(first.expression,'listening')
        for i in range(108):first.set_expression(f'AKIRA_{i+1:03d}')
        self.assertEqual(first.selected.id,'AKIRA_108')
        self.assertLessEqual(len(first._photos),12)


class SourceSettingsPage(unittest.TestCase):
    def test_source_fields_are_in_a_selectable_notebook_page(self):
        from desktop import Desktop
        from settings import DEFAULT,load_config
        with tempfile.TemporaryDirectory() as temporary,patch.dict(os.environ,{'LOCALAPPDATA':temporary}):
            folder=Path(temporary);(folder/'akira_config.json').write_text(json.dumps(load_config(DEFAULT)),encoding='utf-8')
            root=tk.Tk();app=Desktop(root,folder,preview=True,start_actor=False)
            try:
                root.geometry('1024x640+0+0');app.navigate(6)
                app.settings_notebook.select(app.settings_sources_tab);root.update()
                self.assertEqual(str(app.settings_sources_tab),str(app.settings_notebook.select()))
                self.assertEqual(set(app.source_key_entries),{'COINGLASS_API_KEY','YOUTUBE_API_KEY'})
                self.assertTrue(all(e.winfo_ismapped() for e in app.source_key_entries.values()))
                self.assertTrue(all(e.cget('show') for e in app.source_key_entries.values()))
            finally:app.close()


if __name__=='__main__':unittest.main()
