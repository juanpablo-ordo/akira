"""Describe actual inputs and their purpose, without inventing probabilities."""
from trade_review import finite
from datetime import datetime,timezone,timedelta

INDICATORS={
 'ema9':('EMA 9','Timing dentro de la tesis estructural'), 'ema21':('EMA 21','Tendencia inmediata'),
 'ema50':('EMA 50','Filtro de tendencia'), 'ema200':('EMA 200','Contexto de tendencia'),
 'rsi':('RSI','Momentum; extremos no implican giro automático'), 'macd':('MACD histograma','Impulso y divergencia'),
 'atr':('ATR','Escala de volatilidad, distancia estructural y protección'), 'adx':('ADX','Fuerza de tendencia'),
 'band_low':('Bollinger inferior','Extremo de distribución reciente'), 'band_high':('Bollinger superior','Extremo de distribución reciente'),
 'vwap':('VWAP','Referencia ponderada por volumen de ticks'), 'mfi':('MFI','Flujo aproximado con volumen del bróker'),
 'cci':('CCI','Desviación del precio típico'), 'roc':('ROC','Velocidad de cambio'),
 'stochastic':('Estocástico','Posición dentro del rango'), 'williams':('Williams %R','Posición relativa en rango'),
 'obv_slope':('OBV pendiente','Participación aproximada del volumen de ticks'),
 'bos':('BOS','Ruptura del rango previo por cierre'), 'sweep':('Barrido','Extremo roto con cierre de vuelta al rango'),
 'fib382':('Fibonacci 38.2','Nivel del rango de 50 velas'), 'fib50':('Fibonacci 50','Punto medio del rango de 50 velas'),
 'fib618':('Fibonacci 61.8','Nivel del rango de 50 velas'),
}

def indicator_rows(snapshot):
 out=[]
 for symbol,info in (snapshot.get('symbols') or {}).items():
  if (snapshot.get('markets') or {}).get(symbol,{}).get('scheduled_closed'):continue
  for tf,frame in (info.get('frames') or {}).items():
   for key,(name,purpose) in INDICATORS.items():
    value=finite(frame.get(key))
    out.append([symbol,tf,name,value,purpose if value is not None else 'Dato no disponible; no se contabiliza como confirmación',frame.get('last_bar')])
 return out

def number(value,digits=3):
 value=finite(value)
 return f'{value:,.{digits}f}'.rstrip('0').rstrip('.') if value is not None else 'sin dato'

def plan_explanation(plan):
 assessment=plan.get('assessment') or {}
 evidence=assessment.get('evidence') or [];warnings=assessment.get('warnings') or []
 parts=[str(value) for value in evidence[:4]+warnings[:3]]
 if parts:return '; '.join(parts)
 return str(plan.get('scenario_state') or 'La propuesta requiere confirmar estructura, precio, spread y capacidad de riesgo en MT5 antes de enviarse.')

