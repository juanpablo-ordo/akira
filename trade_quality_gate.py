"""Read-only, causal entry checks. No requests, code generation or SL changes."""
import math

def value(row,key,default=None):return row.get(key,default) if isinstance(row,dict) else getattr(row,key,default)
def num(x,default=0):
    try:x=float(x);return x if math.isfinite(x) else default
    except (ValueError,TypeError,OverflowError):return default


def pending_admission(config,plan):
    from capital_guard import rules
    policy=rules(config)
    if value(plan,'lane')!='PENDING' or not (policy['enabled'] and policy['strict_pending_quality']):
        return {'allowed':True,'reason':'','enabled':False}
    from strategy import symbol_strategy
    cfg=symbol_strategy(config,value(plan,'symbol'));key=str(value(plan,'key','')).upper()
    structural=value(plan,'signal_timeframe') in ('H1','H4','D1','W1') or any(t in key for t in (':H1:',':H4:',':D1:',':W1:')) or 'MAPA STRUCTURAL' in str(value(plan,'reason','')).upper()
    quality=num(value(plan,'quality_score'));activation=num(value(plan,'activation_score'))
    for field,current in (('base_quality_score',quality),('base_activation_score',activation)):
        baseline=value(plan,field)
        if baseline is not None:
            if field=='base_quality_score':quality=min(current,num(baseline))
            else:activation=min(current,num(baseline))
    group='structural' if structural else 'tactical'
    min_quality=float(cfg.get('pending_'+group+'_quality_min',84 if structural else 76))
    min_activation=float(cfg.get('pending_'+group+'_activation_min',18 if structural else 42))
    combined=(.9*quality+.1*activation) if structural else (.75*quality+.25*activation)
    grade='A+' if combined>=90 else 'A' if combined>=84 else 'B+' if combined>=76 else 'B'
    required=str(config.get('execution',{}).get('minimum_structural_grade','A')).upper()
    ranks={'B':0,'B+':1,'A':2,'A+':3}
    side=num(value(plan,'side'));risk=side*(num(value(plan,'entry'))-num(value(plan,'sl')))
    rr=side*(num(value(plan,'tp'))-num(value(plan,'entry')))/risk if risk>0 else 0
    minimum_rr=float(cfg.get('min_rr_pending',2.2));reason=''
    if quality<min_quality or activation<min_activation:reason=f'Calidad estricta: {quality:.1f}/{activation:.1f} frente a {min_quality:g}/{min_activation:g}; una alternativa no reduce los umbrales.'
    elif ranks.get(grade,-1)<ranks.get(required,2):reason=f'Calidad estricta: grado {grade}; se exige {required} también en el mapa táctico.'
    elif rr+1e-9<minimum_rr:reason=f'Calidad estricta: R:R {rr:.2f} inferior al mínimo configurado {minimum_rr:g}; la vía rápida no lo rebaja.'
    return {'allowed':not reason,'reason':reason,'enabled':True,'grade':grade,'required_grade':required,
        'quality':quality,'activation':activation,'minimum_quality':min_quality,'minimum_activation':min_activation,'minimum_rr':minimum_rr}

def family(plan):
    key=str(value(plan,'key','')).upper();kind=value(plan,'kind');lane=value(plan,'lane')
    if lane=='RUNNER':return 'RUNNER_RETEST_M5' if value(plan,'signal_timeframe')=='M5' else 'RUNNER_CONTINUACION_M15'
    if any(x in key for x in ('REV','SWEEP','RECLAIM')):return 'REVERSION_CONFIRMADA'
    if 'RANGE' in key:return 'RANGO_RECHAZO'
    return 'PENDIENTE_RETROCESO' if kind=='LIMIT' else 'PENDIENTE_RUPTURA'

def owned_outcomes(g):
    """Only journaled, complete own outcomes; never infer them from screenshots."""
    out={}
    for meta in g.journal.data.get('positions',{}).values():
        c=meta.get('closure') or {};p=meta.get('plan') or {}
        if c.get('state')!='CONFIRMADO MT5' or not c.get('deal_ids') or meta.get('lane') not in ('PENDING','RUNNER'):continue
        # These journal records are created only for owned positions. New records
        # additionally carry magic. Older records require an actual stored plan.
        from execution import OWN_PENDING,OWN_RUNNER,LEGACY_PENDING,LEGACY_POSITIONS
        magic=meta.get('magic')
        if magic is not None and int(magic) not in ({OWN_PENDING,OWN_RUNNER}|(LEGACY_PENDING|LEGACY_POSITIONS if g.cfg.get('manage_legacy_akira') else set())):continue
        if magic is None and not p.get('key'):continue
        pid=str(c['position_id']);out[pid]={**c,'pnl':c['net'],'closed_at':c['exit_time'],'plan':p,
            'strategy_id':family(p),'lane':meta['lane'],'initial_sl':meta.get('initial_sl'),
            'mfe_r':meta.get('max_favorable_r'),'mae_r':meta.get('max_adverse_r')}
    for pid,r in g.journal.data.get('pending_outcomes',{}).items():
        if str(pid) not in out and r.get('deal_ids'):
            out[str(pid)]={**r,'strategy_id':r.get('strategy_id') or 'SIN_TESIS_REGISTRADA','lane':'PENDING'}
        elif str(pid) in out and r.get('deal_ids') and set(r['deal_ids']).issuperset(out[str(pid)].get('deal_ids',[])):
            # Associated charges can arrive after the initial closure receipt.
            # A complete newer own history supersedes the old net, never drops fees.
            out[str(pid)].update(pnl=r['pnl'],net=r['pnl'],deal_ids=r['deal_ids'])
    return sorted(out.values(),key=lambda r:(num(r.get('closed_at')),str(r.get('position_id'))))

