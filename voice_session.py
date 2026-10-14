"""Explicit local voice sessions. Capture, recognition and speech never run in Tk/MT5."""
from pathlib import Path
import hashlib,json,os,queue,re,shutil,subprocess,sys,tempfile,threading,time,uuid,wave

PIPER_CATALOG='https://huggingface.co/rhasspy/piper-voices/resolve/main/voices.json'
PIPER_ROOT='https://huggingface.co/rhasspy/piper-voices/resolve/main/'
_STT_LOCK=threading.Lock();_STT_KEY=None;_STT_MODEL=None

def recognition_model(root,name):
 global _STT_KEY,_STT_MODEL
 key=(str(Path(root).resolve()),name)
 with _STT_LOCK:
  if _STT_KEY!=key or _STT_MODEL is None:
   from faster_whisper import WhisperModel
   model=WhisperModel(name,device='cpu',compute_type='int8',cpu_threads=2,num_workers=1,download_root=str(Path(root)/'state'/'speech_models'))
   _STT_MODEL=model;_STT_KEY=key
  return _STT_MODEL

def audio_inventory():
 import sounddevice as sd
 inputs=[];outputs=[]
 for i,d in enumerate(sd.query_devices()):
  item={'id':i,'name':str(d['name'])}
  if d.get('max_input_channels',0)>0:inputs.append(item)
  if d.get('max_output_channels',0)>0:outputs.append(item)
 return {'inputs':inputs,'outputs':outputs}

def voice_files_available(folder,files,metadata):
 try:
  for relative in files:
   target=folder/Path(relative).name;size=target.stat().st_size
   expected=(metadata.get(relative) or {}).get('size_bytes')
   if size<=0 or expected and size!=int(expected):return False
   if relative.endswith('.onnx.json') and not isinstance(json.loads(target.read_text(encoding='utf-8')),dict):return False
  return any(p.endswith('.onnx') for p in files) and any(p.endswith('.onnx.json') for p in files)
 except (OSError,ValueError,UnicodeError):return False

def voice_inventory(root,include_online=False):
 root=Path(root);folder=root/'state'/'voices';folder.mkdir(parents=True,exist_ok=True);rows=[]
 try:
  import pyttsx3
  engine=pyttsx3.init()
  for v in engine.getProperty('voices'):
   rows.append({'id':'system:'+str(v.id),'name':str(v.name),'engine':'system','installed':True,'language':str(getattr(v,'languages',[])),'gender':str(getattr(v,'gender','') or 'sin especificar')})
  engine.stop()
 except Exception:pass
 catalog=folder/'catalog.json';data={}
 try:data=json.loads(catalog.read_text(encoding='utf-8'))
 except (OSError,ValueError):pass
 if include_online:
  from urllib.request import urlopen
  with urlopen(PIPER_CATALOG,timeout=8) as response:
   raw=response.read(2000001)
   if len(raw)>2000000:raise ValueError('Catálogo de voces demasiado grande')
   data=json.loads(raw)
  tmp=catalog.with_suffix('.tmp');tmp.write_text(json.dumps(data),encoding='utf-8');tmp.replace(catalog)
 for key,v in data.items():
  # Retain only model and configuration paths belonging to the official catalog.
  files=[p for p in v.get('files',{}) if str(p).endswith(('.onnx','.onnx.json')) and '..' not in str(p).split('/') and not str(p).startswith('/')]
  model=next((p for p in files if p.endswith('.onnx')),None)
  if not model:continue
  local=folder/Path(model).name
  speakers=v.get('speaker_id_map') or {'voz':0}
  language=v.get('language') or {};language_name=language.get('name_native') or language.get('name_english') or language.get('code') or 'Sin idioma'
  display_name=language_name+' · '+str(v.get('name') or key.rsplit('-',1)[0])+' · '+{'low':'Básica','x_low':'Compacta','medium':'Media','high':'Alta'}.get(v.get('quality'),'')
  installed=voice_files_available(folder,files,v.get('files') or {})
  for name,speaker in speakers.items():
   rows.append({'id':'piper:'+key+':'+str(speaker),'name':display_name+(' · '+str(name) if len(speakers)>1 else ''),'engine':'piper','installed':installed,
    'language':(v.get('language') or {}).get('code',''),'model':str(local),'files':files,'file_metadata':v.get('files',{}),'speaker':int(speaker),'license_url':PIPER_ROOT+str(Path(model).parent.as_posix())+'/MODEL_CARD','license':'Licencia y características en la ficha del modelo; no se inventan edad o género'})
 return sorted(rows,key=lambda r:(not bool(re.search(r'(?i)(?:^es(?:[_-]|$)|spanish|español)',r.get('language',''))),not r.get('installed'),r.get('engine')!='system',r.get('name','')))

