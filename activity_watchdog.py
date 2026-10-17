"""Six-hour trading-session diagnostic without trading side effects.

Tracks confirmed broker tickets, not intent creation, scanner cycle time, or
AI suggestions. The watcher NEVER submits or modifies a broker request.
"""
from __future__ import annotations

class SessionWatchdog:
    def __init__(self, start_at):
        self.start_at=float(start_at)
        self.last_confirmed_at=float(start_at)
        self._known_tickets=None
        self._seen_tickets=set()  # A restored historical ticket is not a new fill.
        self._last_message=''
        self._transition_count=0

    def inspect(self, view, now):
        now=float(now)
        # Clock rollbacks (terminal/OS adjustment) cannot imply six hours idle.
        if now<self.start_at:
            self.start_at=now;self.last_confirmed_at=now
        tickets=set()
        for family in ('orders','positions'):
            for item in view.get(family) or []:
                if not isinstance(item,dict) or not item.get('owned'):continue
                ticket=item.get('ticket')
                if ticket is not None:tickets.add(str(family)+':'+str(ticket))
        if self._known_tickets is None:
            self._known_tickets=tickets
            self._seen_tickets.update(tickets)
        else:
            if tickets-self._seen_tickets:self.last_confirmed_at=now
            self._seen_tickets.update(tickets)
            self._known_tickets=tickets
        total=sum(len(v) for v in (view.get('candidates') or {}).values() if isinstance(v,list))
        viable=sum(1 for info in (view.get('symbols') or {}).values()
                   for plan in (info.get('scenario_book') or [])
                   if isinstance(plan,dict) and plan.get('sendable') and not plan.get('confirmed'))
        gate=view.get('execution_gate') or {}
        active_market=any(v.get('open') for v in (view.get('markets') or {}).values() if isinstance(v,dict))
        blocked=gate.get('code') not in ('TRADE_ENABLED',None)
        idle=max(0.,now-self.last_confirmed_at)
        session=max(0.,now-self.start_at)
        reasons=[]
        if blocked:reasons.append(str(gate.get('reason') or gate.get('code')))
        elif not active_market:reasons.append('Los instrumentos configurados no tienen una sesión abierta.')
        elif viable:reasons.append(str(viable)+' candidatas con marca de viabilidad; revisar cupos, riesgo, revisión IA y confirmación MT5.')
        elif total:reasons.append(str(total)+' candidatas técnicas, ninguna marcada como inmediatamente ejecutable.')
        else:reasons.append('No se detectaron candidatas técnicas recientes; comprobar histórico/ticks e indicadores.')
        if (view.get('unconfirmed') or []):reasons.append('Existen solicitudes MT5 con resultado incierto: reconciliar antes de repetir.')
        # A health diagnostic is never an excuse to lower risk or force a trade.
        level='ATTENTION' if gate.get('code')=='TRADE_ENABLED' and active_market and idle>=1800 else 'INFO'
        if session>=21600 and idle>=21600:level='SIX_HOURS'
        report={'state':level,'session_seconds':round(session,1),'seconds_since_confirmed_ticket':round(idle,1),
                'candidate_count':total,'viable_count':viable,'owned_active_tickets':len(tickets),
                'last_confirmation_at':self.last_confirmed_at,'reasons':reasons,
                'forced_orders':0,'risk_limits_modified':False}
        return report
