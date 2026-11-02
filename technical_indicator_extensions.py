"""Closed-bar, auditable indicator extensions.

All returned values are CONTEXT ONLY. No entry/stop is approved because a
new indicator exists. Avoid double counting correlated indicator families.
Tick volume is not exchange-traded volume in XAUUSDm CFDs.
"""
from __future__ import annotations
import math


def sma(values,n):
    return sum(values[-n:])/n if len(values)>=n and n>0 else None


def wma(values,n):
    if n<=0 or len(values)<n:return None
    data=values[-n:];return sum((i+1)*v for i,v in enumerate(data))/(n*(n+1)/2)


def hma(values,n):
    """Hull MA with an explicit finite history; uses no future candles."""
    if n<2 or len(values)<n+int(math.sqrt(n)):return None
    half=n//2;root=max(1,int(math.sqrt(n)))
    raw=[2*wma(values[:i+1],half)-wma(values[:i+1],n)
         for i in range(n-1,len(values))]
    return wma(raw,root)


def _ema(values,n):
    if not values:return None
    alpha=2/(n+1);v=float(values[0])
    for x in values[1:]:v=alpha*x+(1-alpha)*v
    return v


def _channel(bars,n):
    if len(bars)<n:return None
    sample=bars[-n:]
    return max(b.high for b in sample),min(b.low for b in sample)


def _psar(bars):
    if len(bars)<4:return None
    long=bars[1].close>=bars[0].close
    sar=float(bars[0].low if long else bars[0].high)
    extreme=float(bars[0].high if long else bars[0].low);af=.02
    for i in range(1,len(bars)):
        b=bars[i]
        sar=sar+af*(extreme-sar)
        if long:
            sar=min(sar,bars[i-1].low,bars[i-2].low if i>1 else bars[i-1].low)
            if b.low<sar:
                long=False;sar=extreme;extreme=b.low;af=.02
            elif b.high>extreme:
                extreme=b.high;af=min(.2,af+.02)
        else:
            sar=max(sar,bars[i-1].high,bars[i-2].high if i>1 else bars[i-1].high)
            if b.high>sar:
                long=True;sar=extreme;extreme=b.high;af=.02
            elif b.low<extreme:
                extreme=b.low;af=min(.2,af+.02)
    return sar


def _last_confirmed_pivot(bars,span=3):
    # Never use an unconfirmed newest candle as a swing pivot.
    for i in range(len(bars)-span-1,span-1,-1):
        sl=bars[i-span:i+span+1]
        if bars[i].high>max(x.high for j,x in enumerate(sl) if j!=span):
            return bars[i].high
        if bars[i].low<min(x.low for j,x in enumerate(sl) if j!=span):
            return bars[i].low
    return None


def _supertrend(bars,period=14,multiplier=3):
    if len(bars)<period+2:return None
    ranges=[max(b.high-b.low,abs(b.high-bars[i-1].close),abs(b.low-bars[i-1].close))
            for i,b in enumerate(bars) if i>0]
    atr=sum(ranges[:period])/period
    upper=lower=0.0;direction=1;st=0.0
    for i in range(period,len(bars)):
        atr=(atr*(period-1)+ranges[i-1])/period
        mid=(bars[i].high+bars[i].low)/2
        next_upper=mid+multiplier*atr;next_lower=mid-multiplier*atr
        if i>period:
            next_upper=min(next_upper,upper) if bars[i-1].close<=upper else next_upper
            next_lower=max(next_lower,lower) if bars[i-1].close>=lower else next_lower
            if direction==1 and bars[i].close<lower:direction=-1
            elif direction==-1 and bars[i].close>upper:direction=1
        upper,lower=next_upper,next_lower
        st=lower if direction==1 else upper
    return st,direction


