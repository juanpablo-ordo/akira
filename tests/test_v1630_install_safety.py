"""Regression checks for safe release retirement and installer lifecycle."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from install_release import cleanup_old_releases

ROOT = Path(__file__).resolve().parent.parent


class InstallerLifecycleSafety(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.home = Path(self.t.name).resolve()
        self.runtime = self.home / '.akira_runtime'
        self.releases = self.runtime / 'releases'
        self.active = self.releases / 'Akira_active'
        self.old = self.releases / 'Akira_previous'
        for location in (self.active, self.old):
            location.mkdir(parents=True)
            for f in ('Akira.py', 'akira_version.py', 'akira_config.json'):
                (location / f).write_text('{}', encoding='utf-8')
        (self.active / 'RELEASE_READY.json').write_text('{}', encoding='utf-8')
        (self.old / 'state').mkdir()
        (self.old / 'state' / 'trades.json').write_text('{"saved":true}',encoding='utf-8')
        (self.runtime / 'active_install.json').write_text(json.dumps({'root':str(self.active)}),encoding='utf-8')
        self.backups = self.home / 'Akira_Datos_Conservados'

    def test_locked_old_release_is_deferred_without_affecting_active(self):
        original = Path.rename
        def locked(path, target):
            if path.resolve() == self.old.resolve():
                raise PermissionError('simulated Windows file lock')
            return original(path, target)
        with patch.object(Path, 'rename', autospec=True, side_effect=locked):
            result = cleanup_old_releases(self.runtime, self.backups)
        self.assertEqual(result['status'], 'PARTIAL_CLEANUP')
        self.assertEqual(result['deferred'][0]['stage'],'rename')
        self.assertTrue(self.old.is_dir())
        self.assertTrue(self.active.is_dir())
        self.assertEqual(json.loads((self.runtime/'active_install.json').read_text())['root'],str(self.active))

    def test_partial_delete_is_never_renamed_back_as_healthy_release(self):
        with patch('install_release.shutil.rmtree', side_effect=PermissionError('in use')):
            result = cleanup_old_releases(self.runtime, self.backups)
        self.assertEqual(result['status'],'PARTIAL_CLEANUP')
        self.assertEqual(result['deferred'][0]['stage'],'delete')
        self.assertFalse(self.old.exists())
        self.assertTrue(Path(result['deferred'][0]['quarantine']).is_dir())
        self.assertTrue(self.active.is_dir())

    def test_success_path_preserves_backup_and_active(self):
        result = cleanup_old_releases(self.runtime, self.backups)
        self.assertEqual(result['status'],'CLEANED')
        self.assertEqual(len(result['removed']),1)
        self.assertEqual(len(result['deferred']),0)
        self.assertEqual(list(self.backups.rglob('trades.json'))[0].read_text(),'{"saved":true}')
        self.assertTrue(self.active.is_dir())

    def test_no_start_before_installer_commit(self):
        source = (ROOT / 'INSTALL_AKIRA.ps1').read_text(encoding='utf-8-sig')
        self.assertNotIn('Start-Process -FilePath $akiraExe',source)
        self.assertLess(source.index('$installPhase=\'Confirmar activación completa\''),
                        source.index("$hostResult=[ordered]@{status='INSTALLED'"))
        self.assertIn('autostart=$false',source)

    def test_repeated_failed_install_is_not_offered_blindly(self):
        source=(ROOT/'AKIRA_Instalador.ps1').read_text(encoding='utf-8-sig')
        self.assertIn('VER DIAGNÓSTICO',source)
        self.assertIn('if ($script:installationFailed)',source)
        self.assertNotIn('REINTENTAR INSTALACIÓN',source)

    def test_uninstaller_has_two_confirmed_modes_and_worker_copy(self):
        source=(ROOT/'DESINSTALAR_AKIRA.ps1').read_text(encoding='utf-8-sig')
        for required in ('Invoke-AkiraCompleteRemoval','-EraseAll','CONSERVAR DATOS',
                         'ELIMINAR TODO','ELIMINAR AKIRA','AKIRA_UNINSTALL_WORKER_'):
            self.assertIn(required,source)
        self.assertIn('Copy-Item -LiteralPath $PSCommandPath -Destination $script:temporaryWorker',source)


    def test_native_self_check_writes_failure_diagnostics(self):
        source=(ROOT/'build_windows.py').read_text(encoding='utf-8')
        self.assertIn('NATIVE_SELF_CHECK_STDERR.log',source)
        self.assertIn('NATIVE_SELF_CHECK_TIMEOUT.txt',source)
        self.assertIn('capture_output=True',source)
        self.assertIn('result.returncode',source)


if __name__=='__main__':unittest.main()
