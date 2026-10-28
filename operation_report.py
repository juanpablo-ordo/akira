"""Informe para personas y soporte. Se ejecuta fuera del actor MT5."""
from datetime import datetime,timezone,timedelta
from pathlib import Path
import copy,json,math,os,re,tempfile,zipfile
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape
from trade_review import assess_plan,finite
from order_timing import broker_seconds,pending_times,positive
from analysis_details import indicator_rows,analysis_text

LOCAL=timezone(timedelta(hours=-6),'Guatemala')
NS='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
ET.register_namespace('',NS)
SHEETS=('Resumen','Pendientes','Runners','Cierres','Riesgo','Fuentes','Decisiones')
HEADERS={
 'Resumen':('Área','Dato','Valor','Interpretación'),
 'Pendientes':('Ticket / propuesta','Símbolo','Tipo','Propiedad','Entrada','SL','TP','R:R','Riesgo USD','Lote','Estrellas','Revisión','Colocación local','Origen de hora'),
 'Runners':('Símbolo','Estado','Dirección','Entrada','SL','TP','Lote','Riesgo USD','Límite USD','Motivo','Ticket','Solicitud local','Apertura MT5 local'),
 'Cierres':('Posición','Símbolo','Vía','Entrada local','Salida local','Duración min','Precio entrada','SL original','Precio salida','Neto USD','MFE R','Captura observada','Motivo','Evaluación','Colocación local','Origen de hora'),
 'Riesgo':('Ticket / solicitud','Símbolo','Origen','Propiedad','Lote','Entrada','SL','Reserva USD','Margen futuro USD','Detalle','Colocación / apertura local','Origen de hora'),
 'Fuentes':('Fuente','Estado','Fecha / edad','Uso','Detalle'),
 'Decisiones':('Hora local','Símbolo','Acción','Ticket','Motivo','SL anterior','SL nuevo','R al solicitar')}


def action_name(operation,event=None):
    event=event or {}
    if operation=='open':
        runner=event.get('lane')=='RUNNER' or (event.get('request') or {}).get('magic')==170003
        return 'Abrir runner' if runner else 'Colocar pendiente'
    return {'modify_order':'Modificar pendiente','cancel':'Retirar pendiente','protect':'Proteger SL/TP','close':'Cerrar runner'}.get(operation,str(operation))


def stamp(value):
    value=finite(value)
    if value is None:return ''
    try:return datetime.fromtimestamp(value,LOCAL).strftime('%d/%m/%Y %H:%M:%S')
    except (ValueError,OverflowError,OSError):return ''


def clean(value):
    if isinstance(value,dict):
        return {str(k):clean(v) for k,v in value.items() if not re.search(r'(?:password|secret|api_key|access_token|authorization|credential)',str(k),re.I)}
    if isinstance(value,(tuple,list)):return [clean(v) for v in value]
    if isinstance(value,float) and not math.isfinite(value):return None
    if isinstance(value,(str,int,float,bool)) or value is None:return value
    return str(value)


def redact_snapshot(snapshot):
    row=clean(copy.deepcopy(snapshot))
    account=row.get('account') or {}
    if account.get('login') is not None:account['login']='***'+str(account['login'])[-4:]
    row.pop('runtime',None)
    return row


def closed_trades(snapshot,cutoff):
    groups={};journal=snapshot.get('position_journal') or {}
    journal_by_id={str(r.get('identifier',k)):(k,r) for k,r in journal.items()}
    for deal in snapshot.get('history_deals') or []:
        pid=deal.get('position_id')
        if not pid or deal.get('type') not in (0,1):continue
        groups.setdefault(str(pid),[]).append(deal)
    out=[];times=pending_times(snapshot)
    for pid,deals in groups.items():
        deals=sorted(deals,key=lambda d:finite(d.get('time'),0));ins=[d for d in deals if d.get('entry')==0];exits=[d for d in deals if d.get('entry') in (1,3)]
        if not exits or finite(exits[-1].get('time'),0)<cutoff:continue
        # No agrupar un reversal de netting como un cierre sencillo, ni confundir
        # un cierre parcial con una operación terminada.
        if any(d.get('entry')==2 for d in deals):continue
        vin=sum(finite(d.get('volume'),0) for d in ins);vout=sum(finite(d.get('volume'),0) for d in exits)
        if not ins or vin<=0 or vout<vin-1e-8:continue
        key,row=journal_by_id.get(pid,(pid,{}));plan=row.get('plan') or {}
        magic=int(ins[0].get('magic') or 0)
        lane=plan.get('lane') or row.get('lane') or ('RUNNER' if magic==170003 else 'PENDING' if magic==170002 else 'MANUAL / ANTERIOR')
        entry=sum(finite(d.get('price'),0)*finite(d.get('volume'),0) for d in ins)/vin
        exit_price=sum(finite(d.get('price'),0)*finite(d.get('volume'),0) for d in exits)/vout
        net=sum(sum(finite(d.get(k),0) for k in ('profit','commission','swap','fee')) for d in deals)
        cause={0:'Terminal',1:'Móvil',2:'Web',3:'Programa / EA',4:'Stop Loss',5:'Take Profit',6:'Stop Out'}.get(exits[-1].get('reason'),'Motivo no suministrado')
        from position_events import summarize_closure
        closure=row.get('closure') or summarize_closure(key,row,deals)
        if closure and closure.get('initiator')=='AKIRA':cause=closure['cause']
        mfe=finite(row.get('max_favorable_r'));mfe_usd=finite(row.get('max_favorable_usd'))
        capture=max(0,net)/mfe_usd if mfe_usd is not None and mfe_usd>0 else None
        review='Sin MFE registrado: no se puede juzgar si cerró demasiado pronto.' if mfe is None else 'Máximo observado desde '+stamp(row.get('tracking_started_at'))+'; no demuestra qué habría pasado después.'
        if cause=='Stop Loss' and capture is not None and capture<.25 and mfe>=1.25:
            review='SL ejecutado tras devolver parte del máximo observado; revisar los cambios de protección. '+review
        out.append({'ticket':str(key),'symbol':ins[0].get('symbol',''),'lane':lane,'entry_time':broker_seconds(ins[0]),
            'placed_at':(times.get(str(ins[0].get('order'))) or {}).get('placed_at') or positive(row.get('requested_at')),
            'placement_source':(times.get(str(ins[0].get('order'))) or {}).get('source') or ('Akira: solicitud registrada' if positive(row.get('requested_at')) else 'Sin registro de colocación'),
            'exit_time':broker_seconds(exits[-1]),'duration_minutes':(finite(exits[-1].get('time'),0)-finite(ins[0].get('time'),0))/60,
            'entry':entry,'initial_sl':finite(row.get('initial_sl')),'exit_price':exit_price,'net_usd':net,
            'mfe_r':mfe,'capture':capture,'cause':cause,'review':review})
    return sorted(out,key=lambda r:r['exit_time'],reverse=True)


