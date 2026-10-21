"""AKIRA Studio: user assets, languages and safe cosmetic preferences.

This module does not import or control MT5. Invalid assets cannot change trading.
"""
from __future__ import annotations
import copy, json, os, re, shutil, hashlib, threading, subprocess, math, time
from pathlib import Path
from dataclasses import dataclass
from collections import OrderedDict

STATES=('idle','blink','listening','talking','thinking','analyzing','happy','alert','sleeping','loading','connecting','waking','bullish','bearish','caring','surprised')
ALIASES={
 'idle':('idle','normal','reposo','quieto','neutral','base'),
 'blink':('blink','parpadeo','eyesclosed','ojoscerrados'),
 'listening':('listen','escucha','mic','hearing'),
 'talking':('talk','speak','habla','boca','speaking'),
 'thinking':('think','pensando','pensar','duda'),
 'analyzing':('analy','analiz','focus','concentr'),
 'happy':('happy','feliz','alegr','smile','sonrie'),
 'alert':('alert','warning','error','sorpresa','enoj','angry'),
 'sleeping':('sleep','dormido','sueno','zzz'),
 'loading':('load','cargan','esperando','spinner','wait'),
 'connecting':('connect','conectan'),
 'waking':('wake','despert'),
 'bullish':('bull','alcista'),
 'bearish':('bear','bajista'),
 'caring':('care','amor','ternura','empat'),
 'surprised':('surprise','asombr'),
}
LOCALES=('es','en','pt','fr','de','it','ja','zh','ko','ar')
UI_LABELS={
 'es':('TRADING','PENDIENTES','CUENTA','ANÁLISIS','FUENTES','CHAT','AJUSTES','TERMINAL'),
 'en':('TRADING','PENDING','ACCOUNT','ANALYSIS','SOURCES','CHAT','SETTINGS','TERMINAL'),
 'pt':('NEGOCIAÇÃO','PENDENTES','CONTA','ANÁLISE','FONTES','CHAT','AJUSTES','TERMINAL'),
 'fr':('TRADING','ORDRES','COMPTE','ANALYSE','SOURCES','CHAT','RÉGLAGES','TERMINAL'),
 'de':('HANDEL','ORDERS','KONTO','ANALYSE','QUELLEN','CHAT','EINSTELLUNGEN','TERMINAL'),
 'it':('TRADING','ORDINI','CONTO','ANALISI','FONTI','CHAT','IMPOSTAZIONI','TERMINALE'),
 'ja':('取引','指値注文','口座','分析','情報源','チャット','設定','端末'),
 'zh':('交易','挂单','账户','分析','来源','聊天','设置','终端'),
 'ko':('거래','예약 주문','계정','분석','자료','채팅','설정','터미널'),
 'ar':('التداول','الأوامر','الحساب','التحليل','المصادر','الدردشة','الإعدادات','الطرفية')
}
DEFAULT={
 'brand_name':'AKIRA','language_ui':'es','language_chat':'auto','language_voice_in':'auto','language_voice_out':'es',
 'translate_input':False,'translate_output':False,'language_pack':'',
 'theme':'AKIRA Original','accent':'#00ddff','secondary':'#ff2585','font':'Rajdhani','font_scale':100,'font_bold':False,'theme_profiles':{},'theme_profile_name':'',
 'glow':65,'panel_texture':'Neon grid','reduce_motion':False,'background_color':'',
 'wallpaper':{'kind':'default','file':'','fit':'cover','rotation':0,'offset_x':0,'offset_y':0,'opacity':65,'fps':30,'quality':70,'max_memory_mb':128,'max_cpu_percent':10,'crop_left':0,'crop_right':0,'crop_top':0,'crop_bottom':0,'enabled':False,'loop':True,'vsync':True,'zoom':100},
 'avatar':{'active':False,'entries':[],'sequences':{},'profile':'default','animate':True,'repeat':True}
}

