"""
Platform-specific helpers: single-instance locking and battery-saver detection.

Despite the module name (kept for backwards compatibility with imports
elsewhere in the codebase) this now supports both Windows and Linux.
"""

import sys
import subprocess


class MutexNotAquiredError(Exception):
    pass


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class NamedMutex:
        # https://stackoverflow.com/questions/8799646/preventing-multiple-instances-of-my-application
        create_mutex = ctypes.windll.kernel32.CreateMutexA
        create_mutex.argtypes = [wintypes.LPCVOID, wintypes.BOOL, wintypes.LPCSTR]
        create_mutex.restype = wintypes.HANDLE

        wait_for_single_object = ctypes.windll.kernel32.WaitForSingleObject
        wait_for_single_object.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        wait_for_single_object.restype = wintypes.DWORD

        release_mutex = ctypes.windll.kernel32.ReleaseMutex
        release_mutex.argtypes = [wintypes.HANDLE]
        release_mutex.restype = wintypes.BOOL

        close_handle = ctypes.windll.kernel32.CloseHandle
        close_handle.argtypes = [wintypes.HANDLE]
        close_handle.restype = wintypes.BOOL

        def __init__(self, name: bytes):
            self.handle = self.create_mutex(None, False, name)
            result = self.wait_for_single_object(self.handle, 0)
            # 0x00 = WAIT_OBJECT_0 (acquired), 0x80 = WAIT_ABANDONED (prev crash, still acquirable)
            if result not in (0x00, 0x80):
                raise MutexNotAquiredError

        def release(self):
            self.release_mutex(self.handle)
            self.close_handle(self.handle)

    # https://stackoverflow.com/a/6156606/7274182
    # https://docs.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-system_power_status
    class SYSTEM_POWER_STATUS(ctypes.Structure):
        _fields_ = [
            ("ACLineStatus", wintypes.BYTE),
            ("BatteryFlag", wintypes.BYTE),
            ("BatteryLifePercent", wintypes.BYTE),
            ("SystemStatusFlag", wintypes.BYTE),
            ("BatteryLifeTime", wintypes.DWORD),
            ("BatteryFullLifeTime", wintypes.DWORD),
        ]

    def battery_saver_enabled() -> bool:
        SYSTEM_POWER_STATUS_P = ctypes.POINTER(SYSTEM_POWER_STATUS)

        GetSystemPowerStatus = ctypes.windll.kernel32.GetSystemPowerStatus
        GetSystemPowerStatus.argtypes = [SYSTEM_POWER_STATUS_P]
        GetSystemPowerStatus.restype = wintypes.BOOL

        status = SYSTEM_POWER_STATUS()

        if not GetSystemPowerStatus(ctypes.pointer(status)):
            return False
        return bool(status.SystemStatusFlag)

else:
    import fcntl
    import os
    import tempfile

    class NamedMutex:
        """File-lock based single-instance guard (fcntl flock)."""

        def __init__(self, name: bytes):
            lock_dir = os.environ.get("XDG_RUNTIME_DIR", tempfile.gettempdir())
            self._lock_path = os.path.join(lock_dir, name.decode() + ".lock")
            self._fh = open(self._lock_path, "w")
            try:
                fcntl.flock(self._fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                self._fh.close()
                raise MutexNotAquiredError

        def release(self):
            try:
                fcntl.flock(self._fh, fcntl.LOCK_UN)
            finally:
                self._fh.close()

    def battery_saver_enabled() -> bool:
        """
        True if the freedesktop power-profiles-daemon is set to 'power-saver'.
        Falls back to False if power-profiles-daemon isn't available.
        """
        try:
            result = subprocess.run(
                ["powerprofilesctl", "get"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            return result.stdout.strip() == "power-saver"
        except (FileNotFoundError, subprocess.SubprocessError):
            return False
