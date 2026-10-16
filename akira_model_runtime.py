"""Installed llama.cpp process supervision with bundled CPU/model recovery.

Never terminates Ollama or arbitrary llama-server processes. This class only
owns subprocesses launched by this specific AkiraAssistant instance. Localhost
only; zero network/model downloads; financial Engine never imports this module.
"""
from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
import os, subprocess, sys, threading, time, weakref
from urllib.parse import urlsplit
from urllib.request import urlopen

_SHARED=weakref.WeakValueDictionary()
_SHARED_LOCK=threading.Lock()


def shared_runtime(settings,log_root,profile=None):
    """Chat and research must never launch rival servers on the same port."""
    key=(str(Path(log_root).resolve()),str((settings or {}).get('local_endpoint') or ''))
    with _SHARED_LOCK:
        runtime=_SHARED.get(key)
        if runtime is None:
            runtime=ManagedLlamaProcess(settings,profile=profile,log_root=log_root)
            _SHARED[key]=runtime
        return runtime


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
    def __init__(self, settings, profile=None, clock=time.monotonic, log_root=None):
        self.settings=settings or {}
        self.profile=profile or hardware_profile()
        self.clock=clock
        self.proc=None
        self.lock=threading.RLock()
        self.active=0
        self.last_use=clock()
        self._watcher=None
        self._force_cpu=False  # Automatic fallback if Vulkan cannot start on this PC.
        self._closed=False
        self.log_path=Path(log_root)/'logs'/'IA_LOCAL.log' if log_root is not None else None
        self.path_resolution={}

    def _paths(self):
        exe_value=str(self.settings.get('local_runtime_exe') or '').strip()
        model_value=str(self.settings.get('local_runtime_model') or '').strip()
        # Resolve against AKIRA.exe, never the user's current working directory.
        # The bundled files sit next to the application, outside PyInstaller's _internal.
        app_dir=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
        def resolve(value, candidates):
            configured=Path(os.path.expandvars(value)).expanduser() if value else None
            if configured is not None and not configured.is_absolute():configured=app_dir/configured
            if configured is not None and configured.is_file():return configured
            return next((p for p in candidates if p.is_file()),configured or candidates[0])
        exe=resolve(exe_value,[app_dir/'local_ai/bin/llama-server.exe',app_dir/'local_ai/cpu/llama-server.exe'])
        model=resolve(model_value,[app_dir/'local_ai/models/Qwen3-4B-Q4_K_M.gguf'])
        self.path_resolution={'executable':str(exe),'model':str(model),'app_dir':str(app_dir)}
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
        if paths is None:raise FileNotFoundError('Faltan llama-server.exe y el modelo GGUF. Ejecuta el instalador de AKIRA completo.')
        port=self._port(endpoint)
        desktop=desktop or {}
        profile=self.profile
        ctx=min(8192,max(1024,int(desktop.get('model_context_tokens',profile['context_tokens']))))
        use_gpu=bool(desktop.get('model_use_gpu',True)) and not self._force_cpu
        gpu=max(0,int(profile['gpu_layers'])) if use_gpu else 0
        exe=paths[0]
        if not use_gpu:
            cpu=exe.parent.parent/'cpu'/'llama-server.exe'
            if cpu.is_file():exe=cpu
        if exe.parent.name.lower()=='cpu':gpu=0
        return [str(exe),'--model',str(paths[1]),'--host','127.0.0.1','--port',str(port),
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
        if self._closed:raise RuntimeError('La aplicación cerró su motor de IA; no se vuelve a iniciar desde tareas pendientes.')
        command=self.command(endpoint,desktop)
        port=self._port(endpoint)
        with self.lock:
            if self._closed:raise RuntimeError('La aplicación cerró su motor de IA.')
            if self.proc and self.proc.poll() is None:
                self.last_use=self.clock();return True
            # No apropiarse de otro servidor/modelo, que puede ser ajeno a Akira.
            if self._health(port):
                raise RuntimeError('El puerto de la IA está ocupado por un servidor externo. Akira no lo cerrará.')
            # Keep the owned model below normal CPU priority so MT5 and Tk
            # retain scheduling preference when the machine is under load.
            flags=getattr(subprocess,'CREATE_NO_WINDOW',0)|getattr(subprocess,'BELOW_NORMAL_PRIORITY_CLASS',0)
            stream=None
            try:
                if self.log_path is not None:
                    self.log_path.parent.mkdir(parents=True,exist_ok=True)
                    if self.log_path.exists() and self.log_path.stat().st_size>4000000:
                        self.log_path.replace(self.log_path.with_suffix('.previous.log'))
                    stream=self.log_path.open('ab',buffering=0)
                    stream.write(('\nINICIO IA '+time.strftime('%Y-%m-%d %H:%M:%S')+'\n').encode('utf-8'))
                self.proc=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=stream or subprocess.DEVNULL,
                    stderr=subprocess.STDOUT,creationflags=flags)
            finally:
                if stream is not None:stream.close()
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
    def session(self,endpoint,desktop=None,cancel_event=None):
        if cancel_event is not None and cancel_event.is_set():raise RuntimeError('Análisis detenido por el usuario')
        if not self.enabled():
            yield
            return
        with self.lock:self.active+=1
        try:
            self.start(endpoint,desktop)
            # Give the server a short bootstrap window, never block MT5.
            port=self._port(endpoint)
            deadline=self.clock()+90
            while self.clock()<deadline and not self._health(port):
                if cancel_event is not None and cancel_event.is_set():raise RuntimeError('Análisis detenido por el usuario')
                with self.lock:
                    if self.proc is None or self.proc.poll() is not None:
                        if not self._force_cpu and bool((desktop or {}).get('model_use_gpu',True)):
                            # Retry only our own process with the CPU binary;
                            # never terminate servers owned by other applications.
                            self._force_cpu=True
                            self.start(endpoint,desktop)
                        else:
                            raise RuntimeError('El motor local no pudo iniciar, ni con CPU')
                time.sleep(.4)
            if not self._health(port):raise TimeoutError('llama.cpp no completó el inicio en 90 s')
            yield
        finally:
            with self.lock:
                self.active=max(0,self.active-1)
                self.last_use=self.clock()

    def stop(self):
        with self.lock:
            if self.active:raise RuntimeError('Modelo en uso; no se puede cerrar hasta terminar la respuesta')
            self._terminate_own()

    def shutdown(self):
        """Close only Akira's own inference subprocess during application exit."""
        with self.lock:
            self._closed=True
            self.active=0
            self._terminate_own()
