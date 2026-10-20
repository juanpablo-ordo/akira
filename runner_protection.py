"""Limits for direct runners only; pending fills keep their original risk/protection."""
import math


def _number(value, default=0.0):
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (ValueError, TypeError, OverflowError):
        return default


def entry_cap(gateway, plan, snapshot):
    cap = gateway.trade_cap(snapshot)
    if plan.lane == 'RUNNER':
        fraction = _number(gateway.cfg['runner'].get('max_trade_budget_pct', 50)) / 100
        cap *= max(0.0, min(1.0, fraction))
    return cap


def decision(gateway, plan, snapshot, now=None):
    """Read confirmed own results; no network, broker calls, or invented outcomes."""
    from trade_quality_gate import owned_outcomes
    now = gateway.clock() if now is None else float(now)
    rules = gateway.cfg['runner']
    cap = entry_cap(gateway, plan, snapshot)
    window = 86400.0
    outcomes = [row for row in owned_outcomes(gateway)
                if row.get('lane') == 'RUNNER'
                and 0 <= now - _number(row.get('closed_at')) < window]
    losses = [row for row in outcomes if _number(row.get('pnl')) < 0]
    gross_loss = sum(-_number(row.get('pnl')) for row in losses)
    loss_budget = gateway.trade_cap(snapshot) * _number(rules.get('loss_budget_trades', 1))
    same_asset = [row for row in losses if row.get('symbol') == plan.symbol]
    cooldown = _number(rules.get('loss_cooldown_seconds', 3600))
    until = max((_number(row.get('closed_at')) + cooldown for row in same_asset), default=0)
    reason = ''
    if rules.get('preserve_pending_orders', True) and any(
            order.symbol == plan.symbol and gateway.owned_order(order) for order in snapshot.orders):
        reason = 'Prioridad a las pendientes confirmadas: una runner no retira su mapa para entrar a mercado.'
    elif gross_loss >= loss_budget - 1e-9 and losses:
        # No same-day win resets this budget. Restarting also preserves the receipts.
        until = max(until, min(_number(row.get('closed_at')) + window for row in losses))
        reason = ('Runners en pausa por pérdidas confirmadas en 24 h: '
                  f'{gross_loss:.2f} USD frente a {loss_budget:.2f} USD autorizados para esta vía. '
                  'Las pendientes conservan sus propios controles.')
    elif until > now:
        reason = 'Runner en pausa tras una pérdida confirmada de este activo; esperar nueva estructura y el fin de la pausa.'
    return {'allowed': not reason, 'reason': reason, 'runner_cap_usd': round(cap, 8),
            'gross_loss_24h_usd': round(gross_loss, 8), 'loss_budget_24h_usd': round(loss_budget, 8),
            'resume_not_before': until if reason and until > now else None,
            'confirmed_runner_closures': len(outcomes),
            'scope': 'Solo entradas directas RUNNER. No aumenta riesgo, mueve SL ni cancela pendientes.'}
