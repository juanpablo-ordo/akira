"""Visual-only palette application for Akira Studio.

Loads the user's theme before Tk widgets are constructed. Never imports the
trading engine, sends orders, or runs a periodic repaint loop. The original
AKIRA palette is the default and remains available after any customization.
"""
from __future__ import annotations
import sys

ORIGINAL={
    'BG':'#010b18','PANEL':'#031326','CARD':'#031a31','LINE':'#164762',
    'CYAN':'#23ddf4','BLUE':'#1079c5','PINK':'#ed58cc','AMBER':'#ffc45a',
    'GREEN':'#44e5b5','RED':'#ff6d89','MUTED':'#88a9bf','TEXT':'#e3effa',
}
PRESETS={
    'AKIRA Original':{},
    'Nebulosa':{'BG':'#100d25','PANEL':'#1c1635','CARD':'#231c44','LINE':'#51447e','BLUE':'#6545bd'},
    'Océano':{'BG':'#031722','PANEL':'#072936','CARD':'#0b3445','LINE':'#205e6c','BLUE':'#0d83a6'},
    'Aurora':{'BG':'#031b22','PANEL':'#082f39','CARD':'#103944','LINE':'#23737b','BLUE':'#087589'},
    'Violeta':{'BG':'#120c27','PANEL':'#21153f','CARD':'#2d1c50','LINE':'#755692','BLUE':'#7442b7'},
    'Cobre':{'BG':'#1d120d','PANEL':'#2e2117','CARD':'#412c1f','LINE':'#966642','BLUE':'#9c5e28'},
    'Noche polar':{'BG':'#050912','PANEL':'#0d1729','CARD':'#14243b','LINE':'#35516f','BLUE':'#246387'},
    'Carbono':{'BG':'#101315','PANEL':'#1a2127','CARD':'#252d34','LINE':'#45525c','BLUE':'#27648b'},
}


def palette_for(studio):
    """Return valid static colors; do not execute/load any user-supplied code."""
    from re import fullmatch
    studio=studio or {}
    profile=(studio.get('theme_profiles') or {}).get(studio.get('theme'),{})
    palette={**ORIGINAL,**PRESETS.get(profile.get('theme',studio.get('theme')), {})}
    for key,source in (('CYAN','accent'),('PINK','secondary'),('BG','background_color')):
        value=studio.get(source)
        if isinstance(value,str) and fullmatch(r'#[0-9a-fA-F]{6}',value):
            palette[key]=value.lower()
    return palette


def apply_theme(studio,root=None):
    """Apply a palette to modules before their widgets are created.

    Every class with static Tk colors reads its module globals when building
    the UI, so update existing imported palettes in place. A restart is
    intentionally required; changing live widgets would stall MT5 views.
    """
    palette=palette_for(studio)
    affected=('cyber_ui','desktop','desktop_services','desktop_layout',
              'akira_studio_ui','desktop_settings','akira_live2d')
    for name in affected:
        mod=sys.modules.get(name)
        if mod is None:continue
        for key,value in palette.items():
            if key in vars(mod):setattr(mod,key,value)
    cyber=sys.modules.get('cyber_ui')
    if cyber is not None:
        cyber.STUDIO_GLOW=max(0,min(100,int(studio.get('glow',65))))
        cyber.STUDIO_TEXTURE=studio.get('panel_texture','Neon grid')
        cyber.STUDIO_FONT_SCALE=max(60,min(160,int(studio.get('font_scale',100))))
        family=str(studio.get('font','') or '').strip()
        if family and root is not None and hasattr(root,'tk'):
            from tkinter import font
            available={f.casefold():f for f in font.families(root)}
            if family.casefold() in available:
                cyber.FONT=available[family.casefold()]
                for name in affected:
                    mod=sys.modules.get(name)
                    if mod is not None and 'FONT' in vars(mod):setattr(mod,'FONT',cyber.FONT)
    return palette
