"""Give interactive chat priority over cancellable background model requests."""
from contextlib import contextmanager
import threading


class BackgroundDeferred(RuntimeError):
    pass


class InferencePriority:
    def __init__(self):
        self.lock=threading.RLock();self.users=0;self.background=set()

    @contextmanager
    def interactive(self):
        with self.lock:
            self.users+=1
            for event in self.background:event.set()
        try:yield
        finally:
            with self.lock:self.users=max(0,self.users-1)

    @contextmanager
    def auxiliary(self):
        event=threading.Event()
        with self.lock:
            if self.users:raise BackgroundDeferred('Revisión aplazada mientras Akira responde al chat')
            self.background.add(event)
        try:
            yield event
            if event.is_set():raise BackgroundDeferred('Revisión aplazada para dar prioridad al chat')
        except Exception as error:
            if event.is_set():raise BackgroundDeferred('Revisión aplazada para dar prioridad al chat') from error
            raise
        finally:
            with self.lock:self.background.discard(event)


PRIORITY=InferencePriority()
