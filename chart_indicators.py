"""Compute chart series with the same closed-bar functions used by the engine."""
import math
from strategy import ema_series,frame,Bar

OPTIONS=('Precio','Medias y Bollinger','RSI','MACD','ADX','Volumen y estructura')

def indicator_chart(raw,tf='M15'):
    bars=tuple(Bar(**{k:b[k] for k in ('time','open','high','low','close','volume')}) for b in raw)
    if len(bars)<60:return {'series':{},'detail':'Se necesitan 60 velas cerradas; no se inventan indicadores.'}
    close=[b.close for b in bars];series={}
    for period in (9,21,50,200):series['EMA '+str(period)]=ema_series(close,period)
    series['Bollinger inferior']=[None]*len(bars);series['Bollinger superior']=[None]*len(bars)
    series['RSI']=[None]*len(bars);series['MACD']=[None]*len(bars);series['ADX']=[None]*len(bars)
    final=None
    for n in range(60,len(bars)+1):
        f=frame(tf,bars[:n]);final=f
        for key,value in [('Bollinger inferior',f.band_low),('Bollinger superior',f.band_high),('RSI',f.rsi),('MACD',f.macd_hist),('ADX',f.extra['adx'])]:series[key][n-1]=value
    return {'series':series,'lows':list(final.lows),'highs':list(final.highs),'atr':final.atr,
      'parameters':'EMA 9/21/50/200; Bollinger 20×2; RSI Wilder 14; MACD 12/26/9; ADX 14.',
      'detail':'Calculado con las funciones del motor y las velas cerradas publicadas. La curva usa una ventana limitada; el valor exacto que decidió el motor se muestra aparte.'}

def finite_series(rows):return [x for x in rows if x is not None and math.isfinite(x)]
