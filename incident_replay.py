"""Read-only forensic replay of an AKIRA ticket; never recreates nonexistent ticks.

The supplied reports may contain MFE and a closing deal, but no complete
broker bid/ask series or confirmed modification attempts. Such data cannot prove
that a more favorable SL would have been accepted in time.
"""
import json
import math


def audit_ticket(export, ticket, ticks=None):
    ticket=str(ticket)
    snap=export.get('snapshot') or {}
    meta=(snap.get('position_journal') or {}).get(ticket) or {}
    close=next((r for r in (export.get('closed') or []) if str(r.get('ticket'))==ticket),None)
    if not close:
        return {'ticket':ticket,'state':'NOT_IN_EXPORT',
                'broker_accepted_stop':False,'loss_avoidable_proven':False}
    initial=float(meta.get('initial_sl') or close.get('initial_sl') or 0)
    plan=meta.get('plan') or {}
    direction=1 if (plan.get('side') or meta.get('side') or 1) in (1,'BUY') else -1
    entry=float(close.get('entry') or meta.get('entry') or 0)
    risk=direction*(entry-initial)
    mfe=close.get('mfe_r')
    attempts=[x for x in (meta.get('management_events') or []) if x.get('operation') in ('protect','ticket_stop')]
    confirmed=[x for x in attempts if x.get('retcode') in (10009,10008) and x.get('new_sl') is not None]
    facts={'ticket':ticket,'symbol':close.get('symbol'),'side':'BUY' if direction==1 else 'SELL',
           'entry':entry,'original_sl':initial,'exit_price':close.get('exit_price'),
           'net_usd':close.get('net_usd'),'mfe_r_observed':mfe,
           'mfe_usd_observed':meta.get('max_favorable_usd'),
           'last_modify_recorded':meta.get('last_modify'),
           'protection_state':meta.get('protection_state'),
           'risk_price':risk if risk>0 else None,
           'documented_stop_attempts':len(attempts),'documented_accepted_requests':len(confirmed)}
    quotes=[]
    for t in ticks or ():
        try:
            bid=float(t['bid']);ask=float(t['ask']);utc=float(t['utc'])
            if math.isfinite(bid) and math.isfinite(ask) and math.isfinite(utc) and 0<bid<=ask:
                price=bid if direction==1 else ask
                quotes.append({'utc':utc,'bid':bid,'ask':ask,
                               'executable_price':price,
                               'current_r':round(direction*(price-entry)/risk,6) if risk>0 else None,
                               'broker_check_retcode':t.get('order_check_retcode'),
                               'broker_send_retcode':t.get('order_send_retcode'),
                               'confirmed_sl':t.get('confirmed_sl')})
        except (KeyError,TypeError,ValueError):continue
    complete=bool(quotes) and all(q['broker_check_retcode'] is not None and
                                  q['broker_send_retcode'] is not None and
                                  q['confirmed_sl'] is not None for q in quotes)
    return {'ticket':ticket,'state':'FORENSIC_REPLAY',
            'facts':facts,'observed_quotes':quotes[-10000:],
            'evidence_complete':complete,
            'broker_accepted_stop':bool(confirmed),
            'loss_avoidable_proven':False,
            'missing':([] if quotes else ['Bid/ask histórico por cada ciclo de gestión'])+
                ([] if complete else ['order_check, order_send y SL confirmado para las modificaciones pertinentes']),
            'conclusion':'El reporte no permite demostrar una pérdida evitable. No se inventaron ticks, retcodes ni fills.'}


def audit_json_file(path,ticket,ticks=None):
    with open(path,encoding='utf-8') as stream:source=json.load(stream)
    return audit_ticket(source,ticket,ticks)
