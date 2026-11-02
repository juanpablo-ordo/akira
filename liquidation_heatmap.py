"""Reproducible ESTIMATED liquidity bands from closed MT5 candle/tick volume.

This is NOT an observed exchange liquidation heatmap. No external liquidations,
funding, global XAU futures positioning, or order-book depth is inferred.
Execution gates must never treat these estimates as independent trade evidence.
"""
from __future__ import annotations

import math


def estimate_bands(symbol, frames, now, bins=16):
    frame=frames.get('M15') or frames.get('H1')
    result={'symbol':symbol,'kind':'ESTIMATED_PRICE_VOLUME',
            'observed_liquidations':False,'trade_confirmation':False,
            'source':'MT5 closed bars and broker tick volume',
            'generated_at_utc':float(now),'bands':[],
            'status':'INSUFFICIENT_DATA',
            'limitations':'A proxy of price concentration, not real liquidations or stop orders.'}
    if frame is None:return result
    bars=list(frame.bars)[-96:]
    if len(bars)<24:return result
    if not all(math.isfinite(float(v)) for b in bars for v in (b.open,b.high,b.low,b.close,b.volume)):
        return result
    low=min(b.low for b in bars);high=max(b.high for b in bars)
    if not high>low:return result
    count=min(32,max(8,int(bins)))
    step=(high-low)/count
    prior=[0.0]*count;recent=[0.0]*count
    cutoff=len(bars)//2
    for i,b in enumerate(bars):
        if b.high<b.low or b.volume<0:return result
        # Price-time occupancy with tick-volume weighting; not order-book depth.
        hits=[j for j in range(count) if low+(j+1)*step>b.low and low+j*step<b.high]
        if not hits:continue
        share=float(b.volume)/len(hits)
        target=prior if i<cutoff else recent
        for j in hits:target[j]+=share
    peak=max([*prior,*recent,1e-12])
    result['status']='ESTIMATED'
    result['last_closed_bar_utc']=int(bars[-1].time)
    result['timeframe']=getattr(frame,'name','M15')
    result['bars_used']=len(bars)
    result['price_min']=round(low,5);result['price_max']=round(high,5)
    result['intensity_scale']='Relative 0-100 within this snapshot, independently normalized over one shared maximum'
    result['coverage']='Broker-derived price/tick-volume occupancy; no exchange liquidation coverage'
    result['bands']=[{
        'low':round(low+j*step,5),'high':round(low+(j+1)*step,5),
        'historical_intensity':round(100*prior[j]/peak,1),
        'current_intensity':round(100*recent[j]/peak,1),
        'change':round(100*(recent[j]-prior[j])/peak,1)}
        for j in range(count)]
    return result


def heatmap_is_execution_evidence(heatmap):
    """Estimation never supplies an entry approval or broker-order verdict."""
    return False
