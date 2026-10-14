"""Decisiones rápidas y tarjetas operativas; nunca llama a modelos ni a MT5.

El actor valida y ejecuta. Esta capa interpreta el pedido y presenta evidencia,
sin convertir un seguimiento de formato en una nueva orden financiera.
"""
import math
import re
from conversation_state import folded, is_technical_request
from trade_review import assess_plan,assessment_text
from selection_evidence import quality_text


def target_symbol(message):
    text=folded(message)
    btc=bool(re.search(r'\b(?:btc\w*|bitcoin)\b',text))
    gold=bool(re.search(r'\b(?:oro|gold|xau\w*)\b',text))
    return 'ALL' if btc==gold else 'BTCUSDm' if btc else 'XAUUSDm'


def fast_command(message, previous='', analysis_only=False, pending_execution=False):
    text=folded(message)
    prior=folded(previous)
    if all(re.search(r'\b'+key+r'\s*[:=]?\s*\d',text) for key in ('(?:entry|entrada|e)','sl','tp')):return None
    formatting=bool(re.search(r'\bestrellas?\b',text) or re.fullmatch(
        r'(?:damelas|damelos|muestralas|muestralos|ordenalas|ordenalos)(?:\s+.*)?',text)
        or (len(text)<180 and re.match(r'^(?:y (?:en|con|para)|ahora (?:con|en|para))\b',text)))
    runner=bool(re.search(r'\b(?:runner\w*|longs?|shorts?|orden(?:es)? normales?)\b',text))
    raw_runner=runner
    pending=bool(re.search(r'\bpendient\w*\b',text))
    if formatting and not (runner or pending or is_technical_request(text)):
        if not is_technical_request(prior) and not re.search(r'\b(?:longs?|shorts?)\b',prior):return None
        runner=bool(re.search(r'\b(?:runner\w*|longs?|shorts?|orden(?:es)? normales?)\b',prior))
        pending=bool(re.search(r'\bpendient\w*\b',prior))
    if not (runner or pending or is_technical_request(text) or formatting):return None
    # Solo las palabras de ESTE mensaje autorizan operar; nunca las del anterior.
    analysis_only=analysis_only or bool(re.search(r'\b(?:sin (?:operar|ejecutar|enviar|colocar)|solo (?:analisis|parametros)|no operes)\b|'
        r'\bno\s+(?:(?:quiero|permito)\s+que\s+)?(?:(?:me|los|las|lo|la|se)\s+)*(?:pon\w*|pong\w*|coloc\w*|met\w*|ejecut\w*|envi\w*|abr\w*|activ\w*)',text))
    open_runner=raw_runner and not analysis_only and bool(re.search(
        r'\b(?:pon\w*|coloc\w*|met[ea]\w*|ejecut\w*|envi\w*|abre\w*|abrir|activa\w*)\b',text))
    execute=not analysis_only and (pending_execution or open_runner)
    mode='trade' if runner and pending else 'runner' if runner else 'pending'
    action='assistant_'+('best_' if execute else 'analyze_')+mode
    symbol_text=text if re.search(r'\b(?:btc\w*|bitcoin|oro|gold|xau\w*)\b',text) else (prior if formatting else text)
    command={'action':action,'symbol':target_symbol(symbol_text)}
    long=bool(re.search(r'\blongs?\b',text));short=bool(re.search(r'\bshorts?\b',text))
    if mode in ('runner','trade') and long!=short:command['runner_side']='BUY' if long else 'SELL'
    return command


def number(value, default=0.0):
    try:
        n=float(value)
        return n if math.isfinite(n) else default
    except (ValueError,TypeError):return default


def stars(row):
    assessment=row.get('assessment')
    if isinstance(assessment,dict) and 'stars' in assessment:
        count=int(assessment['stars'])
        return '⭐'*count+'☆'*(5-count) if count else 'sin calificación validada'
    quality=row.get('quality_score')
    if quality is None or number(quality)<=0:return 'sin calificación validada'
    score=number(quality)
    count=5 if score>=95 else 4 if score>=87 else 3 if score>=78 else 2 if score>=65 else 1
    return '⭐'*count+'☆'*(5-count)


