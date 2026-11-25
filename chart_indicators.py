"""Compute chart series with the same closed-bar functions used by the engine."""
import math
from strategy import ema_series,frame,Bar

OPTIONS=('Precio','Medias y Bollinger','RSI','MACD','ADX','Volumen y estructura')

def indicator_description(key):
    """Explain only indicators or measurements actually supplied by the engine."""
    if key.startswith('ema') and key[3:].isdigit():
        return f'Media exponencial de {key[3:]} velas para seguir la dirección del precio.'
    if key.startswith('fib'):
        return 'Nivel de retroceso medido sobre el último tramo analizado.'
    return {
        'rsi':'Momento relativo entre subidas y bajadas.',
        'macd':'Histograma de impulso entre medias rápidas y lentas.',
        'adx':'Fuerza de la tendencia, independientemente de su dirección.',
        'atr':'Rango medio de las velas; mide volatilidad.',
        'stochastic':'Posición del cierre dentro del rango reciente.',
        'williams':'Posición relativa del cierre en el rango reciente.',
        'cci':'Distancia del precio típico respecto a su media.',
        'mfi':'Presión de compra y venta ponderada por volumen.',
        'roc':'Variación del precio respecto a velas anteriores.',
        'obv_slope':'Dirección del volumen acumulado según los cambios de cierre.',
        'volume_ratio':'Actividad de la vela respecto a su media reciente.',
        'vwap':'Precio medio ponderado por volumen.',
        'bos':'Ruptura de la estructura observada.',
        'sweep':'Barrido de un nivel previo con reacción posterior.',
        'donchian_high20':'Máximo de la ventana de 20 velas.',
        'donchian_low20':'Mínimo de la ventana de 20 velas.',
        'volume_profile_poc_estimated':'Zona de mayor actividad estimada; no es volumen ejecutado por nivel.',
    }.get(key,'')

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


def price_overlays(rows, frame_values):
    """Price curves use the published closed bars. The final markers use actor values."""
    closes=[float(bar['close']) for bar in rows if bar.get('closed',True)]
    if len(closes)<21:return {}
    curves={}
    for period in (9,21,50,200):
        if len(closes)<period:continue
        value=frame_values.get('ema'+str(period))
        if not isinstance(value,(int,float)) or not math.isfinite(value):continue
        curve=list(ema_series(closes,period))
        curve[-1]=float(value)
        curves['EMA '+str(period)]=curve
    return curves


def order_levels(info, orders, symbol):
    levels={}
    for row in orders:
        if row.get('symbol')!=symbol:continue
        ticket=row.get('ticket')
        for field,label in (('entry','Entrada'),('sl','SL'),('tp','TP')):
            value=row.get(field,row.get('price_open') if field=='entry' else None)
            if isinstance(value,(int,float)) and math.isfinite(value) and value>0:
                levels[f'MT5 #{ticket} · {label}']=value
    requests=info.get('transition_request') or {}
    for field,label in (('price','Entrada'),('sl','SL'),('tp','TP')):
        value=requests.get(field)
        if isinstance(value,(int,float)) and math.isfinite(value) and value>0:
            levels[f'Solicitud sin confirmar · {label}']=value
    for row in (info.get('scenario_book') or ()):
        if row.get('ticket') or len(levels)>=28:continue
        entry=row.get('entry');direction='Compra' if row.get('side') in (1,'BUY') else 'Venta'
        if isinstance(entry,(int,float)) and math.isfinite(entry) and entry>0:
            levels[f"Propuesta {direction} {row.get('kind','')} · {entry:g}"]=entry
    return levels
