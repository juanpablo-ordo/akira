"""Launch maintenance outside the app so removal does not depend on its UI/MT5."""
from pathlib import Path
import os,shutil,subprocess,tempfile

def launch_uninstaller(folder,platform=None,launch=None):
    if (platform or os.name)!='nt':
        raise RuntimeError('El desinstalador de este paquete está preparado para Windows.')
    # On a real Windows installation prefer the separate native uninstaller.
    # It detaches itself before removing the active release directory.
    native=Path(folder)/'AKIRA_Desinstalador.exe'
    if os.name=='nt' and native.is_file():
        return (launch or subprocess.Popen)([str(native)],cwd=str(Path(folder)),
            creationflags=getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0))
    script=Path(folder)/'DESINSTALAR_AKIRA.ps1'
    if not script.is_file():
        raise FileNotFoundError('Falta DESINSTALAR_AKIRA.ps1 en la instalación.')
    # The worker must not run from a directory that it will remove.
    staging=Path(tempfile.mkdtemp(prefix='AKIRA_DESINSTALADOR_'))
    try:
        detached=staging/script.name;shutil.copy2(script,detached)
        return (launch or subprocess.Popen)(['powershell.exe','-NoLogo','-NoProfile','-STA',
            '-ExecutionPolicy','Bypass','-File',str(detached)],cwd=str(staging),
            creationflags=getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0)|getattr(subprocess,'CREATE_NO_WINDOW',0))
    except Exception:
        shutil.rmtree(staging,ignore_errors=True)
        raise
