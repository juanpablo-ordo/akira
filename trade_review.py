"""Valoración explicable con datos del motor; sin red, modelos ni acceso MT5."""
import math
import re

PERIODS={'M1':60,'M5':300,'M15':900,'M30':1800,'H1':3600,'H4':14400,'D1':86400,'W1':604800}


def finite(value,default=None):
    try:
        value=float(value)
        return value if math.isfinite(value) else default
    except (TypeError,ValueError):return default


def source_timeframe(row):
    if row.get('timeframe') in PERIODS:return row['timeframe']
    key=str(row.get('key','')).upper()
    for token in key.split(':'):
        if token in PERIODS:return token
    if row.get('lane')=='RUNNER':return str(row.get('signal_timeframe') or 'M15')
    match=re.search(r'\b(M1|M5|M15|M30|H1|H4|D1|W1)\b',str(row.get('reason','')).upper())
    return match.group(1) if match else ''


def frame_value(frame,key,default=None):
    return frame.get(key,default) if isinstance(frame,dict) else getattr(frame,key,default)


def assess_plan(row,frames=None,now=None,quote=None):
    frames=frames or {};side=1 if row.get('side') in (1,'BUY','LONG') else -1
    entry,sl,tp=(finite(row.get(k),0.0) for k in ('entry','sl','tp'))
    risk=side*(entry-sl) if entry>0 and sl>0 else 0
    reward=side*(tp-entry) if entry>0 and tp>0 else 0
    rr=reward/risk if risk>0 and reward>0 else None
    quality=finite(row.get('quality_score'));activation=finite(row.get('activation_score'))
    count=0 if quality is None or quality<=0 else 5 if quality>=95 else 4 if quality>=87 else 3 if quality>=78 else 2 if quality>=65 else 1
    tf=source_timeframe(row);source=frames.get(tf)
    atr=finite(row.get('horizon_atr'),0.0) or finite(frame_value(source,'atr'),0.0) or finite(row.get('atr'),0.0)
    ratio=risk/atr if risk>0 and atr>0 else None
    evidence=[];warnings=[]
    if entry<=0 or sl<=0 or tp<=0:
        count=0;warnings.append('Faltan niveles completos de entrada, SL o TP; no calcular R:R ni calificar la geometría.')
    elif risk<=0 or reward<=0:
        count=0;warnings.append('Entrada, SL y TP no forman una geometría válida.')
    else:evidence.append(f'R:R {rr:.2f}; distancia al SL {risk:.3f}; recorrido al TP {reward:.3f}.')
    if ratio is None:
        count=min(count,3);warnings.append('Falta ATR del horizonte original para valorar el espacio del SL.')
    else:
        evidence.append(f'SL de {ratio:.2f} ATR del horizonte {tf or "registrado"}.')
        if ratio<.25:
            count=min(count,3);warnings.append('SL inferior a 0,25 ATR del horizonte; sensible a retrocesos y ruido.')
        elif ratio<.35:
            count=min(count,4);warnings.append('SL ajustado: comprobar la invalidación y el ruido del horizonte.')
    reason=str(row.get('reason','')).lower()
    observed=row.get('target_observed')
    if observed is None:
        # La entrada puede nacer de un swing observado mientras el TP sigue
        # siendo una proyección. Exigir evidencia referida al OBJETIVO.
        if any(x in reason for x in ('proyectad','projected','proyección','proyeccion')) or re.search(r'(?:objetivo|target|breakout)[^;]{0,45}m[ií]nimo',reason):observed=False
        elif re.search(r'(?:objetivo|target|tp)[^;]{0,65}(?:observad|observed|swing|estructura)',reason):observed=True
    if observed is False:
        count=min(count,3);warnings.append('El objetivo incluye proyección; no equivale a una zona objetivo observada.')
    elif observed is None:
        count=min(count,4);warnings.append('La procedencia del objetivo no está identificada en el registro.')
    else:evidence.append('Objetivo sustentado en estructura observada.')
    h1=frames.get('H1');trend=finite(frame_value(h1,'trend'))
    if trend is not None:
        if side*trend<-.18:
            count=min(count,3);warnings.append('La dirección va contra el impulso H1; necesita confirmación de reversión.')
        else:evidence.append('Dirección compatible con H1.' if side*trend>=.18 else 'H1 sin impulso direccional fuerte.')
    if quote and finite(quote.get('spread'),0)>0 and risk>0:
        spread=finite(quote['spread'],0)
        if risk<spread*3:
            count=min(count,2);warnings.append('El SL deja menos de tres spreads de espacio.')
    freshness='sin datos de antigüedad'
    bars=frame_value(source,'bars',())
    last=frame_value(source,'last_bar')
    if last is None and isinstance(bars,(list,tuple)) and bars:
        last=frame_value(bars[-1],'time')
    if now is not None and tf in PERIODS and finite(last) is not None:
        age=float(now)-(float(last)+PERIODS[tf]);freshness='velas actuales' if -2<=age<=PERIODS[tf]+60 else 'velas desactualizadas'
        if freshness=='velas desactualizadas':count=min(count,2);warnings.append('Velas del horizonte desactualizadas; revisar antes de una nueva entrada.')
    required=finite(row.get('risk_usd'))
    if required is None:required=finite(row.get('required_risk_usd'))
    if required is None:required=finite((row.get('funding') or {}).get('minimum_risk_usd'))
    cap=finite(row.get('risk_cap_usd'))
    if cap is not None and required is not None and required>cap+1e-8:warnings.append(f'Riesgo {required:.2f} superior al límite por operación {cap:.2f}.')
    if row.get('block_reason'):warnings.append(str(row['block_reason']))
    confirmed=bool(row.get('confirmed'));state='Confirmada en MT5' if confirmed else 'Lista para enviar' if row.get('sendable') else 'Propuesta sin envío confirmado'
    return {'stars':count,'label':'★'*count+'☆'*(5-count) if count else 'Sin valoración suficiente',
        'quality_score':quality,'activation_score':activation,'rr':rr,'stop_distance':risk if risk>0 else None,
        'reward_distance':reward if reward>0 else None,'source_timeframe':tf,'source_atr':atr or None,
        'stop_atr_ratio':ratio,'target_observed':observed,'freshness':freshness,'state':state,
        'risk_usd':required,'risk_cap_usd':cap,'evidence':evidence,'warnings':list(dict.fromkeys(warnings)),
        'meaning':'Estrellas de evidencia técnica; no son probabilidad de ganancias. Cercanía tampoco es probabilidad de activación.'}


def assessment_text(row):
    a=row.get('assessment') or assess_plan(row)
    lines=[a['label']+' · '+a['state'],a['meaning']]
    if a.get('quality_score') is not None:lines.append(f'Índice técnico {a["quality_score"]:.1f}/100; cercanía {finite(a.get("activation_score"),0):.0f}/100.')
    lines.extend(a['evidence']);lines.extend('Revisar: '+s for s in a['warnings'])
    return '\n'.join(lines)
