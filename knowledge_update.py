"""Refresh dated retrievable knowledge; never modifies weights, code or trading rules."""
import copy,threading,time
from concurrent.futures import ThreadPoolExecutor,as_completed
from reference_library import CATALOG,update_reference
from knowledge import KnowledgeStore

class KnowledgeUpdater:
    def __init__(self,cfg,root,emit=lambda row:None,clock=time.time,fetch=update_reference):
        self.cfg,self.root,self.emit,self.clock,self.fetch=cfg,root,emit,clock,fetch
        self.stop=threading.Event();self.wake=threading.Event();self.authorized=False;self.thread=None;self.next_due=0;self.announced=False
        self.status={'state':'LISTO','updated':None,'sources':[]};self.lock=threading.RLock()
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
        pool=ThreadPoolExecutor(max_workers=3,thread_name_prefix='AkiraKnowledgeSource')
        try:
            pending={pool.submit(self.fetch,self.root,url):(name,url) for name,url in jobs if not self.stop.is_set()}
            for future in as_completed(pending):
                if self.stop.is_set():break
                name,url=pending[future]
                try:
                    result=future.result();row={'name':name,'url':url,'state':'INDEXADA','fetched':result['fetched'],'characters':result['characters']}
                except Exception as exc:row={'name':name,'url':url,'state':'ERROR','error':type(exc).__name__+': '+str(exc)[:220]}
                rows.append(row)
                with self.lock:self.status['sources']=copy.deepcopy(rows)
        finally:pool.shutdown(wait=False,cancel_futures=True)
        with self.lock:self.status={'state':'ACTUALIZADO' if not any(r['state']=='ERROR' for r in rows) else 'ACTUALIZACIÓN PARCIAL','updated':now,'sources':rows}
        failed=[r['name']+': '+r['error'] for r in rows if r['state']=='ERROR']
        self.emit({'stage':self.status['state'],'detail':'Biblioteca de conversación: '+str(sum(r['state'] in ('INDEXADA','EN CACHÉ') for r in rows))+'/'+str(len(CATALOG))+' páginas de referencia indexadas o vigentes. '+('Pendientes: '+'; '.join(failed)+'. ' if failed else '')+'La comprobación financiera de cada orden se muestra por separado en VERIFICAR.','status':self.read()})
        if options.get('automatic_cache',True):
            from cache_maintenance import candidates,clean
            try:clean(self.root,candidates(self.root,options.get('cache_days',14),self.clock))
            except (OSError,ValueError):pass
    def run(self):
        while not self.stop.is_set():
            try:self.tick()
            except Exception as exc:self.emit({'stage':'ERROR','detail':'Actualización de conocimiento: '+type(exc).__name__})
            self.wake.wait(30);self.wake.clear()
