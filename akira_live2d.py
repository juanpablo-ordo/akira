"""AKIRA R6 · ilustraciones originales en un catálogo de 108 expresiones.

No hace OpenGL ni filtros por frame. Las imágenes se redimensionan al abrir o
al ajustar el panel. En idle solo mueve el sprite y alterna frames para parpadeo/
boca; por eso el coste de CPU es mínimo comparado con V183/V185.
"""
from __future__ import annotations

import math
import random
import sys
import time
import tkinter as tk
import weakref
from pathlib import Path

try:
    from PIL import Image, ImageTk
except Exception:
    Image = ImageTk = None

_SOURCE_IMAGES=weakref.WeakValueDictionary()


def _root():
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


SPRITE_MAP = {
    "idle": "akira_pixel_idle.png",
    "blink": "akira_pixel_blink.png",
    "talking": "akira_pixel_talking.png",
    "thinking": "akira_pixel_thinking.png",
    "analyzing": "akira_pixel_analyzing.png",
    "bullish": "akira_pixel_bullish.png",
    "bearish": "akira_pixel_bearish.png",
    "happy": "akira_pixel_happy.png",
    "alert": "akira_pixel_alert.png",
    "trading": "akira_pixel_analyzing.png",
    "waiting": "akira_pixel_idle.png",
    "error": "akira_pixel_alert.png",
    "sleeping": "akira_pixel_sleeping.png",
}



def expression_for_reply(answer: str) -> str:
    """Choose a lightweight, purely visual reaction to an AI response.

    This never affects market logic or execution decisions.
    """
    msg = str(answer or "").lower()
    if any(word in msg for word in ("no se pudo", "sin conexión", "error:", "falló", "no llegó una respuesta")):
        return "alert"
    if any(word in msg for word in ("felicidades", "objetivo alcanzado", "ganancia confirmada", "take profit alcanzado")):
        return "happy"
    if any(word in msg for word in ("lo lograste", "bien hecho", "excelente avance")):
        return "celebrating"
    if any(word in msg for word in ("lo siento", "estoy contigo", "aquí para escucharte", "gracias por contarme")):
        return "caring"
    if any(word in msg for word in ("qué sorpresa", "me sorprende", "no me lo esperaba", "inesperado")):
        return "surprised"
    if any(word in msg for word in ("cuéntame más", "a qué te refieres", "puedes contarme", "me da curiosidad")):
        return "curious"
    if any(word in msg for word in ("sigo analizando", "revisando indicadores", "verificando precios")):
        return "analyzing"
    if any(word in msg for word in ("necesito comprobar", "déjame revisar", "considerando opciones")):
        return "thinking"
    return "talking"


def expression_for_dialogue(question: str, answer: str) -> str:
    """Use what was asked and what Akira answered; purely visual, not a trade signal."""
    text=str(question or '').lower()
    reply=str(answer or '').lower()
    decided=expression_for_reply(reply)
    if decided!='talking':return decided
    if any(key in text for key in ('analiza','mercado','oro','bitcoin','btc','xau','pendiente','gráfico','indicador')):
        return 'analyzing'
    if any(key in text for key in ('por qué','explica','cómo','que significa','qué significa','investiga','busca')):
        return 'thinking'
    return 'talking'


def expression_for_voice_event(kind: str, text: str = '') -> str:
    """Call avatar transitions: listening, speaking, paused, errors and ending."""
    kind=str(kind or '').lower();msg=str(text or '').lower()
    if kind in ('error','download_error') or any(s in msg for s in ('error','audio saturado','desconectó')):return 'alert'
    if 'llamada finalizada' in msg or 'demostración terminada' in msg:return 'idle'
    if 'silenciado' in msg or kind=='paused':return 'sleeping'
    if 'procesando' in msg or 'transcribiendo' in msg or 'preparando voz' in msg:return 'thinking'
    if 'responde' in msg or kind=='speaking':return 'talking'
    if kind in ('partial','final') or 'escuchando' in msg or 'reanudando escucha' in msg or 'micrófono activo' in msg:return 'listening'
    return 'idle'