def read_language_pack(path):
    """Validate an inert JSON translation dictionary; never evaluate its text."""
    source=Path(str(path)) if path else None
    if not source or not source.is_file() or source.stat().st_size>256*1024:return {}
    try:doc=json.loads(source.read_text(encoding='utf-8'))
    except (OSError,UnicodeError,ValueError):return {}
    if not isinstance(doc,dict):return {}
    locale=str(doc.get('locale',''))
    if not re.fullmatch(r'[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]{2,8})*',locale):return {}
    source_rows=doc.get('translations')
    if not isinstance(source_rows,dict) or len(source_rows)>2500:return {}
    result={}
    for k,v in source_rows.items():
        if not isinstance(k,str) or not isinstance(v,str) or not (1<=len(k)<=400 and 1<=len(v)<=650):return {}
        if any(ord(ch)<32 and ch not in '\n\t' for ch in k+v):return {}
        result[k]=v
    return {'locale':locale,'translations':result}

def import_language_pack(folder,source):
    source=Path(source);doc=read_language_pack(source)
    if not doc:raise ValueError('Paquete de idioma inválido: JSON con locale y translations requerido.')
    dest=asset_root(folder)/'languages';dest.mkdir(parents=True,exist_ok=True)
    content=json.dumps(doc,ensure_ascii=False,sort_keys=True).encode('utf-8')
    target=dest/(hashlib.sha256(content).hexdigest()[:16]+'.json')
    if not target.exists():target.write_bytes(content)
    return str(target),doc['locale']

def apply_language_pack(root,language_pack,locale):
    """Translate static native widgets and headings once after UI creation.

    Dynamic market messages are intentionally not guessed by a dictionary.
    """
    pack=read_language_pack(language_pack)
    if not pack or pack['locale']!=locale:return 0
    translations=pack['translations'];counter=0
    def visit(parent):
        nonlocal counter
        for widget in parent.winfo_children():
            try:
                if 'text' in widget.keys():
                    caption=str(widget.cget('text'))
                    if caption in translations:
                        widget.configure(text=translations[caption]);counter+=1
                if widget.winfo_class()=='TNotebook':
                    for tab in widget.tabs():
                        caption=widget.tab(tab,'text')
                        if caption in translations:
                            widget.tab(tab,text=translations[caption]);counter+=1
            except Exception:pass
            visit(widget)
    visit(root)
    return counter

def normalize_name(value):
    value=' '.join(str(value).strip().split())
    if not 1 <= len(value) <= 40 or any(ord(x)<32 or x in '<>\\/\"|:*?' for x in value):
        raise ValueError('El nombre debe tener 1–40 caracteres y no incluir caracteres de rutas.')
    return value

def safe_studio(cfg):
    result=copy.deepcopy(DEFAULT)
    src=cfg.get('studio') or {}
    if not isinstance(src,dict):return result
    for k,v in src.items():
        if k=='wallpaper' and isinstance(v,dict):result[k].update({a:b for a,b in v.items() if a in result[k]})
        elif k=='avatar' and isinstance(v,dict):result[k].update({a:b for a,b in v.items() if a in result[k]})
        elif k in result:result[k]=v
    return result

