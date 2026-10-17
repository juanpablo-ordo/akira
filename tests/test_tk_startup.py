"""Real Tcl interpreters: initialize library loading before loading Tk."""
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import ttk
import unittest
from tk_runtime import create_root,initialize_tk


class TclBootstrapTests(unittest.TestCase):
    def test_missing_lazy_loader_is_initialized_before_native_tk(self):
        window=tk.Tk(useTk=False)
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
            window=tk.Tk(useTk=False)
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
