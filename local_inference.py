"""Give interactive chat priority over cancellable background model requests."""
from contextlib import contextmanager
import threading,time


class BackgroundDeferred(RuntimeError):
    pass


class InferencePriority:
    def __init__(self):
        self.lock=threading.RLock();self.condition=threading.Condition(self.lock)
        self.users=0;self.background=set();self.owner=None;self.depth=0

    @contextmanager
    def interactive(self,cancel_event=None,timeout=15):
        ident=threading.get_ident();deadline=time.monotonic()+timeout;acquired=False
        with self.condition:
            self.users+=1
            for event in self.background:event.set()
        try:
            with self.condition:
                while self.background or self.owner not in (None,ident):
                    if cancel_event is not None and cancel_event.is_set():raise RuntimeError('Análisis detenido por el usuario')
                    remaining=deadline-time.monotonic()
                    if remaining<=0:raise TimeoutError('La tarea anterior de IA no liberó el modelo; usa Reparar asistente para comprobarlo.')
                    self.condition.wait(min(.1,remaining))
                self.owner=ident;self.depth+=1;acquired=True
            yield
        finally:
            with self.condition:
                self.users=max(0,self.users-1)
                if acquired:
                    self.depth-=1
                    if not self.depth:self.owner=None
                self.condition.notify_all()

    @contextmanager
    def auxiliary(self):
        event=threading.Event()
        with self.condition:
            if self.users:raise BackgroundDeferred('Revisión aplazada mientras Akira responde al chat')
            if self.background:raise BackgroundDeferred('Otra revisión ya ocupa el modelo; no se acumulan consultas')
            self.background.add(event)
        try:
            yield event
            if event.is_set():raise BackgroundDeferred('Revisión aplazada para dar prioridad al chat')
        except Exception as error:
            if event.is_set():raise BackgroundDeferred('Revisión aplazada para dar prioridad al chat') from error
            raise
        finally:
            with self.condition:self.background.discard(event);self.condition.notify_all()


PRIORITY=InferencePriority()
