"""AKIRA V193 · avatar pixel art por sprites precalculados.

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
    if 'procesando' in msg or 'transcribiendo' in msg:return 'thinking'
    if 'responde' in msg or kind=='speaking':return 'talking'
    if kind in ('partial','final') or 'escuchando' in msg or 'micrófono activo' in msg:return 'idle'
    return 'idle'


def vtuber_available():
    folder = _root() / "assets" / "vtuber"
    return Image is not None and all((folder / name).exists() for name in set(SPRITE_MAP.values()))


class AkiraLive2D(tk.Frame):
    EXPRESSIONS = set(SPRITE_MAP)

    def __init__(self, parent, width=320, height=300, bg="#071522", **kw):
        super().__init__(parent, width=width, height=height, bg=bg, **kw)
        self.bg = bg; self.w = int(width); self.h = int(height)
        self.expression = "idle"; self.t0 = time.monotonic(); self.last_activity = self.t0
        self._next_blink = self.t0 + random.uniform(2.2, 4.8)
        self._blink_until = 0.0
        self._next_idle_mouth = self.t0 + random.uniform(4.0, 8.0)
        self._mouth_until = 0.0
        self.canvas = tk.Canvas(self, width=width, height=height, bg=bg, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.frames = {};self._source_images={};self._resize_job=None
        self._load_frames()
        first = self.frames.get("idle")
        self.sprite = self.canvas.create_image(width//2, height//2, anchor="center", image=first)
        self.canvas.bind('<Configure>',self._resize)
        self._photo_keep = list(self.frames.values())
        self._shown = None;self._tick_interval_ms=180
        self.after(self._tick_interval_ms, self._tick)

    def _load_frames(self):
        if Image is None:
            return
        folder = _root() / "assets" / "vtuber"
        fallback = _root() / "assets" / "akira.png"
        cache = {}
        for state, filename in SPRITE_MAP.items():
            path = folder / filename
            if not path.exists(): path = fallback
            if path in cache:
                self.frames[state] = cache[path]
                continue
            try:
                if path not in self._source_images:
                    src=_SOURCE_IMAGES.get(path)
                    if src is None:
                        with Image.open(path) as original:src=original.convert("RGBA")
                        _SOURCE_IMAGES[path]=src
                    self._source_images[path]=src
                src = self._source_images[path]
                # Mantener el mismo lienzo en todos los estados: recortar cada
                # expresión por separado haría saltar el personaje al cambiarla.
                ratio = min((self.w * .92) / max(1, src.width), (self.h * .92) / max(1, src.height))
                size = (max(1, int(src.width * ratio)), max(1, int(src.height * ratio)))
                src = src.resize(size, Image.Resampling.NEAREST)
                cache[path] = ImageTk.PhotoImage(src)
                self.frames[state] = cache[path]
            except Exception:
                pass
        if "idle" not in self.frames and fallback.exists():
            src=Image.open(fallback).convert("RGBA"); src.thumbnail((int(self.w*.92),int(self.h*.92)),Image.Resampling.LANCZOS)
            self.frames["idle"] = ImageTk.PhotoImage(src)

    def _resize(self,event):
        self.canvas.coords(self.sprite,event.width/2,event.height/2)
        if event.width<30 or event.height<30:return
        if abs(event.width-self.w)<12 and abs(event.height-self.h)<12:return
        self.w,self.h=event.width,event.height
        if self._resize_job is not None:self.after_cancel(self._resize_job)
        self._resize_job=self.after(150,self._resize_frames)

    def _resize_frames(self):
        self._resize_job=None
        if not self.winfo_exists():return
        self._load_frames();self._photo_keep=list(self.frames.values());self._shown=None
        frame=self.frames.get(self.expression) or self.frames.get('idle')
        if frame is not None:self.canvas.itemconfigure(self.sprite,image=frame)

    def set_expression(self, name):
        n = str(name or "idle").lower()
        n = n if n in self.EXPRESSIONS else "idle"
        if n != self.expression:
            self.expression = n
            self.last_activity = time.monotonic()

    def _frame_name(self, now):
        expr = self.expression
        if expr == "sleeping": return "sleeping"
        # Blink: no dibujamos ojos artificiales. Un frame de ojos cerrados aparece
        # 100-140 ms y vuelve al idle original.
        if now >= self._next_blink:
            self._blink_until = now + random.uniform(.10, .14)
            self._next_blink = now + random.uniform(2.4, 5.2)
        if now < self._blink_until:
            return "blink" if "blink" in self.frames else "idle"
        # Lengua/boca en reposo de forma ocasional, como un PNGTuber.
        if now >= self._next_idle_mouth:
            self._mouth_until = now + random.uniform(.18, .30)
            self._next_idle_mouth = now + random.uniform(4.5, 9.0)
        if expr == "talking":
            return "talking" if int((now-self.t0)*7) % 2 == 0 else "idle"
        if expr == "idle" and now < self._mouth_until:
            return "talking"
        return expr if expr in self.frames else "idle"

    def set_refresh_interval(self, milliseconds):
        """Only changes idle animation; never affects order monitoring."""
        self._tick_interval_ms=max(120,min(1000,int(milliseconds)))

    def _tick(self):
        try:
            if not self.winfo_exists(): return
            if not self.winfo_ismapped():
                self.after(max(1000,self._tick_interval_ms),self._tick)
                return
            now = time.monotonic(); t = now-self.t0
            name = self._frame_name(now); frame = self.frames.get(name) or self.frames.get("idle")
            if frame is not None and name != self._shown:
                self.canvas.itemconfigure(self.sprite, image=frame)
                self._shown = name
            expr=self.expression
            amp = .55 if expr in ("analyzing","thinking","trading") else 1.5
            bob = amp * math.sin(t*1.45)
            sway = (.8 if expr in ("analyzing","thinking","trading") else 1.5) * math.sin(t*.67)
            self.canvas.coords(self.sprite, self.canvas.winfo_width()/2+sway, self.canvas.winfo_height()/2+bob)
            self.after(self._tick_interval_ms, self._tick)
        except tk.TclError:
            pass
