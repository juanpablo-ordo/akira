"""Explicit selection among implemented rule families; no new risk policy."""
from dataclasses import replace
from functools import lru_cache
import math
from trade_quality_gate import family

ADAPTIVE='AKIRA_ADAPTATIVA'
FAMILIES=('PENDIENTE_RETROCESO','PENDIENTE_RUPTURA','RUNNER_CONTINUACION_M15','RUNNER_RETEST_M5','REVERSION_CONFIRMADA','RANGO_RECHAZO')
STRATEGY_VERSION=2
SELECTOR_VERSION=2

def selected(cfg):return (cfg.get('strategy_choice') or {}).get('selected',ADAPTIVE)

@lru_cache(maxsize=1)
def variants():
    from strategy_lab import definitions
    return {d['id']:d for d in definitions() if d.get('spec')}

def known(choice):return choice in (ADAPTIVE,*FAMILIES) or choice in variants()

def allows(plan,cfg):
    choice=selected(cfg)
    if not known(choice):return False
    target=variants()[choice]['base_family'] if choice in variants() else choice
    return target==ADAPTIVE or family(plan)==target

def tag(plan,cfg):
    from akira_version import BUILD_ID
    return replace(plan,strategy_id=family(plan),strategy_version=STRATEGY_VERSION,
                   selector_id=selected(cfg),selector_version=SELECTOR_VERSION,execution_build=BUILD_ID)


def variant_decision(plan,cfg,frames):
    """Refine an existing validated technical proposal; never synthesize live levels."""
    d=variants().get(selected(cfg))
    if not d:return True,''
    def get(obj,key,default=None):
        return obj.get(key,default) if isinstance(obj,dict) else getattr(obj,key,default)
    def num(obj,key,default=0):
        try:
            value=float(get(obj,key,default))
            return value if math.isfinite(value) else default
        except (ValueError,TypeError):return default
    f=frames.get('M15') or {};h=frames.get('H1') or {};bars=get(f,'bars',[]) or []
    atr=num(f,'atr');side=num(plan,'side');entry=num(plan,'entry');sl=num(plan,'sl');tp=num(plan,'tp')
    if len(bars)<24 or atr<=0:return False,'La variante necesita al menos 24 velas M15 y un ATR válido.'
    spec=d['spec'];risk=side*(entry-sl)
    if risk<=0 or side*(tp-entry)/risk<spec['min_rr']:return False,'Recorrido insuficiente para el R:R mínimo de la variante.'
    last=bars[-1];low=num(last,'low');high=num(last,'high');close=num(last,'close');body=side*(close-num(last,'open'))
    prior=bars[-21:-1];lo=min(num(b,'low') for b in prior);hi=max(num(b,'high') for b in prior)
    key=spec['template'];anchor=None
    if key=='EMA_PULLBACK':
        ema=num(f,'ema21',num(f,'slow'))
        if side*num(h,'trend')<=.18 or side*num(f,'trend')<=.12 or not 35<=num(f,'rsi',50)<=70 or abs(entry-ema)>atr*.5:
            return False,'Falta retroceso a EMA21 con tendencia M15/H1 y RSI compatibles.'
        anchor=min(num(b,'low') for b in bars[-8:]) if side==1 else max(num(b,'high') for b in bars[-8:])
    elif key=='BREAK_RETEST':
        window=bars[-10:-2];level=max(num(b,'high') for b in window) if side==1 else min(num(b,'low') for b in window)
        touch=low<=level+atr*.2 if side==1 else high>=level-atr*.2
        if side*num(h,'trend')<=.18 or side*(num(bars[-2],'close')-level)<=atr*.025 or not touch or side*(close-level)<=atr*.025 or abs(entry-level)>atr*.5:
            return False,'La ruptura necesita cierre y retest confirmados junto al nivel observado.'
        anchor=min(num(b,'low') for b in bars[-3:]) if side==1 else max(num(b,'high') for b in bars[-3:])
    elif key=='SWEEP_RECLAIM':
        swept=low<lo and close>lo+atr*.05 if side==1 else high>hi and close<hi-atr*.05
        if not swept or body<=atr*.2 or num(f,'volume_ratio')<.7:return False,'Falta un barrido recuperado con cuerpo y volumen suficientes.'
        anchor=low if side==1 else high
    else:
        adx=num(f,'adx',num(get(f,'extra',{}),'adx',99))
        rejection=low<=lo+atr*.1 and close>lo+atr*.2 if side==1 else high>=hi-atr*.1 and close<hi-atr*.2
        if adx>=18 or abs(num(h,'trend'))>.25 or body<=atr*.15 or not rejection:return False,'Falta rechazo confirmado de un rango lateral.'
        anchor=low if side==1 else high
    if side*(anchor-sl)<atr*spec['buffer_atr']-1e-8:return False,'El SL no deja el colchón de invalidación requerido por la variante.'
    return True,'Variante seleccionada: '+d['name']+'; condiciones verificadas sobre niveles técnicos originales.'