def read_recent_events(folder,hours,as_of,max_bytes=6*1024*1024):
    """Lectura acotada en el worker; nunca dentro del ciclo MT5."""
    if not hours:return [],False
    end=datetime.fromtimestamp(as_of,timezone.utc);cutoff=as_of-hours*3600
    rows=[];budget=max_bytes;truncated=False
    for n in range(min(8,math.ceil(hours/24)+1)):
        path=Path(folder)/('eventos_'+(end-timedelta(days=n)).strftime('%Y-%m-%d')+'.jsonl')
        if not path.is_file():continue
        size=path.stat().st_size;take=min(size,budget);offset=size-take;truncated|=bool(offset)
        with path.open('rb') as stream:
            stream.seek(offset);raw=stream.read(take)
        budget-=take
        if offset:raw=raw.partition(b'\n')[2]
        for line in raw.splitlines():
            try:
                row=json.loads(line);when=datetime.fromisoformat(str(row['utc']).replace('Z','+00:00')).timestamp()
            except (ValueError,TypeError,KeyError,UnicodeError):continue
            if when<cutoff or when>as_of+5 or not row.get('operation'):continue
            rows.append(row)
        if budget<=0:truncated=True;break
    rows.sort(key=lambda r:r['utc'])
    return rows[-1000:],truncated or len(rows)>1000


def source_rows(research,as_of):
    rows=[]
    for name,row in (research.get('sources') or {}).items():
        if not isinstance(row,dict):continue
        age=finite(row.get('age_seconds'))
        if age is None and finite(row.get('updated'),0)>0:age=max(0,as_of-float(row['updated']))
        state='Vigente según proveedor' if row.get('fresh') is True else 'Sin vigencia confirmada'
        rows.append([str(name),state,f'{age:.0f} s' if age is not None else 'Sin fecha','Contexto auxiliar',str(row.get('error') or row.get('state') or '')])
    from email.utils import parsedate_to_datetime
    for group in ('news','videos'):
        for row in (research.get(group) or [])[:10]:
            date=str(row.get('date') or row.get('published') or row.get('published_at') or 'Sin fecha');dated=None
            try:dated=parsedate_to_datetime(date).timestamp()
            except (ValueError,TypeError,OverflowError):pass
            if dated is None:
                try:dated=datetime.fromisoformat(date.replace('Z','+00:00')).timestamp()
                except (ValueError,TypeError,OverflowError):pass
            current=dated is not None and -300<=as_of-dated<=86400
            rows.append(['Noticia' if group=='news' else 'YouTube','Publicación reciente' if current else 'Fecha antigua o sin verificar',date,
                'Contexto; no confirmación intradía' if current else 'Referencia; requiere verificar actualidad',str(row.get('title',''))+' '+str(row.get('url',''))])
    for name,row in (research.get('global_markets') or {}).items():
        rows.append([name,'Mercado externo disponible',stamp(row.get('market_time') or row.get('updated')) or 'Ver fecha/edad del proveedor',
            'Contraste BTC; USD y USDT se conservan separados. No es precio de ejecución MT5.',
            'Par '+str(row.get('quote','sin dato'))+'; bid '+str(row.get('bid'))+'; ask '+str(row.get('ask'))+'; desequilibrio libro '+str(row.get('imbalance'))+'; funding '+str(row.get('funding','sin dato'))+'; interés abierto USD '+str(row.get('open_interest_usd','sin dato'))])
    for row in (research.get('macro') or {}).get('rows',[]):
        rows.append(['FRED · '+str(row.get('name','')),'Serie diaria, sujeta a rezago de publicación',str(row.get('date','sin fecha')),
            str(row.get('used_for','Contexto macro; no señal por sí sola')),str(row.get('value','sin dato'))+' · variación '+str(row.get('last_change','sin dato'))])
    if not rows:rows=[['Fuentes externas','Sin detalle disponible','','MT5 sigue siendo la fuente de precios','El informe no realiza búsquedas ni inventa fuentes actuales.']]
    return rows


