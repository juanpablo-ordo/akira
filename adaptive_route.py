"""Live adaptive routing across existing, independently checked strategy families.

Uses the SAME regime classifier as planner.v203_regime. Never fabricates a
setup, modifies stops, overrides a manual strategy choice, or treats a score
as validated trading profitability.
"""
import math
from trade_quality_gate import family
from strategy_choice import ADAPTIVE,selected

PREFERENCES={
    'TREND':('PENDIENTE_RETROCESO','RUNNER_CONTINUACION_M15','RUNNER_RETEST_M5'),
    'RANGE':('RANGO_RECHAZO','REVERSION_CONFIRMADA','PENDIENTE_RETROCESO'),
    'BREAKOUT':('PENDIENTE_RUPTURA','RUNNER_CONTINUACION_M15','RUNNER_RETEST_M5'),
    'HIGH_VOL':('PENDIENTE_RUPTURA','RUNNER_CONTINUACION_M15'),
    'LOW_VOL':('RANGO_RECHAZO','REVERSION_CONFIRMADA'),
    'MEAN_REVERSION':('RANGO_RECHAZO','REVERSION_CONFIRMADA','PENDIENTE_RETROCESO'),
    'LIQUIDITY_SWEEP':('REVERSION_CONFIRMADA','RUNNER_RETEST_M5','RANGO_RECHAZO'),
    'NEWS_SHOCK':()
}

def route(plan,cfg,regime):
    group=family(plan)
    name=str((regime or {}).get('regime') or '')
    try:conf=float((regime or {}).get('confidence') or 0)
    except (TypeError,ValueError):conf=0.
    if selected(cfg)!=ADAPTIVE or not math.isfinite(conf) or conf<.55 or name not in PREFERENCES:
        return {'regime':name or 'UNKNOWN','family':group,'adjustment':0.0,
                'state':'MANUAL_OR_UNCERTAIN','entry_allowed':True,
                'reason':'Se mantienen las reglas técnicas anteriores.'}
    preferred=PREFERENCES[name]
    if name=='NEWS_SHOCK' and conf>=.75:
        return {'regime':name,'family':group,'adjustment':0.0,
                'state':'SHOCK_CAUTION','entry_allowed':False,
                'reason':'Régimen de noticia/expansión brusca de alta confianza: no añadir exposición.'}
    if group in preferred:
        pos=preferred.index(group)
        adjust=max(.35,2.4-0.7*pos)*min(1.0,conf)
        state='PREFERRED'
    else:
        adjust=-1.6*min(1.0,conf)
        state='DEPRIORITIZED'
    return {'regime':name,'family':group,'adjustment':round(adjust,3),
            'state':state,'entry_allowed':True,
            'reason':'Prioridad adaptativa de régimen (no evidencia de rentabilidad).'}
