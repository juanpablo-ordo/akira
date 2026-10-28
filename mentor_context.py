"""Bounded read-only facts for the assistant. No broker/network/model imports."""
from collections import defaultdict
import math,re
from conversation_core import folded


def number(value):
    try:
        n=float(value)
        return n if math.isfinite(n) else None
    except (TypeError,ValueError,OverflowError):return None


def system_question(message):
    text=folded(message)
    return bool(re.search(r'\b(?:akira|mi cuenta|el bot|el motor|mi riesgo|mis perdidas)\b',text)
                and re.search(r'\b(?:pierde|perdi[oó]|perdidas|rendimiento|riesgo|funciona|fall[oa]|estado|saldo|presupuesto|actividad)\b',text))


def performance(snapshot):
    unique={};ignored=0
    for row in snapshot.get('confirmed_strategy_outcomes') or []:
        # Imported excerpts without a complete broker receipt are not a sample.
        pid=row.get('position_id');pnl=number(row.get('pnl',row.get('net')))
        if pid is None or row.get('state')!='CONFIRMADO MT5' or not row.get('deal_ids') or pnl is None:
            ignored+=1;continue
        unique[str(pid)]=row
    groups=defaultdict(list)
    for row in unique.values():groups[str(row.get('symbol','?')),str(row.get('lane','?'))].append(row)
    result=[]
    for (symbol,lane),rows in sorted(groups.items()):
        pnls=[number(r.get('pnl',r.get('net'))) for r in rows];gain=sum(p for p in pnls if p>0);loss=-sum(p for p in pnls if p<0)
        result.append(dict(symbol=symbol,lane=lane,closed=len(rows),wins=sum(p>0 for p in pnls),net=round(sum(pnls),8),
            observed_win_rate=round(sum(p>0 for p in pnls)/len(pnls),6),profit_factor=round(gain/loss,6) if loss else None,
            first_exit=min((number(r.get('exit_time',r.get('closed_at'))) or 0 for r in rows)),
            last_exit=max((number(r.get('exit_time',r.get('closed_at'))) or 0 for r in rows))))
    return dict(groups=result,closed=len(unique),net=round(sum(g['net'] for g in result),8),ignored=ignored,
        scope='Cierres propios completos disponibles en esta captura, con costes. No es una tasa de acierto futura ni una prueba de rentabilidad.')


def inspect_state(snapshot,section,now):
    stamp=number(snapshot.get('as_of_utc',snapshot.get('updated')))
    if not snapshot.get('connected') or stamp is None or not -5<=now-stamp<=15:
        return dict(ok=False,error='La captura de MT5 falta o tiene más de 15 segundos; no se presenta como estado actual.')
    if section=='performance':data=performance(snapshot)
    elif section=='account':data={k:(snapshot.get('account') or {}).get(k) for k in ('balance','equity','floating','daily_net','currency','margin_free')}
    elif section=='risk':
        ledger=snapshot.get('portfolio_risk') or {}
        data=dict(protection=snapshot.get('capital_protection') or {},
                  trade_cap=snapshot.get('trade_risk_cap'),portfolio_cap=snapshot.get('risk_cap'),
                  reserved=ledger.get('reserved_usd',snapshot.get('reserved_risk')),available=ledger.get('available_usd'))
    elif section=='activity':
        data=dict(mode=snapshot.get('mode'),paused=snapshot.get('paused'),status={str(k):{'state':str(v.get('state',''))[:120],'detail':str(v.get('detail',''))[:450]} for k,v in list((snapshot.get('status') or {}).items())[:4] if isinstance(v,dict)})
    else:return dict(ok=False,error='Sección no autorizada')
    return dict(ok=True,as_of_utc=stamp,read_only=True,section=section,data=data)


def diagnostic_reply(message,snapshot,now):
    text=folded(message)
    if not system_question(message) or not re.search(r'\b(?:pierde|perdio|perdidas|rendimiento)\b',text):return None
    # Never swallow an explicit execution request or recommend account risk from
    # a conversational sentence. It retains the existing actor command path.
    if re.search(r'\b(?:abre|abrir|pon|coloca|ejecuta|compra|vende|cierra|cancela|reanuda)\w*\b',text):return None
    facts=inspect_state(snapshot,'performance',now)
    if not facts['ok']:return facts['error']
    data=facts['data'];currency=(snapshot.get('account') or {}).get('currency') or 'moneda de cuenta'
    if not data['closed']:return 'No hay cierres propios completos confirmados en esta captura para explicar el rendimiento. Genera el informe con historial MT5; no voy a atribuir las pérdidas a una vía sin datos.'
    lines=[f"En el historial disponible hay {data['closed']} cierres propios completos y un neto de {data['net']:.2f} {currency}."]
    for g in data['groups']:
        lines.append(f"{g['symbol']} · {g['lane']}: {g['wins']}/{g['closed']} ganadoras, neto {g['net']:.2f} {currency}. Esto describe el pasado; no mide la probabilidad de la próxima orden.")
    guard=snapshot.get('capital_protection') or {}
    if guard.get('enabled') and guard.get('reason'):lines.append(guard['reason'])
    ledger=snapshot.get('portfolio_risk') or {}
    if number(ledger.get('reserved_usd')) is not None:lines.append(f"Riesgo todavía reservado: {ledger['reserved_usd']:.2f} {currency}. Las pendientes pueden activarse mientras MT5 no confirme su retirada.")
    lines.append('El score técnico no demuestra rentabilidad. Para atribuir causas a cada entrada hay que revisar su tesis, exposición y ejecución; este resumen no cambia ninguna orden.')
    return '\n'.join(lines)