def build_report(snapshot,hours=24):
    snapshot=redact_snapshot(snapshot);as_of=finite(snapshot.get('as_of_utc'),finite(snapshot.get('updated'),0))
    cutoff=as_of-float(hours)*3600 if hours else as_of
    account=snapshot.get('account') or {};ledger=snapshot.get('portfolio_risk') or {};symbols=snapshot.get('symbols') or {}
    warnings=[]
    safety=snapshot.get('entry_safety') or {}
    if safety.get('enabled') and not safety.get('allowed',True):warnings.append(safety.get('reason','Nuevas entradas en pausa por pérdidas confirmadas.'))
    if snapshot.get('preview'):warnings.append('VISTA PREVIA · Datos simulados de prueba; no pertenecen a una cuenta real ni prueban calidad financiera.')
    if snapshot.get('report_capture_note'):warnings.append(snapshot['report_capture_note'])
    if not snapshot.get('connected'):warnings.append('Informe sin conexión actual confirmada; los datos pueden ser históricos.')
    if snapshot.get('imported_logs'):warnings.append('Reconstruido de registros aportados. Faltan velas, configuración e historial de deals; los datos ausentes se indican.')
    if snapshot.get('event_log_truncated'):warnings.append('La lectura de eventos se limitó a los registros más recientes; el diario y el historial de cierres se muestran por separado.')
    history=snapshot.get('history_state') or {}
    if history.get('error'):warnings.append('Historial de cierres: '+str(history['error']))
    if finite(account.get('equity')) is None:warnings.append('Patrimonio no disponible: el límite de riesgo no se interpreta como saldo.')
    pendings=[];seen=set();runners=[];decisions=[];overview=[];times=pending_times(snapshot)
    summary=[['Cuenta','Hora de la captura',stamp(as_of),'America/Guatemala (UTC-6)'],['Cuenta','Versión',snapshot.get('build','No registrada'),'Versión del motor que produjo los datos'],
        ['Cuenta','Patrimonio USD',finite(account.get('equity')),'Dato MT5; ausente no significa cero'],
        ['Riesgo','Límite conjunto USD',finite(ledger.get('cap_usd')),'Compartido entre BTC, oro y operaciones manuales'],
        ['Riesgo','Reservado USD',finite(ledger.get('reserved_usd')),'Suma de posiciones, pendientes y solicitudes sin confirmar'],
        ['Riesgo','Libre USD',finite(ledger.get('available_usd')),'Capacidad conjunta; cada operación también tiene su propio límite'],
        ['Riesgo','Límite por operación USD',finite(snapshot.get('trade_risk_cap')),'Ninguna entrada nueva puede superarlo por tener presupuesto conjunto libre; las runners directas tienen además su propio tope reducido'],
        ['Velocidad','Último ciclo ms',finite(snapshot.get('cycle_ms')),'Medición del motor; no garantiza latencia futura del bróker']]
    for symbol,info in symbols.items():
        if (snapshot.get('markets') or {}).get(symbol,{}).get('scheduled_closed'):continue
        status=(snapshot.get('status') or {}).get(symbol) or {};runner=info.get('runner') or {};plan=runner.get('plan') or {};funding=runner.get('funding') or {}
        overview.append(f'{symbol}: {status.get("state","Sin estado")}. {status.get("detail","")} Runner: {runner.get("state","Sin diagnóstico")}. {runner.get("detail","")}')
        summary.append(['Operación',symbol,status.get('state','Sin estado'),status.get('detail','')])
        for reason in info.get('allocation_reasons') or []:summary.append(['Mapa',symbol,'Lado / capacidad',str(reason)])
        runner_risk=finite(runner.get('risk'))
        if runner_risk is None:runner_risk=finite(funding.get('minimum_risk_usd'))
        runners.append([symbol,runner.get('state','Sin diagnóstico'),'LONG' if plan.get('side')==1 else 'SHORT' if plan.get('side')==-1 else 'Sin señal',
            finite(plan.get('entry')),finite(plan.get('sl')),finite(plan.get('tp')),finite(runner.get('volume')),runner_risk,
            finite(funding.get('trade_cap_usd'),finite(snapshot.get('trade_risk_cap'))),runner.get('detail','No registrado'),'Sin ticket',None,None])
        plans=list(info.get('scenario_book') or info.get('pending_book') or [])
        represented={str(r.get('ticket')) for r in plans if r.get('ticket')}
        for row in info.get('pending_book') or []:
            if row.get('confirmed') and row.get('ticket') and str(row['ticket']) not in represented:
                plans.append(row);represented.add(str(row['ticket']))
        for row in plans:
            row={**row,'symbol':symbol};ticket=str(row.get('ticket') or '')
            financial=next((r for r in ledger.get('rows',[]) if str(r.get('ticket'))==ticket and r.get('kind')=='pending'),{})
            if financial:
                row.update(volume=financial.get('volume'),risk_usd=financial.get('risk_usd'))
            row['assessment']=row.get('assessment') or assess_plan(row,info.get('frames'),as_of,info)
            pendings.append(row)
            if ticket:seen.add(ticket)
    for order in snapshot.get('orders') or []:
        if (snapshot.get('markets') or {}).get(order.get('symbol'),{}).get('scheduled_closed'):continue
        if str(order.get('ticket')) in seen:continue
        typ=int(order.get('type',2));row={**order,'side':1 if typ%2==0 else -1,'kind':'LIMIT' if typ in (2,3,6,7) else 'STOP',
            'lane':'PENDING','confirmed':True,'quality_score':None}
        financial=next((r for r in ledger.get('rows',[]) if r.get('kind')=='pending' and r.get('ticket')==row.get('ticket')),{})
        row['risk_usd']=financial.get('risk_usd');row['assessment']=assess_plan(row);pendings.append(row)
    # A runner diagnostic is not an open position. List confirmed live positions
    # independently, including positions activated from a pending order.
    for position in snapshot.get('positions') or []:
        ticket=str(position.get('ticket') or '')
        meta=(snapshot.get('position_journal') or {}).get(ticket) or {}
        plan=meta.get('plan') or {};lane=plan.get('lane') or meta.get('lane')
        if lane not in ('RUNNER','PENDING') and position.get('magic') not in (170002,170003):continue
        risk=next((r.get('risk_usd') for r in ledger.get('rows',[]) if str(r.get('ticket'))==ticket and r.get('kind')=='position'),None)
        opened=broker_seconds(position) or positive(meta.get('opened_at'))
        runners.append([position.get('symbol',''),'POSICIÓN ABIERTA · '+('runner directa' if lane=='RUNNER' or position.get('magic')==170003 else 'pendiente activada'),
            'LONG' if position.get('type')==0 else 'SHORT',finite(position.get('entry')),finite(position.get('sl')),finite(position.get('tp')),
            finite(position.get('volume')),finite(risk),finite(snapshot.get('trade_risk_cap')),'SL/TP vigentes en MT5.',
            ticket,stamp(meta.get('requested_at')) or 'Sin registro',stamp(opened) or 'Sin registro de apertura MT5'])
    closed=closed_trades(snapshot,cutoff) if hours else []
    closed=[r for r in closed if not (snapshot.get('markets') or {}).get(r['symbol'],{}).get('scheduled_closed')]
    for ticket,row in (snapshot.get('position_journal') or {}).items():
        for event in row.get('management_events') or []:
            if finite(event.get('time'),0)<cutoff:continue
            decisions.append([stamp(event.get('time')),row.get('symbol') or (row.get('plan') or {}).get('symbol',''),action_name(event.get('operation',''),event),str(ticket),
                event.get('reason',''),finite(event.get('old_sl')),finite(event.get('new_sl')),finite(event.get('rr_at_request'))])
    for event in snapshot.get('operational_events') or []:
        when=0
        try:when=datetime.fromisoformat(str(event.get('utc','')).replace('Z','+00:00')).timestamp()
        except (ValueError,TypeError):pass
        if when<cutoff:continue
        decisions.append([stamp(when),event.get('symbol',''),action_name(event.get('operation',''),event),str((event.get('request') or {}).get('order') or (event.get('request') or {}).get('position') or event.get('order') or ''),
            event.get('reason') or event.get('message',''),None,finite((event.get('request') or {}).get('sl')),finite(event.get('rr_at_request'))])
    pending_rows=[]
    owned_ids={str(r.get('ticket')) for r in snapshot.get('orders') or [] if r.get('owned')}
    for row in pendings:
        a=row['assessment'];ticket=row.get('ticket');own=(str(ticket) in owned_ids) if ticket else None
        review='; '.join(a['evidence']+a['warnings'])
        if a.get('quality_score') is not None:review=f'Índice técnico {a["quality_score"]:.1f}/100. '+review
        timing=times.get(str(ticket)) or {}
        row['placed_at']=timing.get('placed_at');row['placement_source']=timing.get('source','Aún no enviada' if not ticket else 'Sin registro de hora')
        pending_rows.append([str(ticket) if ticket else 'Propuesta',row.get('symbol',''),('BUY' if row.get('side') in (1,'BUY') else 'SELL')+' '+str(row.get('kind','')),
            'Akira' if own else 'Manual / externa' if ticket else a['state'],finite(row.get('entry')),finite(row.get('sl')),finite(row.get('tp')),
            finite(a.get('rr')),finite(a.get('risk_usd')),finite(row.get('volume')),a['label'],review,stamp(row['placed_at']) or ('Aún no enviada' if not ticket else 'Sin registro'),row['placement_source']])
    risk_rows=[[str(r.get('ticket') or r.get('operation') or 'Sin ticket'),r.get('symbol',''),{'pending':'Pendiente','position':'Posición','intent':'Solicitud sin confirmar'}.get(r.get('kind'),r.get('kind','')),'Akira' if r.get('owned') else 'Manual / externa',
        finite(r.get('volume')),finite(r.get('entry')),finite(r.get('sl')),finite(r.get('reserved_usd')),finite(r.get('future_margin_usd')),r.get('reason','')] for r in ledger.get('rows',[])]
    for record in risk_rows:
        ticket=record[0]
        timing=times.get(ticket) or {}
        position=next((p for p in snapshot.get('positions') or [] if str(p.get('ticket'))==ticket),None)
        if position is not None:
            record.extend([stamp(broker_seconds(position)) or 'Sin registro','MT5: apertura de posición'])
        else:record.extend([stamp(timing.get('placed_at')) or 'Sin registro',timing.get('source','Sin registro de hora')])
    # Historical confirmed pending receipts survive log rotation/cancellation.
    for ticket,meta in (snapshot.get('order_journal') or {}).items():
        timing=times.get(str(ticket)) or {};placed=positive(timing.get('placed_at'))
        if placed is None or placed<cutoff:continue
        plan=meta.get('plan') or {}
        decisions.append([stamp(placed),plan.get('symbol',''),'Colocación de pendiente',str(ticket),
            timing.get('source','')+'; el registro de envío no implica que la pendiente se activó.',None,finite(plan.get('sl')),None])
    close_rows=[[r['ticket'],r['symbol'],r['lane'],stamp(r['entry_time']),stamp(r['exit_time']),r['duration_minutes'],r['entry'],r['initial_sl'],r['exit_price'],r['net_usd'],r['mfe_r'],r['capture'],r['cause'],r['review'],stamp(r.get('placed_at')) or 'Sin registro',r.get('placement_source','Sin registro')] for r in closed]
    summary.append(['Historial','Operaciones cerradas completas',len(closed),f'Últimas {hours} horas; solo operaciones con entrada y cierre completos en el historial disponible'])
    summary.append(['Historial','Neto de esos cierres USD',sum(r['net_usd'] for r in closed) if closed else None,'Incluye beneficio, comisión, swap y fee de cada operación reconstruida'])
    for warning in warnings:summary.append(['Revisar','Dato faltante',None,warning])
    from quality_study import scope_metrics
    metrics=scope_metrics(snapshot,cutoff)
    for symbol,lanes in metrics.items():
        if (snapshot.get('markets') or {}).get(symbol,{}).get('scheduled_closed'):continue
        for lane,values in lanes.items():
            for key,name in [('closed','Cierres completos'),('win_rate','Proporción ganadora histórica'),('net_usd','Resultado neto USD'),('profit_factor','Factor de beneficio'),('drawdown_usd','Drawdown de cierres USD')]:
                summary.append(['Resultados',symbol+' '+lane+' · '+name,values.get(key),'Período elegido; historial propio con costes. Sin dato cuando faltan cierres completos.'])
    study=snapshot.get('quality_study') or {}
    summary.append(['Estudio','Referencias reales para comparar',study.get('comparisons',0),'Capturas y recomendaciones vinculadas. Su importación no demuestra superioridad.'])
    for symbol,count in (study.get('cases') or {}).items():
        if (snapshot.get('markets') or {}).get(symbol,{}).get('scheduled_closed'):continue
        summary.append(['Estudio',symbol+' · Casos capturados',count,'Una geometría inmutable por lado/tipo y vela M15; los ciclos repetidos no inflan la muestra.'])
    for symbol,count in (study.get('recorded_quotes') or {}).items():
        if (snapshot.get('markets') or {}).get(symbol,{}).get('scheduled_closed'):continue
        summary.append(['Estudio',symbol+' · Cotizaciones observadas',count,'MT5, muestreo cada 30 s, retención 120 días; puede omitir cruces entre muestras. No ejecuciones reales.'])
    for name,row in ((study.get('quote_comparison') or {}).get('groups') or {}).items():
        if (snapshot.get('markets') or {}).get(name.split(' / ')[0],{}).get('scheduled_closed'):continue
        stats=row['holdout'];summary.append(['Estudio',name+' · Pares fuera de muestra',stats['pairs'],row['status']])
        summary.append(['Estudio',name+' · Diferencia media neta R',stats.get('delta_r'),'Replay bid/ask; inicio común, costes R aportados. No resultado de ejecución real.'])
        summary.append(['Estudio',name+' · Intervalo 95% por día',str(stats.get('confidence_95_by_day') or 'Sin muestra suficiente'),'Incertidumbre agrupada por día; no probabilidad de ganar una próxima orden.'])
    summary.append(['Método','Estrellas y cercanía','Índices técnicos','No son probabilidades de ganar o activarse. No se ejecuta ninguna orden al generar este informe.'])
    from operation_verifier import verification
    for symbol in snapshot.get('symbols',{}):
        if (snapshot.get('markets') or {}).get(symbol,{}).get('scheduled_closed'):continue
        for stage in verification(snapshot,symbol)['stages']:
            summary.append(['Verificación',symbol+' · '+stage['name'],stage['state'],stage['detail']])
    for cohort,trial in ((study.get('selector_comparison') or {}).get('groups') or {}).items():
        symbol=cohort.split(' / ')[0]
        if (snapshot.get('markets') or {}).get(symbol,{}).get('scheduled_closed'):continue
        for name,value in trial['policies'].items():summary.append(['Estudio',symbol+' · '+name,value['mean_net_r'],value['status']+'; '+str(trial['holdout_decisions'])+' decisiones / '+str(trial['holdout_days'])+' días; '+trial['status']])
    for s,tf,name,value,purpose,last_bar in indicator_rows(snapshot):
        summary.append(['Indicadores',s+' '+tf+' · '+name,value,purpose+'; última vela '+stamp(last_bar)])
    for name,row in (snapshot.get('markets') or {}).items():
        if row.get('scheduled_closed'):
            summary.append(['Mercados','Instrumento cerrado',None,'Mercado no operativo durante esta captura; la exposición previa sigue incluida en el riesgo total de cuenta.'])
    # Risk totals always include all instruments, even when activity rows are hidden.
    closed_symbols={s for s,r in (snapshot.get('markets') or {}).items() if r.get('scheduled_closed')}
    risk_rows=[r for r in risk_rows if r[1] not in closed_symbols]
    close_rows=[r for r in close_rows if r[1] not in closed_symbols]
    decisions=[r for r in decisions if r[1] not in closed_symbols]
    verifications=[r for r in (snapshot.get('pending_verifications') or {}).values() if r.get('symbol') not in closed_symbols]
    for r in verifications:
        for stage in r.get('stages') or []:
            decisions.append([stamp(r.get('as_of_utc') or as_of),r['symbol'],'Verificar '+stage['name'],str(r.get('ticket') or 'propuesta'),stage['state']+' · '+stage['detail'],None,None,None])
    lab=(snapshot.get('research') or {}).get('strategy_lab') or {}
    for strategy in lab.get('strategies') or []:
        for symbol,m in strategy.get('symbols',{}).items():
            if symbol in closed_symbols:continue
            actual=m.get('realized') or {};paper=m.get('holdout') or {}
            wr=actual.get('win_rate');percent='Sin muestra' if wr is None else f'{100*wr:.1f}% observado'
            net='Sin muestra' if actual.get('net') is None else f"{actual['net']:,.3f}"
            detail=(strategy['name']+' · '+str(strategy.get('mode'))+f" · {actual.get('n',0)} cierres propios · {percent}; neto {net}. "
                +f"Holdout {paper.get('n',0)} casos, {m.get('holdout_days',0)} días: {m.get('state','EN ESTUDIO')}. No probabilidad individual.")
            decisions.append([stamp(lab.get('updated') or as_of),symbol,'Estrategia y evidencia',strategy['id'],detail,None,None,None])
    for key,check in (snapshot.get('entry_quality_checks') or {}).items():
        if check.get('symbol') not in closed_symbols:
            decisions.append([stamp(check.get('time') or as_of),check.get('symbol',''),'Calidad de entrada',key,check.get('reason',''),None,None,None])
    return {'schema':1,'build':snapshot.get('build'),'as_of_utc':as_of,'local_time':stamp(as_of),'hours':hours,
        'overview':overview,'warnings':warnings,'pendings':pendings,'closed':closed,'snapshot':snapshot,'verifications':verifications,
        'tables':{'Resumen':summary,'Pendientes':pending_rows,'Runners':runners,'Cierres':close_rows,'Riesgo':risk_rows,
            'Fuentes':source_rows(snapshot.get('research') or {},as_of),'Decisiones':decisions[-1000:]}}


