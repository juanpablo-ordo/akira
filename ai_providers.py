"""Configured, verifiable text providers. Names alone never indicate health."""
import json,time,threading
from urllib.parse import urlsplit
from urllib.request import Request,build_opener,HTTPSHandler,HTTPRedirectHandler
from network_tls import https_context
from source_recovery import SourceDeadline
from akira_secrets import get_secret

_CALLS=SourceDeadline(limit=2)  # shared: abandoned sockets cannot spawn unlimited replacements

class NoCredentialRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('El proveedor redirigió la solicitud autenticada; configura su endpoint final')

def validate_endpoint(endpoint):
    u=urlsplit(endpoint)
    if u.username or u.password or u.query or u.fragment:raise ValueError('Endpoint IA sin credenciales, parámetros ni fragmentos')
    if not u.hostname or u.scheme not in ('https','http'):raise ValueError('Endpoint IA inválido')
    if u.scheme=='http' and u.hostname not in ('127.0.0.1','localhost','::1'):raise ValueError('La IA externa requiere HTTPS')
    if not u.path.endswith('/chat/completions'):raise ValueError('Usa un endpoint compatible /v1/chat/completions')
    return endpoint

class CloudAIProvider:
    def __init__(self,config,transport=None):
        self.config=config;self.transport=transport;self.calls=_CALLS
    def complete(self,messages,purpose='conversation',cancel_event=None,progress=None,response_format=None,timeout=None):
        cfg=self.config.get('assistant',{});endpoint=validate_endpoint(str(cfg.get('cloud_endpoint','')))
        model=str(cfg.get({'conversation':'general_model','research':'research_model','trade_review':'trading_model'}[purpose]) or cfg.get('model','')).strip()
        if not model:raise ValueError('Selecciona un modelo del proveedor externo')
        key=get_secret('OPENAI_API_KEY' if urlsplit(endpoint).hostname=='api.openai.com' else 'CUSTOM_AI_API_KEY')
        if not key and urlsplit(endpoint).hostname not in ('127.0.0.1','localhost','::1'):raise ValueError('Falta la clave del proveedor IA seleccionado')
        budget=float(timeout or cfg.get(purpose+'_timeout_seconds',150))
        payload={'model':model,'messages':messages,'stream':response_format is None,'max_tokens':700 if purpose=='conversation' else 1100}
        if response_format:payload['response_format']={'type':'json_schema','json_schema':{'name':'akira_review','strict':True,'schema':response_format}}
        def perform():
            headers={'Content-Type':'application/json','Accept':'text/event-stream' if payload['stream'] else 'application/json'}
            if key:headers['Authorization']='Bearer '+key
            req=Request(endpoint,data=json.dumps(payload,ensure_ascii=False).encode(),headers=headers,method='POST')
            opener=self.transport or build_opener(HTTPSHandler(context=https_context()),NoCredentialRedirect()).open
            deadline=time.monotonic()+budget;answer='';finish=None
            with opener(req,timeout=min(30,budget)) as response:
                if payload['stream']:
                    total=0
                    for raw in response:
                        if cancel_event is not None and cancel_event.is_set():raise RuntimeError('Análisis detenido por el usuario')
                        if time.monotonic()>deadline:raise TimeoutError('La generación externa agotó su plazo')
                        total+=len(raw)
                        if total>2_000_000:raise ValueError('Respuesta externa demasiado grande')
                        line=raw.decode('utf-8').strip()
                        if not line.startswith('data:'):continue
                        data=line[5:].strip()
                        if data=='[DONE]':break
                        chunk=json.loads(data)
                        if chunk.get('error'):raise RuntimeError('El proveedor devolvió un error de generación')
                        for choice in chunk.get('choices',[]):
                            text=(choice.get('delta') or {}).get('content') or ''
                            if not isinstance(text,str):raise ValueError('Fragmento externo inválido')
                            answer+=text;finish=choice.get('finish_reason') or finish
                            if text and progress:progress(answer)
                else:
                    raw=response.read(2_000_001)
                    if len(raw)>2_000_000:raise ValueError('Respuesta externa demasiado grande')
                    data=json.loads(raw);choice=(data.get('choices') or [{}])[0]
                    answer=(choice.get('message') or {}).get('content') or '';finish=choice.get('finish_reason')
            if not isinstance(answer,str) or not answer.strip():raise ValueError('El proveedor no devolvió texto')
            if finish not in ('stop',):raise ValueError('La respuesta externa no terminó: '+str(finish))
            return answer
        return self.calls.run('provider:'+endpoint,perform,budget,cancel_event=cancel_event)

class AIProviderManager:
    def __init__(self,config,health=None):
        self.config=config;self.health=health;self.cloud=CloudAIProvider(config)
    def order(self):
        cfg=self.config.get('assistant',{});mode=cfg.get('provider_mode','local')
        if mode!='auto':return [mode]
        primary=cfg.get('provider_primary','local')
        return [primary,'cloud' if primary=='local' else 'local']
    def run(self,purpose,local,cloud,cancel_event=None):
        errors=[]
        for provider in self.order():
            if cancel_event is not None and cancel_event.is_set():raise RuntimeError('Análisis detenido por el usuario')
            if self.health:self.health.begin(provider,str(self.config['assistant'].get('local_model' if provider=='local' else {'conversation':'general_model','research':'research_model','trade_review':'trading_model'}[purpose])))
            try:
                answer=(local if provider=='local' else cloud)()
                if not str(answer).strip():raise ValueError('Respuesta vacía')
                self.last_provider=provider
                if self.health:self.health.finish(answer)
                return answer
            except Exception as exc:
                if self.health:self.health.finish(error=exc)
                errors.append(provider+': '+type(exc).__name__+': '+str(exc)[:220])
        raise RuntimeError(' | '.join(errors))