def install_voice(root,row,progress=lambda x:None,cancel=None,byte_progress=None):
 if row.get('engine')!='piper':return
 from urllib.request import urlopen
 folder=Path(root)/'state'/'voices';folder.mkdir(parents=True,exist_ok=True)
 # Validate the complete model/config pair before replacing any installed file.
 with tempfile.TemporaryDirectory(prefix='install_',dir=folder) as staging:
  staging=Path(staging);pending=[];committed=[]
  for relative in row['files']:
   if cancel and cancel.is_set():raise RuntimeError('Descarga cancelada')
   if '..' in relative.split('/') or relative.startswith('/') or not relative.endswith(('.onnx','.onnx.json')):raise ValueError('Ruta de voz inválida')
   target=folder/Path(relative).name;temporary=staging/target.name
   if any(target==p[0] for p in pending):raise ValueError('Archivo de voz repetido')
   progress('Descargando '+target.name)
   digest=hashlib.md5();metadata=(row.get('file_metadata') or {}).get(relative,{})
   last_progress=0.0
   with urlopen(PIPER_ROOT+relative,timeout=12) as response,temporary.open('wb') as stream:
    total=0
    while True:
     if cancel and cancel.is_set():raise RuntimeError('Descarga cancelada')
     chunk=response.read(262144)
     if not chunk:break
     total+=len(chunk)
     if total>180000000:raise ValueError('Modelo de voz supera el tamaño permitido')
     stream.write(chunk)
     digest.update(chunk)
     now=time.monotonic()
     if byte_progress and now-last_progress>=.25:
      byte_progress(target.name,total,int(metadata.get('size_bytes') or 0));last_progress=now
   if not total:raise ValueError('Modelo de voz vacío')
   expected=metadata.get('md5_digest')
   if expected and digest.hexdigest()!=expected:raise ValueError('La descarga no coincide con la integridad publicada del modelo')
   if metadata.get('size_bytes') and total!=int(metadata['size_bytes']):raise ValueError('Descarga incompleta de la voz')
   if relative.endswith('.onnx.json'):
    try:configuration=json.loads(temporary.read_text(encoding='utf-8'))
    except (ValueError,UnicodeError):raise ValueError('Configuración de voz inválida')
    if not isinstance(configuration,dict):raise ValueError('Configuración de voz inválida')
   pending.append((target,temporary))
   if byte_progress:byte_progress(target.name,total,int(metadata.get('size_bytes') or total))
  if cancel and cancel.is_set():raise RuntimeError('Descarga cancelada')
  try:
   for target,temporary in pending:
    backup=staging/(target.name+'.previous')
    if target.exists():target.replace(backup)
    committed.append((target,backup));temporary.replace(target)
  except Exception:
   for target,backup in reversed(committed):
    target.unlink(missing_ok=True)
    if backup.exists():backup.replace(target)
   raise

def unique_voice_models(rows):
 """Several speakers can use the same model; download that pair only once."""
 models={}
 for row in rows:
  if row.get('engine')!='piper':continue
  files=tuple(sorted(set(row.get('files') or [])))
  if not any(p.endswith('.onnx') for p in files) or not any(p.endswith('.onnx.json') for p in files):continue
  models.setdefault(files,dict(row))
 return list(models.values())

def voice_pair_valid(root,row,cancel=None):
 folder=Path(root)/'state/voices'
 try:
  for relative in row['files']:
   target=folder/Path(relative).name;metadata=(row.get('file_metadata') or {}).get(relative,{})
   size=target.stat().st_size
   if size<=0 or metadata.get('size_bytes') and size!=int(metadata['size_bytes']):return False
   if relative.endswith('.onnx.json'):
    if not isinstance(json.loads(target.read_text(encoding='utf-8')),dict):return False
   expected=metadata.get('md5_digest')
   if expected:
    digest=hashlib.md5()
    with target.open('rb') as stream:
     while True:
      if cancel and cancel.is_set():return False
      chunk=stream.read(262144)
      if not chunk:break
      digest.update(chunk)
    if digest.hexdigest()!=expected:return False
  return True
 except (OSError,ValueError,UnicodeError,KeyError):return False

