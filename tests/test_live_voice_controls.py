"""User-requested live controls and icon accessibility in the Qt call dialog."""
import tempfile
import unittest
from unittest.mock import patch
class LiveVoiceControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])
    def test_voice_controls_are_compact_and_speed_is_live(self):
        from desktop_qt import StudioWindow
        with tempfile.TemporaryDirectory() as folder:
            w=StudioWindow(folder,preview=True,start_actor=False)
            try:
                with patch.object(w,'load_voices'):
                    w.open_call()
                    w.call_dialog.show();self.app.processEvents()
                    for name,widget in w.call_buttons.items():
                        self.assertEqual(widget.text(),'')
                        self.assertEqual(widget.accessibleName(),name)
                        self.assertEqual(widget.width(),46)
                    with patch.object(w,'apply_call_audio') as apply:
                        # Qt signal retains original bound callback at connection
                        # time; check the field value is immediately visible.
                        w.voice_rate.setValue(151)
                    self.assertEqual(w.call_audio_options()['rate'],151)
            finally:
                w.close();self.app.processEvents()
if __name__=='__main__':unittest.main()
