"""Real Piper/Whisper and optional local LLM, using a synthetic audio sink.

No microphone or broker is contacted. --app checks the actual windowed EXE's
persistent speech worker, including the absence of stdin/stdout in that build.
"""
import argparse,hashlib,json,os,sys,tempfile,threading,time,traceback,wave
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
from urllib.request import urlopen

VOICE='es_ES-davefx-medium'
FILES={'.onnx':'6658b03b1a6c316ee4c265a9896abc1393353c2d9e1bca7d66c2c442e222a917',
    '.onnx.json':'0e0dda87c732f6f38771ff274a6380d9252f327dca77aa2963d5fbdf9ec54842'}

def get_voice(root):
    folder=Path(root)/'state/voices';folder.mkdir(parents=True,exist_ok=True)
    for suffix,expected in FILES.items():
        path=folder/(VOICE+suffix)
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            with urlopen('https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/davefx/medium/'+VOICE+suffix,timeout=45) as response:payload=response.read(80_000_000)
            if hashlib.sha256(payload).hexdigest()!=expected:raise ValueError('Voz de prueba sin verificar')
            path.write_bytes(payload)
    return {'engine':'piper','id':'piper:'+VOICE,'model':str(folder/(VOICE+'.onnx')),'speaker':0}

def recognize_qa(audio,stt,root,terms):
    """Accept only real ASR that understands a meaningful part of the sentence."""
    from voice_session import recognition_model,transcribe_with_recovery
    def meaningful(text):
        return len(text.split())>=4 and any(term in text.casefold() for term in terms)
    first=transcribe_with_recovery(stt,audio,language='es',beam_size=1,vad_filter=False)
    if meaningful(first):return first,stt
    # Tiny can drop the beginning of synthetic Piper speech; confirm with
    # a stronger real Whisper model instead of accepting a truncated fragment.
    stronger=recognition_model(root,'base')
    second=transcribe_with_recovery(stronger,audio,language='es',beam_size=5,vad_filter=False)
    if meaningful(second):return second,stronger
    raise AssertionError('Reconocimiento incompleto: tiny='+repr(first)+'; base='+repr(second))


