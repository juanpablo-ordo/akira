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

def rich_text(value):
    links=[]
    def link(title,url):
        if not safe_url(url):return title
        links.append('<a style="color:#00ddff" href="'+html.escape(url,quote=True)+'">'+html.escape(title)+'</a>');return '\x00'+str(len(links)-1)+'\x00'
    text=re.sub(r'\[([^\]\n]+)\]\((https?://[^\s)]+)\)',lambda m:link(m[1],m[2]),str(value or ''))
    text=re.sub(r'https?://[^\s<>\x00]+',lambda m:link(source_name(m[0].rstrip('.,;')),m[0].rstrip('.,;')),text)
    text=html.escape(human(text)).replace('\n','<br>');text=re.sub(r'\*\*([^*]+)\*\*',r'<b>\1</b>',text)
    for i,item in enumerate(links):text=text.replace('\x00'+str(i)+'\x00',item)
    return text

def set_document(widget,text,follow=False):
    if getattr(widget,'_studio_document',None)==text:return
    bar=widget.verticalScrollBar();position=bar.value();at_end=position>=bar.maximum()-3;widget._studio_document=text;widget.setHtml(text)
    widget.document().documentLayout().documentSize();bar.setValue(bar.maximum() if follow and at_end else min(position,bar.maximum()))

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

def source_abstract(value):
    if isinstance(value,str):
        try:value=json.loads(value)
        except ValueError:return human(value)
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
