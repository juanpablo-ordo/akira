"""Offline regression checks: never delete active releases or user data."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from install_release import (excluded_from_release, inspect_install_diagnostics,
                             cleanup_install_diagnostics, checked_manifest)

ROOT = Path(__file__).resolve().parent.parent


class StorageCleanupTests(unittest.TestCase):
    def setUp(self):
        work=tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.home=Path(work.name)
        self.runtime=self.home/'.akira_runtime'
        self.active=self.runtime/'releases'/'Akira_active'
        self.active.mkdir(parents=True)
        (self.active/'RELEASE_READY.json').write_text('{}')
        (self.runtime/'active_install.json').write_text(json.dumps({'root':str(self.active)}))
        self.diagnostics=self.home/'Akira_Diagnostico_Instalacion'
        self.diagnostics.mkdir()
        self.current=self.diag(99,'INSTALLED')

    def diag(self,i,status='FAILED'):
        folder=self.diagnostics/f'20261013_{i:06d}.{i:08x}'
        folder.mkdir()
        (folder/'INSTALACION_COMPLETA.log').write_text('test')
        (folder/'INSTALL_HOST_RESULT.json').write_text(json.dumps({'status':status}))
        return folder

    def test_protect_active_diagnostic_and_keep_latest_success_failure(self):
        old_success=[self.diag(i,'INSTALLED') for i in range(1,5)]
        old_failure=[self.diag(i+10,'FAILED') for i in range(1,5)]
        plan=inspect_install_diagnostics(self.runtime,self.current)
        self.assertEqual(len(plan['removable']),4)
        done=cleanup_install_diagnostics(self.runtime,self.current)
        self.assertEqual(done['status'],'CLEANED')
        self.assertEqual(len(done['removed']),4)
        self.assertTrue(self.current.exists())
        self.assertTrue(self.active.exists())
        self.assertTrue(old_success[-1].exists())
        self.assertTrue(old_failure[-1].exists())
        self.assertFalse(old_success[0].exists())
        self.assertFalse(old_failure[0].exists())

    def test_no_active_pointer_does_not_delete_anything(self):
        first=self.diag(1)
        second=self.diag(2)
        third=self.diag(3)
        (self.runtime/'active_install.json').unlink()
        with self.assertRaisesRegex(ValueError,'activada'):
            cleanup_install_diagnostics(self.runtime,self.current)
        self.assertTrue(first.exists() and second.exists() and third.exists())

    def test_protect_unknown_user_files_and_data(self):
        files=[self.diag(i) for i in range(1,7)]
        (files[0]/'AKIRA_SECRETS.json').write_text('do not touch')
        (files[1]/'user.db').write_bytes(b'user data')
        (files[2]/'state').mkdir()
        cleanup_install_diagnostics(self.runtime,self.current)
        for item in files[:3]:
            self.assertTrue(item.is_dir())

    def test_unknown_directory_name_is_never_deleted(self):
        unknown=self.diagnostics/'Notas_de_usuario'
        unknown.mkdir()
        (unknown/'nota.txt').write_text('keep')
        for i in range(1,7):self.diag(i)
        cleanup_install_diagnostics(self.runtime,self.current)
        self.assertTrue(unknown.exists())

    def test_symlink_is_protected(self):
        outside=self.home/'outside'
        outside.mkdir()
        (outside/'personal.txt').write_text('keep')
        for i in range(1,7):self.diag(i)
        trap=self.diagnostics/'20261013_000123.0000007b'
        try:
            trap.symlink_to(outside,target_is_directory=True)
        except (OSError,NotImplementedError):
            self.skipTest('symlinks unavailable')
        cleanup_install_diagnostics(self.runtime,self.current)
        self.assertTrue(outside.joinpath('personal.txt').exists())
        self.assertTrue(trap.is_symlink())

    def test_cleanup_failure_is_reported_not_silent(self):
        for i in range(1,8):self.diag(i)
        with patch('install_release.shutil.rmtree',side_effect=PermissionError('locked')):
            result=cleanup_install_diagnostics(self.runtime,self.current)
        self.assertEqual(result['status'],'PARTIAL_CLEANUP')
        self.assertGreater(len(result['deferred']),0)

    def test_legacy_previews_not_copied_to_runtime(self):
        self.assertTrue(excluded_from_release('VALIDACIONES_ANTERIORES/16_2/log.json'))
        self.assertTrue(excluded_from_release('INTERFAZ_16_2_1/old.png'))
        self.assertTrue(excluded_from_release('EJEMPLOS_INFORMES/sample.pdf'))
        self.assertFalse(excluded_from_release('Akira.py'))
        self.assertFalse(excluded_from_release('state/reports.json'))
        self.assertFalse(excluded_from_release('desktop_layout.py'))
        self.assertFalse(excluded_from_release('akira_config.json'))

    def test_installer_uninstaller_lifecycle_hooks(self):
        install=(ROOT/'INSTALL_AKIRA.ps1').read_text(encoding='utf-8-sig')
        uninstall=(ROOT/'DESINSTALAR_AKIRA.ps1').read_text(encoding='utf-8-sig')
        self.assertIn("@('inspect-maintenance'",install)
        self.assertIn("@('cleanup-maintenance'",install)
        self.assertLess(install.index('$installCommitted=$true'),install.index("@('cleanup-maintenance'"))
        self.assertIn("(Join-Path $Plan.context.runtime 'venv')",uninstall)
        self.assertIn("foreach ($venvName in @('venv','.venv','ai'))",uninstall)
        self.assertIn("(Join-Path $Plan.context.runtime 'ai')",uninstall)


if __name__=='__main__': unittest.main()
