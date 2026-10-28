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


def hardware_profile(ram_gb=None, gpu_vram_gb=None, cpu_cores=None):
    """Starting recommendation, not a promise of fixed RAM/VRAM consumption."""
    # Auto mode reads this PC. Unknown GPU memory is zero, not an assumed 8 GB.
    if ram_gb is None:
        try:
            import psutil
            ram_gb=psutil.virtual_memory().total/1073741824
        except (ImportError,OSError):ram_gb=4
    if cpu_cores is None:
        cpu_cores=os.cpu_count() or 2
        try:
            import psutil
        except ImportError:pass
        else:
            try:cpu_cores=len(psutil.Process().cpu_affinity())
            except (psutil.Error,OSError,AttributeError):pass
    vram=max(0,float(gpu_vram_gb or 0))
    ram=max(1,float(ram_gb))
    # A 4B Q4 model has headroom; large 14B/30B models saturate 8GB cards.
    return {
        'model_class':'4B GGUF Q4_K_M' if ram>=16 else '2B GGUF Q4_K_M',
        'context_tokens':4096 if ram>=16 else 2048,
        'gpu_layers':12 if vram>=8 else 0,
        'cpu_threads':min(6,max(1,int(cpu_cores)//2)),
        'logical_cores':max(1,int(cpu_cores)),
        'detected_ram_gb':round(ram,2),
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
        self._launch_command=None;self._requested_command=None
        self._warm_until=0

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
        candidates=[app_dir/'local_ai/models/Qwen3-4B-Q4_K_M.gguf'] if not model_value or Path(model_value).name=='Qwen3-4B-Q4_K_M.gguf' else []
        model=resolve(model_value,candidates)
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

    def desktop_policy(self,desktop):
        profile=self.profile
        from resource_optimizer import effective_desktop
        hw={'ram_gb':profile.get('detected_ram_gb',0),'logical_cores':profile.get('logical_cores',0),
            'physical_cores':profile.get('physical_cores',max(1,int(profile.get('logical_cores',0))//2)),
            'dedicated_gpu':int(profile.get('gpu_layers',0))>0}
        return effective_desktop(desktop,hardware=hw)

    def command(self,endpoint,desktop=None):
        paths=self._paths()
        if paths is None:raise FileNotFoundError('Faltan llama-server.exe y el modelo GGUF. Ejecuta el instalador de AKIRA completo.')
        port=self._port(endpoint);desktop=self.desktop_policy(desktop);profile=self.profile
        ctx=min(8192,max(1024,int(desktop.get('model_context_tokens',profile['context_tokens']))),max(1024,int(desktop.get('memory_budget_mb',3072))*2))
        use_gpu=bool(desktop.get('model_use_gpu',True)) and not self._force_cpu
        gpu=max(0,int(profile['gpu_layers'])) if use_gpu else 0
        exe=paths[0]
        if not use_gpu:
            cpu=exe.parent.parent/'cpu'/'llama-server.exe'
            if cpu.is_file():exe=cpu
        if exe.parent.name.lower()=='cpu':gpu=0
        mode=desktop.get('performance_profile','Equilibrado')
        threads=max(1,int(profile['cpu_threads']))
        if mode=='Ahorro de energía':threads=min(1 if 0<int(profile.get('logical_cores',0))<=4 else 2,threads)
        elif mode=='Equilibrado':threads=min(4,threads)
        batch,ubatch=(128,64) if mode=='Ahorro de energía' else (256,128)
        cache_mb=0 if mode=='Ahorro de energía' else 512 if mode=='Equilibrado' else 1024
        loading='none' if mode=='Ahorro de energía' and gpu==0 else 'mmap'
        command=[str(exe),'--model',str(paths[1]),'--host','127.0.0.1','--port',str(port),
                '--ctx-size',str(ctx),'--n-gpu-layers',str(gpu),
                '--threads',str(threads),'--threads-batch',str(threads),
                '--batch-size',str(batch),'--ubatch-size',str(ubatch),
                '--load-mode',loading,'--cache-ram',str(cache_mb),
                '--poll','0','--poll-batch','0','--parallel','1','--jinja']
        if mode=='Ahorro de energía' and gpu==0:
            command+=['--flash-attn','on','--cache-type-k','q8_0','--cache-type-v','q8_0']
        return command

    def reconfigure(self,desktop):
        desktop=self.desktop_policy(desktop)
        with self.lock:
            self._idle_override=int(desktop.get('model_keep_alive_seconds',15))
            endpoint=self.settings.get('local_endpoint','http://127.0.0.1:18987/v1/chat/completions')
            self._requested_command=self.command(endpoint,desktop) if self._paths() else None
            if not self.active and self.proc and self._launch_command!=self._requested_command:self._terminate_own()

    def _terminate_own(self):
        proc=self.proc
        if proc is None:return
        self.proc=None
        self._warm_until=0
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
                self._requested_command=command
                if self._launch_command is not None and command!=self._launch_command and self.active<=1:self._terminate_own()
                else:self.last_use=self.clock();return True
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
                self._launch_command=list(command);self._requested_command=list(command)
                if self._closed:
                    self._terminate_own();raise RuntimeError('La aplicación cerró mientras arrancaba el modelo')
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
                idle=int(getattr(self,'_idle_override',self.settings.get('local_runtime_idle_seconds',self.profile['idle_unload_seconds'])))
                idle=max(0,min(900,idle))
                pending=self._launch_command is not None and self._requested_command is not None and self._launch_command!=self._requested_command
                if not self.active and (pending or self.clock()>=self._warm_until and self.clock()-self.last_use>=idle):
                    self._terminate_own()
                    return

    def keep_warm(self,seconds=30):
        """A short conversation lease; never changes saved memory/risk preferences."""
        with self.lock:
            if self._closed or self.proc is None or self.proc.poll() is not None:return False
            self._warm_until=self.clock()+max(0,min(60,int(seconds)))
            return True

    @contextmanager
    def session(self,endpoint,desktop=None,cancel_event=None):
        desktop=self.desktop_policy(desktop)
        if cancel_event is not None and cancel_event.is_set():raise RuntimeError('Análisis detenido por el usuario')
        if not self.enabled():
            yield
            return
        with self.lock:
            self.active+=1
            if desktop and 'model_keep_alive_seconds' in desktop:self._idle_override=max(0,min(600,int(desktop['model_keep_alive_seconds'])))
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
            from akira_local_ai import owned_context
            with owned_context(self.effective_parameters().get('context_tokens') or int((desktop or {}).get('model_context_tokens',self.profile['context_tokens']))):yield
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

    def shutdown_async(self):
        """Signal the owned child before UI exit; reap without freezing the window."""
        self._closed=True;proc=self.proc;self.proc=None;self.active=0
        if proc is None or proc.poll() is not None:return
        try:proc.terminate()
        except OSError:return
        def reap():
            try:proc.wait(timeout=4)
            except subprocess.TimeoutExpired:
                try:proc.kill();proc.wait(timeout=3)
                except (OSError,subprocess.TimeoutExpired):pass
        threading.Thread(target=reap,name='AkiraModelReaper',daemon=True).start()

    def effective_parameters(self):
        command=self._launch_command or []
        def value(flag):
            try:return int(command[command.index(flag)+1])
            except (ValueError,IndexError):return None
        return {'owned_pid':self.proc.pid if self.proc and self.proc.poll() is None else None,
                'context_tokens':value('--ctx-size'),'gpu_layers':value('--n-gpu-layers'),'cpu_threads':value('--threads'),
                'pending_reload':bool(self._requested_command is not None and self._launch_command!=self._requested_command)}
