"""Confirm exits from MT5 deals; disappearing tickets never prove a closure.

Read-only monitoring, one history lookup per cycle, with persistent evidence.
"""
import math

REASONS={0:'Cierre desde la terminal',1:'Cierre desde el móvil',2:'Cierre desde la web',
    3:'Cierre por programa / EA',4:'Stop Loss ejecutado por MT5',5:'Take Profit ejecutado por MT5',
    6:'Stop Out del broker',7:'Rollover',8:'Margen de variación',9:'Ajuste por split',10:'Acción corporativa'}

def value(row,key,default=None):
    return row.get(key,default) if isinstance(row,dict) else getattr(row,key,default)

def number(value,default=0.0):
    try:
        result=float(value)
        return result if math.isfinite(result) else default
    except (ValueError,TypeError,OverflowError):return default

def summarize_closure(ticket,meta,deals):
    pid=int(meta.get('identifier') or ticket)
    rows=[d for d in deals or () if int(value(d,'position_id',0) or 0)==pid]
    trades=[d for d in rows if value(d,'type') in (0,1)]
    if any(value(d,'entry')==2 for d in trades):return None
    ins=[d for d in trades if value(d,'entry')==0];outs=[d for d in trades if value(d,'entry') in (1,3)]
    vin=sum(number(value(d,'volume')) for d in ins);vout=sum(number(value(d,'volume')) for d in outs)
    if not ins or not outs or vin<=0 or abs(vout-vin)>1e-8:return None
    last=max(outs,key=lambda d:(number(value(d,'time')),number(value(d,'ticket'))))
    try:deal_ids=[int(value(d,'ticket')) for d in rows]
    except (TypeError,ValueError,OverflowError):return None
    if not deal_ids or any(ticket<=0 for ticket in deal_ids):return None
    exited=number(value(last,'time'));entered=min(number(value(d,'time')) for d in ins)
    if exited<entered:return None
    reason=value(last,'reason');cause=REASONS.get(reason,'Motivo no suministrado por MT5')
    decisions=[r for r in meta.get('management_events',[]) if r.get('operation')=='close']
    decision=decisions[-1].get('reason','') if decisions else ''
    matched=[r for r in decisions if (number(r.get('deal'))>0 and int(number(r.get('deal')))==int(value(last,'ticket')))
        or (number(r.get('order'))>0 and int(number(r.get('order')))==int(number(value(last,'order'))))]
    if matched:decision=matched[-1].get('reason','')
    initiator='AKIRA' if matched and decision and reason not in (4,5,6) else 'MT5'
    if initiator=='AKIRA':cause='AKIRA: '+decision
    net=sum(sum(number(value(d,k)) for k in ('profit','commission','swap','fee')) for d in rows)
    return {'id':'CLOSE:'+str(pid)+':'+str(value(last,'ticket')),'state':'CONFIRMADO MT5',
        'ticket':int(ticket),'position_id':pid,'symbol':str(value(ins[0],'symbol',meta.get('symbol',''))),
        'side':int(meta.get('side') or (1 if value(ins[0],'type')==0 else -1)),
        'entry_time':entered,'exit_time':exited,'entry_price':sum(number(value(d,'price',meta.get('entry',0)))*number(value(d,'volume')) for d in ins)/vin,
        'exit_price':sum(number(value(d,'price'))*number(value(d,'volume')) for d in outs)/vout,
        'volume':vin,'net':round(net,8),'broker_reason':reason,'cause':cause,'initiator':initiator,'exit_deal_id':int(value(last,'ticket')),
        'decision_reason':decision,'request_matched_to_exit':bool(matched),'deal_ids':deal_ids,
        'evidence':'Volumen de entrada y salida completo en historial MT5; incluye comisión, swap y tasas.'}

class ClosureMonitor:
    def __init__(self,g):
        self.g=g;self.retry={};self.started=g.clock()

    def poll(self):
        g=self.g;now=g.clock()
        pending=[(ticket,row) for ticket,row in g.journal.data['positions'].items()
            if row.get('closed_observed_at') and not row.get('closure')
            and now-number(row.get('closed_observed_at'))<=86400
            and now>=self.retry.get(ticket,0)]
        if not pending:return
        ticket,row=max(pending,key=lambda item:number(item[1].get('closed_observed_at')))
        self.retry[ticket]=now+5
        try:
            deals=g.api.history_deals_get(position=int(row.get('identifier') or ticket))
        except Exception as exc:
            row['closure_history_state']='Historial no disponible: '+type(exc).__name__;return
        closure=summarize_closure(ticket,row,deals)
        if not closure:
            row['closure_history_state']='Esperando evidencia de salida completa en MT5; no se afirma un cierre ni un resultado.'
            return
        closure['currency']=g.account_currency
        closure['id']='CLOSE:'+str((g.identity or ('unknown',))[0])+':'+str(closure['position_id'])+':'+str(closure['exit_deal_id'])
        row['closure']=closure;row['closure_history_state']='Historial completo confirmado'
        self.retry.pop(ticket,None)
        merged={int(d.ticket):d for d in g.history};merged.update({int(d.ticket):d for d in deals or ()})
        g.history=list(merged.values())
        g.journal.save()
        g.log.event(closure['symbol'],'CIERRE CONFIRMADO · '+closure['cause'],
            operation='position_closed',closure=closure,reason=closure['cause'],ticket=closure['ticket'])

    def rows(self):
        rows=[row['closure'] for row in self.g.journal.data['positions'].values() if row.get('closure')]
        return sorted(rows,key=lambda row:row['exit_time'],reverse=True)[:50]
