"""Inter-process atomic JSON persistence with bounded Windows sharing retries.

A stable OS lock serializes writers. Every invocation uses a different temporary
file; failed writes never replace the last valid snapshot.
"""
import json
import os
from pathlib import Path
import tempfile
import time


def _lock_byte(fd, unlock=False):
    os.lseek(fd, 0, os.SEEK_SET)
    if os.name == 'nt':
        import msvcrt
        msvcrt.locking(fd, msvcrt.LK_UNLCK if unlock else msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_UN if unlock else fcntl.LOCK_EX | fcntl.LOCK_NB)


def save_atomic_json(path, payload, *, lock_attempts=150, replace_attempts=8):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    # Serialize only supported JSON values before locking or touching disk.
    encoded=json.dumps(payload,ensure_ascii=False,default=str)
    lock_fd=os.open(str(path)+'.lock',os.O_RDWR|os.O_CREAT,0o600)
    acquired=False
    temp_path=None
    try:
        for attempt in range(lock_attempts):
            try:
                _lock_byte(lock_fd)
                acquired=True
                break
            except (BlockingIOError,PermissionError):
                if attempt+1==lock_attempts:
                    raise TimeoutError('No se pudo adquirir el bloqueo de persistencia')
                time.sleep(.01)
            except OSError:
                if attempt+1==lock_attempts:
                    raise TimeoutError('No se pudo adquirir el bloqueo de persistencia')
                time.sleep(.01)
        fd,filename=tempfile.mkstemp(prefix=path.stem+'.',suffix='.tmp',dir=str(path.parent))
        temp_path=Path(filename)
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        for attempt in range(replace_attempts):
            try:
                os.replace(temp_path,path)
                temp_path=None
                return
            except PermissionError:
                if attempt+1==replace_attempts:raise
                # Windows can temporarily hold the destination open (WinError 32).
                time.sleep(.05*(attempt+1))
    finally:
        if temp_path is not None:
            try:temp_path.unlink(missing_ok=True)
            except OSError:pass
        if acquired:
            try:_lock_byte(lock_fd,unlock=True)
            finally:os.close(lock_fd)
        else:
            os.close(lock_fd)
