"""Observe actual Windows media release; fail if the lock does not clear.

Security scanners may briefly open a freshly generated MP4 after its decoder
has exited. Only Windows sharing/lock violations get a bounded observation
window. Other permissions errors and persistent locks remain test failures.
"""
from pathlib import Path
import time


def remove_closed_media(path,timeout=2):
    deadline=time.monotonic()+timeout
    while True:
        try:
            Path(path).unlink()
            return
        except PermissionError as error:
            if getattr(error,'winerror',None) not in (32,33) or time.monotonic()>=deadline:
                raise
            time.sleep(min(.025,max(0,deadline-time.monotonic())))
