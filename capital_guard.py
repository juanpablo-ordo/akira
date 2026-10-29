"""Account-wide capital protection, using broker facts rather than model scores.

History reconstruction is causal. Deposits/withdrawals move the reference rather
than masquerading as trading returns. No prices, stops or model calls here.
"""
import math


DEFAULTS = dict(enabled=True, trade_pct=2.0, portfolio_pct=6.0, symbol_pct=3.0,
                daily_loss_pct=6.0, max_drawdown_pct=15.0,
                one_position_per_symbol=True, strict_pending_quality=True,
                loss_streak_limit=3, loss_pause_hours=24.0,
                fomc_pause=True, event_pause_minutes=60)


def rules(config):
    return {**DEFAULTS, **(config.get('capital_protection') or {})}


def amount(row, key, default=0):
    value = row.get(key, default) if isinstance(row, dict) else getattr(row, key, default)
    result = float(value or 0)
    if not math.isfinite(result):
        raise ValueError('Dato monetario no finito: ' + key)
    return result


def net(row):
    return sum(amount(row, key) for key in ('profit', 'commission', 'swap', 'fee'))


def history_metrics(history, balance, equity, now):
    """Balance curve over the available history, not an invented equity curve."""
    rows = sorted((r for r in history if amount(r, 'time') <= now + 1),
                  key=lambda r: (amount(r, 'time_msc', amount(r, 'time') * 1000), amount(r, 'ticket')))
    current = float(balance) - sum(net(r) for r in rows)
    peak = max(0.0, current)
    today = int(now // 86400) * 86400
    day_net = 0.0
    flows = {}
    for row in rows:
        pnl = net(row)
        current += pnl
        if int(amount(row, 'type')) == 2:  # DEAL_TYPE_BALANCE
            peak = max(0.0, peak + pnl)
            flows[str(int(amount(row, 'ticket')))] = pnl
        elif amount(row, 'time') >= today:
            day_net += pnl
        peak = max(peak, current)
    # Funding during the day is capital, not profit. Floating P/L counts toward
    # daily loss without adding the same realized losses a second time.
    day_basis = max(0.0, float(balance) - day_net)
    return dict(balance_peak=max(peak, float(balance)), day_basis=day_basis,
                daily_net=day_net, daily_loss=max(0.0, day_basis-float(equity)), cashflows=flows)



def metrics_for(gateway,snapshot):
    """At most one history sort per broker refresh, balance or UTC day change."""
    key=(getattr(gateway,'history_revision',0),gateway.history_time,len(gateway.history),
         float(snapshot.account.balance),int(gateway.clock()//86400))
    cached=getattr(gateway,'_capital_metrics',None)
    if cached is None or cached[0]!=key:
        value=history_metrics(gateway.history,snapshot.account.balance,snapshot.account.balance,gateway.clock())
        gateway._capital_metrics=(key,value)
    result=dict(gateway._capital_metrics[1])
    result['daily_loss']=max(0.0,result['day_basis']-float(snapshot.account.equity))
    return result


def status(gateway, snapshot, refresh=False):
    cfg = rules(gateway.cfg)
    if not cfg['enabled']:
        return dict(enabled=False, allowed=True, reason='', drawdown_pct=0.0)
    now = gateway.clock()
    if refresh and (gateway.history_error or not gateway.history_time or now-gateway.history_time > 5):
        gateway.refresh_history(now, force=True)
    if gateway.history_error or not gateway.history_time or not -2 <= now-gateway.history_time <= 120:
        return dict(enabled=True, allowed=False, reason='Protección de capital: esperando historial MT5 vigente.', ready=False)
    try:
        balance=amount(snapshot.account, 'balance');equity=amount(snapshot.account, 'equity')
        metrics=metrics_for(gateway,snapshot)
        saved=gateway.journal.data.get('capital_guard') or {}
        if not isinstance(saved,dict):raise ValueError('Referencia de capital dañada')
        known=saved.get('cashflows') or {}
        if not isinstance(known,dict):raise ValueError('Movimientos de capital dañados')
        funding=sum(v for k,v in metrics['cashflows'].items() if k not in known) if saved else 0.0
        peak=max(metrics['balance_peak'], amount(saved,'peak')+funding, equity)
        drawdown=max(0.0,(peak-equity)/peak*100) if peak>0 else 100.0
        reference=dict(peak=peak,cashflows=metrics['cashflows'])
        if reference!=saved:
            gateway.journal.data['capital_guard']=reference
            if not saved or now-getattr(gateway,'_capital_last_save',0)>=5 or drawdown>=cfg['max_drawdown_pct']:
                gateway.journal.save();gateway._capital_last_save=now
        daily_limit=metrics['day_basis']*cfg['daily_loss_pct']/100
        reason=''
        if drawdown >= cfg['max_drawdown_pct']-1e-9:
            reason=f'Protección de capital: caída {drawdown:.2f}% desde la referencia {peak:.2f}; límite {cfg["max_drawdown_pct"]:g}%.'
        elif metrics['daily_loss'] >= daily_limit-1e-9 and metrics['daily_loss']>0:
            reason=f'Protección de capital: pérdida diaria {metrics["daily_loss"]:.2f} frente a {daily_limit:.2f} autorizados.'
        return dict(enabled=True, ready=True, allowed=not reason, reason=reason, peak=peak,
                    drawdown_pct=drawdown, day_basis=metrics['day_basis'], daily_limit=daily_limit,
                    daily_loss=metrics['daily_loss'], daily_net=metrics['daily_net'],
                    trade_pct=cfg['trade_pct'], portfolio_pct=cfg['portfolio_pct'], symbol_pct=cfg['symbol_pct'])
    except (TypeError,ValueError,OverflowError) as exc:
        return dict(enabled=True, ready=False, allowed=False, reason='Protección de capital: datos incompletos. '+str(exc))


def symbol_cap(config, snapshot):
    return max(0.0, min(float(snapshot.account.balance),float(snapshot.account.equity)))*rules(config)['symbol_pct']/100


def pending_reduction(gateway, snapshot, ledger, state, entry_block=''):
    """Pick ONE owned ticket to withdraw; reconcile before the next decision.

Never promises that an order cannot fill while its cancellation is in flight.
External exposure consumes capacity but is never cancelled here.
"""
    cfg=rules(gateway.cfg)
    owned={int(o.ticket):o for o in snapshot.orders if gateway.owned_order(o) and o.symbol not in gateway.journal.data['intents']}
    candidates=[]
    for row in ledger['rows']:
        ticket=int(row.get('ticket') or 0)
        if row['kind']!='pending' or ticket not in owned:continue
        reason=''
        if entry_block:reason=entry_block
        elif cfg['enabled']:
            if not state['allowed']:reason=state['reason']
            elif cfg['one_position_per_symbol'] and any(p.symbol==row['symbol'] for p in snapshot.positions):
                reason='Una posición activa ocupa este símbolo; no acumular otra entrada.'
            elif not row['risk_known']:reason='Riesgo de la pendiente no calculable.'
            elif row['reserved_usd']>gateway.trade_cap(snapshot)+1e-9:reason='La pendiente supera el límite por orden actualizado.'
            elif sum(r['reserved_usd'] for r in ledger['rows'] if r.get('symbol')==row['symbol'])>symbol_cap(gateway.cfg,snapshot)+1e-9:
                reason='La exposición conjunta del símbolo supera el límite de capital.'
            elif ledger['reserved_usd']>ledger['cap_usd']+1e-9:reason='El riesgo conjunto supera el presupuesto actualizado.'
        if reason:candidates.append((row['reserved_usd'],ticket,reason))
    if not candidates:return None
    _,ticket,reason=max(candidates)
    return owned[ticket],reason