def run(report,voice_root,app=None,exe=None,model=None):
    from voice_session import SpeechServer,render_speech,recognition_model,VoiceSession
    from settings import DEFAULT,load_config
    result={'status':'FAILED','audio_devices':'SYNTHETIC OUTPUT; no microphone','live_account_used':False,
        'speech_worker':'frozen Windows EXE' if app else 'source Python','real_language_model':bool(exe and model)}
    worker=SpeechServer(command=[str(Path(app).resolve())] if app else None);call=None;voice=None;runtime=None;temporary=None
    try:
        selected=get_voice(voice_root)
        temporary=tempfile.TemporaryDirectory(prefix='akira_spoken_check_');tmp=temporary.name
        root=Path(tmp);request={'voice':selected,'path':str(root/'heard.wav'),
            'text':'Dime el saldo de mi cuenta.','rate':160,'volume':.8}
        start=time.monotonic();worker.render(request,lambda:False);pid=worker.proc.pid
        request.update(path=str(root/'preview.wav'),text='Hola, soy Akira. Estoy escuchando.')
        worker.render(request,lambda:False)
        if worker.proc.pid!=pid:raise AssertionError('No se reutilizó la voz entre frases')
        with wave.open(str(root/'preview.wav')) as wav:
            if wav.getnframes()<1000:raise AssertionError('Voz sin audio')
            result['preview_seconds']=round(wav.getnframes()/wav.getframerate(),2)
        result['synthesis_seconds']=round(time.monotonic()-start,3);result['voice_worker_reused']=True
        import numpy as np
        with wave.open(str(root/'heard.wav')) as wav:
            rate=wav.getframerate();audio=np.frombuffer(wav.readframes(wav.getnframes()),dtype='int16').astype('float32')/32768
        audio=np.interp(np.linspace(0,len(audio)-1,round(len(audio)*16000/rate)),np.arange(len(audio)),audio).astype('float32')
        stt=recognition_model(voice_root,'tiny')
        heard,stt=recognize_qa(audio,stt,voice_root,('saldo','cuenta','dinero','balance'))
        result['recognized_synthetic_audio']=heard
        if exe and model:
            from voice_conversation import CallConversation
            from chat_store import ChatStore
            from knowledge import KnowledgeStore
            from akira_model_runtime import shared_runtime
            cfg=load_config(DEFAULT)
            cfg['assistant'].update(local_runtime_enabled=True,local_endpoint='http://127.0.0.1:18994/v1/chat/completions',
                local_runtime_exe=str(Path(exe).resolve()),local_runtime_model=str(Path(model).resolve()),provider_mode='local')
            cfg['desktop'].update(low_resource_mode='ultra',model_use_gpu=False,model_context_tokens=2048)
            runtime=shared_runtime(cfg['assistant'],root);assistant=NS(chats=ChatStore(root),memory=KnowledgeStore(root),_managed_model=runtime)
            assistant.chats.remember('Mi activo favorito es el oro.')
            assistant.chats=ChatStore(root)  # Recover the explicit memory from disk.
            events=[];output={'bytes':0,'first_audio_seconds':None};began=time.monotonic()
            class Output:
                def __init__(self,**kwargs):pass
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def write(self,raw):
                    output['bytes']+=len(raw)
                    if output['first_audio_seconds'] is None:output['first_audio_seconds']=round(time.monotonic()-began,3)
            voice=VoiceSession(root,events.append,{'streaming_call':True},selected)
            real_server=SpeechServer
            with patch.dict(sys.modules,{'sounddevice':NS(RawOutputStream=Output)}),patch('voice_session.SpeechServer',side_effect=lambda:real_server(command=[str(Path(app).resolve())] if app else None)):
                call=CallConversation(assistant,lambda:cfg,lambda:{'connected':True,
                    'account':{'balance':50,'equity':50,'currency':'USD'},
                    'status':{'BTCUSDm':{'state':'SYNTHETIC QA'},'XAUUSDm':{'state':'SYNTHETIC QA'}}},voice)
                turns=[]
                for question,pattern in ((heard,r'50|cincuenta'),('¿Cuál es mi activo favorito?',r'oro|xauusd|gold')):
                    if turns:
                        request.update(path=str(root/'second.wav'),text=question,rate=160)
                        worker.render(request,lambda:False)
                        with wave.open(request['path']) as wav:
                            rate=wav.getframerate();audio=np.frombuffer(wav.readframes(wav.getnframes()),dtype='int16').astype('float32')/32768
                        audio=np.interp(np.linspace(0,len(audio)-1,round(len(audio)*16000/rate)),np.arange(len(audio)),audio).astype('float32')
                        question,stt=recognize_qa(audio,stt,voice_root,('activo','favorito','oro'))
                    before=output['bytes'];began=time.monotonic();output['first_audio_seconds']=None
                    if not call.ask(question):raise AssertionError('La llamada no aceptó el turno')
                    deadline=time.monotonic()+180
                    while time.monotonic()<deadline:
                        if not call.busy and not voice.speaking.is_set() and voice.speech_chunks.empty() and not voice.awaiting.is_set():break
                        time.sleep(.05)
                    errors=[e['text'] for e in events if e.get('kind')=='error']
                    if errors or call.busy or output['bytes']<=before:raise AssertionError('Sin respuesta hablada: '+str(errors))
                    reply=call.history[-1]['content']
                    import re
                    if not re.search(pattern,reply,re.I):raise AssertionError('La respuesta no usó la evidencia disponible: '+reply)
                    if assistant.chats.history():raise AssertionError('El micrófono se escribió en ChatStore')
                    turns.append({'recognized':question,'reply':reply,'first_audio_seconds':output['first_audio_seconds'],
                        'metrics':dict(call.metrics),'audio_bytes':output['bytes']-before})
                result.update(audio_output=output,turns=turns,chat_messages=0,
                    persistent_memory_recovered=True,effective_parameters=runtime.effective_parameters())
                call.close();voice.stop()
        result['status']='PASSED'
    except Exception:result.update(status='FAILED',error=traceback.format_exc())
    finally:
        worker.close()
        if call:call.close()
        if voice:voice.stop()
        if runtime:runtime.shutdown()
        if temporary:
            try:temporary.cleanup()
            except Exception:result.update(status='FAILED',error=traceback.format_exc())
    Path(report).parent.mkdir(parents=True,exist_ok=True);Path(report).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--report',required=True);p.add_argument('--voice-root',required=True)
    p.add_argument('--app');p.add_argument('--exe');p.add_argument('--model');a=p.parse_args()
    result=run(a.report,a.voice_root,a.app,a.exe,a.model);print(json.dumps(result,ensure_ascii=False));raise SystemExit(0 if result['status']=='PASSED' else 1)
