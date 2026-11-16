"""Run an authorized update after AKIRA exits, and recover on validation failure."""
from __future__ import annotations

import base64
import ctypes
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from release_updates import (ReleaseTrust, UpdateError, canonical_json,
                             verified_release, verify_installer)


def stage_install(profile, installer, release, current_exe=None):
    if os.name!='nt' or not getattr(sys,'frozen',False):
        raise UpdateError('La instalación desde AKIRA requiere la aplicación instalada en Windows.')
    exe=Path(current_exe or sys.executable).resolve()
    profile=Path(profile).resolve()
    app=exe.parent
    if (exe.name.lower()!='akira.exe' or not (app/'unins000.exe').is_file()
            or profile==app or profile in app.parents or app in profile.parents):
        raise UpdateError('La ubicación de AKIRA y sus datos debe verificarse antes de actualizar.')
    if not (profile/'akira_config.json').is_file():
        raise UpdateError('No se encontró la configuración que debe conservarse.')
    work=Path(tempfile.mkdtemp(prefix='AKIRA-actualizacion-',dir=profile.parent))
    runtime=work/'runtime'
    runtime.mkdir()
    shutil.copy2(exe,runtime/'AKIRA.exe')
    shutil.copytree(app/'_internal',runtime/'_internal')
    payload={'app':str(app),'profile':str(profile),'installer':str(Path(installer).resolve()),
             'envelope':base64.b64encode(release.envelope).decode(),'pid':os.getpid()}
    ticket=work/'update-job.json'
    ticket.write_bytes(canonical_json(payload))
    return subprocess.Popen([str(runtime/'AKIRA.exe'),'--update-job',str(ticket)],
        cwd=str(runtime),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
        env={**os.environ,'PYINSTALLER_RESET_ENVIRONMENT':'1'},
        creationflags=subprocess.CREATE_NO_WINDOW)


def wait_for_app(pid):
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[ctypes.c_uint32,ctypes.c_int,ctypes.c_uint32]
    kernel.OpenProcess.restype=ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_uint32]
    kernel.WaitForSingleObject.restype=ctypes.c_uint32
    kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    handle=kernel.OpenProcess(0x00100000,0,int(pid))
    if not handle:
        if ctypes.get_last_error()==87:return
        raise UpdateError('No se pudo verificar que AKIRA se cerró.')
    try:
        if kernel.WaitForSingleObject(handle,60_000)!=0:
            raise UpdateError('AKIRA sigue abierto. Vuelve a intentar la actualización.')
    finally:
        kernel.CloseHandle(handle)


def validated_install(exe, profile, release, work):
    result_file=work/'health.json'
    result=subprocess.run([str(exe),'--update-health',str(result_file),'--app-root',str(profile)],
                           cwd=str(exe.parent),timeout=480,check=False)
    if result.returncode:
        raise UpdateError('La configuración, IA local o comprobación de instalación falló.')
    result=json.loads(result_file.read_text(encoding='utf-8'))
    if (result.get('status')!='PASSED' or result.get('release',{}).get('version')!=release.version
            or result['release'].get('commit')!=release.metadata['commit']):
        raise UpdateError('La versión instalada no coincide con el manifiesto firmado.')


def replace_with_backup(destination, backup, quarantine):
    if destination.exists():
        os.replace(destination,quarantine)
    os.replace(backup,destination)


def run_install_job(ticket):
    from akira_version import RELEASE_VERSION

    ticket=Path(ticket).resolve()
    work=ticket.parent
    job=json.loads(ticket.read_text(encoding='utf-8'))
    app=Path(job['app']).resolve()
    profile=Path(job['profile']).resolve()
    exe=app/'AKIRA.exe'
    installer=Path(job['installer']).resolve()
    trust=ReleaseTrust.load()
    state={'status':'FAILED','error':'La actualización no se completó.'}
    touched=False
    backups=None
    try:
        if (ticket.name!='update-job.json' or work.parent!=profile.parent or not exe.is_file()
                or not installer.is_relative_to(profile/'state'/'updates') or app in profile.parents):
            raise UpdateError('La solicitud de instalación no corresponde a esta aplicación.')
        release=verified_release(base64.b64decode(job['envelope'],validate=True),trust,RELEASE_VERSION)
        wait_for_app(job['pid'])
        verify_installer(installer,release,trust)
        app_work=Path(tempfile.mkdtemp(prefix='AKIRA-respaldo-',dir=app.parent))
        backups=(app_work/'binarios',work/'datos')
        shutil.copytree(app,backups[0])
        shutil.copytree(profile,backups[1],ignore=shutil.ignore_patterns('updates'))
        touched=True
        result=subprocess.run([str(installer),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',
                              '/DIR='+str(app),'/LOG='+str(work/'installer.log')],
                              cwd=str(work),timeout=1800,check=False)
        if result.returncode:
            raise UpdateError('El instalador terminó con código '+str(result.returncode)+'.')
        validated_install(exe,profile,release,work)
        state={'status':'PASSED','version':release.version,'commit':release.metadata['commit']}
    except Exception as exc:
        state['error']=str(exc)[:400]
        if touched:
            try:
                replace_with_backup(app,backups[0],backups[0].parent/'fallida')
                replace_with_backup(profile,backups[1],work/'datos-fallidos')
                state['status']='RESTORED'
            except OSError as recovery:
                state.update(status='RECOVERY_REQUIRED',error=str(recovery)[:400],
                             previous_error=state['error'])
    state['diagnostics']=str(work)
    (work/'result.json').write_bytes(canonical_json(state))
    if state['status'] in ('PASSED','RESTORED'):
        (profile/'state').mkdir(parents=True,exist_ok=True)
        (profile/'state'/'update-result.json').write_bytes(canonical_json(state))
        launch_env=os.environ.copy()
        launch_env['PYINSTALLER_RESET_ENVIRONMENT']='1'
        subprocess.Popen([str(exe),'--app-root',str(profile)],cwd=str(app),
                         env=launch_env,creationflags=subprocess.CREATE_NO_WINDOW)
    return 0 if state['status']=='PASSED' else 1


def update_health(profile, report):
    """Validate the real installed model and migrate only after the checks pass."""
    from akira_version import release_identity
    from assistant_akira import AkiraAssistant
    from settings import desktop_release_config, load_config, save_config

    profile=Path(profile)
    config=profile/'akira_config.json'
    cfg=desktop_release_config(load_config(config))
    cfg['mode']='observe'
    assistant=AkiraAssistant(cfg,profile,auto_prepare=False)
    try:
        result=assistant.local_llm_reply('Responde en una frase breve que el modelo funciona.',{})
        if not str(result).strip() or not assistant._model_inference_verified:
            raise UpdateError('La IA local no produjo una respuesta verificable.')
        save_config(cfg,config)
        Path(report).write_bytes(canonical_json({'status':'PASSED','release':release_identity()}))
        return 0
    finally:
        assistant._managed_model.shutdown()
