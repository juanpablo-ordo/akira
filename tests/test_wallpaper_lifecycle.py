"""Owned decoder exit, native handle barriers and immediate media replacement."""
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock,patch

from tests.media_fixture import remove_closed_media

_APP=None


class DecoderShutdownTests(unittest.TestCase):
    def fixture(self,folder):
        import imageio_ffmpeg
        path=Path(folder)/'fixture.mp4'
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-f','lavfi','-i',
                        'testsrc2=size=160x100:rate=12','-t','1','-c:v','mpeg4','-threads','1',str(path)],
                       check=True,capture_output=True,timeout=20)
        return path

    def worker(self,path):
        from studio_background import WallpaperWorker
        return WallpaperWorker({'file':str(path),'fps':12,'quality':50,'fit':'contain',
                                'max_memory_mb':256,'max_cpu_percent':30},(320,200))

    def test_native_exit_wait_does_not_trust_a_cached_popen_exit_code(self):
        from studio_background import wait_decoder_exit
        import ctypes
        kernel=Mock();kernel.WaitForSingleObject.return_value=0
        process=Mock(args=['owned decoder'],_handle=37,returncode=1);process.wait.return_value=1
        with patch('studio_background.sys.platform','win32'),patch.object(ctypes,'WinDLL',return_value=kernel,create=True):
            self.assertEqual(wait_decoder_exit(process,1.5),1)
        kernel.WaitForSingleObject.assert_called_once_with(37,1500)
        process.wait.assert_called_once_with(timeout=1.5)

    def test_timeout_kills_and_reaps_only_the_owned_decoder_before_closing_handles(self):
        from studio_background import release_decoder
        events=[];process=Mock();process.poll.return_value=None
        process.terminate.side_effect=lambda:events.append('terminate')
        process.kill.side_effect=lambda:events.append('kill')
        process.stdout.close.side_effect=lambda:events.append('pipe closed')
        process._handle.Close.side_effect=lambda:events.append('handle closed')
        def wait(proc,timeout):
            self.assertIs(proc,process);events.append('wait')
            if events.count('wait')==1:raise subprocess.TimeoutExpired('owned',timeout)
        with patch('studio_background.wait_decoder_exit',side_effect=wait):release_decoder(process,.1)
        self.assertEqual(events,['pipe closed','terminate','wait','kill','wait','handle closed'])

    def test_an_unconfirmed_exit_still_fails_and_keeps_the_native_handle_valid(self):
        from studio_background import release_decoder
        process=Mock();process.poll.return_value=0
        with patch('studio_background.wait_decoder_exit',side_effect=subprocess.TimeoutExpired('owned',.01)):
            with self.assertRaises(subprocess.TimeoutExpired):release_decoder(process,.01)
        process.kill.assert_called_once()
        process._handle.Close.assert_not_called()

    def test_stop_during_launch_still_reaps_the_child_and_releases_its_file(self):
        from studio_background import WallpaperWorker
        with tempfile.TemporaryDirectory() as folder:
            path=self.fixture(folder);worker=self.worker(path)
            original=subprocess.Popen;created=threading.Event();publish=threading.Event();children=[]
            def launch(*args,**kwargs):
                child=original(*args,**kwargs);children.append(child);created.set()
                if not publish.wait(3):raise TimeoutError('launch fixture stalled')
                return child
            with patch('studio_background.subprocess.Popen',side_effect=launch):
                worker.start()
                try:
                    self.assertTrue(created.wait(3));self.assertIsNone(worker.process)
                    worker.stop();publish.set();worker.close()
                finally:
                    publish.set();worker.close()
            self.assertTrue(worker.finished.is_set());self.assertEqual(worker.status['state'],'STOPPED')
            self.assertIsNotNone(children[0].poll());self.assertTrue(children[0].stdout.closed)
            remove_closed_media(path)

    def test_repeated_play_pause_close_releases_media_and_preserves_an_unrelated_process(self):
        bystander=subprocess.Popen([sys.executable,'-c','import sys;sys.stdin.buffer.read(1)'],
                                   stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            for i in range(12):
                with tempfile.TemporaryDirectory() as folder:
                    path=self.fixture(folder);worker=self.worker(path);worker.start()
                    try:
                        deadline=time.monotonic()+4
                        while not worker.frames and worker.status.get('state')!='ERROR' and time.monotonic()<deadline:time.sleep(.01)
                        self.assertTrue(worker.frames,worker.status)
                        if i%2==0:worker.visible.clear()
                    finally:worker.close()
                    self.assertFalse(worker.thread.is_alive());self.assertTrue(worker.finished.is_set())
                    self.assertEqual(worker.status['state'],'STOPPED');self.assertTrue(worker.process.stdout.closed)
                    self.assertIsNotNone(worker.process.poll());self.assertIsNone(bystander.poll())
                    remove_closed_media(path);self.assertFalse(path.exists())
        finally:
            bystander.stdin.close();bystander.wait(timeout=5)


class SurfaceOwnershipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global _APP
        from PySide6.QtWidgets import QApplication
        _APP=QApplication.instance() or QApplication([])

    def test_resize_waits_for_the_old_decoder_and_final_close_joins_its_reader(self):
        from studio_background import BackgroundSurface
        surface=BackgroundSurface();old=Mock(shutdown_error=None)
        try:
            surface.worker=old;old.thread.is_alive.return_value=True;surface.restart()
            self.assertIs(surface.worker,old);self.assertTrue(surface._resize.isActive())
            old.thread.is_alive.return_value=False;surface.restart()
            self.assertIsNone(surface.worker);self.assertFalse(surface._resize.isActive())
            surface.worker=old;surface.stop();old.close.assert_called_once();self.assertIsNone(surface.worker)
        finally:surface.stop();surface.close()


class FixtureReleaseTests(unittest.TestCase):
    def test_permanent_windows_sharing_violation_is_not_hidden(self):
        error=PermissionError('still locked');error.winerror=32
        with patch.object(Path,'unlink',side_effect=error):
            with self.assertRaises(PermissionError):remove_closed_media('fixture.mp4',timeout=.03)

    def test_other_permission_errors_are_not_retried(self):
        with patch.object(Path,'unlink',side_effect=PermissionError('access denied')) as unlink:
            with self.assertRaises(PermissionError):remove_closed_media('fixture.mp4')
        unlink.assert_called_once()

    def test_transient_windows_sharing_is_observed_until_the_actual_delete_succeeds(self):
        error=PermissionError('scanner');error.winerror=32
        with patch.object(Path,'unlink',side_effect=[error,None]) as unlink:
            remove_closed_media('fixture.mp4')
        self.assertEqual(unlink.call_count,2)


if __name__=='__main__':unittest.main()
