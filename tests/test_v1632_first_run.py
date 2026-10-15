"""An empty standalone AKIRA.exe must create a safe per-user configuration."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from settings import ensure_user_config, load_config
from windows_identity import application_root


class FirstRunTests(unittest.TestCase):
    def test_first_run_creates_observe_only_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = ensure_user_config(Path(tmp) / 'AKIRA')
            self.assertTrue(path.is_file())
            cfg = load_config(path)
            self.assertEqual(cfg['mode'], 'observe')
            self.assertEqual(cfg['expected_login'], 0)

    def test_existing_config_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'akira_config.json'
            path.write_text('{"my_custom_setting":"keep"}', encoding='utf-8')
            ensure_user_config(tmp)
            self.assertEqual(path.read_text(encoding='utf-8'), '{"my_custom_setting":"keep"}')

    def test_invalid_existing_config_is_not_silently_wiped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'akira_config.json'
            path.write_text('not valid JSON', encoding='utf-8')
            ensure_user_config(tmp)
            self.assertEqual(path.read_text(encoding='utf-8'), 'not valid JSON')

    def test_portable_windows_exe_root_is_localappdata_not_user_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / 'AppData' / 'Local'
            with patch.dict(os.environ, {'LOCALAPPDATA': str(local)}, clear=False), \
                 patch.object(sys, 'frozen', True, create=True), \
                 patch.object(sys, 'executable', str(Path(tmp) / 'Downloads' / 'AKIRA.exe')):
                os.environ.pop('AKIRA_APP_ROOT', None)
                self.assertEqual(application_root(), (local / 'AKIRA').resolve())

    def test_explicit_installer_root_still_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {'AKIRA_APP_ROOT': str(Path(tmp) / 'installed')}, clear=False), \
                 patch.object(sys, 'frozen', True, create=True):
                self.assertEqual(application_root(), (Path(tmp) / 'installed').resolve())

if __name__ == '__main__':
    unittest.main()
