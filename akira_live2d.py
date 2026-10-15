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
        self.playing=False;self.last_level=0

    def subscribe(self,avatar):
        self.listeners.add(avatar);avatar._receive(self.expression,self.selected,False)

    def publish(self,name,context='',force=False):
        name=str(name or 'idle');context=str(context or '')
        if self.playing and not force:return
        if name==self.expression and context==self.context:return
        self.sequence+=1;self.expression=name;self.context=context
        self.selected=self.catalog.choose(name,self.sequence,context)
        self.next_variation=self.clock()+18
        for avatar in list(self.listeners):avatar._receive(name,self.selected,True)

    def refresh(self):
        if not self.playing and self.expression in ('idle','waiting') and self.clock()>=self.next_variation:
            self.publish(self.expression,str(self.sequence+1))

    def playback(self,active):
        self.playing=bool(active);self.last_level=0
        self.publish('AKIRA_046' if active else 'listening',force=True)

    def level(self,value):
        if not self.playing or self.clock()-self.last_level<.16:return
        self.last_level=self.clock()
        self.publish('AKIRA_047' if float(value)>.035 else 'AKIRA_046',force=True)


class AkiraLive2D(tk.Frame):
    """Illustrated faces with short crossfades, sharing the desktop director."""
    EXPRESSIONS=set(SPRITE_MAP)|{'listening','curious','caring','surprised','focused','celebrating'}

    def __init__(self,parent,width=320,height=300,bg='#071522',director=None,**kw):
        super().__init__(parent,width=width,height=height,bg=bg,**kw)
        from collections import OrderedDict
        from akira_expressions import get_catalog
        self.catalog=get_catalog(_root());self.expression_count=len(self.catalog.entries)
        root=self.winfo_toplevel()
        if director is None:
            director=getattr(root,'_akira_director',None)
            if director is None:director=AvatarDirector(self.catalog);root._akira_director=director
        self.director=director;self.bg=bg;self.w,self.h=int(width),int(height)
        self.expression='idle';self.selected=self.catalog.choose('idle')
        self._photos=OrderedDict();self._closed=False;self._tick_interval_ms=250
        self._resize_job=self._tick_job=self._fade_job=None
        self.canvas=tk.Canvas(self,width=width,height=height,bg=bg,highlightthickness=0,bd=0)
        self.canvas.pack(fill='both',expand=True)
        self.sprite=self.canvas.create_image(width/2,height/2,anchor='center')
        self.canvas.bind('<Configure>',self._resize)
        self.bind('<Map>',lambda e:self._draw(),add='+')
        self.bind('<Destroy>',self._destroy,add='+')
        director.subscribe(self)
        # Windows can defer <Map> beyond update_idletasks(). Give the canvas
        # its first frame now; later hidden updates still avoid image work.
        self._paint(self._image(self.selected))
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
        self._photo_keep=ImageTk.PhotoImage(image,master=self.canvas)
        self.canvas.itemconfigure(self.sprite,image=self._photo_keep)
        self.canvas.coords(self.sprite,self.w/2,self.h/2)

    def _draw(self):
        if not self._closed and self.winfo_ismapped():self._paint(self._image(self.selected))

    def _receive(self,name,entry,animate):
        previous=self.selected;self.expression=name;self.selected=entry
        if self._fade_job is not None:
            self.after_cancel(self._fade_job);self._fade_job=None
        if self._closed or not self.winfo_ismapped():return
        if not animate or previous.id==entry.id:self._draw();return
        before,after=self._image(previous),self._image(entry);started=time.monotonic()
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
            if visible:self.director.refresh()
            self._tick_job=self.after(self._tick_interval_ms if visible else 1500,self._tick)
        except tk.TclError:pass

    def _destroy(self,event):
        if event.widget is not self:return
        self._closed=True;self.director.listeners.discard(self)
        for job in (self._tick_job,self._resize_job,self._fade_job):
            if job is not None:
                try:self.after_cancel(job)
                except tk.TclError:pass
        self._photos.clear()
