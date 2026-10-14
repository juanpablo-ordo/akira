"""Optional embedded llama.cpp PROCESS SUPERVISION (not a bundled model).

Never terminates Ollama or arbitrary llama-server processes. This class only
owns subprocesses launched by this specific AkiraAssistant instance. Localhost
only; zero network/model downloads; financial Engine never imports this module.
"""
from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
import os, subprocess, threading, time
from urllib.parse import urlsplit
from urllib.request import urlopen


def hardware_profile(ram_gb=32, gpu_vram_gb=8, cpu_cores=12):
    """Starting recommendation, not a promise of fixed RAM/VRAM consumption."""
    vram=max(0,float(gpu_vram_gb))
    ram=max(1,float(ram_gb))
    # A 4B Q4 model has headroom; large 14B/30B models saturate 8GB cards.
    return {
        'model_class':'4B GGUF Q4_K_M' if ram>=16 else '2B GGUF Q4_K_M',
        'context_tokens':4096 if ram>=16 else 2048,
        'gpu_layers':12 if vram>=8 else 0,
        'cpu_threads':min(6,max(2,int(cpu_cores)//2)),
        'parallel_requests':1,
        'idle_unload_seconds':30,
        'target_model_vram_gb':4.5 if vram>=8 else 0.0,
        'notes':'Presupuesto orientativo. Medir con el Administrador de tareas y ajustar tras pruebas.'
    }


class ManagedLlamaProcess:
    def __init__(self, settings, profile=None, clock=time.monotonic):
        self.settings=settings or {}
        self.profile=profile or hardware_profile()
        self.clock=clock
        self.proc=None
        self.lock=threading.RLock()
        self.active=0
        self.last_use=clock()
        self._watcher=None

    def _paths(self):
        exe=Path(str(self.settings.get('local_runtime_exe') or ''))
        model=Path(str(self.settings.get('local_runtime_model') or ''))
        if not str(self.settings.get('local_runtime_exe') or '').strip() or not str(self.settings.get('local_runtime_model') or '').strip():
            return None
        if not (exe.is_file() and model.is_file()):return None
        if exe.suffix.lower() not in ('.exe','') or model.suffix.lower()!='.gguf':return None
        return exe.resolve(),model.resolve()

    def enabled(self):
        return bool(self.settings.get('local_runtime_enabled',False))

    @staticmethod
    def _port(endpoint):
        p=urlsplit(str(endpoint))
        if p.scheme!='http' or p.hostname not in ('127.0.0.1','localhost','::1') or p.path.rstrip('/')!='/v1/chat/completions':
            raise ValueError('IA integrada: solamente se permite una API llama.cpp en localhost')
        return p.port or 80

    def _health(self,port):
        try:
            with urlopen('http://127.0.0.1:'+str(port)+'/health',timeout=.7) as r:
                return int(r.status)==200
        except (OSError,ValueError):return False

    def command(self,endpoint,desktop=None):
        paths=self._paths()
        if paths is None:raise FileNotFoundError('Faltan llama-server.exe y el modelo GGUF. Akira no los descarga ni instala silenciosamente.')
        port=self._port(endpoint)
        desktop=desktop or {}
        profile=self.profile
        ctx=min(8192,max(1024,int(desktop.get('model_context_tokens',profile['context_tokens']))))
        gpu=max(0,int(profile['gpu_layers'])) if bool(desktop.get('model_use_gpu',True)) else 0
        return [str(paths[0]),'--model',str(paths[1]),'--host','127.0.0.1','--port',str(port),
                '--ctx-size',str(ctx),'--n-gpu-layers',str(gpu),
                '--threads',str(profile['cpu_threads']),'--parallel','1']

    def _terminate_own(self):
        proc=self.proc
        if proc is None:return
        self.proc=None
        if proc.poll() is None:
            try:proc.terminate();proc.wait(timeout=4)
            except (OSError,subprocess.TimeoutExpired):
                if proc.poll() is None:
                    try:proc.kill();proc.wait(timeout=3)
                    except (OSError,subprocess.TimeoutExpired):pass

    def start(self,endpoint,desktop=None):
        if not self.enabled():return False
        command=self.command(endpoint,desktop)
        port=self._port(endpoint)
        with self.lock:
            if self.proc and self.proc.poll() is None:
                self.last_use=self.clock();return True
            # No apropiarse de otro servidor/modelo, que puede ser ajeno a Akira.
            if self._health(port):
                raise RuntimeError('El puerto de la IA está ocupado por un servidor externo. Akira no lo cerrará.')
            flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
            self.proc=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,creationflags=flags)
            self.last_use=self.clock()
            if self._watcher is None or not self._watcher.is_alive():
                self._watcher=threading.Thread(target=self._watch,name='AkiraLocalModelIdle',daemon=True)
                self._watcher.start()
        return True

    def _watch(self):
        while True:
            time.sleep(2)
            with self.lock:
                if self.proc is None:return
                idle=int(self.settings.get('local_runtime_idle_seconds',self.profile['idle_unload_seconds']))
                idle=max(0,min(900,idle))
                if not self.active and self.clock()-self.last_use>=idle:
                    self._terminate_own()
                    return

    @contextmanager
    def session(self,endpoint,desktop=None):
        if not self.enabled():
            yield
            return
        with self.lock:self.active+=1
        try:
            self.start(endpoint,desktop)
            # Give the server a short bootstrap window, never block MT5.
            port=self._port(endpoint)
            deadline=self.clock()+25
            while self.clock()<deadline and not self._health(port):
                with self.lock:
                    if self.proc is None or self.proc.poll() is not None:
                        raise RuntimeError('El motor local terminó durante el arranque')
                time.sleep(.4)
            if not self._health(port):raise TimeoutError('llama.cpp no completó el inicio en 25 s')
            yield
        finally:
            with self.lock:
                self.active=max(0,self.active-1)
                self.last_use=self.clock()

    def stop(self):
        with self.lock:
            if self.active:raise RuntimeError('Modelo en uso; no se puede cerrar hasta terminar la respuesta')
            self._terminate_own()
