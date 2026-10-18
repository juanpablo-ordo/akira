"""The illustrated AKIRA expression catalog. Visual state only; no trading code.

Atlases stay unchanged on disk. Cells are read at display time, with a bounded
shared decode cache and a small per-avatar Tk thumbnail cache.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

CATALOG_VERSION = 1
MIN_EXPRESSIONS = 99
UI_REVISION = "R6 · 108 expresiones"

STATE_GROUPS = {
    "idle": ("friendly",), "waiting": ("friendly",),
    "happy": ("joy", "encourage"), "bullish": ("encourage",),
    "thinking": ("thinking", "curious"), "curious": ("curious",),
    "analyzing": ("focus",), "trading": ("focus",), "focused": ("focus",),
    "listening": ("listening",), "talking": ("speaking",),
    "caring": ("affection",), "surprised": ("surprise",),
    "celebrating": ("encourage",), "sleeping": ("sleep",),
    "alert": ("concern",), "error": ("concern",), "bearish": ("concern",),
    "blink": ("sleep",),
}


@dataclass(frozen=True)
class Expression:
    id: str
    label: str
    group: str
    group_label: str
    atlas: str
    column: int
    row: int
    bounds: tuple | list | None = None


class ExpressionCatalog:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.folder = self.root / "assets" / "expressions"
        data = json.loads((self.folder / "catalog.json").read_text(encoding="utf-8"))
        if data.get("schema") != CATALOG_VERSION or data.get("grid") != [3, 3]:
            raise ValueError("El catálogo de expresiones no es compatible con esta versión.")
        self.entries = tuple(Expression(**row) for row in data["expressions"])
        self.canvas_size = int(data.get('canvas_size', 448))
        if not 256 <= self.canvas_size <= 1024:raise ValueError('Lienzo de avatar inválido')
        self.by_id = {entry.id: entry for entry in self.entries}
        if len(self.by_id) != len(self.entries) or len(self.entries) < MIN_EXPRESSIONS:
            raise ValueError("AKIRA necesita al menos 99 expresiones distintas y completas.")
        cells = set()
        for entry in self.entries:
            if not 0 <= entry.row < 3 or not 0 <= entry.column < 3:
                raise ValueError("Celda fuera del atlas: " + entry.id)
            path = (self.folder / entry.atlas).resolve()
            if path.parent != self.folder or not path.is_file():
                raise ValueError("Falta una ilustración de AKIRA: " + entry.atlas)
            cell = (entry.atlas, entry.row, entry.column)
            if cell in cells:
                raise ValueError("Dos expresiones usan la misma cara: " + entry.id)
            cells.add(cell)
            if entry.bounds is not None:
                if len(entry.bounds)!=4 or not all(isinstance(v,int) and v>=0 for v in entry.bounds):
                    raise ValueError('Recorte inválido: '+entry.id)
        self._atlases = OrderedDict()

    def candidates(self, state):
        if state in self.by_id:
            return (self.by_id[state],)
        groups = STATE_GROUPS.get(state, STATE_GROUPS["idle"])
        return tuple(entry for entry in self.entries if entry.group in groups)

    def choose(self, state, sequence=0, context=""):
        candidates = self.candidates(state)
        if not candidates:
            candidates = self.candidates("idle")
        index = int.from_bytes(hashlib.sha256(str(context).encode("utf-8")).digest()[:4], "big") if context else sequence
        return candidates[index % len(candidates)]

    def cell(self, expression):
        from PIL import Image
        entry = self.by_id[expression] if isinstance(expression, str) else expression
        path = self.folder / entry.atlas
        source = self._atlases.pop(path, None)
        if source is None:
            with Image.open(path) as image:
                source = image.convert("RGBA")
        self._atlases[path] = source
        while len(self._atlases) > 2:
            self._atlases.popitem(last=False)
        width, height = source.size
        bounds = entry.bounds or (round(entry.column * width / 3), round(entry.row * height / 3),
                  round((entry.column + 1) * width / 3), round((entry.row + 1) * height / 3))
        if not 0<=bounds[0]<bounds[2]<=width or not 0<=bounds[1]<bounds[3]<=height:
            raise ValueError('Ilustración fuera de límites: '+entry.id)
        sprite=source.crop(bounds)
        ratio=min((self.canvas_size-24)/sprite.width,(self.canvas_size-24)/sprite.height)
        sprite=sprite.convert('RGBa').resize((max(1,round(sprite.width*ratio)),max(1,round(sprite.height*ratio))),Image.Resampling.LANCZOS).convert('RGBA')
        # Actual illustrated bounds can cross a nominal grid line. A shared
        # transparent canvas prevents clipping tails or showing a neighbor's
        # outline, while keeping every dog's feet at the same display height.
        canvas=Image.new('RGBA',(self.canvas_size,self.canvas_size))
        canvas.paste(sprite,((self.canvas_size-sprite.width)//2,self.canvas_size-sprite.height-8))
        return canvas

    def image(self, expression, width, height):
        from PIL import Image
        source = self.cell(expression)
        ratio = min(max(1, width) / source.width, max(1, height) / source.height)
        size = (max(1, round(source.width * ratio)), max(1, round(source.height * ratio)))
        if size == source.size:
            return source
        if ratio >= 1:
            return source.resize(size, Image.Resampling.NEAREST)
        # Premultiplied alpha prevents hidden transparent RGB from tinting edges.
        return source.convert("RGBa").resize(size, Image.Resampling.LANCZOS).convert("RGBA")

    def validate_artwork(self):
        """Decode every cell: reject empty, duplicate, opaque, or corrupt assets."""
        hashes = set()
        for entry in self.entries:
            image = self.cell(entry)
            if image.getbbox() is None or image.getextrema()[3] != (0, 255):
                raise ValueError("Expresión vacía o sin transparencia: " + entry.id)
            digest = hashlib.sha256(image.tobytes()).hexdigest()
            if digest in hashes:
                raise ValueError("Expresión duplicada: " + entry.id)
            hashes.add(digest)
        return {"count": len(self.entries), "distinct_cells": len(hashes), "transparent": True}


_CATALOGS = {}


def get_catalog(root):
    root = Path(root).resolve()
    path = root / "assets" / "expressions" / "catalog.json"
    stamp = path.stat().st_mtime_ns
    key = (root, stamp)
    catalog = _CATALOGS.get(key)
    if catalog is None:
        catalog = ExpressionCatalog(root)
        _CATALOGS.clear()
        _CATALOGS[key] = catalog
    return catalog