def priority(row):
    # Una geometría financiable y actual tiene prioridad sobre un plan imposible
    # de enviar. Las puntuaciones no representan probabilidades estadísticas.
    executable=2 if row.get('confirmed') else 1 if row.get('sendable') else 0
    return (executable, number(row.get('quality_score'))*.65+number(row.get('activation_score'))*.35)


def plan_line(row, runner=False):
    side=row.get('side')
    buy=side in (1,'BUY','LONG')
    name=('LONG' if buy else 'SHORT') if runner else ('BUY' if buy else 'SELL')+' '+str(row.get('kind','?'))
    entry,sl,tp=(number(row.get(k)) for k in ('entry','sl','tp'))
    risk=(entry-sl) if buy else (sl-entry)
    reward=(tp-entry) if buy else (entry-tp)
    rr=reward/risk if risk>0 else 0
    text=f'{stars(row)} {name} · Entry={entry:g} · SL={sl:g} · TP={tp:g} · R:R {rr:.2f}'
    if row.get('confirmed') and int(row.get('ticket') or 0)>0:text+=f" · MT5 confirmado #{int(row['ticket'])}"
    else:text+=' · '+str(row.get('block_reason') or row.get('scenario_state') or 'ANÁLISIS · sin envío confirmado')
    funding=row.get('funding') or {}
    required=row.get('required_risk_usd') or funding.get('minimum_risk_usd') or row.get('risk_usd')
    cap=row.get('risk_cap_usd')
    if required is not None and cap is not None:
        text+=f' · riesgo mínimo ${number(required):.2f} / límite ${number(cap):.2f}'
    assessment=row.get('assessment') or {}
    if assessment.get('warnings'):text+='\n  Revisar: '+str(assessment['warnings'][0])
    return text


def instant_review(message,snapshot,previous='',now=None):
    """Explicar la captura ya recibida, fuera del lock del LLM y sin operar."""
    text=folded(message)
    comparison=bool(re.search(r'\b(?:probabil\w*|porcentaj\w*|compar\w*|verifica\w*|confirma\w*|comproba\w*|mejores?)\b',text)
        and re.search(r'\b(?:pendient\w*|orden\w*|oro|xau\w*|btc\w*|bitcoin|akira)\b',text+' '+folded(previous)))
    asks_to_trade=bool(re.search(r'\b(?:pon\w*|coloc\w*|met[ea]\w*|ejecut\w*|envi\w*|abre\w*|abrir|activa\w*)\b',text))
    if comparison and not asks_to_trade:
        from quality_study import quality_text as account_quality_text
        return account_quality_text(snapshot or {})
    if not re.search(r'\b(?:calidad|valora\w*|evalua\w*)\b|\bcomo (?:la |lo |las |los )?ves\b',text):return None
    # Un pedido explícito de colocar conserva su vía del actor y validación viva.
    if re.search(r'\b(?:pon\w*|coloc\w*|met[ea]\w*|ejecut\w*|envi\w*|abre\w*|abrir|activa\w*)\b',text):return None
    if not re.search(r'\b(?:pendient\w*|orden\w*|runner\w*|oro|xau\w*|btc\w*|bitcoin)\b',text+' '+folded(previous)):return None
    snapshot=snapshot or {};symbols=snapshot.get('symbols') or {}
    if not symbols:return None
    captured=number(snapshot.get('as_of_utc') or snapshot.get('updated'))
    if now is not None and captured and now-captured>15:
        return 'La captura MT5 tiene más de 15 segundos. Actualiza la conexión antes de valorar estas órdenes como vigentes.'
    target=target_symbol(text if target_symbol(text)!='ALL' else previous)
    ticket=re.search(r'#\s*(\d+)|\bticket\s+(\d+)',text)
    ticket=(ticket.group(1) or ticket.group(2)) if ticket else None
    lines=['Valoración del último ciclo MT5:']
    found=False
    for symbol,info in symbols.items():
        if target!='ALL' and not symbol.upper().startswith(target[:3]):continue
        rows=info.get('scenario_book') or info.get('pending_book') or []
        rows=[r for r in rows if str(r.get('ticket'))==ticket] if ticket else [r for r in rows if r.get('confirmed')]
        for item in rows:
            row=dict(item);row['assessment']=row.get('assessment') or assess_plan(row,info.get('frames'),captured,info)
            lines.extend([symbol+' · '+plan_line(row),assessment_text(row)]);found=True
        runner=info.get('runner') or {}
        lines.append(symbol+' · Runner: '+str(runner.get('state') or 'Sin diagnóstico')+' · '+str(runner.get('detail') or 'Sin motivo registrado'))
    if not found:lines.append('No hay una pendiente confirmada que coincida en esta captura. Las propuestas del mapa todavía requieren validación y confirmación MT5.')
    ledger=snapshot.get('portfolio_risk') or {}
    if ledger:
        lines.append(f'Riesgo conjunto: reservado {number(ledger.get("reserved_usd")):.2f}, libre {number(ledger.get("available_usd")):.2f}; límite por operación '+
            (f'{number(snapshot["trade_risk_cap"]):.2f}.' if snapshot.get('trade_risk_cap') is not None else 'no registrado.'))
        external=[r for r in ledger.get('rows',[]) if not r.get('owned') and number(r.get('reserved_usd'))>0]
        for r in external:lines.append(f'Manual / externa #{r.get("ticket")}: reserva {number(r.get("reserved_usd")):.2f} en {r.get("symbol","")}.')
    lines.append('Para evaluar cierres y motivos del SL, abre GENERAR INFORME · PDF / EXCEL. Esta revisión no envía ni cambia órdenes.')
    return '\n'.join(lines)


