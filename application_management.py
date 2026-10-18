"""Launch maintenance outside the app so removal does not depend on its UI/MT5."""
from pathlib import Path
import os,shutil,subprocess,tempfile,sys

def native_uninstaller_candidates(folder, executable=None, localappdata=None):
    """Prefer the native Inno Setup remover, even when user data is elsewhere.

    Never scan the entire disk or erase directories. The Windows native uninstaller
    owns application cleanup and can be started independently of the Akira UI.
    """
    root = Path(folder)
    exe = Path(executable or sys.executable)
    data = Path(localappdata or os.environ.get('LOCALAPPDATA') or root)
    parents = [exe.parent, root, data / 'Programs' / 'AKIRA']
    seen = set()
    for parent in parents:
        normalized = str(parent).casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        yield parent / 'unins000.exe'


def launch_uninstaller(folder,platform=None,launch=None,executable=None,localappdata=None):
    if (platform or os.name)!='nt':
        raise RuntimeError('El desinstalador de este paquete está preparado para Windows.')
    runner = launch or subprocess.Popen
    # Inno Setup's unins000.exe is the correct remover for R4+.
    for native in native_uninstaller_candidates(folder,executable,localappdata):
        if native.is_file():
            return runner([str(native)],cwd=str(native.parent),
                creationflags=getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0))
    # Retain legacy support for old standalone installs, if present.
    native=Path(folder)/'AKIRA_Desinstalador.exe'
    if native.is_file():
        return runner([str(native)],cwd=str(native.parent),
            creationflags=getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0))
    script=Path(folder)/'DESINSTALAR_AKIRA.ps1'
    if not script.is_file():
        raise FileNotFoundError('No se encontró el desinstalador nativo de AKIRA. Abre Configuración de Windows > Aplicaciones instaladas > AKIRA > Desinstalar.')
    staging=Path(tempfile.mkdtemp(prefix='AKIRA_DESINSTALADOR_'))
    try:
        detached=staging/script.name;shutil.copy2(script,detached)
        return runner(['powershell.exe','-NoLogo','-NoProfile','-STA',
            '-ExecutionPolicy','Bypass','-File',str(detached)],cwd=str(staging),
            creationflags=getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0)|getattr(subprocess,'CREATE_NO_WINDOW',0))
    except Exception:
        shutil.rmtree(staging,ignore_errors=True)
        raise


def prepare_native_uninstall(app_dir,timeout=25,processes=None,close_windows=None):
    """Close only helpers whose executable is inside this installation."""
    import time
    root=Path(app_dir).resolve();owned=[]
    if processes is None:
        import psutil
        processes=psutil.process_iter(['pid','exe','name'])
    for process in processes:
        try:
            info=process.info;pid=int(info.get('pid',process.pid))
            if pid==os.getpid():continue
            exe=Path(info.get('exe') or process.exe()).resolve()
            if not exe.is_relative_to(root):continue
            name=exe.name.casefold()
            if name not in ('akira.exe','llama-server.exe','piper.exe') and not (name.startswith('ffmpeg') and name.endswith('.exe')):continue
            owned.append(process)
        except (OSError,ValueError,AttributeError):continue
        except Exception:continue
    ids={p.pid for p in owned}
    if close_windows is not None:close_windows(ids)
    elif os.name=='nt' and ids:
        import ctypes
        from ctypes import wintypes
        user=ctypes.windll.user32
        @ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
        def visit(hwnd,_):
            pid=wintypes.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
            if pid.value in ids:user.PostMessageW(hwnd,0x0010,0,0)
            return True
        user.EnumWindows(visit,0)
    def alive(p):
        try:return p.is_running()
        except Exception:return False
    deadline=time.monotonic()+max(0,float(timeout))
    while any(alive(p) for p in owned) and time.monotonic()<deadline:time.sleep(.1)
    for p in owned:
        if not alive(p):continue
        try:p.terminate();p.wait(timeout=4)
        except Exception:
            try:p.kill();p.wait(timeout=3)
            except Exception:pass
    return {'status':'READY' if not any(alive(p) for p in owned) else 'BUSY','owned_processes':len(owned)}
