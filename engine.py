"""Motor de pendientes y runners: analizar, dimensionar, ejecutar y confirmar."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict,replace
from types import SimpleNamespace
import copy,math,time
from execution import Blocked,MarketPaused,order_plan,BUY
from strategy import Plan,quote_identity,symbol_strategy,build_fast_future_map_pendings,build_snap_analyst_pendings
from planner import PendingPlanner
from pending_portfolio import select_portfolio,pending_priority,pending_overlap
from learning import PendingLearner
from position_manager import PositionManager
from akira_version import BUILD_ID
from evolution import FEATURE_VERSION,entry_features
from runner import runner_plan
from decision_status import decision_status
from trade_review import assess_plan
from market_calendar import state_for
from datetime import datetime,timezone


class Engine:
    def __init__(self,g,cfg,log,context=None):
        self.g,self.cfg,self.log,self.context=g,cfg,log,context
        self.learner=PendingLearner(g);self.planner=PendingPlanner(g,cfg,log,self.learner)
        self.positions=PositionManager(g,self.planner)
        self.analysis=ThreadPoolExecutor(max_workers=2,thread_name_prefix='AkiraIndicators')
        for c in self.planner.caches.values():c.analysis_executor=self.analysis
        self.confirmations={};self.candidates={};self.status={};self.lifecycle={};self.paused=False
        self.initialized=False;self.cycle=0;self.started={};self.last_scan={};self.last_checked={};self.duration_ms=0.0
        self.dom_subscribed=set();self.dom_retry={};self.first_requests={};self.allocation_reasons={}
        self.quotes={};self._last_research_submit=0.0;self._last_history=0.0
        self.map_cache={};self.allocation_cache={};self._last_heartbeat=0.0
        self._last_snapshot_dump=0.0
        self.runner_views={};self.deep_initialized=False
        self.pending_cycles={}
        self.allocation_checks={}
        self._last_view={};self._analysis_evaluations={}
        self._study_due=0.0
        self.pending_checks={};self.pending_check_queue=[];self.pending_verification_requests={};self._pending_auto_due=0.0
        self.review_requirements={};self.review_account=[]
        self.review_preferences=self.g.journal.path.with_name('pending_review_preferences.json')
        try:
            raw=self.review_preferences.read_text(encoding='utf-8')
            saved=__import__('json').loads(raw) if len(raw)<=65536 else {}
            self.review_account=saved.get('account',[])
            self.review_requirements={k:v for k,v in saved.get('required',{}).items() if isinstance(v,dict) and v.get('symbol') in cfg['symbols'] and isinstance(v.get('key'),str)}
        except (OSError,ValueError,TypeError,AttributeError):pass
        self.g.pending_review_guard=self.pending_review_guard
        self.g.entry_quality_guard=self.entry_quality_guard
        self.entry_checks={};self._confirmed_outcomes=[]
        self._quality_notices=set()
        from activity_watchdog import SessionWatchdog
        self.session_watchdog=SessionWatchdog(self.g.clock())

    def close(self):
        # Existing broker SL/TP and pending orders survive application shutdown.
        self.analysis.shutdown(wait=False,cancel_futures=True)
        for s in self.dom_subscribed:
            try:self.g.api.market_book_release(s)
            except (AttributeError,RuntimeError):pass

    def update_book(self,symbol):
        api=self.g.api;now=self.g.clock()
        if not hasattr(api,'market_book_add'):return
        try:
            if symbol not in self.dom_subscribed and now>=self.dom_retry.get(symbol,0):
                if api.market_book_add(symbol):self.dom_subscribed.add(symbol)
                else:self.dom_retry[symbol]=now+60
            rows=api.market_book_get(symbol) if symbol in self.dom_subscribed else None
            if rows:
                buy=sum(float(getattr(x,'volume_dbl',x.volume)) for x in rows if int(x.type)==2)
                sell=sum(float(getattr(x,'volume_dbl',x.volume)) for x in rows if int(x.type)==1)
                self.planner.broker_book[symbol]={'state':'DOM del bróker','imbalance':(buy-sell)/max(buy+sell,1e-9),'levels':len(rows)}
            else:self.planner.broker_book[symbol]={'state':'DOM no suministrado por el bróker'}
        except Exception as e:self.planner.broker_book[symbol]={'state':'DOM no disponible: '+type(e).__name__}

    def warmup(self,fast=False):
        now=self.g.clock()
        # REFLEX: primero M1/M5 de TODOS los símbolos, después estructura HTF.
        # Así BTC no monopoliza el arranque mientras XAU sigue en CARGANDO. W1 no
        # bloquea el primer mapa; MarketCache lo refresca después en segundo plano.
        for symbol,cache in self.planner.caches.items():
            if not self.market_state(symbol)['open']:continue
            self.log.report(symbol,'CARGANDO','REFLEX · cargando M1/M5 y preparando mapa futuro')
            cache.prime_critical(now)
        # FLASHMAP: M15/H1 de TODOS los símbolos antes de profundizar.
        # Esto permite un primer mapa BTC+XAU sin esperar M30/H4/D1 ni Internet.
        for symbol,cache in self.planner.caches.items():
            if not self.market_state(symbol)['open']:continue
            cache.prime_fast_structural(now)
        # Después de que AMBOS ya tienen M15/H1, completar M30/H4/D1. Así XAU no
        # queda detrás de todo el stack HTF de BTC y la interfaz abre con todos los
        # marcos disponibles desde la primera publicación.
        if not fast:self.complete_warmup()
        self.initialized=True
        self.submit_context()

    def submit_context(self):
        if not self.context:return
        try:self.context.submit(self.research_snapshot())
        except Exception as exc:self.log.report('IA','CONTEXTO AUXILIAR',type(exc).__name__+': '+str(exc)[:220])

    def complete_warmup(self):
        if self.deep_initialized:return
        for symbol,cache in self.planner.caches.items():
            if self.market_state(symbol)['open']:cache.prime_deep_structural(self.g.clock())
        self.deep_initialized=True

    def market_state(self,symbol):
        state=state_for(symbol,datetime.fromtimestamp(self.g.clock(),timezone.utc),self.cfg)
        return {'open':state.open,'scheduled_closed':not state.open,'state':state.state,
            'next_open':state.next_open_guatemala,'schedule_source':state.source}

    def try_runner(self,symbol,q,required_side=0):
        """Retirar pendientes propias y confirmar antes de un runner; no duplicar."""
        g=self.g
        if self.cfg['execution'].get('pending_only',False):
            self.runner_views[symbol]={'state':'ENTRADAS SOLO PENDIENTES','detail':'Las posiciones activadas se gestionan como runners; no se abren entradas directas a mercado.'}
            return False
        plan,detail=runner_plan(symbol,self.planner.caches[symbol].frames,q,self.cfg,self.planner.research_context)
        row={'state':'ESPERANDO CONFIRMACIÓN','detail':detail,'plan':plan.to_dict() if plan else None}
        self.runner_views[symbol]=row
        if plan is None:return False
        if required_side and plan.side!=required_side:
            row.update(state='DIRECCIÓN SOLICITADA SIN CONFIRMACIÓN',plan=None,
                       detail=f'Solicitaste {"LONG" if required_side==1 else "SHORT"}; la señal disponible confirma el lado contrario. Conservar pendientes.')
            return False
        snap=g.snapshot()
        if any(p.symbol==symbol for p in snap.positions):
            row.update(state='POSICIÓN ACTIVA',detail='Una posición ya ocupa este símbolo; se gestiona su protección')
            return False
        entries=g.journal.data.get('runner_entries',{})
        if plan.key in entries:
            row.update(state='TESIS YA SOLICITADA',detail='Esperando nueva confirmación; no reabrir la misma vela')
            return False
        if any(str(key).startswith('RUN:'+symbol+':') and g.clock()-float(stamp)<self.cfg['runner']['entry_cooldown_seconds'] for key,stamp in entries.items()):
            row.update(state='ESPERANDO NUEVA TESIS',detail='Pausa entre runners del mismo símbolo')
            return False
        own=[o for o in snap.orders if o.symbol==symbol and g.owned_order(o)]
        # Preserve the original structural/loss veto in both preview and send.
        try:self.entry_quality_guard(plan,snap)
        except Blocked as exc:
            row.update(state='RUNNER BLOQUEADO',detail=str(exc));return False
        protection=g.runner_protection(plan,snap);row['capital_protection']=protection
        if not protection['allowed']:
            row.update(state='RUNNER EN PAUSA',detail=protection['reason'])
            return False
        ignored=tuple(int(o.ticket) for o in own)
        try:
            evaluation={}
            row['funding']=g.funding_diagnostic(plan,snap,ignored,evaluation=evaluation)
            g.permissions(snap)
            volume=g.volume_for_plan(plan,snap,ignored,evaluation=evaluation)
            validated,q,risk,reward,margin=g.validate_plan(plan,snap,ignored,volume=volume,evaluation=evaluation)
            row.update(plan=validated.to_dict(),volume=volume,risk=risk,reward=reward)
            self.entry_quality_guard(validated,snap)
            # Comprobar geometría/margen ANTES de retirar un mapa que sí era válido.
            for o in own:
                if not g.cancel(o,'Runner M15/H1 confirmado: retirar mapa antes de entrar'):
                    g.reconcile(g.snapshot())
                    row.update(state='REVISANDO RETIRO',detail='MT5 no confirmó retiro; runner en espera')
                    self.status[symbol]=dict(state=row['state'],detail=row['detail']);return True
                g.reconcile(g.snapshot())
                if symbol in g.journal.data['intents']:
                    row.update(state='RECONCILIANDO',detail='Retiro sin evidencia final; runner en espera')
                    self.status[symbol]=dict(state=row['state'],detail=row['detail']);return True
            # Una pendiente pudo ACTIVARSE durante el retiro: nueva foto y todos
            # los controles del Gateway impiden agregar otra entrada.
            if g.send_runner(self.with_learning_features(validated,q)):
                g.reconcile(g.snapshot())
                confirmed=[p for p in g.snapshot().positions if p.symbol==symbol and g.owned_order(p)]
                row.update(state='RUNNER CONFIRMADO' if confirmed else 'RUNNER SOLICITADO',
                           detail=f'{"LONG" if plan.side==1 else "SHORT"} · lote {volume:g} · riesgo estimado {risk:.2f} · SL/TP estructurales')
            else:row.update(state='RUNNER SIN CONFIRMACIÓN',detail='Revisar respuesta de MT5; no duplicar')
            self.status[symbol]=dict(state=row['state'],detail=row['detail']);return True
        except Blocked as exc:
            row.update(state='RUNNER BLOQUEADO',detail=str(exc));return False

    def review_runner(self,symbol,q,required_side=0):
        """La misma tesis de entrada, dimensionada sin retirar ni enviar órdenes."""
        g=self.g;snap=g.snapshot()
        plan,detail=runner_plan(symbol,self.planner.caches[symbol].frames,q,self.cfg,self.planner.research_context)
        row={'state':'ESPERANDO CONFIRMACIÓN','detail':detail,'plan':plan.to_dict() if plan else None}
        self.runner_views[symbol]=row
        if plan is None:return row
        if required_side and plan.side!=required_side:
            row.update(state='DIRECCIÓN SOLICITADA SIN CONFIRMACIÓN',plan=None,
                       detail=f'Solicitaste {"LONG" if required_side==1 else "SHORT"}; falta confirmación de ese lado.')
            return row
        try:
            self.entry_quality_guard(plan,snap)
            protection=g.runner_protection(plan,snap);row['capital_protection']=protection
            if not protection['allowed']:raise Blocked(protection['reason'])
            own=tuple(int(o.ticket) for o in snap.orders if o.symbol==symbol and g.owned_order(o))
            row['funding']=g.funding_diagnostic(plan,snap,own)
            entries=g.journal.data.get('runner_entries',{})
            if plan.key in entries:raise Blocked('Esta tesis runner ya fue solicitada; esperar otra confirmación')
            if any(str(key).startswith('RUN:'+symbol+':') and g.clock()-float(stamp)<self.cfg['runner']['entry_cooldown_seconds'] for key,stamp in entries.items()):
                raise Blocked('Pausa entre runners del mismo símbolo')
            g.permissions(snap)
            volume=g.volume_for_plan(plan,snap,own)
            validated,q,risk,reward,margin=g.validate_plan(plan,snap,own,volume=volume)
            self.entry_quality_guard(validated,snap)
            row.update(state='RUNNER LISTO · SIN ENVÍO',detail=detail,plan=validated.to_dict(),
                       volume=volume,risk=risk,reward=reward)
            if self.paused or self.cfg['mode']!='trade' or g.runtime_execution_block:
                row.update(state='RUNNER · ANÁLISIS',detail=g.runtime_execution_block or 'Motor en pausa/observación; sin envío')
        except Blocked as exc:row.update(state='RUNNER BLOQUEADO',detail=str(exc))
        return row

    def evidence_ready(self,symbol,now):
        cache=self.planner.caches[symbol];ok,reason=cache.ready(now)
        if not ok:return False,reason
        for name,seconds in (('M15',1800),('H1',7200)):
            f=cache.frames.get(name)
            if f is None or now-f.bars[-1].time>seconds or now-f.bars[-1].time<0:
                return False,'Esperando estructura cerrada y reciente '+name
        return True,'Datos técnicos vigentes'

    def confirm(self,key,q,reason,seconds=None):
        now=self.g.clock();identity=quote_identity(q)
        before=self.confirmations.get(key)
        if before is None or before['reason']!=reason:
            self.confirmations[key]={'reason':reason,'since':now,'ticks':1,'last':identity};return False
        if before['last']!=identity:before['ticks']+=1;before['last']=identity
        needed=self.cfg['pending']['replace_confirm_seconds'] if seconds is None else seconds
        return now-before['since']>=needed and before['ticks']>=self.cfg['pending']['replace_min_ticks']

    def invalidate_reason(self,order,old,symbol,q):
        side=old.side;ref=q.bid if side==1 else q.ask
        # LIMIT through its original invalidation cannot be a valid future thesis.
        if old.kind=='LIMIT' and side*(ref-old.sl)<=0:return 'Precio cruzó invalidación de la zona LIMIT'
        frames=self.planner.caches[symbol].frames
        from entry_momentum import adverse_impulse
        impulse=adverse_impulse(old,frames,self.g.clock(),q)
        if impulse:return impulse['reason']
        for name in ('M15','H1'):
            f=frames.get(name)
            if f and f.bars[-1].time>old.bar_time and side*(f.bars[-1].close-old.sl)<-f.atr*.04:
                return 'Vela cerrada '+name+' invalidó la zona original'
        return ''

    def matching(self,old,candidate):
        if (old.side,old.kind)!=(candidate.side,candidate.kind):return False
        a=self.planner.pending_slot(old.side,old.kind,old);b=self.planner.pending_slot(candidate.side,candidate.kind,candidate)
        horizon=max(old.horizon_atr,candidate.horizon_atr,old.atr,candidate.atr,1e-9)
        return a==b or abs(old.entry-candidate.entry)<=horizon*.22

    def lifecycle_action(self,symbol,plans,q,snap=None):
        g=self.g;now=g.clock();snap=snap or g.snapshot()
        evaluation={}
        own=[o for o in snap.orders if o.symbol==symbol and g.owned_order(o)]
        for o in sorted(own,key=lambda o:(float(getattr(o,'time_setup',0)),int(o.ticket))):
            meta=g.journal.data['orders'].get(str(o.ticket),{})
            old=order_plan(o,meta.get('plan'));key=(symbol,int(o.ticket))
            if old.sl<=0 or old.tp<=0:
                reason='Pendiente propia sin SL/TP estructural completo'
                if self.confirm(key,q,reason):
                    accepted=g.cancel(o,reason);self.lifecycle[str(o.ticket)]={'state':'INVALIDATED' if accepted else 'REJECTED','reason':reason};return accepted
                continue
            invalid=self.invalidate_reason(o,old,symbol,q)
            if invalid:
                self.lifecycle[str(o.ticket)]={'state':'INVALIDATING','reason':invalid}
                if self.confirm(key,q,invalid):return g.cancel(o,invalid)
                continue
            matches=[p for p in plans if self.matching(old,p)]
            filtered=getattr(self.planner,'pending_adaptation_rejections',{}).get(symbol,[])
            if not matches and any(self.matching(old,p) for p in filtered):
                self.confirmations.pop(key,None)
                self.lifecycle[str(o.ticket)]={'state':'VALID','reason':'Zona vigente; el filtro aprendido solo decide nuevas entradas'}
                continue
            if not matches:
                horizon=max(old.horizon_atr,old.atr,1e-9)
                ref=q.ask if old.side==1 else q.bid
                max_distance=float(symbol_strategy(self.cfg,symbol).get('pending_max_activation_source_atr',6.0))*horizon
                if abs(ref-old.entry)>max_distance:
                    reason='Zona fuera del alcance de activación configurado; esperar una alternativa más cercana'
                    # No retirar de inmediato una tesis nueva por un quote aislado.
                    # El usuario puede revocar manualmente; las invalidaciones
                    # verdaderas por SL/vela se procesan más arriba sin esta demora.
                    age=max(0.,now-float(meta.get('created',getattr(o,'time_setup',now))))
                    if age<180:
                        self.confirmations.pop(key,None)
                        self.lifecycle[str(o.ticket)]={'state':'VALID','reason':'Zona lejana en observación; falta persistencia para retirar'}
                        continue
                    self.lifecycle[str(o.ticket)]={'state':'WEAKENING','reason':reason}
                    if self.confirm(key,q,reason,max(120.0,self.cfg['pending']['orphan_cancel_seconds'])):return g.cancel(o,reason)
                    continue
                # Menor saldo/margen o un fallo al calcular dinero no invalidan
                # por sí mismos una zona ya colocada con SL/TP. La invalidación
                # por precio/vela se comprueba arriba, independientemente del cap.
                financial=[r for r in self.planner.pending_candidate_audit.get(symbol,[])
                    if r.get('key')==old.key and r.get('reject_code') in ('over_risk_budget','money_unavailable')]
                if financial:
                    self.confirmations.pop(key,None)
                    self.lifecycle[str(o.ticket)]={'state':'VALID','reason':'Zona vigente; presupuesto bloquea nuevas entradas'}
                    continue
                newest=max((f.bars[-1].time for name,f in self.planner.caches[symbol].frames.items()
                            if name in ('M15','H1')),default=0)
                if newest<=old.bar_time:
                    self.confirmations.pop(key,None)
                    self.lifecycle[str(o.ticket)]={'state':'VALID','reason':'Esperando nueva vela estructural para reevaluar la zona'}
                    continue
                # Absence during missing/stale data never fabricates invalidation.
                # Un fallo de fuentes/selector o una fluctuación de ranking NO
                # invalida la orden de MT5. Exigir dos cierres M15 nuevos y una
                # edad mínima: protege contra los bucles del 12–13 de octubre.
                m15=self.planner.caches[symbol].frames.get('M15')
                newer=sum(int(b.time)>int(old.bar_time) for b in m15.bars[-8:]) if m15 else 0
                min_age=max(900.0,float(self.cfg['pending'].get('orphan_min_age_seconds',900)))
                age=max(0.,now-float(meta.get('created',getattr(o,'time_setup',now))))
                if age<min_age or newer<max(2,int(self.cfg['pending'].get('orphan_min_m15_bars',2))):
                    self.confirmations.pop(key,None)
                    self.lifecycle[str(o.ticket)]={'state':'VALID','reason':'Orden conservada: falta evidencia estructural nueva para retirar la zona'}
                    continue
                reason='Tesis fuera del mapa válido durante revisión sostenida'
                self.lifecycle[str(o.ticket)]={'state':'WEAKENING','reason':reason}
                if self.confirm(key,q,reason,max(120.0,self.cfg['pending']['orphan_cancel_seconds'])):return g.cancel(o,reason)
                continue
            best=next((p for p in sorted(matches,key=lambda p:self.oracle_priority(symbol,p),reverse=True)
                       if g.pending_budget_status(p,snap,(int(o.ticket),),evaluation=evaluation)[0]),None)
            if best is None:
                self.confirmations.pop(key,None)
                self.lifecycle[str(o.ticket)]={'state':'VALID','reason':'Zona vigente; las nuevas alternativas no cumplen presupuesto/geometría para editar'}
                continue
            horizon=max(old.horizon_atr,best.horizon_atr,best.atr,1e-9)
            ref=q.ask if best.side==1 else q.bid
            near=abs(ref-old.entry)<=max(old.atr*self.cfg['pending']['freeze_near_activation_atr'],q.spread*2)
            material=max(abs(best.entry-old.entry),abs(best.sl-old.sl),abs(best.tp-old.tp))>=max(old.atr*self.cfg['pending']['edit_distance_atr'],q.spread*.5)
            improved=self.oracle_priority(symbol,best)-self.oracle_priority(symbol,old)>=self.cfg['pending']['replace_score_advantage']
            refreshed=(best.bar_time>old.bar_time and material and best.quality_score>=old.quality_score+1.0)
            age=now-float(meta.get('last_modify',getattr(o,'time_setup',now)))
            if material and (improved or refreshed) and not near and age>=self.cfg['pending']['sticky_min_seconds']:
                # A slot does not justify continually dragging a pending with price.
                reason='Mejor zona confirmada del mismo lado/tipo'
                held=self.pending_return_reason(meta,best,now)
                if held:
                    self.confirmations.pop(key,None)
                    self.lifecycle[str(o.ticket)]={'state':'VALID','reason':held};continue
                # Cada candidata confirma SUS niveles. Alternar dos zonas no
                # puede acumular ticks bajo el mismo texto genérico de mejora.
                signature=self.improvement_signature(reason,best)
                if self.confirm(key,q,signature):
                    accepted=g.modify_pending(o,best,reason);self.lifecycle[str(o.ticket)]={'state':'VALID' if accepted is None else 'IMPROVED' if accepted else 'REJECTED','reason':'Pendiente ya tiene esos mismos niveles; no se modifica' if accepted is None else reason};return bool(accepted)
            else:self.confirmations.pop(key,None)
            self.lifecycle[str(o.ticket)]={'state':'VALID','reason':'Zona estructural aún válida'}
        return False

    def pending_return_reason(self,meta,candidate,now):
        """Evitar volver por ruido a una zona que acabamos de abandonar."""
        seconds=float(self.cfg['pending'].get('switch_return_cooldown_seconds',90))
        advantage=float(self.cfg['pending'].get('switch_return_quality_advantage',4))
        horizon=max(candidate.horizon_atr,candidate.atr,1e-9)
        for zone in meta.get('recent_zones',[])[-6:]:
            if now-float(zone.get('abandoned_at',0))>=seconds:continue
            if abs(candidate.entry-float(zone.get('entry',0)))>max(horizon,float(zone.get('horizon_atr',0)))*.22:continue
            if candidate.bar_time>int(zone.get('bar_time',0)) and candidate.quality_score>=float(zone.get('quality_score',0))+advantage:continue
            return 'Zona vigente; alternativa recién abandonada sin nueva evidencia suficiente para volver a mover la entrada'
        return ''

    @staticmethod
    def improvement_signature(reason,plan):
        # Separar zonas y cambios materiales sin reiniciar una confirmación por
        # cada céntimo de ajuste del feed. La invalidación y el Gateway sí usan
        # siempre los niveles exactos y actuales.
        bucket=max(plan.horizon_atr,plan.atr,1e-9)*.10
        levels=tuple(round(v/bucket) for v in (plan.entry,plan.sl,plan.tp))
        return (reason,plan.key,levels)

    def analysis_evaluation(self,symbol,snap):
        """Caché de valoración de este ciclo y libro, jamás usada en order_send."""
        seed=self._analysis_evaluations.get(symbol)
        marker=self.book_marker(snap)
        scope=self.valuation_scope(symbol,snap);now=self.g.clock()
        reusable=bool(seed and seed[1].get('_valuation_scope')==scope and
            0<=now-seed[1].get('_valued_at',-float('inf'))<=.5)
        if reusable and seed[0]==marker:return seed[1]
        evaluation={'_valuation_scope':scope,'_valued_at':now}
        if reusable:
            # El libro puede cambiar tras confirmar una orden; el dinero de una
            # misma geometría/cotización no. Las reservas se reconstruyen siempre
            # con el nuevo libro y diario, sin copiar ningún resultado agregado.
            methods={'symbol_info','symbol_info_tick','order_calc_profit','order_calc_margin'}
            evaluation.update({k:v for k,v in seed[1].items()
                if isinstance(k,tuple) and k and k[0] in methods})
            # No renovar la edad de los cálculos copiados al cambiar el libro.
            evaluation['_valued_at']=seed[1]['_valued_at']
        self._analysis_evaluations[symbol]=(marker,evaluation)
        return evaluation

    def valuation_scope(self,symbol,snap):
        q=self.quotes.get(symbol)
        return (self.cycle,symbol,
            (q.sequence,q.bid,q.ask) if q else None,str(snap.account.currency),
            repr(self.cfg['risk']),repr(self.cfg['sizing']),float(self.cfg['lot']))

    def book_marker(self,snap):
        return (self.cycle,
            tuple((p.symbol,p.ticket,p.type,p.magic,p.volume,p.price_open,p.sl,p.tp,getattr(p,'swap',0)) for p in snap.positions),
            tuple((o.symbol,o.ticket,o.type,o.magic,o.volume_current,o.price_open,o.sl,o.tp,getattr(o,'price_stoplimit',0)) for o in snap.orders),
            float(snap.account.balance),float(snap.account.equity),float(snap.account.margin),float(snap.account.margin_free),str(snap.account.currency),
            repr(self.g.journal.data['intents']),repr(self.cfg['risk']),repr(self.cfg['sizing']),float(self.cfg['lot']),
            tuple((s,(q.sequence,q.bid,q.ask)) for s,q in sorted(self.quotes.items())))

    def oracle_priority(self,symbol,plan):
        """Ranking estilo mapa manual: estructura primero, activación después.

        No es probabilidad ni salta filtros. Solo ordena planes que ya sobrevivieron
        Planner/Gateway local. H1/H4/D1 definen sesgo; M15 ayuda a elegir entre
        retroceso LIMIT y ruptura STOP para no perseguir una vela ya extendida.
        """
        base=float(pending_priority(plan))
        if not bool(self.cfg.get('final_architecture',{}).get('human_scenario_ranker',True)):
            return base
        frames=self.planner.caches[symbol].frames
        num=den=0.0
        for tf,w in (('M15',.12),('H1',.30),('H4',.34),('D1',.24)):
            f=frames.get(tf)
            if f is None:continue
            num+=max(-1.0,min(1.0,float(f.trend)))*w;den+=w
        bias=num/max(den,1e-9) if den else 0.0
        align=int(plan.side)*bias
        activation=float(getattr(plan,'activation_score',0.0) or 0.0)
        rr=float(getattr(plan,'rr',0.0) or 0.0)
        bonus=max(-5.0,min(5.0,align*5.0))
        bonus+=max(-2.5,min(3.0,(activation-55.0)/15.0))
        if 1.7<=rr<=4.0:bonus+=1.5
        elif rr>4.5:bonus-=min(3.0,(rr-4.5)*1.2)
        m15=frames.get('M15')
        m15_align=(int(plan.side)*float(m15.trend)) if m15 is not None else 0.0
        if str(plan.kind).upper()=='STOP':
            # STOP es la cobertura para no perder ruptura futura: premiar cuando M15
            # ya prepara la dirección, sin exigir que H4 haya girado antes del break.
            bonus+=2.0 if m15_align>.15 else -1.0 if m15_align<-.55 else 0.0
        else:
            # LIMIT funciona mejor como pullback/retest a favor del contexto mayor.
            bonus+=2.0 if align>.10 else -2.0 if align<-.55 else 0.0
        return base+bonus

    def allocate(self,symbol,plans,snap=None):
        g=self.g;snap=snap or g.snapshot();own=[o for o in snap.orders if o.symbol==symbol and g.owned_order(o)]
        self.allocation_checks[symbol]=[]
        if bool(self.cfg.get('execution',{}).get('suspend_new_map_while_position_open',True)):
            active=[p for p in snap.positions if p.symbol==symbol and g.owned(p)]
            if active:
                self.allocation_reasons[symbol]=['Posición propia activa; SNAPMAP retiró alternativas y espera cierre antes de volver a armar pendientes']
                return []
        maximum=max(0,int(self.cfg['pending']['max_own_map_orders'])-len(own))
        evaluation=self.analysis_evaluation(symbol,snap)
        ledger=g.reservation_ledger(snap,evaluation=evaluation);budget=ledger['available_usd']
        self.allocation_reasons[symbol]=[]
        if maximum==0:self.allocation_reasons[symbol].append('Mapa de pendientes propias completo')
        if budget<=0:self.allocation_reasons[symbol].append(g.reservation_reason(ledger))
        if maximum<=0 or budget<=0:return []
        existing=[];represented=[]
        for o in snap.orders:
            if o.symbol!=symbol or int(o.type) not in (2,3,4,5):continue
            p=order_plan(o,(g.journal.data['orders'].get(str(o.ticket)) or {}).get('plan'));existing.append(p)
            if g.owned_order(o):represented.append(self.planner.pending_slot(p.side,p.kind,p))
        options=[];skipped=set()
        for p in plans:
            quality=self.evaluate_entry_quality(p)
            # Una dirección ya ocupada no necesita repetir valoraciones de todas
            # sus alternativas al completar el otro lado en la misma vuelta.
            slot=self.planner.pending_slot(p.side,p.kind,p)
            side_orders=[o for o in snap.orders if o.symbol==symbol and int(o.type) in (2,3,4,5) and (1 if int(o.type)%2==0 else -1)==p.side]
            represented_slot=slot in represented
            full_side=len(side_orders)>=int(self.cfg['pending']['max_same_side_orders'])
            if represented_slot or full_side:
                reason=('Una pendiente propia ya cubre esta zona' if represented_slot else
                    ('BUY' if p.side==1 else 'SELL')+': lado ocupado por '+', '.join(('Akira ' if g.owned_order(o) else 'manual/externa ')+'#'+str(o.ticket) for o in side_orders)+
                    '; límite '+str(self.cfg['pending']['max_same_side_orders'])+' pendiente(s) por lado')
                if (p.side,reason) not in skipped:
                    self.allocation_reasons[symbol].append(reason)
                    self.allocation_checks[symbol].append({'key':p.key,'kind':p.kind,'side':p.side,'allowed':False,'detail':reason,'risk_usd':None})
                    skipped.add((p.side,reason))
                continue
            try:
                # All broker geometry/risk checks apply, even before selection.
                allowed,detail,risk=g.pending_budget_status(p,snap,evaluation=evaluation)
                check={'key':p.key,'kind':p.kind,'side':p.side,'allowed':allowed,'detail':detail,'risk_usd':risk or None}
                if not allowed:
                    try:check['funding']=g.funding_diagnostic(p,snap,evaluation=evaluation)
                    except Blocked as exc:check['funding_error']=str(exc)
                if not quality['allowed']:
                    check['quality_reason']=quality['reason']
                    if allowed:allowed=False;detail=quality['reason'];check.update(allowed=False,detail=detail)
                self.allocation_checks[symbol].append(check)
                if not allowed:
                    self.allocation_reasons[symbol].append(detail)
                    self.planner.pending_filter_reasons.setdefault(symbol,{})[p.key]=detail;continue
                options.append({'plan':p,'risk':risk,'value':self.oracle_priority(symbol,p),'slot':slot})
            except Blocked as e:self.allocation_reasons[symbol].append(str(e))
        return select_portfolio(options,budget,maximum,int(self.cfg['pending']['max_same_side_orders']),
            existing,represented,spacing=self.cfg['pending']['multi_zone_min_spacing_atr'],
            preserve_opposite=self.cfg['pending']['preserve_opposite_map'],
            opposite_quality=self.cfg['pending']['opposite_map_min_quality'])

    def scan_plans(self,symbol,q,force=False,snapshot=None):
        """Reutiliza indicadores y zonas; cada envío vuelve a validar quote y libro."""
        now=self.g.clock();cache=self.planner.caches[symbol];before=self.map_cache.get(symbol)
        fusion=(self.planner.research_context.get('fusion') or {}).get(symbol,{})
        source_rows=self.planner.research_context.get('sources') or {}
        source_revision=tuple(sorted((str(name),int(float(row.get('updated',0) or 0))) for name,row in source_rows.items()
                                     if isinstance(row,dict) and row.get('updated')))
        marker=(tuple((name,f.bars[-1].time) for name,f in cache.frames.items()),
                round(float(fusion.get('bias',0)),4),round(float(fusion.get('confidence',0)),4),source_revision,
                round(float(self.planner.broker_book.get(symbol,{}).get('imbalance',0)),3))
        atr=cache.frames['M1'].atr if 'M1' in cache.frames else 0
        refresh=max(.03,float(self.cfg.get('execution',{}).get('rapid_parameter_map_refresh_seconds',.08)))
        if (not force and before and marker==before['marker'] and now-before['at']<refresh and
                abs(q.bid-before['bid'])<max(atr*.06,q.spread*.4) and abs(q.spread-before['spread'])<max(q.spread*.1,1e-9)):
            return before['plans']
        evaluation=self.analysis_evaluation(symbol,snapshot) if snapshot is not None else {}
        if snapshot is not None:evaluation['snapshot']=snapshot
        strict=self.planner.proposed_pending_plans(symbol,cache.setups,q,all_candidates=True,presence=False,evaluation=evaluation,financial_gate=False)
        if evaluation.get('snapshot') is not None:
            self._analysis_evaluations[symbol]=(self.book_marker(evaluation['snapshot']),evaluation)
        strict_audit=[dict(x) for x in self.planner.pending_candidate_audit.get(symbol,[])]
        plans=list(strict);fallback_audit=[]
        # V12.7 SNAPMAP: el pase rápido compite SIEMPRE, no solo cuando falta un
        # lado. Antes una candidata A/A+ podía existir en papel pero quedar bloqueada
        # por riesgo/margen y, por estar 'representado' ese lado, Akira jamás probaba
        # su SELL STOP/BUY STOP o LIMIT alternativo. Ahora strict + presence forman
        # un único pool y el Gateway intenta la mejor alternativa realmente ejecutable
        # en la MISMA vuelta. Internet/LLM no bloquean este mapa técnico.
        if bool(self.cfg.get('execution',{}).get('always_keep_pending_map',True)):
            fallback=self.planner.proposed_pending_plans(symbol,cache.setups,q,all_candidates=True,presence=True,evaluation=evaluation,financial_gate=False)
            fallback_audit=[dict(x) for x in self.planner.pending_candidate_audit.get(symbol,[])]
            seen={p.key for p in plans}
            represented={int(p.side) for p in strict}
            missing={1,-1}-represented
            all_alt=bool(self.cfg.get('execution',{}).get('presence_all_alternatives',True))
            for p in fallback:
                if p.key in seen: continue
                if all_alt or int(p.side) in missing:
                    plans.append(p);seen.add(p.key)
        # Conservar también un fill LIMIT financiable que el planner ya valida
        # dentro de la misma zona. La valoración técnica original no desaparece
        # cuando no existe ese fill; el Gateway decide qué se puede enviar.
        funded_audit=[]
        if any(r.get('financially_blocked') and r.get('kind')=='LIMIT' for r in strict_audit+fallback_audit):
            funded=self.planner.proposed_pending_plans(symbol,cache.setups,q,all_candidates=True,
                        presence=True,evaluation=evaluation,financial_gate=True)
            funded_audit=[dict(x) for x in self.planner.pending_candidate_audit.get(symbol,[])]
            by_key={p.key:p for p in plans}
            for p in funded:by_key[p.key]=p
            plans=list(by_key.values())
        plans=sorted(plans,key=lambda p:self.oracle_priority(symbol,p),reverse=True)
        # Conservar auditoría de ambos pases. Antes el pase PRESENCE borraba el
        # diagnóstico estricto y la interfaz parecía no tener un escenario opuesto.
        merged={}
        for row in strict_audit+fallback_audit+funded_audit:
            key=str(row.get('key',''))
            if not key:continue
            before_row=merged.get(key)
            rank=lambda r: (2 if r.get('status') in ('QUALIFIED','SOFT_FALLBACK') else 1 if r.get('status')=='DETECTED' else 0,
                            not bool(r.get('financially_blocked')),
                            float(r.get('quality_score') or 0),float(r.get('activation_score') or 0))
            if before_row is None or rank(row)>rank(before_row):merged[key]=row
        if merged:self.planner.pending_candidate_audit[symbol]=list(merged.values())
        self.map_cache[symbol]={'marker':marker,'at':now,'bid':q.bid,'spread':q.spread,'plans':plans}
        return plans

    def replace_for_better_portfolio(self,symbol,plans,q,snap=None):
        """A full map can yield capacity to a materially better new scenario."""
        g=self.g;now=g.clock();snap=snap or g.snapshot()
        # Las estrellas/rankings son heurísticos, NO una prueba suficiente para
        # cancelar una orden válida. Opt-in explícito; por defecto conservamos.
        if not bool(self.cfg['pending'].get('auto_replace_valid_pending',False)):
            return False
        own=[o for o in snap.orders if o.symbol==symbol and g.owned_order(o)]
        if not own or not plans:return False
        oldrows=[(o,order_plan(o,(g.journal.data['orders'].get(str(o.ticket)) or {}).get('plan'))) for o in own]
        unmatched=[p for p in plans if not any(self.matching(old,p) or pending_overlap(old,p) for _,old in oldrows)]
        if not unmatched:return False
        worst_o,worst=min(oldrows,key=lambda x:self.oracle_priority(symbol,x[1]))
        evaluation={}
        best=next((p for p in sorted(unmatched,key=lambda p:self.oracle_priority(symbol,p),reverse=True)
                   if g.pending_budget_status(p,snap,(int(worst_o.ticket),),evaluation=evaluation)[0]),None)
        if best is None:return False
        advantage=self.oracle_priority(symbol,best)-self.oracle_priority(symbol,worst)
        if advantage<max(15.0,float(self.cfg['pending'].get('portfolio_min_quality_advantage',15)),
                         float(self.cfg['pending']['portfolio_replace_advantage'])):return False
        min_age=max(900.0,float(self.cfg['pending'].get('portfolio_min_age_seconds',900)))
        if now-float(getattr(worst_o,'time_setup',now))<min_age:return False
        # Un mismo candidato repetido en cada tick no cuenta como evidencia
        # nueva. La tesis superior debe venir de una vela M15 cerrada posterior.
        m15=self.planner.caches[symbol].frames.get('M15')
        if not m15 or int(m15.bars[-1].time)<=int(worst.bar_time) or int(best.bar_time)<=int(worst.bar_time):return False
        if abs((q.ask if worst.side==1 else q.bid)-worst.entry)<=max(worst.atr*self.cfg['pending']['freeze_near_activation_atr'],q.spread*2):return False
        reason='Sustituir tesis inferior por escenario de mayor calidad confirmada'
        if self.pending_return_reason(g.journal.data['orders'].get(str(worst_o.ticket),{}),best,now):return False
        signature=self.improvement_signature(reason,best)
        if self.confirm((symbol,int(worst_o.ticket),'portfolio'),q,signature,seconds=max(30.0,self.cfg['pending']['replace_confirm_seconds'])):
            return g.cancel(worst_o,reason)
        return False

    def execute_pending_map(self,symbol,plans,q):
        """Una sola vía para automático y botón: revisar, renovar y completar.

        Cada intento revalida el libro real. Solo un rechazo definitivo permite
        pasar a otra candidata; una respuesta incierta detiene el símbolo.
        """
        g=self.g;sent=changed=attempts=0;last_error='';attempted=set()
        limit=int(self.cfg['execution'].get('pending_attempts_per_cycle',8))
        snap=g.snapshot()
        g.permissions(snap)
        before_positions={int(p.ticket) for p in snap.positions if p.symbol==symbol and g.owned(p)}
        if symbol not in g.journal.data['intents']:
            if self.lifecycle_action(symbol,plans,q,snap):
                changed+=1;snap=g.snapshot();g.reconcile(snap)
        while attempts<limit and symbol not in g.journal.data['intents']:
            if changed and any(p.symbol==symbol and g.owned(p) for p in snap.positions):
                last_error='Pendiente activada durante la revisión; gestionar posición antes de renovar el mapa';break
            if g.clock()<g.cooldowns.get(symbol,0):
                last_error=g.last_rejection.get(symbol,'Bróker en pausa de reintento');break
            pool=[p for p in plans if (p.key,p.entry,p.sl,p.tp) not in attempted]
            chosen=self.allocate(symbol,pool,snap)
            if not chosen:
                if not changed and self.replace_for_better_portfolio(symbol,pool,q,snap):
                    changed+=1;snap=g.snapshot();g.reconcile(snap);continue
                break
            plan=chosen[0]['plan'];attempted.add((plan.key,plan.entry,plan.sl,plan.tp));attempts+=1
            try:
                # La selección es local; el envío siempre usa una cotización nueva.
                fresh_q=g.quote(symbol)
                accepted=g.send_immediate_plan(self.with_learning_features(plan,fresh_q))
                if accepted:
                    self.first_requests.setdefault(symbol,{'cycle':self.cycle,'time':g.clock()})
                    sent+=1;snap=g.snapshot();g.reconcile(snap)
                    if any(p.symbol==symbol and g.owned(p) for p in snap.positions):
                        last_error='Orden activada; gestionar posición antes de completar alternativas';break
                    if not self.cfg['execution'].get('fill_all_available_directions_same_cycle',True):break
                else:
                    last_error=g.last_rejection.get(symbol,'Solicitud sin confirmación final MT5')
                    snap=g.snapshot()
            except Blocked as exc:last_error=str(exc);snap=g.snapshot()
        finish=g.snapshot();levels=self.confirmed_levels(symbol,finish)
        activated=any(p.symbol==symbol and g.owned(p) and int(p.ticket) not in before_positions for p in finish.positions)
        unresolved=symbol in g.journal.data['intents']
        if unresolved:
            state='RECONCILIANDO';detail='Solicitud enviada; falta evidencia final MT5 y no se duplica'
        elif activated:
            state='POSICIÓN ACTIVADA';detail='Pendiente activada durante la revisión; gestionar SL/TP antes de renovar el mapa'
        elif sent or changed:
            state='PENDIENTES CONFIRMADAS' if levels else 'MAPA ACTUALIZADO'
            detail=f'{sent} pendiente(s) nuevas · {changed} edición(es)/retiro(s) · {len(levels)} pendiente(s) MT5'
            if last_error:detail+=' · '+last_error
        elif levels:
            state='MAPA VIGENTE';detail=f'{len(levels)} pendiente(s) confirmadas; niveles revisados'
            if last_error:detail+=' · '+last_error
        else:
            reasons=self.allocation_reasons.get(symbol,[]) or list(self.planner.pending_filter_reasons.get(symbol,{}).values())
            detail=last_error or (reasons[0] if reasons else 'No hay una nueva zona estructural válida')
            financial=[r for r in self.planner.pending_candidate_audit.get(symbol,[])
                       if r.get('reject_code')=='over_risk_budget' and r.get('risk_usd')]
            checks=self.allocation_checks.get(symbol,[])
            funding=[r['funding'] for r in checks if r.get('funding')]
            all_unfunded=bool(checks and len(funding)==len(checks) and all(not r['minimum_fits'] for r in funding))
            ledger=g.reservation_ledger(finish);portfolio_blocked=ledger['available_usd']<=0
            state='BLOQUEO DE RIESGO' if portfolio_blocked or (not plans and financial) or all_unfunded else 'ESPERANDO ENVÍO' if plans else 'ESCENARIOS EN REVISIÓN'
            if portfolio_blocked:detail=g.reservation_reason(ledger)
            elif state=='BLOQUEO DE RIESGO':
                cheapest=min((r['minimum_risk_usd'] for r in funding),default=min((float(r['risk_usd']) for r in financial),default=0.0))
                available=min((r['available_usd'] for r in funding),default=g.trade_cap(finish))
                detail=f"{len(plans)} candidatas técnicas; menor riesgo estimado {cheapest:.2f} USD; presupuesto disponible por orden {available:.2f} USD. Ninguna cabe con su SL y lote permitido"
        row={'accepted':bool(sent or changed),'sent':sent,'changed':changed,'attempts':attempts,
             'levels':levels,'unconfirmed':unresolved,'state':state,'detail':detail}
        self.pending_cycles[symbol]={k:v for k,v in row.items() if k!='levels'}
        self.status[symbol]={'state':state,'detail':detail}
        return row

    def directional_scenarios(self,symbol,snap=None,evaluation=None,ledger=None):
        """Muestra el mapa instantáneo por cuadrante: BUY/SELL × LIMIT/STOP.

        Engine sigue ejecutando como máximo una pendiente por dirección. La tabla
        puede enseñar hasta cuatro parámetros para que sea evidente qué está
        preparando Akira para retroceso y ruptura, incluso si Gateway bloquea uno.
        """
        snap=snap or self.g.snapshot();out=[]
        try:
            q=self.g.quote(symbol,evaluation)
            market_fresh=True
        except Blocked:
            # SOLO para visualizar niveles históricos, jamás para order_send.
            try:q=self.g.reserve_quote(symbol,evaluation)
            except Blocked:return []
            market_fresh=False
        frames=self.planner.caches[symbol].frames;evaluation={} if evaluation is None else evaluation
        ledger=ledger or self.g.reservation_ledger(snap,evaluation=evaluation)
        own=[]
        for o in snap.orders:
            if o.symbol!=symbol or not self.g.owned_order(o):continue
            p=order_plan(o,(self.g.journal.data['orders'].get(str(o.ticket)) or {}).get('plan'))
            own.append((o,p))
        candidates=list(self.candidates.get(symbol,[]))
        audit=list(self.planner.pending_candidate_audit.get(symbol,[]))
        used=set()

        def append_live(side,kind):
            rows=[x for x in own if int(x[1].side)==side and str(x[1].kind)==kind]
            if not rows:return False
            o,p=max(rows,key=lambda x:pending_priority(x[1]))
            financial=next((r for r in ledger['rows'] if r.get('kind')=='pending' and r.get('ticket')==int(o.ticket)),{})
            out.append({**p.to_dict(),'ticket':int(o.ticket),'confirmed':True,'sendable':True,
                        'volume':float(o.volume_current),'risk_usd':financial.get('risk_usd'),
                        'risk_cap_usd':self.g.trade_cap(snap),
                        'scenario_state':'MT5 CONFIRMADA','block_reason':''});used.add((side,kind));return True

        def append_candidate(side,kind):
            rows=[p for p in candidates if int(p.side)==side and str(p.kind)==kind]
            if not rows:return False
            checked=[]
            for p in sorted(rows,key=lambda p:self.oracle_priority(symbol,p),reverse=True):
                allowed,detail,risk=self.g.pending_budget_status(p,snap,evaluation=evaluation) if market_fresh else (False,'No se permite enviar con precio desactualizado',0)
                quality=self.evaluate_entry_quality(p)
                if not quality['allowed'] and allowed:allowed=False;detail=quality['reason']
                checked.append((p,allowed,detail,risk))
                if allowed:break
            p,allowed,detail,risk=next((r for r in checked if r[1]),checked[0])
            if allowed and (self.paused or self.cfg['mode']!='trade'):
                allowed=False;detail='Motor en pausa/observación; parámetros disponibles sin envío'
            try:funding=self.g.funding_diagnostic(p,snap,evaluation=evaluation) if market_fresh else {}
            except Blocked:funding={}
            out.append({**p.to_dict(),'confirmed':False,'sendable':bool(market_fresh and allowed),
                        'risk_usd':risk or funding.get('minimum_risk_usd'),'risk_cap_usd':self.g.trade_cap(snap),'funding':funding,
                        'scenario_state':'LISTA PARA MT5' if allowed else 'ANÁLISIS · BLOQUEADA' if market_fresh else 'PAUSA · ESPERAR TICK NUEVO',
                        'block_reason':'' if allowed else detail});used.add((side,kind));return True

        def append_audit(side,kind):
            side_name='BUY' if side==1 else 'SELL'
            rows=[r for r in audit if str(r.get('side','')).upper()==side_name and str(r.get('kind','')).upper()==kind
                  and float(r.get('entry') or 0)>0 and float(r.get('sl') or 0)>0 and float(r.get('tp') or 0)>0]
            if not rows:return False
            def score(r):
                tf={'H4':4,'H1':3,'M30':2,'M15':1,'M5':0}.get(str(r.get('timeframe','')),0)
                q=float(r.get('quality_score') or 0);a=float(r.get('activation_score') or 0)
                rr=float(r.get('rr') or 0);rr_pen=max(0.0,rr-4.0)*8
                snap_bonus=8.0 if str(r.get('key','')).startswith('SWING:SNAP:') else 0.0
                return snap_bonus+tf*6+q*.55+a*.25-rr_pen
            r=max(rows,key=score)
            quality=float(r.get('quality_score') or 0);activation=float(r.get('activation_score') or 0)
            out.append({'key':r.get('key',''),'side':side,'lane':'PENDING','kind':kind,
                        'entry':float(r['entry']),'sl':float(r['sl']),'tp':float(r['tp']),
                        'quality_score':r.get('quality_score'),'activation_score':r.get('activation_score'),
                        'score':float(r.get('quality_score') or 0),'confirmed':False,'sendable':False,
                        'scenario_state':'ANÁLISIS · NO ENVIADA','block_reason':str(r.get('reason') or r.get('reject_code') or 'No pasó filtros'),
                        'risk_usd':r.get('risk_usd'),'required_risk_usd':r.get('required_risk_usd'),'risk_cap_usd':r.get('risk_cap_usd'),
                        'timeframe':r.get('timeframe',''),'rr':r.get('rr')});used.add((side,kind));return True

        # Orden visual: venta de retroceso/ruptura y compra de retroceso/ruptura.
        # En una tendencia bajista el usuario ve de inmediato SELL LIMIT + SELL STOP;
        # en una alcista, BUY LIMIT + BUY STOP, sin ocultar el escenario opuesto.
        for side,kind in ((-1,'LIMIT'),(-1,'STOP'),(1,'LIMIT'),(1,'STOP')):
            append_live(side,kind) or append_candidate(side,kind) or append_audit(side,kind)

        # Si algún cuadrante no llegó ni al audit, construir parámetros FLASHMAP
        # de análisis. Siguen siendo visibles, NO saltan Planner/Gateway.
        missing=[x for x in ((-1,'LIMIT'),(-1,'STOP'),(1,'LIMIT'),(1,'STOP')) if x not in used]
        if missing:
            try:
                cache=self.planner.caches[symbol]
                fallback=build_snap_analyst_pendings(cache.frames,symbol_strategy(self.cfg,symbol),__import__('collections').Counter())
            except Exception:
                fallback=[]
            for side,kind in missing:
                rows=[x for x in fallback if int(x.side)==side and str(x.kind)==kind]
                if not rows:continue
                x=max(rows,key=lambda z:float(getattr(z,'score',0)))
                entry=float(x.level);sl=float(x.stop);tp=float(x.target)
                rr=side*(tp-entry)/max(side*(entry-sl),1e-9)
                source_tf=str(getattr(x,'timeframe','M15') or 'M15');src=frames.get(source_tf) or frames.get('M15') or frames.get('M1')
                atr=float(getattr(src,'atr',1.0) or 1.0);ref=q.ask if side==1 else q.bid
                activation=max(5.0,min(95.0,92.0-abs(entry-ref)/max(atr,1e-9)*28.0))
                out.append({'key':x.key,'side':side,'lane':'PENDING','kind':kind,'entry':entry,'sl':sl,'tp':tp,
                            'quality_score':None,'activation_score':activation,'score':float(x.score),
                            'confirmed':False,'sendable':False,'scenario_state':'TESIS FLASH · VALIDANDO',
                            'block_reason':'Parámetros instantáneos de estructura observada; Planner, riesgo, margen y Gateway aún deben aprobarlos',
                            'risk_usd':None,'required_risk_usd':None,'risk_cap_usd':float(self.g.trade_cap(snap)),
                            'timeframe':getattr(x,'timeframe','M15'),'rr':rr,'reason':x.reason})
        for row in out:
            row['assessment']=assess_plan(row,frames,self.g.clock(),{'spread':q.spread})
        return out[:4]

    def heartbeat(self,view=None):
        # El dashboard se actualiza con cada snapshot; escribir cuatro mensajes
        # por segundo en disco no acelera las operaciones y congestiona la UI.
        now=self.g.clock();every=max(10.0,float(self.cfg.get('desktop',{}).get('terminal_heartbeat_seconds',.5)))
        if now-self._last_heartbeat<every:return
        self._last_heartbeat=now
        view=view or self.view();ledger=view['portfolio_risk']
        for symbol in self.planner.caches:
            if not self.market_state(symbol)['open']:continue
            plans=self.candidates.get(symbol,[]);buy=sum(int(p.side)==1 for p in plans);sell=sum(int(p.side)==-1 for p in plans)
            live=sum(o['symbol']==symbol and o['owned'] for o in view['orders'])
            status=self.status.get(symbol,{})
            # Separar PARAMETROS (tesis) y ENVIABLES (aprobadas): no etiquetar
            # todo como "mapa 0" si ya se calcularon cuatro escenarios.
            scenarios=view['symbols'][symbol]['scenario_book'];proposals=len(scenarios)
            enviable=sum(bool(r.get('sendable')) and not r.get('confirmed') for r in scenarios)
            detail=status.get('detail','')[:500]
            runner=view['symbols'][symbol].get('runner',{})
            self.log.event(symbol,f"CICLO {self.cycle} · {proposals} escenarios con parámetros · técnicas BUY {buy} / SELL {sell} · nuevas enviables {enviable} · MT5 confirmadas {live} · {status.get('state','')} · {detail} · RUNNER {runner.get('state','ESPERANDO')}: {str(runner.get('detail',''))[:240]}",build=BUILD_ID,portfolio_risk=ledger,runner=runner)
        # La función Reporter.dump existía pero nunca se llamaba: persistimos
        # el estado operativo de ambos símbolos para soporte y auditoría.
        # Reporter.status registra eventos de diagnóstico, pero el estado del
        # ciclo está en Engine.status; sincronizar antes de persistir.
        for symbol,state in self.status.items():
            self.log.status[symbol]=dict(state)
        try:self.log.dump()
        except OSError as exc:self.log.event('DIARIO','No pude guardar estado.json: '+str(exc)[:160])

    def research_snapshot(self):
        out={}
        snap=self.g.snapshot()
        paper_costs={}
        for s,c in self.planner.caches.items():
            q=self.quotes.get(s)
            frames={k:self.frame_summary(f) for k,f in c.frames.items()}
            book=[{**order_plan(o,(self.g.journal.data['orders'].get(str(o.ticket)) or {}).get('plan')).to_dict(),'ticket':int(o.ticket),'confirmed':True,'volume':float(o.volume_current)} for o in snap.orders if o.symbol==s and self.g.owned_order(o)]
            book.extend(p.to_dict() for p in self.candidates.get(s,[])[:8])
            out[s]={'bid':q.bid if q else None,'ask':q.ask if q else None,'spread':q.spread if q else None,'quote_time':q.time if q else None,
                    'frames':frames,'broker_book':self.planner.broker_book.get(s,{}),'pending_book':book,'scenario_book':book,
                    'bars':{tf:[b.to_dict() for b in c.frames[tf].bars[-320 if tf in ('M5','M15') else 180:]] for tf in ('M5','M15','H1','H4','D1') if tf in c.frames}}
            baseline=getattr(self.planner,'pending_adaptation_baseline',{}).get(s,[])
            out[s]['adaptation_candidates']=[p.to_dict() for p in baseline]
            if q:
                from runner import baseline_runner_candidates
                runner_candidates,_=baseline_runner_candidates(s,c.frames,q,self.cfg,{})
                out[s]['adaptation_candidates'].extend(p.to_dict() for p,_ in runner_candidates)
            if q:
                try:
                    lot=float(self.cfg['lot']);unit=abs(self.g.profit(s,1,lot,q.ask,q.ask+1))
                    paper_costs[s]={'profit_per_price_unit':unit,'round_turn_fee':float(self.cfg['risk']['round_turn_commission_per_lot'])*lot,
                        'lot':lot,'source':'order_calc_profit MT5; comisión estimada de ajustes'}
                except Blocked:pass
        return {'symbols':out,'as_of_utc':self.g.clock(),'markets':{s:self.market_state(s) for s in out},
                'pending_performance':{s:self.learner.metrics(s) for s in out},
                'confirmed_learning_outcomes':list(self.learner.records.values()),'learning_account':list(self.g.identity or ()),
                'confirmed_strategy_outcomes':copy.deepcopy(self._confirmed_outcomes[-300:]),'paper_costs':paper_costs,
                'selection_configuration':self.verification_configuration(),'research_sources':copy.deepcopy(self.planner.research_context.get('sources',{})),
                'build':BUILD_ID}

    @staticmethod
    def frame_summary(f):
        return {**f.extra,'atr':f.atr,'ema9':f.fast,'ema21':f.slow,'trend':f.trend,'rsi':f.rsi,
            'macd':f.macd_hist,'regime':f.regime,'bars':len(f.bars),'last_bar':f.bars[-1].time,
            'band_low':f.band_low,'band_high':f.band_high,'volume_ratio':f.volume_ratio}

    def with_learning_features(self,plan,q):
        frames=self.planner.caches[plan.symbol].frames
        values=entry_features(plan.side,plan,{},frames,None,q.spread)
        return replace(plan,learning_features=tuple(values),learning_feature_version=FEATURE_VERSION)

    def read_context(self):
        if not self.context:return {}
        try:
            state=self.context.read()
            if not isinstance(state,dict):raise ValueError('Estado de contexto sin estructura válida')
            from strategy_adaptation import execution_identity
            state['execution_identity']=execution_identity(self.g.identity,BUILD_ID,self.verification_configuration())
            return state
        except Exception as exc:
            detail='Contexto auxiliar no disponible: '+type(exc).__name__+': '+str(exc)[:250]
            self.log.report('IA','CONTEXTO',detail)
            return {'fusion':{},'sources':{'context_worker':{'fresh':False,'age_seconds':None,'inflight':False,'error':detail}}}

    def step(self):
        started=time.perf_counter();g=self.g;now=g.clock();self.cycle+=1
        if not self.initialized:self.warmup(fast=True)
        snap=g.snapshot();g.reconcile(snap)
        if snap.orders or snap.positions or g.journal.data['intents']:snap=g.snapshot()
        # Confirm a disappearing own position BEFORE another entry can reuse
        # its thesis. Still one targeted history lookup; no full-history wait.
        try:g.closure_monitor.poll()
        except Exception as exc:self.log.report('MT5','HISTORIAL DE CIERRE','No se pudo confirmar el cierre: '+type(exc).__name__)
        from trade_quality_gate import owned_outcomes
        self._confirmed_outcomes=owned_outcomes(g)
        snap=self.enforce_capital_protection(snap)
        snap=self.review_loss_pendings(snap)
        # El primer envío no espera una consulta de 90 días de deals.
        self.planner.research_context=self.read_context()
        if not self.paused and not g.runtime_execution_block and getattr(g,'network_available',True) is not False:self.positions.step(snap)
        symbols=list(self.planner.caches)
        # Rotate first priority so one symbol cannot consume every available turn.
        shift=self.cycle%max(1,len(symbols));symbols=symbols[shift:]+symbols[:shift]
        for symbol in symbols:
            try:
                market=self.market_state(symbol)
                if not market['open']:
                    self.status[symbol]={'state':'MERCADO CERRADO','detail':market['state']+'. Próxima apertura estimada: '+market['next_open']}
                    self.runner_views[symbol]={'state':'MERCADO CERRADO','detail':'Seguimiento operativo en pausa; se conserva el riesgo de tickets existentes.'}
                    self.quotes.pop(symbol,None)
                    continue
                if self.status.get(symbol,{}).get('state')=='MERCADO CERRADO':
                    cache=self.planner.caches[symbol];cache.prime_critical(now);cache.prime_fast_structural(now);cache.prime_deep_structural(now)
                cache=self.planner.caches[symbol];cache.advance(now)
                ready,detail=self.evidence_ready(symbol,now)
                q=g.quote(symbol);self.quotes[symbol]=q;self.planner.tapes[symbol].update(q,cache.frames,now)
                self.update_book(symbol)
                self.planner.flow[symbol]={'live':self.planner.tapes[symbol].last_metrics}
                if not ready:self.status[symbol]={'state':'CARGANDO','detail':detail};continue
                plans=self.scan_plans(symbol,q,snapshot=snap)
                self.candidates[symbol]=plans;self.last_scan[symbol]=now
                if g.runtime_execution_block:
                    plan,runner_detail=runner_plan(symbol,cache.frames,q,self.cfg,self.planner.research_context)
                    self.runner_views[symbol]={'state':'EJECUCIÓN BLOQUEADA','detail':g.runtime_execution_block,
                        'technical_detail':runner_detail,'plan':plan.to_dict() if plan else None}
                    self.status[symbol]={'state':'EJECUCIÓN BLOQUEADA','detail':g.runtime_execution_block};continue
                if self.paused:self.status[symbol]={'state':'PAUSA','detail':'Niveles conservados en MT5; análisis sigue activo'};continue
                if getattr(g,'network_available',True) is False:
                    self.status[symbol]={'state':'SIN INTERNET','detail':'Nuevas entradas en pausa; reconexión automática. Se conservan los niveles confirmados en MT5.'};continue
                if self.cfg['mode']!='trade':self.status[symbol]={'state':'OBSERVAR','detail':f'Solo análisis: {len(plans)} candidatas evaluadas; no se envían órdenes. Activa la operativa desde el encabezado o Ajustes → Operación.'};continue
                if symbol in g.journal.data['intents']:self.status[symbol]={'state':'RECONCILIANDO','detail':'Esperando evidencia MT5 de la solicitud anterior'};continue
                # Fund valid pending entries first. Runners use remaining capacity
                # and cannot cancel a confirmed map under the default policy.
                self.execute_pending_map(symbol,plans,q)
                if symbol not in g.journal.data['intents']:self.try_runner(symbol,q)
            except MarketPaused as e:
                # No fabricar nuevas órdenes con el último precio de oro durante
                # el cierre diario. Mantener la última propuesta visible.
                self.status[symbol]={'state':'MERCADO EN PAUSA','detail':str(e)}
            except Blocked as e:self.status[symbol]={'state':'ESPERANDO','detail':str(e)}
            finally:self.last_checked[symbol]=g.clock()
        # Los primeros intentos BTC+XAU usan M15/H1 antes de consultas profundas.
        # Completar H4/D1 ahora conserva el análisis visible sin bloquear el envío.
        self.complete_warmup()
        self.process_pending_verification()
        if self.cycle>1 and now-self._last_history>=30:
            self.learner.update();self._last_history=now
        if self.context and (self.cycle==1 or now-self._last_research_submit>=8):
            self.submit_context();self._last_research_submit=now
        # Measure technical/MT5 work separately from presentation preparation.
        # No network call, additional broker query or extra order check.
        technical_ms=(time.perf_counter()-started)*1000
        view_started=time.perf_counter()
        view=self.view();view['network_available']=getattr(g,'network_available',True)
        # Supervises prolonged silence; reads existing actor facts only.
        # It never sends a trade or alters risk to manufacture activity.
        view['session_activity']=self.session_watchdog.inspect(view,now)
        from snapshot_copy import snapshot_copy
        self._last_view=snapshot_copy(view)
        snapshot_ms=(time.perf_counter()-view_started)*1000
        if now>=self._pending_auto_due:
            from compact_review import automatic_targets
            automatic=automatic_targets(view,self.cfg)
            self.queue_pending_verification(automatic,view,deep=True)
            self._pending_auto_due=now+{'Ahorro de energía':600,'Equilibrado':180,'Rendimiento':20}.get(self.cfg.get('desktop',{}).get('performance_profile'),180)
        if self.context and hasattr(self.context,'study') and now>=self._study_due:
            self.context.study.submit({**view,**self.report_history()});self._study_due=now+30
        self.heartbeat(view)
        self.duration_ms=(time.perf_counter()-started)*1000
        view['cycle_ms']=round(self.duration_ms,1);self._last_view['cycle_ms']=view['cycle_ms']
        view['cycle_breakdown_ms']={'analysis_execution':round(technical_ms,2),
            'snapshot_ui':round(snapshot_ms,2),
            'postprocessing':round(max(0.,self.duration_ms-technical_ms-snapshot_ms),2)}
        self._last_view['cycle_breakdown_ms']=view['cycle_breakdown_ms']
        return view

    def analysis_evidence(self,symbol):
        ready,detail=self.evidence_ready(symbol,self.g.clock())
        frames=self.planner.caches[symbol].frames
        fusion=(self.planner.research_context.get('fusion') or {}).get(symbol,{})
        sources=sorted({c['name'] for c in fusion.get('components',[]) if c.get('name') and float(c.get('weight',0))>0})
        return {'technical_ready':ready,'technical_detail':detail,
                'timeframes':[tf for tf in ('M1','M5','M15','M30','H1','H4','D1','W1') if tf in frames],
                'context_sources':sources,'pending_samples':self.learner.metrics(symbol)['samples'],
                'first_request_cycle':self.first_requests.get(symbol,{}).get('cycle')}

    def confirmed_levels(self,symbol,snap=None):
        snap=snap or self.g.snapshot();self.g.reconcile(snap)
        # Mismas reglas que el mapa; conservar TODOS los tickets del usuario.
        out=[];q=self.quotes.get(symbol);evaluation={}
        for o in snap.orders:
            if o.symbol!=symbol or not self.g.owned_order(o):continue
            plan=order_plan(o,(self.g.journal.data['orders'].get(str(o.ticket)) or {}).get('plan'))
            # Mostrar riesgo de estos tickets sin volver a valorar todo el
            # portafolio al terminar cada símbolo. El ledger completo va en view.
            try:risk,_=self.g.plan_money(plan,float(o.volume_current),evaluation=evaluation)
            except Blocked:risk=None
            row={**plan.to_dict(),'ticket':int(o.ticket),'confirmed':True,'side':'BUY' if plan.side==1 else 'SELL',
                'entry':float(o.price_open),'sl':float(o.sl),'tp':float(o.tp),'volume':float(o.volume_current),
                'risk_usd':risk,'risk_cap_usd':self.g.trade_cap(snap)}
            row['assessment']=assess_plan(row,self.planner.caches[symbol].frames,self.g.clock(),
                {'spread':q.spread} if q else None)
            out.append(row)
        return out

    def confirmed_runner_levels(self,symbol,snap=None):
        from execution import OWN_RUNNER
        snap=snap or self.g.snapshot();self.g.reconcile(snap)
        out=[]
        for p in snap.positions:
            if p.symbol!=symbol or int(p.magic)!=OWN_RUNNER:continue
            meta=self.g.journal.data['positions'].get(str(p.ticket)) or {}
            row={**(meta.get('plan') or {}),'ticket':int(p.ticket),'confirmed':True,
                        'side':1 if int(p.type)==0 else -1,'lane':'RUNNER','kind':'MARKET',
                        'entry':float(p.price_open),'sl':float(p.sl),'tp':float(p.tp),'volume':float(p.volume)}
            q=self.quotes.get(symbol)
            row['assessment']=assess_plan(row,self.planner.caches[symbol].frames,self.g.clock(),
                {'spread':q.spread} if q else None)
            out.append(row)
        return out

    def handle_command(self,cmd):
        """Se ejecuta exclusivamente en el actor MT5; el chat envía mensajes."""
        action=cmd.get('action');g=self.g
        if action=='network_state':
            if type(cmd.get('online')) is not bool:return {'ok':False,'error':'Estado de conexión inválido'}
            g.network_available=cmd['online']
            if self.context:
                self.context.internet_available=cmd['online']
                if cmd['online']:self.context.refresh()
            return {'ok':True,'online':g.network_available}
        if action=='assistant_snapshot':return {'ok':True,'snapshot':self.view()}
        if action=='refresh_sources':
            if self.context:
                with self.context.lock:
                    self.context.due.clear();self.context.failures.clear()
                self.context.wake.set()
            return {'ok':True,'detail':'Nueva consulta solicitada en segundo plano.'}
        if action=='export_diagnostic':return {'ok':True,'snapshot':self.diagnostic_snapshot()}
        if action=='export_report_snapshot':return {'ok':True,'snapshot':self.report_snapshot()}
        if action=='strategy_lab_refresh':
            if not self.context or not hasattr(self.context,'strategy_lab'):return {'ok':False,'error':'El laboratorio necesita el motor de investigación activo.'}
            self.context.strategy_lab.submit(self.research_snapshot())
            return {'ok':True,'accepted':True,'detail':'Generación y evaluación solicitadas en segundo plano; sin envío de órdenes.'}
        if action=='verify_pending':
            from pending_verification import targets,identity
            view=self.view();plans=targets(view);symbol=cmd.get('symbol','ALL');pid=cmd.get('id')
            if symbol!='ALL' and symbol not in self.cfg['symbols']:return {'ok':False,'error':'Símbolo desconocido'}
            chosen=[p for p in plans if (symbol=='ALL' or p['symbol']==symbol) and (not pid or identity(p)==pid)
                and not view.get('markets',{}).get(p['symbol'],{}).get('scheduled_closed')]
            if not chosen:return {'ok':False,'error':'La pendiente ya no está vigente o el mercado está cerrado. Selecciona una pendiente actual.'}
            if 'require' in cmd:
                if type(cmd['require']) is not bool:return {'ok':False,'error':'La exigencia de IA debe ser verdadera o falsa'}
                account=list(self.g.identity or ())
                if account!=self.review_account:self.review_requirements={};self.review_account=account
                for p in chosen:
                    if cmd['require']:self.review_requirements[identity(p)]={'symbol':p['symbol'],'key':p['key'],'ticket':p.get('ticket')}
                    else:self.review_requirements.pop(identity(p),None)
                temp=self.review_preferences.with_suffix('.tmp');temp.parent.mkdir(parents=True,exist_ok=True)
                temp.write_text(__import__('json').dumps({'account':account,'required':self.review_requirements},ensure_ascii=False),encoding='utf-8');temp.replace(self.review_preferences)
            job=str(self.cycle)+'-'+str(len(self.pending_verification_requests)+1)
            self.queue_pending_verification(chosen,view,deep=bool(cmd.get('deep',True)),force=True)
            self.pending_verification_requests[job]={'id':job,'requested':self.g.clock(),'targets':[identity(p) for p in chosen],
                'deep':bool(cmd.get('deep',True)),'fingerprints':{identity(p):p['verification_fingerprint'] for p in chosen}}
            while len(self.pending_verification_requests)>16:self.pending_verification_requests.pop(next(iter(self.pending_verification_requests)))
            return {'ok':True,'accepted':True,'job':job,'targets':[identity(p) for p in chosen],
                'detail':('IA exigida: nuevos envíos o cambios de lo seleccionado esperan un dictamen vigente. ' if cmd.get('require') else '')+'Revisión individual solicitada. MT5 se comprueba uno por ciclo y la IA trabaja en segundo plano; verificar no envía ni modifica órdenes.'}
        if action=='apply_settings':
            from settings_effects import validate_form,changes
            revision=int(cmd.get('settings_revision') or 0)
            if revision and revision<=getattr(self,'settings_revision',0):return {'ok':False,'settings_applied':False,'stale_settings':True,'error':'Se descartó una solicitud de ajustes anterior a la última ya aplicada.'}
            saved=validate_form(cmd['config']);rows=changes(self.cfg,saved);self.cfg.update(saved)
            if revision:self.settings_revision=revision
            paths=cmd.get('changed_paths') or [r['path'] for r in rows]
            if any(not p.startswith(('desktop.','assistant.','knowledge.','charts.','studio.')) for p in paths):
                self.map_cache.clear();self.allocation_cache.clear();self._analysis_evaluations.clear()
            if self.context and any(p.startswith(('research.','assistant.')) for p in paths):self.context.refresh()
            return {'ok':True,'settings_applied':True,'changed_paths':paths,'detail':'Cambios aplicados por sus componentes: '+', '.join(paths),'effective':{p:__import__('settings_effects').value_at(self.cfg,p) for p in paths}}
        if action=='reverify':
            self.map_cache.clear();self.allocation_cache.clear();self._analysis_evaluations.clear()
            return {'ok':True,'detail':'Evaluación técnica renovada; envío mantiene sus validaciones críticas.'}
        if action=='risk_settings':
            self.map_cache.clear();self.allocation_cache.clear();self._analysis_evaluations.clear()
            snap=g.snapshot();cap=g.trade_cap(snap);ledger=g.reservation_ledger(snap)
            sizing=self.cfg['sizing']
            sizing_state={'enabled':bool(sizing['enabled']),'pending_scale_enabled':bool(sizing['scale_pending']),
                          'minimum_score':float(sizing['boost_score']),'minimum_quality':float(sizing['boost_quality']),
                          'risk_utilization':float(sizing['risk_utilization']),'configured_max_lot':float(sizing['max_lot']),
                          'automatic_override_of_minimum_lot_risk':bool(self.cfg['risk']['min_lot_structural_override_enabled'])}
            return {'ok':True,'detail':f'Riesgo aplicado: máximo {cap:.2f} USD por operación y presupuesto conjunto libre {ledger["available_usd"]:.2f} USD. Escalado de pendientes: {"activo" if sizing_state["pending_scale_enabled"] else "desactivado"}. Se evalúan BTC y oro por separado según SL, margen y mínimo MT5; no se fuerza un símbolo si no cabe.', 'trade_risk_cap':cap,'portfolio_risk':ledger,'adaptive_sizing':sizing_state}
        if action=='pause':self.paused=bool(cmd.get('paused',True));return {'ok':True}
        if action=='refresh':
            selected=cmd.get('sources')
            if selected is not None and (not isinstance(selected,list) or any(x!='local_ai' for x in selected)):
                return {'ok':False,'error':'Fuente de actualización no permitida'}
            if self.context:
                if selected is None:self.context.refresh()
                else:self.context.refresh(sources=selected)
            return {'ok':True,'detail':'Actualización solicitada a los proveedores en segundo plano'}
        runner_request=action in ('assistant_best_runner','assistant_analyze_runner','assistant_best_trade','assistant_analyze_trade')
        runner_only=action in ('assistant_best_runner','assistant_analyze_runner')
        analyze_only=action in ('assistant_analyze_pending','assistant_analyze_runner','assistant_analyze_trade')
        required_side={'BUY':1,'SELL':-1}.get(str(cmd.get('runner_side') or '').upper(),0)
        if cmd.get('runner_side') and not required_side:return {'ok':False,'error':'Dirección runner inválida'}
        if action not in ('assistant_best_pending','assistant_analyze_pending','assistant_best_runner','assistant_analyze_runner','assistant_best_trade','assistant_analyze_trade','assistant_plan','cancel_pending'):return {'ok':False,'error':'Acción desconocida'}
        if action in ('assistant_plan','cancel_pending') and (self.paused or self.cfg['mode']!='trade' or g.runtime_execution_block):return {'ok':False,'error':g.runtime_execution_block or 'Motor en pausa/observación: no se envió ninguna orden'}
        if action=='cancel_pending':
            o=next((o for o in g.snapshot().orders if int(o.ticket)==int(cmd.get('ticket',0))),None)
            if o is None:return {'ok':False,'error':'El ticket ya no figura como pendiente en MT5'}
            if not g.owned_order(o):return {'ok':False,'error':'La pendiente es manual/externa; no se modifica'}
            accepted=g.cancel(o,'Retirada explícita desde la interfaz');g.reconcile(g.snapshot())
            unresolved=o.symbol in g.journal.data['intents']
            return {'ok':bool(accepted and not unresolved),'unconfirmed':unresolved,'detail':'Retiro confirmado' if accepted and not unresolved else 'Retiro sin confirmación MT5'}
        if not self.initialized:self.warmup(fast=True)
        target=str(cmd.get('symbol') or 'ALL').upper()
        symbols=list(self.planner.caches) if target=='ALL' else [s for s in self.planner.caches if s.upper()==target or (s.startswith('BTC') and target.startswith('BTC')) or (s.startswith('XAU') and target.startswith('XAU'))]
        if not symbols:return {'ok':False,'error':'Símbolo no activo en Akira'}
        results=[]
        for symbol in symbols:
            detail='';unconfirmed=False;runner={};positions=[];accepted=False
            try:
                cache=self.planner.caches[symbol];cache.advance(g.clock())
                snap=g.snapshot();g.reconcile(snap);ready,reason=self.evidence_ready(symbol,g.clock())
                if not ready:raise Blocked(reason)
                q=g.quote(symbol);self.quotes[symbol]=q
                if action=='assistant_plan':
                    side={'BUY':1,'SELL':-1}.get(str(cmd.get('side')).upper(),0)
                    f=self.planner.caches[symbol].frames['M1']
                    plan=Plan(symbol,'CHAT:'+str(cmd.get('request_id',g.clock())),side,'PENDING',str(cmd.get('kind')).upper(),
                              float(cmd['entry']),float(cmd['sl']),float(cmd['tp']),f.atr,0,
                              str(cmd.get('reason') or 'Orden exacta del usuario'),int(f.bars[-1].time))
                    if cmd.get('candidate_id'):
                        from pending_verification import identity
                        original=next((p for p in self.candidates.get(symbol,[]) if identity(p.to_dict())==cmd['candidate_id']),None)
                        if original is None:raise Blocked('La candidata ya no está vigente. Actualiza la ficha antes de enviarla.')
                        if any(float(getattr(original,key))!=float(cmd[key]) for key in ('entry','sl','tp')) or original.side!=side or original.kind!=str(cmd.get('kind')).upper():
                            raise Blocked('Los niveles o la dirección cambiaron. No se envió una propuesta distinta de la seleccionada.')
                        plan=original
                    accepted=g.send_immediate_plan(self.with_learning_features(plan,q))
                else:
                    if self.context:self.planner.research_context=self.read_context()
                    cache=self.planner.caches[symbol];self.planner.tapes[symbol].update(q,cache.frames,g.clock());self.update_book(symbol)
                    restricted=analyze_only or self.paused or self.cfg['mode']!='trade' or g.runtime_execution_block
                    accepted=False;runner_handled=False
                    if runner_request:
                        if restricted:self.review_runner(symbol,q,required_side)
                        else:runner_handled=self.try_runner(symbol,q,required_side)
                        runner=dict(self.runner_views.get(symbol) or {})
                        positions=self.confirmed_runner_levels(symbol)
                        detail=str(runner.get('detail') or 'Sin señal runner confirmada')
                        accepted=bool(positions)
                    if not runner_only:
                        plans=self.scan_plans(symbol,q,force=True);self.candidates[symbol]=plans
                        if restricted:
                            detail=g.runtime_execution_block or ('Análisis actualizado; solicitado sin ejecución' if analyze_only else 'Análisis actualizado; motor en pausa/observación y sin envíos')
                        elif not runner_handled and not positions:
                            pending_result=self.execute_pending_map(symbol,plans,q)
                            accepted=pending_result['accepted'];detail=pending_result['detail']
                levels=[] if runner_only else self.confirmed_levels(symbol)
                unconfirmed=symbol in g.journal.data['intents']
                if unconfirmed:detail='Solicitud enviada sin evidencia final de MT5; no se duplica'
                elif action=='assistant_plan' and accepted and levels:detail='Pendiente confirmada por MT5'
                elif action=='assistant_plan' and accepted:detail='La orden se aceptó pero ya no figura como pendiente; revisar activación en posiciones'
                elif not detail:detail='MT5 rechazó/no confirmó la solicitud; revisar TERMINAL'
            except (Blocked,ValueError,TypeError,KeyError) as exc:
                detail=str(exc);levels=[] if runner_only else self.confirmed_levels(symbol);unconfirmed=symbol in g.journal.data['intents']
            self.log.event(symbol,'CHAT · '+detail)
            scenarios=[] if runner_only else self.directional_scenarios(symbol)
            results.append({'symbol':symbol,'levels':levels,'scenarios':scenarios,'runner':runner,
                            'positions':positions,'detail':detail,'execution_confirmed':bool(accepted),'risk_cap_usd':g.trade_cap(g.snapshot()),'unconfirmed':unconfirmed})
        return {'ok':any(r['execution_confirmed'] for r in results) if action=='assistant_plan' else any(r['levels'] or r['positions'] for r in results),'results':results,
                'execution_confirmed':any(r['execution_confirmed'] for r in results),
                'portfolio_risk':g.reservation_ledger(g.snapshot()),'unconfirmed':any(r['unconfirmed'] for r in results)}

    def view(self):
        snap=self.g.snapshot();a=snap.account;evaluation={};ledger=self.g.reservation_ledger(snap,evaluation=evaluation)
        account={k:getattr(a,k,None) for k in ('login','server','balance','equity','margin','margin_free','currency')}
        from risk_limits import configured_limits
        self._risk_limits=configured_limits(self.cfg,account)
        account['floating']=sum(float(getattr(p,'profit',0))+float(getattr(p,'swap',0)) for p in snap.positions)
        from datetime import datetime,timezone
        today=datetime.fromtimestamp(self.g.clock(),timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
        account['daily_net']=sum(self.g.pnl(d) for d in self.g.history if float(d.time)>=today and int(d.type) in (0,1)) if self.g.history_time and not self.g.history_error else None
        rows=[]
        for o in snap.orders:
            r=self.g.fingerprint(o,'order');r.update(owned=self.g.owned_order(o),comment=str(getattr(o,'comment','')),lifecycle=self.lifecycle.get(str(o.ticket),{}));rows.append(r)
        positions=[]
        for p in snap.positions:
            row=self.g.fingerprint(p,'position');row.update(owned=self.g.owned(p),profit=float(getattr(p,'profit',0)),swap=float(getattr(p,'swap',0)));positions.append(row)
        symbols={}
        for s,c in self.planner.caches.items():
            q=self.quotes.get(s);frames={}
            for name,f in c.frames.items():
                frames[name]=self.frame_summary(f)
            book=[]
            for o in snap.orders:
                if o.symbol!=s or not self.g.owned_order(o):continue
                p=order_plan(o,(self.g.journal.data['orders'].get(str(o.ticket)) or {}).get('plan'))
                book.append({**p.to_dict(),'ticket':int(o.ticket),'confirmed':True,'state':'MT5 CONFIRMADA'})
            book.extend({**p.to_dict(),'confirmed':False,'state':'CANDIDATA'} for p in self.candidates.get(s,[])[:8])
            bars_by_timeframe={name:[b.to_dict() for b in f.bars[-80:]] for name,f in c.frames.items()}
            symbols[s]={'bid':q.bid if q else None,'ask':q.ask if q else None,'spread':q.spread if q else None,
                        'quote_time':q.time if q else None,
                        'checked_at':self.last_checked.get(s),'last_analysis_at':self.last_scan.get(s),
                        'frames':frames,'bars':[b.to_dict() for b in c.frames['M1'].bars[-60:]] if 'M1' in c.frames else [],
                        'bars_by_timeframe':bars_by_timeframe,
                        'pending_book':book,'pending_performance':self.learner.metrics(s),'live':self.planner.tapes[s].last_metrics,
                        'broker_book':self.planner.broker_book.get(s,{}),
                        'scenario_book':self.directional_scenarios(s,snap,evaluation=evaluation,ledger=ledger),
                        'runner':self.runner_views.get(s,{}),'pending_cycle':self.pending_cycles.get(s,{}),
                        'allocation_checks':self.allocation_checks.get(s,[]),
                        'allocation_reasons':self.allocation_reasons.get(s,[]),
                        'broker_rejections':list(self.planner.pending_filter_reasons.get(s,{}).values())[:10],
                        'cache_errors':dict(c.errors),'analysis_inflight':c.analysis_future is not None}
            symbols[s]['decision']=decision_status(s,self.candidates.get(s,[]),
                self.planner.pending_candidate_audit.get(s,[]),symbols[s]['scenario_book'],
                self.allocation_checks.get(s,[]),book,self.pending_cycles.get(s,{}),self.status.get(s,{}),
                self.g.trade_cap(snap),self.g.runtime_execution_block or ('Sin Internet: nuevas entradas en pausa' if getattr(self.g,'network_available',True) is False else ''),self.cfg['mode'],self.paused)
        from operation_health import execution_gate
        safety=self.entry_safety()
        entry_block=self.g.runtime_execution_block or (safety['reason'] if not safety['allowed'] else '')
        effective_gate=execution_gate(self.cfg['mode'],self.paused,entry_block,
                                     getattr(self.g,'network_available',True),account)
        view={'build':BUILD_ID,'connected':True,'mode':self.cfg['mode'],'paused':self.paused,'network_available':getattr(self.g,'network_available',True),
                'execution_gate':effective_gate,
                'execution_block':entry_block,'execution_allowed':not bool(entry_block) and self.cfg['mode']=='trade' and not self.paused and getattr(self.g,'network_available',True),
                'account':account,'orders':rows,'positions':positions,'symbols':symbols,'as_of_utc':self.g.clock(),
                'status':self.status,'candidates':{s:[p.to_dict() for p in ps[:16]] for s,ps in self.candidates.items()},
                'audit':self.planner.pending_candidate_audit,'research':self.planner.research_context,
                'analysis':{s:self.analysis_evidence(s) for s in self.planner.caches},
                'learning':{s:self.learner.metrics(s) for s in self.planner.caches},
                'cycle_ms':round(self.duration_ms,1),'cycle':self.cycle,'updated':self.g.clock(),
                'position_closures':self.g.closure_monitor.rows(),
                'position_management':{str(p.ticket):copy.deepcopy(self.g.journal.data['positions'].get(str(p.ticket),{})) for p in snap.positions if self.g.owned(p)},
                'capital_protection':self.g.capital_status(snap),'entry_safety':self.entry_safety(),'risk_cap':ledger['cap_usd'],'trade_risk_cap':self.g.trade_cap(snap),'reserved_risk':ledger['reserved_usd'],
                'portfolio_risk':ledger,'risk_limits':self._risk_limits,
                'selection_evidence':self.planner.selection_summary,
                'selection_configuration':self.verification_configuration(),
                'quality_study':self.planner.research_context.get('quality_study',{}),
                'entry_quality_checks':copy.deepcopy(self.entry_checks),
                'confirmed_strategy_outcomes':copy.deepcopy(self._confirmed_outcomes[-300:]),
                'markets':{s:self.market_state(s) for s in self.planner.caches},
                'broker_terms':copy.deepcopy(getattr(self.g,'broker_terms',{})),
                'data_limits':{'max_tick_age_seconds':self.cfg['strategy']['max_tick_age_seconds']},
                'verification_receipts':copy.deepcopy(getattr(self.g,'verification_receipts',{})),
                'unconfirmed':list(self.g.journal.data['intents'])}
        from pending_verification import reports
        if self.review_requirements and list(self.g.identity or ())==self.review_account:
            from pending_verification import targets,identity
            promoted=False
            for p in targets(view):
                if not p.get('confirmed'):continue
                old=next((pid for pid,r in self.review_requirements.items() if not r.get('ticket') and r['symbol']==p['symbol'] and r['key']==p['key']),None)
                if old:
                    rule=self.review_requirements.pop(old);rule['ticket']=p['ticket'];self.review_requirements[identity(p)]=rule;promoted=True
            if promoted:
                temp=self.review_preferences.with_suffix('.tmp');temp.parent.mkdir(parents=True,exist_ok=True)
                temp.write_text(__import__('json').dumps({'account':self.review_account,'required':self.review_requirements},ensure_ascii=False),encoding='utf-8');temp.replace(self.review_preferences)
        view['required_pending_reviews']=list(self.review_requirements) if list(self.g.identity or ())==self.review_account else []
        view['pending_verifications']=reports(view,self.pending_checks)
        from operation_health import verification_job
        reviews=(view.get('research') or {}).get('pending_reviews') or {}
        for jid,job in list(self.pending_verification_requests.items()):
            # A finished job keeps its original decision; it cannot become a
            # waiting job again when a provider refreshes after the deadline.
            if job.get('terminal'):
                continue
            self.pending_verification_requests[jid]=verification_job(
                job,view['pending_verifications'],self.pending_checks,reviews,
                self.g.clock(),self.context is not None)
        view['pending_verification_requests']=copy.deepcopy(self.pending_verification_requests)
        return view

    def verification_configuration(self):
        return {**{k:copy.deepcopy(self.cfg[k]) for k in ('strategy_choice','strategy','symbol_profiles','execution','pending','risk','sizing','management','runner','lot','mode')},
            'research':{k:v for k,v in self.cfg['research'].items() if isinstance(v,bool) or k in ('model','pending_score_weight','dom_score_weight','cloud_pick_bonus','pending_activation_weight')},
            'model_configuration':{k:self.cfg.get('assistant',{}).get(k) for k in ('cloud','local_primary','model','trading_model','local_model','local_model_lite','local_vision_model')},
            'evolution_model':self.cfg.get('evolution',{}).get('analysis_model')}

    def entry_quality_guard(self,plan,snap):
        evidence=self.evaluate_entry_quality(plan,live=True)
        if not evidence['allowed']:
            self.notice_quality_block(plan,evidence['reason'])
            raise Blocked('Calidad de entrada: '+evidence['reason'])

    def evaluate_entry_quality(self,plan,live=False):
        from trade_quality_gate import evaluate,owned_outcomes
        evidence=evaluate(plan,self.planner.caches[plan.symbol].frames,
            owned_outcomes(self.g) if live else self._confirmed_outcomes,self.g.clock(),
            strict=self.cfg['execution'].get('require_primary_structural_engine',True))
        safety=self.entry_safety(live=live)
        if not safety['allowed']:
            evidence.update(allowed=False,reason=safety['reason'])
            evidence['checks'].append({'name':'Pausa tras racha de pérdidas propias','passed':False,'reason':safety['reason']})
        for meta in self.g.journal.data.get('positions',{}).values():
            if meta.get('symbol')==plan.symbol and meta.get('closed_observed_at') and not meta.get('closure') and 0<=self.g.clock()-float(meta['closed_observed_at'])<=900:
                reason='Cierre propio aún sin confirmar en MT5; esperar su resultado antes de reabrir '+plan.symbol
                evidence.update(allowed=False,reason=reason);evidence['checks'].append({'name':'Cierre confirmado','passed':False,'reason':reason});break
        self.entry_checks[plan.symbol+':'+plan.key]={'symbol':plan.symbol,'time':self.g.clock(),
            'levels':{k:getattr(plan,k) for k in ('symbol','side','kind','entry','sl','tp')},**evidence}
        while len(self.entry_checks)>64:self.entry_checks.pop(next(iter(self.entry_checks)))
        return evidence

    def notice_quality_block(self,plan,reason):
        key='QUALITY:'+plan.symbol+':'+str(plan.side)+':'+reason
        if key in self._quality_notices:return
        self._quality_notices.add(key)
        if len(self._quality_notices)>128:self._quality_notices={key}
        self.log.event(plan.symbol,'ENTRADA EVITADA · '+reason,operation='quality_entry_blocked',reason=reason,event_key=key)

    def entry_safety(self,live=False):
        from entry_safety import loss_pause
        from trade_quality_gate import owned_outcomes
        return loss_pause(self.cfg,owned_outcomes(self.g) if live else self._confirmed_outcomes,self.g.clock())

    def enforce_capital_protection(self,snap):
        from capital_guard import pending_reduction
        g=self.g
        safety=self.entry_safety()
        if (self.paused and safety['allowed']) or self.cfg['mode']!='trade' or g.runtime_execution_block or getattr(g,'network_available',True) is False:return snap
        state=g.capital_status(snap,refresh=True)
        entry_block=g.daily_loss_reason(snap) or (safety['reason'] if not safety['allowed'] else '')
        for _ in range(len(snap.orders)):
            choice=pending_reduction(g,snap,g.reservation_ledger(snap),state,entry_block)
            if choice is None:break
            order,reason=choice
            if order.symbol in g.journal.data['intents']:break
            try:
                if not g.cancel(order,'Protección de capital: '+reason):break
                snap=g.snapshot();g.reconcile(snap);snap=g.snapshot()
                if order.symbol in g.journal.data['intents']:break
            except Blocked as exc:
                self.log.report(order.symbol,'RETIRO PENDIENTE',str(exc));break
        return snap

    def review_loss_pendings(self,snap):
        from trade_quality_gate import evaluate
        if self.paused or self.cfg['mode']!='trade' or self.g.runtime_execution_block:return snap
        for o in snap.orders:
            if not self.g.owned_order(o):continue
            side=1 if int(o.type)%2==0 else -1
            rows=[r for r in self._confirmed_outcomes if r.get('symbol')==o.symbol and int(r.get('side',0))==side]
            lost=bool(rows and float(rows[-1].get('pnl',0))<0)
            from capital_guard import rules as protection_rules
            protection=protection_rules(self.cfg);continuous=protection['enabled'] and protection['strict_pending_quality']
            if not lost and not continuous:continue
            if continuous and not self.market_state(o.symbol)['open']:continue
            p=order_plan(o,(self.g.journal.data['orders'].get(str(o.ticket)) or {}).get('plan'))
            evidence=evaluate(p,self.planner.caches[o.symbol].frames,self._confirmed_outcomes,self.g.clock(),strict=continuous)
            if continuous:
                from trade_quality_gate import pending_admission
                admission=pending_admission(self.cfg,p)
                if not admission['allowed']:evidence.update(allowed=False,reason=admission['reason'])
            if evidence['allowed']:continue
            try:
                if self.g.cancel(o,('Revisión tras pérdida confirmada: ' if lost else 'Revisión continua de tesis: ')+evidence['reason']):
                    self.notice_quality_block(p,evidence['reason']);return self.g.snapshot()
            except Blocked as exc:self.log.report(o.symbol,'REVISIÓN DE TESIS',str(exc))
        return snap

    def pending_review_guard(self,plan,snap,volume,ticket=0):
        """Optional, user-demanded gate immediately before a new send or edit."""
        if list(self.g.identity or ())!=self.review_account:return
        policy=next(((pid,r) for pid,r in self.review_requirements.items() if r['symbol']==plan.symbol
            and (int(r.get('ticket') or 0)==ticket if ticket else not r.get('ticket') and r['key']==plan.key)),None)
        if not policy:return
        from pending_verification import fingerprint,identity
        pid,_=policy
        current={'symbols':{s:{'frames':{tf:self.frame_summary(f) for tf,f in c.frames.items()},
            'bid':self.quotes[s].bid if s in self.quotes else None,'ask':self.quotes[s].ask if s in self.quotes else None,
            'spread':self.quotes[s].spread if s in self.quotes else None,'quote_time':self.quotes[s].time if s in self.quotes else None} for s,c in self.planner.caches.items()},
            'research':self.planner.research_context,'selection_configuration':self.verification_configuration(),
            'markets':{s:self.market_state(s) for s in self.planner.caches},'updated':self.g.clock()}
        proposed={**plan.to_dict(),'volume':None}
        choices=[(pid,{**plan.to_dict(),'volume':volume})] if ticket else []
        if ticket:choices[0][1]['ticket']=ticket
        choices.append((identity(proposed),proposed))
        reviews=self.planner.research_context.get('pending_reviews') or {};reason='revisión individual aún pendiente, desactualizada o sin asistente disponible'
        for review_id,row in choices:
            review=reviews.get(review_id) or {};data=review.get('data') or {}
            if not isinstance(data,dict):data={}
            valid=review.get('fingerprint')==fingerprint(current,row) and review.get('state')=='COMPLETE' and -5<=self.g.clock()-float(review.get('updated') or 0)<=180
            if valid and data.get('verdict')=='APPROVE' and isinstance(data.get('reason'),str) and data['reason'].strip() and isinstance(data.get('missing'),list) and not data['missing']:return
            reason=review.get('error') or data.get('reason') or reason
        if self.context and hasattr(self.context,'request_pending_reviews'):
            current['required_pending_reviews']=[identity(proposed)]
            self.context.request_pending_reviews([proposed],current)
        raise Blocked('Verificación IA exigida para '+pid+': '+str(reason)[:240]+'. Revisa su ficha o desactiva la exigencia y solicita de nuevo.')

    def queue_pending_verification(self,plans,view,deep=True,force=False):
        from pending_verification import identity,levels
        for plan in plans:
            if view.get('markets',{}).get(plan['symbol'],{}).get('scheduled_closed'):continue
            pid=identity(plan);old=self.pending_checks.get(pid) or {}
            if not force and old.get('levels')==levels(plan) and old.get('broker_fingerprint')==plan.get('broker_fingerprint') and self.g.clock()-float(old.get('at') or 0)<20:continue
            self.pending_check_queue=[p for p in self.pending_check_queue if identity(p)!=pid]
            self.pending_check_queue.append(copy.deepcopy(plan))
        self.pending_check_queue=self.pending_check_queue[-48:]
        if deep and self.context and hasattr(self.context,'request_pending_reviews'):
            if force:
                missing=[name for name,row in view.get('research',{}).get('sources',{}).items() if isinstance(row,dict) and
                    row.get('enabled') is not False and not row.get('fresh') and not row.get('inflight')]
                if missing:self.context.refresh(sources=missing)
            self.context.request_pending_reviews(plans,view,force=force)

    def process_pending_verification(self):
        """One read-only MT5 check per cycle, always in the actor thread."""
        if not self.pending_check_queue or getattr(self.g,'network_available',True) is False:return
        from pending_verification import identity,levels
        from execution import PENDING,MODIFY,BUY_LIMIT,SELL_LIMIT,BUY_STOP,SELL_STOP
        data=self.pending_check_queue.pop(0);pid=identity(data)
        row={'levels':levels(data),'fingerprint':data.get('verification_fingerprint'),'broker_fingerprint':data.get('broker_fingerprint'),
            'at':self.g.clock(),'risk_passed':False,'broker_checked':False}
        self.pending_checks[pid]=row
        try:
            if not self.market_state(data['symbol'])['open']:raise Blocked('Mercado cerrado; no se comprueban niveles con precios antiguos')
            snap=self.g.snapshot();ticket=int(data.get('ticket') or 0)
            live=next((o for o in snap.orders if int(o.ticket)==ticket and self.g.owned_order(o)),None) if ticket else None
            if ticket and not live:raise Blocked('La pendiente se activó o desapareció de MT5; esta revisión ya no aplica')
            if live and any(float(getattr(live,k))!=float(data[n]) for k,n in (('price_open','entry'),('sl','sl'),('tp','tp'))):raise Blocked('Los niveles cambiaron en MT5; se solicita una revisión nueva')
            frame=self.planner.caches[data['symbol']].frames.get('M15')
            values={k:data[k] for k in Plan.__dataclass_fields__ if k in data}
            values.setdefault('lane','PENDING');values.setdefault('atr',frame.atr if frame else 1)
            values.setdefault('score',float(data.get('quality_score') or 0));values.setdefault('reason','Propuesta técnica conservada')
            values.setdefault('bar_time',frame.bars[-1].time if frame and frame.bars else int(self.g.clock()))
            p=Plan(**values);ignore=(ticket,) if ticket else ();evaluation={}
            volume=float(live.volume_current) if live else self.g.volume_for_plan(p,snap,ignore,evaluation=evaluation)
            p,q,risk,reward,margin=self.g.validate_plan(p,snap,ignore,volume=volume,editing=bool(live),evaluation=evaluation)
            if any(abs(float(getattr(p,k))-float(data[k]))>1e-8 for k in ('entry','sl','tp')):raise Blocked('Estos niveles requieren normalización al tick del broker; no se verifica una geometría distinta')
            typ=(BUY_LIMIT if p.side==1 else SELL_LIMIT) if p.kind=='LIMIT' else (BUY_STOP if p.side==1 else SELL_STOP)
            request={'action':MODIFY if live else PENDING,'symbol':p.symbol,'type':typ,'price':p.entry,'sl':p.sl,'tp':p.tp,'volume':volume,'type_filling':2}
            if live:request.update(order=ticket,type_time=int(getattr(live,'type_time',0)),expiration=int(getattr(live,'time_expiration',0)))
            else:request.update(self.g.pending_time_fields(self.g.valuation_call(evaluation,'symbol_info',p.symbol),self.cfg['pending']['ttl_seconds']))
            row.update(risk_passed=True,risk_usd=risk,reward_usd=reward,margin=margin,volume=volume)
            # An already-confirmed MT5 pending with these exact levels is a
            # no-op. MT5 returns 10025 for a redundant MODIFY; that is NOT an
            # order rejection. Risk/geometry/account checks above still run.
            if live and self.g.pending_parameters_unchanged(live,request):
                row.update(broker_checked=True,unchanged_confirmed=True,
                    broker_basis='Orden visible en MT5 con niveles idénticos; validación de riesgo y geometría aprobada; no se envió order_check MODIFY redundante.',
                    request={k:request[k] for k in ('action','type','price','sl','tp','volume')})
            else:
                try:self.g.check(request,p)
                except Blocked as exc:row['broker_error']=str(exc);raise
                row.update(broker_checked=True,request={k:request[k] for k in ('action','type','price','sl','tp','volume')})
        except Exception as exc:row['error']=type(exc).__name__+': '+str(exc)[:400]
        while len(self.pending_checks)>64:self.pending_checks.pop(next(iter(self.pending_checks)))

    def diagnostic_snapshot(self):
        """Foto solicitada al actor, sin enviar, editar ni retirar órdenes."""
        row=self.view()
        row['diagnostic']={'version':2,'cycle':self.cycle,'initialized':self.initialized,
            'deep_initialized':self.deep_initialized,'last_scan':dict(self.last_scan),
            'first_requests':dict(self.first_requests),'broker_cooldowns':dict(self.g.cooldowns),
            'last_broker_rejection':dict(self.g.last_rejection),'history_error':self.g.history_error}
        row['configured_execution']={k:self.cfg[k] for k in ('mode','symbols','risk','capital_protection','sizing','runner','pending','execution','pending_policy')}
        row['configured_execution']['management']=copy.deepcopy(self.cfg['management'])
        row.update(self.report_history())
        for symbol,cache in self.planner.caches.items():
            row['symbols'][symbol]['bars_by_timeframe']={name:[b.to_dict() for b in f.bars] for name,f in cache.frames.items()}
            row['symbols'][symbol]['cache_errors']=dict(cache.errors)
            info=self.g.api.symbol_info(symbol)
            row['symbols'][symbol]['broker_rules']={k:getattr(info,k,None) for k in
                ('volume_min','volume_step','volume_max','trade_tick_size','point','trade_stops_level','trade_freeze_level','trade_mode','order_mode')}
        return row

    def report_history(self):
        keys=('ticket','order','position_id','time','time_msc','symbol','type','entry','volume','price','profit','commission','swap','fee','magic','reason','comment')
        return {'order_journal':copy.deepcopy(self.g.journal.data['orders']),
            'runner_entries':copy.deepcopy(self.g.journal.data.get('runner_entries',{})),
            'position_journal':copy.deepcopy(self.g.journal.data['positions']),
            'history_deals':[{k:getattr(d,k,None) for k in keys} for d in self.g.history],
            'history_state':{'updated':self.g.history_time,'error':self.g.history_error},
            'operational_events':copy.deepcopy(list(getattr(self.log,'recent_events',()))) }

    def report_snapshot(self):
        """Lectura del último ciclo: cero llamadas MT5 y cero escrituras al bróker."""
        if not self._last_view:raise Blocked('Esperando el primer ciclo; vuelve a generar el informe al conectar MT5')
        row=copy.deepcopy(self._last_view)
        row['configured_execution']={k:copy.deepcopy(self.cfg[k]) for k in ('mode','symbols','risk','capital_protection','sizing','runner','pending','execution','pending_policy','management')}
        row.update(self.report_history())
        return row
