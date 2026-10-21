"""Small, labelled LLM digest; full calculations remain in the technical engine."""
import json
import math

FIELDS=('trend','rsi','adx','atr','volume_ratio','bos','sweep','macd')


def finite(value):
    if isinstance(value,bool):return value
    if isinstance(value,(int,float)) and math.isfinite(value):return round(value,4)
    return None


def build(snapshot,sources,now,stale=600):
    from pending_verification import relevant_source
    symbols={};omitted=0;count=0
    for symbol,info in (snapshot.get('symbols') or {}).items():
        if (snapshot.get('markets') or {}).get(symbol,{}).get('scheduled_closed'):continue
        frames={}
        for tf,row in (info.get('frames') or {}).items():
            frames[tf]=[finite(row.get(k)) for k in FIELDS]
            omitted+=sum(k not in FIELDS for k in row);count+=1
        symbols[symbol]={'bid':finite(info.get('bid')),'ask':finite(info.get('ask')),'frames':frames}
    if not symbols:raise ValueError('No hay activos abiertos para revisar')
    evidence={};omitted_sources=[]
    for name,row in sources.items():
        if not isinstance(row,dict) or not all(relevant_source(name,s) for s in symbols):continue
        stamp=float(row.get('updated') or 0);data=row.get('data')
        if not stamp or not -5<=now-stamp<(86400 if name=='macro:FRED' else stale) or row.get('error') or not data:
            omitted_sources.append(name);continue
        if name.startswith('derivatives:'):
            from providers import public_derivatives_bias
            b,c,detail=public_derivatives_bias(data)
            text=detail[:180]+'; peso '+str(round(c,2))+'; sesgo '+str(round(b,2))
        elif name.startswith('coinglass:'):
            from providers import coinglass_bias
            b,c,detail=coinglass_bias(data);text=detail[:180]
        elif name=='fed' or name=='news' or name.startswith(('global_news:','search:')):
            rows=data.get('items',[]) if isinstance(data,dict) else data if isinstance(data,list) else []
            text='; '.join(str(r.get('title') or '')[:85] for r in rows[:2] if isinstance(r,dict))
        else:continue
        if text:evidence[name]={'age_s':round(max(0,now-stamp)),'excerpt':text}
        if len(evidence)>=2:break
    payload={'columns':list(FIELDS),'sources':evidence,'symbols':symbols,
        'as_of':snapshot.get('as_of_utc') or snapshot.get('updated'),
        'scope':'Resumen parcial, todos los marcos. No se revisan indicadores omitidos. Vídeos solo para estudio; sin permiso de operar.'}
    text=json.dumps(payload,ensure_ascii=False,separators=(',',':'),allow_nan=False)
    # Reduce external excerpts first; NEVER discard the second symbol or a frame.
    while len(text)>1900 and evidence:
        evidence.pop(next(reversed(evidence)));text=json.dumps(payload,ensure_ascii=False,separators=(',',':'),allow_nan=False)
    if len(text)>2600:raise ValueError('El resumen supera el presupuesto del modelo; el análisis técnico continúa')
    return text,{'input_chars':len(text),'active_symbols':list(symbols),'timeframe_count':count,
        'omitted_raw_indicator_values':omitted,'input_scope':'COMPACT_INDICATORS_COMPLETE_TIMEFRAMES',
        'engine_indicators_complete':True,'source_count':len(evidence),'unavailable_sources':omitted_sources,
        'sources_omitted_for_budget':[name for name in sources if name not in evidence],'digest_version':2}


def automatic_targets(view,cfg):
    """No model time for unaffordable proposals; explicit/required checks remain."""
    from pending_verification import targets,identity
    plans=targets(view);required=set(view.get('required_pending_reviews') or [])
    eco=(cfg.get('desktop') or {}).get('performance_profile')=='Ahorro de energía'
    selected=[]
    for p in plans:
        if identity(p) in required:selected.append(p)
        elif not eco and p.get('confirmed'):selected.append(p)
    if not eco:
        cap=float(view.get('trade_risk_cap') or 0)
        for symbol in view.get('symbols') or {}:
            for side in (1,-1):
                choices=[p for p in plans if p['symbol']==symbol and p.get('side')==side and not p.get('confirmed')
                    and p.get('sendable') and isinstance(p.get('risk_usd'),(int,float)) and 0<p['risk_usd']<=cap]
                if choices:selected.append(max(choices,key=lambda p:float(p.get('quality_score') or 0)))
    return list({identity(p):p for p in selected}.values())