def report_text(model):
    lines=['AKIRA - INFORME OPERATIVO',model['local_time']+' Guatemala',str(model.get('build') or '')]
    lines.extend(model['overview']);lines.extend('REVISAR: '+x for x in model['warnings'])
    for name in ('Resumen','Pendientes','Runners','Riesgo','Cierres'):
        lines.append('\n'+name.upper())
        for row in model['tables'][name][:40]:lines.append(' | '.join('Sin dato' if v is None else str(round(v,4)) if isinstance(v,float) else str(v) for v in row))
    return '\n'.join(lines)


def write_pdf(model,path):
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak,KeepTogether
    except ImportError as exc:raise RuntimeError('Falta reportlab para exportar PDF. Ejecuta de nuevo INSTALAR_AKIRA.cmd.') from exc
    import reportlab
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    # ReportLab ships these redistributable fonts; embed them so PDF viewers do
    # not substitute a different font or lose accents on another computer.
    font_dir=Path(reportlab.__file__).parent/'fonts';regular='Helvetica';bold='Helvetica-Bold'
    if (font_dir/'Vera.ttf').is_file() and (font_dir/'VeraBd.ttf').is_file():
        pdfmetrics.registerFont(TTFont('AkiraReport',str(font_dir/'Vera.ttf')))
        pdfmetrics.registerFont(TTFont('AkiraReportBold',str(font_dir/'VeraBd.ttf')))
        pdfmetrics.registerFontFamily('AkiraReport',normal='AkiraReport',bold='AkiraReportBold',italic='AkiraReport',boldItalic='AkiraReportBold')
        regular='AkiraReport';bold='AkiraReportBold'
    styles=getSampleStyleSheet();styles.add(ParagraphStyle(name='AkiraBody',fontName=regular,fontSize=9,leading=13,spaceAfter=6,textColor=colors.HexColor('#26364A')))
    styles.add(ParagraphStyle(name='AkiraSmall',parent=styles['AkiraBody'],fontSize=8,leading=11))
    styles.add(ParagraphStyle(name='AkiraAnalysis',parent=styles['AkiraBody'],leading=12,spaceAfter=2))
    styles['Title'].textColor=colors.HexColor('#114C67');styles['Heading2'].textColor=colors.HexColor('#114C67')
    for key in ('Title','Heading2','Heading3'):styles[key].fontName=bold
    for key in ('Heading2','Heading3'):styles[key].keepWithNext=True
    def safe(value):
        text='Sin dato' if value is None else f'{value:,.3f}' if isinstance(value,float) else str(value)
        text=text.replace('★','*').replace('☆','-')
        from urllib.parse import urlsplit
        parts=[];pos=0
        for match in re.finditer(r'https?://[^\s<>]+',text):
            url=match.group(0);host=urlsplit(url).hostname or 'Fuente'
            parts.append(escape(text[pos:match.start()]));parts.append('<link href="'+escape(url,{'"':'&quot;'})+'" color="#087E9B">'+escape(host.removeprefix('www.'))+'</link>');pos=match.end()
        parts.append(escape(text[pos:]))
        return ''.join(parts).replace('\n','<br/>')
    def paragraph(value,small=False):return Paragraph(safe(value),styles['AkiraSmall' if small else 'AkiraBody'])
    def table(headers,rows,widths=None):
        data=[[paragraph(x,True) for x in headers]]+[[paragraph(x,True) for x in r] for r in rows]
        t=Table(data,colWidths=widths,repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#DDEDF3')),('VALIGN',(0,0),(-1,-1),'TOP'),
            ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F3F6F9')]),('LINEBELOW',(0,0),(-1,0),.6,colors.HexColor('#92ADBC')),
            ('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
        return t
    story=[Paragraph('AKIRA · INFORME OPERATIVO',styles['Title']),paragraph(model['local_time']+' · Guatemala · '+str(model.get('build') or 'Versión no registrada'))]
    story.extend(paragraph(x) for x in model['overview']);story.extend(paragraph('Revisar: '+x) for x in model['warnings'])
    story.append(Paragraph('Cuenta y capacidad',styles['Heading2']))
    story.append(table(('Dato','Valor','Lectura'),[[r[1],r[2],r[3]] for r in model['tables']['Resumen'] if r[0] in ('Cuenta','Riesgo','Velocidad','Historial')],[130,95,298]))
    story.append(paragraph('Estrellas = evidencia técnica. Cercanía = índice relativo. Ninguno es una probabilidad de ganancias o activación. Generar el informe solo lee datos.'))
    story.append(Paragraph('Resultados propios medidos',styles['Heading2']))
    story.append(table(('Métrica','Resultado','Definición'),[[r[1],f'{r[2]*100:.1f}%' if r[2] is not None and r[1].endswith('Proporción ganadora histórica') else r[2],r[3]] for r in model['tables']['Resumen'] if r[0]=='Resultados'],[180,70,273]))
    story.append(Paragraph('Estudio y comparación',styles['Heading2']))
    story.append(table(('Métrica','Resultado','Alcance'),[[r[1],r[2],r[3]] for r in model['tables']['Resumen'] if r[0]=='Estudio'],[180,70,273]))
    for symbol in (model['snapshot'].get('symbols') or {}):
        if (model['snapshot'].get('markets') or {}).get(symbol,{}).get('scheduled_closed'):continue
        story.append(PageBreak());story.append(Paragraph(safe(symbol+' · Análisis e indicadores'),styles['Heading2']))
        section_titles=('ESTRUCTURA E INDICADORES','DATOS QUE ENTRAN EN LA DECISIÓN','PENDIENTES Y MATEMÁTICAS','FUENTES Y VIGENCIA')
        for line in analysis_text(model['snapshot'],symbol).splitlines():
            if line in section_titles:story.append(Paragraph(safe(line),styles['Heading3']))
            elif line.strip():story.append(Paragraph(safe(line),styles['AkiraAnalysis']))
            else:story.append(Spacer(1,4))
        from operation_verifier import verification
        story.append(Paragraph('Verificación con datos reales',styles['Heading3']))
        verified=verification(model['snapshot'],symbol)
        story.append(table(('Etapa','Estado','Datos y alcance'),[[r['name'],r['state'],r['detail']] for r in verified['stages']],[145,88,290]))
        story.append(paragraph('Progreso '+str(verified['completed'])+'/'+str(verified['total'])+' de comprobaciones con datos disponibles. No es porcentaje de ganancia. Las fuentes opcionales ausentes no paralizan el mapa técnico; las restricciones críticas del Gateway nunca se omiten.',True))
    story.append(PageBreak());story.append(Paragraph('Pendientes y valoración',styles['Heading2']))
    for row in model['tables']['Pendientes']:
        title=f'{row[1]} · {row[2]} · {row[0]} · {row[3]}'
        story.append(KeepTogether([Paragraph(safe(title),styles['Heading3']),
            table(('Entrada','SL','TP','R:R','Riesgo USD','Lote'),[row[4:10]],[99,99,99,65,90,71]),
            paragraph('Colocación: '+str(row[12])+' · '+str(row[13])+' · Guatemala (UTC-6).'),
            paragraph('Valoración: '+str(row[10])+' · '+str(row[11])),Spacer(1,9)]))
    if not model['tables']['Pendientes']:story.append(paragraph('No hay pendientes o propuestas documentadas en esta captura.'))
    if model.get('verifications'):
        story.append(Paragraph('Verificación pendiente por pendiente',styles['Heading2']))
        for row in model['verifications']:
            story.append(Paragraph(safe(row['id']+' · '+row['state']),styles['Heading3']))
            story.append(paragraph(str(row['completed'])+'/'+str(row['total'])+' comprobaciones. Estrategia: '+row['strategy']))
            for stage in row['stages']:story.append(paragraph(stage['name']+' · '+stage['state']+'\n'+stage['detail']))
            story.append(paragraph(row['scope']))
    story.append(Paragraph('Posiciones y gestión de runners',styles['Heading2']))
    for row in model['tables']['Runners']:
        story.append(Paragraph(safe(row[0]+' · '+row[1]),styles['Heading3']));story.append(paragraph(row[9]))
        story.append(paragraph('Ticket '+str(row[10])+' · Solicitud: '+str(row[11] or 'Sin registro')+' · Apertura MT5: '+str(row[12] or 'Sin registro')+' · Guatemala (UTC-6).'))
        if row[3] is not None:story.append(table(('Dirección','Entrada','SL','TP','Riesgo USD','Límite USD'),[[row[2],row[3],row[4],row[5],row[7],row[8]]],[79,99,99,99,77,70]))
    story.append(Paragraph('Reservas por ticket',styles['Heading2']))
    story.append(table(('Ticket','Símbolo / origen','Propiedad','Reserva USD','Margen USD'),[[r[0],r[1]+' / '+r[2],r[3],r[7],r[8]] for r in model['tables']['Riesgo']],[95,135,125,84,84]))
    story.append(Paragraph('Cierres y protección',styles['Heading2']))
    if not model['closed']:story.append(paragraph('No hay cierres completos reconstruibles para el período. Esto no significa que no hubo operaciones: puede faltar historial o haber cierres parciales.'))
    for row in model['closed'][:500]:
        story.append(Paragraph(safe(f'{row["symbol"]} · #{row["ticket"]} · {row["lane"]}'),styles['Heading3']))
        story.append(paragraph(f'Entrada {stamp(row["entry_time"])}; salida {stamp(row["exit_time"])}; duración {row["duration_minutes"]:.1f} min. Neto {row["net_usd"]:.2f} USD. Motivo: {row["cause"]}.'))
        story.append(paragraph('Colocación: '+(stamp(row.get('placed_at')) or 'Sin registro')+' · '+row.get('placement_source','Sin registro de hora')+'.'))
        story.append(paragraph(row['review']))
    if len(model['closed'])>500:story.append(paragraph('PDF muestra los 500 cierres más recientes. Excel conserva todos los cierres reconstruidos.'))
    story.append(Paragraph('Decisiones y cambios',styles['Heading2']))
    story.append(table(('Hora','Símbolo / ticket','Acción','Motivo'),[[r[0],r[1]+' / '+r[3],r[2],r[4]] for r in model['tables']['Decisiones'][-50:]],[95,110,68,250]))
    if len(model['tables']['Decisiones'])>50:story.append(paragraph('PDF incluye los 50 cambios más recientes. Excel incluye hasta 1000 cambios.'))
    story.append(Paragraph('Fuentes y actualidad',styles['Heading2']))
    story.append(table(('Fuente','Fecha / vigencia','Uso y límites'),[[r[0]+' · '+r[1],r[2] or 'Sin dato',r[3]+'\n'+r[4]] for r in model['tables']['Fuentes']],[135,100,288]))
    def footer(canvas,doc):
        canvas.setFont(regular,8);canvas.setFillColor(colors.HexColor('#61778A'))
        canvas.drawString(36,22,'AKIRA · Lectura de datos · Guatemala (UTC-6)');canvas.drawRightString(A4[0]-36,22,str(doc.page))
    SimpleDocTemplate(str(path),pagesize=A4,rightMargin=36,leftMargin=36,topMargin=36,bottomMargin=40,title='Akira - Informe operativo',author='Akira').build(story,onFirstPage=footer,onLaterPages=footer)


def column(index):
    text='';index+=1
    while index:index,n=divmod(index-1,26);text=chr(65+n)+text
    return text


def literal(value):
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]','',str(value))[:32767]


def write_excel(model,path,template=None):
    """Rellenar la plantilla diseñada con artifact-tool; solo biblioteca estándar.

    Conserva estilos, anchos y encabezados. Textos externos son inlineStr:
    ninguna nota de noticias, comentario o símbolo se evalúa como fórmula.
    """
    template=Path(template or Path(__file__).parent/'assets'/'report_template.xlsx')
    if not template.is_file():raise RuntimeError('Falta la plantilla Excel; ejecuta de nuevo INSTALAR_AKIRA.cmd.')
    with zipfile.ZipFile(template) as source,zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as target:
        price_sheet=ET.fromstring(source.read('xl/worksheets/sheet2.xml'))
        money_style=price_sheet.find('.//{'+NS+'}c[@r="I6"]').get('s','0')
        close_sheet=ET.fromstring(source.read('xl/worksheets/sheet4.xml'))
        percentage_style=close_sheet.find('.//{'+NS+'}c[@r="L6"]').get('s','0')
        date_style=close_sheet.find('.//{'+NS+'}c[@r="D6"]').get('s','0')
        for item in source.infolist():
            content=source.read(item.filename)
            match=re.fullmatch(r'xl/worksheets/sheet(\d+)\.xml',item.filename)
            if match:
                index=int(match.group(1))-1
                if index>=len(SHEETS):raise ValueError('Plantilla Excel incompatible')
                name=SHEETS[index];root=ET.fromstring(content);data=root.find('{'+NS+'}sheetData')
                proto=next((r for r in data if r.get('r')=='6'),None)
                cell_styles={re.sub(r'\d+','',c.get('r','')):c.get('s','0') for c in (proto if proto is not None else ())}
                widths={}
                for c in root.findall('./{'+NS+'}cols/{'+NS+'}col'):
                    for n in range(int(c.get('min')),int(c.get('max'))+1):widths[n-1]=float(c.get('width',20))
                for r in list(data):
                    if int(r.get('r','0'))>=6:data.remove(r)
                # A3 siempre contiene la hora y versión de ESTA captura.
                for r in data:
                    if r.get('r')=='3':
                        for c in list(r):r.remove(c)
                        c=ET.SubElement(r,'{'+NS+'}c',{'r':'A3','t':'inlineStr'})
                        ET.SubElement(ET.SubElement(c,'{'+NS+'}is'),'{'+NS+'}t').text=model['local_time']+' · Guatemala · '+str(model.get('build') or '')
                header=data.find("{"+NS+"}row[@r='5']")
                if header is not None:
                    first=next(iter(header),None);header_style=first.get('s','0') if first is not None else '0'
                    for child in list(header):header.remove(child)
                    for ci,title in enumerate(HEADERS[name]):
                        cell=ET.SubElement(header,'{'+NS+'}c',{'r':column(ci)+'5','s':header_style,'t':'inlineStr'})
                        ET.SubElement(ET.SubElement(cell,'{'+NS+'}is'),'{'+NS+'}t').text=title
                cols=root.find('{'+NS+'}cols')
                if cols is not None:
                    for ci in range(len(HEADERS[name])):
                        if ci not in widths:
                            ET.SubElement(cols,'{'+NS+'}col',{'min':str(ci+1),'max':str(ci+1),'width':'27','customWidth':'1'});widths[ci]=27
                rows=model['tables'][name]
                if not rows:rows=[['Sin registros disponibles']+[None]*(len(HEADERS[name])-1)]
                for ri,values in enumerate(rows,6):
                    lines=max((math.ceil(len(str(v or ''))/max(8,widths.get(ci,20)-2)) for ci,v in enumerate(values)),default=1)
                    row=ET.SubElement(data,'{'+NS+'}row',{'r':str(ri),'ht':str(min(200,max(24,lines*14+8))),'customHeight':'1'})
                    for ci,value in enumerate(values):
                        key=column(ci);attrs={'r':key+str(ri),'s':cell_styles.get(key,'0')}
                        if name=='Resumen' and ci==2 and isinstance(value,(int,float)) and str(values[1]).endswith('USD'):attrs['s']=money_style
                        if name=='Resumen' and ci==2 and isinstance(value,(int,float)) and str(values[1]).endswith('Proporción ganadora histórica'):attrs['s']=percentage_style
                        c=ET.SubElement(row,'{'+NS+'}c',attrs)
                        if isinstance(value,(int,float)) and not isinstance(value,bool) and finite(value) is not None:
                            ET.SubElement(c,'{'+NS+'}v').text=str(value)
                        elif value is not None:
                            c.set('t','inlineStr');t=ET.SubElement(ET.SubElement(c,'{'+NS+'}is'),'{'+NS+'}t');t.set('{http://www.w3.org/XML/1998/namespace}space','preserve');t.text=literal(value)
                        date_columns={'Cierres':(3,4,14),'Pendientes':(12,),'Runners':(11,12),'Riesgo':(10,)}
                        if ci in date_columns.get(name,()) and value and re.fullmatch(r'\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}',str(value)):
                            c.set('s',date_style)
                            when=datetime.strptime(str(value),'%d/%m/%Y %H:%M:%S')
                            serial=(when-datetime(1899,12,30)).total_seconds()/86400
                            for child in list(c):c.remove(child)
                            c.attrib.pop('t',None);ET.SubElement(c,'{'+NS+'}v').text=str(serial)
                        if name=='Pendientes' and ci==7 and values[4] is not None and values[5] is not None and values[6] is not None and values[7] is not None:
                            formula=ET.Element('{'+NS+'}f');formula.text=f'IFERROR(ABS(G{ri}-E{ri})/ABS(E{ri}-F{ri}),"")';c.insert(0,formula)
                        if name=='Resumen' and ci==2 and value is not None:
                            expression=None
                            if values[1]=='Reservado USD' and model['tables']['Riesgo'] and not any(r.get('scheduled_closed') for r in model['snapshot'].get('markets',{}).values()):expression='SUM(Riesgo!H6:H'+str(len(model['tables']['Riesgo'])+5)+')'
                            elif values[1]=='Libre USD':expression='MAX(0,C9-C10)'
                            elif values[1]=='Neto de esos cierres USD' and model['tables']['Cierres']:expression='SUM(Cierres!J6:J'+str(len(model['tables']['Cierres'])+5)+')'
                            if expression:
                                formula=ET.Element('{'+NS+'}f');formula.text=expression;c.insert(0,formula)
                end=len(rows)+5;last=column(len(HEADERS[name])-1)
                dimension=root.find('{'+NS+'}dimension')
                if dimension is not None:dimension.set('ref',f'A1:{last}{end}')
                filt=root.find('{'+NS+'}autoFilter')
                if filt is not None:root.remove(filt)
                filt=ET.Element('{'+NS+'}autoFilter',{'ref':f'A5:{last}{end}'});root.insert(list(root).index(data)+1,filt)
                content=ET.tostring(root,encoding='utf-8',xml_declaration=True)
            target.writestr(item,content)


def export_report(model,path,format='pdf',include_diagnostic=True):
    path=Path(path);format=format.lower()
    if format not in ('pdf','xlsx'):raise ValueError('Escoge PDF o Excel')
    path=path.with_suffix('.'+format);path.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix='.akira_report_',suffix='.'+format,dir=path.parent);os.close(fd)
    temporary=Path(temp);companion=None
    try:
        (write_pdf if format=='pdf' else write_excel)(model,temporary)
        os.replace(temporary,path)
        if include_diagnostic:
            companion=path.with_name(path.stem+'_datos.json');temp_json=companion.with_suffix('.tmp')
            temp_json.write_text(json.dumps(clean(model),ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8');os.replace(temp_json,companion)
    finally:temporary.unlink(missing_ok=True)
    return {'path':str(path.resolve()),'diagnostic_path':str(companion.resolve()) if companion else None,'format':format}
