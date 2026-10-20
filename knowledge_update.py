"""Refresh dated retrievable knowledge; never modifies weights, code or trading rules."""
import copy,threading,time
from concurrent.futures import ThreadPoolExecutor,as_completed,TimeoutError
from reference_library import CATALOG,update_reference
from knowledge import KnowledgeStore

class KnowledgeUpdater:
    def __init__(self,cfg,root,emit=lambda row:None,clock=time.time,fetch=update_reference):
        self.cfg,self.root,self.emit,self.clock,self.fetch=cfg,root,emit,clock,fetch
        self.stop=threading.Event();self.wake=threading.Event();self.authorized=False;self.thread=None;self.next_due=0;self.announced=False
        self.status={'state':'LISTO','updated':None,'sources':[]};self.lock=threading.RLock()
        self.batch_timeout_seconds=45
    def read(self):
        with self.lock:return copy.deepcopy(self.status)
    def start(self, initial_delay_seconds=0):
        if self.thread and self.thread.is_alive():return
        # Defer ONLY automatic, noncritical knowledge refresh. Explicit user
        # refresh overrides the delay via refresh(); MT5 is unaffected.
        if initial_delay_seconds and self.cfg.get('knowledge',{}).get('mode','automatic')=='automatic':
            self.next_due=max(self.next_due,self.clock()+max(0,float(initial_delay_seconds)))
        self.thread=threading.Thread(target=self.run,daemon=True,name='AkiraKnowledge');self.thread.start()
    def refresh(self):self.authorized=True;self.next_due=0;self.wake.set()
    def close(self):self.stop.set();self.wake.set()
    def tick(self):
        options=self.cfg.get('knowledge',{});now=self.clock()
        # An explicit refresh is a one-shot request even with automation off.
        if now<self.next_due or (not options.get('enabled',True) and not self.authorized):return
        interval=max(3600,float(options.get('interval_hours',24))*3600)
        if options.get('mode','automatic')=='request' and not self.authorized:
            if not self.announced:
                self.announced=True;self.emit({'stage':'SOLICITUD','detail':'Hay fuentes de conocimiento por revisar. Puedes autorizar su actualización desde Ajustes.'})
            return
        self.authorized=False;self.announced=False;self.next_due=now+interval
        store=KnowledgeStore(self.root);jobs=[];rows=[]
        for name,url,desc in CATALOG:
            old=store.get(url)
            if old and now-float(old['fetched'])<interval:rows.append({'name':name,'url':url,'state':'EN CACHÉ','fetched':old['fetched']})
            else:jobs.append((name,url))
        with self.lock:self.status={'state':'ACTUALIZANDO','updated':self.status['updated'],'sources':rows}
        pool=ThreadPoolExecutor(max_workers=3,thread_name_prefix='AkiraKnowledgeSource');received=set()
        def failed(name,url,exc):
            from network_tls import connection_message
            state,detail=connection_message(exc)
            old=store.get(url)
            return {'name':name,'url':url,'state':state,'detail':detail,
                'fetched':old.get('fetched') if old else None,'cached_content':bool(old),
                'error':type(exc).__name__+': '+str(exc)[:220]}
        try:
            pending={pool.submit(self.fetch,self.root,url):(name,url) for name,url in jobs if not self.stop.is_set()}
            try:
                for future in as_completed(pending,timeout=self.batch_timeout_seconds):
                    if self.stop.is_set():break
                    name,url=pending[future];received.add(future)
                    try:
                        result=future.result();row={'name':name,'url':url,'state':'INDEXADA','fetched':result['fetched'],'characters':result['characters']}
                    except Exception as exc:row=failed(name,url,exc)
                    rows.append(row)
                    with self.lock:self.status['sources']=copy.deepcopy(rows)
            except TimeoutError:pass
            for future,(name,url) in pending.items():
                if future not in received:
                    future.cancel();rows.append(failed(name,url,TimeoutError('Tiempo de espera de biblioteca agotado')))
        finally:pool.shutdown(wait=False,cancel_futures=True)
        failures=[r for r in rows if r.get('error')]
        if failures:self.next_due=min(self.next_due,now+3600)
        state='ACTUALIZACIÓN CANCELADA' if self.stop.is_set() else 'ACTUALIZACIÓN PARCIAL' if failures else 'ACTUALIZADO'
        with self.lock:self.status={'state':state,'updated':now,'sources':rows,'next_update':self.next_due}
        detail=('Biblioteca: '+str(sum(r['state'] in ('INDEXADA','EN CACHÉ') for r in rows))+'/'+str(len(CATALOG))+' referencias vigentes. '+
            ('Quedaron '+str(len(failures))+' fuentes pendientes. Las ya guardadas siguen disponibles con su fecha; se volverá a consultar en una hora. ' if failures else '')+
            'La biblioteca ayuda a conversar y estudiar; no bloquea las operaciones de BTC u oro.')
        self.emit({'stage':state,'detail':detail,'status':self.read()})
        if options.get('automatic_cache',True):
            from cache_maintenance import candidates,clean
            try:clean(self.root,candidates(self.root,options.get('cache_days',14),self.clock))
            except (OSError,ValueError):pass
    def run(self):
        while not self.stop.is_set():
            try:self.tick()
            except Exception as exc:self.emit({'stage':'ERROR','detail':'Actualización de conocimiento: '+type(exc).__name__})
            self.wake.wait(30);self.wake.clear()
