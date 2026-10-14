"""Reservas del libro MT5 y solicitudes inciertas, con evidencia por ticket.

Una cancelación sin acuse conserva su riesgo original hasta conciliarse. Si un
diario antiguo omitió el importe, se reconstruye con sus niveles y volumen;
no se confunde ese campo ausente con una operación sin SL. Las posiciones
manuales forman parte del presupuesto, pero nunca se modifican aquí.
"""
import math


def finite(value, positive=False):
    try:
        result=float(value)
        return result if math.isfinite(result) and result>=(1e-300 if positive else 0) else None
    except (TypeError,ValueError):return None


def identifier(value):
    try:return max(0,int(value or 0))
    except (TypeError,ValueError,OverflowError):return 0


def order_type(value):
    try:
        typ=int(value)
        return typ if typ in range(8) and float(value)==typ else None
    except (TypeError,ValueError,OverflowError):return None


def matching_objects(g,snap,symbol,intent):
    """Un comentario vacío o de otro símbolo no confirma una solicitud."""
    req=intent.get('request') or {};op=intent.get('operation')
    ids={identifier(intent.get('order')),identifier(req.get('order'))}-{0}
    comment=str(req.get('comment') or '') if op=='open' else ''
    found=[]
    for kind,pool in (('pending',snap.orders),('position',snap.positions)):
        for obj in pool:
            if str(obj.symbol)!=str(symbol):continue
            owned=g.owned_order(obj) if kind=='pending' else g.owned(obj)
            if op=='open' and not owned:continue
            matched=identifier(obj.ticket) in ids or (kind=='position' and identifier(getattr(obj,'identifier',0)) in ids)
            if matched or (not ids and comment and owned and str(getattr(obj,'comment',''))==comment):found.append((kind,obj))
    return found


def levels_cost(g,symbol,side,volume,entry,sl,evaluation=None,swap=0):
    from execution import Blocked
    if side not in (1,-1) or any(finite(v,positive=True) is None for v in (volume,entry,sl)):
        raise Blocked('Niveles/volumen de reserva incompletos o sin SL')
    q=g.reserve_quote(symbol,evaluation);info=g.valuation_call(evaluation,'symbol_info',symbol)
    if info is None:raise Blocked('Sin reglas MT5 para valorar el ticket')
    slip=max(q.spread*g.cfg['risk']['slippage_spread_fraction'],float(info.trade_tick_size or info.point)*2)
    profit=g.profit(symbol,side,float(volume),float(entry),float(sl)-side*slip,evaluation)
    if not math.isfinite(float(swap)):raise Blocked('Swap de reserva inválido')
    risk=max(0.0,-profit-float(swap))+g.cfg['risk']['round_turn_commission_per_lot']*float(volume)
    margin=g.valuation_call(evaluation,'order_calc_margin',0 if side==1 else 1,symbol,float(volume),float(entry))
    return risk,finite(margin)


def intent_cost(g,symbol,intent,evaluation=None):
    """Reconstruir una reserva antigua sin inventar lote ni acercar el SL."""
    from execution import Blocked
    req=intent.get('request') or {};before=intent.get('before') or {};plan=intent.get('plan') or {}
    if any(row.get('symbol') not in (None,'',symbol) for row in (req,before,plan)):
        return None,None,'Datos de la solicitud pertenecen a otro símbolo; falta evidencia MT5'
    risk=finite(intent.get('risk'));margin=finite(intent.get('margin'))
    recovered=False;costs=[];proposals=[]
    if before and finite(before.get('entry'),positive=True) is not None and finite(before.get('sl'),positive=True) is None:
        return None,None,'Ticket original sin SL calculable; solicitud todavía sin confirmar'
    volume=req.get('volume',before.get('volume'))
    typ=order_type(req.get('type',before.get('type')))
    if typ is not None and typ in range(8):
        entry=req.get('stoplimit') if typ in (6,7) else req.get('price')
        proposals.append((1 if typ%2==0 else -1,volume,entry,req.get('sl')))
    if before and order_type(before.get('type')) is not None:
        typ=int(before['type']);entry=before.get('stoplimit') if typ in (6,7) else before.get('entry')
        proposals.append((1 if typ%2==0 else -1,before.get('volume'),entry,before.get('sl')))
    if plan:
        proposals.append((plan.get('side'),volume,plan.get('entry'),plan.get('sl')))
    for side,vol,entry,sl in proposals:
        if side not in (1,-1) or any(finite(v,positive=True) is None for v in (vol,entry,sl)):continue
        try:costs.append(levels_cost(g,symbol,side,vol,entry,sl,evaluation))
        except Blocked:continue
    if costs:
        recovered=risk is None or margin is None
        risk=max([r for r,_ in costs]+([] if risk is None else [risk]))
        margins=[m for _,m in costs if m is not None]
        if margins:margin=max(margins+([] if margin is None else [margin]))
    source='Reserva reconstruida con niveles y volumen del diario' if recovered else 'Reserva registrada antes del envío'
    if risk is None:source='Solicitud sin importe ni niveles/volumen suficientes; falta evidencia MT5'
    return risk,margin,source