def trade_result_text(result):
    if not isinstance(result,dict):
        return '🐾 Solicitud en cola; aún no tengo confirmación de MT5. Revisa TERMINAL antes de repetirla.'
    rows=result.get('results')
    if not isinstance(rows,list):
        return '🐾 '+str(result.get('detail') or result.get('error') or result.get('note') or 'Sin confirmación de MT5')
    lines=['🐾 Resultado real del motor:']
    ledger=result.get('portfolio_risk') or {}
    if ledger and ledger.get('available_usd',0)<=0:
        from risk_reservations import reservation_reason
        lines.append(reservation_reason(ledger))
    for row in rows:
        lines.append(str(row.get('symbol','?'))+' · '+str(row.get('detail') or 'Sin detalle'))
        runner=row.get('runner') or {}
        plan=runner.get('plan')
        positions=[p for p in row.get('positions',[]) if p.get('confirmed') and int(p.get('ticket') or 0)>0]
        if positions:
            for p in positions:lines.append(plan_line(p,runner=True))
        elif plan:
            lines.append(plan_line({**plan,'confirmed':False,'scenario_state':runner.get('state'),
                'block_reason':runner.get('detail'),'risk_usd':runner.get('risk'),
                'risk_cap_usd':row.get('risk_cap_usd'),'funding':runner.get('funding') or {}},runner=True))
        elif runner:lines.append('RUNNER · '+str(runner.get('detail') or runner.get('state') or 'Esperando confirmación'))
        levels=[x for x in row.get('levels',[]) if int(x.get('ticket') or 0)>0 and x.get('confirmed') is True]
        for x in levels:lines.append(plan_line(x))
        # Mostrar las mejores alternativas por lado; las cuatro geometrías y el
        # audit completo permanecen en el mapa y en EXPORTAR ESTADO.
        scenarios=[x for x in row.get('scenarios',[]) if not x.get('confirmed')]
        for side in (1,-1):
            candidates=[x for x in scenarios if x.get('side')==side]
            if candidates and not any(x.get('side') in (side,'BUY' if side==1 else 'SELL') for x in levels):
                lines.append(plan_line(max(candidates,key=priority)))
        if row.get('unconfirmed'):lines.append('Envío pendiente de reconciliación MT5; no repetir la orden.')
    lines.append('Estrellas = prioridad técnica relativa; no son probabilidad de ganancias ni garantía de activación.')
    return '\n'.join(lines)
