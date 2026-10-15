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
    if 'procesando' in msg or 'transcribiendo' in msg:return 'thinking'
    if 'responde' in msg or kind=='speaking':return 'talking'
    if kind in ('partial','final') or 'escuchando' in msg or 'micrófono activo' in msg:return 'listening'
    return 'idle'


def vtuber_available():
    if Image is None:
        return False
    try:
        from akira_expressions import get_catalog, MIN_EXPRESSIONS
        return len(get_catalog(_root()).entries) >= MIN_EXPRESSIONS
    except (OSError, ValueError, KeyError, TypeError):
        return False


class AkiraLive2D(tk.Frame):
    """A real illustrated expression, never a face painted over another face."""
    EXPRESSIONS = set(SPRITE_MAP) | {'listening', 'curious', 'caring', 'surprised', 'focused', 'celebrating'}

    def __init__(self, parent, width=320, height=300, bg="#071522", **kw):
        super().__init__(parent, width=width, height=height, bg=bg, **kw)
        from collections import OrderedDict
        from akira_expressions import get_catalog
        self.bg = bg
        self.w, self.h = int(width), int(height)
        self.expression = 'idle'
        self.catalog = get_catalog(_root())
        self.expression_count = len(self.catalog.entries)
        self._sequence = 0
        self.selected = self.catalog.choose('idle')
        self._photos = OrderedDict()
        self._resize_job = self._tick_job = None
        self._tick_interval_ms = 250
        self._next_variation = time.monotonic() + 18
        self._closed = False
        self.canvas = tk.Canvas(self, width=width, height=height, bg=bg, highlightthickness=0, bd=0)
        self.canvas.pack(fill='both', expand=True)
        self.sprite = self.canvas.create_image(width / 2, height / 2, anchor='center')
        self.canvas.bind('<Configure>', self._resize)
        self.bind('<Destroy>', self._destroy, add='+')
        self._draw()
        self._tick_job = self.after(self._tick_interval_ms, self._tick)

    def _draw(self):
        if self._closed:
            return
        key = (self.selected.id, self.w, self.h)
        photo = self._photos.pop(key, None)
        if photo is None:
            image = self.catalog.image(self.selected, max(1, round(self.w * .94)), max(1, round(self.h * .94)))
            photo = ImageTk.PhotoImage(image, master=self.canvas)
        self._photos[key] = photo
        while len(self._photos) > 12:
            self._photos.popitem(last=False)
        self._photo_keep = photo
        self.canvas.itemconfigure(self.sprite, image=photo)
        self.canvas.coords(self.sprite, self.w / 2, self.h / 2)

    def _resize(self, event):
        if event.width < 20 or event.height < 20:
            return
        if (self.w, self.h) == (event.width, event.height):
            return
        self.w, self.h = event.width, event.height
        self.canvas.coords(self.sprite, self.w / 2, self.h / 2)
        if self._resize_job is not None:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(140, self._resize_frames)

    def _resize_frames(self):
        self._resize_job = None
        if not self._closed:
            self._photos.clear()
            self._draw()

    def set_expression(self, name, context=''):
        name = str(name or 'idle')
        if name not in self.EXPRESSIONS and name not in self.catalog.by_id:
            name = 'idle'
        if name == self.expression and not context:
            return
        self.expression = name
        self._sequence += 1
        self.selected = self.catalog.choose(name, self._sequence, context)
        self._next_variation = time.monotonic() + 18
        self._draw()

    def set_refresh_interval(self, milliseconds):
        self._tick_interval_ms = max(160, min(1000, int(milliseconds)))

    def _tick(self):
        self._tick_job = None
        if self._closed:
            return
        try:
            visible = self.winfo_ismapped()
            if visible and time.monotonic() >= self._next_variation and self.expression in ('idle', 'waiting'):
                self._sequence += 1
                self.selected = self.catalog.choose(self.expression, self._sequence)
                self._next_variation = time.monotonic() + 18
                self._draw()
            # No body shaking, artificial eyes, or mouth overlay. Hidden pages
            # do not decode images or repaint, and states stay stable while resizing.
            self._tick_job = self.after(self._tick_interval_ms if visible else 1500, self._tick)
        except tk.TclError:
            pass

    def _destroy(self, event):
        if event.widget is not self:
            return
        self._closed = True
        for job in (self._tick_job, self._resize_job):
            if job is not None:
                try:
                    self.after_cancel(job)
                except tk.TclError:
                    pass
        self._photos.clear()
