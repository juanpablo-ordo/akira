"""Exercise the Windows API branch without depending on any machine's PIDs.

The real controller keeps its native liveness check. Only WinDLL is mocked here;
the production function, ctypes pointer, exit-code logic and handle release run.
"""
import ctypes
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import assistant_startup


class WindowsProcessQueryTests(unittest.TestCase):
    def setUp(self):
        self.kernel=SimpleNamespace(OpenProcess=Mock(return_value=99),
            GetExitCodeProcess=Mock(),CloseHandle=Mock())
        self.dll=patch.object(ctypes,'WinDLL',return_value=self.kernel,create=True)
        self.dll_factory=self.dll.start();self.addCleanup(self.dll.stop)
        self.host=patch.object(assistant_startup,'os',SimpleNamespace(name='nt'))
        self.host.start();self.addCleanup(self.host.stop)
        self.last_error=patch.object(ctypes,'get_last_error',return_value=87,create=True)
        self.error=self.last_error.start();self.addCleanup(self.last_error.stop)

    def exit_code(self,code):
        def read(handle,pointer):pointer._obj.value=code;return 1
        self.kernel.GetExitCodeProcess.side_effect=read

    def test_live_windows_process_uses_read_only_query_and_releases_its_handle(self):
        self.exit_code(259)
        self.assertTrue(assistant_startup._pid_alive(456))
        self.dll_factory.assert_called_once_with('kernel32',use_last_error=True)
        self.kernel.OpenProcess.assert_called_once_with(0x1000,False,456)
        self.kernel.CloseHandle.assert_called_once_with(99)

    def test_finished_windows_process_is_not_an_active_preparation(self):
        self.exit_code(0)
        self.assertFalse(assistant_startup._pid_alive(456))
        self.kernel.CloseHandle.assert_called_once_with(99)

    def test_nonexistent_windows_pid_does_not_query_or_close_an_invalid_handle(self):
        self.kernel.OpenProcess.return_value=0
        self.assertFalse(assistant_startup._pid_alive(456))
        self.kernel.GetExitCodeProcess.assert_not_called();self.kernel.CloseHandle.assert_not_called()

    def test_access_denied_keeps_the_conservative_owner_check(self):
        self.kernel.OpenProcess.return_value=0;self.error.return_value=5
        self.assertTrue(assistant_startup._pid_alive(456))
        self.kernel.GetExitCodeProcess.assert_not_called();self.kernel.CloseHandle.assert_not_called()

    def test_exit_code_query_failure_releases_the_handle_and_is_not_ready(self):
        self.kernel.GetExitCodeProcess.return_value=0
        self.assertFalse(assistant_startup._pid_alive(456))
        self.kernel.CloseHandle.assert_called_once_with(99)

    def test_invalid_pid_never_reaches_the_windows_query(self):
        self.assertFalse(assistant_startup._pid_alive('invalid'))
        self.kernel.OpenProcess.assert_not_called();self.kernel.CloseHandle.assert_not_called()


if __name__=='__main__':unittest.main()
