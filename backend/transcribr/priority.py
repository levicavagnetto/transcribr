"""Running the worker below normal CPU priority, so the web service stays responsive."""

import ctypes
import logging
import os
import sys

log = logging.getLogger(__name__)

NICENESS = 10
_BELOW_NORMAL_PRIORITY_CLASS = 0x00004000


def lower_priority() -> None:
    """Lower this process's CPU priority (niceness 10, or Windows' below-normal class)."""
    if sys.platform == "win32":
        from ctypes import wintypes  # noqa: PLC0415 - Windows only

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        # Declare the types: the process handle is 64-bit and would be truncated as a C int.
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.SetPriorityClass.restype = wintypes.BOOL
        if not kernel32.SetPriorityClass(
            kernel32.GetCurrentProcess(), _BELOW_NORMAL_PRIORITY_CLASS
        ):
            log.warning(
                "could not lower the worker's CPU priority (error %d)", ctypes.get_last_error()
            )
        return
    current = os.nice(0)
    if current < NICENESS:
        os.nice(NICENESS - current)
