"""Entradas M15 o retest M5, con tesis y gestión M15/H1; nunca scalping."""
from strategy import Plan, structural_target
import math


def _m15_runner_plan(symbol, frames, quote, cfg, context=None):
    rules = cfg['runner']
    if not rules['enabled']:
        return None, 'Runners desactivados'
    m15, h1 = frames.get('M15'), frames.get('H1')
    if not m15 or not h1 or len(m15.bars) < 14:
        return None, 'Esperando estructura M15/H1'
    atr = float(m15.atr)
    if atr <= 0:
        return None, 'ATR M15 inválido'
    last, previous = m15.bars[-1], m15.bars[-2]
    width = max(last.high-last.low, 1e-9)
    body = abs(last.close-last.open)/width
    if width > atr*rules['max_signal_range_atr']:
        return None, 'Vela extendida: preparar retroceso pendiente, no perseguir'
    for side in (1, -1):
        if side*h1.trend < rules['min_h1_alignment'] or side*m15.trend < .12:
            continue
        if side*(last.close-last.open) <= 0 or body < rules['min_body_fraction']:
            continue
        if (side == 1 and m15.rsi > 78) or (side == -1 and m15.rsi < 22):
            continue
        history = m15.bars[-10:-1]
        level = max(b.high for b in history) if side == 1 else min(b.low for b in history)
        breakout = side*(last.close-level) >= atr*.025
        signal = 'ruptura M15 confirmada'
        if not breakout:
            old = m15.bars[-11:-2]
            level = max(b.high for b in old) if side == 1 else min(b.low for b in old)
            touched = last.low <= level+atr*.20 if side == 1 else last.high >= level-atr*.20
            retest=(side*(previous.close-level) > atr*.025 and touched and side*(last.close-level) > atr*.025)
            if retest:signal = 'retest M15 confirmado'
            elif rules.get('allow_continuation',True):
                # Continuación normal tras retroceso observado: H1/M15 siguen
                # alineados, recupera EMA21 y rompe la estructura de tres velas.
                # No exige volver a romper el máximo/mínimo de diez velas.
                prior=m15.bars[-4:-1]
                base=float(m15.slow)
                pulled=any((b.low<=base+atr*.20 if side==1 else b.high>=base-atr*.20)
                           and side*(b.close-base)>=-atr*.15 for b in prior)
                established=side*(m15.bars[-5].close-base)>atr*.10
                level=max(b.high for b in prior) if side==1 else min(b.low for b in prior)
                if not (pulled and established and side*(last.close-base)>atr*.10 and side*(last.close-level)>=atr*.025):continue
                signal='continuación M15 tras retroceso y recuperación confirmados'
            else:continue
        entry = quote.ask if side == 1 else quote.bid
        if side*(entry-level) < 0 or abs(entry-last.close) > atr*rules['max_entry_drift_atr']:
            return None, 'Precio salió de la ventana del runner; conservar escenarios pendientes'
        if side*(entry-level) > atr*rules['max_extension_atr']:
            return None, 'Ruptura ya extendida; esperar nueva estructura'
        anchor = min(b.low for b in m15.bars[-3:]) if side == 1 else max(b.high for b in m15.bars[-3:])
        buffer = max(atr*.15, quote.spread*2)
        sl = anchor-side*buffer+(quote.spread if side == -1 else 0)
        risk = side*(entry-sl)
        if risk < atr*rules['min_stop_atr'] or risk > atr*rules['max_stop_atr']:
            return None, 'Invalidación M15 fuera de la distancia estructural del runner'
        target, target_reason = structural_target(frames, side, entry, sl, atr, 'RUNNER')
        if 'proyección' in target_reason:
            if rules['require_observed_target']:
                return None, 'Esperando objetivo observado por delante'
            target = entry+side*risk*rules['projected_target_r']
            target_reason = 'TP proyectado en R; sin swing observado por delante'
        elif side == -1:
            target += quote.spread
        if side*(target-entry)/risk < rules['min_rr']:
            return None, 'El siguiente obstáculo no deja recorrido suficiente'
        volume = max(0.0, min(2.0, m15.volume_ratio))
        score = min(98.0, 72+body*10+min(10.0, side*h1.trend*8)+min(6.0, volume*3))
        quality = min(98.0, score+2)
        if score < rules['min_score'] or quality < rules['min_quality']:
            continue
        # Contexto YA disponible; nunca esperar a una descarga o un modelo.
        # Las fuentes no rescatan una señal que falló los filtros técnicos.
        context=context or {}
        sources=context.get('sources') or {}
        fresh=False
        for r in sources.values():
            if not isinstance(r,dict) or not r.get('fresh'):continue
            try:age=quote.time-float(r.get('updated',0) or 0)
            except (TypeError,ValueError):continue
            if 0<=age<=300:fresh=True;break
        fusion=(context.get('fusion') or {}).get(symbol) or {}
        adjustment=0.0
        if fresh:
            try:
                bias=float(fusion.get('bias',0) or 0);confidence=float(fusion.get('confidence',0) or 0)
                if not all(math.isfinite(x) for x in (bias,confidence)):raise ValueError('Contexto no finito')
            except (TypeError,ValueError):bias=confidence=0.0
            bias=max(-1.0,min(1.0,bias));confidence=max(0.0,min(1.0,confidence))
            adjustment=side*bias*confidence*4
            score=max(0.0,min(98.0,score+adjustment))
            quality=max(0.0,min(98.0,quality+adjustment))
            if score<rules['min_score'] or quality<rules['min_quality']:
                return None, 'Contexto externo fresco contrario: conservar pendientes, esperar confirmación más fuerte'
        key = f'RUN:{symbol}:{side}:{last.time}'
        reason = f'{signal}; H1 alineado; SL de invalidación M15; {target_reason}; contexto fresco {adjustment:+.1f}; puntuación técnica, no probabilidad'
        return Plan(symbol, key, side, 'RUNNER', 'MARKET', entry, sl, target,
                    atr, score, reason, last.time, horizon_atr=atr,
                    quality_score=quality), reason
    return None, 'Esperando ruptura, retest o continuación M15 cerrada con H1 alineado; pendientes siguen activas'


