"""Evidence for exact pending levels. Pure readers never contact or modify MT5."""
import hashlib,json,math

DONE={'DISPONIBLE','CALCULADO','COMPROBADO','CONFIRMADO MT5','REVISADA','NO APLICA','VALIDADO','YA VIGENTE'}
INDICATORS=('atr','ema9','ema21','ema50','ema200','rsi','macd','adx','stochastic','williams',
    'cci','mfi','roc','obv_slope','vwap','bos','sweep','fib382','fib50','fib618','range_hi','range_lo','volume_ratio')

def number(value):
    try:
        value=float(value)
        return value if math.isfinite(value) else None
    except (ValueError,TypeError,OverflowError):return None

def identity(plan):
    return str(plan.get('symbol',''))+' / '+('MT5 #'+str(plan['ticket']) if plan.get('ticket') else str(plan.get('key') or 'SIN CLAVE'))

def levels(plan):
    return {k:plan.get(k) for k in ('symbol','side','kind','entry','sl','tp','volume')}

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()[:24]

def relevant_source(name,symbol):
    if name in ('local_ai','cloud','pending_ai','worker','strategy_reference'):return False
    if symbol.startswith('XAU') and (':BTC' in name or name.startswith(('venue:','derivatives:'))):return False
    if symbol.startswith('BTC') and (':XAU' in name or ':GOLD' in name.upper()):return False
    return True

def context_fingerprint(snapshot):
    frames={s:digest({k:v for k,v in (row.get('frames') or {}).items() if k in ('M15','H1','H4','D1')}) for s,row in (snapshot.get('symbols') or {}).items()}
    # Reception timestamps change on every poll, even for identical evidence.
    # Reviews have a separate 180 s lifetime and record their actual input dates.
    # A loss of usable evidence, changed closed candles, settings or exact levels
    # invalidates them immediately. BTC-only sources cannot invalidate gold.
    sources={s:digest({k:{'enabled':True,'fresh':bool(v.get('fresh')),
        'usable':bool(v.get('usable',True)),'failed':bool(v.get('error'))}
        for k,v in (snapshot.get('research') or {}).get('sources',{}).items()
        if isinstance(v,dict) and v.get('enabled') is not False and relevant_source(k,s)}) for s in frames}
    return {'frames':frames,'sources':sources,'configuration':digest(snapshot.get('selection_configuration') or {})}

def fingerprint(snapshot,plan,context=None):
    context=context or context_fingerprint(snapshot)
    return digest({'levels':levels(plan),'frames':context['frames'].get(plan['symbol']),
        'sources':context['sources'].get(plan['symbol']),'configuration':context['configuration']})

def broker_fingerprint(snapshot,plan):
    """Risk/order_check evidence depends on the book and settings, not news."""
    cfg=snapshot.get('selection_configuration') or {}
    book={name:sorted([tuple(str(r.get(k)) for k in ('ticket','symbol','type','entry','sl','tp','volume'))
        for r in snapshot.get(name,[])],key=str) for name in ('orders','positions')}
    account=snapshot.get('account') or {}
    return digest({'levels':levels(plan),'book':book,
        'account':{k:account.get(k) for k in ('login','server','currency','balance')},
        'configuration':{k:cfg.get(k) for k in ('risk','sizing','execution','pending','management')}})

def targets(snapshot,context=None):
    """Every owned confirmed order, then distinct visible structural scenarios."""
    out=[];seen=set();context=context or context_fingerprint(snapshot)
    live={int(o['ticket']):o for o in snapshot.get('orders',[]) if o.get('owned')}
    for symbol,row in (snapshot.get('symbols') or {}).items():
        scenarios=list(row.get('scenario_book') or [])
        for plan in list(row.get('pending_book') or [])+scenarios:
            if not isinstance(plan,dict) or plan.get('lane','PENDING')!='PENDING':continue
            p={**plan,'symbol':symbol};ticket=p.get('ticket')
            if ticket:
                current=next((x for x in scenarios if x.get('ticket')==ticket),{})
                p.update({k:current[k] for k in ('assessment','quality_score','activation_score','scenario_state','block_reason') if k in current})
            if p.get('confirmed'):
                order=live.get(int(ticket or 0))
                if snapshot.get('orders') is not None and not order:continue
                if order:p.update({k:order[k] for k in ('entry','sl','tp','volume') if k in order})
            key=identity(p)
            # A confirmed record and its map counterpart are the same geometry.
            geometry=(symbol,p.get('side'),p.get('kind'),p.get('entry'),p.get('sl'),p.get('tp'))
            if key in seen or geometry in seen:continue
            seen.update((key,geometry));p['verification_id']=key;p['verification_fingerprint']=fingerprint(snapshot,p,context)
            p['broker_fingerprint']=broker_fingerprint(snapshot,p);out.append(p)
    return out

