"""Escaped, readable Studio presentation. No broker or execution access."""
import html,json,re
from urllib.parse import urlsplit
from notification_center import safe_text

def human(value):
    text=safe_text(str(value or ''))
    for a,b in {'TimeoutError':'Se agotó el tiempo de espera','JSONDecodeError':'La respuesta no tenía el formato esperado','AUTH_REQUIRED':'El proveedor pide iniciar sesión','Invalid API key provided':'La clave API no fue aceptada','PermissionError':'Windows no permitió acceder al archivo','ConnectionError':'No se pudo conectar','QUEUED':'En espera','RUNNING':'En revisión','COMPLETE':'Revisión terminada','PENDING_REJECTED':'Propuesta descartada','UNSUPPORTED':'No disponible para este instrumento','analyzed':'Analizado'}.items():text=text.replace(a,b)
    return text

def safe_url(value):
    try:
        u=urlsplit(str(value));return str(value) if u.scheme in ('http','https') and u.hostname and not u.username and not u.password else ''
    except ValueError:return ''

def source_name(url):
    host=(urlsplit(url).hostname or 'Fuente').removeprefix('www.')
    return {'news.xbox.com':'Xbox Wire','youtube.com':'YouTube','youtu.be':'YouTube','coinglass.com':'CoinGlass','reuters.com':'Reuters'}.get(host,host)

def readable_math(text):
    """Render common generated math as inert text; leave currency untouched."""
    if '$' not in text and r'\(' not in text and r'\[' not in text:return text
    if '`' in text:
        parts=re.split(r'(```[\s\S]*?```|`[^`\n]*`)',text)
        if len(parts)>1:return ''.join(part if i%2 else readable_math(part) for i,part in enumerate(parts))
    symbols={'pi':'π','theta':'θ','alpha':'α','beta':'β','gamma':'γ','Delta':'Δ','sigma':'σ',
        'lambda':'λ','infty':'∞','cdot':'·','times':'×','leq':'≤','geq':'≥','neq':'≠','pm':'±','to':'→','sum':'Σ','int':'∫'}
    def convert(match):
        value=next(v for v in match.groups() if v is not None)
        if not re.search(r'[\\=^_{}]|^\s*[A-Za-zπθφ]\s*$',value):return match.group(0)
        value=re.sub(r'\\(?:left|right)\b','',value)
        value=re.sub(r'\\(?:mathrm|text|operatorname)\{([^{}]*)\}',r'\1',value)
        value=re.sub(r'\\([A-Za-z]+)\b',lambda m:symbols.get(m[1],m[0]),value)
        for _ in range(8):
            before=value
            value=re.sub(r'\\sqrt\{([^{}]*)\}',r'√(\1)',value)
            value=re.sub(r'\\frac\{([^{}]*)\}\{([^{}]*)\}',r'(\1)/(\2)',value)
            value=re.sub(r'([\^_])\{([^{}]*)\}',r'\1(\2)',value)
            if value==before:break
        value=re.sub(r'\\[,;!]',' ',value)
        return value.strip()
    return re.sub(r'(?<!\\)\$\$([\s\S]*?)\$\$|(?<!\\)\$([^$\n]+)\$|\\\((.*?)\\\)|\\\[([\s\S]*?)\\\]',convert,text)

def rich_text(value):
    links=[]
    def link(title,url):
        if not safe_url(url):return title
        links.append('<a style="color:#00ddff" href="'+html.escape(url,quote=True)+'">'+html.escape(title)+'</a>');return '\x00'+str(len(links)-1)+'\x00'
    text=re.sub(r'\[([^\]\n]+)\]\((https?://[^\s)]+)\)',lambda m:link(m[1],m[2]),str(value or ''))
    text=re.sub(r'https?://[^\s<>\x00]+',lambda m:link(source_name(m[0].rstrip('.,;')),m[0].rstrip('.,;')),text)
    text=html.escape(human(readable_math(text))).replace('\n','<br>');text=re.sub(r'\*\*([^*]+)\*\*',r'<b>\1</b>',text)
    for i,item in enumerate(links):text=text.replace('\x00'+str(i)+'\x00',item)
    return text

