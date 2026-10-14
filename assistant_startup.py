"""Recover the Windows assistant in a worker; never wait in Tk or the MT5 actor.

Installation metadata is progress, not proof that an inference service is ready.
Only the independently queried /api/tags response can establish availability.
"""
from pathlib import Path
import json
import os
import re
import subprocess
import threading
import time
from urllib.parse import urlparse

ACTIVE_PHASES = {'INSTALLING', 'STARTING', 'DOWNLOADING', 'VERIFYING', 'VISION', 'WAITING'}

def _number(value):
    try: return float(value or 0)
    except (ValueError, TypeError): return 0.0

def _pid_alive(pid):
    if os.name!='nt':return True  # PID liveness is exercised via injection in offline tests.
    try:
        import ctypes
        from ctypes import wintypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.argtypes=(wintypes.DWORD,wintypes.BOOL,wintypes.DWORD)
        kernel.OpenProcess.restype=wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes=(wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD))
        kernel.CloseHandle.argtypes=(wintypes.HANDLE,)
        handle=kernel.OpenProcess(0x1000,False,int(pid))
        if not handle:return ctypes.get_last_error()==5
        try:
            code=wintypes.DWORD()
            return bool(kernel.GetExitCodeProcess(handle,ctypes.byref(code))) and code.value==259
        finally:kernel.CloseHandle(handle)
    except (OSError,ValueError,TypeError,OverflowError):return False
PHASE_LABELS = {
    'CHECKING': 'comprobando asistente', 'INSTALLING': 'instalando asistente',
    'STARTING': 'iniciando asistente', 'DOWNLOADING': 'descargando asistente',
    'VERIFYING': 'verificando asistente', 'VISION': 'preparando visión',
    'WAITING': 'preparación en curso', 'MISSING': 'asistente sin preparar',
    'UNAVAILABLE': 'asistente sin conexión', 'FAILED': 'asistente necesita reparación',
    'STALLED': 'preparación sin avance', 'DISABLED': 'asistente desactivado',
}