def assess(snapshot,plan,checks=None,reviews=None,context=None):
    stages=[];symbol=plan['symbol'];pid=identity(plan);fp=fingerprint(snapshot,plan,context)
    info=(snapshot.get('symbols') or {}).get(symbol,{})
    frames=info.get('frames') or {};f=frames.get('M15') or {};now=float(snapshot.get('updated') or snapshot.get('as_of_utc') or 0)
    def add(name,state,detail,critical=False):stages.append({'name':name,'state':state,'detail':str(detail),'critical':critical})
    market=(snapshot.get('markets') or {}).get(symbol,{})
    age=now-float(info.get('quote_time') or 0);bid=number(info.get('bid'));ask=number(info.get('ask'))
    fresh=bid is not None and ask is not None and bid>0 and ask>=bid and -5<=age<=float((snapshot.get('data_limits') or {}).get('max_tick_age_seconds',10)) and not snapshot.get('ui_age_seconds',0)>3
    add('Cotización y sesión','PAUSA' if market.get('scheduled_closed') else 'DISPONIBLE' if fresh else 'DESACTUALIZADA',f'Tick de {max(0,age):.1f} s; el envío vuelve a comprobar precio y sesión.',True)
    structural=all(frames.get(tf) and (number(frames[tf].get('atr')) or 0)>0 and 0<=now-float(frames[tf].get('last_bar') or 0)<=limit for tf,limit in (('M15',1800),('H1',7200)))
    add('Estructura multitemporal','DISPONIBLE' if structural else 'INCOMPLETA','Temporalidades: '+', '.join(frames)+'; H1/H4/D1 contextualizan el horizonte, M15 la activación.',True)
    missing=[key for key in INDICATORS if number(f.get(key)) is None]
    add('Indicadores y matemáticas','DISPONIBLE' if not missing else 'INCOMPLETA',str(len(INDICATORS)-len(missing))+'/'+str(len(INDICATORS))+' valores M15 calculados. '+('Faltan: '+', '.join(missing) if missing else ', '.join(INDICATORS)))
    side=plan.get('side');entry=number(plan.get('entry'));sl=number(plan.get('sl'));tp=number(plan.get('tp'))
    geometry=side in (-1,1) and all(v is not None and v>0 for v in (entry,sl,tp)) and side*(entry-sl)>0 and side*(tp-entry)>0
    trend=number((frames.get('H1') or {}).get('trend')) or 0
    strategy='Ruptura y continuación' if plan.get('kind')=='STOP' else 'Retroceso con tendencia' if side in (-1,1) and side*trend>0 else 'Reversión o rango: requiere confirmación'
    reason=str(plan.get('reason') or '')[:600]
    entry_checks=snapshot.get('entry_quality_checks') or {}
    entry_check=entry_checks.get(str(plan.get('symbol'))+':'+str(plan.get('key'))) or entry_checks.get(plan.get('key')) or {}
    if entry_check.get('symbol') not in (None,plan.get('symbol')):entry_check={}
    match=entry_check.get('levels')=={k:plan.get(k) for k in ('symbol','side','kind','entry','sl','tp')} and -5<=now-float(entry_check.get('time') or 0)<=30
    rejected=match and not entry_check.get('allowed')
    add('Estrategia y tesis','BLOQUEADO' if rejected else 'CALCULADO' if reason else 'SIN TESIS',
        strategy+'. '+(entry_check.get('reason') if rejected else reason or 'No hay tesis conservada para estos niveles; no se reconstruye una explicación inventada.'),bool(rejected))
    add('Entrada, invalidación y objetivo','CALCULADO' if geometry else 'BLOQUEADO',f'Entry {entry}; SL {sl}; TP {tp}. '+('Geometría direccional coherente.' if geometry else 'Niveles incompletos o invertidos.'),True)
    rr=side*(tp-entry)/(side*(entry-sl)) if geometry else None
    quality=number(plan.get('quality_score')) or 0;warnings=(plan.get('assessment') or {}).get('warnings') or []
    add('Calidad y recorrido','REVISAR' if quality<60 or warnings else 'CALCULADO',f'Calidad técnica {quality:.1f}/100; R:R geométrico {rr:.2f}. '+ '; '.join(str(w) for w in warnings) if rr is not None else 'R:R no calculable. Las estrellas no son probabilidad de ganar.')
    sources=(snapshot.get('research') or {}).get('sources') or {}
    relevant=[(name,row) for name,row in sources.items() if isinstance(row,dict) and relevant_source(name,symbol)]
    available=[name for name,row in relevant if row.get('fresh') and row.get('usable',True) and not row.get('error') and row.get('enabled') is not False]
    unavailable=[name+': '+str(row.get('error') or 'sin datos vigentes') for name,row in relevant if name not in available and row.get('enabled') is not False]
    add('Fuentes y contradicciones','DISPONIBLE' if available else 'SIN APORTE',
        'Fuentes útiles ('+str(len(available))+'/'+str(len(relevant))+'): '+(', '.join(available) or 'ninguna')+
        '. Sin señal válida: '+('; '.join(unavailable) or 'ninguna registrada')+
        '. Una fuente ausente o un vídeo sin transcripción no cuenta como confirmación; fuentes correlacionadas no son pruebas independientes.')
    check=(checks or {}).get(pid) or {}
    check_matches=check.get('broker_fingerprint')==broker_fingerprint(snapshot,plan) if check.get('broker_fingerprint') else check.get('fingerprint')==fp
    valid_check=check.get('levels')==levels(plan) and check_matches and -5<=now-float(check.get('at') or 0)<=30
    add('Riesgo de ESTA pendiente','COMPROBADO' if valid_check and check.get('risk_passed') else 'BLOQUEADO' if valid_check and check.get('error') else 'PENDIENTE',
        f"Riesgo {check.get('risk_usd')}; lote {check.get('volume')}; margen {check.get('margin')}. "+str(check.get('error') or 'Comprobación individual; excluye su propio ticket de la reserva para evitar contarlo dos veces. Se repite antes de un envío.') if valid_check else 'Falta una comprobación vigente ligada a estos niveles, lote y libro; no se reutiliza la de otra orden.',True)
    # 10025 is not a failed new order. For an existing unchanged confirmed
    # ticket we verified the broker book + live risk without a no-op MODIFY.
    unchanged=bool(valid_check and plan.get('confirmed') and check.get('unchanged_confirmed')
                   and check.get('broker_checked') and check.get('risk_passed'))
    add('Restricciones MT5 de ESTA pendiente','YA VIGENTE' if unchanged else 'COMPROBADO' if valid_check and check.get('broker_checked') else 'RECHAZADO' if valid_check and check.get('broker_error') else 'PENDIENTE',
        str(check.get('broker_basis') or 'Ticket confirmado con los mismos niveles; no se requiere modificar MT5.') if unchanged else
        str(check.get('broker_error') or 'order_check individual, sin enviar ni modificar la orden.') if valid_check else 'Debe comprobarse esta geometría con MT5; verla colocada no sustituye order_check actual.',True)
    review=(reviews or {}).get(pid) or {};review_matches=review.get('fingerprint')==fp
    data=review.get('data') or {};verdict=data.get('verdict')
    current=review_matches and -5<=now-float(review.get('updated') or now)<=180
    elapsed=max(0,now-float(review.get('started') or review.get('requested') or now))
    running=review_matches and review.get('state') in ('QUEUED','RUNNING')
    deadline=90 if review.get('state')=='QUEUED' else 65
    ai_approved=(review.get('state')=='COMPLETE' and isinstance(data,dict)
                 and verdict=='APPROVE' and isinstance(data.get('reason'),str)
                 and bool(data['reason'].strip()) and isinstance(data.get('missing'),list)
                 and not data['missing'])
    state=('REVISADA' if current and ai_approved else
           'RECHAZADA IA' if current and review.get('state')=='COMPLETE' else
           'TIEMPO AGOTADO' if running and elapsed>deadline else
           'EN CONSULTA' if running else
           'ERROR' if review_matches and review.get('state')=='ERROR' else
           'DESACTUALIZADA' if review else 'PENDIENTE')
    required=pid in (snapshot.get('required_pending_reviews') or [])
    queue_detail=(f'Consulta en curso desde hace {elapsed:.0f} s; {review.get("queue_ahead",0)} revisión(es) delante. ' if state=='EN CONSULTA' else 'La revisión agotó su plazo; vuelve a solicitarla si sigue siendo necesaria. ' if state=='TIEMPO AGOTADO' else '')
    add('IA: revisión de ESTA pendiente',state,('Exigida por el usuario para nuevos envíos y cambios. ' if required else '')+queue_detail+str(data.get('reason') or review.get('error') or 'La revisión de IA debe citar estos niveles y sus indicadores. Una opinión general sobre BTC u oro no cumple esta etapa.')+(' · Dictamen: '+str(verdict) if verdict else '')+(' · Faltantes: '+', '.join(data.get('missing') or []) if data.get('missing') else '')+(' · Evidencia recibida hasta '+str(review['evidence_at'])+' UTC; una recepción nueva no borra el dictamen, cuya vigencia máxima es 180 s.' if review.get('evidence_at') else ''),required)
    stats={}
    from selection_trials import cell
    from quality_study import QualityStudy
    models_by_cohort=(snapshot.get('quality_study') or {}).get('validated_probabilities',{})
    config_hash=hashlib.sha256(json.dumps(snapshot.get('selection_configuration') or {},sort_keys=True,default=str).encode()).hexdigest()[:16] if models_by_cohort else ''
    provider=str(QualityStudy.provider(snapshot));target_cell=cell(plan)
    for cohort,models in models_by_cohort.items():
        if cohort.startswith(symbol+' / ') and cohort.endswith(' / '+config_hash) and (' / '+str(snapshot.get('build'))+' / ') in cohort and (' / '+provider+' / ') in cohort:
            stats={name:models[key]['bins'][target_cell] for name,key in (('activation','activation'),('favorable','favorable_given_activation')) if key in models and target_cell in models[key].get('bins',{})}
    add('Estudio y probabilidad','VALIDADO' if stats else 'EN ESTUDIO',
        'Replay fuera de muestra del mismo proveedor, configuración, versión y clase de ESTA pendiente: '+str(stats)+'. Activación y recorrido favorable no son probabilidad de ganancia de cuenta; consultar muestra y costes.' if stats else
        'La evidencia de ejecución y calidad no prueba ganancias. Falta un estudio comparable de esta clase de pendiente; no se inventa una probabilidad individual.')
    add('Estado de la orden','CONFIRMADO MT5' if plan.get('confirmed') else 'PROPUESTA',('#'+str(plan.get('ticket'))+' visible en MT5.' if plan.get('confirmed') else 'Niveles propuestos, sin colocación confirmada.')+' Verificar no envía, edita ni elimina órdenes.')
    completed=sum(s['state'] in DONE for s in stages);critical=[s['name'] for s in stages if s['critical'] and s['state'] not in DONE]
    # Optional research cannot block a technically valid order. Required IA,
    # broker checks and risk are separate; nothing here sends to MT5.
    if critical or quality<60 or warnings or (required and state=='RECHAZADA IA'):
        status='REVISAR'
    elif required and state!='REVISADA':
        status='REVISIÓN IA OBLIGATORIA · '+state
    elif state!='REVISADA':
        status='COMPROBACIONES ESENCIALES OK · IA OPCIONAL '+state
    else:
        status='REVISIÓN COMPLETA · VER LÍMITES'
    return {'id':pid,'fingerprint':fp,'symbol':symbol,'ticket':plan.get('ticket'),'key':plan.get('key'),'calibration':stats,
        'levels':levels(plan),'confirmed':bool(plan.get('confirmed')),'ai_required':required,'stages':stages,'completed':completed,'total':len(stages),
        'progress':round(100*completed/len(stages),1),'state':status,'missing':[s['name']+' · '+s['state'] for s in stages if s['state'] not in DONE],
        'critical_missing':critical,'ai_gate':'obligatoria' if required else 'opcional','strategy':strategy,'as_of_utc':now,'ai':review if current else {},'scope':'Cobertura de comprobaciones de estos niveles; no porcentaje de ganancias ni garantía.'}

def reports(snapshot,checks=None):
    reviews=(snapshot.get('research') or {}).get('pending_reviews') or {}
    context=context_fingerprint(snapshot)
    return {identity(p):assess(snapshot,p,checks,reviews,context) for p in targets(snapshot,context)}

def report_text(row):
    p=row['levels'];side='COMPRA' if p.get('side')==1 else 'VENTA'
    def display(value):return 'sin dato' if number(value) is None else f'{float(value):,.6f}'.rstrip('0').rstrip('.')
    params=side+' '+str(p.get('kind') or '')+' · Entrada '+display(p.get('entry'))+' · SL '+display(p.get('sl'))+' · TP '+display(p.get('tp'))+' · Lote '+display(p.get('volume'))
    return '\n'.join([row['id']+' · '+row['state'],params,f"VERIFICACIÓN {row['completed']}/{row['total']} · {row['progress']}%",'Estrategia: '+row['strategy']]+[
        stage['name']+' · '+stage['state']+'\n  '+stage['detail'] for stage in row['stages']]+[row['scope']])
