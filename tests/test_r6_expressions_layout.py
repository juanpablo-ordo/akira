"""Artwork and actual Tk integration regressions for the user's R6 request."""
from tk_runtime import create_root
from pathlib import Path
import json
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

from akira_expressions import ExpressionCatalog, STATE_GROUPS, MIN_EXPRESSIONS
from akira_live2d import AkiraLive2D, expression_for_voice_event
from desktop_layout import PanelLayout, constrained_sashes, fitted_geometry

ROOT = Path(__file__).resolve().parents[1]


class CatalogTests(unittest.TestCase):
    def test_all_108_illustrations_decode_and_have_distinct_visible_pixels(self):
        result = ExpressionCatalog(ROOT).validate_artwork()
        self.assertEqual(result['count'], 108)
        self.assertEqual(result['distinct_cells'], 108)
        self.assertTrue(result['transparent'])

    def test_every_state_uses_new_drawings_and_every_expression_is_selectable(self):
        catalog = ExpressionCatalog(ROOT)
        self.assertEqual(len({entry.label for entry in catalog.entries}), 108)
        for state in STATE_GROUPS:
            self.assertTrue(catalog.candidates(state), state)
            self.assertIn(catalog.choose(state).id, catalog.by_id)
        for entry in catalog.entries:
            self.assertEqual(catalog.choose(entry.id), entry)

    def test_no_stretched_or_empty_thumbnails_at_sidebar_and_call_sizes(self):
        catalog = ExpressionCatalog(ROOT)
        for width, height in ((94, 66), (150, 90), (260, 220), (900, 130)):
            for entry in catalog.entries:
                image = catalog.image(entry, width, height)
                self.assertLessEqual(image.width, width)
                self.assertLessEqual(image.height, height)
                self.assertLess(abs(image.width / image.height - 1), .025)
                self.assertIsNotNone(image.getbbox())
        self.assertLessEqual(len(catalog._atlases), 2)

    def test_an_incomplete_catalog_is_rejected_instead_of_reusing_old_faces(self):
        original = json.loads((ROOT / 'assets/expressions/catalog.json').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'assets/expressions'
            folder.mkdir(parents=True)
            original['expressions'] = original['expressions'][:9]
            (folder / 'catalog.json').write_text(json.dumps(original, ensure_ascii=False), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, '99'):
                ExpressionCatalog(tmp)

    def test_voice_listening_has_a_dedicated_expression(self):
        self.assertEqual(expression_for_voice_event('state', 'Micrófono activo, escuchando'), 'listening')
        self.assertEqual(expression_for_voice_event('speaking'), 'talking')

    def test_new_reaction_groups_are_used_by_conversations(self):
        from akira_live2d import expression_for_reply
        self.assertEqual(expression_for_reply('Estoy aquí para escucharte.'), 'caring')
        self.assertEqual(expression_for_reply('¡Qué sorpresa! No me lo esperaba.'), 'surprised')
        self.assertEqual(expression_for_reply('Cuéntame más sobre eso.'), 'curious')
        self.assertEqual(expression_for_reply('¡Lo lograste, bien hecho!'), 'celebrating')


class LayoutBounds(unittest.TestCase):
    def test_large_monitor_ratios_do_not_hide_laptop_panes(self):
        positions = constrained_sashes(740, (.02, .98), (170, 190, 230))
        self.assertGreaterEqual(positions[0], 170)
        self.assertGreaterEqual(positions[1] - positions[0], 190 + 14)
        self.assertLessEqual(positions[1], 740 - 230 - 14)

    def test_small_screens_keep_the_whole_window_in_bounds(self):
        for sw, sh in ((640, 480), (800, 600), (1024, 600), (1366, 768)):
            width, height, mw, mh = fitted_geometry(1600, 1000, sw, sh)
            self.assertLessEqual(width, sw - 32)
            self.assertLessEqual(height, sh - 80)
            self.assertLessEqual(mw, width)
            self.assertLessEqual(mh, height)


class NativeBuildDiagnostics(unittest.TestCase):
    def test_windowed_failure_uses_json_when_stderr_is_empty(self):
        from build_windows import read_self_check_report
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'NATIVE_SELF_CHECK.json'
            path.write_text(json.dumps({'status':'FAILED','error':'No se completó compact_controls'},ensure_ascii=False),encoding='utf-8')
            for code in (0,1):
                with self.subTest(code=code),self.assertRaisesRegex(RuntimeError,'compact_controls'):
                    read_self_check_report(path,code,'')

    def test_missing_or_invalid_report_never_passes_with_a_zero_exit(self):
        from build_windows import read_self_check_report
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'NATIVE_SELF_CHECK.json'
            for contents in (None,'not JSON','[]'):
                if contents is not None:path.write_text(contents,encoding='utf-8')
                with self.subTest(contents=contents),self.assertRaisesRegex(RuntimeError,'ausente o ilegible'):
                    read_self_check_report(path,0)

    def test_success_requires_both_report_and_zero_exit(self):
        from build_windows import read_self_check_report
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'NATIVE_SELF_CHECK.json'
            expected={'status':'PASSED','build':'AKIRA_16_3_4_R7'}
            path.write_text(json.dumps(expected),encoding='utf-8')
            self.assertEqual(read_self_check_report(path,0),expected)
            with self.assertRaisesRegex(RuntimeError,'Código de salida: 1'):
                read_self_check_report(path,1)


class TkRegressions(unittest.TestCase):
    def setUp(self):
        try:
            self.root = create_root()
        except tk.TclError:
            self.skipTest('A graphical Tk display is required')
        self.addCleanup(self.root.destroy)

    def test_all_108_faces_are_actually_displayable_with_bounded_cache(self):
        avatar = AkiraLive2D(self.root, width=170, height=125)
        avatar.pack()
        self.root.update()
        self.assertTrue(avatar.winfo_ismapped())
        seen = set()
        for entry in avatar.catalog.entries:
            avatar.set_expression(entry.id)
            self.assertEqual(avatar.selected.id, entry.id)
            self.assertTrue(avatar.canvas.itemcget(avatar.sprite, 'image'))
            seen.add(avatar.selected.id)
        self.assertEqual(len(seen), 108)
        self.assertLessEqual(len(avatar._photos), 12)
        selected = avatar.selected.id
        avatar.configure(width=350, height=160)
        self.root.update_idletasks()
        avatar._resize_frames()
        self.assertEqual(avatar.selected.id, selected)
        avatar.destroy()
        self.assertTrue(avatar._closed)

    def test_nested_dividers_do_not_restore_during_parent_drag(self):
        with tempfile.TemporaryDirectory() as tmp:
            layout = PanelLayout(self.root, Path(tmp) / 'layout.json')
            parent = layout.pane(self.root, 'outer')
            child = layout.pane(parent, 'inner')
            parent.add(child)
            child.add(tk.Frame(child))
            child.add(tk.Frame(child))
            layout.dragging.add('outer')
            layout.queue_restore('inner')
            self.assertNotIn('inner', layout.restore_jobs)

    def test_compact_controls_accept_small_fonts_and_reject_clipping(self):
        from native_ui_check import control_geometry
        self.root.tk.call('tk','scaling',1.0)
        self.root.geometry('400x250+0+0')
        control=tk.Button(self.root,text='OCULTAR',font=('DejaVu Sans',-7),
            borderwidth=0,highlightthickness=1,padx=5,pady=3)
        control.pack()
        title=tk.Label(self.root,text='¿Qué necesitas?',font=('DejaVu Sans',-11),wraplength=300)
        title.pack()
        self.root.update()
        self.assertLess(control.winfo_width(),100)
        self.assertLess(title.winfo_reqwidth(),150)
        self.assertTrue(control_geometry(self.root,control,True)['passed'])
        self.assertTrue(control_geometry(self.root,title,True)['passed'])
        control.configure(width=1)
        self.root.update_idletasks()
        self.assertFalse(control_geometry(self.root,control,True)['readable'])
        control.configure(width=0)
        control.pack_forget();control.place(x=390,y=0)
        self.root.update_idletasks()
        self.assertFalse(control_geometry(self.root,control,True)['inside'])


if __name__ == '__main__':
    unittest.main()
