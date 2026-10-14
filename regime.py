REGIMES=("TREND","RANGE","BREAKOUT","HIGH_VOL","LOW_VOL","NEWS_SHOCK","MEAN_REVERSION","LIQUIDITY_SWEEP")
import math
def _clamp(x,a=0.0,b=1.0): return max(a,min(b,float(x)))
"""Clasificación de régimen y regularización de muestras."""
import math
def regularize_metrics(metrics, min_samples=12, prior_win=.5, prior_payoff=1.0, prior_strength=6.0):
    """Shrink tiny samples toward neutral instead of overfitting 3-5 trades."""
    m=dict(metrics or {})
    n=max(0,int(m.get('samples',0) or 0)); w=n/(n+max(1.0,float(prior_strength)))
    wr=w*float(m.get('win_rate',prior_win))+(1-w)*prior_win
    payoff=w*float(m.get('payoff',prior_payoff) or prior_payoff)+(1-w)*prior_payoff
    avg_win=float(m.get('avg_win',0) or 0); avg_loss=float(m.get('avg_loss',0) or 0)
    ev=wr*avg_win-(1-wr)*avg_loss if (avg_win or avg_loss) else float(m.get('expectancy',0) or 0)*w
    m.update(raw_samples=n,regularized=True,usable=n>=int(min_samples),regularized_win_rate=wr,
             regularized_payoff=payoff,regularized_expectancy=ev,confidence=_clamp(n/max(float(min_samples),1.0)))
    return m

def classify_regime(frames, live=None, external=None):
    """Explicit 8-regime classifier from cached/local state. No network calls."""
    live=live or {}; external=external or {}
    m1=frames.get('M1'); m5=frames.get('M5'); m15=frames.get('M15'); h1=frames.get('H1')
    if not m1 or not m5:
        return {'regime':'LOW_VOL','confidence':0.0,'scores':{r:0.0 for r in REGIMES}}
    atr_ratio=float(m1.atr)/max(float(m5.atr),1e-9)
    fast=abs(float(live.get('fast_atr',0) or 0)); body=abs(float(live.get('body_atr',0) or 0))
    adx=float((m5.extra or {}).get('adx',0) or 0); bos=int((m1.extra or {}).get('bos',0) or 0); sweep=int((m1.extra or {}).get('sweep',0) or 0)
    aligned=[float(f.trend) for f in (m1,m5,m15,h1) if f is not None]
    trend_strength=abs(sum(aligned)/max(len(aligned),1)); disagreement=(max(aligned)-min(aligned)) if aligned else 0.0
    ext_news=float(external.get('news_shock',0) or 0); ext_vol=float(external.get('volatility',0) or 0)
    scores={r:0.0 for r in REGIMES}
    scores['TREND']=_clamp((trend_strength-.10)*2.5 + max(0,adx-16)/28)
    scores['RANGE']=_clamp((.20-trend_strength)*3.0 + max(0,18-adx)/22)
    scores['BREAKOUT']=_clamp(abs(bos)*.55 + fast*3.2 + body*2.0 + max(0,adx-20)/35)
    scores['HIGH_VOL']=_clamp(fast*3.5 + body*2.5 + atr_ratio*1.6 + ext_vol*.4)
    scores['LOW_VOL']=_clamp(.8-fast*3.0-body*2.0-max(0,adx-15)/35)
    scores['NEWS_SHOCK']=_clamp(ext_news + fast*2.2 + body*2.0)
    scores['MEAN_REVERSION']=_clamp(scores['RANGE']*.65 + disagreement*.65 + (1 if abs(float(m1.rsi)-50)>25 else 0)*.25)
    scores['LIQUIDITY_SWEEP']=_clamp(abs(sweep)*.65 + fast*2.0 + disagreement*.35)
    regime=max(scores,key=scores.get); ordered=sorted(scores.values(),reverse=True); confidence=_clamp((ordered[0]-(ordered[1] if len(ordered)>1 else 0))*1.8+.35)
    return {'regime':regime,'confidence':confidence,'scores':{k:round(v,3) for k,v in scores.items()},
            'trend_strength':round(trend_strength,3),'adx':round(adx,2)}
