"""Theme preferences influence real Tk drawing without touching MT5."""
import unittest
from studio_theme import palette_for,ORIGINAL,apply_theme

class PaletteTests(unittest.TestCase):
    def test_original_is_default_and_does_not_change(self):
        self.assertEqual(palette_for({}),ORIGINAL)
        self.assertEqual(palette_for({'theme':'AKIRA Original'}),ORIGINAL)
    def test_presets_have_distinct_surface_colors(self):
        for name in ('Nebulosa','Océano','Carbono'):
            with self.subTest(name=name):
                self.assertNotEqual(palette_for({'theme':name})['PANEL'],ORIGINAL['PANEL'])
    def test_hex_overrides_are_local_and_validated(self):
        p=palette_for({'theme':'Océano','accent':'#A1B2C3','secondary':'not-a-color'})
        self.assertEqual(p['CYAN'],'#a1b2c3')
        self.assertEqual(p['PINK'],ORIGINAL['PINK'])
    def test_theme_updates_actual_palette_globals(self):
        import cyber_ui
        try:
            apply_theme({'theme':'Nebulosa','glow':10,'panel_texture':'Circuit','font_scale':120})
            self.assertEqual(cyber_ui.PANEL,palette_for({'theme':'Nebulosa'})['PANEL'])
            self.assertEqual(cyber_ui.STUDIO_GLOW,10)
            self.assertEqual(cyber_ui.STUDIO_TEXTURE,'Circuit')
            self.assertEqual(cyber_ui.STUDIO_FONT_SCALE,120)
        finally:apply_theme({'theme':'AKIRA Original'})

if __name__=='__main__':unittest.main()
