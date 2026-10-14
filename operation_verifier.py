"""Truthful validation stages from actual published inputs and Gateway receipts."""
import math

def usable(value):
    try:return math.isfinite(float(value))
    except (ValueError,TypeError,OverflowError):return False

def verification(snapshot,symbol):
    info=(snapshot.get('symbols') or {}).get(symbol,{})
    frames=info.get('frames') or {};sources=(snapshot.get('research') or {}).get('sources') or {}
    stages=[]
    def add(name,state,detail,critical=False):stages.append({'name':name,'state':state,'detail':str(detail),'critical':critical})
    market=(snapshot.get('markets') or {}).get(symbol,{})
    stamp=float(snapshot.get('updated') or snapshot.get('as_of_utc') or 0)
    age=stamp-float(info.get('quote_time') or stamp)
    max_age=float((snapshot.get('data_limits') or {}).get('max_tick_age_seconds',10))
    fresh_quote=usable(info.get('bid')) and usable(info.get('ask')) and float(info.get('bid') or 0)>0 and float(info.get('ask') or 0)>=float(info.get('bid') or 0) and -5<=age<=max_age
    old_ui=float(snapshot.get('ui_age_seconds') or 0)>3
    quote_state='PAUSA' if market.get('scheduled_closed') else 'DESACTUALIZADA' if old_ui or not -5<=age<=max_age else 'DISPONIBLE' if fresh_quote else 'SIN DATO'
    add('Cotización y sesión',quote_state,market.get('state','MT5')+f'; edad del tick {max(0,age):.1f} s. Precio y sesión se comprueban otra vez antes del envío.',True)
    structural=all(frames.get(tf) and usable(frames[tf].get('atr')) and float(frames[tf]['atr'])>0
        and usable(frames[tf].get('last_bar')) and 0<=stamp-float(frames[tf]['last_bar'])<=max_age
        for tf,max_age in (('M15',1800),('H1',7200)))
    add('Estructura multitemporal','DISPONIBLE' if structural else 'INCOMPLETA',', '.join(frames) or 'No hay temporalidades cerradas',True)
    f=frames.get('M15',{});keys=('rsi','macd','adx','ema9','ema21','atr')
    valid=[key for key in keys if usable(f.get(key))]
    add('Indicadores técnicos','DISPONIBLE' if len(valid)==len(keys) else 'INCOMPLETA','M15: '+', '.join(valid))
    add('Liquidez y volumen','DISPONIBLE' if usable(f.get('volume_ratio')) else 'SIN DATO','Volumen de ticks MT5; libro de mercado solo cuando el broker lo proporciona.')
    groups=[('Noticias macroeconómicas',('news','fed','macro:','global_news:','search:')),
      ('Análisis externos y YouTube',('technical:','youtube','local_ai','model')),
      ('Exchanges y derivados',('venue:','derivatives:','coinglass:'))]
    for label,prefixes in groups:
        def relevant(k):
            if symbol.startswith('XAU') and (k.startswith(('venue:','derivatives:')) or ':BTC' in k):return False
            if symbol.startswith('BTC') and (':XAU' in k or ':GOLD' in k.upper()):return False
            return True
        rows=[(k,v) for k,v in sources.items() if isinstance(v,dict) and k.startswith(prefixes) and relevant(k)]
        fresh=[k for k,v in rows if v.get('fresh') and v.get('usable',True) and v.get('enabled') is not False and not v.get('error')]
        pending=[k for k,v in rows if v.get('inflight')]
        add(label,'DISPONIBLE' if fresh else 'EN CONSULTA' if pending else 'SIN APORTE','Vigentes: '+(', '.join(fresh) or 'ninguna')+'; una fuente sin aporte no cuenta como confirmación.')
    add('Volatilidad','DISPONIBLE' if usable(f.get('atr')) and float(f.get('atr') or 0)>0 else 'SIN DATO','ATR M15: '+str(f.get('atr','sin dato')))
    receipts=[r for r in (snapshot.get('verification_receipts') or {}).values() if r.get('symbol')==symbol]
    receipt=max(receipts,key=lambda r:r.get('at',0),default={})
    receipt_fresh=bool(receipt and -5<=stamp-float(receipt.get('at') or 0)<=30)
    ledger=snapshot.get('portfolio_risk') or {};risk_block=''
    if ledger and (not ledger.get('risk_known',True) or float(ledger.get('reserved_usd',0))>float(ledger.get('cap_usd',0))+.01):
        from risk_reservations import reservation_reason
        risk_block=reservation_reason(ledger)
    risk_state='BLOQUEADO' if risk_block else 'CALCULADO' if receipt_fresh and receipt.get('risk_passed') else 'RECHAZADO' if receipt_fresh and receipt.get('error') else 'RESERVA CALCULADA' if ledger.get('risk_known') else 'PENDIENTE'
    risk_detail='Gateway calcula la reserva del libro y vuelve a evaluar cada nuevo candidato antes del envío.'
    if receipt_fresh:risk_detail=receipt.get('error') or ('Riesgo '+str(receipt.get('risk_usd'))+'; margen '+str(receipt.get('margin'))+'; lote '+str(receipt.get('volume')))
    add('Riesgo, lote y margen',risk_state,risk_block or risk_detail,True)
    live=[o for o in snapshot.get('orders',[]) if o.get('symbol')==symbol and o.get('owned')]
    add('Restricciones MT5 / Exness','COMPROBADO' if receipt_fresh and receipt.get('broker_checked') else 'CONFIRMADO MT5' if live else 'PENDIENTE','order_check real para el candidato; se repite antes del envío' if receipt_fresh and receipt.get('broker_checked') else str(len(live))+' pendiente(s) visibles en MT5; las nuevas propuestas aún necesitan order_check.' if live else 'Sin order_check vigente para el candidato; no se presenta como aprobado.',True)
    study=snapshot.get('quality_study') or {};stats={}
    from selection_trials import cell
    import hashlib,json
    fingerprint=hashlib.sha256(json.dumps(snapshot.get('selection_configuration') or {},sort_keys=True,default=str).encode()).hexdigest()[:16]
    for cohort,models in study.get('validated_probabilities',{}).items():
        if not cohort.startswith(symbol+' / ') or not cohort.endswith(' / '+fingerprint) or (' / '+str(snapshot.get('build'))+' / ') not in cohort:continue
        from quality_study import QualityStudy
        if (' / '+str(QualityStudy.provider(snapshot))+' / ') not in cohort:continue
        candidates=[p for p in info.get('scenario_book',[]) if p.get('quality_score') is not None]
        if not candidates:continue
        p=max(candidates,key=lambda p:float(p['quality_score']));key=cell(p)
        stats={name:models[target]['bins'][key] for name,target in [('activation','activation'),('favorable','favorable_given_activation')] if target in models and key in models[target]['bins']}
        stats['validated']=bool(stats)
    add('Estudio estadístico','VALIDADO' if stats.get('validated') else 'EN ESTUDIO','Modelo de replay fuera de muestra del mismo proveedor y configuración: '+str(stats)+'. Costes aportados, muestreo de 30 s y parámetros congelados; no probabilidad de ganancia en la cuenta.' if stats.get('validated') else 'Se necesitan resultados prospectivos con costes y muestra suficiente. Ninguna estrella se convierte en probabilidad.')
    add('Pendientes y continuación','CONFIRMADO MT5' if any(p.get('confirmed') for p in info.get('scenario_book',[])) else 'MAPA TÉCNICO',(snapshot.get('status') or {}).get(symbol,{}).get('detail','Sin confirmación de ejecución'))
    complete_states=('DISPONIBLE','CALCULADO','COMPROBADO','VALIDADO','CONFIRMADO MT5','RESERVA CALCULADA')
    completed=sum(r['state'] in complete_states for r in stages)
    state='MERCADO CERRADO' if market.get('scheduled_closed') else 'SIN ACTUALIZACIÓN DEL MOTOR' if old_ui else 'CALCULANDO VELAS' if info.get('analysis_inflight') else 'REVISIÓN ACTIVA' if structural else 'PREPARANDO DATOS'
    missing=[r['name']+' · '+r['state'] for r in stages if r['state'] not in complete_states]
    return {'symbol':symbol,'stages':stages,'completed':completed,'total':len(stages),'progress':100*completed/len(stages),
      'activity':state,'cycle':snapshot.get('cycle'),'updated':stamp,'cycle_ms':snapshot.get('cycle_ms'),
      'missing':missing,'execution_block':risk_block or snapshot.get('execution_block') or '',
      'confirmed_orders':len(live),'scope_version':2,
      'risk_receipt':receipt,'activation_estimate':stats.get('activation') if stats.get('validated') else None,
      'favorable_estimate':stats.get('favorable') if stats.get('validated') else None,
      'scope':'La barra muestra cobertura de datos, no una descarga ni un porcentaje de ganancia. Puede permanecer en el mismo valor mientras el ciclo sigue revisando. Las fuentes opcionales ausentes no detienen el mapa técnico; el riesgo y order_check sí condicionan el envío.'}

def verification_text(snapshot,symbol):
    row=verification(snapshot,symbol)
    return '\n'.join([symbol+' · '+row['activity']+' · ciclo '+str(row['cycle']),
        'COBERTURA DE DATOS '+str(row['completed'])+'/'+str(row['total']),
        'Nuevas entradas: '+(row['execution_block'] or 'Sin bloqueo conjunto identificado; cada candidato debe cumplir sus propios filtros.')]+[r['name']+' · '+r['state']+'\n  '+r['detail'] for r in row['stages']]+[row['scope']])
