"""A partially copied Tcl/Tk tree is never accepted as proof of GUI readiness."""
import json
import tempfile
import unittest
from pathlib import Path
from ci_tcltk import _scan, MANIFEST, verify_snapshot, REQUIRED


class TclTkSnapshotContract(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for folder, names in REQUIRED.items():
            p = self.root / folder
            p.mkdir()
            for name in names:
                (p / name).write_text("stub data "+name, encoding="utf-8")
            for n in range(16):
                (p / f"extra{n}.tcl").write_text(f"stub {n}", encoding="utf-8")
        files = _scan(self.root)
        (self.root / MANIFEST).write_text(json.dumps({"schema": 1, "files": files}), encoding="utf-8")

    def test_complete_copy_has_reproducible_manifest(self):
        self.assertGreaterEqual(verify_snapshot(self.root), 15)

    def test_missing_button_is_rejected_not_skipped(self):
        (self.root / 'tk8.6' / 'button.tcl').unlink()
        with self.assertRaisesRegex(RuntimeError, 'button.tcl'):
            verify_snapshot(self.root)

    def test_corrupt_resource_is_detected_by_digest(self):
        (self.root / 'tcl8.6' / 'init.tcl').write_text('tampered', encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'init.tcl'):
            verify_snapshot(self.root)

    def test_added_file_is_also_detected(self):
        (self.root / 'tk8.6' / 'untracked.tcl').write_text('surprise', encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'untracked.tcl'):
            verify_snapshot(self.root)


if __name__ == '__main__':
    unittest.main()
