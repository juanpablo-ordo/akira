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
