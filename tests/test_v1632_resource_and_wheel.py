"""Regressions: wheel events in a Toplevel and functional resource presets."""
from tk_runtime import create_root
import json, tempfile, unittest, tkinter as tk
from pathlib import Path
from resource_optimizer import profile_budget, ollama_limits, PROFILES
from settings import DEFAULT, load_config
from settings_effects import validate_form
from desktop_layout import scroll_frame

class ResourcePresetRegressions(unittest.TestCase):
    def test_preset_knobs_are_different_and_valid(self):
        profiles=[profile_budget(k) for k in PROFILES]
        self.assertEqual(len({p['model_context_tokens'] for p in profiles}),3)
        self.assertTrue(profiles[0]['model_use_gpu'])
        self.assertFalse(profiles[2]['model_use_gpu'])
        for name in PROFILES:
            cfg=load_config(DEFAULT)
            cfg['desktop'].update(profile_budget(name),performance_profile=name)
            self.assertEqual(validate_form(cfg)['desktop']['performance_profile'],name)
            settings,keep=ollama_limits(cfg)
            if name=='Ahorro de energía':
                self.assertEqual(keep,'0s');self.assertEqual(settings['num_gpu'],0)
    def test_new_install_does_not_auto_install_ollama(self):
        cfg=load_config(DEFAULT)
        self.assertFalse(cfg['assistant']['auto_install_local_ai'])

class WindowWheelRegressions(unittest.TestCase):
    def test_mousewheel_over_notification_card_in_dialog(self):
        try:r=create_root()
        except tk.TclError:self.skipTest('Tk graphical display required')
        self.addCleanup(r.destroy);r.withdraw()
        win=tk.Toplevel(r);win.geometry('430x280+40+40')
        shell,body=scroll_frame(win,'#071522');shell.pack(fill='both',expand=True)
        cards=[]
        for i in range(60):
            w=tk.Label(body,text='NOTIFICACION '+str(i),height=2)
            w.pack(fill='x');cards.append(w)
        r.update_idletasks();r.update()
        canvas=shell._scroll_canvas
        self.assertLess(canvas.yview()[0],.01)
        # The event is sent to the *card*, not to its scrollbar or the root.
        cards[1].event_generate('<MouseWheel>',delta=-120)
        r.update()
        for i in range(9):r.after(20,r.update)
        self.assertGreater(canvas.yview()[0],0.001)

if __name__=='__main__':unittest.main()