def reservation_ledger(g,snap,ignore_orders=(),evaluation=None):
    from execution import Blocked
    ignored={int(ticket) for ticket in ignore_orders}
    # El objeto Snapshot puede contener tickets mutables (FakeMT5/conectores) y
    # el diario puede cambiar tras conciliar. La identidad Python no prueba que
    # las reservas sigan siendo las mismas. Usar los datos efectivos del libro.
    key=('reservation_ledger',tuple(sorted(ignored)),
        tuple((str(o.symbol),int(o.ticket),int(o.type),int(o.magic),float(o.volume_current),
            float(o.price_open),float(o.sl),getattr(o,'price_stoplimit',0)) for o in snap.orders),
        tuple((str(p.symbol),int(p.ticket),int(p.type),int(p.magic),float(p.volume),
            float(p.price_open),float(p.sl),float(getattr(p,'swap',0))) for p in snap.positions),
        float(snap.account.balance),float(snap.account.equity),float(snap.account.margin_free),
        str(getattr(snap.account,'currency','')),repr(g.journal.data['intents']),repr(g.cfg['risk']),
        bool(g.cfg['manage_legacy_akira']))
    if evaluation is not None and key in evaluation:return evaluation[key]
    cap=g.total_cap(snap);rows=[];visible={};unknown=False
    for kind,pool in (('position',snap.positions),('pending',snap.orders)):
        for obj in pool:
            if kind=='pending' and int(obj.ticket) in ignored:continue
            symbol=str(obj.symbol);typ=int(obj.type);risk=None;margin=None;reason='Niveles vigentes en MT5'
            volume=float(obj.volume if kind=='position' else obj.volume_current)
            if volume==0:continue
            entry=float(obj.price_open)
            try:
                if kind=='position' and typ not in (0,1):raise Blocked('Tipo de posición no reconocido')
                if kind=='pending' and typ not in (2,3,4,5,6,7):raise Blocked('Tipo de pendiente no reconocido')
                if kind=='pending' and typ in (6,7):
                    entry=float(getattr(obj,'price_stoplimit',0));reason='SL y precio Limit de la Stop Limit MT5'
                risk,margin=levels_cost(g,symbol,1 if typ%2==0 else -1,volume,entry,float(obj.sl),evaluation,
                    float(getattr(obj,'swap',0)) if kind=='position' else 0)
            except Blocked as exc:reason=str(exc)
            amount=cap if risk is None else risk;unknown=unknown or risk is None
            # El margen actual de las posiciones ya está en account.margin.
            future=0.0 if kind=='position' else (max(0.0,float(snap.account.margin_free)) if margin is None else margin)
            row={'kind':kind,'symbol':symbol,'ticket':int(obj.ticket),'type':typ,'volume':finite(volume),'entry':finite(entry),'sl':finite(obj.sl),
                 'owned':g.owned(obj) if kind=='position' else g.owned_order(obj),'risk_usd':risk,'reserved_usd':amount,
                 'future_margin_usd':future,'risk_known':risk is not None,'reason':reason}
            rows.append(row);visible[kind,int(obj.ticket)]=row
    for symbol,intent in g.journal.data['intents'].items():
        op=intent.get('operation')
        if op not in ('open','cancel','modify_order'):continue
        matches=matching_objects(g,snap,symbol,intent)
        covered=[visible[kind,int(obj.ticket)] for kind,obj in matches if (kind,int(obj.ticket)) in visible]
        # Un retiro no añade exposición al ticket que todavía aparece en MT5.
        # Una edición sí reserva el mayor riesgo entre el SL anterior y el nuevo.
        if covered and (op=='cancel' or (op=='modify_order' and any(r['kind']=='position' for r in covered))):
            risk,margin,reason=0.0,0.0,'Reserva incluida en el ticket visible MT5'
        else:
            risk,margin,reason=intent_cost(g,symbol,intent,evaluation)
            req=intent.get('request') or {};vol=finite(req.get('volume'),positive=True)
            full_visible=bool(covered and (op!='open' or (vol is not None and sum(r['volume'] or 0 for r in covered)>=vol-1e-9)))
            if full_visible and op=='open':risk,margin,reason=0.0,0.0,'Reserva incluida en el ticket visible MT5'
            elif covered:
                if any(not r['risk_known'] for r in covered):risk=0.0
                elif risk is not None:risk=max(0.0,risk-sum(r['risk_usd'] for r in covered))
                if margin is not None:margin=max(0.0,margin-sum(r['future_margin_usd'] for r in covered))
        amount=cap if risk is None else risk;unknown=unknown or risk is None
        req=intent.get('request') or {}
        rows.append({'kind':'intent','symbol':symbol,'ticket':identifier(req.get('order')) or identifier(intent.get('order')),
            'operation':op,'owned':True,'risk_usd':risk,'reserved_usd':amount,
            'future_margin_usd':max(0.0,float(snap.account.margin_free)) if margin is None else margin,
            'risk_known':risk is not None,'reason':reason,'retcode':intent.get('retcode'),
            'matched_tickets':[int(obj.ticket) for _,obj in matches]})
    total=sum(r['reserved_usd'] for r in rows)
    result={'cap_usd':cap,'reserved_usd':total,'available_usd':max(0.0,cap-total),'risk_known':not unknown,
        'future_margin_usd':sum(r['future_margin_usd'] for r in rows),'currency':str(getattr(snap.account,'currency','')),
        'positions':len(snap.positions),'pending_orders':len(snap.orders),'unconfirmed_requests':len(g.journal.data['intents']),
        'rows':rows}
    if evaluation is not None:evaluation[key]=result
    return result