def context_indicators(bars,atr):
    bars=list(bars)
    if len(bars)<60:return {}
    close=[float(b.close) for b in bars]
    if not all(math.isfinite(float(x)) for b in bars for x in
               (b.open,b.high,b.low,b.close,b.volume)):return {}
    if any(b.high<b.low or b.volume<0 for b in bars):return {}
    high20,low20=_channel(bars,20)
    high22,low22=_channel(bars,22)
    high52,low52=_channel(bars,52)
    high9,low9=_channel(bars,9)
    high26,low26=_channel(bars,26)
    high14,low14=_channel(bars,14)
    midpoint=lambda high,low:(high+low)/2
    prev=bars[-2];last=bars[-1]
    pivot=(prev.high+prev.low+prev.close)/3
    moneys=[]
    ad=0.0
    for b in bars:
        mf=((b.close-b.low)-(b.high-b.close))/max(b.high-b.low,1e-12)
        value=mf*max(0,b.volume)
        ad+=value;moneys.append(value)
    flow20=sum(moneys[-20:])
    sumvolume=sum(b.volume for b in bars[-20:])
    deup=sum(max(0,bars[i].high-bars[i-1].high) for i in range(len(bars)-14,len(bars)))
    dedown=sum(max(0,bars[i-1].low-bars[i].low) for i in range(len(bars)-14,len(bars)))
    demarker=100*deup/max(deup+dedown,1e-10)
    midpoint20=midpoint(high20,low20)
    # Profile peak is an occupancy proxy on broker tick volume, not DOM/liquidations.
    width=max((max(b.high for b in bars[-80:])-min(b.low for b in bars[-80:]))/16,1e-10)
    origin=min(b.low for b in bars[-80:])
    profile=[0.0]*16
    for b in bars[-80:]:
        idx=min(15,max(0,int((b.close-origin)/width)))
        profile[idx]+=float(b.volume)
    poc=origin+(profile.index(max(profile))+.5)*width
    fvg_up=bars[-3].high<bars[-1].low
    fvg_down=bars[-3].low>bars[-1].high
    st=_supertrend(bars[-120:])
    lastpivot=_last_confirmed_pivot(bars)
    return {
        'sma20':sma(close,20),'wma20':wma(close,20),'hma20':hma(close,20),
        'ichimoku_tenkan':midpoint(high9,low9),'ichimoku_kijun':midpoint(high26,low26),
        'ichimoku_span_a_current':(midpoint(high9,low9)+midpoint(high26,low26))/2,
        'ichimoku_span_b_current':midpoint(high52,low52),
        'parabolic_sar':_psar(bars[-120:]),
        'supertrend':st[0] if st else None,'supertrend_direction':st[1] if st else None,
        'zigzag_last_confirmed':lastpivot,
        'donchian_high20':high20,'donchian_low20':low20,
        'keltner_upper':_ema(close[-80:],20)+2*atr,
        'keltner_lower':_ema(close[-80:],20)-2*atr,
        'chandelier_buy_stop':high22-3*atr,'chandelier_sell_stop':low22+3*atr,
        'cmf20':flow20/max(sumvolume,1e-10),'accumulation_distribution':ad,
        'demarker14':demarker,'pivot_pp_previous':pivot,
        'pivot_r1_previous':2*pivot-prev.low,'pivot_s1_previous':2*pivot-prev.high,
        'pivot_fib_r1_previous':pivot+.382*(prev.high-prev.low),
        'pivot_fib_s1_previous':pivot-.382*(prev.high-prev.low),
        'fibonacci_extension_1272':low20+1.272*(high20-low20),
        'fvg_last_three':1 if fvg_up else -1 if fvg_down else 0,
        'volume_profile_poc_estimated':poc,
    }


def indicator_provenance():
    return {'families':{
        'trend':['sma20','wma20','hma20','ichimoku_tenkan','ichimoku_kijun','parabolic_sar','supertrend','zigzag_last_confirmed'],
        'momentum':['demarker14'],
        'volatility':['donchian_high20','donchian_low20','keltner_upper','keltner_lower','chandelier_buy_stop','chandelier_sell_stop'],
        'volume_tick_proxy':['cmf20','accumulation_distribution','volume_profile_poc_estimated'],
        'structure':['pivot_pp_previous','pivot_r1_previous','pivot_s1_previous','pivot_fib_r1_previous','pivot_fib_s1_previous','fibonacci_extension_1272','fvg_last_three']},
        'decision_use':'BOUNDED_INDEPENDENT_FAMILY_RANKING',
        'independent_confirmation':False,
        'decision_module':'indicator_decision.indicator_evidence',
        'maximum_score_adjustment':2.4,
        'entry_authorization':False,
        'price_data':'CLOSED_MT5_BARS',
        'volume_data':'BROKER_TICK_VOLUME_NOT_EXCHANGE_VOLUME'}
