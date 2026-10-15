"""Evalúa toda la estructura y el contexto sin llamadas a internet."""
from collections import Counter
import math
from dataclasses import replace
from types import SimpleNamespace
import time
from execution import Blocked,BUY_LIMIT,SELL_LIMIT
from strategy import Plan,symbol_strategy,_wick_noise_floor
from market_cache import MarketCache
from tape import MarketTape
from pending_portfolio import pending_priority
from regime import regularize_metrics,classify_regime
from statistical import wilson_lower
from pending_edge import PendingEdge
from evolution import FEATURE_VERSION,entry_features,probability
from selection_evidence import SelectorEvidence,candidate_features,FEATURE_VERSION as SELECTION_VERSION

class PendingPlanner:
    def __init__(self,g,cfg,log,learner):
        self.g,self.cfg,self.log,self.learner=g,cfg,log,learner
        self.caches={s:MarketCache(g.api,s,log,cfg) for s,on in cfg['symbols'].items() if on}
        self.tapes={s:MarketTape() for s in self.caches}
        self.flow={};self.broker_book={};self.research_context={}
        self.opportunity_ledgers={s:SimpleNamespace(seen=set(),counts=Counter()) for s in self.caches}
        self.pending_filter_stats={};self.pending_filter_reasons={};self.pending_candidate_audit={}
        self.pending_cached_candidates={};self.final_edge=PendingEdge(cfg)
        self.selection_evidence=SelectorEvidence()
        self.selection_summary=self.selection_evidence.summary()
    def recent_pending_performance(self,symbol,now=None):
        return self.learner.metrics(symbol)

    def v203_regime(self,symbol):
        cache=self.caches[symbol]
        live=(self.flow.get(symbol,{}) or {}).get("live") or (self.tapes[symbol].last_metrics or {})
        ext=(self.research_context.get("fusion") or {}).get(symbol) or {}
        return classify_regime(cache.frames,live,ext)

    def pending_ev_proxy(self,plan,symbol):
        """EV comparable para reemplazo de pendientes; no se presenta como probabilidad."""
        risk=max(abs(float(plan.entry)-float(plan.sl)),1e-9); reward=max(abs(float(plan.tp)-float(plan.entry)),0.0)
        rr=reward/risk
        q=float(getattr(plan,'quality_score',0) or plan.score or 0)/100.0
        a=float(getattr(plan,'activation_score',0) or 0)/100.0
        hist=self.recent_pending_performance(symbol)
        hist=regularize_metrics(hist,self.cfg.get('learning',{}).get('min_samples_pending',12))
        empirical=float(hist.get('regularized_expectancy',hist.get('expectancy',0)) or 0)
        # proxy in R-units: quality/activation only rank; history is shrunk when sample is small.
        p=max(.20,min(.80,.35+.38*q+.12*a))
        return p*rr-(1-p)+max(-.25,min(.25,empirical*.05*float(hist.get('confidence',0))))

    def _pending_priority(self,plan):
        cfg=self.cfg.get('pending_policy',{})
        return pending_priority(plan) if cfg.get('enabled',False) and cfg.get('pending_quality_priority',True) else float(plan.score)

    def pending_grade(self,quality,activation,structural=True):
        combined=(.90*float(quality)+.10*float(activation)) if structural else (.75*float(quality)+.25*float(activation))
        if combined>=90:return 'A+'
        if combined>=84:return 'A'
        if combined>=76:return 'B+'
        return 'B'

    def research_freshness_factor(self):
        """Decaimiento por edad para contexto externo cacheado; MT5/local no se afecta."""
        raw=str(self.research_context.get("updated","") or "")
        if not raw:return .45
        try:
            from datetime import datetime,timezone
            dt=datetime.fromisoformat(raw.replace('Z','+00:00'))
            if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
            age=max(0.0,datetime.now(timezone.utc).timestamp()-dt.timestamp())
        except Exception:return .45
        fresh=float(self.cfg.get("research",{}).get("external_fresh_seconds",90.0))
        stale=float(self.cfg.get("research",{}).get("external_stale_seconds",600.0))
        if age<=fresh:return 1.0
        if age>=stale:return .15
        return max(.15,1.0-(age-fresh)/max(stale-fresh,1e-9)*.85)

    def fuse_pending_context(self,symbol,plans):
        """Torneo V201 de pendientes: estructura manda; fuentes ayudan a desempatar.

        Todo usa snapshots/cache ya disponibles: no espera red en el camino de
        order_send. Cloud/CoinGlass/DOM nunca pueden rescatar geometría mala ni
        convertir cercanía en calidad.
        """
        fusion=(self.research_context.get("fusion") or {}).get(symbol) or {}
        bias=max(-1.0,min(1.0,float(fusion.get("bias",0.0) or 0.0)))
        confidence=max(0.0,min(1.0,float(fusion.get("confidence",0.0) or 0.0)))
        freshness=self.research_freshness_factor()
        confidence*=freshness
        ext_weight=float(self.cfg.get("research",{}).get("pending_score_weight",7.0))
        selected_key=str(fusion.get("pending_key","") or "")
        pick_bonus=min(4.0,max(0.0,float(self.cfg.get("research",{}).get("cloud_pick_bonus",4.0))))
        book=self.broker_book.get(symbol) or {}
        imbalance=max(-1.0,min(1.0,float(book.get("imbalance",0.0) or 0.0))) if book.get("state")=="DOM del bróker" else 0.0
        dom_weight=float(self.cfg.get("research",{}).get("dom_score_weight",2.0))
        label=str(fusion.get("label","")).strip()
        deep_review=(self.research_context.get('deep_review') or {}).get(symbol) or {}
        review_conf=max(0.0,min(.35,float(deep_review.get('confidence',0.0) or 0.0)))
        review_preferred={str(x).upper() for x in (deep_review.get('preferred') or [])}
        review_avoid={str(x).upper() for x in (deep_review.get('avoid') or [])}
        review_bonus_cap=float(self.cfg.get('final_architecture',{}).get('deep_review_scenario_bonus',5.0))
        review_penalty_cap=float(self.cfg.get('final_architecture',{}).get('deep_review_scenario_penalty',6.5))
        pending_perf=regularize_metrics(self.recent_pending_performance(symbol),self.cfg.get('learning',{}).get('min_samples_pending',12))
        pending_regime=self.v203_regime(symbol)
        out=[]
        for p in plans:
            if p.lane!="PENDING":
                out.append(p); continue
            structural=('MAPA STRUCTURAL' in str(p.reason).upper() or ':H1:' in p.key.upper() or ':H4:' in p.key.upper())
            source='STRUCTURAL' if structural else 'TACTICAL'
            source_adjust=p.side*bias*confidence*ext_weight + p.side*imbalance*dom_weight
            # V12.1: además del promedio fusionado, cuenta consenso independiente.
            # Dos o más fuentes frescas en contra deben importar más que una sola
            # media cercana a cero; ninguna fuente puede rescatar mala geometría.
            components=list(fusion.get("components") or [])
            # El consenso necesita fuentes INDEPENDIENTES. Varias URLs del
            # mismo agregador de noticias no son tres confirmaciones distintas.
            # Se conserva el voto más fuerte de cada familia para el veto;
            # las señales originales quedan registradas en la fusión.
            independent={}
            for index,c in enumerate(components):
                try:
                    cb=float(c.get("bias",0) or 0)
                    cw=max(0.0,float(c.get("weight",0) or 0))*freshness
                    if not math.isfinite(cb) or not math.isfinite(cw):continue
                except (TypeError,ValueError,AttributeError):
                    continue
                name=str(c.get('name') or f'unknown:{index}').lower().split(':',1)[0]
                family='news_web' if name in ('news','global_news','search') else name
                if family not in independent or cw>independent[family][1]:
                    independent[family]=(cb,cw)
            agree=oppose=0.0; opposite_sources=0; agreeing_sources=0
            for cb,cw in independent.values():
                signed=p.side*cb
                if signed>=.18:
                    agree+=cw; agreeing_sources+=1
                elif signed<=-.18:
                    oppose+=cw; opposite_sources+=1
            consensus_adjust=max(-7.0,min(5.0,(agree-oppose)*9.0))
            if (bool(self.cfg.get("execution",{}).get("external_consensus_veto",True)) and
                    opposite_sources>=2 and oppose>agree*1.25 and confidence>=.22):
                consensus_adjust-=min(4.0,1.5+opposite_sources*.75)
            source_adjust=max(-10.0,min(9.0,source_adjust+consensus_adjust))
            scenario_token=('BUY_' if int(p.side)==1 else 'SELL_')+str(p.kind).upper()
            review_scale=min(1.0,review_conf/.35) if review_conf>0 else 0.0
            review_adjust=0.0
            if scenario_token in review_preferred:review_adjust+=review_bonus_cap*review_scale
            if scenario_token in review_avoid:review_adjust-=review_penalty_cap*review_scale
            picked=bool(selected_key and p.key==selected_key)
            cloud_adjust=pick_bonus if picked else 0.0

            risk=abs(float(p.entry)-float(p.sl)); reward=abs(float(p.tp)-float(p.entry))
            rr=reward/max(risk,1e-9)
            source_atr=max(float(getattr(p,"horizon_atr",0.0) or 0.0),float(p.atr),1e-9)
            structural_ratio=risk/source_atr
            preferred=float(symbol_strategy(self.cfg,symbol).get("pending_preferred_max_rr",4.5))
            geometry_adjust=0.0
            if rr>preferred:
                geometry_adjust-=min(8.0,(rr-preferred)*1.7)
            elif 1.75<=rr<=min(preferred,4.2):
                geometry_adjust+=2.4
            if structural_ratio<.14:
                geometry_adjust-=7.0
            elif structural_ratio>1.05:
                geometry_adjust-=min(5.0,(structural_ratio-1.05)*4.0)
            elif .20<=structural_ratio<=.78:
                geometry_adjust+=2.5

            # Historial real solo pesa con muestra suficiente; nunca se inventa
            # una probabilidad a partir de un score técnico.
            empirical_adjust=0.0
            if int(getattr(p,'empirical_samples',0) or 0)>=20:
                empirical_adjust=max(-5.0,min(5.0,float(getattr(p,'empirical_expectancy',0.0) or 0.0)*1.8))
                wr=float(getattr(p,'empirical_win_rate',-.1))
                if wr>=.60: empirical_adjust+=1.2
                elif 0<=wr<.40: empirical_adjust-=1.5
                empirical_adjust=max(-6.0,min(6.0,empirical_adjust))

            quality=max(0.0,min(100.0,float(getattr(p,"quality_score",p.score) or p.score)+
                                      source_adjust+cloud_adjust+review_adjust+geometry_adjust+empirical_adjust))
            # Solo un modelo de pendientes promovido sobre resultados fuera de muestra.
            daily=self.research_context.get('daily_learning') or {}
            champion=(daily.get('champions') or {}).get(symbol,{})
            learned_adjust=0.0
            if (daily.get('account')==list(self.g.identity or ()) and champion.get('promoted') is True and
                    champion.get('feature_version')==FEATURE_VERSION and champion.get('test_samples',0)>=20):
                values=entry_features(p.side,p,{},self.caches[symbol].frames,None,0)
                prob=probability(champion.get('weights',[]),values)
                base=float(champion.get('base_rate',.5))
                learned_adjust=max(-3.0,min(3.0,(prob-base)*10))
                quality=max(0.0,min(100.0,quality+learned_adjust))
            activation=max(0.0,min(100.0,float(getattr(p,"activation_score",0.0) or 0.0)))
            # H1/H4 se elige por calidad estructural. M5/M15/M30 sí necesita más
            # peso de activación porque su trabajo es llenar el mapa cercano.
            activation_weight=.10 if structural else .25
            final=min(100.0,activation_weight*activation+(1.0-activation_weight)*quality)
            final_pending_edge=None
            if bool(self.cfg.get('final_architecture',{}).get('pending_meta_edge_enabled',True)):
                try:
                    final_pending_edge=self.final_edge.pending_edge(p,quality,activation,pending_perf,pending_regime,bias*confidence)
                    blend=float(self.cfg.get('final_architecture',{}).get('pending_edge_blend',.38))
                    blend=max(0.0,min(.65,blend))
                    final=(1.0-blend)*final+blend*float(final_pending_edge.get('utility',final))
                except Exception:
                    final_pending_edge=None
            reason=(p.reason+f"; TORNEO FINAL {source}: calidad {quality:.1f}, activación {activation:.1f}, "
                    f"fuentes {source_adjust:+.1f} (fresh {freshness:.2f}; consenso +{agreeing_sources}/-{opposite_sources}), ORACLE {review_adjust:+.1f}, geometría {geometry_adjust:+.1f}, historial {empirical_adjust:+.1f}, modelo de cierres {learned_adjust:+.1f}")
            if deep_review.get('thesis'):reason+='; ORACLE tesis: '+str(deep_review.get('thesis'))[:220]
            if final_pending_edge is not None:
                reason+=(f"; META-EDGE pendiente util {float(final_pending_edge.get('utility',0)):.1f}/100 "
                         f"EV-proxy hipotético (NO GANANCIA ESPERADA VALIDADA) {float(final_pending_edge.get('ev_r',0)):+.2f}R · índice relativo de activación {100*float(final_pending_edge.get('activation_proxy',0)):.0f}/100 (NO probabilidad)")
            if picked: reason+=f"; selección cloud +{cloud_adjust:.1f} (solo desempate)"
            if label: reason+=f"; {label[:220]}"
            ranked=replace(p,score=final,activation_score=activation,quality_score=quality,reason=reason)
            # Quote is provided once for the whole map. This path never performs
            # extra MT5 calls or waits for training/network/external analysis.
            selection_quote=getattr(self,'_selection_quotes',{}).get(symbol)
            selection_enabled=self.cfg.get('quality_selection',{}).get('enabled',True)
            if selection_quote is not None and self.selection_evidence.usable(symbol,self.g.clock(),selection_enabled):
                features=candidate_features(ranked,self.caches[symbol].frames,selection_quote,self.g.clock())
                adjustment=self.selection_evidence.adjustment(symbol,features,self.g.clock(),
                    selection_enabled)
                reason+=f'; SELECCIÓN VALIDADA ajuste {adjustment:+.2f}/100 (prior externo; no probabilidad de la cuenta)'
                ranked=replace(ranked,reason=reason,selection_adjustment=adjustment,
                               selection_feature_version=SELECTION_VERSION,selection_features=features)
            out.append(ranked)
        return sorted(out,key=lambda p:(p.score,p.quality_score,p.activation_score),reverse=True)

    def proposed_pending_plans(self,symbol,setups,q,all_candidates=False,presence=False,evaluation=None,financial_gate=True):
        """Convierte el mapa FUTURO mostrado en intentos reales de MT5.

        V155 podía mostrar una zona buena como WATCH pero nunca volver a intentar
        enviarla porque había fallado un filtro de evaluación previo. V193 toma la
        mejor propuesta H1/H4 de cada tipo/lado, conserva EXACTOS sus niveles
        estructurales y la pasa al Gateway. El Gateway sigue imponiendo geometría,
        margen, riesgo y reglas reales del bróker antes de order_send.
        """
        if not hasattr(self,'_selection_quotes'):self._selection_quotes={}
        self._selection_quotes[symbol]=q
        rows=[];thresholds={}
        diag=Counter(); reasons={}; audit=[]
        def reject(setup,code,detail):
            diag[code]+=1
            reasons[setup.key]=detail
            record=next((x for x in audit if x['key']==setup.key),None)
            if record is not None: record.update(status='PENDING_REJECTED',reject_code=code,reason=detail)
            token=(setup.key,'PENDING_REJECTED',code)
            ledger=self.opportunity_ledgers[symbol]
            if token not in ledger.seen:
                ledger.seen.add(token);ledger.counts['PENDING_REJECTED']+=1
        fusion=(self.research_context.get("fusion") or {}).get(symbol) or {}
        selected_key=str(fusion.get("pending_key","") or "")
        pending_perf=self.recent_pending_performance(symbol,self.g.clock())
        # Una sola foto de cuenta por mapa. Antes cada zona hacía hasta cuatro
        # llamadas IPC adicionales; durante una caída el HOT path se atrasaba.
        # La caché dura únicamente este escaneo técnico. Gateway vuelve a valorar
        # cuenta, precio, divisa, riesgo y margen antes de cada envío real.
        evaluation=evaluation if evaluation is not None else {}
        if 'snapshot' not in evaluation:evaluation['snapshot']=self.g.snapshot()
        map_snapshot=evaluation['snapshot']; account=map_snapshot.account
        presence_gap=bool(presence)
        r_cfg=self.cfg.get("risk",{})
        # Usar exactamente el mismo cap que Gateway. Así la UI/Planner nunca
        # promete una orden que el transporte rechazará por otra cifra.
        absolute_cap=float(self.g.trade_cap(map_snapshot))

        # V200: calcular dinero con la distancia REAL que se va a enviar. V200
        # podía decidir demasiado pronto que una zona "no cabe" y nunca intentaba
        # mejorar el precio de entrada dentro de la MISMA zona. Para LIMIT se puede
        # esperar un fill más profundo, conservar el SL estructural y bajar riesgo.
        # No estrechamos el SL ni movemos una STOP de breakout hacia atrás.
        if 'info' not in evaluation:evaluation['info']=self.g.valuation_call(evaluation,'symbol_info',symbol)
        info_pending=evaluation['info']
        noise_floors=evaluation.setdefault('noise_floors',{})
        def quoted_profit(side,volume,entry,exit_price):
            return self.g.profit(symbol,side,volume,entry,exit_price,evaluation)
        evaluation_volume=float(self.cfg['lot'])
        def pending_money(entry_price,sl_price,tp_price,side_value):
            nonlocal evaluation_volume
            if info_pending is None:
                raise Blocked("sin symbol_info")
            step=float(getattr(info_pending,"trade_tick_size",0) or getattr(info_pending,"point",0) or .01)
            slip=max(q.spread*float(self.cfg["risk"]["slippage_spread_fraction"]),step*2)
            volume=float(self.cfg['lot'])
            if self.cfg['sizing']['enabled']:
                vstep=float(info_pending.volume_step)
                minimum=math.ceil((float(info_pending.volume_min)-1e-10)/vstep)*vstep
                minimum_risk=max(0.0,-float(quoted_profit(side_value,minimum,entry_price,sl_price-side_value*slip)))+float(self.cfg['risk']['round_turn_commission_per_lot'])*minimum
                fit=absolute_cap/max(minimum_risk,1e-9)*minimum
                ceiling=min(float(info_pending.volume_max),float(self.cfg['sizing']['max_lot']),max(minimum,volume))
                volume=max(minimum,math.floor((min(ceiling,fit)+1e-10)/vstep)*vstep)
            evaluation_volume=round(volume,8)
            commission=float(self.cfg['risk']['round_turn_commission_per_lot'])*volume
            reward_money=float(quoted_profit(side_value,volume,entry_price,tp_price))-commission
            risk_money=max(0.0,-float(quoted_profit(side_value,volume,entry_price,sl_price-side_value*slip)))+commission
            return risk_money,reward_money,step,slip

        def fit_limit_entry_to_budget(entry_price,sl_price,tp_price,side_value,horizon_value):
            """Busca el fill LIMIT más cercano al original que cabe en el presupuesto.

            Se mueve ENTRY hacia la invalidación (mejor precio), nunca el SL. Si el
            ajuste deja de pertenecer razonablemente a la zona o el bróker/spread no
            permiten geometría, se conserva el rechazo normal.
            """
            if not bool(self.cfg.get("execution",{}).get("pending_budget_fit_entry",True)):
                return None
            if info_pending is None:
                return None
            step=float(getattr(info_pending,"trade_tick_size",0) or getattr(info_pending,"point",0) or .01)
            broker_floor=max(step,float(getattr(info_pending,"trade_stops_level",0) or 0)*float(getattr(info_pending,"point",step) or step))
            spread_fraction=max(.08,float(symbol_strategy(self.cfg,symbol).get("max_spread_risk_fraction",.45)))
            min_gap=max(step*3,broker_floor*1.15,q.spread/max(spread_fraction*.90,1e-6))
            edge=sl_price+side_value*min_gap
            # LIMIT debe seguir siendo FUTURA respecto al precio ejecutable actual.
            ref=q.ask if side_value==1 else q.bid
            future=side_value*(ref-edge)
            if future<=max(broker_floor,step*2):
                return None
            cfg_local=symbol_strategy(self.cfg,symbol)
            max_shift=max(horizon_value*float(cfg_local.get('pending_budget_fit_max_shift_source_atr',.25)) if horizon_value>0 else 0,
                          q.spread*5,step*12)
            if abs(edge-entry_price)>max_shift:
                # SENTINEL: el fill no puede viajar casi hasta el SL solo para que
                # 0.01 quepa. Ese patrón fabricaba R:R enormes y entradas pobres.
                edge=entry_price + (edge-entry_price)*(max_shift/max(abs(edge-entry_price),1e-12))
            # Buscar en ticks negociables: 30 bisecciones sub-tick no cambian la
            # orden enviada y multiplicaban innecesariamente las llamadas a MT5.
            start_tick=round(entry_price/step)
            end_tick=math.ceil(edge/step) if side_value==1 else math.floor(edge/step)
            direction=-side_value
            span=int((end_tick-start_tick)*direction)
            if span<=0:return None
            edge=end_tick*step
            try:
                edge_risk,edge_reward,_,_=pending_money(edge,sl_price,tp_price,side_value)
            except Blocked:
                return None
            target_cap=absolute_cap*.94
            if edge_risk>target_cap+1e-9 or edge_reward<=0:
                return None
            lo,hi=0,span
            while hi-lo>1:
                mid=(lo+hi)//2
                candidate=(start_tick+direction*mid)*step
                try:
                    candidate_risk,_,_,_=pending_money(candidate,sl_price,tp_price,side_value)
                except Blocked:
                    return None
                if candidate_risk<=target_cap:
                    hi=mid
                else:
                    lo=mid
            fitted=(start_tick+direction*hi)*step
            original_price_risk=side_value*(entry_price-sl_price)
            fitted_price_risk=side_value*(fitted-sl_price)
            min_ratio=float(cfg_local.get('pending_budget_fit_min_risk_ratio',.70))
            if original_price_risk>0 and fitted_price_risk < original_price_risk*min_ratio:
                return None
            risk_money,reward_money,_,_=pending_money(fitted,sl_price,tp_price,side_value)
            return fitted,risk_money,reward_money

        for setup in setups:
            if setup.lane!="PENDING" or setup.kind not in ("LIMIT","STOP"):
                continue
            diag["raw_pending"]+=1
            tf=str(getattr(setup,"timeframe","") or "")
            presence_reserve=(str(setup.key).startswith('SWING:PRESENCE:') or str(setup.key).startswith('SWING:FAST:') or str(setup.key).startswith('SWING:SNAP:'))
            if presence_reserve and not presence:
                # Reserve candidates are deliberately invisible to the strict A/A+ map.
                continue
            source_map='STRUCTURAL' if tf in ('H1','H4') else 'TACTICAL'
            symbol_cfg=symbol_strategy(self.cfg,symbol)
            execution_cfg=self.cfg.get("execution",{})
            if source_map=='TACTICAL':
                allow_mid=bool(execution_cfg.get('allow_m15_m30_pending_origin',False)) and tf in ('M15','M30')
                allow_m5=(bool(execution_cfg.get('allow_m5_pending_origin',False)) and tf=='M5'
                          and str(setup.key).startswith('SWING:INTRADAY:'))
                if bool(execution_cfg.get('structural_only_pending',True)) and not (allow_mid or allow_m5):
                    reject(setup,'structural_only','Solo zonas M5 observadas y confirmadas por M15/H1, M15/M30 o estructura H1/H4 pueden llegar a MT5')
                    continue
            side=int(setup.side)
            # Source bars are BID. BUY activates at ASK but exits at BID;
            # SELL activates at BID but exits at ASK. This Plan is what UI,
            # risk estimate and MT5 use after conversion.
            entry=float(setup.level)+(q.spread if side==1 else 0.0)
            sl=float(setup.stop)+(q.spread if side==-1 else 0.0)
            tp=float(setup.target)+(q.spread if side==-1 else 0.0)
            horizon=max(float(setup.atr),float(getattr(setup,'horizon_atr',0.0) or 0.0))
            distance=(side*(q.bid-float(setup.level)) if setup.kind=='LIMIT' else
                      side*(float(setup.level)-q.bid))
            item={'key':setup.key,'map':source_map,'timeframe':tf,'side':'BUY' if setup.side==1 else 'SELL',
                  'kind':setup.kind,'entry':entry,'sl':sl,'tp':tp,'distance':round(distance,4),
                  'chart_bid_level':float(setup.level),'bidask_spread':round(q.spread,6),
                  'distance_atr':round(distance/max(horizon,1e-9),3),
                  'rr':round(int(setup.side)*(tp-entry)/max(int(setup.side)*(entry-sl),1e-9),3),
                  'quality_score':None,'activation_score':None,'risk_usd':None,
                  'potential_reward_usd':None,'expected_value_usd':None,
                  'status':'DETECTED','reject_code':'','reason':''}
            audit.append(item)
            # QUALITY-FIRST: un timeframe H1/H4 no convierte una EMA o una
            # proyección matemática en estructura observada. Solo el motor SWING
            # dedicado puede originar una orden: swing HTF, OB no mitigado o
            # ruptura H1 construidos sobre barras reales. Dejamos el rechazo en el
            # audit para que la UI explique por qué Akira NO envió una zona mediocre.
            if (source_map=='STRUCTURAL' and bool(execution_cfg.get('require_primary_structural_engine',True))
                    and not str(setup.key).startswith('SWING:')):
                reject(setup,'unobserved_structural_origin','H1/H4 sin origen SWING/OB/BOS observado; no ejecutar EMA/Fib/zona dinámica como si fuera estructura')
                continue
            if (source_map=='STRUCTURAL' and bool(execution_cfg.get('require_observed_target',True))
                    and not (presence and bool(execution_cfg.get('presence_allow_projected_target',True)))
                    and 'sin swing observado' in str(setup.reason).lower()):
                reject(setup,'unobserved_target','TP proyectado sin swing H1/H4/D1 observado; Akira espera un objetivo estructural real')
                continue
            token=(setup.key,'PENDING_GENERATED','')
            ledger=self.opportunity_ledgers[symbol]
            if token not in ledger.seen:
                ledger.seen.add(token);ledger.counts['PENDING_GENERATED']+=1
            if tf not in ('H1','H4','M5','M15','M30'):
                reject(setup,"unsupported_timeframe",f"Marco {tf} sin estructura M5/M15/M30/H1/H4")
                continue
            fast_tactical=(str(setup.key).startswith('SWING:FAST:') or str(setup.key).startswith('SWING:SNAP:')) and tf in ('M15','M30')
            intraday=str(setup.key).startswith('SWING:INTRADAY:') and tf=='M5'
            if source_map=='TACTICAL' and ((not setup.key.startswith('MAP:') and not fast_tactical and not intraday) or tf not in self.caches[symbol].frames):
                reject(setup,'unverified_tactical_thesis','Pendiente táctica sin zona M15/M30 construida y vigente por el motor')
                continue
            diag['htf' if source_map=='STRUCTURAL' else 'tactical']+=1
            side=int(setup.side)
            # Sigue siendo una PENDIENTE FUTURA: V193 elimina el bloqueo de score,
            # no el requisito de que la zona esté realmente por delante del precio.
            cfg=symbol_cfg
            selected=bool(selected_key and setup.key==selected_key and
                          self.cfg.get("execution",{}).get("execute_ai_pending_exact",True))
            direct=bool(self.cfg.get("execution",{}).get("direct_pending_from_map",True))
            # V193: si el propio mapa FUTURO ya propone el nivel, no volver a
            # descartarlo por el filtro ATR que servía para descubrir zonas. Aquí
            # solo exigimos que siga estando por delante del mercado. La distancia
            # mínima real del bróker se valida justo antes de order_send.
            # V193: IA NO puede acercar una pendiente para "forzar" ejecución.
            # BTC y ORO usan la misma regla HTF: distancia M1 + distancia respecto
            # al ATR del timeframe que originó la zona. Así BTC deja de verse como
            # un microentrada disfrazado aunque la IA seleccione esa fila.
            # build_setups() ya decidió que esta es una zona HTF. No repetir el
            # umbral M1, pero sí exigir una fracción del ATR/horizonte del timeframe
            # que originó la zona. Esto evita que BTC vuelva a parecer microentrada.
            minimum_future=max(horizon*(float(cfg.get('pending_horizon_fraction',.22)) if source_map=='STRUCTURAL' else .12),q.spread*2)
            if distance<minimum_future:
                reject(setup,"too_close",f"Demasiado cerca: {distance:.2f} < {minimum_future:.2f} de distancia futura mínima")
                continue
            # V193: DIRECTO no significa aceptar una zona absurda o caducada. El SELL STOP
            # BTC visto a ~76k con mercado ~81k sobrevivía porque direct_pending_from_map
            # saltaba el máximo de distancia. Ahora todos los caminos respetan un techo
            # estructural tanto en ATR M1 como en ATR del timeframe de origen.
            # V193: una tesis H1/H4 se mide contra el ATR DEL MARCO QUE LA ORIGINA.
            # El límite M1 servía al microentrada y estaba descartando zonas swing válidas,
            # especialmente XAU. M1 puede afinar timing, pero no decide el horizonte HTF.
            max_future=horizon*(float(cfg.get('pending_max_activation_source_atr',3.6)) if source_map=='STRUCTURAL' else (2.45 if fast_tactical else 1.65))
            if distance>max_future:
                reject(setup,"too_far",f"Demasiado lejos para activación: {distance:.2f} > {max_future:.2f} (ATR M1 y fuente)")
                continue
            if not direct and not selected and distance>horizon*float(cfg["max_pending_distance_atr"]):
                reject(setup,"legacy_distance","Distancia superior al máximo estructural configurado")
                continue
            # V200: primero validar geometría y DINERO REAL; luego decidir si una
            # LIMIT puede esperar un fill mejor dentro de la misma zona.
            risk=side*(entry-sl); reward=side*(tp-entry)
            original_risk=risk
            if risk<=0 or reward<=0:
                reject(setup,"bad_geometry","Entry, SL y TP no tienen la geometría BUY/SELL correcta")
                continue
            try:
                risk_money,reward_money,step,slip=pending_money(entry,sl,tp,side)
            except Blocked:
                reject(setup,"money_unavailable","MT5 no pudo calcular riesgo y beneficio con 0.01 lote")
                continue

            budget_fitted=False
            original_entry=entry
            if financial_gate and risk_money>absolute_cap+1e-9 and setup.kind=="LIMIT":
                fitted=fit_limit_entry_to_budget(entry,sl,tp,side,horizon)
                if fitted is not None:
                    entry,risk_money,reward_money=fitted
                    budget_fitted=True
                    risk=side*(entry-sl); reward=side*(tp-entry)
                    effective_level=entry-(q.spread if side==1 else 0.0)
                    distance=side*(q.bid-effective_level)
                    item.update(entry=entry,distance=round(distance,4),distance_atr=round(distance/max(horizon,1e-9),3),
                                budget_fit=True,original_entry=original_entry)
                    diag["budget_fit_entry"]+=1

            item.update(volume=evaluation_volume,risk_cap_usd=round(absolute_cap,3),risk_usd=round(risk_money,3),potential_reward_usd=round(reward_money,3),
                        rr=round(reward/max(risk,1e-9),3))
            # V200 QUALITY FIRST: después de cualquier conversión BID/ASK la orden
            # debe seguir teniendo un SL que sobreviva ruido real. Nunca aceptar el
            # patrón visto en XAU 4177.685/4179.070/4143.413 (~24.7R) donde el ENTRY
            # quedó pegado a la invalidación solo para encajar dinero.
            m1_frame=self.caches[symbol].frames.get('M1')
            m1_atr=float(m1_frame.atr) if m1_frame is not None else float(setup.atr)
            noise_key=(side,'M5' if str(setup.key).startswith('SWING:INTRADAY:') and tf=='M5' else 'HTF')
            if noise_key not in noise_floors:
                noise_floors[noise_key]=_wick_noise_floor(self.caches[symbol].frames,side,
                    ('M1','M5') if noise_key[1]=='M5' else None)
            wick_floor=noise_floors[noise_key]
            # El SL pertenece a la estructura original. Cuando un LIMIT espera
            # un fill más profundo para caber en el presupuesto, la robustez HTF se
            # comprueba contra la distancia ORIGINAL zona→invalidación; la distancia
            # fill→SL solo debe sobrevivir ruido M1/mechas/spread. Así el presupuesto
            # nunca mueve el SL, pero tampoco convierte una tesis swing en micro-stop.
            source_floor=horizon*float(cfg.get('pending_stop_min_source_atr',.55))
            if original_risk+1e-9<source_floor:
                reject(setup,'stop_structure_floor',f'Invalidación estructural original {original_risk:.3f} < piso HTF {source_floor:.3f}')
                continue
            if budget_fitted:
                min_stop=max(
                    m1_atr*float(cfg.get('pending_budget_fit_min_m1_atr',1.15)),
                    wick_floor*float(cfg.get('pending_budget_fit_wick_mult',.85)),
                    q.spread*float(cfg.get('pending_min_spread_stop_mult',3.0)),
                )
            else:
                min_stop=max(
                    m1_atr*float(cfg.get('pending_stop_min_m1_atr',1.8)),
                    wick_floor*float(cfg.get('pending_wick_clearance_mult',1.25)),
                    q.spread*float(cfg.get('pending_min_spread_stop_mult',3.0)),
                    source_floor,
                )
            if risk+1e-9<min_stop:
                try:
                    safe_sl=entry-side*min_stop
                    required_risk_money,_,_,_=pending_money(entry,safe_sl,tp,side)
                except Exception:
                    required_risk_money=None
                item.update(required_stop_distance=round(min_stop,4),required_risk_usd=(round(required_risk_money,3) if required_risk_money is not None else None),risk_cap_usd=round(absolute_cap,3))
                extra=(f'; SL seguro con 0.01 requeriría aprox. {required_risk_money:.2f} USD vs cap {absolute_cap:.2f} USD' if required_risk_money is not None else '')
                reject(setup,'stop_noise_floor',f'SL demasiado estrecho desde el fill: {risk:.3f} < piso de ruido {min_stop:.3f}'+extra)
                continue
            if financial_gate and risk_money>absolute_cap+1e-9:
                reject(setup,"over_risk_budget",f"Riesgo {risk_money:.2f} > límite {absolute_cap:.2f} USD con lote {evaluation_volume:g}; no hay fill LIMIT válido en la zona que respete SL y presupuesto")
                continue
            if not financial_gate and risk_money>absolute_cap+1e-9:
                item.update(financially_blocked=True,
                    funding_reason=f'Riesgo estimado {risk_money:.2f} > límite {absolute_cap:.2f}; completar valoración técnica, sin autorización de envío')

            # El SL estructural sigue intacto; al mejorar ENTRY el riesgo de precio
            # puede bajar mucho sin destruir la invalidación original.
            max_stop=horizon*(float(cfg.get('pending_stop_max_source_atr',1.8)) if source_map=='STRUCTURAL' else (3.2 if fast_tactical else 1.8))
            if risk>max_stop:
                reject(setup,"stop_too_wide",f"Stop estructural demasiado amplio desde el fill: {risk:.2f} > {max_stop:.2f}")
                continue
            rr=reward/max(risk,1e-9)
            preferred_min=float(cfg.get("min_rr_pending",1.4))
            hard_min=float(cfg.get("pending_hard_min_rr",1.15))
            sanity_max=float(cfg.get('pending_sanity_max_rr',30.0))
            hard_max=min(sanity_max,float(cfg.get('pending_hard_max_rr',sanity_max)))
            if rr<hard_min or rr>hard_max:
                reject(setup,'rr_outside',f'R:R {rr:.2f} fuera del rango estructural {hard_min:.2f}–{hard_max:.2f}')
                continue
            max_target=horizon*float(cfg.get('pending_target_max_source_atr',6.0))
            if reward>max_target:
                reject(setup,'target_too_far',f'TP demasiado lejano para el horizonte: {reward:.2f} > {max_target:.2f}')
                continue
            rr_preference_penalty=max(0.0,(preferred_min-rr)*3.5)
            if rr_preference_penalty:
                diag["rr_below_preference"]+=1
            minimum_reward=float(cfg.get("pending_min_reward_money",0.0) or 0.0)
            if reward_money<=0:
                reject(setup,"reward_too_small","TP estructural sin beneficio monetario positivo")
                continue
            reward_soft_penalty=4.0 if minimum_reward and reward_money<minimum_reward else 0.0
            if reward_soft_penalty: diag["reward_below_preference"]+=1
            if "sin swing observado" in str(setup.reason):
                reward_soft_penalty+=5.0
                diag["target_projection"]+=1
            # V193 añade una puntuación explícita de ACTIVACIÓN. Una zona no gana
            # solo por ser técnicamente bonita si está tan lejos que casi nunca se
            # toca; tampoco se acerca hasta parecer microentrada. El punto dulce se mide
            # contra el ATR del timeframe que originó la zona.
            distance_source=distance/max(horizon,1e-9)
            activation_weight=float(self.cfg.get("research",{}).get("pending_activation_weight",9.0))
            sweet=float(cfg.get("pending_sweet_limit_atr",.38) if setup.kind=="LIMIT" else
                        cfg.get("pending_sweet_stop_atr",.27))
            near_cap=float(cfg.get("pending_near_limit_atr",.90) if setup.kind=="LIMIT" else
                           cfg.get("pending_near_stop_atr",.65))
            low=max(float(cfg.get("pending_horizon_fraction",.11)),.04)
            if distance_source<=sweet:
                activation_score=72.0+28.0*max(0.0,min(1.0,(distance_source-low)/max(sweet-low,1e-9)))
            else:
                activation_score=100.0-42.0*max(0.0,min(1.0,(distance_source-sweet)/max(near_cap-sweet,1e-9)))
                if distance_source>near_cap:
                    activation_score-=min(28.0,(distance_source-near_cap)*35.0)
            activation_score=max(0.0,min(100.0,activation_score))
            source_ratio=original_risk/max(horizon,1e-9)
            structural_ratio_floor=float(cfg.get('pending_source_ratio_min_quality',.55))
            if source_map=='STRUCTURAL' and source_ratio+1e-9<structural_ratio_floor:
                reject(setup,'structural_stop_too_tight',f'Invalidación {source_ratio:.2f} ATR-fuente < piso estructural {structural_ratio_floor:.2f}; no usar stop de rango corto')
                continue
            tf_bonus={"M5":0.0,"M15":3.0,"M30":3.5,"H1":4.0,"H4":3.0}.get(tf,0.0)
            rr_bonus=min(9.0,max(0.0,(rr-float(cfg.get("min_rr_pending",1.8)))*4.0))
            # V193 PRECISION PENDING: la zona debe convivir con el contexto mayor.
            # Esto no es una probabilidad estadística; es un filtro de confluencia.
            frames=self.caches[symbol].frames
            mtf_weights={"M15":1.2,"H1":2.1,"H4":1.7,"D1":0.9,"W1":0.4}
            mtf_num=mtf_den=0.0; confirmations=0; contradictions=0
            for fname,w in mtf_weights.items():
                f=frames.get(fname)
                if not f: continue
                mtf_num += side*float(f.trend)*w; mtf_den += w
                ex=f.extra or {}; close=float(f.bars[-1].close)
                if ex.get("bos")==side or ex.get("sweep")==side: confirmations+=1
                if side*(close-float(ex.get("ema50",close)))>0: confirmations+=1
                if side*(float(ex.get("ema50",close))-float(ex.get("ema200",close)))>0: confirmations+=1
                if side*float(f.macd_hist)>0: confirmations+=1
                vwap=float(ex.get("vwap",close) or close)
                if side*(close-vwap)>0: confirmations+=1
                if side*float(ex.get("obv_slope",0.0) or 0.0)>.01: confirmations+=1
                adx=float(ex.get("adx",0.0) or 0.0)
                if adx>=22 and side*float(f.trend)>.25: confirmations+=1
                rsi=float(f.rsi)
                if (side==1 and 42<=rsi<=68) or (side==-1 and 32<=rsi<=58): confirmations+=1
                if side*float(f.trend)<-.55: contradictions+=1
            mtf_alignment=(mtf_num/max(mtf_den,1e-9)) if mtf_den else 0.0
            reversal_confirmed_stop=(setup.kind=='STOP' and (str(setup.key).startswith('SWING:FAST:S:') or str(setup.key).startswith('SWING:SNAP:S:')) and tf in ('M15','M30'))
            if contradictions>=2 and setup.kind=="STOP" and not reversal_confirmed_stop:
                reject(setup,"mtf_contradiction","Ruptura STOP contradicha por dos marcos superiores")
                continue
            if reversal_confirmed_stop and contradictions>=2:
                # No es un fade: el precio debe romper primero la estructura M15.
                # Penalizamos calidad por ir contra HTF, pero dejamos que compita
                # como cobertura futura para no perder el giro si realmente ocurre.
                mtf_num-=0.20*mtf_den
            mtf_bonus=max(-9.0,min(9.0,mtf_alignment*8.0))+min(5.0,confirmations*.65)-contradictions*2.0
            # Evitar LIMIT que intente atrapar un cuchillo contra H1/H4 con momentum fuerte.
            h1=frames.get("H1"); h4=frames.get("H4")
            strong_opp=sum(1 for f in (h1,h4) if f is not None and side*float(f.trend)<-.68 and float((f.extra or {}).get("adx",0) or 0)>=24)
            if strong_opp>=2 and not reversal_confirmed_stop:
                reject(setup,"htf_strong_against","H1 y H4 con ADX fuerte en contra; no atrapar movimiento")
                continue
            ideal_ratio=float(cfg.get('pending_source_ratio_ideal',.72))
            if source_map=='STRUCTURAL':
                geometry_bonus=max(-7.0,4.0-abs(source_ratio-ideal_ratio)*10.0)
            else:
                geometry_bonus=(3.0 if .16<=source_ratio<=.75 else
                                -6.0 if source_ratio<.12 else -3.0 if source_ratio>1.25 else 0.0)
            # V193 ENSEMBLE DE ESTRATEGIAS: no existe una única estrategia superior
            # en todos los regímenes. Se pondera el tipo de setup según contexto:
            # LIMIT = pullback/retest de oferta-demanda/OB/FVG; STOP = breakout/BOS.
            # Esto selecciona entre familias ya estructurales, nunca inventa niveles.
            setup_text=str(setup.reason or '').lower()
            family=('BREAKOUT/BOS' if setup.kind=='STOP' else
                    'OB/FVG' if ('order block' in setup_text or ' ob ' in (' '+setup_text+' ') or 'fvg' in setup_text) else
                    'PULLBACK/RETEST')
            htf=[f for f in (frames.get('M15'),frames.get('H1'),frames.get('H4')) if f is not None]
            trend_agree=sum(1 for f in htf if side*float(f.trend)>.18)
            trend_opp=sum(1 for f in htf if side*float(f.trend)<-.30)
            adx_avg=(sum(float((f.extra or {}).get('adx',0) or 0) for f in htf)/max(len(htf),1)) if htf else 0.0
            ensemble_bonus=0.0
            if setup.kind=='STOP':
                ensemble_bonus += min(5.0,1.5*trend_agree)-min(8.0,2.8*trend_opp)
                if adx_avg>=22: ensemble_bonus+=2.0
                if any((f.extra or {}).get('bos')==side for f in htf): ensemble_bonus+=2.0
            else:
                ensemble_bonus += min(4.5,1.2*trend_agree)-min(7.0,2.4*trend_opp)
                if 'fvg' in setup_text or 'oferta/demanda' in setup_text or 'swing' in setup_text: ensemble_bonus+=1.5
                if any((f.extra or {}).get('sweep')==side for f in htf): ensemble_bonus+=1.5
                # En tendencia demasiado fuerte contra el LIMIT no tratamos de atrapar cuchillos.
                if adx_avg>=28 and trend_opp>=2: ensemble_bonus-=4.0
            ensemble_bonus=max(-10.0,min(8.0,ensemble_bonus))
            # XAU V193: confluencia pública tipo chart-grader: niveles redondos
            # ($5/$10), estructura HTF y sesión son BONUS, nunca crean la entrada.
            round_bonus=0.0
            if symbol.upper().startswith("XAU"):
                nearest5=round(entry/5.0)*5.0; nearest10=round(entry/10.0)*10.0
                dround=min(abs(entry-nearest5),abs(entry-nearest10))
                tol=max(float(getattr(setup,"atr",0.0))*.22,0.35)
                if dround<=tol:
                    round_bonus=3.0*max(0.0,1.0-dround/max(tol,1e-9))
                hour=time.gmtime(float(self.g.clock())).tm_hour
                if 6<=hour<18: round_bonus+=0.8  # sesión líquida amplia; solo bonus
            # Los scores técnicos suelen vivir en ~57..95. Una pendiente no debe
            # saturar 100 solo por confluencias y dejar sin efecto activación/fuentes.
            provenance_bonus=0.0
            if source_map=='STRUCTURAL':
                if 'order block htf no mitigado' in setup_text: provenance_bonus+=4.0
                elif 'swing htf' in setup_text: provenance_bonus+=3.0
                if 'centro cluster htf' in setup_text or 'confluencias htf' in setup_text: provenance_bonus+=1.5
                if 'fallback' in setup_text or 'proyectad' in setup_text: provenance_bonus-=8.0
            quality_score=64.0+(float(setup.score)-57.0)*.35+tf_bonus+rr_bonus+geometry_bonus+mtf_bonus+ensemble_bonus+round_bonus+provenance_bonus-reward_soft_penalty-rr_preference_penalty
            # HUNTER: un STOP M15/M30 contrario a HTF no intenta adivinar el giro:
            # queda fuera del mercado hasta que el precio ROMPE la microestructura. Esa
            # confirmación futura merece crédito propio, sin fingir que ya existe confluencia HTF.
            if reversal_confirmed_stop:
                quality_score+=float(cfg.get('pending_reversal_break_confirmation_bonus',7.0))
            if minimum_reward>0:
                quality_score+=min(3.0,reward_money/max(minimum_reward,1e-9))
            prefer=max(.1,min(1.0,float(cfg.get("pending_budget_prefer_fraction",.78))))
            if risk_money<=absolute_cap*prefer:
                quality_score+=1.8 if tf in ("H1","H4") else 1.0
            # Reservar margen para que fuentes/DOM puedan desempatar entre dos
            # candidatas ya buenas, sin rescatar una que falló las puertas.
            quality_score=max(0.0,min(95.0,quality_score))
            item.update(quality_score=round(quality_score,2),activation_score=round(activation_score,2))
            # V205: un RR muy alto no es automáticamente "mejor". Solo sobrevive
            # si la calidad estructural realmente lo respalda; evita targets bonitos
            # pero poco plausibles y mantiene casos como 2R–4R sin castigo artificial.
            pcfg=self.cfg.get('pending',{})
            extreme_rr=float(pcfg.get('extreme_rr_threshold',4.5))
            if rr>extreme_rr:
                if bool(pcfg.get('extreme_rr_structural_only',True)) and source_map!='STRUCTURAL':
                    reject(setup,'rr_extreme_unconfirmed',f'R:R {rr:.2f} extremo sin origen H1/H4 estructural')
                    continue
                rq=float(pcfg.get('extreme_rr_min_quality',88.0))
                if quality_score<rq:
                    reject(setup,'rr_extreme_unconfirmed',f'R:R {rr:.2f} exige calidad estructural >= {rq:.0f}; actual {quality_score:.1f}')
                    continue
            # V200 separa dos trabajos distintos. Una H1/H4 de alta calidad puede
            # estar lejos y seguir siendo una excelente pendiente; el mapa táctico
            # M5/M15/M30 sí necesita mayor probabilidad de activación cercana.
            if source_map=='STRUCTURAL':
                min_activation=float(cfg.get('pending_structural_activation_min',18.0))
                min_quality=float(cfg.get('pending_structural_quality_min',cfg.get('pending_quality_min',78.0)))
                if presence:
                    min_activation=float(cfg.get('pending_fallback_structural_activation',8.0))
                    min_quality=float(cfg.get('pending_fallback_structural_quality',68.0))
            else:
                min_activation=float(cfg.get('pending_tactical_activation_min',42.0))
                min_quality=float(cfg.get('pending_tactical_quality_min',cfg.get('pending_quality_min',78.0)))
                if presence:
                    min_activation=float(cfg.get('pending_fallback_tactical_activation',24.0))
                    min_quality=float(cfg.get('pending_fallback_tactical_quality',68.0))
            # Un fill LIMIT mejorado por presupuesto suele estar más profundo y por
            # definición tarda más en activar. No confundir menor cercanía con mala
            # tesis: sigue compitiendo por calidad, pero con piso de activación menor.
            if budget_fitted:
                min_activation=min(min_activation,float(cfg.get('pending_budget_fit_activation_min',34.0)))
            if presence and reversal_confirmed_stop:
                # Cobertura HUNTER: la orden solo puede activarse después de ruptura M15/M30.
                # Mantiene puertas de geometría, SL, R:R, riesgo, margen y Gateway; únicamente
                # evita exigir al giro futuro la misma confluencia que a una tendencia ya madura.
                min_quality=min(min_quality,float(cfg.get('pending_reversal_stop_quality_min',54.0)))
                min_activation=min(min_activation,float(cfg.get('pending_reversal_stop_activation_min',20.0)))
            if presence and str(setup.key).startswith('SWING:SNAP:'):
                # FLASHMAP busca velocidad como el mapa manual: el nivel ya viene de
                # estructura observada M15/H1 y todavía debe superar SL, RR, riesgo,
                # margen, geometría y Gateway. Solo evitamos que el score compuesto
                # vuelva a congelar un nivel útil por una décima de calidad.
                min_quality=min(min_quality,float(cfg.get('pending_snap_quality_min',66.0)))
                min_activation=min(min_activation,float(cfg.get('pending_snap_activation_min',14.0)))
            if pending_perf.get("usable") and float(pending_perf.get("expectancy",0.0))<0:
                # El historial negativo penaliza el ranking, pero en el mapa ALWAYS-ON
                # no puede subir el umbral hasta 100 y dejar el bot seis horas vacío.
                # Geometría, riesgo, margen, RR y estructura siguen siendo puertas duras.
                min_quality += min(4.0 if presence else 8.0,2.0+1.0*int(pending_perf.get("loss_streak",0)))
            # Una sola pérdida reciente del MISMO lado exige confluencia extra,
            # incluso antes de alcanzar cinco muestras. No afecta órdenes vivas.
            if (int(pending_perf.get("last_side",0))==side and float(pending_perf.get("last_pnl",0))<0 and
                    0<=self.g.clock()-float(pending_perf.get("last_close_time",0))<900):
                min_quality += 3.0
            side_samples=(pending_perf.get("side_samples") or {}).get(side,0)
            side_ev=(pending_perf.get("side_expectancy") or {}).get(side,0.0)
            if side_samples>=3 and float(side_ev)<0:
                min_quality += min(3.0 if presence else 5.0,1.5+abs(float(side_ev))*.25)
            if presence:
                # ASTRA: presencia significa 'mejor escenario estructural disponible',
                # no 'esperar una A+ estadísticamente perfecta'. Limitar únicamente
                # los umbrales blandos; nunca se relajan SL/TP, riesgo, margen o MT5.
                min_quality=min(min_quality,90.0)
                min_activation=min(min_activation,12.0)
            if self.cfg.get('pending_policy',{}).get('enabled',False):
                # A presence quota must never promote a weaker zone. Generate
                # observed alternatives, then let them meet the real thresholds.
                if quality_score<min_quality:
                    reject(setup,'quality_low',f'V9.4 calidad {quality_score:.1f} < {min_quality:.1f}; no llenar cupo con fallback')
                    continue
                if activation_score<min_activation:
                    reject(setup,'activation_low',f'V9.4 activación {activation_score:.1f} < {min_activation:.1f}')
                    continue
            structural=(source_map=='STRUCTURAL')
            structure_score=max(0.0,min(100.0,64.0+tf_bonus*3.0+geometry_bonus*2.0+ensemble_bonus*2.0))
            mtf_score=max(0.0,min(100.0,50.0+mtf_alignment*32.0+confirmations*3.0-contradictions*8.0))
            liquidity_score=max(0.0,min(100.0,activation_score+round_bonus*3.0))
            flow_score=max(0.0,min(100.0,50.0+ensemble_bonus*4.0+side*float((self.tapes[symbol].last_metrics or {}).get('tick_balance',0.0) or 0.0)*18.0))
            sl_ideal=float(cfg.get('pending_source_ratio_ideal',.72)) if structural else .48
            sl_quality=max(0.0,min(100.0,100.0-abs(source_ratio-sl_ideal)*(72.0 if structural else 90.0)))
            target_quality=max(0.0,min(100.0,82.0-abs(rr-min(float(cfg.get('pending_preferred_max_rr',4.0)),3.0))*10.0))
            regime_score=max(0.0,min(100.0,50.0+trend_agree*12.0-trend_opp*16.0+(6.0 if adx_avg>=22 else 0.0)))
            item.update(quality_score=round(quality_score,2),activation_score=round(activation_score,2),
                        structure_score=round(structure_score,2),mtf_score=round(mtf_score,2),
                        liquidity_score=round(liquidity_score,2),flow_score=round(flow_score,2),
                        sl_quality=round(sl_quality,2),target_quality=round(target_quality,2),
                        regime_score=round(regime_score,2),entry_precision=round(activation_score,2))
            soft_fallback=bool(presence)
            if presence_reserve:
                item['presence_reserve']=True
                item['fast_reflex']=str(setup.key).startswith('SWING:FAST:')
                item['snap_analyst']=str(setup.key).startswith('SWING:SNAP:')
            activation_weight=.10 if structural else .25
            score=activation_weight*activation_score+(1.0-activation_weight)*quality_score
            if soft_fallback:score-=11.0 if presence_gap else 7.0
            grade=self.pending_grade(quality_score,activation_score,structural)
            item['grade']=grade;item['soft_fallback']=soft_fallback
            if structural:
                execution=self.cfg.get('execution',{})
                grade_key='presence_minimum_structural_grade' if presence else 'minimum_structural_grade'
                required_grade=str(execution.get(grade_key,'B' if presence else 'A') or ('B' if presence else 'A')).upper()
                grade_rank={'B':0,'B+':1,'A':2,'A+':3}
                if grade_rank.get(grade,0)<grade_rank.get(required_grade,0 if presence else 2):
                    reject(setup,'grade_below_required',f'Pendiente {grade}: Akira exige {required_grade} o superior en este mapa')
                    continue
            activation_adjust=(activation_score-70.0)/30.0*activation_weight
            fit_note=(f"; BUDGET-FIT ENTRY {original_entry:g}→{entry:g} conservando SL {sl:g}" if budget_fitted else "")
            reason=(setup.reason+f"; PROPUESTA V200 DIRECTA → ORDER_SEND; MAPA {source_map} {tf}"
                    +fit_note
                    +f"; activación {activation_score:.0f}/100 ({distance_source:.2f} ATR-fuente)"
                    +f"; calidad {quality_score:.0f}/100; grado {grade}; MTF {mtf_alignment:+.2f}; ensemble {family} {ensemble_bonus:+.1f}; round/session {round_bonus:+.1f}; final {score:.0f}/100" + ("; V5 PRESENCE FALLBACK" if soft_fallback and presence_gap else "; BEST_VALID_FALLBACK" if soft_fallback else "")
                    +f"; P/L 0.01: riesgo {risk_money:.2f}, objetivo {reward_money:.2f}" + ("; MAPA SIEMPRE ACTIVO: mejor tesis segura disponible, bajo control continuo" if presence else ""))
            if selected:
                reason+="; IA CLOUD ELIGIÓ ESTA PENDIENTE EXACTA"
            diag["accepted_pre_gateway"]+=1
            side_n=int(pending_perf.get("side_samples",{}).get(side,0) or 0)
            side_wr=float(pending_perf.get("side_win_rate",{}).get(side,.5))
            if side_n>=20:
                conservative_p=wilson_lower(side_wr*side_n,side_n)
                candidate_ev=conservative_p*reward_money-(1-conservative_p)*risk_money
                item['expected_value_usd']=round(candidate_ev,3)
                reason+=f'; EV estimado con historial de pendientes {symbol} {"BUY" if side==1 else "SELL"}: {candidate_ev:+.2f} USD / {side_n} cierres; sin calibración por familia'
                if candidate_ev<=0:
                    # El bucket símbolo/lado mezcla familias, geometrías y builds.
                    # Sirve como prior acotado en fuse_pending_context; no es una
                    # estimación calibrada para vetar TODAS las zonas nuevas.
                    item['historical_warning']=f'Historial agregado desfavorable: EV orientativo {candidate_ev:+.2f}; falta calibración por familia'
                    diag['uncalibrated_empirical_warning']+=1
            else:
                reason+='; EV NO CALIBRADO (muestra insuficiente)'
            item.update(status=('SOFT_FALLBACK' if soft_fallback else 'QUALIFIED'),reason=('BEST_VALID_FALLBACK; falta Gateway/MT5' if soft_fallback else 'Pasa filtros locales; falta Gateway/MT5'))
            # La muestra se refiere a pendientes propias de este mismo símbolo y
            # lado. No se traslada el resultado opuesto a una orden nueva.
            empirical_n=side_n
            empirical_wr=side_wr if side_n>=20 else -1.0
            empirical_ev=float(pending_perf.get("side_expectancy",{}).get(side,0.0) or 0.0) if side_n>=20 else 0.0
            thresholds[setup.key]=(min_quality,min_activation)
            rows.append(Plan(symbol,setup.key,side,"PENDING",setup.kind,entry,sl,tp,
                             float(setup.atr),min(100.0,score),
                             reason,
                             int(setup.created_bar),float(entry if budget_fitted else setup.level),
                             max(float(setup.atr),float(getattr(setup,"horizon_atr",0.0) or 0.0)),
                             activation_score,quality_score,empirical_wr,empirical_n,empirical_ev,
                             signal_timeframe=tf,signal_atr=horizon))
        # CRÍTICO V193: fusionar TODAS las zonas antes de elegir el ganador de cada
        # cuadrante. V168 elegía primero el mejor técnico y después aplicaba IA, por
        # lo que una zona alternativa favorecida por CoinGlass/YouTube/Cloud jamás
        # podía sustituirla. Ahora estructura + activación + fuentes compiten juntas.
        fused=self.fuse_pending_context(symbol,rows)
        valid=[]
        for p in fused:
            # The context fusion can occasionally return a candidate with a
            # different key than the baseline that was fully validated above.
            # Missing provenance must not crash a whole BTC/XAU worker cycle.
            # Nor may we invent a threshold and send an unvalidated order.
            criteria=thresholds.get(p.key)
            if criteria is None:
                reject(p,'fusion_missing_baseline',
                       'Se descartó una tesis fusionada sin evaluación técnica original; no se enviará a MT5.')
                continue
            min_quality,min_activation=criteria
            # REFLEX relaxes the ordinary fallback threshold so the map does not
            # freeze, but an extreme negative final synthesis is still a hard veto.
            # This prevents stale/news-opposed candidates from being sent merely
            # because the presence threshold is configured as zero.
            if presence:
                floor=float(self.cfg.get('execution',{}).get('presence_final_context_floor',18.0))
                # HUNTER sends from the local technical map immediately. Cached web/YouTube
                # may improve or replace it on later cycles, but stale/missing research must
                # never leave MT5 empty. The configured floor still rejects truly collapsed
                # local quality, not lack of Internet.
                min_quality=max(min_quality,floor)
            item=next((r for r in audit if r['key']==p.key),None)
            if item:item.update(quality_score=round(p.quality_score,2),activation_score=round(p.activation_score,2))
            if p.quality_score<min_quality or p.activation_score<min_activation:
                reject(p,'final_context_quality',f'Confluencia final {p.quality_score:.1f}/{p.activation_score:.1f} inferior a {min_quality:.1f}/{min_activation:.1f}')
            else:valid.append(p)
        from strategy_adaptation import candidate_decision,frame_features
        if not hasattr(self,'pending_adaptation_baseline'):self.pending_adaptation_baseline={}
        if not hasattr(self,'pending_adaptation_rejections'):self.pending_adaptation_rejections={}
        self.pending_adaptation_baseline[symbol]=list(valid)
        self.pending_adaptation_rejections[symbol]=[]
        fused=[]
        features=frame_features(self.caches[symbol].frames)
        for plan in valid:
            allowed,detail=candidate_decision(plan,features,self.research_context,self.g.clock())
            if allowed:fused.append(replace(plan,reason=plan.reason+' · '+detail) if detail else plan)
            else:
                self.pending_adaptation_rejections[symbol].append(plan)
                reject(plan,'learned_filter',detail)
        # V193: NO entregar un único candidato por cuadrante. Si el mejor técnico
        # falla por riesgo monetario, margen, stops/freeze o una regla puntual del
        # bróker, V171 no tenía segunda opción y el cuadrante quedaba vacío.
        # Conservamos varias zonas HTF reales del MISMO cuadrante para que el
        # Gateway pruebe, en la misma vuelta, la siguiente alternativa estructural.
        per_quadrant=max(1,min(6,int(self.cfg.get("execution",{}).get("pending_candidates_per_quadrant",3))))
        grouped={}
        for p in fused:
            # El transporte ocupa como máximo un slot por dirección, pero su
            # shortlist debe conservar alternativas LIMIT Y STOP para esa dirección.
            group=(int(p.side),str(p.kind)) if all_candidates else self.pending_slot(p.side,p.kind,p)
            grouped.setdefault(group,[]).append(p)
        chosen=[]
        for key,items in grouped.items():
            items=sorted(items,key=self._pending_priority,reverse=True)
            chosen.extend(items[:per_quadrant] if all_candidates else items[:1])
        diag["fused_candidates"]=len(fused)
        diag["returned_candidates"]=len(chosen)
        self.pending_filter_stats[symbol]=dict(diag)
        self.pending_filter_reasons[symbol]=reasons
        self.pending_candidate_audit[symbol]=sorted(audit,key=lambda x:(x['status'] not in ('QUALIFIED','SOFT_FALLBACK'),abs(x['distance'])))[:40]
        chosen=sorted(chosen,key=self._pending_priority,reverse=True)
        self.pending_cached_candidates[symbol]=(self.g.clock(),chosen)
        return chosen

    def pending_slot(self,side,kind,plan=None):
        """Slot estable del mapa. V205 permite dos zonas distintas del mismo
        cuadrante sin volver a llenar MT5 con duplicados casi idénticos."""
        if self.cfg.get("pending",{}).get("one_order_per_direction",True):
            return int(side)
        key=str((plan or {}).get('key','')) if isinstance(plan,dict) else str(getattr(plan,'key','') or '')
        tf=str((plan or {}).get('timeframe','')) if isinstance(plan,dict) else str(getattr(plan,'timeframe','') or '')
        source='TACTICAL' if key.startswith('MAP:') or tf in ('M5','M15','M30') else 'STRUCTURAL'
        if not self.cfg.get('pending',{}).get('multi_zone_structural_slots',False):
            return int(side),str(kind),source
        parts=key.split(':')
        zone='PRIMARY'
        try:
            if key.startswith('SWING:'):
                # FINAL optimizer appends :OPT<n>.  The stable slot belongs to
                # the structural CLUSTER just before OPT, not to the variant.
                # This lets several entry variants compete internally while two
                # genuinely different H1/H4 zones remain separate MT5 slots.
                candidate=parts[-2] if len(parts)>=2 and parts[-1].upper().startswith('OPT') else (parts[-1] if parts else '')
                zone=f"SWING:{candidate}" if candidate.isdigit() and int(candidate)<20 else 'SWING'
            elif key.startswith('MAP:') and len(parts)>3:
                zone=f"MAP:{parts[3]}"
            elif key.startswith('T:'):
                zone='TAPE'
        except Exception:
            zone='PRIMARY'
        # source queda al final para compatibilidad de diagnósticos/tests antiguos.
        return int(side),str(kind),zone,source

    def pending_order_slot(self,order):
        side=1 if int(order.type)%2==0 else -1
        kind="LIMIT" if int(order.type) in (BUY_LIMIT,SELL_LIMIT) else "STOP"
        metadata=self.g.journal.data.get('orders',{}).get(str(int(order.ticket)),{})
        return self.pending_slot(side,kind,metadata.get('plan') or {})
