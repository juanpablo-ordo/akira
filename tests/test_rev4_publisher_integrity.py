"""Regresiones: el publicador no confunde archivos sin cambios con ausentes."""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PublisherIntegrityTests(unittest.TestCase):
    def test_secrets_module_in_full_source(self):
        self.assertTrue((ROOT / 'akira_secrets.py').is_file())

    def test_checks_index_not_changed_files(self):
        publisher = (ROOT / 'PUBLICAR_A_GITHUB_REV4.ps1').read_text(encoding='utf-8-sig')
        self.assertIn("'akira_secrets.py')", publisher)
        self.assertIn("ls-files --error-unmatch -- akira_secrets.py", publisher)
        self.assertNotIn("'akira_secrets.py' -notin $staged", publisher)
        self.assertIn("AKIRA_SECRETS\\.json", publisher)

    def test_git_can_track_module_without_a_staged_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def git(*args):
                return subprocess.run(['git', '-C', str(root), *args], text=True,
                                      capture_output=True, check=True).stdout.strip()
            git('init', '-q')
            git('config', 'user.email', 'test@example.invalid')
            git('config', 'user.name', 'Akira Test')
            (root / 'akira_secrets.py').write_text('def load(): return {}\n', encoding='utf-8')
            git('add', 'akira_secrets.py')
            git('commit', '-qm', 'initial')
            git('rm', '-q', 'akira_secrets.py')
            (root / 'akira_secrets.py').write_text('def load(): return {}\n', encoding='utf-8')
            git('add', '-A')
            self.assertEqual(git('diff', '--cached', '--name-only'), '')
            self.assertEqual(git('ls-files', '--error-unmatch', '--', 'akira_secrets.py'), 'akira_secrets.py')


if __name__ == '__main__':
    unittest.main()
