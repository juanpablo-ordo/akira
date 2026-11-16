"""Acceptance contracts from the 20-page AKIRA implementation plan.

Synthetic tests cover accessible application behavior; they are not substitutes
for real MT5 demo, microphone, two monitors, Authenticode or Android hardware.
"""
from pathlib import Path
from unittest.mock import patch
import unittest

ROOT=Path(__file__).resolve().parents[1]

class NativeScope(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def test_one_visible_market_workspace_contains_orders_positions_strategy_and_risk(self):
        from desktop_qt import StudioWindow
        from akira_version import DISPLAY_VERSION
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            window=StudioWindow(folder,preview=True,start_actor=False)
            window.show();self.app.processEvents()
            try:
                self.assertEqual(window.brand.text(),'AKIRA '+DISPLAY_VERSION)
                self.assertTrue(window.nav[1].isHidden())
                self.assertTrue(window.nav[2].isHidden())
                self.assertFalse(window.nav[3].isHidden())
                window.navigate(3)
                for name in ('analysis_connection_status','analysis_strategy_selector',
                             'analysis_pending_table','analysis_positions_table','analysis_risk_status'):
                    self.assertTrue(hasattr(window,name),name)
                self.assertEqual(window.analysis_strategy_selector.currentData(),window.strategy_selector.currentData())
                self.assertTrue(window.cloud_choice.isHidden())
                self.assertTrue(window.settings_panel.fields['studio.brand_name'][0].isHidden())
                self.assertIsNone(window.controller.actor)
            finally:
                window.close();self.app.processEvents()

    def test_research_only_hypothesis_cannot_be_applied_as_live_strategy(self):
        from desktop_qt import StudioWindow
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            window=StudioWindow(folder,preview=True,start_actor=False)
            try:
                index=window.strategy_selector.findData('LAB_BTC_BEAR_CONTINUATION_V1')
                self.assertGreaterEqual(index,0)
                window.analysis_strategy_selector.setCurrentIndex(index)
                with patch.object(window,'show_error') as warning,patch.object(window.controller,'save') as persist:
                    window.apply_strategy()
                    warning.assert_called_once()
                    persist.assert_not_called()
            finally:
                window.close();self.app.processEvents()

    def test_mobile_requires_private_tls_pin_and_explicit_user_confirmation(self):
        src=(ROOT/'mobile/src/com/akira/companion/CompanionClient.java').read_text('utf-8')
        android=(ROOT/'mobile/src/com/akira/companion/MainActivity.java').read_text('utf-8')
        server=(ROOT/'mobile_companion.py').read_text('utf-8')
        manifest=(ROOT/'mobile/AndroidManifest.xml').read_text('utf-8')
        self.assertIn('MessageDigest.isEqual(digest, fingerprint)',src)
        self.assertIn('new AlertDialog.Builder(this)',android)
        self.assertIn('Intent.ACTION_DIAL',android)
        self.assertIn("self.emit('mobile_action'",server)
        self.assertIn('android:allowBackup="false"',manifest)

if __name__=='__main__':
    unittest.main()