class AssistantStartup:
    def __init__(self, root, cfg, enabled=False, platform=None, launch=None, clock=time.time, alive=None):
        self.root = Path(root); self.cfg = cfg; self.enabled = enabled
        self.platform = os.name if platform is None else platform
        self.launch = launch or subprocess.Popen; self.clock = clock
        self.alive=alive or _pid_alive
        self.lock = threading.Lock(); self.process = None; self.attempted = False
        self.started = 0.0; self.failure = ''; self.last_progress = {}
        self.auto_retries=0;self.auto_due=0.0;self.auto_error=''
        self.local_profile = self.root / 'state/akira_local_ai_profile.json'
        self.shared_profile = (Path(os.environ['LOCALAPPDATA']) / 'AKIRA/assistant_startup.json'
            if self.platform == 'nt' and os.environ.get('LOCALAPPDATA') else self.local_profile)
        self.output_log=self.shared_profile.parent/'ASISTENTE_PROCESO.log';self._failure_captured=False

    def _profile(self):
        # Called only by the status worker, not by Tk. Atomic writer + bounded read.
        candidates = []
        for path in dict.fromkeys((self.local_profile, self.shared_profile)):
            try:
                with path.open('r', encoding='utf-8-sig') as stream:
                    text = stream.read(65537)
                row = json.loads(text) if len(text) <= 65536 else {}
                if isinstance(row, dict): candidates.append(row)
            except (OSError, ValueError): pass
        active=[r for r in candidates if r.get('phase') in ACTIVE_PHASES-{'WAITING'}
            and 0 <= self.clock()-_number(r.get('heartbeat')) < 120]
        return max(active or candidates, key=lambda r: _number(r.get('heartbeat')), default={})

    def _start(self, force=False):
        # Caller owns lock. No shell and no prompts on the UI thread.
        if self.process is not None and self.process.poll() is None:
            profile=self._profile()
            fresh=0 <= self.clock()-_number(profile.get('heartbeat')) < 120
            failed=profile.get('phase')=='FAILED'
            stalled=not fresh and self.clock()-self.started >= 120
            if not force or not (failed or stalled):
                return {'accepted':True,'action':'SHARED','phase':profile.get('phase') or 'STARTING',
                    'detail':'La preparación sigue en curso; se conserva su progreso.'}
            # Stop only the Popen instance that this application created. A PID
            # copied from a profile is never authority to terminate a process.
            try:
                self.process.terminate()
                try:self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill();self.process.wait(timeout=3)
            except (OSError,subprocess.TimeoutExpired) as exc:
                self.failure='No se pudo reiniciar la preparación: '+str(exc)
                return self._failure_result()
        if self.attempted and not force:
            return {'accepted':False,'action':'ALREADY_ATTEMPTED','detail':'Pulsa REPARAR ASISTENTE para reintentar.'}
        self.attempted = True; self.failure = ''; self.started = self.clock();self._failure_captured=False
        script = self.root / 'PREPARAR_OLLAMA.ps1'
        if not script.is_file():
            self.failure = 'Falta el componente de preparación. Reinstala esta actualización de AKIRA.'
            return self._failure_result()
        try:
            self.output_log.parent.mkdir(parents=True,exist_ok=True)
            with self.output_log.open('ab') as output:
                self.process = self.launch(['powershell.exe', '-NoProfile', '-NonInteractive',
                    '-ExecutionPolicy', 'Bypass', '-File', str(script)], cwd=str(self.root),
                    stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except OSError as exc:
            from notification_center import safe_text
            self.failure = f'Windows no pudo iniciar la preparación: {safe_text(exc)}. Pulsa REPARAR ASISTENTE.'
            return self._failure_result()
        return {'accepted':True,'action':'STARTED','phase':'STARTING',
            'detail':'Preparación iniciada. Se comprobará una respuesta real antes de darla por terminada.',
            'log_path':str(self.output_log)}

    def _failure_result(self):
        return {'accepted':False,'phase':'FAILED','error':self.failure,
            'detail':self.failure,'log_path':str(self.output_log)}

    def preferred_model(self, available, endpoint=None):
        profile=self._profile();model=str(profile.get('text_model') or '')
        configured=str(endpoint or self.cfg.get('assistant',{}).get('local_endpoint') or 'http://127.0.0.1:11434/api/chat')
        same=str(profile.get('endpoint') or configured).rstrip('/')==configured.rstrip('/')
        return model if same and profile.get('inference_ok') is True and model in available else None

    def conversation_model(self, available, endpoint=None):
        """Keep a verified lightweight fallback without forcing a larger model."""
        from akira_local_ai import choose_text_model
        cfg=self.cfg.get('assistant') or {}
        fast=choose_text_model(available,str(cfg.get('fast_chat_model') or 'qwen3:8b'),
            str(cfg.get('local_model_lite') or 'qwen3:4b'),prefer_fast=True)
        verified=self.preferred_model(available,endpoint)
        if not verified:return fast
        def parameters(name):
            match=re.search(r'(?:[:/_-])(\d+(?:\.\d+)?)b(?=$|[-_:])',name,re.I)
            return float(match.group(1)) if match else None
        small,calibrated=parameters(fast),parameters(verified)
        # An unknown alias still uses its actual inference proof. For named
        # sizes, a heavier profile must not override the fast conversation route.
        if fast not in available or small is None or calibrated is None or calibrated<=small:return verified
        return fast

    def _capture_failure(self):
        if self._failure_captured:return
        self._failure_captured=True
        try:
            from notification_center import safe_text
            with self.output_log.open('rb') as stream:
                stream.seek(0,2);end=stream.tell();stream.seek(max(0,end-65536))
                text=stream.read(65536).decode('utf-8','replace')
            path=self.root/'logs/ASISTENTE_PROCESO.log';path.parent.mkdir(parents=True,exist_ok=True)
            if path.resolve()!=self.output_log.resolve():path.write_text(safe_text(text),encoding='utf-8')
        except OSError:pass

    def retry(self):
        with self.lock:
            self.auto_retries=0;self.auto_due=0.0;self.auto_error=''
            if self.platform != 'nt':
                self.failure = 'La preparación automática está disponible en la aplicación de Windows.'
                return self._failure_result()
            if not self._standard_endpoint():
                self.failure = 'El servidor del asistente es externo o usa otro puerto. Revisa la conexión configurada.'
                return self._failure_result()
            profile=self._profile();fresh=0 <= self.clock()-_number(profile.get('heartbeat')) < 120
            if (profile.get('phase') in ACTIVE_PHASES and fresh and profile.get('pid')
                    and profile.get('pid')!=getattr(self.process,'pid',None) and self.alive(profile['pid'])):
                return {'accepted':True,'action':'SHARED','phase':profile['phase'],
                    'detail':'Otra preparación de AKIRA está en curso; se comparte su progreso.'}
            return self._start(force=True)

    def _auto_recover(self,row,now):
        """Three delayed attempts, owned process only; never run a repair loop."""
        if not (self.enabled and self.platform=='nt' and self._standard_endpoint()
                and self.cfg.get('assistant',{}).get('auto_install_local_ai',True)):
            return row
        if row.get('phase') not in ('FAILED','STALLED'):return row
        error=str(row.get('error') or row.get('detail') or '')
        if not self.auto_due:
            self.auto_due=now+min(120,30*2**self.auto_retries);self.auto_error=error
        if now>=self.auto_due and self.auto_retries<3:
            self.auto_retries+=1;self.auto_due=now+min(120,30*2**self.auto_retries)
            result=self._start(force=True)
            if result.get('accepted'):
                row.update(ready=False,phase='STARTING',detail='AKIRA está reparando automáticamente el asistente. Intento '+str(self.auto_retries)+'/3. Último motivo: '+error[:180],auto_repair=True)
                return row
        row.update(auto_repair=False,auto_retry_count=self.auto_retries)
        if self.auto_retries<3:
            row['retry_after_seconds']=max(0,round(self.auto_due-now))
            row['detail']+=' · Recuperación automática en '+str(row['retry_after_seconds'])+' s.'
        else:row['detail']+=' · Tres reintentos automáticos no resolvieron el fallo; consulta el motivo y registro.'
        return row

    def _standard_endpoint(self):
        try:
            url = urlparse(str(self.cfg.get('assistant', {}).get('local_endpoint') or 'http://127.0.0.1:11434/api/chat'))
            return url.scheme == 'http' and url.hostname in ('localhost', '127.0.0.1') and url.port == 11434
        except ValueError: return False

    def observe(self, status):
        row = dict(status); profile = self._profile(); now = self.clock()
        with self.lock:
            self.last_progress = profile
            if self.cfg.get('assistant', {}).get('enabled') is False:
                row.update(ready=False, phase='DISABLED', detail='El asistente está desactivado en los ajustes.'); return row
            inference_failed=(profile.get('inference_checked') is True and profile.get('inference_ok') is False
                and profile.get('text_model') in row.get('models',[])
                and str(profile.get('endpoint') or self.cfg.get('assistant',{}).get('local_endpoint') or 'http://127.0.0.1:11434/api/chat').rstrip('/')
                    ==str(self.cfg.get('assistant',{}).get('local_endpoint') or 'http://127.0.0.1:11434/api/chat').rstrip('/'))
            preparing=(profile.get('recovery_active') and profile.get('phase') not in ('READY','VISION')
                and 0 <= now-_number(profile.get('heartbeat')) < 120)
            owned_running=self.process is not None and self.process.poll() is None
            current_proof=(profile.get('pid')==getattr(self.process,'pid',None)
                and _number(profile.get('heartbeat'))>=self.started-1
                and profile.get('inference_ok') is True and profile.get('phase') in ('READY','VISION'))
            if owned_running and not current_proof:preparing=True
            if inference_failed or preparing:row['ready']=False
            if row.get('ready'):
                self.auto_retries=0;self.auto_due=0.0;self.auto_error=''
                row.update(phase='READY', detail='Asistente disponible. Memoria, herramientas y chat preparados.')
                if profile.get('phase') == 'VISION': row['detail'] += ' La visión se descarga en segundo plano.'
                row.pop('error', None); return row
            phase = str(profile.get('phase') or '')
            heartbeat = _number(profile.get('heartbeat'))
            fresh = 0 <= now - heartbeat < 120
            running = self.process is not None and self.process.poll() is None
            external_busy = (phase in ACTIVE_PHASES and fresh and bool(profile.get('pid'))
                and profile.get('pid') != getattr(self.process, 'pid', None) and self.alive(profile['pid']))
            if (not running and not external_busy and self.enabled and self.platform == 'nt'
                    and self.cfg.get('assistant', {}).get('auto_install_local_ai', True)
                    and self._standard_endpoint()):
                self._start(); running = self.process is not None and self.process.poll() is None
            if self.failure:
                row.update(phase='FAILED', error=self.failure, detail=self.failure); return self._auto_recover(row,now)
            if running or external_busy:
                current = bool(fresh and (external_busy or (running
                    and profile.get('pid')==getattr(self.process,'pid',None) and heartbeat>=self.started-1)))
                if current and phase == 'FAILED':
                    self._capture_failure()
                    error=str(profile.get('error') or 'Preparación fallida')
                    row.update(phase='FAILED', error=str(profile.get('error') or 'Preparación fallida'),
                        detail=error+' · Pulsa REPARAR ASISTENTE; el error quedó en el registro.',log_path=str(self.output_log)); return self._auto_recover(row,now)
                if current:
                    row.update(phase=phase if phase in ACTIVE_PHASES else 'VERIFYING',
                        detail=str(profile.get('detail') or 'Comprobando la disponibilidad del asistente.'))
                    for key in ('completed_bytes', 'total_bytes', 'progress_pct', 'layer'):
                        if profile.get(key) is not None: row[key] = profile[key]
                elif now - self.started > 120:
                    row.update(phase='STALLED', detail='La preparación no comunica avances. Pulsa REPARAR ASISTENTE para reiniciarla; consulta el motivo y registro.')
                else: row.update(phase='STARTING', detail='Windows está iniciando la preparación del asistente.')
                return self._auto_recover(row,now)
            if self.attempted or inference_failed:
                code = self.process.poll() if self.process is not None else None
                if code is not None and code!=0:self._capture_failure()
                error=str(profile.get('error') or f'Preparación terminada ({code}); el asistente no responde.')
                row.update(phase='FAILED', error=error,
                    detail=error+' · Pulsa REPARAR ASISTENTE para reintentar; el registro ASISTENTE_PROCESO.log conserva la salida.',log_path=str(self.output_log)); return self._auto_recover(row,now)
            phase = 'MISSING' if row.get('ok') else 'UNAVAILABLE'
            row.update(phase=phase, detail=('Falta descargar el asistente.' if row.get('ok') else 'El servicio del asistente no responde.')
                + ' Pulsa REPARAR ASISTENTE para prepararlo.')
            return row
