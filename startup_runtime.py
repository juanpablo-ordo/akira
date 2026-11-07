"""Early process guard and hardware inventory, before Qt, models or MT5 start."""
import atexit,getpass,hashlib,os,tempfile
from pathlib import Path


class AlreadyRunning(RuntimeError):pass


class ApplicationLock:
    def __init__(self,namespace='AKIRA_Studio'):
        self.handle=None;self.stream=None
        identity=hashlib.sha256((namespace+':'+getpass.getuser()).encode()).hexdigest()[:24]
        if os.name=='nt':
            import ctypes
            from ctypes import wintypes
            self.kernel=ctypes.WinDLL('kernel32',use_last_error=True)
            self.kernel.CreateMutexW.argtypes=[wintypes.LPVOID,wintypes.BOOL,wintypes.LPCWSTR]
            self.kernel.CreateMutexW.restype=wintypes.HANDLE
            self.kernel.CloseHandle.argtypes=[wintypes.HANDLE]
            self.handle=self.kernel.CreateMutexW(None,False,'Local\\'+identity)
            if not self.handle:raise OSError(ctypes.get_last_error(),'No se pudo reservar la instancia de AKIRA')
            if ctypes.get_last_error()==183:
                self.close();raise AlreadyRunning('AKIRA ya está abierto. Cierra la otra ventana antes de iniciar otra instancia.')
        else:
            import fcntl
            self.stream=(Path(tempfile.gettempdir())/(identity+'.lock')).open('a+b')
            try:fcntl.flock(self.stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError:
                self.close();raise AlreadyRunning('AKIRA ya está abierto. Cierra la otra ventana antes de iniciar otra instancia.')
        atexit.register(self.close)

    def close(self):
        if self.handle is not None:self.kernel.CloseHandle(self.handle);self.handle=None
        if self.stream is not None:self.stream.close();self.stream=None


def duplicate_notice(message):
    if os.name=='nt':
        import ctypes
        ctypes.windll.user32.MessageBoxW(None,str(message),'AKIRA ya está abierto',0x30|0x10000)
    else:
        print(str(message),flush=True)


def prepare_hardware(root):
    from resource_optimizer import desktop_hardware
    from atomic_json import save_atomic_json
    hardware=desktop_hardware()
    try:save_atomic_json(Path(root)/'state'/'hardware.json',hardware,lock_attempts=10)
    except (OSError,TimeoutError):pass
    return hardware