def install_all_voices(root,rows,emit=lambda event:None,cancel=None):
 """Bounded, sequential I/O. Failures do not erase complete installed pairs."""
 root=Path(root);folder=root/'state/voices';folder.mkdir(parents=True,exist_ok=True)
 models=unique_voice_models(rows)
 sizes=[sum(int((r.get('file_metadata') or {}).get(p,{}).get('size_bytes') or 0) for p in r['files']) for r in models]
 state={'state':'downloading','models_total':len(models),'models_done':0,'downloaded':0,
  'skipped':0,'failed':0,'errors':[],'bytes_total':sum(sizes),'bytes_done':0,
  'voices_total':sum(1 for r in rows if r.get('engine')=='piper'),'current':'','file_bytes':0,'file_total':0}
 emit(dict(state))
 for index,row in enumerate(models):
  if cancel and cancel.is_set():state['state']='cancelled';break
  state.update(current=row['name'],file_bytes=0,file_total=0);emit(dict(state))
  if voice_pair_valid(root,row,cancel):
   state['skipped']+=1
  else:
   try:
    if cancel and cancel.is_set():state['state']='cancelled';break
    required=max(sizes[index],180000000 if not sizes[index] else 0)+536870912
    if shutil.disk_usage(folder).free<required:raise OSError('Espacio insuficiente para el siguiente modelo de voz')
    def bytes_event(filename,done,total):
     state.update(current=row['name']+' · '+filename,file_bytes=done,file_total=total);emit(dict(state))
    install_voice(root,row,cancel=cancel,byte_progress=bytes_event)
    state['downloaded']+=1
   except Exception as exc:
    if cancel and cancel.is_set():state['state']='cancelled';break
    state['failed']+=1;state['errors'].append({'voice':row['name'],'error':str(exc)[:200]})
    if isinstance(exc,OSError) and 'Espacio insuficiente' in str(exc):state['state']='disk_full';emit(dict(state));break
  state['models_done']+=1;state['bytes_done']+=sizes[index];emit(dict(state))
 if state['state']=='downloading':state['state']='partial' if state['failed'] else 'complete'
 if not models:state['state']='empty'
 emit(dict(state));return state

class VoiceDownloadBatch:
 """One job per window owner; cancellation is separate from ending a call."""
 def __init__(self,root,emit,application_stop=None):
  self.root=Path(root);self.emit=emit;self.application_stop=application_stop
  self.cancel_event=threading.Event();self.job_id=uuid.uuid4().hex;self.thread=None;self.active=False
 def is_set(self):return self.cancel_event.is_set() or bool(self.application_stop and self.application_stop.is_set())
 def cancel(self):self.cancel_event.set()
 def start(self):
  if self.thread is not None:return False
  self.active=True
  self.thread=threading.Thread(target=self._run,name='AkiraAllVoices',daemon=True)
  self.thread.start();return True
 def _emit(self,state):self.emit({'job_id':self.job_id,**state})
 def _run(self):
  try:
   if self.is_set():self._emit({'state':'cancelled','finished':True});return
   self._emit({'state':'catalog','current':'Consultando el catálogo de voces…'})
   try:rows=voice_inventory(self.root,include_online=True)
   except Exception:
    rows=voice_inventory(self.root,include_online=False)
    if not unique_voice_models(rows):raise RuntimeError('No se pudo obtener el catálogo. Reintenta con conexión a Internet.')
   result=install_all_voices(self.root,rows,self._emit,self)
   self._emit({**result,'finished':True,'rows':rows})
  except Exception as exc:self._emit({'state':'error','finished':True,'error':str(exc)[:240]})
  finally:self.active=False

def clean_speech(text):
 text=re.sub(r'\[([^\]]+)\]\(https?://[^)]+\)',r'\1',str(text))
 return re.sub(r'https?://\S+','fuente consultada',text).replace('★','').replace('☆','')[:4000]

def speech_worker(request_path):
 data=json.loads(Path(request_path).read_text(encoding='utf-8'));voice=data['voice'];path=data['path'];text=clean_speech(data['text'])
 if voice['engine']=='piper':
  from piper import PiperVoice,SynthesisConfig
  model=PiperVoice.load(voice['model'])
  config=SynthesisConfig(speaker_id=voice.get('speaker',0),length_scale=180/max(80,min(300,int(data.get('rate',180)))),volume=max(0,min(1,float(data.get('volume',.8)))))
  with wave.open(path,'wb') as wav:model.synthesize_wav(text,wav,syn_config=config)
 else:
  import pyttsx3
  engine=pyttsx3.init();engine.setProperty('voice',voice['id'].removeprefix('system:'));engine.setProperty('rate',int(data.get('rate',180)));engine.setProperty('volume',float(data.get('volume',.8)))
  engine.save_to_file(text,path);engine.runAndWait();engine.stop()

