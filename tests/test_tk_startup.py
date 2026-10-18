"""Real Tcl interpreters: initialize library loading before loading Tk."""
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import ttk
import unittest
from tk_runtime import create_root,initialize_tk,create_interpreter


class TclBootstrapTests(unittest.TestCase):
    def test_missing_lazy_loader_is_initialized_before_native_tk(self):
        window=create_interpreter()
        try:
            if window.tk.call('info','commands','::tcl_findLibrary'):
                window.tk.call('rename','::tcl_findLibrary','')
            window.tk.setvar('auto_index(tcl_findLibrary)',
                'error {invalid command name "tcl_findLibrary"}')
            self.assertFalse(window.tk.call('info','commands','::tcl_findLibrary'))
            initialize_tk(window)
            window.withdraw()
            self.assertTrue(window._tkloaded)
            self.assertTrue(window.tk.call('info','commands','::tcl_findLibrary'))
            ttk.Progressbar(window,maximum=10,value=5).pack()
            tk.Button(window,text='Inicialización nativa').pack()
            window.update_idletasks()
            self.assertFalse(window._akira_tk_bootstrap['already_loaded'])
        finally:
            if window.tk.call('info','commands','destroy'):window.destroy()

    def test_missing_loader_file_is_rejected_before_loading_tk(self):
        with tempfile.TemporaryDirectory() as tmp:
            window=create_interpreter()
            original=window.tk.getvar('tcl_library')
            try:
                window.tk.setvar('tcl_library',str(Path(tmp)))
                with self.assertRaisesRegex(FileNotFoundError,'auto.tcl'):initialize_tk(window)
                self.assertFalse(window._tkloaded)
            finally:window.tk.setvar('tcl_library',original)

    def test_sequential_interpreters_keep_their_own_valid_loader(self):
        for _ in range(12):
            window=create_root()
            try:
                window.withdraw()
                proof=window._akira_tk_bootstrap
                self.assertTrue(Path(proof['loader']).is_file())
                self.assertTrue(window.tk.call('info','commands','::tcl_findLibrary'))
                self.assertEqual(proof['tk'],str(window.tk.call('package','provide','Tk')))
            finally:window.destroy()


class TransientWindowsLibraryRead(unittest.TestCase):
    def test_observed_native_read_error_recovers_using_same_readable_library(self):
        from unittest.mock import Mock,patch
        import tk_runtime
        with tempfile.TemporaryDirectory() as t:
            (Path(t)/'init.tcl').write_text('# intact selected Python library')
            error=tk.TclError('init.tcl: couldn\'t read file "init.tcl": No error');window=Mock();window._akira_tk_bootstrap={}
            with patch.object(tk_runtime,'_WINDOWS_BOOTSTRAP',True),patch.dict('os.environ',{'TCL_LIBRARY':t}),patch('tk_runtime.tk.Tk',side_effect=[error,window]) as create,patch('tk_runtime.initialize_tk',return_value=window),patch('tk_runtime.time') as timer,patch('tk_runtime.gc'):
                self.assertIs(create_root(),window)
            self.assertEqual(create.call_count,2);timer.sleep.assert_called_once_with(.05);self.assertEqual(window._akira_tk_bootstrap['initialization_attempts'],2)
    def test_missing_or_incompatible_libraries_are_not_hidden_by_retry(self):
        from unittest.mock import patch
        import tk_runtime
        for message in ('init.tcl: couldn\'t read file "init.tcl": No error','init.tcl: version conflict for package Tcl'):
            with self.subTest(message=message),tempfile.TemporaryDirectory() as t,patch.object(tk_runtime,'_WINDOWS_BOOTSTRAP',True),patch.dict('os.environ',{'TCL_LIBRARY':t}),patch('tk_runtime.tk.Tk',side_effect=tk.TclError(message)) as create,patch('tk_runtime.time') as timer:
                with self.assertRaises(tk.TclError):create_root()
                create.assert_called_once();timer.sleep.assert_not_called()
    def test_persistent_native_read_error_stops_after_three_attempts(self):
        from unittest.mock import patch
        import tk_runtime
        with tempfile.TemporaryDirectory() as t:
            (Path(t)/'init.tcl').write_text('# intact selected Python library')
            with patch.object(tk_runtime,'_WINDOWS_BOOTSTRAP',True),patch.dict('os.environ',{'TCL_LIBRARY':t}),patch('tk_runtime.tk.Tk',side_effect=tk.TclError('init.tcl: couldn\'t read file "init.tcl": No error')) as create,patch('tk_runtime.time') as timer,patch('tk_runtime.gc'):
                with self.assertRaisesRegex(tk.TclError,'No error'):create_root()
            self.assertEqual(create.call_count,3);self.assertEqual(timer.sleep.call_count,2)
