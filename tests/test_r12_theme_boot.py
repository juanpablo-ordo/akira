import json,tempfile,tkinter as tk,unittest
from pathlib import Path
from desktop import Desktop
from settings import load_config,DEFAULT
from studio_theme import apply_theme,palette_for

class ThemeBootTests(unittest.TestCase):
    def test_custom_colors_are_applied_to_real_shell_and_restore_original(self):
        import cyber_ui
        with tempfile.TemporaryDirectory() as tmp:
            cfg=load_config(DEFAULT)
            cfg['assistant']['auto_install_local_ai']=False
            cfg['desktop'].update(notifications=False,notification_popup=False)
            cfg['studio'].update(theme='Océano',accent='#16dab6',secondary='#ef79be',font_scale=115,panel_texture='Circuit')
            folder=Path(tmp);(folder/'akira_config.json').write_text(json.dumps(cfg),encoding='utf-8')
            root=tk.Tk()
            app=None
            try:
                app=Desktop(root,folder,preview=True,start_actor=False)
                root.update_idletasks()
                wanted=palette_for(cfg['studio'])
                self.assertEqual(app.sidebar.cget('bg'),wanted['BG'])
                self.assertEqual(app.brand_title.cget('fg'),wanted['CYAN'])
                self.assertEqual(cyber_ui.STUDIO_TEXTURE,'Circuit')
                self.assertEqual(cyber_ui.STUDIO_FONT_SCALE,115)
                self.assertEqual(app.current_page_index,1)
            finally:
                if app:app.close()
                else:root.destroy()
                apply_theme(DEFAULT['studio'])

if __name__=='__main__':unittest.main()