def analysis_text(snapshot,symbol):
 info=(snapshot.get('symbols') or {}).get(symbol,{});market=(snapshot.get('markets') or {}).get(symbol,{})
 status=(snapshot.get('status') or {}).get(symbol,{})
 lines=[('ORO' if symbol.startswith('XAU') else 'BITCOIN')+' · '+symbol]
 if market.get('scheduled_closed'):
  return '\n'.join(lines+['MERCADO CERRADO · '+market.get('state',''), 'Próxima apertura estimada: '+market.get('next_open','Sin confirmar'),
   'Precios y análisis operativos suspendidos. Los tickets existentes conservan su reserva de riesgo.'])
 lines+=['ESTADO · '+str(status.get('state','Sin estado')),str(status.get('detail','')),'ESTRUCTURA E INDICADORES',
  'Tendencia: EMA y ADX. Impulso: RSI, MACD, ROC, CCI y osciladores.',
  'Volatilidad: ATR y Bollinger. Participación: VWAP, MFI y OBV con volumen de ticks del bróker.',
  'Niveles: rupturas por cierre, barridos y Fibonacci. Cada dato aporta contexto; varios indicadores correlacionados no son pruebas independientes.']
 for tf,f in (info.get('frames') or {}).items():
  trend=finite(f.get('trend'),0);direction='ALCISTA' if trend>.18 else 'BAJISTA' if trend<-.18 else 'MIXTA'
  lines.append(f'{tf} · {direction} · régimen {f.get("regime","sin dato")} · {f.get("bars","?")} velas cerradas')
  if finite(f.get('last_bar')):
   when=datetime.fromtimestamp(float(f['last_bar']),timezone(timedelta(hours=-6))).strftime('%d/%m/%Y %H:%M')
   lines.append('   Última vela cerrada: '+when+' · Guatemala')
  data=[name+': '+number(f.get(key)) for key,(name,_) in INDICATORS.items() if finite(f.get(key)) is not None]
  lines.extend('   '+' · '.join(data[i:i+4]) for i in range(0,len(data),4))
  missing=len(INDICATORS)-len(data)
  if missing:lines.append(f'   {missing} indicadores sin dato: no cuentan como confirmación.')
 analysis=(snapshot.get('analysis') or {}).get(symbol,{})
 fusion=(snapshot.get('research') or {}).get('fusion',{}).get(symbol,{})
 lines+=['DATOS QUE ENTRAN EN LA DECISIÓN',str(analysis.get('technical_detail','')), 'Fuentes con aporte actual: '+(', '.join(analysis.get('context_sources') or []) or 'Ninguna fuente externa vigente; análisis técnico MT5'),
  'Contexto agregado: '+str(fusion.get('label') or 'Sin contexto externo utilizable'), 'PENDIENTES Y MATEMÁTICAS']
 for p in (info.get('scenario_book') or []):
  side='BUY' if p.get('side') in (1,'BUY') else 'SELL';a=p.get('assessment') or {}
  lines.append(f'{side} {p.get("kind","")} · Entrada {number(p.get("entry"))} · SL {number(p.get("sl"))} · TP {number(p.get("tp"))} · R:R {number(a.get("rr",p.get("rr")),2)} · riesgo {number(p.get("risk_usd"),2)} USD')
  lines.append('   '+plan_explanation(p))
 research=snapshot.get('research') or {}
 lines+=['FUENTES Y VIGENCIA']
 for name,state in (research.get('sources') or {}).items():
  if symbol.startswith('XAU') and (name.startswith('venue:') or name.startswith('derivatives:BTC')):continue
  lines.append('  '+name+' · '+('APORTE DISPONIBLE' if state.get('fresh') and not state.get('error') else 'SIN APORTE')+' · edad '+str(state.get('age_seconds','sin dato'))+' s'+(' · '+str(state['error']) if state.get('error') else ''))
 if symbol.startswith('BTC'):
  for name,row in (research.get('global_markets') or {}).items():
   lines.append(f'  {name} · {row.get("quote")} · bid {row.get("bid")} / ask {row.get("ask")} · libro {row.get("imbalance")} · funding {row.get("funding","sin dato")} · OI USD {row.get("open_interest_usd","sin dato")}')
 for row in (research.get('macro') or {}).get('rows',[]):lines.append('  '+row['name']+' · '+str(row['value'])+' · '+row['date']+' · '+row['frequency'])
 lines.extend('  '+name+' · '+row['state'] for name,row in (research.get('reference_sources') or {}).items())
 runner=info.get('runner') or {}
 lines+=['RUNNERS · '+str(runner.get('state','Sin estado')),str(runner.get('detail','')),
  'GESTIÓN · Invalidación estructural, volatilidad, SL/TP y límites de riesgo. Sin scalping.',
  'CALIDAD · Estrellas y cercanía son índices técnicos. Resultados de la cuenta y comparaciones se miden por separado.']
 return '\n'.join(lines)
