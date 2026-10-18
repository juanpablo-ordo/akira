"""Akira Local Core — IA local sin créditos para AKIRA FINAL V6 PUBLIC AI.

Ollama corre fuera del HOT loop. Este módulo proporciona conversación, tool-calling
local y visión opcional. Nunca llama MT5 ni decide órdenes directamente.
"""
from __future__ import annotations
import json, os, re, time, threading
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from urllib.parse import urlsplit
from http.client import HTTPConnection
from contextlib import contextmanager
import io

_STATUS={"when":0.0,"ok":None,"detail":"no comprobado"}
_STATUS_LOCK=threading.Lock()
_CONTEXT=threading.local()

@contextmanager
def visible_output(callback):
    previous=getattr(_CONTEXT,'visible',None);_CONTEXT.visible=callback
    try:yield
    finally:_CONTEXT.visible=previous

@contextmanager
def owned_context(tokens):
    """Actual owned server context, scoped to this request's worker thread."""
    previous=getattr(_CONTEXT,'tokens',None);_CONTEXT.tokens=int(tokens)
    try:yield
    finally:_CONTEXT.tokens=previous

def fit_owned_request(endpoint,payload,timeout,cancel_event):
    """Count the exact Jinja prompt with the same pinned server, not characters.

    Only old conversational turns may be removed. System instructions, evidence,
    tools and the current user message remain intact or the request fails.
    """
    context=getattr(_CONTEXT,'tokens',None)
    if not context:return payload
    parts=urlsplit(endpoint);base=parts.scheme+'://'+parts.netloc;deadline=time.monotonic()+float(timeout)
    result={**payload,'messages':list(payload['messages'])}
    for _ in range(8):
        if cancel_event is not None and cancel_event.is_set():raise RuntimeError('Análisis detenido por el usuario')
        remaining=deadline-time.monotonic()
        if remaining<=0:raise TimeoutError('Se agotó el plazo preparando el contexto local')
        template=_post(base+'/apply-template',result,timeout=min(3,remaining),cancel_event=cancel_event,stream_on_cancel=False)
        if not isinstance(template.get('prompt'),str):raise RuntimeError('El servidor no confirmó la plantilla del contexto local')
        tokens=_post(base+'/tokenize',{'content':template['prompt'],'add_special':True,'parse_special':True,'with_pieces':False},timeout=min(3,max(.1,deadline-time.monotonic())),cancel_event=cancel_event,stream_on_cancel=False).get('tokens')
        if not isinstance(tokens,list):raise RuntimeError('El servidor no confirmó los tokens del contexto local')
        room=context-len(tokens)-64
        wanted=max(128,min(int(result['max_tokens']),context//2))
        if room>=wanted:result['max_tokens']=min(int(result['max_tokens']),room);return result
        messages=result['messages'];last_user=max((i for i,r in enumerate(messages) if r.get('role')=='user'),default=-1)
        old=[i for i,r in enumerate(messages[:last_user]) if r.get('role') in ('user','assistant') and not r.get('tool_calls')]
        if old:
            remove=set(old[:2]);result['messages']=[r for i,r in enumerate(messages) if i not in remove];continue
        if room>=128:result['max_tokens']=min(int(result['max_tokens']),room);return result
        raise RuntimeError('El mensaje y sus datos esenciales no caben en el contexto local de '+str(context)+' tokens. Amplía el contexto en Ajustes o reduce el adjunto; no se recortó la pregunta ni se ejecutó ninguna acción.')
    raise RuntimeError('No se pudo ajustar la conversación al contexto local sin quitar datos esenciales')


def _post_direct_cancellable(url,payload,timeout,cancel_event):
    """Own the socket before response headers, where model generation can wait."""
    parts=urlsplit(url);connection=HTTPConnection(parts.hostname,parts.port or 80,timeout=timeout)
    done=threading.Event();expired=threading.Event();deadline=time.monotonic()+float(timeout)
    def interrupt():
        while not done.wait(.05):
            if time.monotonic()>=deadline or cancel_event.is_set():
                if time.monotonic()>=deadline:expired.set()
                try:
                    import socket
                    if connection.sock is not None:connection.sock.shutdown(socket.SHUT_RDWR)
                except (OSError,AttributeError):pass
                connection.close();return
    threading.Thread(target=interrupt,name='AkiraCancelLocal',daemon=True).start()
    try:
        path=parts.path+('?' +parts.query if parts.query else '')
        connection.request('POST',path,json.dumps(payload,ensure_ascii=False).encode('utf-8'),
                           {'Content-Type':'application/json','User-Agent':'AKIRA local'})
        response=connection.getresponse()
        if response.status>=400:
            raise HTTPError(url,response.status,response.reason,response.headers,io.BytesIO(response.read(2000)))
        if payload.get('stream'):
            content=[];total=0;last=0;finish=None
            while True:
                raw=response.readline()
                if not raw:break
                total+=len(raw)
                if total>8_000_000:raise RuntimeError('Respuesta de IA demasiado grande')
                if cancel_event.is_set():raise RuntimeError('Análisis detenido por el usuario')
                if not raw.startswith(b'data:'):continue
                data=raw[5:].strip()
                if data==b'[DONE]':break
                choice=(json.loads(data).get('choices') or [{}])[0];delta=choice.get('delta') or {}
                if delta.get('content'):content.append(str(delta['content']))
                if choice.get('finish_reason'):finish=choice['finish_reason']
                callback=getattr(_CONTEXT,'visible',None)
                if callback and content and time.monotonic()-last>.08:callback(_clean(''.join(content)));last=time.monotonic()
            callback=getattr(_CONTEXT,'visible',None)
            if callback and content:callback(_clean(''.join(content)))
            result={'choices':[{'message':{'role':'assistant','content':''.join(content)},'finish_reason':finish}]}
        else:result=json.loads(response.read(8_000_000).decode('utf-8','replace'))
        if expired.is_set():raise TimeoutError('AKIRA agotó el tiempo total de inferencia')
        if cancel_event.is_set():raise RuntimeError('Análisis detenido por el usuario')
        return result
    except Exception:
        if expired.is_set():raise TimeoutError('AKIRA agotó el tiempo total de inferencia; la consulta fue detenida') from None
        if cancel_event.is_set():raise RuntimeError('Análisis detenido por el usuario') from None
        raise
    finally:done.set();connection.close()


def _post(url,payload,timeout=90,cancel_event=None,stream_on_cancel=True):
    """Streaming cancellable; close the real socket when user presses DETENER."""
    if cancel_event is not None and cancel_event.is_set():
        raise RuntimeError('Análisis detenido por el usuario')
    parts=urlsplit(str(url))
    if cancel_event is not None and parts.scheme=='http' and parts.hostname in ('127.0.0.1','localhost','::1') and parts.path.rstrip('/').endswith('/v1/chat/completions'):
        return _post_direct_cancellable(url,payload,timeout,cancel_event)
    streaming = cancel_event is not None and stream_on_cancel
    payload=dict(payload)
    if streaming:payload['stream']=True
    req=Request(url,data=json.dumps(payload,ensure_ascii=False).encode('utf-8'),headers={
        'Content-Type':'application/json','User-Agent':'Akira/13.2 Local AI'})
    finished=threading.Event();expired=threading.Event();deadline=time.monotonic()+float(timeout)
    with urlopen(req,timeout=timeout) as r:
        def interrupt():
            while not finished.wait(.10):
                timed_out=time.monotonic()>=deadline
                if timed_out or (cancel_event is not None and cancel_event.is_set()):
                        if timed_out:expired.set()
                        try:
                            # Interrupt a blocking readline from the other thread.
                            import socket
                            sock=getattr(getattr(getattr(r,'fp',None),'raw',None),'_sock',None)
                            if sock is not None:sock.shutdown(socket.SHUT_RDWR)
                        except Exception:pass
                        try:r.close()
                        except Exception:pass
                        break
        threading.Thread(target=interrupt,name='AkiraCancelHTTP',daemon=True).start()
        try:
            if not streaming:
                result=json.loads(r.read(8_000_000).decode('utf-8','replace'))
                if expired.is_set():raise TimeoutError('AKIRA agotó el tiempo total de inferencia; la consulta fue detenida')
                return result
            content=[];tool_calls=[];last={};bytes_read=0
            for raw in r:
                if cancel_event.is_set():raise RuntimeError('Análisis detenido por el usuario')
                bytes_read+=len(raw)
                if bytes_read>16_000_000:raise RuntimeError('Respuesta de IA demasiado grande')
                if not raw.strip():continue
                chunk=json.loads(raw.decode('utf-8','replace'))
                if chunk.get('error'):raise RuntimeError(str(chunk['error'])[:300])
                msg=chunk.get('message') or {}
                if msg.get('content'):content.append(str(msg['content']))
                for call in msg.get('tool_calls') or []:
                    # Ollama normalmente envía cada tool-call completa en un chunk.
                    if call not in tool_calls:tool_calls.append(call)
                if chunk.get('done'):last=chunk
            if expired.is_set():raise TimeoutError('AKIRA agotó el tiempo total de inferencia; la consulta fue detenida')
            if cancel_event.is_set():raise RuntimeError('Análisis detenido por el usuario')
            return {'message':{'role':'assistant','content':''.join(content),'tool_calls':tool_calls},**{k:v for k,v in last.items() if k!='message'}}
        except Exception:
            if expired.is_set():raise TimeoutError('AKIRA agotó el tiempo total de inferencia; la consulta fue detenida') from None
            if cancel_event is not None and cancel_event.is_set():
                raise RuntimeError('Análisis detenido por el usuario') from None
            raise
        finally:finished.set()


# llama.cpp can serve the OpenAI-compatible API locally, without Ollama.
# This client never launches another user's process or uploads chats remotely.
def _direct_local_engine(endpoint):
    parts=urlsplit(str(endpoint))
    if not parts.path.rstrip('/').endswith('/v1/chat/completions'):
        return False
    if parts.scheme != 'http' or parts.hostname not in ('127.0.0.1','localhost','::1'):
        raise ValueError('El motor local solo admite conexiones HTTP a esta computadora')
    return True

def _direct_base(endpoint):
    return str(endpoint).rsplit('/chat/completions',1)[0]

def _direct_chat(messages,model,endpoint,timeout,tools,options,raw,think,cancel_event,response_format):
    opts=dict(options or {})
    mapped=[]
    for message in messages:
        m=dict(message)
        if m.get('role') == 'tool':
            m={'role':'tool','tool_call_id':str(m.get('tool_call_id') or m.get('tool_name') or ''),
               'content':str(m.get('content') or '')}
        mapped.append(m)
    payload={'model':model,'messages':mapped,'stream':False,
             'temperature':float(opts.get('temperature',.2)),
             'top_p':float(opts.get('top_p',.90)),
             'max_tokens':int(opts.get('num_predict',3000)),
             'chat_template_kwargs':{'enable_thinking':bool(think)}}
    if tools:payload['tools']=tools
    elif response_format is None and getattr(_CONTEXT,'visible',None) is not None and cancel_event is not None:payload['stream']=True
    if not think and mapped and not any('/no_think' in str(m.get('content','')) for m in mapped):
        # Qwen3 can consume the whole token budget in hidden reasoning otherwise.
        mapped.insert(0,{'role':'system','content':'/no_think\nDa una respuesta visible, concisa y útil.'})
    if response_format is not None:
        if response_format=='json':payload['response_format']={'type':'json_object'}
        elif isinstance(response_format,dict) and response_format.get('type') not in ('json_object','json_schema'):
            # llama.cpp expects a format envelope, not a bare JSON Schema.
            payload['response_format']={'type':'json_object','schema':response_format}
        else:payload['response_format']=response_format
    try:
        began=time.monotonic();payload=fit_owned_request(endpoint,payload,timeout,cancel_event)
        data=_post(endpoint,payload,timeout=max(.1,float(timeout)-(time.monotonic()-began)),cancel_event=cancel_event,stream_on_cancel=False)
    except HTTPError as exc:
        raise RuntimeError(f'Motor local HTTP {exc.code}: '+exc.read(500).decode('utf-8','replace')) from exc
    except URLError as exc:
        raise RuntimeError(f'Motor local llama.cpp no disponible: {exc.reason}') from exc
    choice=((data.get('choices') or [{}])[0])
    message=choice.get('message') or {}
    result={'message':message,'done':choice.get('finish_reason') not in ('length',),
            'backend':'llama.cpp','finish_reason':choice.get('finish_reason')}
    if raw:return result
    if response_format is not None and not result['done']:
        raise RuntimeError('La respuesta estructurada del motor local quedó incompleta')
    output=_clean(message.get('content'))
    if not output:raise RuntimeError('El motor local respondió sin contenido')
    return output

def status(endpoint='http://127.0.0.1:11434/api/chat',force=False):
    now=time.monotonic()
    with _STATUS_LOCK:
        if not force and _STATUS.get('endpoint')==endpoint and _STATUS.get('ok') is not None and now-float(_STATUS.get('when') or 0)<15:
            return dict(_STATUS)
    direct=_direct_local_engine(endpoint)
    base=_direct_base(endpoint) if direct else endpoint.rsplit('/api/',1)[0]
    try:
        req=Request(base+('/models' if direct else '/api/tags'),headers={'User-Agent':'Akira/7.3 Local AI'})
        with urlopen(req,timeout=2.5) as r:
            data=json.loads(r.read(800_000).decode('utf-8','replace'))
        key='data' if direct else 'models'
        if not isinstance(data,dict) or not isinstance(data.get(key),list):raise ValueError('Respuesta de disponibilidad inválida')
        models=list(dict.fromkeys(str(x.get('id') if direct else (x.get('name') or x.get('model'))) for x in data[key] if isinstance(x,dict) and (x.get('id') if direct else (x.get('name') or x.get('model')))))
        row={'when':now,'ok':True,'detail':'AKIRA activo','models':models}
    except Exception as exc:
        row={'when':now,'ok':False,'detail':f'{type(exc).__name__}: {exc}','models':[]}
    row['endpoint']=endpoint
    with _STATUS_LOCK:_STATUS.clear();_STATUS.update(row)
    return dict(row)


def choose_text_model(available,preferred='qwen3:8b',lite='qwen3:4b',prefer_fast=False):
    names=[str(x) for x in (available or [])]
    if prefer_fast:
        for wanted in (preferred,lite,'qwen3:8b','qwen3:4b','gemma3:4b'):
            matches=[n for n in names if n==wanted or n.startswith(wanted+'-') or n.startswith(wanted+':')]
            if wanted and matches:return matches[0]
    # REFLEX prioriza el modelo local más capaz ya instalado. El instalador solo
    # descarga modelos grandes cuando la RAM declarada deja margen suficiente.
    order=[]
    for candidate in ('qwen3:30b-a3b','qwen3:14b'):
        if any(n.startswith(candidate) for n in names): order.append(candidate)
    order.extend([preferred,lite,'qwen3:8b','qwen3:4b','gemma3:4b'])
    for wanted in order:
        if wanted:
            matches=[n for n in names if n==wanted or n.startswith(wanted+'-') or n.startswith(wanted+':')]
            if matches:return matches[0]
    # Reuse an installed conversational model when the configured one is absent.
    # Embedding and vision-only models cannot stand in for the text assistant.
    for name in names:
        if name.lower().startswith(('qwen','gemma','llama','mistral','phi','deepseek','gpt-oss')) and not any(x in name.lower() for x in ('embed','vision','-vl',':vl')):
            return name
    if len(names)==1:return names[0]  # El motor llama.cpp anuncia un único GGUF
    return preferred if preferred and preferred!='auto' else 'qwen3:8b'


def _clean(text):
    text=str(text or '')
    text=re.sub(r'<think>.*?</think>','',text,flags=re.I|re.S).strip()
    text=re.sub(r'^\s*</?think>\s*','',text,flags=re.I).strip()
    return text


def chat(messages,model='qwen3:8b',endpoint='http://127.0.0.1:11434/api/chat',timeout=90,
         tools=None,options=None,keep_alive='90s',raw=False,think=False,cancel_event=None,response_format=None):
    if _direct_local_engine(endpoint):
        return _direct_chat(messages,model,endpoint,timeout,tools,options,raw,think,cancel_event,response_format)
    payload={'model':model,'messages':messages,'stream':False,'think':bool(think),'keep_alive':keep_alive,
             'options':{'temperature':0.15,'num_ctx':8192,'num_predict':3000,'top_p':0.90,'num_thread':max(2,min(4,(os.cpu_count() or 4)//2))}}
    if options: payload['options'].update(options)
    if tools: payload['tools']=tools
    if response_format is not None:payload['format']=response_format
    try:data=_post(endpoint,payload,timeout=timeout,cancel_event=cancel_event)
    except HTTPError as exc:
        try:detail=exc.read(100000).decode('utf-8','replace')
        except Exception:detail=str(exc)
        raise RuntimeError(f'Ollama HTTP {exc.code}: {detail[:500]}')
    except URLError as exc: raise RuntimeError(f'Akira Local Core no disponible: {exc.reason}')
    if raw:return data
    if response_format is not None and data.get('done') is False:raise RuntimeError('La respuesta estructurada de AKIRA quedó incompleta')
    text=_clean((data.get('message') or {}).get('content'))
    if not text: raise RuntimeError('Akira Local Core respondió sin texto')
    return text


def vision_chat(prompt,images_b64,model='gemma3:4b',endpoint='http://127.0.0.1:11434/api/chat',timeout=150):
    if _direct_local_engine(endpoint):
        content=[{'type':'text','text':str(prompt)}]
        content += [{'type':'image_url','image_url':{'url':'data:image/jpeg;base64,'+str(x)}} for x in images_b64 if x]
        msg={'role':'user','content':content}
    else:
        msg={'role':'user','content':str(prompt),'images':[str(x) for x in images_b64 if x]}
    return chat([{'role':'system','content':'Eres el módulo visual local de Akira. Describe solo lo que realmente aparece en las imágenes y separa observación de inferencia.'},msg],
                model=model,endpoint=endpoint,timeout=timeout,options={'temperature':0.20,'num_ctx':8192,'num_predict':1800},keep_alive='0')


def agent(messages,tools,executor,model='qwen3:8b',endpoint='http://127.0.0.1:11434/api/chat',timeout=120,max_rounds=3,reasoning=False,cancel_event=None,options=None,total_timeout=None,context_char_budget=28000,keep_alive='90s'):
    """Tool loop local. `tools` usa el esquema nativo de Ollama.

    Si el modelo no emite tool_calls, devuelve su respuesta normal. Las herramientas
    son ejecutadas por código confiable, nunca por texto arbitrario del modelo.
    """
    convo=list(messages)
    deadline=time.monotonic()+float(total_timeout if total_timeout is not None else timeout)
    def remaining():
        seconds=deadline-time.monotonic()
        if seconds<=0:raise TimeoutError('El modelo agotó el tiempo total de esta respuesta')
        return min(float(timeout),seconds)
    allowed={str((row.get('function') or {}).get('name')) for row in (tools or [])}
    rounds=max(1,min(int(max_rounds or 3),8))
    for _ in range(rounds):
        if cancel_event is not None and cancel_event.is_set():raise RuntimeError('Análisis detenido por el usuario')
        data=chat(convo,model=model,endpoint=endpoint,timeout=remaining(),tools=tools,raw=True,think=reasoning,cancel_event=cancel_event,options=options,keep_alive=keep_alive)
        if cancel_event is not None and cancel_event.is_set():raise RuntimeError('Análisis detenido por el usuario')
        msg=data.get('message') or {}
        calls=msg.get('tool_calls') or []
        text=_clean(msg.get('content'))
        if not calls:
            if text:return text
            raise RuntimeError('Akira Local Core no devolvió respuesta visible')
        convo.append({'role':'assistant','content':text,'tool_calls':calls})
        for call in calls[:5]:
            if cancel_event is not None and cancel_event.is_set():raise RuntimeError('Análisis detenido por el usuario')
            remaining()
            fn=(call.get('function') or {}) if isinstance(call,dict) else {}
            name=str(fn.get('name') or '')
            args=fn.get('arguments') or {}
            if isinstance(args,str):
                try:args=json.loads(args)
                except Exception:args={}
            try:
                if name not in allowed:raise ValueError('Herramienta fuera del alcance de este pedido')
                result=executor(name,args if isinstance(args,dict) else {})
            except Exception as exc:result={'ok':False,'error':f'{type(exc).__name__}: {exc}'}
            content=json.dumps(result,ensure_ascii=False,default=str)
            current_size=sum(len(str(row.get('content') or '')) for row in convo)
            available=max(0,int(context_char_budget)-current_size-400)
            if available<200:content='Resultado demasiado grande; usa los datos suministrados para responder.'
            elif len(content)>min(10000,available):content=content[:min(10000,available)]+'…'
            if _direct_local_engine(endpoint):
                convo.append({'role':'tool','tool_call_id':str(call.get('id') or name),'content':content})
            else:convo.append({'role':'tool','tool_name':name,'content':content})
    # one final synthesis without tools
    if cancel_event is not None and cancel_event.is_set():raise RuntimeError('Análisis detenido por el usuario')
    return chat(convo,model=model,endpoint=endpoint,timeout=remaining(),tools=None,think=reasoning,cancel_event=cancel_event,options=options,keep_alive=keep_alive)
