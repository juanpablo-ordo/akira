"""Deterministic, closed-bar market-regime descriptor for AKIRA Adaptive.

A regime label proposes hypotheses for prospective tests; it is NOT evidence of
strategy profitability or approval to bypass the usual admission/AI/risk gate.
"""
import math


def _finite(frame,key,default=None):
    value=(frame.extra or {}).get(key,default) if key not in ('trend','atr','regime') else getattr(frame,key,default)
    try:
        value=float(value)
        return value if math.isfinite(value) else None
    except (ValueError,TypeError):return None


def classify_regime(frames,market=None):
    session=str((market or {}).get('session') or '').upper()
    if session in ('CLOSED','CLOSE_ONLY'):
        return {'regime':'SESSION_CLOSED','candidates':['MAINTAIN_OR_REASSESS_EXISTING'],
                'can_authorize_entry':False,'validation':'BROKER_SESSION_ONLY'}
    f=frames.get('M15');h=frames.get('H1')
    if f is None or h is None or len(f.bars)<20 or len(h.bars)<20:
        return {'regime':'INSUFFICIENT_DATA','candidates':[],
                'can_authorize_entry':False,'validation':'CLOSED_BAR_REQUIREMENTS'}
    mtrend=_finite(f,'trend');htrend=_finite(h,'trend');atr=_finite(f,'atr')
    if None in (mtrend,htrend,atr) or atr<=0:
        return {'regime':'INSUFFICIENT_DATA','candidates':[],
                'can_authorize_entry':False,'validation':'NONFINITE_OR_MISSING'}
    last=f.bars[-1];prev=f.bars[-2]
    if not all(math.isfinite(float(x)) for x in (last.open,last.close,last.high,last.low)):
        return {'regime':'INSUFFICIENT_DATA','candidates':[],
                'can_authorize_entry':False,'validation':'NONFINITE_BAR'}
    volume=_finite(f,'volume_ratio',1.0)
    bos=_finite(f,'bos',0.0)
    sweep=_finite(f,'sweep',0.0)
    if last.high-last.low>=1.8*atr and (volume or 0)>=1.25:
        regime='VOLATILE_EXPANSION';candidates=['BREAKOUT_RETEST','WAIT_COOLDOWN']
    elif bos and htrend*bos<-.25 and mtrend*bos>.12 and last.close!=prev.close:
        regime='CONFIRMED_REVERSAL_CANDIDATE';candidates=['SWEEP_ABSORPTION','RETEST']
    elif mtrend*htrend>.08 and abs(mtrend)>=.28 and abs(htrend)>=.28:
        regime='TREND_UP' if mtrend>0 else 'TREND_DOWN'
        candidates=['CONTINUATION','PULLBACK','BREAKOUT_RETEST']
    else:
        regime='RANGE';candidates=['SWEEP_ABSORPTION','CONFIRMED_RETEST','WAIT']
    return {'regime':regime,'candidates':candidates,
            'can_authorize_entry':False,
            'validation':'DESCRIPTIVE_CLOSED_BAR_ONLY',
            'last_m15_closed_at':last.time,'last_h1_closed_at':h.bars[-1].time,
            'family_weights':'Trend/momentum/volume/structure each contribute at most one independent family.',
            'profitability_claim':'NONE'}
