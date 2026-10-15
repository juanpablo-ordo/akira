"""Regression: a build-time AI response does not prove the installed AI exists."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from installer import check_installed_ai as check


class InstalledAITests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder=Path(temporary.name)
        self.root=self.folder/'installed'
        self.model=self.root/'local_ai/models'/check.MODEL_NAME
        for name in ('AKIRA.exe','local_ai/bin/llama-server.exe','local_ai/cpu/llama-server.exe','unins000.exe'):
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'MZtest executable')
        self.model.parent.mkdir(parents=True,exist_ok=True)
        self.model.write_bytes(b'GGUFsmall synthetic fixture')
        digest=hashlib.sha256(self.model.read_bytes()).hexdigest()
        pinned=patch.object(check,'SHA',digest);pinned.start();self.addCleanup(pinned.stop)

    def test_verifies_actual_installed_bytes_and_uses_installed_cpu_server(self):
        with patch.object(check,'smoke') as inference:
            result=check.check_installed_ai(self.root)
        self.assertEqual(result['status'],'PASSED')
        self.assertFalse(result['model_downloaded_by_check'])
        inference.assert_called_once_with((self.root/'local_ai/cpu/llama-server.exe').resolve(),self.model.resolve())

    def test_model_deleted_after_setup_is_rejected_without_downloading(self):
        self.model.unlink()
        with patch.object(check,'smoke') as inference, self.assertRaises(FileNotFoundError):
            check.check_installed_ai(self.root)
        inference.assert_not_called()

    def test_truncated_or_changed_model_is_rejected(self):
        self.model.write_bytes(b'GGUFcorrupted bytes')
        with patch.object(check,'smoke') as inference, self.assertRaisesRegex(ValueError,'SHA-256'):
            check.check_installed_ai(self.root)
        inference.assert_not_called()

    def test_missing_cpu_engine_or_uninstaller_is_rejected(self):
        for name in ('local_ai/cpu/llama-server.exe','unins000.exe'):
            path=self.root/name;original=path.read_bytes();path.unlink()
            with self.subTest(name=name),self.assertRaises(FileNotFoundError):
                check.validate_installed_payload(self.root)
            path.write_bytes(original)

    def test_inference_failure_cannot_report_a_successful_installation(self):
        with patch.object(check,'smoke',side_effect=RuntimeError('no visible answer')):
            with self.assertRaisesRegex(RuntimeError,'no visible answer'):
                check.check_installed_ai(self.root)

    def test_native_install_failure_includes_log_and_existing_data_is_protected(self):
        setup=self.folder/'setup.exe';setup.write_bytes(b'MZtest')
        log=self.folder/'setup.log';log.write_text('No se pudo copiar la IA: disco lleno.',encoding='utf-8')
        with patch.object(check.subprocess,'run',return_value=Mock(returncode=1)) as run:
            with self.assertRaisesRegex(RuntimeError,'disco lleno'):
                check.run_installer(setup,self.folder/'fresh',log)
            arguments=run.call_args.args[0]
            self.assertIn('/VERYSILENT',arguments)
            self.assertIn('/NORESTART',arguments)
            run.reset_mock()
            with self.assertRaises(FileExistsError):
                check.run_installer(setup,self.root,log)
            run.assert_not_called()


if __name__=='__main__':
    unittest.main()
