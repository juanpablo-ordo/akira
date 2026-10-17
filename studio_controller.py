"""UI-independent Studio controller; the existing actor remains the sole MT5 writer."""
from __future__ import annotations
import copy,json,os,queue,threading,time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from assistant_akira import AkiraAssistant
from command_bridge import CommandBridge
from execution import Reporter
from runtime import run_session
from settings import load_config,save_config,DEFAULT
from settings_effects import validate_form,changes
from notification_center import NotificationCenter,safe_text


class StudioController:
    def __init__(self,folder,preview=False,start_actor=True):
        self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True)
        config_path=self.folder/'akira_config.json'
        self.cfg=load_config(config_path if config_path.exists() else DEFAULT);self.preview=bool(preview)
        if not config_path.exists():save_config(self.cfg,config_path)
        self.commands=queue.Queue(maxsize=128);self.bridge=CommandBridge(self.commands)
        self.events=queue.Queue(maxsize=512);self.stop=threading.Event();self.view={};self._latest=None;self._snapshot_lock=threading.Lock()
        self.log_rows=deque(maxlen=300);self._jobs=set();self._jobs_lock=threading.Lock()
        self.io=ThreadPoolExecutor(max_workers=3,thread_name_prefix='AkiraStudioIO');self.chat_busy=False;self.closed=False
        self.notices=NotificationCenter(self.folder);self.network=None;self.online=None;self.last_evidence=-100
        self.voice=None;self.voice_rows=[];self.resources={};self._usage_due=0;self._usage_loading=False
        self._closure_seen=set();self._pending_signature=None
        self.reporter=Reporter(self.folder/'logs',callback=lambda row:self.emit('log',row),console=False)
        self.assistant=AkiraAssistant(self.cfg,self.folder,trade_callback=self.bridge.request,
            progress_callback=lambda row:self.emit('chat_progress',row),auto_prepare=False)
        self._runtime_cfg=copy.deepcopy(self.cfg)
        self.actor=None;self._services_started=False

    def start_services(self):
        """Start only after the UI is constructed; a failed window cannot own an actor."""
        if self._services_started or self.closed:return
        self._services_started=True;self.bridge.starting=True
        if not self.preview:
            from akira_secrets import protect_existing
            self.job('protect_existing_credentials',protect_existing)
        self.actor=threading.Thread(target=run_session,args=(self._runtime_cfg,self.folder,self.reporter,self.stop,self.commands,self.publish,self.preview),name='AkiraMT5',daemon=True);self.actor.start()
        if not self.preview:
            from connectivity import ConnectivityMonitor,internet_available
            self.network=ConnectivityMonitor(lambda row:self.emit('network',row),check=lambda:time.monotonic()-self.last_evidence<5 or internet_available());self.network.start()
            from knowledge_update import KnowledgeUpdater
            self.knowledge=KnowledgeUpdater(self.cfg,self.folder,lambda row:self.emit('knowledge',row));self.knowledge.start(initial_delay_seconds=45)

    def emit(self,kind,data):
        if self.closed:return
        try:self.events.put_nowait({'kind':kind,'data':data})
        except queue.Full:
            # Financial events are durably recorded by Reporter before delivery.
            # Only an overrun of the display queue is discarded; never commands.
            self._display_overrun=True

    def publish(self,view):
        with self._snapshot_lock:self._latest=view

    def poll(self):
        with self._snapshot_lock:view=self._latest;self._latest=None
        results=[]
        if view is not None:
            self.view=view;self.bridge.connected=bool(view.get('connected'));self.bridge.starting=False
            from connectivity import recently_connected
            if recently_connected(view):self.last_evidence=time.monotonic()
            results.append({'kind':'snapshot','data':view})
            self.job('operation_notices',lambda:self.operation_notices(view))
        for _ in range(120):
            try:row=self.events.get_nowait()
            except queue.Empty:break
            if row['kind']=='network':
                self.online=row['data']['online']
                if type(self.online) is bool:
                    try:self.commands.put_nowait({'action':'network_state','online':self.online})
                    except queue.Full:self.emit('error','Cola del motor llena; revisa el terminal antes de reenviar.')
                    if not self.online:self.notify('Sin Internet','Entradas que necesitan conexión en pausa. Reintento automático activo.','warning')
                    else:
                        self.notify('Conexión recuperada','Se comprobarán cotizaciones, órdenes y posiciones antes de nuevos envíos.')
                        if hasattr(self,'knowledge'):self.knowledge.refresh()
            elif row['kind']=='log':self.log_rows.appendleft(row['data'])
            results.append(row)
        return results

    def job(self,name,function,event=None):
        with self._jobs_lock:
            if self.closed or name in self._jobs or len(self._jobs)>=24:return False
            self._jobs.add(name)
        def run():
            try:
                result=function()
                if event:self.emit(event,result)
            except Exception as error:self.emit('error',safe_text(type(error).__name__+': '+str(error)))
            finally:
                with self._jobs_lock:self._jobs.discard(name)
        self.io.submit(run);return True

    def request(self,command):
        name='command:'+str(time.monotonic_ns())
        return self.job(name,lambda:self.bridge.request(command),'command_result')

    def notify(self,title,body,severity='info'):
        self.notices.add(title,safe_text(body),severity=severity)
        self.emit('notice',{'title':title,'body':safe_text(body),'severity':severity})

    def operation_notices(self,view):
        for row in view.get('position_closures') or []:
            key=row.get('id')
            if row.get('state')!='CONFIRMADO MT5' or not key or key in self._closure_seen:continue
            self._closure_seen.add(key);currency=row.get('currency') or (view.get('account') or {}).get('currency','USD')
            title=str(row['symbol'])+' · operación cerrada';body=f"#{row['ticket']} · neto {float(row['net']):+.2f} {currency}\nMotivo: {row.get('cause','Sin causa recibida')}";severity='warning' if float(row['net'])<0 else 'info'
            if self.notices.add_once(title,body,key,severity=severity):self.emit('notice',{'title':title,'body':body,'severity':severity,'financial':True})
        signature=tuple(sorted((str(o.get('ticket')),o.get('entry'),o.get('sl'),o.get('tp')) for o in view.get('orders') or [] if o.get('owned')))
        if self._pending_signature is not None and signature!=self._pending_signature and self.cfg['desktop'].get('notify_pending_change',True):self.notify('Pendientes actualizadas','MT5 confirmó un cambio en el mapa. Consulta los tickets y niveles en Cuenta.')
        self._pending_signature=signature

    def ask(self,message,use_cloud=False):
        message=str(message).strip()
        if not message or self.chat_busy:return False
        self.chat_busy=True;self.assistant.reset_cancel();snapshot={**self.view,'network_available':self.online if self.online is not None else self.view.get('network_available',True)}
        cid=self.assistant.chats.active
        def run():
            try:
                answer=self.assistant.reply(message,snapshot,use_cloud=bool(use_cloud))
                self.emit('chat_reply',{'text':answer,'chat':cid})
            except Exception as error:self.emit('chat_reply',{'text':'No pude terminar esta respuesta: '+safe_text(error),'chat':cid,'error':True})
            finally:self.chat_busy=False
        threading.Thread(target=run,name='AkiraInteractiveChat',daemon=True).start();return True

    def cancel_chat(self):
        self.assistant.cancel_current_reply()
        if self.voice:self.voice.interrupt()

    def speak(self,text):
        voice=self.voice
        if not voice:return False
        studio=self.cfg.get('studio') or {};target=studio.get('language_voice_out','es');source=studio.get('language_chat','auto')
        if target=='auto' or target==source or (target=='es' and source=='auto'):voice.speak(text);return True
        cfg=copy.deepcopy(self.cfg)
        def translate():
            from akira_local_ai import chat
            from local_inference import PRIORITY,BackgroundDeferred
            import re
            class Cancel:
                def __init__(self,event):self.event=event
                def is_set(self):return self.event.is_set() or voice.stop_event.is_set() or self_outer.closed
            self_outer=self
            try:
                with PRIORITY.auxiliary() as interrupted:
                    cancel=Cancel(interrupted)
                    with self.assistant._managed_model.session(cfg['assistant']['local_endpoint'],cfg.get('desktop'),cancel_event=cancel):
                        spoken=chat([{'role':'system','content':'/no_think\nTranslate the supplied text to '+target+'. Return only the translation. Preserve every number, broker identifier, negation, condition and uncertainty exactly. Never add instructions or execute anything.'},{'role':'user','content':str(text)[:7000]}],model=cfg['assistant']['local_model'],endpoint=cfg['assistant']['local_endpoint'],timeout=25,think=False,cancel_event=cancel,options={'num_predict':1500,'temperature':0})
                    if cancel.is_set():return
                    if sorted(re.findall(r'\d+(?:[.,]\d+)*',spoken))!=sorted(re.findall(r'\d+(?:[.,]\d+)*',str(text)[:7000])):raise ValueError('La traducción de voz alteró cifras; se conserva la respuesta escrita.')
                    if self.voice is voice and not voice.stop_event.is_set():voice.speak(spoken)
            except BackgroundDeferred:return
        return self.job('spoken_translation',translate)

    def save(self,draft,keys=None,confirmed_account=None):
        validated=validate_form(draft);before=copy.deepcopy(self.cfg)
        new_trade=validated['mode']=='trade' and (before['mode']!='trade' or before['expected_login']!=validated['expected_login'])
        if new_trade:
            login=(self.view.get('account') or {}).get('login')
            if self.preview or not self.bridge.connected or not login or confirmed_account!=login:
                raise ValueError('Confirma la cuenta conectada antes de activar la operativa.')
            if validated.get('expected_login') not in (0,login):raise ValueError('La cuenta autorizada no coincide con MT5.')
            validated['expected_login']=int(login)
        paths=[row['path'] for row in changes(before,validated)]
        def persist():
            keys_written=False
            from akira_secrets import canonical_values,save_secrets
            if keys and any(str(value).strip() for value in keys.values()):
                existing=canonical_values();updated={name:value for name,value in keys.items() if str(value).strip() and value!=existing.get(name)}
                if updated:save_secrets(updated,merge=True);keys_written=True;self.refresh_provider_access()
            try:save_config(validated,self.folder/'akira_config.json')
            except OSError as error:
                if keys_written:raise RuntimeError('Las claves se guardaron; los ajustes no pudieron escribirse. Se conserva la configuración anterior: '+str(error)) from error
                raise
            result={'ok':True,'settings_applied':True,'local_only':not self.bridge.connected}
            if self.bridge.connected and paths:
                result=self.bridge.request({'action':'apply_settings','config':validated,'changed_paths':paths})
                if not result.get('ok') and not result.get('unconfirmed'):
                    save_config(before,self.folder/'akira_config.json')
                    raise RuntimeError(('Las claves se guardaron. ' if keys_written else '')+'No se aplicaron los ajustes; configuración anterior conservada. '+str(result.get('error','')))
            self.cfg=copy.deepcopy(validated);self.assistant.cfg=self.cfg
            self.assistant._managed_model.settings=self.cfg.get('assistant') or {}
            if hasattr(self,'knowledge'):self.knowledge.cfg=self.cfg
            return {'config':copy.deepcopy(self.cfg),'paths':paths,'result':result,'saved':True,'keys_saved':bool(keys)}
        return self.job('save_settings',persist,'settings_saved')

    def refresh_provider_access(self):
        """Drop cached authentication failures when the user changes a credential."""
        import providers
        for cache,lock in (('_YT_CACHE','_YT_LOCK'),('_CG_AUTH_CACHE','_CG_AUTH_LOCK')):
            store=getattr(providers,cache,None);guard=getattr(providers,lock,None)
            if store is not None:
                if guard:
                    with guard:store.clear()
                else:store.clear()
        self.assistant._cache.clear() if hasattr(self.assistant,'_cache') else None
        if self.bridge.connected:self.request({'action':'refresh_sources'})

    def collect_resources(self,wallpaper=None):
        if self._usage_loading or time.monotonic()<self._usage_due:return
        self._usage_loading=True;self._usage_due=time.monotonic()+4
        def sample():
            try:
                import psutil
                if not hasattr(self,'_meter'):self._meter=psutil.Process(os.getpid());self._meter.cpu_percent()
                own={'app':{'pid':self._meter.pid,'ram_mb':round(self._meter.memory_info().rss/1048576,1),'cpu_percent':round(self._meter.cpu_percent()/max(1,os.cpu_count() or 1),2)}}
                for name,proc in (('model',self.assistant._managed_model.proc),('wallpaper',wallpaper),('voice',getattr(self.voice,'process',None))):
                    if proc and proc.poll() is None:
                        try:
                            meter=psutil.Process(proc.pid);own[name]={'pid':proc.pid,'ram_mb':round(meter.memory_info().rss/1048576,1)}
                        except psutil.Error:pass
                self.resources={'processes':own,'system_ram_percent':psutil.virtual_memory().percent}
                return self.resources
            finally:self._usage_loading=False
        self.job('resources',sample,'resources')

    def export_report(self,path,format='pdf',hours=24):
        def export():
            from operation_report import build_report,export_report,read_recent_events
            if self.bridge.connected:
                result=self.bridge.request({'action':'export_report_snapshot'})
                if not result.get('ok'):raise RuntimeError('No se obtuvo la instantánea completa del informe.')
                view=result['snapshot']
            else:view=copy.deepcopy(self.view)
            events,truncated=read_recent_events(self.folder/'logs',hours,time.time())
            view['operational_events']=list({(r.get('utc'),r.get('symbol'),r.get('operation')):r for r in [*(view.get('operational_events') or []),*events]}.values());view['event_log_truncated']=truncated
            model=build_report(view,hours=hours);export_report(model,Path(path),format=format)
            return {'path':str(path),'format':format}
        return self.job('export_report',export,'exported')

    def export_diagnostic(self,path):
        def export():
            from operation_report import redact_snapshot
            def strip(value):
                if isinstance(value,dict):return {k:strip(v) for k,v in value.items() if not any(word in k.lower() for word in ('key','secret','cookie','password','token','history'))}
                if isinstance(value,list):return [strip(v) for v in value]
                return value
            data={'build':__import__('akira_version').BUILD_ID,'snapshot':redact_snapshot(copy.deepcopy(self.view)),
                  'preferences':strip(self.cfg),'resources':self.resources,'errors':[safe_text(r.get('message','')) for r in self.log_rows if r.get('symbol')=='ERROR']}
            Path(path).write_text(json.dumps(data,ensure_ascii=False,indent=2,default=str),encoding='utf-8');return {'path':str(path)}
        return self.job('export_diagnostic',export,'exported')

    def close(self):
        self.closed=True;self.stop.set();self.cancel_chat()
        if self.voice:self.voice.stop()
        if self.network:self.network.close()
        if hasattr(self,'knowledge'):self.knowledge.close()
        self.io.shutdown(wait=False,cancel_futures=True)
        self.assistant._managed_model.shutdown_async()
