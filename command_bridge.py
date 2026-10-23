"""Mensajes entre chat/interfaz y el único hilo autorizado a usar MT5."""
import queue,threading,time,uuid

class CommandBridge:
    def __init__(self,commands,timeout=20):
        self.commands=commands;self.timeout=timeout;self.connected=False;self.starting=False

    def request(self,cmd,cancel_event=None):
        inspect=cmd.get('action')=='inspect_mt5'
        if not self.connected and not self.starting and not inspect:return {'ok':False,'error':'El motor todavía no está conectado a MT5'}
        event=threading.Event();box={};lock=threading.Lock()
        request={**cmd,'request_id':uuid.uuid4().hex,'_done':event,'_reply':box,'_lock':lock,'_started':False,'_cancelled':False}
        if cancel_event is not None and cancel_event.is_set():return {'ok':False,'cancelled':True,'error':'La aplicación se está cerrando.'}
        try:self.commands.put(request,timeout=1)
        except queue.Full:return {'ok':False,'error':'Hay solicitudes pendientes. Espera un momento antes de repetir.'}
        deadline=time.monotonic()+(max(self.timeout,140) if inspect else self.timeout)
        while True:
            if cancel_event is not None and cancel_event.is_set():
                with lock:request['_cancelled']=True
                return {'ok':False,'cancelled':True,'error':'La aplicación se está cerrando.'}
            left=deadline-time.monotonic()
            if left<=0:break
            if event.wait(min(.1,left) if cancel_event is not None else left):return box.get('result',{'ok':False,'error':'Respuesta del motor vacía'})
        with lock:
            if not request['_started']:
                request['_cancelled']=True
                return {'ok':False,'error':'El motor no inició esta solicitud; se retiró de la cola'}
        return {'ok':False,'unconfirmed':True,'note':'Solicitud iniciada, respuesta MT5 aún no disponible. Revisa TERMINAL antes de repetir.'}

def dispatch(engine,cmd,handler=None):
    lock=cmd.get('_lock')
    if lock:
        with lock:
            if cmd.get('_cancelled'):return
            cmd['_started']=True
    try:result=(handler or engine.handle_command)(cmd)
    except Exception as exc:result={'ok':False,'error':type(exc).__name__+': '+str(exc)}
    if '_reply' in cmd:cmd['_reply']['result']=result
    if '_done' in cmd:cmd['_done'].set()

