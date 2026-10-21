"""Reproduce Windows CI path, native geometry and Tcl library regressions."""
from tk_runtime import create_root
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from installer.check_tk_runtime import copy_libraries


class TkRuntimeCopyTests(unittest.TestCase):
    def fixture(self,root):
        source=root/'python/tcl'
        files={'tcl8.6/init.tcl':'# Tcl initialization',
               'tcl8.6/auto.tcl':'# library loader',
               'tcl8.6/tclIndex':'# command index',
               'tk8.6/tk.tcl':'# Tk initialization',
               'tk8.6/ttk/ttk.tcl':'source -encoding utf-8 [file join $::ttk::library progress.tcl]',
               'tk8.6/ttk/progress.tcl':'# native progress support'}
        for name,body in files.items():
            path=source/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(body,encoding='utf-8')
        return source

    def test_missing_progress_file_fails_before_creating_or_publishing_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=self.fixture(root);destination=root/'verified'
            (source/'tk8.6/ttk/progress.tcl').unlink()
            with self.assertRaisesRegex(FileNotFoundError,'progress.tcl'):copy_libraries(source,destination)
            self.assertFalse(destination.exists())

    def test_missing_tcl_loader_fails_before_copying_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=self.fixture(root);destination=root/'verified'
            (source/'tcl8.6/auto.tcl').unlink()
            with self.assertRaisesRegex(FileNotFoundError,'auto.tcl'):copy_libraries(source,destination)
            self.assertFalse(destination.exists())

    def test_every_referenced_ttk_script_must_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=self.fixture(root)
            (source/'tk8.6/ttk/ttk.tcl').write_text('source [file join $::ttk::library treeview.tcl]',encoding='utf-8')
            with self.assertRaisesRegex(FileNotFoundError,'treeview.tcl'):copy_libraries(source,root/'verified')

    def test_verified_copy_is_independent_of_the_host_python_files(self):
        with tempfile.TemporaryDirectory(prefix='Akira Windows ñ ') as tmp:
            root=Path(tmp);source=self.fixture(root);destination=root/'verified'
            report=copy_libraries(source,destination)
            self.assertEqual(report['verified_files'],6)
            for path in source.rglob('*.tcl'):
                copied=destination/path.relative_to(source)
                self.assertEqual(path.read_bytes(),copied.read_bytes())
            (source/'tk8.6/ttk/progress.tcl').unlink()
            self.assertTrue((Path(report['tk_library'])/'ttk/progress.tcl').is_file())

    def test_corrupt_copy_is_rejected_without_modifying_the_original(self):
        import shutil
        real=shutil.copytree
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=self.fixture(root);destination=root/'verified'
            def corrupt(src,dst,*args,**kwargs):
                result=real(src,dst,*args,**kwargs)
                if Path(src).name=='tk8.6':(Path(dst)/'ttk/progress.tcl').write_text('corrupt',encoding='utf-8')
                return result
            with patch('installer.check_tk_runtime.shutil.copytree',side_effect=corrupt):
                with self.assertRaisesRegex(RuntimeError,'no coincide'):copy_libraries(source,destination)
            self.assertFalse(destination.exists())
            self.assertEqual((source/'tk8.6/ttk/progress.tcl').read_text(),'# native progress support')


class NativeGeometryTests(unittest.TestCase):
    def test_windows_titlebar_timer_never_reenters_geometry_processing(self):
        import ctypes
        from types import SimpleNamespace
        from unittest.mock import Mock
        import windows_identity
        window=Mock()
        window.winfo_id.return_value=123
        window.update_idletasks.side_effect=AssertionError('Nested Tk geometry loop')
        parent=Mock(return_value=456);dwm=Mock(return_value=0)
        libraries=SimpleNamespace(user32=SimpleNamespace(GetParent=parent),
            dwmapi=SimpleNamespace(DwmSetWindowAttribute=dwm))
        with patch.object(windows_identity,'os',SimpleNamespace(name='nt')),patch.object(ctypes,'windll',libraries,create=True):
            self.assertTrue(windows_identity.apply_dark_titlebar(window))
        window.update_idletasks.assert_not_called()
        self.assertEqual(dwm.call_count,3)
        self.assertEqual(dwm.call_args_list[0].args[0],456)

    def test_native_measurement_accepts_small_buttons_and_rejects_both_axes_of_clipping(self):
        import tkinter as tk
        from native_ui_check import control_geometry
        root=create_root()
        try:
            root.geometry('400x250+0+0')
            for size in (-7,-11,-16):
                button=tk.Button(root,text='OCULTAR',font=('DejaVu Sans',size),
                                 borderwidth=0,highlightthickness=1,padx=5,pady=3)
                button.pack();root.update()
                width,height=button.winfo_reqwidth(),button.winfo_reqheight()
                result=control_geometry(root,button,True)
                self.assertTrue(result['passed'],result)
                self.assertEqual((int(button.cget('width')),int(button.cget('height'))),(0,0))
                button.pack_forget();button.place(x=5,y=5,width=width-12,height=height)
                root.update_idletasks();self.assertFalse(control_geometry(root,button,True)['readable'])
                button.place_configure(width=width,height=height-6)
                root.update_idletasks();self.assertFalse(control_geometry(root,button,True)['readable'])
                button.destroy()
        finally:root.destroy()


if __name__=='__main__':unittest.main()
