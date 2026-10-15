"""Real filesystem transactions: preserve the old app even when Windows holds its folder."""
from contextlib import contextmanager
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from akira_version import BUILD_ID
import install_release as installer
from knowledge import KnowledgeStore
from settings import DEFAULT


@contextmanager
def held_directory(path):
    if os.name != 'nt':
        with patch('install_release.os.rename', side_effect=PermissionError('Directory held open')):
            yield
        return
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    create.restype = wintypes.HANDLE
    close = kernel.CloseHandle
    close.argtypes = (wintypes.HANDLE,)
    close.restype = wintypes.BOOL
    # Share read/write, exclude delete: this real handle prevents a Windows folder rename.
    handle = create(str(path), 0, 3, None, 3, 0x02000000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        yield
    finally:
        close(handle)


class ReleaseInstallerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='Akira actualización ')
        self.addCleanup(temp.cleanup)
        # Windows TEMP can use RUNNER~1 while the installer resolves runneradmin.
        self.root = Path(temp.name).resolve()
        self.source = self.root / 'payload'
        self.source.mkdir()
        self.runtime = self.root / '.akira_runtime'
        self.legacy = self.root / 'Local' / 'Akira'
        self.legacy.mkdir(parents=True)
        self.diag = self.root / 'diagnostic'
        self.diag.mkdir()
        self.shortcut = self.root / 'Desktop' / 'Akira.lnk'
        self.shortcut.parent.mkdir()
        self.shortcut.write_bytes(b'ORIGINAL SHORTCUT')
        self.next_shortcut = self.diag / 'Nueva_Akira.lnk'
        self.next_shortcut.write_bytes(b'NEW SHORTCUT')
        self.config = self.root / 'migrated.json'
        config = json.loads(json.dumps(DEFAULT))
        config['mode'] = 'observe'
        config['expected_login'] = 123456
        for path in (self.config, self.legacy / 'akira_config.json', self.source / 'akira_config.json'):
            path.write_text(json.dumps(config), encoding='utf-8')
        (self.source / 'Akira.py').write_text('# offline application fixture\n', encoding='utf-8')
        (self.source / 'akira_version.py').write_text('BUILD_ID=' + repr(BUILD_ID), encoding='utf-8')
        (self.source / 'VALIDACION_V12.json').write_text(json.dumps({'build': BUILD_ID, 'tests': 1}), encoding='utf-8')
        manifest = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.source.iterdir()}
        (self.source / 'PACKAGE_SHA256.json').write_text(json.dumps(manifest), encoding='utf-8')
        self.report = {'build': BUILD_ID, 'status': 'PASSED', 'exit_code': 0, 'child_exit_code': 0,
                       'collected': 1, 'tests_run': 1, 'failures': 0, 'errors': 0, 'skipped': 0}
        self.write_report()
        self.memory = KnowledgeStore(self.legacy)
        self.memory.remember('user', 'Memoria de la IA que debe conservarse')
        (self.legacy / 'state' / 'account.json').write_text('{"intents":{"CURRENT":{}}}', encoding='utf-8')

    def write_report(self):
        (self.diag / 'INSTALL_RESULT_AKIRA.json').write_text(json.dumps(self.report), encoding='utf-8')

    def prepare(self):
        result = installer.prepare_release(self.source, self.runtime, self.config, self.diag, self.legacy)
        return Path(result['root'])

    def activate(self, release):
        return installer.activate_release(self.runtime, release, self.diag, self.shortcut, self.next_shortcut)

    def test_directory_held_open_does_not_block_new_release_and_old_data_is_intact(self):
        original = (self.legacy / 'akira_config.json').read_bytes()
        with held_directory(self.legacy):
            release = self.prepare()
            self.activate(release)
        self.assertTrue(self.legacy.is_dir())
        self.assertEqual((self.legacy / 'akira_config.json').read_bytes(), original)
        self.assertEqual(KnowledgeStore(release).history(), self.memory.history())
        self.assertEqual((release / 'state' / 'account.json').read_bytes(), (self.legacy / 'state' / 'account.json').read_bytes())
        self.assertEqual(json.loads((release / 'akira_config.json').read_text())['expected_login'], 123456)

    def test_failed_validation_never_creates_release(self):
        self.report['status'] = 'FAILED'
        self.write_report()
        with self.assertRaisesRegex(ValueError, 'validación completa'):
            self.prepare()
        self.assertFalse((self.runtime / 'releases').exists())

    def test_altered_payload_is_rejected_before_copy(self):
        (self.source / 'Akira.py').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'alterado'):
            self.prepare()
        self.assertFalse((self.runtime / 'releases').exists())

    def test_copy_failure_keeps_original_app_pointer_and_shortcut(self):
        with patch('install_release.shutil.copy2', side_effect=PermissionError('copy denied')):
            with self.assertRaisesRegex(PermissionError, 'copy denied'):
                self.prepare()
        self.assertEqual(self.shortcut.read_bytes(), b'ORIGINAL SHORTCUT')
        self.assertFalse((self.runtime / 'active_install.json').exists())
        self.assertTrue((self.legacy / 'akira_config.json').is_file())

    def test_success_activates_new_release_and_next_update_selects_its_current_state(self):
        release = self.prepare()
        result = self.activate(release)
        self.assertEqual(result['status'], 'ACTIVATED')
        self.assertEqual(self.shortcut.read_bytes(), b'NEW SHORTCUT')
        self.assertEqual(installer.current_install(self.runtime, self.legacy), release)
        self.assertEqual(installer.read_json(self.diag / 'INSTALL_ACTIVATION.json')['status'], 'ACTIVATED')

    def test_launch_failure_rollback_restores_existing_pointer_and_shortcut_bytes(self):
        previous = self.prepare()
        self.activate(previous)
        old_pointer = (self.runtime / 'active_install.json').read_bytes()
        old_shortcut = self.shortcut.read_bytes()
        second_diag = self.root / 'second_diagnostic'
        second_diag.mkdir()
        self.diag = second_diag
        self.write_report()
        release = self.prepare()
        self.next_shortcut.write_bytes(b'SECOND SHORTCUT')
        self.activate(release)
        installer.rollback_release(self.runtime, self.diag)
        self.assertEqual((self.runtime / 'active_install.json').read_bytes(), old_pointer)
        self.assertEqual(self.shortcut.read_bytes(), old_shortcut)
        self.assertTrue(previous.is_dir())
        self.assertTrue(release.is_dir())

    def test_pointer_write_failure_restores_already_updated_shortcut(self):
        release = self.prepare()
        real = installer.atomic_bytes
        pointer = self.runtime / 'active_install.json'
        def fail_pointer(path, content):
            if Path(path).resolve() == pointer.resolve():
                raise PermissionError('pointer denied')
            return real(path, content)
        with patch('install_release.atomic_bytes', side_effect=fail_pointer):
            with self.assertRaisesRegex(PermissionError, 'pointer denied'):
                self.activate(release)
        self.assertEqual(self.shortcut.read_bytes(), b'ORIGINAL SHORTCUT')
        self.assertFalse(pointer.exists())

    def test_shortcut_write_failure_does_not_change_pointer(self):
        release = self.prepare()
        real = installer.atomic_bytes
        def fail_shortcut(path, content):
            if Path(path).resolve() == self.shortcut.resolve():
                raise PermissionError('shortcut held open')
            return real(path, content)
        with patch('install_release.atomic_bytes', side_effect=fail_shortcut):
            with self.assertRaisesRegex(PermissionError, 'shortcut held open'):
                self.activate(release)
        self.assertEqual(self.shortcut.read_bytes(), b'ORIGINAL SHORTCUT')
        self.assertFalse((self.runtime / 'active_install.json').exists())

    def test_rollback_removes_only_a_shortcut_created_by_this_install(self):
        self.shortcut.unlink()
        self.activate(self.prepare())
        installer.rollback_release(self.runtime, self.diag)
        self.assertFalse(self.shortcut.exists())
        self.assertFalse((self.runtime / 'active_install.json').exists())

    def test_rollback_never_overwrites_a_later_external_pointer(self):
        self.activate(self.prepare())
        pointer = self.runtime / 'active_install.json'
        pointer.write_bytes(b'CHANGED BY ANOTHER INSTALLER')
        with self.assertRaisesRegex(RuntimeError, 'no se sobrescribe'):
            installer.rollback_release(self.runtime, self.diag)
        self.assertEqual(pointer.read_bytes(), b'CHANGED BY ANOTHER INSTALLER')

    def test_incomplete_release_cannot_be_activated(self):
        release = self.prepare()
        (release / 'RELEASE_READY.json').unlink()
        with self.assertRaises(FileNotFoundError):
            self.activate(release)
        self.assertEqual(self.shortcut.read_bytes(), b'ORIGINAL SHORTCUT')

    def test_ready_code_altered_after_preparation_cannot_be_activated(self):
        release = self.prepare()
        (release / 'Akira.py').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'alterado'):
            self.activate(release)
        self.assertEqual(self.shortcut.read_bytes(), b'ORIGINAL SHORTCUT')

    def test_invalid_active_pointer_is_not_replaced_with_old_account_defaults(self):
        self.runtime.mkdir()
        (self.runtime / 'active_install.json').write_text(json.dumps({'root': str(self.legacy)}))
        with self.assertRaisesRegex(ValueError, 'activa registrada'):
            installer.current_install(self.runtime, self.legacy)

    def test_interrupted_old_folder_swap_recovers_its_backup(self):
        backup = self.legacy.parent / 'Akira.backup.pre11.previous'
        self.legacy.rename(backup)
        self.assertEqual(installer.current_install(self.runtime, self.legacy), backup.resolve())

    def test_process_detection_catches_regular_and_versioned_akira_but_not_other_python_apps(self):
        commands = (
            '"C:\\Users\\USUARIO_EJEMPLO\\.akira_runtime\\venv\\Scripts\\pythonw.exe" "C:\\Users\\USUARIO_EJEMPLO\\AppData\\Local\\Akira\\Akira.py"',
            'python.exe C:\\Users\\USUARIO_EJEMPLO\\.akira_runtime\\releases\\Akira_11_0_2_abc\\Akira.py',
            'pythonw.exe "C:\\Users\\Nombre con espacios\\Akira\\Akira.py" --preview',
            'python.exe C:\\Akira_FINAL_V7\\Akira_FINAL_V7.py',
            'python.exe Akira.py',
        )
        for command in commands:
            self.assertIsNotNone(re.search(installer.PROCESS_PATTERN, command), command)
        for command in ('python.exe C:\\Other\\report.py', 'python.exe C:\\Akira\\export.py',
                        'python.exe C:\\Akira\\tests\\test_akira.py', 'python.exe -c "print(1)"'):
            self.assertIsNone(re.search(installer.PROCESS_PATTERN, command), command)


if __name__ == '__main__':
    unittest.main()
