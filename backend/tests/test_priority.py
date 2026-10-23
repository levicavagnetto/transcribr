import subprocess
import sys

PROBE = """
import sys
from transcribr.priority import lower_priority
lower_priority()
if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32")
    k.GetCurrentProcess.restype = wintypes.HANDLE
    k.GetPriorityClass.argtypes = [wintypes.HANDLE]
    k.GetPriorityClass.restype = wintypes.DWORD
    print(hex(k.GetPriorityClass(k.GetCurrentProcess())))
else:
    import os
    print(os.nice(0))
"""


def test_the_worker_process_runs_below_normal_priority() -> None:
    out = subprocess.run(  # noqa: S603 - our own interpreter and probe
        [sys.executable, "-c", PROBE], capture_output=True, text=True, check=True
    ).stdout.strip()
    if sys.platform == "win32":
        assert out == "0x4000"  # BELOW_NORMAL_PRIORITY_CLASS
    else:
        assert int(out) >= 10
