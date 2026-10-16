"""Finite execution and verification diagnostics. Read-only: never sends MT5 orders.

Published reasons are tied to the effective configuration and the latest
broker snapshot; showing a ready badge never authorizes trading on its own.
"""
from __future__ import annotations

from copy import deepcopy


def execution_gate(mode, paused=False, runtime_block='', network_available=True,
                   account=None, preview=False):
    """Explain why operations are or are not permitted, without changing mode.

    An installation starts in OBSERVE by design.  Never silently transition to
    TRADE after startup, upgrade, login changes or reconnection.
    """
    account = account or {}
    if preview:
        code, reason, action = 'PREVIEW', 'Vista previa: no se ejecutan órdenes.', 'Conecta MT5 demo para realizar pruebas.'
    elif mode != 'trade':
        code, reason, action = ('OBSERVE',
            'Solo análisis seleccionado: Akira no enviará ni modificará órdenes de apertura.',
            'Para operar, selecciona Operativa automática en Ajustes y confirma la cuenta y sus límites.')
    elif paused:
        code, reason, action = ('PAUSED', 'La gestión fue pausada; las nuevas entradas están suspendidas.',
                                'Reanuda manualmente la gestión cuando corresponda.')
    elif runtime_block:
        code, reason, action = ('BROKER_BLOCK', str(runtime_block)[:400],
                               'Revisa el terminal, los permisos, el margen o las restricciones indicadas.')
    elif network_available is False:
        code, reason, action = ('OFFLINE',
            'La conectividad esencial no está disponible; nuevas entradas suspendidas.',
            'Esperar reconexión y reconciliación de posiciones y órdenes; no duplicar solicitudes.')
    else:
        code, reason, action = ('TRADE_ENABLED',
            'Modo automático autorizado; cada orden todavía debe superar todos los controles de riesgo y MT5.',
            'Comprueba pendientes, posiciones y motivos de descarte en Operaciones.')
    return {'code': code, 'execution_allowed': code == 'TRADE_ENABLED',
            'reason': reason, 'next_action': action,
            'mode': mode, 'paused': bool(paused),
            'account_login': account.get('login'),
            'network_available': bool(network_available),
            'risk_checks_skipped': False}


def verification_job(job, reports, checks, reviews, now, ai_available, timeout_seconds=125):
    """One bounded user-triggered verification with terminal failure states.

    A completed review or check is counted only when its exact fingerprint
    matches the job request and its recorded timestamp is newer than the
    request.  A timeout is not a successful review or permission to execute.
    """
    record=deepcopy(job);requested=float(job.get('requested') or 0)
    age=max(0., float(now)-requested)
    details=[];missing=[];changed=[];completed=0;failures=[]
    deep=bool(job.get('deep',False))
    for pid in job.get('targets',[]):
        report=reports.get(pid)
        expected=(job.get('fingerprints') or {}).get(pid)
        if not report or report.get('fingerprint')!=expected:
            changed.append(pid)
            details.append({'id':pid,'kind':'context','state':'CHANGED',
                            'reason':'La tesis o los niveles ya no coinciden; solicitar una revisión nueva.'})
            continue
        check=checks.get(pid) or {}
        current_check=check.get('fingerprint')==expected and float(check.get('at') or 0)>=requested
        broker_finished=bool(check.get('broker_checked')) or bool(check.get('error') or check.get('broker_error'))
        if current_check and broker_finished:
            completed+=1
            bad=bool(check.get('error') or check.get('broker_error')) or not bool(check.get('risk_passed'))
            if bad:failures.append('Revisión técnica rechazada: '+pid)
            details.append({'id':pid,'kind':'broker','state':'REJECTED' if bad else 'COMPLETE',
                            'reason':str(check.get('error') or check.get('broker_error') or '')[:250]})
        else:
            details.append({'id':pid,'kind':'broker','state':'WAITING','reason':'Comprobación actual de riesgo/MT5 pendiente.'})
        if deep:
            review=reviews.get(pid) or {}
            match=review.get('fingerprint')==expected and float(review.get('updated') or 0)>=requested
            state=str(review.get('state') or '') if match else ''
            if state in ('COMPLETE','ERROR'):
                completed+=1
                ai_data=review.get('data')
                ai_data=ai_data if isinstance(ai_data,dict) else {}
                approved=(state=='COMPLETE' and ai_data.get('verdict')=='APPROVE'
                          and isinstance(ai_data.get('reason'),str) and bool(ai_data['reason'].strip())
                          and isinstance(ai_data.get('missing'),list) and not ai_data['missing'])
                if not approved:
                    failures.append('Revisión IA sin aprobación verificable: '+pid)
                details.append({'id':pid,'kind':'ai','state':'COMPLETE' if approved else 'REJECTED',
                                'reason':str(review.get('error') or ai_data.get('reason') or
                                              'Respuesta IA incompleta, inválida o sin aprobación explícita.')[:250]})
            else:
                details.append({'id':pid,'kind':'ai','state':'WAITING','reason':'Esperando dictamen IA de estos niveles.'})
        critical=report.get('critical_missing') or []
        missing.extend(critical)
        # Never present a technical check as successful when critical inputs
        # (quotes, stops, broker rights or risk) remain unavailable.
        if critical and current_check and broker_finished:
            failures.append('Requisitos esenciales aún ausentes: '+pid)
    total=len(job.get('targets',[]))*(2 if deep else 1)
    if changed:phase='DATOS O NIVELES CAMBIADOS'
    elif not ai_available and deep:phase='SIN SERVICIO DE IA'
    elif failures:phase='REVISIÓN RECHAZADA O FALLIDA'
    elif completed>=total:phase='REVISIÓN TERMINADA'
    elif age>=timeout_seconds:phase='TIEMPO AGOTADO'
    else:phase='REVISANDO'
    record.update(completed=completed,total=total,phase=phase,
                  changed=changed,missing=sorted(set(missing)),ai_available=bool(ai_available),
                  elapsed_seconds=round(age,1),details=details,
                  terminal=phase!='REVISANDO',
                  # Explicitly never treat 'COMPLETED' as trade authorization.
                  authorizes_orders=False)
    return record
