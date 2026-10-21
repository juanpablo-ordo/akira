"""Pendientes activadas: mantener SL/TP de estructura y proteger después de avanzar."""
import math
from execution import BUY,Blocked
from strategy import round_price
from runner import runner_exit


class PositionManager:
    def __init__(self,g,planner):self.g,self.planner=g,planner;self.last_stats_save=0.0

    def restore_previous_protection(self,p,row):
        """Only existing legacy positions; never creates or adds market exposure."""
        if float(p.sl)>0:return False
        original=float(row.get('initial_sl',0) or (row.get('plan') or {}).get('sl',0) or 0)
        side=1 if int(p.type)==BUY else -1
        if original<=0:
            raise Blocked('Posición anterior sin SL ni invalidación registrada: añade protección en MT5; no inventar un corte monetario')
        return self.g.update_stop(p,original,reason='restaurar protección de posición anterior',allow_restore=True)

    def step(self,snap):
        g=self.g;now=g.clock()
        # SENTINEL/SNAPMAP OCO: si una pendiente propia se activa, retirar la
        # pendiente opuesta del mismo símbolo. Nunca toca órdenes manuales/otros EAs.
        if bool(g.cfg.get('pending',{}).get('oco_cancel_opposite_on_fill',True)):
            for p in snap.positions:
                if not g.owned(p):continue
                pside=1 if int(p.type)==BUY else -1
                for o in list(snap.orders):
                    if o.symbol!=p.symbol or not g.owned_order(o):continue
                    oside=1 if int(o.type)%2==0 else -1
                    if oside==pside:continue
                    try:g.cancel(o,'OCO SNAPMAP · la tesis opuesta se retira al activarse una posición propia')
                    except Blocked as exc:g.log.report(o.symbol,'OCO',str(exc))

        for p in snap.positions:
            if not g.owned(p) or p.symbol in g.journal.data['intents']:continue
            row=g.journal.data['positions'].get(str(p.ticket)) or {}
            try:
                if not g.owned_order(p):
                    self.restore_previous_protection(p,row)
                    continue
                plan=row.get('plan') or {};side=1 if int(p.type)==BUY else -1
                initial=float(row.get('initial_sl',0) or plan.get('sl',0) or 0)
                if initial<=0:
                    g.log.report(p.symbol,'PROTECCIÓN','Pendiente activada sin invalidación original: conservar niveles MT5 y revisar diario');continue
                if float(p.sl)<=0:
                    g.update_stop(p,initial,tp=float(p.tp) or float(plan.get('tp',0)),allow_restore=True);continue
                cache=self.planner.caches.get(p.symbol);frames=cache.frames if cache else {}
                structural_runner=(plan.get('lane')=='RUNNER' or (plan.get('lane')=='PENDING' and g.cfg['management'].get('pending_fills_as_runners',False))) and g.cfg['management'].get('runner_structure_only',True)
                if structural_runner:row['management_style']='RUNNER_ESTRUCTURAL'
                f=frames.get('M15') if structural_runner else frames.get('M15') or frames.get('M5')
                if structural_runner and not f:
                    row['protection_state']='Runner conserva SL: esperando estructura M15 confirmada'
                if not f and not structural_runner:continue
                q=g.quote(p.symbol);exit=q.bid if side==1 else q.ask
                risk=side*(float(p.price_open)-initial)
                if risk<=0:continue
                gained=side*(exit-float(p.price_open));rr=gained/risk
                row.setdefault('tracking_started_at',now)
                row['max_favorable_r']=max(float(row.get('max_favorable_r',0)),rr)
                row['max_adverse_r']=max(float(row.get('max_adverse_r',0)),-rr)
                row['last_rr']=rr
                row['max_favorable_usd']=max(float(row.get('max_favorable_usd',0)),float(getattr(p,'profit',0)))
                if now-self.last_stats_save>=10:g.journal.save();self.last_stats_save=now
                if now-float(row.get('time',getattr(p,'time',now)))<g.cfg['management']['minimum_hold_seconds']:continue
                if now-float(row.get('last_modify',0))<g.cfg['management']['modify_seconds']:continue
                if structural_runner and f:
                    entry_time=float(row.get('time',getattr(p,'time',now)))
                    reason=runner_exit(plan,frames,side,rr,g.cfg,entry_time=entry_time,now=now)
                    row['exit_review']={'time':now,'entry_time':entry_time,
                        'last_closed_m15':f.bars[-1].time+900,
                        'post_entry_candle':f.bars[-1].time>=entry_time,'reason':reason or 'Sin invalidación nueva posterior a la entrada'}
                    if reason:
                        if g.close_runner(p,reason):g.reconcile(g.snapshot())
                        continue
                if structural_runner and f and g.cfg['management'].get('extend_targets',False) and rr>=g.cfg['management'].get('extension_min_r',1.8):
                    h1=frames.get('H1')
                    strong=h1 and side*h1.trend>.18 and side*f.trend>.25 and f.extra.get('adx',0)>=22
                    if strong and row.get('last_extension_bar')!=f.bars[-1].time:
                        observed=[v for other in (f,h1) for v,_ in (other.highs if side==1 else other.lows)
                            if side*(v-float(p.tp))>f.atr*.3 and side*(v-exit)>f.atr*.5]
                        row['target_review']={'bar':f.bars[-1].time,'rr':rr,'continuation':bool(strong),'observed_targets':observed[:4]}
                        if observed:
                            extended=min(observed,key=lambda v:side*(v-exit))-side*f.atr*.06
                            if g.update_stop(p,float(p.sl),tp=extended,reason='continuación M15/H1: siguiente pivote observado, SL conservado'):
                                row['last_extension_bar']=f.bars[-1].time;row['last_modify']=now;g.journal.save();continue
                if rr<g.cfg['management']['breakeven_at_r']:continue
                # Cover spread/estimated fee; no profit closure at a cent target.
                fee=max(g.cfg['risk']['round_turn_commission_per_lot'],float(row.get('entry_fees_per_lot',0) or 0))*float(p.volume)
                unit=abs(g.profit(p.symbol,side,float(p.volume),float(p.price_open),float(p.price_open)+side))
                noise=max(q.spread*1.5,fee/max(unit,1e-9))
                target=float(p.price_open)+side*noise
                if structural_runner:
                    entry_time=float(row.get('time',getattr(p,'time',now)))
                    # A structural pivot can improve protection, but must not veto
                    # the configured progress floor after the current quote reaches R.
                    # This uses no historical peak to force an unexecutable stop.
                    progress=g.cfg['management'].get('protect_progress',True)
                    swings=[v for v,t in ((f.lows if side==1 else f.highs)[-10:] if f else ())
                        if t>=entry_time and t>int(plan.get('bar_time',0))
                        and side*(exit-v)>max(f.atr*.3,noise)]
                    if not swings:
                        if not progress:
                            row['protection_state']='Runner conserva SL: falta pivote M15 posterior confirmado';continue
                        reason='avance hasta umbral R: cubrir costes estimados sin esperar pivote M15'
                        row['protection_state']='Candidato de protección de avance; aún sin pivote M15 posterior'
                    else:
                        swing=max(swings) if side==1 else min(swings)
                        structural=swing-side*max(f.atr*g.cfg['management']['trail_atr'],noise)
                        if not progress or side*(structural-target)>0:
                            target=structural
                            reason='runner: pivote M15 posterior confirmado; conservar margen ATR'
                        else:
                            reason='avance hasta umbral R: cubrir costes estimados; pivote M15 no mejora protección'
                        row['protection_state']='Candidato de protección: avance y pivote M15 revisados'
                else:
                    reason='pendiente activada: breakeven/trailing de estructura'
                if not structural_runner:
                  if rr>=g.cfg['management']['trail_at_r']:
                    swings=[v for v,_ in (f.lows if side==1 else f.highs)[-10:] if side*(exit-v)>max(f.atr*.3,noise)]
                    if swings:
                        swing=max(swings) if side==1 else min(swings)
                        structural=swing-side*max(f.atr*g.cfg['management']['trail_atr'],noise)
                        if side*(structural-target)>0:target=structural
                if side*(target-float(p.sl))>float(g.api.symbol_info(p.symbol).trade_tick_size or .01)*2:
                    if g.update_stop(p,target,reason=reason):
                        row['last_modify']=now
                        row['protection_state']='Protección solicitada; esperando confirmación MT5'
                        g.journal.save()
            except Blocked as e:g.log.report(p.symbol,'PROTECCIÓN',str(e))
