"""Bound public-source work and name real alternatives without relabelling data."""
import threading,time
from urllib.parse import urlparse


class SourceDeadline:
    def __init__(self,limit=64):
        self.lock=threading.Lock();self.tasks={};self.limit=limit;self.closed=threading.Event();self.cooldowns={}

    @staticmethod
    def _provider(name):
        # Limit repeated DNS failures across query variants while allowing
        # unrelated sources to continue working.
        if name.startswith(('fact:', 'verified:')):return 'fact-provider'
        if name.startswith('web:'):
            return 'web:'+(urlparse(name[4:]).hostname or name[4:])
        return name.split(':',1)[0] or name

    def _failed(self,provider,reason):
        with self.lock:
            previous=self.cooldowns.get(provider) or {}
            count=min(6,int(previous.get('count',0))+1)
            dns=any(word in str(reason).lower() for word in ('11002','getaddrinfo','name resolution'))
            delay=min(180,30*(2**(count-1))) if dns else min(90,5*(2**(count-1)))
            self.cooldowns[provider]={'count':count,'until':time.monotonic()+delay,
                'reason':type(reason).__name__}

    def run(self,name,function,timeout=45,cancel_event=None):
        if cancel_event is not None and cancel_event.is_set():raise RuntimeError('Análisis detenido por el usuario')
        provider=self._provider(name)
        with self.lock:
            cooldown=self.cooldowns.get(provider)
            if cooldown and time.monotonic()<cooldown['until']:
                raise TimeoutError('Fuente temporalmente suspendida tras '+cooldown['reason']+
                    '; reintento en '+str(round(cooldown['until']-time.monotonic()))+' s. Otras fuentes siguen disponibles.')
            for key,row in list(self.tasks.items()):
                if row['done'].is_set():self.tasks.pop(key)
            if self.closed.is_set():raise RuntimeError('Consultas de fuentes cerradas')
            if name in self.tasks:raise TimeoutError('La conexión anterior sigue bloqueada; no se duplicará la consulta. Otras fuentes continúan.')
            if len(self.tasks)>=self.limit:raise TimeoutError('Se alcanzó el límite de conexiones públicas pendientes; no se crean más hilos.')
            row={'done':threading.Event()};self.tasks[name]=row
            def work():
                try:row['result']=function()
                except Exception as error:row['error']=error
                finally:row['done'].set()
            threading.Thread(target=work,name='AkiraSourceDeadline',daemon=True).start()
        deadline=time.monotonic()+timeout
        while not row['done'].wait(min(.1,max(.001,deadline-time.monotonic()))):
            if cancel_event is not None and cancel_event.is_set():raise RuntimeError('Análisis detenido por el usuario')
            if self.closed.is_set():raise RuntimeError('Consultas de fuentes cerradas')
            if time.monotonic()>=deadline:
                exc=TimeoutError('La fuente superó su plazo; resultado tardío descartado y conexión aislada.')
                self._failed(provider,exc)
                raise exc
        with self.lock:
            if self.tasks.get(name) is row:self.tasks.pop(name)
        if cancel_event is not None and cancel_event.is_set():raise RuntimeError('Análisis detenido por el usuario')
        if 'error' in row:
            self._failed(provider,row['error'])
            raise row['error']
        with self.lock:self.cooldowns.pop(provider,None)
        return row.get('result')


def alternatives(statuses):
    """Alternative context is not a replica of an unavailable official feed."""
    for name,row in statuses.items():
        if row.get('enabled') is False or row.get('fresh') and row.get('usable') and not row.get('error'):continue
        if name.startswith('venue:'):allowed=lambda key:key.startswith('venue:')
        elif name.startswith('local_ai:'):
            target='technical_review:'+name.partition(':')[2];allowed=lambda key:key==target
        elif name in ('youtube','strategy_reference') or name=='fed' or name.startswith('global_news:'):
            allowed=lambda key:key=='news' or key.startswith(('search:','global_news:'))
        else:continue
        found=[key for key,value in statuses.items() if key!=name and allowed(key) and value.get('enabled') is not False
               and value.get('fresh') and value.get('usable') and not value.get('error')]
        if found:row['fallback_sources']=sorted(found)[:3]
    return statuses


def technical_review(snapshot,symbol):
    info=(snapshot.get('symbols') or {}).get(symbol) or {};frames=info.get('frames') or {}
    names={'M15':'impulso M15','H1':'tendencia H1'};parts=[]
    for tf,title in names.items():
        trend=(frames.get(tf) or {}).get('trend')
        if isinstance(trend,(int,float)):parts.append(title+': '+('alcista' if trend>.12 else 'bajista' if trend<-.12 else 'neutral'))
    return {'origin':'technical_engine','neural_review':False,'symbol':symbol,'summary':'; '.join(parts),
        'detail':'Resumen del motor técnico actual; no es una revisión neuronal ni una confirmación independiente. '+ '; '.join(parts)} if len(parts)==2 else None
