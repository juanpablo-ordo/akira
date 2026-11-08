"""Regression tests for field observations; synthetic GPU output and Qt widgets."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

class NvidiaDetection(unittest.TestCase):
    def test_5060ti_memory_is_not_truncated_by_cim(self):
        from resource_optimizer import detected_nvidia_vram_gb
        def fake(args,**kw):
            self.assertEqual(args[0],'nvidia-smi')
            return SimpleNamespace(returncode=0,stdout='16384\n')
        self.assertEqual(detected_nvidia_vram_gb(fake),16)
    def test_failure_does_not_guess_gpu_memory(self):
        from resource_optimizer import detected_nvidia_vram_gb
        self.assertEqual(detected_nvidia_vram_gb(lambda *a,**k:SimpleNamespace(returncode=1,stdout='')),0)
    def test_automatic_profile_uses_detected_vram(self):
        from akira_model_runtime import hardware_profile
        with patch('resource_optimizer.desktop_hardware',return_value={'ram_gb':32,
                'gpu_vram_gb':16,'dedicated_gpu':True,'gpus':[{'Name':'NVIDIA GeForce RTX 5060 Ti'}],
                'physical_cores':10}):
            profile=hardware_profile(ram_gb=32,cpu_cores=20)
        self.assertEqual(profile['detected_gpu_vram_gb'],16)
        self.assertGreater(profile['gpu_layers'],0)
    def test_explicit_cpu_only_is_honored(self):
        from akira_model_runtime import hardware_profile
        self.assertEqual(hardware_profile(ram_gb=8,gpu_vram_gb=0,cpu_cores=4)['gpu_layers'],0)

class WaveAndSettings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])
    def test_wave_repaints_faster_than_old_eight_hertz(self):
        from studio_widgets import SignalWave
        w=SignalWave()
        w.show()
        self.app.processEvents()
        self.assertLessEqual(w.timer.interval(),33)
        self.assertTrue(w.timer.isActive())
        w.set_saving(True)
        self.assertFalse(w.timer.isActive())
        w.close()
    def test_wallpaper_never_offers_invalid_165fps(self):
        from studio_settings_qt import wallpaper_fps_choices
        self.assertNotIn(165,wallpaper_fps_choices(165))
        self.assertIn(144,wallpaper_fps_choices(165))
        self.assertTrue(all(1<=fps<=144 for fps in wallpaper_fps_choices(240)))

if __name__=='__main__':unittest.main()
