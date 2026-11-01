"""Read-only closed-session planning from observed, closed MT5 bars.

Plans describe conditions to reassess at reopening. They are never executable
orders and cannot be passed off as a neural approval or a current quote.
"""
from datetime import datetime, timedelta, timezone
import hashlib,json,math
from market_state import MarketDataFreshnessValidator,PERIOD_SECONDS,value


def build_preopen_plan(symbol,frames,now,config,market,events=(),positions=()):
    evidence={};missing=[]
    for tf in ('H1','H4','D1'):
        f=frames.get(tf)
        health=MarketDataFreshnessValidator.inspect(symbol,tf,f,now,config)
        bars=[b for b in value(f,'bars',()) if float(value(b,'time',0))+PERIOD_SECONDS[tf]<=now]
        if not health['ready'] or not bars:missing.append(tf)
        if bars:
            evidence[tf]={'last_open_utc':value(bars[-1],'time'),'trend':value(f,'trend'),
                          'atr':value(f,'atr'),'rsi':value(f,'rsi'),'health':health['state']}
    h1=frames.get('H1');bars=[b for b in value(h1,'bars',()) if value(b,'time',0)+3600<=now]
    weekly={};scenarios=[]
    if bars:
        last=datetime.fromtimestamp(bars[-1].time,timezone.utc)
        monday=(last-timedelta(days=last.weekday())).replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
        week=[b for b in bars if b.time>=monday]
        prices=[v for b in week for v in (b.open,b.high,b.low,b.close)]
        if week and all(math.isfinite(v) and v>0 for v in prices):
            high=max(b.high for b in week);low=min(b.low for b in week)
            weekly={'from_utc':week[0].time,'through_utc':week[-1].time+3600,
                'open':week[0].open,'high':high,'low':low,'close':week[-1].close,
                'change_pct':round((week[-1].close/week[0].open-1)*100,3),
                'closed_h1_bars':len(week),'observed_days':len({datetime.fromtimestamp(b.time,timezone.utc).date() for b in week}),
                'coverage':'Historial recibido de MT5; no se inventan velas faltantes'}
            if len(week)<24:missing.append('HISTORIAL_SEMANAL_INCOMPLETO')
            # These are observed structural references, never an invented SL/TP.
            scenarios=[
                {'side':'BUY','reference':high,'condition':'Ruptura y retesteo confirmados de la resistencia observada, con estructura H1/H4 favorable.',
                 'invalidation':'Rechazo de la ruptura o pérdida del soporte que origine la nueva entrada.'},
                {'side':'SELL','reference':low,'condition':'Pérdida y retesteo confirmados del soporte observado, con estructura H1/H4 favorable.',
                 'invalidation':'Recuperación del soporte o ruptura de la resistencia que origine la nueva entrada.'},
                {'side':'WAIT','condition':'Sin confirmación estructural, con gap que invalida el plan, spread excesivo o presupuesto insuficiente.'}]
    retained=[{k:e.get(k) for k in ('id','title','url','published_utc','verification','category')}
              for e in events if symbol in e.get('symbols',[]) and 0<=now-float(e.get('published_utc',0))<=7*86400][:8]
    active=[{'ticket':int(value(p,'ticket',0)),'side':'BUY' if value(p,'type')==0 else 'SELL',
             'entry':value(p,'price_open'),'sl':value(p,'sl'),'tp':value(p,'tp'),
             'management':'SL/TP conservados en el bróker; gestión dinámica pendiente de sesión y tick válidos.'}
            for p in positions if value(p,'symbol')==symbol]
    payload={'symbol':symbol,'evidence':evidence,'weekly':weekly,'events':retained,'positions':active}
    revision=hashlib.sha256(json.dumps(payload,sort_keys=True,default=str).encode()).hexdigest()
    return {**payload,'revision':revision,'prepared_at':now,'session':market.get('session'),
        'state':'PREPARED' if not missing else 'WAITING_HISTORY','missing':missing,
        'next_open':market.get('next_open',''),'scenarios':scenarios,
        'execution_allowed':False,'requires_revalidation':True,
        'reopening_checks':['Tick y sesión MT5 vigentes','Gap respecto del último cierre y spread actual',
                            'Estructura H1/H4/D1 actualizada','Posiciones, costes y riesgo efectivo',
                            'Nueva revisión IA de Entry/SL/TP/volumen exactos'],
        'detail':('Plan condicional preparado con el historial recibido; se revalidará al abrir.' if not missing
                  else 'Preparando reapertura; falta historial válido: '+', '.join(missing)+'.')}


def preopen_text(plan):
    if not plan:return ''
    lines=[plan.get('detail','')]
    week=plan.get('weekly') or {}
    if week:
        lines.append('Semana observada: máximo '+str(round(week['high'],4))+' · mínimo '+str(round(week['low'],4))+
                     ' · cierre '+str(round(week['close'],4))+' · cambio '+str(week['change_pct'])+'%.')
    for row in plan.get('scenarios',[]):
        lines.append(row['side']+(' · referencia '+str(round(row['reference'],4)) if 'reference' in row else '')+': '+row['condition'])
    if plan.get('positions'):lines.append(str(len(plan['positions']))+' posición(es) conservada(s); SL/TP siguen en MT5.')
    if plan.get('events'):lines.append('Contexto fechado: '+'; '.join(e['title'] for e in plan['events'][:3]))
    neural=(plan.get('neural_review') or {}).get(plan.get('symbol'),{})
    if neural:lines.append('Revisión IA del historial: '+str(neural.get('thesis') or '')+' '+str(neural.get('note') or ''))
    lines.append('Reapertura: comprobar tick, gap, spread, estructura, riesgo y revisión IA antes de enviar.')
    return '\n'.join(lines)