class VoiceSession:
 def __init__(self,root,emit,options,voice):
  self.root=Path(root);self.emit=emit;self.options=dict(options);self.voice=dict(voice)
  self.session_id=uuid.uuid4().hex
  self.stop_event=threading.Event();self.paused=threading.Event();self.awaiting=threading.Event();self.speaking=threading.Event();self.interrupt_event=threading.Event()
  self.audio=queue.Queue(maxsize=120);self.started=False;self.stream=None;self.process=None
  self.last_text='';self.samples=[];self._threads=[];self._revision=0
 def event(self,kind,**data):self.emit({'kind':kind,'session_id':self.session_id,**data})
 def start(self):
  if self.started:return
  self.started=True;self.event('state',text='Preparando reconocimiento. El modelo se instala una vez; todavía no grabo.')
  thread=threading.Thread(target=self._run,name='AkiraVoice',daemon=True);self._threads.append(thread);thread.start()
 def pause(self):
  self.paused.set();self._revision+=1;self._drain();self.event('state',text='Micrófono silenciado · puedes reanudar o finalizar')
 def resume(self):
  self._revision+=1;self.paused.clear();self.awaiting.clear();self._drain();self.event('state',text='Reanudando micrófono…')
 def cancel_message(self):
  self._revision+=1;self._drain();self.awaiting.clear();self.last_text='';self.event('partial',text='');self.event('state',text='Mensaje cancelado · Escuchando')
 def submit_message(self):
  self.awaiting.set();self._revision+=1;self._drain();self.event('state',text='Procesando tu mensaje')
 def _drain(self):
  while True:
   try:self.audio.get_nowait()
   except queue.Empty:break
  self.samples=[]
 def stop(self):
  self.stop_event.set();self.interrupt();self._drain()
  if self.stream:
   try:self.stream.abort()
   except Exception:pass
  self.event('state',text='Llamada finalizada · Micrófono desactivado')
 def interrupt(self):
  self.interrupt_event.set()
  if self.process and self.process.poll() is None:
   try:self.process.terminate()
   except OSError:pass
  self.awaiting.clear()
 def _run(self):
  try:
   import numpy as np,sounddevice as sd
   model_name=str(self.options.get('model','tiny'))
   if model_name not in ('tiny','base','small'):model_name='tiny'
   model=recognition_model(self.root,model_name)
   if self.stop_event.is_set():return
   device=self.options.get('input_device');device=None if device in (None,-1,'') else int(device)
   inventory=audio_inventory()
   if device is not None and device not in [d['id'] for d in inventory['inputs']]:raise RuntimeError('El micrófono seleccionado se desconectó')
   if not inventory['inputs']:raise RuntimeError('No hay micrófonos disponibles. Revisa los permisos de Windows para AKIRA.')
   reader=threading.Thread(target=self._capture,args=(sd,device),name='AkiraMicrophone',daemon=True);self._threads.append(reader);reader.start()
   active=[];silence=0;partial_due=0;epoch=self._revision
   while not self.stop_event.is_set():
    try:chunk=self.audio.get(timeout=.25)
    except queue.Empty:continue
    if epoch!=self._revision:active=[];silence=0;epoch=self._revision
    if self.paused.is_set() or self.awaiting.is_set() or self.speaking.is_set():active=[];silence=0;continue
    power=float(np.sqrt(np.mean(chunk*chunk)));voiced=power>=.008
    if not active and not voiced:continue
    active.append(chunk);silence=0 if voiced else silence+1
    now=time.monotonic()
    final=(silence>=8 and len(active)>=5) or len(active)>=150
    if not final and (len(active)<10 or now<partial_due):continue
    self.event('state',text='Transcribiendo' if final else 'Escuchando · transcripción en directo')
    revision=self._revision;audio=np.concatenate(active[-150:]);segments,_=model.transcribe(audio,language=self.options.get('language','es'),beam_size=1,vad_filter=True,condition_on_previous_text=False)
    text=' '.join(s.text.strip() for s in segments).strip()[:1500];partial_due=time.monotonic()+2
    if self.stop_event.is_set():break
    if self.paused.is_set() or revision!=self._revision:active=[];silence=0;continue
    if text:self.last_text=text;self.event('partial',text=text)
    if final:
     active=[];silence=0
     if text:
      self.awaiting.set();self.event('final',text=text);self.event('state',text='Procesando tu mensaje')
     else:self.event('state',text='No reconocí palabras · Escuchando')
  except Exception as exc:
   if not self.stop_event.is_set():self.event('error',text='Voz: '+str(exc)[:400]);self.stop_event.set()
  finally:
   self.started=False
   if self.stream:
    try:self.stream.close()
    except Exception:pass
   self.stream=None
 def _capture(self,sd,device):
  stream=None
  try:
   import numpy as np
   rate=16000
   try:sd.check_input_settings(device=device,channels=1,dtype='float32',samplerate=rate)
   except Exception:rate=int(sd.query_devices(device,'input')['default_samplerate'])
   count=max(1,int(rate*.1));stream=sd.InputStream(device=device,samplerate=rate,channels=1,dtype='float32',blocksize=count)
   self.stream=stream;running=False
   while not self.stop_event.is_set():
    muted=self.paused.is_set() or self.awaiting.is_set() or self.speaking.is_set()
    if muted:
     if running:stream.stop();running=False
     self.stop_event.wait(.05);continue
    if not running:
     stream.start();running=True;self.event('state',text='Micrófono activo · Escuchando')
    data,overflow=stream.read(count)
    if overflow:self.event('state',text='Audio saturado · revisa el dispositivo')
    if self.paused.is_set() or self.awaiting.is_set() or self.speaking.is_set():continue
    chunk=data[:,0].copy()
    if rate!=16000:chunk=np.interp(np.linspace(0,len(chunk)-1,1600),np.arange(len(chunk)),chunk).astype('float32')
    try:self.audio.put_nowait(chunk)
    except queue.Full:self._revision+=1;self._drain();self.event('state',text='Recuperando audio; habla en frases más cortas')
  except Exception as exc:
   if not self.stop_event.is_set():self.event('error',text='Micrófono: '+str(exc)[:300]);self.stop_event.set()
  finally:
   if stream:
    try:stream.close()
    except Exception:pass
   self.stream=None
 def speak(self,text):
  if self.stop_event.is_set() or self.speaking.is_set():return
  self.interrupt_event.clear();self.speaking.set()
  def work():
   try:
    self.event('state',text='AKIRA responde · puedes interrumpir')
    import numpy as np,sounddevice as sd
    with tempfile.TemporaryDirectory(prefix='akira_voice_') as tmp:
     folder=Path(tmp);path=folder/'answer.wav';request=folder/'request.json'
     request.write_text(json.dumps({'voice':self.voice,'path':str(path),'text':clean_speech(text),'rate':self.options.get('rate',180),'volume':self.options.get('volume',.8)}),encoding='utf-8')
     args=[sys.executable,'--speech-worker',str(request)] if getattr(sys,'frozen',False) else [sys.executable,str(Path(__file__).with_name('Akira.py')),'--speech-worker',str(request)]
     self.process=subprocess.Popen(args,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
     deadline=time.monotonic()+35
     while self.process.poll() is None:
      if self.stop_event.is_set() or self.interrupt_event.is_set() or time.monotonic()>deadline:
       self.process.terminate();self.process.wait(timeout=3)
       if time.monotonic()>deadline:raise RuntimeError('La voz tardó demasiado. Selecciona otra voz e intenta la demostración.')
       return
      self.stop_event.wait(.05)
     if self.process.returncode or not path.is_file():raise RuntimeError('El motor de voz no pudo generar audio. Comprueba la instalación de esa voz.')
     with wave.open(str(path),'rb') as wav:
      width=wav.getsampwidth();rate=wav.getframerate();channels=wav.getnchannels();device=self.options.get('output_device')
      if width not in (2,4):raise RuntimeError('Formato de audio no compatible')
      dtype='int16' if width==2 else 'int32';device=None if device in (None,-1,'') else int(device)
      with sd.RawOutputStream(samplerate=rate,channels=channels,dtype=dtype,device=device) as output:
       while not (self.stop_event.is_set() or self.interrupt_event.is_set()):
        raw=wav.readframes(max(1,int(rate*.1)))
        if not raw:break
        output.write(raw)
   except Exception as exc:self.event('error',text=str(exc)[:400])
   finally:
    self.process=None;self.speaking.clear();self.awaiting.clear();self._drain()
    if not self.stop_event.is_set():self.event('state',text=('Micrófono silenciado' if self.paused.is_set() else 'Reanudando escucha') if self.started else 'Demostración terminada · micrófono desactivado')
  self._threads=[t for t in self._threads if t.is_alive()]
  thread=threading.Thread(target=work,name='AkiraSpeech',daemon=True);self._threads.append(thread);thread.start()