def _m5_retest_plan(symbol, frames, quote, cfg, context=None):
    rules=cfg['runner'];m5,m15,h1=(frames.get(tf) for tf in ('M5','M15','H1'))
    if not rules.get('allow_m5_retest',True) or not m5 or not m15 or not h1:
        return None,'Esperando retest M5 dentro de la tesis M15/H1'
    if len(m5.bars)<14 or len(m15.bars)<14 or min(m5.atr,m15.atr)<=0:
        return None,'Esperando estructura suficiente para retest M5'
    last=m5.bars[-1];age=quote.time-(last.time+300)
    if age< -2 or age>rules.get('m5_signal_max_age_seconds',300):
        return None,'Retest M5 aún no cerrado o caducado'
    width=max(last.high-last.low,1e-9);body=abs(last.close-last.open)/width
    if width>m5.atr*rules['max_signal_range_atr'] or m15.bars[-1].high-m15.bars[-1].low>m15.atr*rules['max_signal_range_atr']:
        return None,'Vela extendida: preparar retroceso pendiente, no perseguir'
    if body<rules.get('m5_min_body_fraction',.55):return None,'Retest M5 sin cuerpo de recuperación suficiente'
    for side in (1,-1):
        if side*h1.trend<rules['min_h1_alignment'] or side*m15.trend<.18:continue
        if side*(last.close-last.open)<=0 or side*(m15.bars[-1].close-m15.slow)<m15.atr*.10:continue
        if (side==1 and m15.rsi>78) or (side==-1 and m15.rsi<22):continue
        prior=m5.bars[-4:-1];base=float(m5.slow)
        pulled=any((b.low<=base+m5.atr*.20 if side==1 else b.high>=base-m5.atr*.20)
                   and side*(b.close-base)>=-m5.atr*.15 for b in prior)
        established=side*(m5.bars[-5].close-base)>m5.atr*.10
        level=max(b.high for b in prior) if side==1 else min(b.low for b in prior)
        if not (pulled and established and side*(last.close-base)>m5.atr*.10
                and side*(last.close-level)>=m5.atr*.025):continue
        entry=quote.ask if side==1 else quote.bid
        if side*(entry-level)<0 or abs(entry-last.close)>m5.atr*rules['max_entry_drift_atr']:
            return None,'Precio salió de la ventana del retest M5; conservar pendientes'
        if side*(entry-level)>m5.atr*rules['max_extension_atr']:
            return None,'Retest M5 ya extendido; preparar nueva zona'
        # El punto de entrada se afina en M5; la invalidación sigue siendo M15.
        anchor=min(b.low for b in m15.bars[-3:]) if side==1 else max(b.high for b in m15.bars[-3:])
        sl=anchor-side*max(m15.atr*.15,quote.spread*2)+(quote.spread if side==-1 else 0)
        risk=side*(entry-sl)
        if not m15.atr*rules['min_stop_atr']<=risk<=m15.atr*rules['max_stop_atr']:
            return None,'Invalidación M15 fuera de la distancia estructural del runner'
        tp,why=structural_target(frames,side,entry,sl,m15.atr,'RUNNER')
        if 'proyección' in why:
            if rules['require_observed_target']:return None,'Esperando objetivo observado por delante'
            tp=entry+side*risk*rules['projected_target_r'];why='TP proyectado en R; sin swing observado por delante'
        elif side==-1:tp+=quote.spread
        if side*(tp-entry)/risk<rules['min_rr']:return None,'El siguiente obstáculo no deja recorrido suficiente'
        score=min(98.0,72+body*10+min(10,side*h1.trend*8)+min(6,max(0,m5.volume_ratio)*3))
        quality=min(98.0,score+2)
        if score<rules['min_score'] or quality<rules['min_quality']:continue
        context=context or {};fresh=False
        for row in (context.get('sources') or {}).values():
            if not isinstance(row,dict) or not row.get('fresh'):continue
            try:source_age=quote.time-float(row.get('updated',0) or 0)
            except (TypeError,ValueError):continue
            if 0<=source_age<=300:fresh=True;break
        adjustment=0.0
        if fresh:
            fusion=(context.get('fusion') or {}).get(symbol) or {}
            try:
                bias=float(fusion.get('bias',0) or 0);confidence=float(fusion.get('confidence',0) or 0)
                if not all(math.isfinite(x) for x in (bias,confidence)):raise ValueError('Contexto inválido')
                adjustment=side*max(-1,min(1,bias))*max(0,min(1,confidence))*4
            except (TypeError,ValueError):adjustment=0.0
            score=max(0,min(98,score+adjustment));quality=max(0,min(98,quality+adjustment))
            if score<rules['min_score'] or quality<rules['min_quality']:
                return None,'Contexto fresco contrario al retest M5; conservar pendientes'
        reason=f'retest M5 cerrado y recuperado; M15/H1 alineados; SL y gestión M15; {why}; contexto fresco {adjustment:+.1f}; sin scalping'
        key=f'RUN:{symbol}:{side}:M5:{last.time}'
        return Plan(symbol,key,side,'RUNNER','MARKET',entry,sl,tp,m15.atr,score,reason,last.time,
                    horizon_atr=m15.atr,quality_score=quality,signal_timeframe='M5',signal_atr=m5.atr),reason
    return None,'Esperando retest M5 cerrado y recuperado dentro de la tendencia M15/H1'


