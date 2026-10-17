"""Explicit selection among implemented rule families; no new risk policy."""
from dataclasses import replace
from trade_quality_gate import family

ADAPTIVE='AKIRA_ADAPTATIVA'
FAMILIES=('PENDIENTE_RETROCESO','PENDIENTE_RUPTURA','RUNNER_CONTINUACION_M15','RUNNER_RETEST_M5','REVERSION_CONFIRMADA','RANGO_RECHAZO')

def selected(cfg):return (cfg.get('strategy_choice') or {}).get('selected',ADAPTIVE)

def allows(plan,cfg):
    choice=selected(cfg)
    if choice not in (ADAPTIVE,*FAMILIES):return False
    return choice==ADAPTIVE or family(plan)==choice

def tag(plan,cfg):
    return replace(plan,strategy_id=family(plan),strategy_version=1,selector_id=selected(cfg),selector_version=1)
