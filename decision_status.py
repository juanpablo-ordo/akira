"""Explicar cada etapa de decisión sin confundir propuesta, envío y confirmación."""
from collections import Counter


def decision_status(symbol,plans,audit,scenarios,checks,orders,cycle,status,trade_cap,
                    runtime_block='',mode='trade',paused=False):
    rejected=Counter(str(r.get('reject_code')) for r in audit if r.get('reject_code'))
    confirmed=[o for o in orders if o.get('confirmed') and o.get('ticket')]
    eligible=[r for r in scenarios if r.get('sendable') and not r.get('confirmed')]
    minima=[r['funding']['minimum_risk_usd'] for r in checks if r.get('funding',{}).get('minimum_risk_usd') is not None]
    return {'symbol':symbol,'evaluated_scenarios':len(audit),'technical_candidates':len(plans),
            'visible_parameters':len(scenarios),'currently_sendable':len(eligible),
            'last_cycle_attempts':int(cycle.get('attempts',0)),'last_cycle_new_orders':int(cycle.get('sent',0)),
            'confirmed_pending_orders':len(confirmed),'unconfirmed_request':bool(cycle.get('unconfirmed')),
            'trade_cap_usd':float(trade_cap),'minimum_evaluated_risk_usd':min(minima) if minima else None,
            'rejection_counts':dict(rejected),'state':str(status.get('state') or 'INICIANDO'),
            'reason':str(runtime_block or status.get('detail') or ''),'mode':mode,'paused':bool(paused),
            'execution_guard':runtime_block or ('PAUSA' if paused else 'OBSERVAR' if mode!='trade' else '')}