def validate_studio(value):
    c=copy.deepcopy(value)
    c['brand_name']=normalize_name(c['brand_name'])
    # A user language pack can extend the built-in navigation locales.
    if c['language_ui'] not in LOCALES:
        translations=read_language_pack(c.get('language_pack',''))
        if translations.get('locale')!=c['language_ui'] and not re.fullmatch(r'[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]{2,8})*',str(c['language_ui'])):
            raise ValueError('Selecciona un código de idioma válido o importa su paquete JSON.')
    for key in ('language_chat','language_voice_in','language_voice_out'):
        if c[key]!='auto' and not re.fullmatch(r'[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]{2,8})*',str(c[key])):raise ValueError('Código de idioma inválido: '+key)

    for k in ('accent','secondary'):
        if not re.fullmatch(r'#[0-9a-fA-F]{6}',str(c[k])):raise ValueError('Color hexadecimal inválido: '+k)
    if c.get('background_color') and not re.fullmatch(r'#[0-9a-fA-F]{6}',str(c['background_color'])):raise ValueError('Color de fondo inválido')
    if not 60<=int(c['font_scale'])<=160:raise ValueError('Escala de fuente fuera de 60–160%')
    if not 0<=int(c['glow'])<=100:raise ValueError('Brillo fuera de rango')
    w=c['wallpaper']
    if w['kind'] not in ('default','image','video','gif'):raise ValueError('Tipo de fondo inválido')
    if w['fit'] not in ('cover','contain','stretch'):raise ValueError('Ajuste de fondo inválido')
    for k,low,high in (('fps',1,144),('quality',20,100),('max_memory_mb',32,512),('max_cpu_percent',1,40),('opacity',0,100)):
        if not low<=int(w[k])<=high:raise ValueError('Parámetro de fondo fuera de rango: '+k)
    if not math.isfinite(float(w['rotation'])) or not -360<=float(w['rotation'])<=360:raise ValueError('Rotación fuera de rango')
    if not 50<=float(w.get('zoom',100))<=200:raise ValueError('Zoom fuera de 50–200%')
    for key in ('enabled','loop','vsync'):
        if type(w.get(key)) is not bool:raise ValueError('Selecciona una casilla válida: '+key)
    if not isinstance(c.get('theme_profiles'),dict) or len(c['theme_profiles'])>40:raise ValueError('Máximo 40 temas personalizados')
    for key in ('offset_x','offset_y'):
        if not -100<=int(w.get(key,0))<=100:raise ValueError('Desplazamiento fuera de -100 a 100')
    for key in ('crop_left','crop_right','crop_top','crop_bottom'):
        if not 0<=int(w.get(key,0))<=45:raise ValueError('Recorte fuera de 0–45%: '+key)
    if w['enabled'] and w['kind']!='default' and not (w['file'] and Path(w['file']).is_file()):
        raise ValueError('El archivo del fondo elegido no está disponible')
    return c

def asset_root(folder):
    path=Path(folder)/'studio'
    path.mkdir(parents=True,exist_ok=True)
    return path

def import_media(folder,source,kind):
    source=Path(source)
    if not source.is_file():raise ValueError('No existe el archivo seleccionado')
    suffix=source.suffix.casefold()
    valid=('.png','.jpg','.jpeg','.webp','.gif') if kind in ('image','gif') else ('.mp4','.webm','.mov','.mkv')
    if suffix not in valid:raise ValueError('Formato de archivo no permitido')
    if source.stat().st_size>300*1024*1024:raise ValueError('El archivo supera el límite de 300 MB')
    if kind in ('image','gif'):
        from PIL import Image
        with Image.open(source) as im:
            if im.width*im.height>45_000_000:raise ValueError('Imagen demasiado grande')
            im.verify()
    dest=asset_root(folder)/'wallpapers';dest.mkdir(exist_ok=True)
    hashing=hashlib.sha256()
    with source.open('rb') as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b''):
            hashing.update(chunk)
    sha=hashing.hexdigest()[:16]
    target=dest/(sha+suffix)
    if not target.exists():shutil.copy2(source,target)
    return str(target)

def detect_expression(filename):
    stem=Path(filename).stem.casefold().replace('-','_')
    scores={state:sum(1 for token in tokens if token in stem) for state,tokens in ALIASES.items()}
    chosen=max(scores,key=scores.get)
    return (chosen,'nombre del archivo',0.95) if scores[chosen] else ('idle','sin etiqueta reconocible: revisable',0.0)

