"""Readable account and execution constraints from the effective live snapshot."""
def security_text(snapshot,cfg):
    account=snapshot.get('account') or {};ledger=snapshot.get('portfolio_risk') or {};management=cfg['management']
    def n(v):return f'{v:,.2f}' if isinstance(v,(int,float)) else 'sin dato'
    rows=['RIESGO Y EJECUCIÓN',
      'Máximo efectivo por operación: '+n(snapshot.get('trade_risk_cap'))+' USD (menor entre cap monetario y porcentaje del patrimonio).',
      'Riesgo reservado: '+n(ledger.get('reserved_usd'))+' USD. Capacidad conjunta libre: '+n(ledger.get('available_usd'))+' USD.',
      'Margen libre MT5: '+n(account.get('margin_free'))+' '+str(account.get('currency',''))+'. Margen mínimo: '+n(cfg['risk']['minimum_margin_level_pct'])+'%.',
      'Resultado neto del día: '+n(account.get('daily_net'))+'. Límites diarios configurados: '+str({k:v for k,v in cfg['risk'].items() if 'daily' in k or 'day_' in k}),
      'SL define invalidación estructural; el lote se calcula con order_calc_profit, costes y margen del broker.',
      'Nunca se estrecha el SL para ocultar un exceso de riesgo. Un tick antiguo, riesgo ocupado, geometría inválida o rechazo MT5 impiden el envío.',
      'Pendientes propias: se comparan con alternativas; solicitudes inciertas se concilian y no se duplican.',
      'Protección de posiciones: pivote M15 confirmado, colchón '+n(management['trail_atr'])+' ATR; umbral de protección '+n(management['breakeven_at_r'])+' R.',
      'Solo pendientes: '+('activo' if cfg['execution'].get('pending_only') else 'desactivado')+'. Gestión de activadas como runners: '+('activa' if management.get('pending_fills_as_runners') else 'gestión habitual')+'.']
    for symbol,terms in (snapshot.get('broker_terms') or {}).items():
        rows+=['BROKER · '+symbol+' · lote min '+str(terms.get('volume_min'))+' / paso '+str(terms.get('volume_step'))+' / max '+str(terms.get('volume_max')),
        'Stops mínimos: '+str(terms.get('trade_stops_level'))+' puntos; freeze: '+str(terms.get('trade_freeze_level'))+'; tick '+str(terms.get('trade_tick_size'))+'.']
    if snapshot.get('execution_block'):rows+=['BLOQUEO ACTUAL · '+str(snapshot['execution_block'])]
    return '\n\n'.join(rows)