def evaluate(plan,frames,outcomes,now,strict=True,config=None):
    side=int(value(plan,'side',0));symbol=value(plan,'symbol');checks=[]
    def check(name,ok,reason):checks.append({'name':name,'passed':bool(ok),'reason':reason});return bool(ok)
    recent=[r for r in outcomes if r.get('symbol')==symbol and int(r.get('side',0))==side
        and 0<=now-num(r.get('closed_at',r.get('exit_time')))<=86400]
    last=recent[-1] if recent else {};lost=bool(last and num(last.get('pnl',last.get('net')))<0)
    m15=frames.get('M15');h1=frames.get('H1')
    bars=value(m15,'bars',[]) or [];last_bar=bars[-1] if bars else {}
    if strict:
        ready=bool(m15 and h1 and bars and (value(h1,'bars',[]) or []))
        if ready:
            ht=value(h1,'bars')[-1]
            if config is not None:
                from market_state import MarketDataFreshnessValidator
                ready=all(MarketDataFreshnessValidator.inspect(symbol,tf,frames[tf],now,config)['ready'] for tf in ('M15','H1'))
            else:ready=0<=now-(num(value(last_bar,'time'))+900)<=960 and 0<=now-(num(value(ht,'time'))+3600)<=7200
        check('Velas estructurales cerradas y actuales',ready,'Faltan M15/H1 cerradas y actuales; no convertir datos ausentes en una entrada de alta calidad.')
    if lost:
        # One full structural candle must start after the actual exit. A new tick
        # or a rewritten candidate id cannot reset a losing thesis.
        closed=num(value(last_bar,'time'))+900<=now+2
        new=closed and num(value(last_bar,'time'))>=num(last.get('closed_at',last.get('exit_time')))
        check('Estructura nueva tras pérdida',new,'Esperando una vela M15 completa posterior al cierre perdedor #'+str(last.get('position_id'))+'. Se conservan SL/TP de posiciones y órdenes existentes.')
        streak=0
        for row in reversed(recent):
            if num(row.get('pnl',row.get('net')))>=0:break
            streak+=1
        if streak>=2:
            aligned=m15 and h1 and side*num(value(m15,'trend'))>.12 and side*num(value(h1,'trend'))>.18
            recovery=side*(num(value(last_bar,'close'))-num(value(last_bar,'open')))>=num(value(m15,'atr'))*.2>0
            check('Reentrada después de pérdidas consecutivas',aligned and recovery,'Dos o más pérdidas del mismo lado requieren una nueva estructura M15/H1 alineada y una vela M15 de recuperación con cuerpo de al menos 0,20 ATR. Una media rezagada no confirma el giro.')
    from entry_momentum import adverse_impulse
    impulse=adverse_impulse(plan,frames,now)
    if impulse:check('Impulso contrario cerca de la entrada',False,impulse['reason'])
    if strict and m15 and h1:
        atr=num(value(m15,'atr'));horizon=num(value(plan,'horizon_atr')) or num(value(plan,'signal_atr')) or atr
        risk=side*(num(value(plan,'entry'))-num(value(plan,'sl')))
        check('Espacio estructural de SL',horizon>0 and risk>=horizon*.35,'El SL debe dejar al menos 0,35 ATR del horizonte declarado. Un presupuesto bajo no autoriza estrechar su invalidación.')
        if value(plan,'kind')=='LIMIT' and side*num(value(m15,'trend'))<-.18:
            m5=frames.get('M5');short=value(m5,'bars',[]) or []
            recovering=False
            if len(short)>=2:
                last,previous=short[-1],short[-2];stamp=num(value(last,'time'))
                body=side*(num(value(last,'close'))-num(value(last,'open')))
                edge=num(value(previous,'high' if side==1 else 'low'))
                recovering=(0<=now-(stamp+300)<=600 and body>=num(value(m5,'atr'))*.2>0
                    and side*(num(value(last,'close'))-edge)>0)
            check('Recuperación antes de LIMIT contra M15',recovering,'La LIMIT va contra el impulso M15: esperar un cierre M5 de recuperación que supere el extremo de la vela anterior. Una H1 favorable no confirma el rebote por sí sola.')
        contrary=side*num(value(h1,'trend'))<-.18
        if contrary:
            # A future reversal STOP needs a trigger outside the whole M15 range,
            # not simply a level near the current price with a high score.
            window=bars[-12:];edge=max((num(value(b,'high')) for b in window),default=0) if side==1 else min((num(value(b,'low')) for b in window),default=0)
            entry=num(value(plan,'entry'));kind=value(plan,'kind')
            confirmed=len(bars)>=2 and all(side*(num(value(b,'close'))-num(value(b,'open')))>=atr*.2 for b in bars[-2:])
            trigger=kind=='STOP' and side*(entry-edge)>=atr*.05
            check('Reversión contra H1',bool(confirmed or trigger),'H1 está en contra: hacen falta dos cierres M15 de recuperación o un STOP más allá de toda la estructura reciente. El score o las noticias no sustituyen esa condición.')
    failures=[c for c in checks if not c['passed']]
    return {'allowed':not failures,'strategy_id':family(plan),'checks':checks,
        'reason':failures[0]['reason'] if failures else 'Condiciones de entrada compatibles con la estructura disponible; no es probabilidad de ganar.',
        'scope':'Comprobaciones causales; riesgo monetario, cuenta y broker se vuelven a validar en Gateway.'}