def _opaque_spans(alpha,axis):
    """Find fully transparent gutters with Pillow's native pixel projection."""
    if not alpha.getbbox():return []
    mask=alpha.point(lambda value:255 if value>8 else 0)
    xs,ys=mask.getprojection()
    occupied=xs if axis=='x' else ys
    spans=[];begin=None
    for i,v in enumerate(tuple(occupied)+(0,)):
        if v and begin is None:begin=i
        elif not v and begin is not None:
            spans.append((begin,i));begin=None
    if len(spans)<2:return []
    widths=[right-left for left,right in spans]
    if min(widths)<24 or max(widths)>min(widths)*1.2:return []
    return spans


def split_sprites(image,rows=0,columns=0):
    """Split a transparent sheet with detectable gutters or a requested grid.

    Never silently split a normal portrait just because it has empty borders.
    If a grid is ambiguous, the user can supply rows and columns explicitly.
    """
    from PIL import Image
    rows=int(rows or 0);columns=int(columns or 0)
    if rows<0 or columns<0 or rows*columns>96:raise ValueError('Hoja: máximo 96 fotogramas')
    im=image.convert('RGBA')
    if rows and columns:
        if im.width//columns<16 or im.height//rows<16:raise ValueError('Casillas demasiado pequeñas')
        return [im.crop((im.width*x//columns,im.height*y//rows,
                         im.width*(x+1)//columns,im.height*(y+1)//rows))
                for y in range(rows) for x in range(columns)]
    if rows or columns:raise ValueError('Indica tanto filas como columnas')
    if im.getextrema()[3][0]>8:return [im]
    alpha=im.getchannel('A');xs=_opaque_spans(alpha,'x');ys=_opaque_spans(alpha,'y')
    if not xs and not ys:return [im]
    if not xs:xs=[(0,im.width)]
    if not ys:ys=[(0,im.height)]
    if len(xs)*len(ys)>96:return [im]
    frames=[im.crop((x1,y1,x2,y2)) for y1,y2 in ys for x1,x2 in xs]
    # Stripes where only some cells are occupied are not a regular sheet.
    if any(frame.getchannel('A').getbbox() is None for frame in frames):return [im]
    return frames


def _frame_visual_classification(previous,current):
    """Conservative frame-to-frame motion hint; not semantic image recognition.

    Upper-face changes suggest blink; lower-face changes suggest speech. Avoid
    making up emotions when samples are too dissimilar or lack clear movement.
    """
    from PIL import Image,ImageChops,ImageStat
    size=(48,64)
    def sample(image):
        canvas=Image.new('RGBA',size,(6,16,34,255));p=image.convert('RGBA')
        p.thumbnail(size,Image.Resampling.BILINEAR)
        canvas.alpha_composite(p,((size[0]-p.width)//2,(size[1]-p.height)//2))
        return canvas.convert('RGB')
    a,b=sample(previous),sample(current)
    diff=ImageChops.difference(a,b).convert('L')
    def mean(box):return ImageStat.Stat(diff.crop(box)).mean[0]
    upper=mean((0,5,48,30));lower=mean((0,35,48,60))
    total=mean((0,0,48,64))
    if total<.75 or total>38:return None
    if upper>5 and upper>lower*2.8:return ('blink',.55)
    if lower>5 and lower>upper*2.8:return ('talking',.55)
    return None


def import_sprites(folder,paths,current=None,rows=0,columns=0):
    """Import images, animated GIFs/WebPs and sprite sheets as ordered frames.

    User supplied source files are never executed. The saved PNGs are canonical
    and all frames are bounded to avoid exhausting memory or the Tk thread.
    """
    from PIL import Image
    current=list(current or [])
    dest=asset_root(folder)/'avatars';dest.mkdir(exist_ok=True)
    for path in paths:
        src=Path(path)
        if src.suffix.casefold() not in ('.png','.webp','.jpg','.jpeg','.gif'):continue
        if not src.is_file() or src.stat().st_size>20*1024*1024:continue
        with Image.open(src) as im:
            if not (16<=im.width<=8192 and 16<=im.height<=8192):continue
            if im.width*im.height>30_000_000:continue
            count=min(96,int(getattr(im,'n_frames',1)))
            frames=[];durations=[]
            if count>1:
                for i in range(count):
                    im.seek(i);frames.append(im.convert('RGBA'))
                    durations.append(max(80,min(2000,int(im.info.get('duration') or 180))))
            else:
                frames=split_sprites(im,rows=rows,columns=columns)
                durations=[180]*len(frames)
        file_state,source,confidence=detect_expression(src.name)
        original=frames[0]
        sha=hashlib.sha256(src.read_bytes()+src.name.encode('utf-8')).hexdigest()[:16]
        for frame_i,image in enumerate(frames):
            image.thumbnail((2048,2048),Image.Resampling.LANCZOS)
            digest=hashlib.sha256(f'{sha}:{frame_i}'.encode()).hexdigest()[:16]
            output=dest/(digest+'.png')
            if not output.exists():image.save(output,optimize=True)
            state=file_state;basis=source;certainty=confidence
            if file_state=='idle' and confidence==0 and frame_i:
                evidence=_frame_visual_classification(original,image)
                if evidence:state,certainty=evidence;basis='pistas de movimiento visual (revisar)'
            row={'id':digest,'path':str(output),'source_name':src.name+(f' · {frame_i+1}/{len(frames)}' if len(frames)>1 else ''),
                'state':state,'detected_by':basis,'confidence':certainty,'order':len(current),
                'source_group':sha,'frame_index':frame_i,'duration_ms':durations[frame_i]}
            if not any(r['id']==digest for r in current):current.append(row)
    return current

def suggested_sequences(entries,existing=None):
    """Build sequences for unambiguous imported animation groups only."""
    result=copy.deepcopy(existing or {})
    groups={}
    for row in ordered_entries(entries):
        if row.get('source_group') and row.get('frame_index') is not None:
            groups.setdefault(row['source_group'],[]).append(row)
    for group in groups.values():
        if len(group)<2:continue
        if len({r.get('state') for r in group})!=1:continue
        state=group[0]['state']
        # Never replace a sequence the user already edited.
        if state in result:continue
        frames=sorted(group,key=lambda r:r['frame_index'])
        delay=round(sum(int(r.get('duration_ms',180)) for r in frames)/len(frames))
        result[state]={'frames':[r['id'] for r in frames],
            'delay_ms':max(33,min(2000,delay)),'durations_ms':[max(33,min(2000,int(r.get('duration_ms',180)))) for r in frames],'loop':True,'auto_created':True}
    return result

def ordered_entries(entries):
    return sorted(entries,key=lambda d:int(d.get('order',0)))

class UserCatalog:
    """Same image/choose interface as bundled catalog; automatic fallback to original."""
    def __init__(self,base,config):
        from dataclasses import dataclass
        self.base=base
        @dataclass(frozen=True)
        class Item:
            id:str
            path:str
            state:str
        rows=config.get('entries',[]);rows=rows if isinstance(rows,list) else []
        rows=[r for r in rows if isinstance(r,dict) and all(isinstance(r.get(k),str) and r[k] for k in ('id','path','state')) and r['state'] in STATES and isinstance(r.get('order',0),(int,float))]
        self.entries=[Item(r['id'],r['path'],r['state']) for r in ordered_entries(rows) if Path(r['path']).is_file()]
        self.by_id={r.id:r for r in self.entries}
        self.animate=bool(config.get('animate',True));self.sequences=config.get('sequences',{});self.sequences=self.sequences if isinstance(self.sequences,dict) else {}
    def choose(self,state,sequence=0,context=''):
        if state in ('AKIRA_046','AKIRA_047'):state='talking'
        if state in self.by_id:return self.by_id[state]
        candidates=[r for r in self.entries if r.state==state]
        if not candidates:candidates=[r for r in self.entries if r.state=='idle']
        if candidates:
            ids=(self.sequences.get(state) or {}).get('frames') or []
            if self.animate and ids and ids[0] in self.by_id:return self.by_id[ids[0]]
            return candidates[int(sequence)%len(candidates)]
        return self.base.choose(state,sequence,context)
    def next_in_sequence(self,state,now,current):
        sequence=self.sequences.get(state)
        if not self.animate or not isinstance(sequence,dict):return None
        frames=[self.by_id[i] for i in sequence.get('frames',[]) if i in self.by_id]
        if len(frames)<2:return None
        if now<getattr(self,'_animation_next',0) and state==getattr(self,'_animation_state',None):return None
        first=state!=getattr(self,'_animation_state',None)
        try:index=frames.index(current)+(0 if first else 1)
        except ValueError:index=0
        if index>=len(frames):index=0 if sequence.get('loop',True) else len(frames)-1
        delays=sequence.get('durations_ms') or []
        value=delays[index] if isinstance(delays,list) and index<len(delays) else sequence.get('delay_ms',180)
        try:delay=max(.033,min(2,float(value)/1000))
        except (ValueError,TypeError):delay=.18
        self._animation_next=now+delay;self._animation_state=state
        return frames[index]

    def image(self,item,width,height):
        if not hasattr(item,'path'):return self.base.image(item,width,height)
        from PIL import Image
        with Image.open(item.path) as src:
            im=src.convert('RGBA');im.thumbnail((max(1,width),max(1,height)),Image.Resampling.LANCZOS)
        canvas=Image.new('RGBA',(max(1,width),max(1,height)))
        canvas.alpha_composite(im,((canvas.width-im.width)//2,(canvas.height-im.height)//2))
        return canvas

def transform_wallpaper(im,size,config):
    """Pure PIL transform; restrict decode/resolution for bounded UI work."""
    from PIL import Image,ImageEnhance
    out=im.convert('RGBA');out=out.rotate(-int(config['rotation']),expand=True)
    target=(max(1,int(size[0])),max(1,int(size[1])))
    fit=config.get('fit','cover')
    if fit=='stretch':out=out.resize(target,Image.Resampling.LANCZOS)
    else:
        ratio=(max if fit=='cover' else min)(target[0]/out.width,target[1]/out.height)
        dims=(max(1,round(out.width*ratio)),max(1,round(out.height*ratio)))
        out=out.resize(dims,Image.Resampling.LANCZOS)
        if fit=='cover':
            fx=(max(-100,min(100,int(config.get('offset_x',0))))+100)/200
            fy=(max(-100,min(100,int(config.get('offset_y',0))))+100)/200
            x=max(0,round((out.width-target[0])*fx))
            y=max(0,round((out.height-target[1])*fy))
            out=out.crop((x,y,x+target[0],y+target[1]))
        else:
            canvas=Image.new('RGBA',target,(6,16,34,255));canvas.alpha_composite(out,((target[0]-dims[0])//2,(target[1]-dims[1])//2));out=canvas
    opacity=max(0,min(100,int(config.get('opacity',100))))/100
    if opacity<1:
        overlay=Image.new('RGBA',out.size,(6,16,34,255))
        out=Image.blend(overlay,out,opacity)
    return out

class WallpaperPreview:
    """Video decoder off the Tk/UI thread with bounded latest-frame queue.

    The preview never requests MT5, never blocks trade execution and stops when
    hidden. These are soft rendering budgets, not OS-wide GPU/CPU caps.
    """
    def __init__(self,tk_canvas,config):
        import queue
        self.canvas=tk_canvas;self.config=copy.deepcopy(config);self.job=None;self.photo=None
        self.frames=queue.Queue(maxsize=2);self.cancel=threading.Event()
        self.last_image=None;self.running=False
    def stop(self):
        self.cancel.set();self.running=False
        if self.job:
            try:self.canvas.after_cancel(self.job)
            except Exception:pass
        self.job=None
    def _read_frames(self,path):
        try:
            import imageio.v2 as iio
            from PIL import Image
            quality=max(20,min(100,int(self.config.get('quality',70))))
            width=max(160,round(480*quality/100)//2*2)
            height=max(90,round(270*quality/100)//2*2)
            effective=min(max(1,int(self.config.get('fps',12))),
                max(1,2*int(self.config.get('max_cpu_percent',10))))
            with iio.get_reader(str(path),format='ffmpeg',size=(width,height)) as reader:
                while not self.cancel.is_set():
                    # Never backlog frames: stale frames are worthless in UI.
                    for raw in reader:
                        if self.cancel.is_set():break
                        frame=Image.fromarray(raw)
                        if self.frames.full():
                            try:self.frames.get_nowait()
                            except Exception:pass
                        try:self.frames.put_nowait(frame)
                        except Exception:pass
                        self.cancel.wait(1/max(1,effective))
                    if self.cancel.is_set():break
        except Exception:
            # A broken/unsupported video must never propagate into UI or trading.
            self.cancel.set()
    def start(self):
        self.stop();self.cancel=threading.Event();self.running=True
        self.last_image=None
        path=Path(self.config.get('file',''))
        self.canvas.delete('all')
        if not path.is_file():return
        try:
            from PIL import Image
            if self.config.get('kind')=='video':
                thread=threading.Thread(target=self._read_frames,args=(path,),daemon=True,name='AkiraWallpaperDecoder')
                thread.start()
            else:
                with Image.open(path) as im:self.last_image=im.convert('RGBA')
            self._tick()
        except Exception as exc:
            self.canvas.create_text(15,20,anchor='nw',fill='#ff6d89',text='Vista previa no disponible: '+str(exc)[:75]);self.stop()
    def _tick(self):
        if not self.running:return
        if not self.canvas.winfo_ismapped():
            self.stop();return
        try:
            from PIL import ImageTk
            if self.config.get('kind')=='video':
                try:
                    while not self.frames.empty():self.last_image=self.frames.get_nowait()
                except Exception:pass
            if self.last_image is not None:
                w=min(720,max(160,self.canvas.winfo_width()))
                h=min(405,max(90,self.canvas.winfo_height()))
                result=transform_wallpaper(self.last_image,(w,h),self.config)
                self.photo=ImageTk.PhotoImage(result,master=self.canvas)
                self.canvas.delete('all');self.canvas.create_image(0,0,anchor='nw',image=self.photo)
        except Exception:self.stop();return
        if self.config.get('kind')=='video':
            fps=min(max(1,int(self.config.get('fps',12))),max(1,2*int(self.config.get('max_cpu_percent',10))))
            self.job=self.canvas.after(max(33,round(1000/fps)),self._tick)

def activate_style(studio, modules=()):
    """Palette activation before widgets exist; does not mutate position/strategy state."""
    import cyber_ui
    palette={
      'AKIRA Original':('#061022','#091b2b','#0b2135','#204960'),
      'Nebulosa':('#08091c','#17122a','#241b3e','#584078'),
      'Océano':('#031d2b','#082a39','#103447','#1a7281'),
      'Carbono':('#0d1016','#171c26','#222a35','#455367'),
    }.get(studio['theme'],('#061022','#091b2b','#0b2135','#204960'))
    values=dict(zip(('BG','PANEL','CARD','LINE'),palette))
    values['CYAN']=studio['accent'];values['PINK']=studio['secondary']
    cyber_ui.STUDIO_GLOW=int(studio['glow'])
    cyber_ui.STUDIO_TEXTURE=str(studio['panel_texture'])
    values['FONT']=str(studio['font'])
    for module in (cyber_ui,*modules):
        for k,v in values.items():
            if hasattr(module,k):setattr(module,k,v)
    return values