def set_document(widget,text,follow=False):
    if getattr(widget,'_studio_document',None)==text:return
    bar=widget.verticalScrollBar();position=bar.value();at_end=position>=bar.maximum()-3;widget._studio_document=text;widget.setHtml(text)
    widget.document().documentLayout().documentSize();bar.setValue(bar.maximum() if follow and at_end else min(position,bar.maximum()))

def next_query(row):
    if row.get('enabled') is False:return '—'
    if row.get('waiting_for_worker'):return 'Esperando conexión'
    if row.get('inflight'):return 'En curso'
    seconds=max(0,round(float(row.get('retry_after_seconds') or 0)))
    if seconds>=3600:return 'En '+str((seconds+3599)//3600)+' h'
    if seconds>=60:return 'En '+str((seconds+59)//60)+' min'
    return 'En '+str(seconds)+' s' if seconds else 'Al estar lista'

INDICATORS={'ema9':'Tendencia rápida (9 velas)','ema21':'Tendencia corta (21 velas)','ema50':'Tendencia media (50 velas)','ema200':'Tendencia de fondo (200 velas)','rsi':'Fuerza de compras y ventas (RSI)','atr':'Movimiento habitual del precio (ATR)','adx':'Fuerza de la tendencia (ADX)','macd':'Impulso (MACD)','volume_ratio':'Volumen frente a lo habitual','bos':'Ruptura de estructura','sweep':'Barrido de liquidez','range_hi':'Techo del rango','range_lo':'Suelo del rango','vwap':'Precio medio ponderado por volumen'}

def frame_html(frames):
    result=[]
    for tf,row in (frames or {}).items():
        result.append('<h3>'+html.escape(tf)+'</h3><table cellspacing="8">')
        for key,value in row.items():
            if key in ('bars','last_bar') or isinstance(value,(dict,list)):continue
            if isinstance(value,float):value=f'{value:,.4f}'
            result.append('<tr><td>'+html.escape(INDICATORS.get(key,key.replace('_',' ').capitalize()))+'</td><td>'+html.escape(str(value))+'</td></tr>')
        result.append('</table>')
    return ''.join(result) or '<p>Aún no se recibieron indicadores del terminal.</p>'

def budget_summary(portfolio,private=False):
    cap=float(portfolio.get('cap_usd') or 0);used=float(portfolio.get('reserved_usd') or 0);available=float(portfolio.get('available_usd',max(0,cap-used)) or 0)
    percent=min(100,max(0,round(used/cap*100))) if cap>0 else 0
    return ('Importes ocultos. Pulsa el ojo de la cuenta para verlos.' if private else f'Presupuesto conjunto: {cap:,.2f} USD\nReservado en órdenes y posiciones: {used:,.2f} USD\nDisponible: {available:,.2f} USD\n\nEl porcentaje indica presupuesto reservado; no mide ganancias.'),percent


def risk_dashboard(view,config,private=False):
    from risk_limits import configured_limits
    connected=bool(view.get('connected'));account=(view.get('account') or {}) if connected else {}
    limits=configured_limits(config,account);ledger=view.get('portfolio_risk') or {}
    actor=view.get('configured_execution') or {}
    applied=connected and actor.get('risk')==config['risk'] and (actor.get('runner') or {}).get('max_trade_budget_pct')==config['runner']['max_trade_budget_pct']
    state='Aplicado en el motor' if applied else 'Guardado; esperando la actualización del motor' if connected else 'Guardado; pendiente de conectar MT5'
    if view.get('preview'):state='Vista previa · no es una cuenta conectada al bróker'
    money=lambda value:f"{float(value):,.2f} {limits['currency']}"
    used=float(ledger.get('reserved_usd',view.get('reserved_risk',0)) or 0)
    if not limits['ready']:
        return {'ready':False,'state':state,'limits':limits,'configured':'Tus límites están guardados. Conecta MT5 para calcular los importes de esta cuenta.',
            'usage':'Esperando órdenes y posiciones de MT5.','caption':'Límites guardados · conecta MT5',
            'metric_value':'••••••' if private else '—','metric_caption':'Importe pendiente de conectar MT5',
            'budget_format':'Esperando datos de la cuenta','usage_format':'Esperando datos de la cuenta','budget_pct':0,'used_pct':0}
    cap=limits['portfolio'];available=max(0,cap-used)
    count=int(ledger.get('pending_orders',len(view.get('orders') or [])))+int(ledger.get('positions',len(view.get('positions') or [])))
    provisional=bool(ledger.get('unconfirmed_requests')) or not ledger.get('risk_known',True)
    usage_note='Hay una reserva provisional a la espera de confirmación de MT5.' if provisional else 'Sin órdenes ni posiciones: todavía no hay riesgo reservado.' if not count and used==0 else 'Reserva confirmada de órdenes y posiciones.'
    total_choice=money(limits['portfolio_money']) if limits['portfolio_money']>0 else 'sin tope adicional en dinero'
    configured=(f"Por orden: hasta {money(limits['per_trade'])}\nElegiste {money(limits['trade_money'])} y {limits['trade_pct']:g}% del patrimonio."
        f"\nRunner directo: hasta {money(limits['runner'])}\nPresupuesto conjunto: {money(cap)}"
        f"\nElegiste {limits['portfolio_pct']:g}% del capital y {total_choice}. Se usa el menor límite aplicable.")
    if limits['per_trade']<=0:configured+='\nEl límite por orden es cero: los topes en dinero y porcentaje deben ser mayores que cero para habilitar riesgo.'
    elif not limits.get('override'):
        binding='el tope en dinero' if limits['trade_money']<=limits['equity']*limits['trade_pct']/100 else 'el porcentaje del patrimonio'
        configured+='\nEn esta cuenta manda '+binding+' para el límite por orden.'
    if limits.get('override'):configured+='\nEl permiso extra para el lote mínimo estructural está incluido en el tope por orden.'
    usage=f"En uso: {money(used)}\nDisponible para nuevas órdenes: {money(available)}\n{usage_note}"
    if used>cap:usage+='\nEl riesgo reservado supera el límite guardado; no queda presupuesto para nuevas entradas.'
    if private:
        configured='Límites ocultos. Pulsa el ojo de la cuenta para ver los importes.'
        usage=usage_note;caption='Límites ocultos · Ajustar riesgo'
    else:caption=f"Por orden: {money(limits['per_trade'])}\nConjunto: {money(cap)}"
    metric_caption='Importes ocultos · Ajustar límites' if private else f"En uso: {money(used)}\nConjunto: {money(cap)}"
    return {'ready':True,'state':state,'limits':limits,'configured':configured,'usage':usage,'caption':caption,
        'metric_value':'••••••' if private else money(limits['per_trade']),'metric_caption':metric_caption,
        'budget_format':'%p% del capital habilitado' if private else money(cap)+' · %p% del capital',
        'usage_format':'%p% del presupuesto en uso' if private else money(used)+' en uso · %p% del presupuesto',
        'budget_pct':round(limits['portfolio_capital_pct']),
        'used_pct':min(100,max(0,round(used/cap*100))) if cap>0 else 100 if used>0 else 0}


def set_plain_document(widget,text):
    if getattr(widget,'_studio_plain_document',None)==text:return
    bar=widget.verticalScrollBar();position=bar.value()
    widget._studio_plain_document=text;widget.setPlainText(text);bar.setValue(min(position,bar.maximum()))


def source_content_key(research):
    def freeze(value):
        if isinstance(value,dict):return tuple((key,freeze(item)) for key,item in value.items())
        if isinstance(value,(list,tuple)):return tuple(freeze(item) for item in value)
        return value
    fields=('url','title','author','source','published','date','status','state','summary','text','note')
    return tuple((group,tuple(tuple(freeze(item.get(key)) for key in fields) for item in research.get(group) or [] if isinstance(item,dict))) for group in ('news','videos'))

def source_abstract(value):
    if isinstance(value,str):
        try:value=json.loads(value)
        except ValueError:return human(value)
    if isinstance(value,dict) and value.get('coverage'):
        labels={'open_interest':'Interés abierto','premium':'Coste de financiación','depth':'Libro de órdenes','global_ls':'Proporción de compras y ventas','oi_history':'Historial de interés abierto','taker_ratio':'Actividad de compradores y vendedores'}
        return str(value.get('detail') or '')+'\n\nDatos disponibles: '+', '.join(labels.get(k,k) for k in value['coverage'])
    if isinstance(value,dict):return '\n'.join(human(k.replace('_',' ').capitalize())+': '+human(v) for k,v in value.items() if not isinstance(v,(dict,list))) or 'Contenido recibido y guardado como contexto. Revisa su fecha y disponibilidad.'
    return human(value)

def market_activity(view,symbol):
    """Explain one asset using actor facts only; a quote is not an execution."""
    row=(view.get('symbols') or {}).get(symbol) or {};decision=row.get('decision') or {}
    status=(view.get('status') or {}).get(symbol) or {};market=(view.get('markets') or {}).get(symbol) or {}
    title='Oro' if symbol.startswith('XAU') else 'Bitcoin' if symbol.startswith('BTC') else symbol
    state=human(decision.get('state') or status.get('state') or 'Esperando datos')
    detail=human(decision.get('reason') or status.get('detail') or 'Esperando condiciones válidas para una pendiente.')
    if view.get('connected') is False:state='Sin conexión con MT5';detail='Esperando el terminal; no se envían nuevas órdenes.'
    elif market.get('scheduled_closed'):
        state='Mercado cerrado';detail=human(status.get('detail') or market.get('state') or 'Esperando la sesión de este instrumento.')
    checked=row.get('checked_at');now=view.get('as_of_utc') or view.get('updated')
    try:
        age=float(now)-float(checked) if checked else None
        checked_text='Revisado hace '+str(max(0,round(age)))+' s' if age is not None and age>=-5 else 'Hora de evaluación no confirmada' if checked else 'Esperando la primera evaluación'
    except (TypeError,ValueError):checked_text='Hora de evaluación no confirmada'
    count=int(decision.get('confirmed_pending_orders') or sum(1 for p in row.get('pending_book') or [] if p.get('confirmed') and p.get('ticket')))
    evaluated=int(decision.get('evaluated_scenarios') or 0)
    counts=str(count)+' pendiente(s) confirmada(s) · '+str(evaluated)+' escenarios evaluados'
    return {'title':title,'state':state,'detail':detail,'checked':checked_text,'counts':counts,
        'text':title+' · '+state+'\n'+checked_text+' · '+str(count)+' pendiente(s)\n'+detail}

def plan_summary(plan,frames=None):
    def price(key):
        try:return f'{float(plan[key]):,.4f}'.rstrip('0').rstrip('.')
        except (KeyError,ValueError,TypeError):return 'sin dato'
    side='compra' if plan.get('side')==1 else 'venta';intent='un retroceso' if plan.get('kind')=='LIMIT' else 'una ruptura confirmada'
    text='<h3>Qué propone Akira</h3><p>Una '+side+' que espera '+intent+'. Entrada: <b>'+price('entry')+'</b>.</p><h3>Protección y objetivo</h3><p>Protección en '+price('sl')+' y objetivo observado en '+price('tp')+'. Si cambia la estructura, Akira evalúa si debe modificar o retirar la pendiente.</p>'
    facts=[]
    for tf,row in (frames or {}).items():
        if tf not in ('M15','H1','H4','D1') or not isinstance(row,dict):continue
        trend=row.get('trend')
        if isinstance(trend,(int,float)):facts.append(tf+': tendencia '+('alcista' if trend>.1 else 'bajista' if trend<-.1 else 'sin dirección clara'))
    text+='<h3>Datos que sustentan la idea</h3><p>'+rich_text('\n'.join(facts) or 'No hay desglose de indicadores asociado a este ticket.')+'</p>'
    if plan.get('reason'):text+='<h3>Observación del análisis</h3><p>'+rich_text(plan['reason'])+'</p>'
    return text

def report_html(report):
    from operation_report import HEADERS
    result=['<h2>Informe de actividad</h2>']
    for title,rows in (report.get('tables') or {}).items():
        result.append('<h3>'+html.escape(title)+'</h3><table cellspacing="7"><tr>'+''.join('<th>'+rich_text(x)+'</th>' for x in HEADERS.get(title,[]))+'</tr>')
        for row in rows[:120]:result.append('<tr>'+''.join('<td>'+rich_text(x)+'</td>' for x in row)+'</tr>')
        result.append('</table>' if rows else '</table><p>No hay registros en este período.</p>')
    return ''.join(result)
