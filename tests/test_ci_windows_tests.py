"""Ensure that splitting the Windows regression suite cannot silently omit tests."""
import tempfile
import unittest
from pathlib import Path
from ci_windows_tests import GUI_MODULES, test_plan as build_test_plan, commands


class WindowsCiContract(unittest.TestCase):
    def test_all_test_modules_are_in_exactly_one_group(self):
        regular, gui = build_test_plan()
        discovered = {p.name for p in (Path(__file__).resolve().parent).glob('test_*.py')}
        self.assertEqual(set(regular) | set(gui), discovered)
        self.assertFalse(set(regular) & set(gui))
        self.assertEqual(len(gui), len(GUI_MODULES))

    def test_every_gui_module_gets_its_own_python_process(self):
        plan = commands()
        self.assertEqual(len(plan), 1 + len(GUI_MODULES))
        for file_name in GUI_MODULES:
            matching = [cmd for _, cmd in plan if f'tests/{file_name}' in cmd]
            self.assertEqual(len(matching), 1)
            self.assertIn('--junitxml=diagnostics/GUI_' + Path(file_name).stem + '.xml', matching[0])
        non_gui = plan[0][1]
        for file_name in GUI_MODULES:
            self.assertIn('--ignore=tests/' + file_name, non_gui)

    def test_new_tk_test_requires_explicit_process_isolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            tests = Path(tmp) / 'tests'; tests.mkdir()
            for name in GUI_MODULES:
                (tests / name).write_text('pass', encoding='utf-8')
            (tests / 'test_simple.py').write_text('def test_ok(): assert True', encoding='utf-8')
            (tests / 'test_another_gui.py').write_text('import tkinter as tk\nr=tk.Tk()', encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'sin proceso aislado'):
                build_test_plan(Path(tmp))
