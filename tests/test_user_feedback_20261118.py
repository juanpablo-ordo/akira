"""Acceptance checks for the user's November 18 recorded desktop feedback."""
import tempfile,unittest
from unittest.mock import Mock,patch

class UserFeedbackQt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def test_molecules_and_status_replace_black_sprite_and_blank_badges(self):
        from desktop_qt import StudioWindow
        with tempfile.TemporaryDirectory() as folder:
            w=StudioWindow(folder,preview=True,start_actor=False)
            w.show();self.app.processEvents()
            try:
                self.assertTrue(w.avatars)
                self.assertTrue(all(getattr(a,'neural_visual',False) for a in w.avatars))
                self.assertFalse(w.avatars[0].grab().isNull())
                self.assertFalse(hasattr(w,'home_notices'))
                self.assertTrue(w.system_connectivity.text())
                self.assertTrue(w.resource_connectivity.text())
                self.assertEqual(w.mt5_retry.text(),'')
                self.assertEqual(w.analysis_refresh.text(),'')
                self.assertIn('MT5',w.analysis_refresh.accessibleName())
                self.assertEqual(w.settings_panel.use_mt5_button.text(),'')
                self.assertIn('MT5',w.settings_panel.use_mt5_button.accessibleName())
                from studio_widgets import SignalWave
                for wave in w.findChildren(SignalWave):
                    self.assertLessEqual(wave.timer.interval(),33)
            finally:
                w.close();self.app.processEvents()

    def test_one_pin_for_every_value_until_manual_relock(self):
        from desktop_qt import StudioWindow
        from PySide6.QtWidgets import QInputDialog
        with tempfile.TemporaryDirectory() as folder:
            w=StudioWindow(folder,preview=True,start_actor=False)
            try:
                with patch.object(w.privacy_pin,'configured',return_value=True),\
                     patch.object(w.privacy_pin,'verify',return_value=True) as verify,\
                     patch.object(QInputDialog,'getText',return_value=('123456',True)):
                    w.toggle_privacy()
                    verify.assert_called_once_with('123456')
                    self.assertTrue(w._privacy_unlocked)
                    self.assertFalse(w.private)
                    self.assertFalse(w.privacy_timer.isActive())
                    self.assertTrue(w.authorize_sensitive('Otra función'))
                    verify.assert_called_once()
                    w.privacy_activation(None)
                    self.assertTrue(w._privacy_unlocked)
                    w.toggle_privacy()
                    self.assertFalse(w._privacy_unlocked)
            finally:
                w.close();self.app.processEvents()

    def test_voice_speed_and_volume_apply_on_value_change(self):
        from desktop_qt import StudioWindow
        with tempfile.TemporaryDirectory() as folder:
            w=StudioWindow(folder,preview=True,start_actor=False)
            try:
                with patch.object(w,'load_voices'):
                    w.open_call()
                voice=Mock();voice.stop_event.is_set.return_value=False
                w.controller.voice=voice
                w.voice_rate.setValue(143)
                w.voice_volume.setValue(57)
                self.assertGreaterEqual(voice.configure_audio.call_count,2)
                opts=voice.configure_audio.call_args.kwargs
                self.assertEqual(opts['rate'],143)
                self.assertAlmostEqual(opts['volume'],.57)
                self.assertEqual(w.call_buttons['INICIAR LLAMADA'].accessibleName(),'INICIAR LLAMADA')
                self.assertEqual(w.call_buttons['INICIAR LLAMADA'].text(),'')
            finally:
                w.controller.voice=None
                w.close();self.app.processEvents()

if __name__=='__main__':
    unittest.main()