def vtuber_available():
    if Image is None:
        return False
    try:
        from akira_expressions import get_catalog, MIN_EXPRESSIONS
        return len(get_catalog(_root()).entries) >= MIN_EXPRESSIONS
    except (OSError, ValueError, KeyError, TypeError):
        return False


class AvatarDirector:
    """One expression and one clock for every view of the same character."""
    def __init__(self,catalog,clock=time.monotonic):
        self.catalog,self.clock=catalog,clock
        self.listeners=weakref.WeakSet();self.sequence=0;self.expression='idle';self.context=''
        self.selected=catalog.choose('idle');self.next_variation=clock()+18
        self.playing=False;self.last_level=0;self.mouth_level=0
        self.loading=False;self.online=True;self.interacting=False;self.blink_frame=None
        self._blink_started=None;self._next_blink=clock()+random.uniform(3.0,5.5)
        self._resume_expression='idle';self._wake_until=0

    def subscribe(self,avatar):
        self.listeners.add(avatar);avatar._receive(self.expression,self.selected,False)

    def publish(self,name,context='',force=False):
        name=str(name or 'idle');context=str(context or '')
        if not self.online and not self.interacting and name!='sleeping' and not force:return
        if self.playing and not force:return
        if name==self.expression and context==self.context:return
        self.sequence+=1;self.expression=name;self.context=context
        self.selected=self.catalog.choose(name,self.sequence,context)
        self.next_variation=self.clock()+18
        for avatar in list(self.listeners):avatar._receive(name,self.selected,True)

    def refresh(self):
        now=self.clock()
        if self.online and self._wake_until and now>=self._wake_until:
            self._wake_until=0;self.publish(self._resume_expression,force=True)
        if self.playing and self.online:
            candidate=getattr(self.catalog,'next_in_sequence',None)
            next_image=candidate('talking',now,self.selected) if candidate else None
            if next_image is not None and next_image.id!=self.selected.id:
                self.selected=next_image
                for avatar in list(self.listeners):avatar._receive(self.expression,self.selected,False)
        if self.playing or not (self.online or self.interacting) or self.expression.startswith('AKIRA_'):return
        # User-authored multi-frame animation; bounded updates, no MT5 calls.
        candidate=getattr(self.catalog,'next_in_sequence',None)
        if candidate is not None:
            next_image=candidate(self.expression,now,self.selected)
            if next_image is not None and next_image.id!=self.selected.id:
                self.selected=next_image
                for avatar in list(self.listeners):avatar._receive(self.expression,self.selected,False)
        before=self.blink_frame
        if self._blink_started is None and now>=self._next_blink:self._blink_started=now
        if self._blink_started is not None:
            age=now-self._blink_started
            self.blink_frame=1 if age<.06 else 2 if age<.14 else 1 if age<.20 else None
            if age>=.20:self._blink_started=None;self._next_blink=now+random.uniform(3.0,5.5)
        if before!=self.blink_frame:
            for avatar in list(self.listeners):avatar._draw()

    def busy(self,active):
        if self.loading==bool(active):return
        self.loading=bool(active)
        for avatar in list(self.listeners):
            if avatar.winfo_ismapped():avatar._loading_ring()

    def network(self,online):
        if bool(online)==self.online:return
        self.online=bool(online);self.blink_frame=None;self._blink_started=None
        if not self.online:
            self._resume_expression='analyzing' if self.expression=='analyzing' else 'idle'
            if not self.interacting:self.publish('sleeping','Sin Internet',force=True)
        else:
            if not self.interacting:self.publish('waking','Conexión recuperada',force=True);self._wake_until=self.clock()+.55

    def interaction(self,active):
        self.interacting=bool(active)
        if not active and not self.online:self.publish('sleeping','Sin Internet',force=True)

    def playback(self,active):
        self.playing=bool(active);self.last_level=0;self.mouth_level=0
        self.publish('AKIRA_046' if active else 'listening',force=True)

    def level(self,value):
        if not self.playing or self.clock()-self.last_level<.16:return
        self.last_level=self.clock()
        self.mouth_level=float(value)
        self.publish('AKIRA_047' if float(value)>.035 else 'AKIRA_046',force=True)