def reservation_reason(ledger):
    currency=ledger.get('currency') or 'moneda de cuenta';rows=[r for r in ledger['rows'] if r['reserved_usd']>0 or not r['risk_known']]
    if rows:
        row=max(rows,key=lambda r:(not r['risk_known'],r['reserved_usd']))
        name={'position':'Posición','pending':'Pendiente','intent':'Solicitud sin confirmar'}[row['kind']]
        owner='AKIRA' if row['owned'] else 'manual/externa'
        main=f"{name} {owner} {row['symbol']}"+(f" #{row['ticket']}" if row.get('ticket') else '')
        main+=' · '+(f"reserva {row['reserved_usd']:.2f} {currency}" if row['risk_known'] else row['reason'])
    else:main='Sin exposición; el límite conjunto calculado de la cuenta es cero'
    return (main+f". Riesgo conjunto: reservado {ledger['reserved_usd']:.2f} / límite {ledger['cap_usd']:.2f} {currency}; "
            f"disponible {ledger['available_usd']:.2f} {currency}")


def ledger_text(ledger,limit=6):
    if not ledger:return 'Esperando libro MT5 para calcular las reservas.'
    currency=ledger.get('currency') or 'moneda de cuenta'
    text=f"Riesgo conjunto: {ledger['reserved_usd']:.2f} / {ledger['cap_usd']:.2f} {currency} reservado · disponible {ledger['available_usd']:.2f} {currency}"
    rows=sorted((r for r in ledger['rows'] if r['reserved_usd']>0 or not r['risk_known']),
                key=lambda r:(not r['risk_known'],r['reserved_usd']),reverse=True)
    for r in rows[:limit]:
        kind={'position':'posición','pending':'pendiente','intent':'solicitud sin confirmar'}[r['kind']]
        author='AKIRA' if r['owned'] else 'manual/externa'
        value=f"{r['reserved_usd']:.2f} {currency}" if r['risk_known'] else 'riesgo no calculable; reserva del límite completo'
        text+=f"\n{kind} {author} {r['symbol']}"+(f" #{r['ticket']}" if r.get('ticket') else '')+f" · {value} · {r['reason']}"
    if len(rows)>limit:text+=f"\n{len(rows)-limit} reservas adicionales en EXPORTAR ESTADO."
    return text
