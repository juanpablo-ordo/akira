"""Explicar cada etapa de decisión sin confundir propuesta, envío y confirmación."""
from collections import Counter
import math


def decision_status(symbol,plans,audit,scenarios,checks,orders,cycle,status,trade_cap,
                    runtime_block='',mode='trade',paused=False):
    rejected=Counter(str(r.get('reject_code')) for r in audit if r.get('reject_code'))
    confirmed=[o for o in orders if o.get('confirmed') and o.get('ticket')]
    eligible=[r for r in scenarios if r.get('sendable') and not r.get('confirmed')]
    def valid(value):return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and value>0
    # Successful budget checks often have no `funding` object. They must not
    # disappear from the minimum just because quality rejected them afterwards.
    minima=[v for r in checks for v in (r.get('funding',{}).get('minimum_risk_usd'),r.get('risk_usd')) if valid(v)]
    minima.extend(r['risk_usd'] for r in audit if valid(r.get('risk_usd')))
    affordable=[r for r in checks if valid(r.get('risk_usd')) and r['risk_usd']<=trade_cap+1e-8]
    quality_wait=Counter(str(r['quality_reason']) for r in affordable if r.get('quality_reason'))
    state=str(status.get('state') or 'INICIANDO');reason=str(runtime_block or status.get('detail') or '')
    if not runtime_block and mode=='trade' and not paused and not confirmed and not eligible:
        if affordable and quality_wait:
            state='ESPERANDO CONFIRMACIÓN'
            reason=(str(len(affordable))+' propuestas caben en el presupuesto. '+
                ' '.join(str(count)+' esperan: '+detail for detail,count in quality_wait.most_common(2)))
        elif minima and min(minima)>trade_cap+1e-8:
            state='PRESUPUESTO INSUFICIENTE PARA ESTAS ZONAS'
            reason=(f'Menor riesgo observado: {min(minima):.2f} USD; límite por entrada: {trade_cap:.2f} USD. '
                'Akira espera otra zona compatible; conserva el límite y la distancia de protección.')
    return {'symbol':symbol,'evaluated_scenarios':len(audit),'technical_candidates':len(plans),
            'visible_parameters':len(scenarios),'currently_sendable':len(eligible),
            'last_cycle_attempts':int(cycle.get('attempts',0)),'last_cycle_new_orders':int(cycle.get('sent',0)),
            'confirmed_pending_orders':len(confirmed),'unconfirmed_request':bool(cycle.get('unconfirmed')),
            'trade_cap_usd':float(trade_cap),'minimum_evaluated_risk_usd':min(minima) if minima else None,
            'budget_compatible_checks':len(affordable),'quality_wait_counts':dict(quality_wait),
            'rejection_counts':dict(rejected),'state':state,
            'reason':reason,'mode':mode,'paused':bool(paused),
            'execution_guard':runtime_block or ('PAUSA' if paused else 'OBSERVAR' if mode!='trade' else '')}
