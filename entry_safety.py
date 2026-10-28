"""Pause new exposure after verified own losses; never moves or closes a position.

Input must come from trade_quality_gate.owned_outcomes, which verifies ownership
and complete broker receipts. Deposits, manual trades and model scores cannot
reset this circuit. Rebuilding or restarting the app does not reset receipts.
"""
import math
from capital_guard import rules


def loss_pause(config,outcomes,now):
    policy=rules(config);limit=int(policy['loss_streak_limit'])
    seconds=float(policy['loss_pause_hours'])*3600
    result={'enabled':bool(policy['enabled']),'allowed':True,'reason':'',
            'loss_streak':0,'loss_streak_limit':limit,'paused_until':None,'closed_ids':[]}
    if not result['enabled']:return result
    unique={}
    for row in outcomes:
        identity=row.get('position_id',row.get('id',row.get('ticket')))
        try:
            when=float(row.get('closed_at',row.get('exit_time')))
            pnl=float(row.get('pnl',row.get('net')))
        except (TypeError,ValueError,OverflowError):continue
        if identity is None or not row.get('deal_ids') or not math.isfinite(when) or not math.isfinite(pnl) or when>now:continue
        unique[str(identity)]={'when':when,'pnl':pnl,'id':str(identity)}
    streak=[];last_trip=None
    for row in sorted(unique.values(),key=lambda r:(r['when'],r['id'])):
        if row['pnl']<0:streak.append(row)
        else:streak=[]
        if len(streak)>=limit:last_trip=(row['when'],[r['id'] for r in streak[-limit:]])
    result['loss_streak']=len(streak)
    # An already-open winning trade cannot silently reopen the circuit after
    # the threshold was reached. Wait the actual cooldown from the last trip.
    if last_trip and last_trip[0]+seconds>now:
        result.update(allowed=False,paused_until=last_trip[0]+seconds,closed_ids=last_trip[1],
            reason=f'Pausa de nuevas entradas: {limit} pérdidas propias consecutivas confirmadas entre BTC y oro. '
                   f'Esperar {policy["loss_pause_hours"]:g} h desde el cierre que activó la pausa. '
                   'Se retiran pendientes propias; las posiciones conservan sus SL/TP.')
    return result