def baseline_runner_candidates(symbol,frames,quote,cfg,context=None):
    rows=[]
    plan,detail=_m15_runner_plan(symbol,frames,quote,cfg,context)
    if plan is not None:
        age=quote.time-(plan.bar_time+900)
        if age< -2 or age>cfg['runner']['max_signal_age_seconds']:
            plan=None;detail='Señal M15 caducada o aún no cerrada'
    if plan is not None:rows.append((plan,detail))
    if cfg['runner']['enabled'] and cfg['runner'].get('allow_m5_retest',True):
        m5_plan,m5_detail=_m5_retest_plan(symbol,frames,quote,cfg,context)
        if m5_plan is not None:rows.append((m5_plan,m5_detail))
        else:detail+=' · '+m5_detail
    return rows,detail


def runner_plan(symbol,frames,quote,cfg,context=None):
    from strategy_adaptation import candidate_decision,frame_features
    from dataclasses import replace
    candidates,detail=baseline_runner_candidates(symbol,frames,quote,cfg,context)
    for plan,reason in candidates:
        allowed,evidence=candidate_decision(plan,frame_features(frames),context or {},quote.time)
        if allowed:return (replace(plan,reason=plan.reason+' · '+evidence) if evidence else plan),reason
        detail=evidence
    return None,detail


def runner_exit(plan, frames, side, rr, cfg, *, entry_time=None, now=None):
    """Solo cerrar por deterioro observado; un tick contrario no es una reversión."""
    f = frames.get('M15')
    period=300 if plan.get('signal_timeframe')=='M5' else 900
    if not f or len(f.bars) < 4 or f.bars[-1].time+900 <= int(plan.get('bar_time', 0))+period:
        return ''
    last, previous = f.bars[-1], f.bars[-2]
    # A pending thesis can be hours old. Only a full M15 candle that started
    # after the actual fill can invalidate a newly activated continuation.
    if entry_time is not None and last.time < float(entry_time):return ''
    if now is not None and last.time+900 > float(now)+2:return ''
    anchor = min(b.low for b in f.bars[-4:-1]) if side == 1 else max(b.high for b in f.bars[-4:-1])
    if side*(last.close-anchor) < -f.atr*.05:
        return 'Cierre M15 rompió la estructura de continuación del runner'
    reversal = all(side*(b.close-b.open) < -f.atr*.20 and
        (entry_time is None or b.time>=float(entry_time)) for b in (last, previous))
    if rr >= cfg['runner']['reversal_exit_min_r'] and reversal and side*f.trend < .05:
        return 'Dos cierres M15 contrarios y pérdida de impulso; proteger recorrido del runner'
    return ''
