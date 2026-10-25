"""Readable account and execution constraints from the effective live snapshot."""
def security_text(snapshot,cfg):
    account=snapshot.get('account') or {};ledger=snapshot.get('portfolio_risk') or {};management=cfg['management']
    def n(v):return f'{v:,.2f}' if isinstance(v,(int,float)) else 'sin dato'
    daily_money=float(cfg['risk'].get('daily_loss_money',0));daily_pct=float(cfg['risk'].get('daily_loss_pct',0))
    daily=('Tope en dinero: '+n(daily_money)+' '+str(account.get('currency') or 'USD') if daily_money>0 else 'Tope en dinero desactivado')
    daily+='; '+('tope porcentual: '+n(daily_pct)+'%' if daily_pct>0 else 'tope porcentual desactivado')+'.'
    rows=['RIESGO Y EJECUCIÓN',
      'Máximo efectivo por operación: '+n(snapshot.get('trade_risk_cap'))+' USD (se aplican el tope en dinero y el porcentaje del patrimonio).',
      'Riesgo reservado: '+n(ledger.get('reserved_usd'))+' USD. Capacidad conjunta libre: '+n(ledger.get('available_usd'))+' USD.',
      'Margen libre MT5: '+n(account.get('margin_free'))+' '+str(account.get('currency',''))+'. Margen mínimo: '+n(cfg['risk']['minimum_margin_level_pct'])+'%.',
      'Resultado neto del día: '+n(account.get('daily_net'))+'. '+daily,
      'La protección de precio (SL) sigue la estructura del mercado. El tamaño de la orden se calcula con los precios, costes y reglas reales del bróker.',
      'Nunca se estrecha el SL para ocultar un exceso de riesgo. Un tick antiguo, riesgo ocupado, geometría inválida o rechazo MT5 impiden el envío.',
      'Pendientes propias: se comparan con alternativas; solicitudes inciertas se concilian y no se duplican.',
      'Protección de posiciones: pivote M15 confirmado, colchón '+n(management['trail_atr'])+' ATR; umbral de protección '+n(management['breakeven_at_r'])+' R.',
      'Protección de avance sin esperar pivote: '+('activa' if management.get('protect_progress',True) else 'desactivada')+'. Solicita cubrir costes estimados al alcanzar el umbral; requiere confirmación MT5 y no garantiza ausencia de pérdidas.',
      'Solo pendientes: '+('activo' if cfg['execution'].get('pending_only') else 'desactivado')+'. Gestión de activadas como runners: '+('activa' if management.get('pending_fills_as_runners') else 'gestión habitual')+'.']
    for symbol,terms in (snapshot.get('broker_terms') or {}).items():
        rows+=['BROKER · '+symbol+' · lote min '+str(terms.get('volume_min'))+' / paso '+str(terms.get('volume_step'))+' / max '+str(terms.get('volume_max')),
        'Stops mínimos: '+str(terms.get('trade_stops_level'))+' puntos; freeze: '+str(terms.get('trade_freeze_level'))+'; tick '+str(terms.get('trade_tick_size'))+'.']
    if snapshot.get('execution_block'):rows+=['BLOQUEO ACTUAL · '+str(snapshot['execution_block'])]
    return '\n\n'.join(rows)