class AkiraLive2D(tk.Frame):
    """Illustrated faces with short crossfades, sharing the desktop director."""
    EXPRESSIONS=set(SPRITE_MAP)|{'listening','curious','caring','surprised','focused','celebrating','waking','loading','connecting'}

    def __init__(self,parent,width=320,height=300,bg='#071522',director=None,**kw):
        super().__init__(parent,width=width,height=height,bg=bg,**kw)
        from collections import OrderedDict
        from akira_expressions import get_catalog
        from avatar_animation import StateSprites
        root=self.winfo_toplevel()
        self.catalog=getattr(root,'_akira_user_catalog',None) or get_catalog(_root())
        self.expression_count=len(self.catalog.entries)
        if director is None:
            director=getattr(root,'_akira_director',None)
            if director is None:director=AvatarDirector(self.catalog);root._akira_director=director
        self.director=director;self.bg=bg;self.w,self.h=int(width),int(height)
        self.expression='idle';self.selected=self.catalog.choose('idle')
        self._photos=OrderedDict();self._closed=False;self._tick_interval_ms=250
        self._state_images=OrderedDict();self._sprites=StateSprites(_root());self._visual_key=None
        self._resize_job=self._tick_job=self._fade_job=None
        self.canvas=tk.Canvas(self,width=width,height=height,bg=bg,highlightthickness=0,bd=0)
        self.canvas.pack(fill='both',expand=True)
        self.sprite=self.canvas.create_image(width/2,height/2,anchor='center')
        self._spinner_base=self.canvas.create_oval(0,0,1,1,outline='#214959',width=2,state='hidden')
        self._spinner=self.canvas.create_arc(0,0,1,1,outline='#23ddf4',width=2,style='arc',extent=90,state='hidden')
        self.canvas.bind('<Configure>',self._resize)
        self.bind('<Map>',self._mapped,add='+')
        self.bind('<Destroy>',self._destroy,add='+')
        director.subscribe(self)
        # Windows can defer <Map> beyond update_idletasks(). Give the canvas
        # its first frame now; later hidden updates still avoid image work.
        self._paint(self._display_image())
        self._tick_job=self.after(self._tick_interval_ms,self._tick)

    def _image(self,entry):
        key=(entry.id,self.w,self.h)
        image=self._photos.pop(key,None)
        if image is None:
            source=self.catalog.image(entry,max(1,round(self.w*.94)),max(1,round(self.h*.94)))
            image=Image.new('RGBA',(max(1,self.w),max(1,self.h)),(0,0,0,0))
            image.paste(source,((self.w-source.width)//2,(self.h-source.height)//2))
        self._photos[key]=image
        while len(self._photos)>12:self._photos.popitem(last=False)
        return image

    def _paint(self,image):
        if self._closed:return
        self._current_pil=image
        self._photo_keep=ImageTk.PhotoImage(image,master=self.canvas)
        self.canvas.itemconfigure(self.sprite,image=self._photo_keep)
        self.canvas.coords(self.sprite,self.w/2,self.h/2)

    def _state_frame(self):
        if hasattr(self.selected,'path'):return None
        if self.expression.startswith('AKIRA_'):return None
        frame={'idle':0,'analyzing':0,'thinking':4,'waiting':4,'loading':4,'connecting':4,
               'sleeping':5,'waking':6,'listening':7}.get(self.expression)
        if frame in (0,4) and self.director.blink_frame is not None:return self.director.blink_frame
        return frame

    def _display_image(self):
        if hasattr(self.selected,'path'):
            # User-provided blinking state overrides the base frame briefly.
            if self.director.blink_frame in (1,2):
                alternative=self.catalog.choose('blink')
                if hasattr(alternative,'path') and alternative.state=='blink':return self._image(alternative)
            return self._image(self.selected)
        frame=self._state_frame()
        if frame is None:return self._image(self.selected)
        key=(frame,self.w,self.h);image=self._state_images.pop(key,None)
        if image is None:image=self._sprites.image(frame,self.w,self.h)
        self._state_images[key]=image
        while len(self._state_images)>12:self._state_images.popitem(last=False)
        return image

    def _draw(self):
        if self._closed or not self.winfo_ismapped() or self._fade_job is not None:return
        key=(self.expression,self.selected.id,self._state_frame(),self.director.blink_frame,self.w,self.h)
        if self._visual_key!=key:self._visual_key=key;self._paint(self._display_image())

    def _loading_ring(self):
        visible=self.director.online and (self.director.loading or self.expression in ('loading','connecting'))
        state='normal' if visible else 'hidden'
        radius=max(5,min(11,self.h*.08));x=self.w-radius-6;y=self.h-radius-6
        for item in (self._spinner_base,self._spinner):
            self.canvas.coords(item,x-radius,y-radius,x+radius,y+radius)
            self.canvas.itemconfigure(item,state=state)
        if visible:self.canvas.itemconfigure(self._spinner,start=-(int(self.director.clock()/.08)%12)*30)

    def _mapped(self,event=None):
        if event is not None and event.widget is not self:return
        self._draw();self._loading_ring()
        if self._tick_job is not None:
            try:self.after_cancel(self._tick_job)
            except tk.TclError:pass
        self._tick_job=self.after(0,self._tick)

    def _receive(self,name,entry,animate):
        previous=self.selected;self.expression=name;self.selected=entry
        self._visual_key=None
        if self._fade_job is not None:
            self.after_cancel(self._fade_job);self._fade_job=None
        if self._closed or not self.winfo_ismapped():return
        if not animate or previous.id==entry.id:self._draw();return
        before=getattr(self,'_current_pil',None)
        if before is None or before.size!=(self.w,self.h):before=self._image(previous)
        after=self._display_image();started=time.monotonic()
        duration=.09 if self.director.playing else .16
        def step():
            self._fade_job=None
            if self._closed or not self.winfo_ismapped():return
            alpha=min(1,(time.monotonic()-started)/duration)
            self._paint(Image.blend(before,after,alpha))
            if alpha<1:self._fade_job=self.after(25,step)
        step()

    def _resize(self,event):
        if event.width<20 or event.height<20 or (self.w,self.h)==(event.width,event.height):return
        self.w,self.h=event.width,event.height
        self.canvas.coords(self.sprite,self.w/2,self.h/2)
        if self._resize_job is not None:self.after_cancel(self._resize_job)
        if self._fade_job is not None:self.after_cancel(self._fade_job);self._fade_job=None
        self._resize_job=self.after(100,self._resize_frames)

    def _resize_frames(self):
        self._resize_job=None
        if not self._closed:self._photos.clear();self._draw()

    def set_expression(self,name,context=''):
        if name not in self.EXPRESSIONS and name not in self.catalog.by_id:name='idle'
        self.director.publish(name,context)

    def set_refresh_interval(self,milliseconds):
        self._tick_interval_ms=max(160,min(1000,int(milliseconds)))

    def _tick(self):
        self._tick_job=None
        if self._closed:return
        try:
            visible=self.winfo_ismapped()
            if visible:self.director.refresh();self._draw();self._loading_ring()
            delay=60 if self.director.blink_frame is not None else 80 if self.director.loading or self.expression in ('loading','connecting') else self._tick_interval_ms
            self._tick_job=self.after(delay if visible else 1500,self._tick)
        except tk.TclError:pass

    def _destroy(self,event):
        if event.widget is not self:return
        self._closed=True;self.director.listeners.discard(self)
        for job in (self._tick_job,self._resize_job,self._fade_job):
            if job is not None:
                try:self.after_cancel(job)
                except tk.TclError:pass
        self._photos.clear()
        self._state_images.clear()
        self._photo_keep=None;self._current_pil=None
