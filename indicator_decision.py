"""Bounded, independent-family votes from completed MT5 bars.

The legacy geometry / MT5 safety gateway remains authoritative. These are
heuristics for ranking, not calibrated odds or permission to send an order.
"""
import math


def _number(data, key):
    value=data.get(key)
    if isinstance(value,bool):return None
    try:
        n=float(value)
        return n if math.isfinite(n) else None
    except (ValueError,TypeError):return None


def _direction(value,reference,band):
    if value is None or reference is None:return None
    return 1 if value>reference+band else -1 if value<reference-band else 0


def indicator_evidence(frames,side):
    """At most one vote per family, not one vote per correlated indicator."""
    f=frames.get('M15');h=frames.get('H1')
    if side not in (-1,1) or f is None or h is None or not f.bars or not h.bars:
        return {'status':'INSUFFICIENT_DATA','adjustment':0.0,'families':{}}
    if not all(math.isfinite(float(v)) for v in (f.atr,h.atr,f.bars[-1].close,h.bars[-1].close)) or f.atr<=0 or h.atr<=0:
        return {'status':'INSUFFICIENT_DATA','adjustment':0.0,'families':{}}
    # A single family is summarized from multiple indicators; extra votes in
    # Ichimoku/MA variants do not earn separate independent confirmations.
    families={}
    for name,frame in (('M15',f),('H1',h)):
        x=frame.extra or {};price=float(frame.bars[-1].close);atr=float(frame.atr)
        trend=[]
        for key in ('supertrend','hma20','ichimoku_kijun'):
            direct=_direction(price,_number(x,key),atr*.03)
            if direct is not None and direct!=0:trend.append(direct)
        dir_value=_number(x,'supertrend_direction')
        if dir_value in (-1,1):trend.append(int(dir_value))
        if trend:
            # H1 is the stronger independent horizon, but trend remains ONE family.
            families['trend_'+name]=round(sum(trend)/len(trend),3)
    x=f.extra or {};price=float(f.bars[-1].close)
    dm=_number(x,'demarker14')
    if dm is not None:
        families['momentum']=1 if dm>=60 else -1 if dm<=40 else 0
    cmf=_number(x,'cmf20')
    if cmf is not None:
        families['volume_tick_proxy']=1 if cmf>=.12 else -1 if cmf<=-.12 else 0
    fvg=_number(x,'fvg_last_three')
    if fvg is not None:families['structure']=int(max(-1,min(1,fvg)))
    if len(families)<3 or 'trend_H1' not in families:
        return {'status':'INSUFFICIENT_DATA','adjustment':0.0,'families':families}
    trend=.65*families['trend_H1']+.35*families.get('trend_M15',0)
    independent={'trend':trend,'momentum':families.get('momentum',0),
                 'volume_tick_proxy':families.get('volume_tick_proxy',0),
                 'structure':families.get('structure',0)}
    # One bounded adjustment per independent family. Max +/-2.4 score points.
    signed=sum(side*v for v in independent.values())/4.0
    adjustment=round(max(-2.4,min(2.4,2.4*signed)),3)
    return {'status':'RANKING_CONTEXT','adjustment':adjustment,'families':independent,
            'timeframes':['M15','H1'],'validated_probability':False,
            'source':'CLOSED_MT5_BARS','scope':'RANK_ONLY_NOT_ENTRY_AUTHORIZATION'}
