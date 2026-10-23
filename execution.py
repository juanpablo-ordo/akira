"""Un único coordinador MT5 para pendientes y runners estructurales protegidos."""
from __future__ import annotations
from dataclasses import dataclass,replace,fields
from datetime import datetime,timezone,timedelta
from pathlib import Path
from types import SimpleNamespace
from collections import deque
import json,math,os,time,uuid
from strategy import Plan,Quote,normalize,symbol_strategy
from akira_version import BUILD_ID
from pending_portfolio import pending_overlap
from risk_reservations import reservation_ledger,reservation_reason,matching_objects

BUY,SELL,BUY_LIMIT,SELL_LIMIT,BUY_STOP,SELL_STOP=0,1,2,3,4,5
DEAL,PENDING,SLTP,MODIFY,REMOVE=1,5,6,7,8
DONE,PLACED,PARTIAL=10009,10008,10010
OWN_PENDING=170002
OWN_RUNNER=170003
# Historical ownership is recognized only for protected transition positions.
LEGACY_PENDING={169002,168002,167002,162002,161002,160002,159002,158002,157002,156002,155002,154002,153002,152002,151002,150002,149002,600002,600004}
LEGACY_POSITIONS={170001,170099,169001,169099,168001,168099,167001,167099,162001,162099,161001,161099,160001,160099,159001,159099,158001,158099,157001,157099,156001,156099,155001,155099,154001,154099,153001,153099,152001,152099,151001,151099,150001,149001,600001,600003,699999}
REJECTED={10004,10006,10007,10013,10014,10015,10016,10017,10018,10019,10020,10021,10022,10024,10025,10026,10027,10028,10029,10030,10032,10033,10034,10035,10036,10038,10039,10040,10041,10042,10043,10044,10045,10046}

class Blocked(Exception):pass

class BrokerRejected(Blocked):
    def __init__(self,code,comment):
        self.code=int(code)
        super().__init__(f'MT5 {self.code}: {comment}')

# Solo rechazos definitivos de geometría/tipo permiten probar otra pendiente.
# Timeout, falta de respuesta, bloqueo de servidor y estado incierto se concilian.
PENDING_ALTERNATIVE_REJECTIONS={10015,10016,10035}

class MarketPaused(Blocked):
    """La cotización dejó de avanzar: no es un fallo de estrategia ni de reloj.

    Nunca usar el último BID/ASK como si fuese precio ejecutable. MT5 exige
    otro tick después de la reapertura antes de crear/modificar órdenes.
    """
    pass

class Journal:
    def __init__(self,path: Path,read_only=False):
        self.path=path
        self.read_only=read_only
        self.data={"schema":1000,"intents":{},"orders":{},"positions":{},"used":{},"baskets":{},"equity":{},"adopted":{}}
        if path.exists():
            self.data=json.loads(path.read_text(encoding="utf-8"))
            if self.data.get("schema") not in (149,150,151,152,153,154,155,156,157,158,159,160,161,162,1000):
                raise ValueError("Estado incompatible. Restaure la copia de seguridad.")
            for key in ("intents","orders","positions","used"):
                if not isinstance(self.data.get(key),dict):
                    raise ValueError(f"Estado dañado: {key}. No se enviaron órdenes.")
            self.data.setdefault("baskets",{})
            self.data.setdefault("equity",{})
            self.data.setdefault("adopted",{})
            self.data["schema"]=1000

    def save(self):
        if self.read_only:
            return
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temp=self.path.with_suffix(".tmp")
        with temp.open("w",encoding="utf-8") as stream:
            json.dump(self.data,stream,ensure_ascii=False,indent=2,allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp,self.path)

class Reporter:
    def __init__(self,folder: Path,callback=None,console=True):
        folder.mkdir(parents=True,exist_ok=True)
        self.folder=folder
        self.last={}
        self.status={}
        self.callback,self.console=callback,console
        self.recent_events=deque(maxlen=300)

    def event(self,symbol,text,**values):
        row={"utc":datetime.now(timezone.utc).isoformat(),"symbol":symbol,"message":text,**values}
        if values.get('operation') or symbol=='ERROR':self.recent_events.append(row)
        if self.console:
            print(f"{row['utc'][11:19]} | {symbol} | {text}",flush=True)
        # Rotación diaria; no crecer indefinidamente en un único archivo.
        with (self.folder/f"eventos_{row['utc'][:10]}.jsonl").open("a",encoding="utf-8") as f:
            f.write(json.dumps(row,ensure_ascii=False,allow_nan=False,default=str)+"\n")
        if self.callback:
            self.callback(row)

    def report(self,symbol,state,detail,**values):
        row={"state":state,"detail":detail,**values}
        self.status[symbol]=row
        key=(symbol,state)
        before=self.last.get(key)
        now=time.monotonic()
        if before is None or now-before>=30:
            self.last[key]=now
            self.event(symbol,f"{state} | {detail}",**values)

    def dump(self):
        target=self.folder/"estado.json"
        temp=target.with_suffix(".tmp")
        temp.write_text(json.dumps(self.status,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
        os.replace(temp,target)

@dataclass
class Snapshot:
    account: object
    terminal: object
    positions: tuple
    orders: tuple

@dataclass
class Prepared:
    plan: Plan
    request: dict
    risk: float
    reward: float
    margin: float
    quote: Quote


def order_plan(order,metadata=None):
    """Use actual broker levels for exposure, not stale intended levels."""
    meta=metadata or {};side=1 if int(order.type)%2==0 else -1
    kind='LIMIT' if int(order.type) in (BUY_LIMIT,SELL_LIMIT) else 'STOP'
    data={f.name:meta[f.name] for f in fields(Plan) if f.name in meta}
    data.update(symbol=str(order.symbol),key=str(meta.get('key','BROKER:'+str(order.ticket))),
        side=side,lane='PENDING',kind=kind,entry=float(order.price_open),sl=float(order.sl),tp=float(order.tp),
        atr=float(meta.get('atr',0) or 0),score=float(meta.get('score',0) or 0),
        reason=str(meta.get('reason','Niveles vigentes en MT5')),
        bar_time=int(meta.get('bar_time',getattr(order,'time_setup',0)) or 0))
    return Plan(**data)


class Gateway:
    def __init__(self,api,cfg,journal,reporter,clock=time.time):
        self.api,self.cfg,self.journal,self.log,self.clock=api,cfg,journal,reporter,clock
        self.identity=None;self.cooldowns={};self.history=[];self.history_time=0.0
        self.history_error='historial sin cargar';self.last_order_send_ms={}
        self.pending_rejections=[];self.last_rejection={}
        self.runtime_execution_block=''
        self.account_currency=''
        from position_events import ClosureMonitor
        self.closure_monitor=ClosureMonitor(self)

    def record_pending_rejection(self,plan,code,comment):
        info=self.api.symbol_info(plan.symbol)
        step=float(info.trade_tick_size or info.point) if info else .00000001
        now=self.clock()
        self.pending_rejections=[r for r in self.pending_rejections if r['until']>now][-63:]
        self.pending_rejections.append({'symbol':plan.symbol,'side':plan.side,'kind':plan.kind,
            'levels':tuple(round(x/step) for x in (plan.entry,plan.sl,plan.tp)),'step':step,
            'until':now+float(self.cfg['execution'].get('pending_rejection_retry_seconds',15.0)),
            'detail':f'MT5 {code}: {comment}; probar otra zona'})

    def pending_rejection_reason(self,plan):
        now=self.clock()
        self.pending_rejections=[r for r in self.pending_rejections if r['until']>now]
        for r in self.pending_rejections:
            if (plan.symbol,plan.side,plan.kind)!=(r['symbol'],r['side'],r['kind']):continue
            normalized=normalize(plan,r['step'])
            if tuple(round(x/r['step']) for x in (normalized.entry,normalized.sl,normalized.tp))==r['levels']:
                return r['detail']
        return ''

    def owned_order(self,obj):
        magic=int(getattr(obj,'magic',0))
        return magic in (OWN_PENDING,OWN_RUNNER) or bool(self.cfg['manage_legacy_akira'] and magic in LEGACY_PENDING)

    def owned(self,obj):
        return self.owned_order(obj) or bool(hasattr(obj,'volume') and not hasattr(obj,'volume_current') and
            self.cfg['manage_legacy_akira'] and int(getattr(obj,'magic',0)) in LEGACY_POSITIONS)

    @staticmethod
    def fingerprint(obj,kind):
        from order_timing import broker_seconds
        return {'kind':kind,'ticket':int(obj.ticket),'symbol':str(obj.symbol),'magic':int(obj.magic),
                'type':int(obj.type),'entry':float(obj.price_open),'sl':float(obj.sl),'tp':float(obj.tp),
                'volume':float(obj.volume if kind=='position' else obj.volume_current),
                'time':broker_seconds(obj,kind)}

    def snapshot(self):
        a,t=self.api.account_info(),self.api.terminal_info()
        p,o=self.api.positions_get(),self.api.orders_get()
        if a is None or t is None or p is None or o is None:raise Blocked('MT5: estado incompleto')
        ident=(int(a.login),str(a.server))
        if self.identity is None:self.identity=ident
        if self.identity!=ident:raise Blocked('Cambió la cuenta MT5. En Ajustes → Operación pulsa Usar cuenta abierta en MT5 y vuelve a autorizarla.')
        saved=self.journal.data.get('account_identity')
        if saved is not None and tuple(saved)!=ident:raise Blocked('El diario pertenece a otra cuenta')
        if saved is None:self.journal.data['account_identity']=list(ident);self.journal.save()
        self.account_currency=str(getattr(a,'currency',''))
        return Snapshot(a,t,tuple(p),tuple(o))

    def valuation_call(self,evaluation,method,*args):
        # Una evaluación puede compartir llamadas idénticas. El envío abre una
        # evaluación NUEVA: nunca recibe la caché del selector/preparación.
        if evaluation is None:return getattr(self.api,method)(*args)
        key=(method,args)
        if key not in evaluation:evaluation[key]=getattr(self.api,method)(*args)
        return evaluation[key]

    def quote(self,symbol,evaluation=None):
        from market_calendar import state_for
        from datetime import datetime,timezone
        market=state_for(symbol,datetime.fromtimestamp(self.clock(),timezone.utc),self.cfg)
        if not market.open:
            raise MarketPaused('MERCADO CERRADO · '+market.state+'. Próxima apertura estimada: '+market.next_open_guatemala+'. MT5 confirma disponibilidad al reabrir.')
        t=self.valuation_call(evaluation,'symbol_info_tick',symbol)
        if t is None:raise MarketPaused(symbol+': esperando cotización nueva de MT5')
        ms=int(getattr(t,'time_msc',0)) or int(t.time)*1000
        q=Quote(float(t.bid),float(t.ask),ms/1000,ms)
        if not all(math.isfinite(x) for x in (q.bid,q.ask,q.time)) or q.bid<=0 or q.ask<q.bid:raise Blocked('Tick inválido')
        age=self.clock()-q.time
        if age< -5:raise Blocked(f'Reloj de Windows/MT5 desincronizado: tick {abs(age):.0f} s en el futuro')
        if age>self.cfg['strategy']['max_tick_age_seconds']:
            raise MarketPaused(f'Sin cotización nueva desde hace {age:.0f} s. '
                               'Posible pausa del mercado/rollover o conexión MT5; '
                               'no se envían órdenes con precios antiguos.')
        return q

    def reserve_quote(self,symbol,evaluation=None):
        """A closed secondary market must not prevent valuing its existing SL."""
        t=self.valuation_call(evaluation,'symbol_info_tick',symbol)
        if t is None:raise Blocked('Sin cotización para valorar exposición existente')
        bid,ask=float(t.bid),float(t.ask)
        if not math.isfinite(bid) or not math.isfinite(ask) or bid<=0 or ask<bid:
            raise Blocked('Cotización de reserva inválida')
        ms=int(getattr(t,'time_msc',0)) or int(t.time)*1000
        return Quote(bid,ask,ms/1000,ms)

    def permissions(self,snap,entry=True):
        a,t=snap.account,snap.terminal
        if self.runtime_execution_block:raise Blocked(self.runtime_execution_block)
        if self.cfg['mode']=='trade' and getattr(self,'requires_execution_lease',False) and not getattr(self,'execution_lease_active',False):raise Blocked('Activando operativa: esperando bloqueo exclusivo de la cuenta')
        if entry and getattr(self,'network_available',True) is False:raise Blocked('Sin Internet: nuevas entradas en pausa; reconexión automática pendiente')
        if self.cfg['mode']!='trade':raise Blocked('OBSERVAR: sin envíos ni modificaciones')
        if not getattr(t,'connected',False):raise Blocked('MT5 desconectado')
        if not getattr(t,'trade_allowed',False) or getattr(t,'tradeapi_disabled',False):raise Blocked('Activa Trading algorítmico y API Python en MT5')
        if not getattr(a,'trade_allowed',False) or not getattr(a,'trade_expert',False):raise Blocked('La cuenta no permite operaciones algorítmicas')
        if self.cfg['expected_login'] and int(a.login)!=self.cfg['expected_login']:raise Blocked('Cuenta diferente de expected_login')
        if self.cfg.get('expected_server') and str(a.server).casefold()!=self.cfg['expected_server'].casefold():raise Blocked('El servidor MT5 no coincide con la cuenta autorizada')
        if entry and (not math.isfinite(float(a.equity)) or float(a.equity)<=0):raise Blocked('Capital no válido')
        limits=[x for x in (float(self.cfg['risk'].get('daily_loss_money',0)),float(a.equity)*float(self.cfg['risk'].get('daily_loss_pct',0))/100) if x>0]
        if entry and limits:
            if self.history_error or not self.history_time or self.clock()-self.history_time>120:raise Blocked('Límite diario activo: esperando historial MT5 vigente')
            today=int(self.clock()//86400)*86400
            realized=sum(self.pnl(d) for d in self.history if float(d.time)>=today and int(d.type) in (0,1))
            if realized<=-min(limits):raise Blocked('Límite de pérdida neta diaria alcanzado; se conserva la gestión de posiciones existentes')

    def profit(self,symbol,side,volume,entry,exit,evaluation=None):
        x=self.valuation_call(evaluation,'order_calc_profit',BUY if side==1 else SELL,symbol,volume,entry,exit)
        if x is None or not math.isfinite(float(x)):raise Blocked('No se pudo calcular P/L real del símbolo')
        return float(x)

    @staticmethod
    def pnl(deal):
        return sum(float(getattr(deal,k,0) or 0) for k in ('profit','commission','swap','fee'))

    def refresh_history(self,now=None,force=False):
        now=self.clock() if now is None else now
        if not force and now-self.history_time<1.0:return self.history
        start=now-86400*90 if not self.history_time else self.history_time-10
        rows=self.api.history_deals_get(datetime.fromtimestamp(start,timezone.utc),datetime.fromtimestamp(now+1,timezone.utc))
        if rows is None:
            self.history_error='Historial MT5 no disponible; aprendizaje conserva último dato';return self.history
        by_id={int(d.ticket):d for d in self.history}
        by_id.update({int(d.ticket):d for d in rows})
        self.history=list(by_id.values());self.history_time=now;self.history_error=''
        return self.history

    def total_cap(self,snap):
        r=self.cfg['risk'];capital=max(0.0,min(float(snap.account.equity),float(snap.account.balance)))
        cap=capital*float(r['portfolio_capital_pct'])/100
        if float(r['portfolio_money_cap'])>0:cap=min(cap,float(r['portfolio_money_cap']))
        return cap

    def trade_cap(self,snap,*unused):
        r=self.cfg['risk']
        equity=float(snap.account.equity)
        base=min(float(r['max_trade_money']),equity*float(r['max_trade_pct'])/100)
        # SENTINEL: no subir el riesgo a escondidas. Este margen extra existe solo
        # si el usuario activa explícitamente la casilla de lote mínimo estructural.
        if not bool(r.get('min_lot_structural_override_enabled',False)):
            return base
        pct=float(r.get('min_lot_structural_override_max_pct',r['max_trade_pct']))
        money=float(r.get('min_lot_structural_override_money_cap',r['max_trade_money']))
        return max(base,min(money,equity*pct/100.0))

    def entry_cap(self,plan,snap):
        from runner_protection import entry_cap
        return entry_cap(self,plan,snap)

    def runner_protection(self,plan,snap):
        from runner_protection import decision
        return decision(self,plan,snap)

    def plan_money(self,plan,volume=None,q=None,evaluation=None):
        volume=self.cfg['lot'] if volume is None else float(volume);q=q or self.quote(plan.symbol,evaluation)
        info=self.valuation_call(evaluation,'symbol_info',plan.symbol)
        if info is None:raise Blocked('Sin symbol_info')
        step=float(info.trade_tick_size or info.point)
        fee=self.cfg['risk']['round_turn_commission_per_lot']*volume
        slip=max(q.spread*self.cfg['risk']['slippage_spread_fraction'],step*2)
        risk=max(0.0,-self.profit(plan.symbol,plan.side,volume,plan.entry,plan.sl-plan.side*slip,evaluation))+fee
        reward=self.profit(plan.symbol,plan.side,volume,plan.entry,plan.tp,evaluation)-fee
        return risk,reward

    def volume_for_plan(self,plan,snap=None,ignore_orders=(),boost=True,evaluation=None):
        """Dimensionar por SL real; más impulso nunca aumenta el presupuesto."""
        snap=snap or self.snapshot();info=self.valuation_call(evaluation,'symbol_info',plan.symbol)
        if info is None:raise Blocked('Sin symbol_info para dimensionar lote')
        # Dimensionar sobre los mismos ticks que validate_plan enviará. Evita
        # valorar dos veces niveles casi iguales y respeta el riesgo normalizado.
        if plan.lane=='PENDING':
            step=float(info.trade_tick_size or info.point)
            if not all(math.isfinite(float(x)) and float(x)>0 for x in (plan.entry,plan.sl,plan.tp,step)):
                raise Blocked('Plan o tick de precio no válido para dimensionar lote')
            plan=normalize(plan,step)
        sizing=self.cfg['sizing']
        if not sizing['enabled']:return float(self.cfg['lot'])
        step=float(info.volume_step)
        if step<=0:raise Blocked('Paso de volumen inválido')
        minimum=math.ceil((float(info.volume_min)-1e-10)/step)*step
        maximum=min(float(info.volume_max),float(sizing['max_lot']))
        ledger=self.reservation_ledger(snap,ignore_orders,evaluation)
        if ledger['available_usd']<=0:raise Blocked(self.reservation_reason(ledger))
        capacity=min(self.entry_cap(plan,snap),ledger['available_usd'])
        unit,_=self.plan_money(plan,minimum,evaluation=evaluation)
        if unit<=0:raise Blocked('Riesgo del lote mínimo no calculable')
        if unit>capacity+1e-9 or maximum<minimum-1e-9:
            raise Blocked(f'Lote mínimo {minimum:g}: riesgo {unit:.2f} > presupuesto disponible {capacity:.2f}; conservar parámetros, no acercar SL')
        qualifies=(float(plan.score)>=sizing['boost_score'] and float(plan.quality_score)>=sizing['boost_quality'])
        can_boost=boost and qualifies and ((plan.lane=='RUNNER' and self.cfg['runner'].get('allow_size_boost',False)) or (plan.lane=='PENDING' and sizing['scale_pending']))
        ceiling=maximum if can_boost else min(maximum,max(minimum,float(self.cfg['lot'])))
        fit=capacity/unit*minimum*(sizing['risk_utilization'] if can_boost else 1.0)
        volume=math.floor((min(ceiling,fit)+1e-10)/step)*step
        return round(max(minimum,volume),8)

    def funding_diagnostic(self,plan,snap,ignore_orders=(),evaluation=None):
        """Dinero del lote mínimo con SL intacto; no autoriza ninguna operación."""
        info=self.valuation_call(evaluation,'symbol_info',plan.symbol)
        if info is None or float(info.volume_step)<=0:raise Blocked('Volumen mínimo no calculable')
        step=float(info.volume_step)
        minimum=math.ceil((float(info.volume_min)-1e-10)/step)*step
        checked_volume=minimum if self.cfg['sizing']['enabled'] else float(self.cfg['lot'])
        risk,_=self.plan_money(plan,checked_volume,evaluation=evaluation)
        ledger=self.reservation_ledger(snap,ignore_orders,evaluation);available=ledger['available_usd']
        cap=self.entry_cap(plan,snap);capacity=min(cap,available)
        return {'broker_min_lot':round(minimum,8),'volume_step':step,'evaluated_lot':checked_volume,
                'minimum_risk_usd':round(risk,4),'trade_cap_usd':round(cap,4),
                'portfolio_available_usd':round(available,4),'available_usd':round(capacity,4),
                'minimum_fits':bool(0<risk<=capacity+1e-9),
                'portfolio_cap_usd':ledger['cap_usd'],'portfolio_reserved_usd':ledger['reserved_usd'],
                'portfolio_risk_known':ledger['risk_known'],
                'portfolio_blocker':self.reservation_reason(ledger) if available<=0 else ''}

    def reservation_ledger(self,snap,ignore_orders=(),evaluation=None):
        return reservation_ledger(self,snap,ignore_orders,evaluation)

    @staticmethod
    def reservation_reason(ledger):return reservation_reason(ledger)

    def exposure_risk(self,snap,ignore_orders=(),evaluation=None):
        return self.reservation_ledger(snap,ignore_orders,evaluation)['reserved_usd']

    def reserved_pending_margin(self,snap,ignore_orders=(),evaluation=None):
        return self.reservation_ledger(snap,ignore_orders,evaluation)['future_margin_usd']

    def validate_plan(self,plan,snap,ignore_orders=(),volume=None,editing=False,evaluation=None):
        if not hasattr(self,'verification_receipts'):self.verification_receipts={}
        row={'symbol':plan.symbol,'at':self.clock(),'key':plan.key,'broker_checked':False}
        self.verification_receipts[plan.key]=row
        while len(self.verification_receipts)>64:self.verification_receipts.pop(next(iter(self.verification_receipts)))
        try:
            result=self._validate_plan(plan,snap,ignore_orders,volume,editing,evaluation)
            p,q,risk,reward,margin=result
            row.update(risk_passed=True,risk_usd=risk,reward_usd=reward,margin=margin,volume=volume or self.cfg['lot'])
            return result
        except Blocked as exc:
            row.update(risk_passed=False,error=str(exc));raise

    def _validate_plan(self,plan,snap,ignore_orders=(),volume=None,editing=False,evaluation=None):
        # Caché estrictamente local cuando el caller no proporciona una. _send
        # mantiene su snapshot nuevo y calcula precios/dinero desde cero aquí.
        evaluation={} if evaluation is None else evaluation
        runner=plan.lane=='RUNNER' and plan.kind=='MARKET'
        if (not runner and (plan.lane!='PENDING' or plan.kind not in ('LIMIT','STOP'))) or plan.side not in (1,-1):raise Blocked('Solo pendientes LIMIT/STOP o runners estructurales')
        if runner:
            if self.cfg['execution'].get('pending_only',False):raise Blocked('Entradas exclusivamente pendientes; los runners se gestionan tras activarse una pendiente')
            rules=self.cfg['runner']
            protection=self.runner_protection(plan,snap)
            if not protection['allowed']:raise Blocked(protection['reason'])
            if not rules['enabled'] or not plan.key.startswith('RUN:'):raise Blocked('Entrada a mercado sin tesis runner autorizada')
            if plan.score<rules['min_score'] or plan.quality_score<rules['min_quality']:raise Blocked('Runner sin confirmación técnica suficiente')
            if plan.key in self.journal.data.get('runner_entries',{}):raise Blocked('Este runner ya se solicitó; esperar nueva vela/tesis')
            if any(p.symbol==plan.symbol for p in snap.positions):raise Blocked('Runner: ya existe una posición en este símbolo')
            if any(o.symbol==plan.symbol and self.owned_order(o) and int(o.ticket) not in ignore_orders for o in snap.orders):raise Blocked('Runner: retirar y confirmar pendientes propias antes de entrar')
        if not self.cfg['symbols'].get(plan.symbol,False):raise Blocked('Símbolo desactivado')
        volume=self.cfg['lot'] if volume is None else float(volume)
        if not all(math.isfinite(float(x)) and float(x)>0 for x in (plan.entry,plan.sl,plan.tp,volume)):raise Blocked('Plan con valores no válidos')
        if volume>self.cfg['sizing']['max_lot']+1e-9:raise Blocked('Volumen supera el máximo configurado')
        if int(getattr(snap.account,'margin_mode',2))!=2 and any(p.symbol==plan.symbol for p in snap.positions):raise Blocked('Cuenta netting con posición: no se añade exposición combinada')
        info=self.valuation_call(evaluation,'symbol_info',plan.symbol);q=self.quote(plan.symbol,evaluation)
        if info is None:raise Blocked('Símbolo no encontrado')
        if not hasattr(self,'broker_terms'):self.broker_terms={}
        self.broker_terms[plan.symbol]={k:getattr(info,k,None) for k in ('volume_min','volume_step','volume_max','trade_stops_level','trade_freeze_level','trade_tick_size','trade_contract_size')}
        if int(info.trade_mode) in (0,3) or (int(info.trade_mode)==1 and plan.side==-1) or (int(info.trade_mode)==2 and plan.side==1):raise Blocked('El símbolo no permite esa dirección')
        step=float(info.trade_tick_size or info.point);vstep=float(info.volume_step)
        if vstep<=0 or volume<float(info.volume_min)-1e-9 or volume>float(info.volume_max)+1e-9 or abs(volume/vstep-round(volume/vstep))>1e-6:raise Blocked('Volumen no permitido por el bróker')
        if runner:
            plan=replace(plan,entry=q.ask if plan.side==1 else q.bid,trigger=plan.trigger or plan.entry)
        plan=normalize(plan,step)
        minimum=max(float(info.trade_stops_level)*float(info.point),step)
        if editing:minimum=max(minimum,float(info.trade_freeze_level)*float(info.point))
        side=plan.side;ref=q.ask if side==1 else q.bid
        distance=side*(ref-plan.entry) if plan.kind=='LIMIT' else side*(plan.entry-ref)
        distances=[side*(plan.entry-plan.sl),side*(plan.tp-plan.entry)]
        if not runner:distances.append(distance)
        else:
            distances.extend((side*((q.bid if side==1 else q.ask)-plan.sl),side*(plan.tp-(q.bid if side==1 else q.ask))))
            tf=plan.signal_timeframe
            if tf not in ('M5','M15'):raise Blocked('Runner: temporalidad de confirmación inválida')
            if tf=='M5' and not self.cfg['runner'].get('allow_m5_retest',True):raise Blocked('Retest M5 desactivado')
            period=300 if tf=='M5' else 900
            max_age=self.cfg['runner'].get('m5_signal_max_age_seconds',300) if tf=='M5' else self.cfg['runner']['max_signal_age_seconds']
            age=self.clock()-(plan.bar_time+period)
            if age< -2 or age>max_age:raise Blocked('Runner: señal '+tf+' caducada o aún no cerrada')
            drift_atr=plan.signal_atr if tf=='M5' else plan.atr
            if not math.isfinite(drift_atr) or drift_atr<=0:raise Blocked('Runner: ATR de confirmación inválido')
            if abs(ref-float(plan.trigger or plan.entry))>drift_atr*self.cfg['runner']['max_entry_drift_atr']:raise Blocked('Runner: precio fuera de la ventana de entrada')
        if min(distances)<minimum-1e-9:raise Blocked('Entrada/SL/TP no cumplen geometría o stops/freeze')
        cfg=symbol_strategy(self.cfg,plan.symbol)
        if q.spread/max(side*(plan.entry-plan.sl),1e-9)>cfg['max_spread_risk_fraction']:raise Blocked('Spread excesivo para esta zona')
        flag=1 if runner else 2 if plan.kind=='LIMIT' else 4
        if int(info.order_mode)&(flag|16|32)!=(flag|16|32):raise Blocked('Bróker no permite este tipo con SL y TP')
        for o in snap.orders:
            if int(o.ticket) in ignore_orders or o.symbol!=plan.symbol:continue
            old=order_plan(o)
            gap=max(plan.atr,old.atr,step)*float(self.cfg['pending']['duplicate_guard_atr'])
            if old.side==plan.side and (pending_overlap(plan,old) or abs(plan.entry-old.entry)<gap):raise Blocked('Zona duplicada o superpuesta con una pendiente existente')
        for position in snap.positions:
            if position.symbol!=plan.symbol or not self.owned_order(position):continue
            meta=self.journal.data['positions'].get(str(position.ticket),{})
            original=meta.get('plan') or {}
            side=1 if int(position.type)==BUY else -1
            if side!=plan.side:raise Blocked('Posición propia activa: no preparar exposición opuesta')
            old=Plan(position.symbol,str(original.get('key','FILLED:'+str(position.ticket))),side,'PENDING','LIMIT',
                float(position.price_open),float(original.get('sl',position.sl) or position.sl),
                float(original.get('tp',position.tp) or position.tp),float(original.get('atr',plan.atr) or plan.atr),
                0.0,'Zona activada vigente',0)
            if side==plan.side and (old.key==plan.key or pending_overlap(plan,old)):
                raise Blocked('Esa tesis ya está activada en una posición; no duplicar la misma exposición')
        own=[o for o in snap.orders if o.symbol==plan.symbol and int(o.ticket) not in ignore_orders and self.owned_order(o)]
        if not runner and (len(own)>=self.cfg['pending']['max_own_map_orders'] or sum((1 if int(o.type)%2==0 else -1)==plan.side for o in own)>=self.cfg['pending']['max_same_side_orders']):raise Blocked('Mapa de este símbolo completo')
        risk,reward=self.plan_money(plan,volume,q,evaluation)
        if risk<=0 or risk>self.entry_cap(plan,snap)+1e-9:raise Blocked(f'Riesgo de operación {risk:.2f} supera límite estructural {self.entry_cap(plan,snap):.2f}')
        if reward/risk<float(cfg['pending_hard_min_rr']):raise Blocked(f'R:R neto {reward/risk:.2f} insuficiente')
        total=self.exposure_risk(snap,ignore_orders,evaluation)+risk
        if total>self.total_cap(snap)+1e-9:raise Blocked(f'Riesgo conjunto {total:.2f} supera {self.total_cap(snap):.2f}')
        margin=self.valuation_call(evaluation,'order_calc_margin',BUY if side==1 else SELL,plan.symbol,volume,plan.entry)
        if margin is None or not math.isfinite(float(margin)) or margin<0:raise Blocked('Margen no calculable')
        future=self.reserved_pending_margin(snap,ignore_orders,evaluation)+float(margin)
        projected=float(snap.account.margin)+future
        if future>float(snap.account.margin_free) or (projected>0 and float(snap.account.equity)/projected*100<self.cfg['risk']['minimum_margin_level_pct']):raise Blocked('Margen proyectado insuficiente incluyendo todas las pendientes')
        return plan,q,risk,reward,float(margin)

    def pending_time_fields(self,info,ttl=0):
        modes=int(getattr(info,'expiration_mode',1) or 1)
        if ttl and modes&4:return {'type_time':2,'expiration':int(self.clock()+ttl)}
        if modes&1:return {'type_time':0,'expiration':0}
        if modes&2:return {'type_time':1,'expiration':0}
        if modes&4:return {'type_time':2,'expiration':int(self.clock()+86400)}
        if modes&8:return {'type_time':3,'expiration':int(self.clock()+86400)}
        raise Blocked('Bróker sin modo de expiración compatible')

    def check(self,request,plan=None):
        r=self.api.order_check(request)
        if r is None:raise Blocked('order_check sin respuesta; no se envió la solicitud')
        code=int(r.retcode)
        if code!=0:
            comment='order_check: '+str(getattr(r,'comment','rechazo'))
            self.last_rejection[str(request.get('symbol',''))]=f'MT5 {code}: {comment}'
            if plan is not None and plan.lane=='PENDING' and int(request.get('action',-1))==PENDING and code in PENDING_ALTERNATIVE_REJECTIONS:
                self.record_pending_rejection(plan,code,comment)
            elif plan is not None and int(request.get('action',-1))==PENDING:
                self.cooldowns[plan.symbol]=self.clock()+(10 if code in (10017,10018,10024,10026,10027) else 2)
            raise BrokerRejected(code,comment)
        if plan is not None and plan.key in getattr(self,'verification_receipts',{}):
            self.verification_receipts[plan.key].update(broker_checked=True,broker_checked_at=self.clock(),broker_request={k:request.get(k) for k in ('action','type','price','sl','tp','volume')})

    def prepare(self,plan,ignore_orders=()):
        if plan.lane!='PENDING':raise Blocked('Preparación pendiente requiere LIMIT/STOP')
        rejected=self.pending_rejection_reason(plan)
        if rejected:raise Blocked(rejected)
        snap=self.snapshot();self.permissions(snap)
        if plan.symbol in self.journal.data['intents']:raise Blocked('Solicitud pendiente de confirmación; no se duplica')
        # Evaluación local de ESTA preparación. _send toma otra foto y vuelve a
        # validar directamente antes de order_send; no reutiliza este dict.
        evaluation={}
        volume=self.volume_for_plan(plan,snap,ignore_orders,evaluation=evaluation)
        p,q,risk,reward,margin=self.validate_plan(plan,snap,ignore_orders,volume=volume,evaluation=evaluation)
        typ=(BUY_LIMIT if p.side==1 else SELL_LIMIT) if p.kind=='LIMIT' else (BUY_STOP if p.side==1 else SELL_STOP)
        req={'action':PENDING,'symbol':p.symbol,'volume':volume,'type':typ,'price':p.entry,
             'sl':p.sl,'tp':p.tp,'magic':OWN_PENDING,'comment':'AKP-11-'+uuid.uuid4().hex[:10],'type_filling':2}
        req.update(self.pending_time_fields(self.valuation_call(evaluation,'symbol_info',p.symbol),self.cfg['pending']['ttl_seconds']))
        self.check(req,p)
        if p.key in getattr(self,'verification_receipts',{}):self.verification_receipts[p.key]['broker_checked']=True
        return Prepared(p,req,risk,reward,margin,q)

    def pending_budget_status(self,plan,snap=None,ignore_orders=(),evaluation=None):
        try:
            if self.runtime_execution_block:raise Blocked(self.runtime_execution_block)
            rejected=self.pending_rejection_reason(plan)
            if rejected:raise Blocked(rejected)
            snap=snap or self.snapshot()
            own=[o for o in snap.orders if o.symbol==plan.symbol and int(o.ticket) not in ignore_orders and self.owned_order(o)]
            if len(own)>=self.cfg['pending']['max_own_map_orders'] or sum((1 if int(o.type)%2==0 else -1)==plan.side for o in own)>=self.cfg['pending']['max_same_side_orders']:
                raise Blocked('Mapa de este símbolo completo para esa dirección')
            volume=self.volume_for_plan(plan,snap,ignore_orders,evaluation=evaluation)
            p,q,risk,reward,margin=self.validate_plan(plan,snap,ignore_orders,volume=volume,evaluation=evaluation)
            return True,'Cumple riesgo, margen y geometría',risk
        except Blocked as e:return False,str(e),0.0

    def send(self,prepared):
        # Re-prepare once with the latest quote and book just before sending.
        p=self.prepare(prepared.plan)
        return self._send(p.plan.symbol,p.request,'open',p.plan,risk=p.risk,reward=p.reward,margin=p.margin)

    def send_immediate_plan(self,plan):
        if plan.lane!='PENDING':raise Blocked('Este canal solo recibe pendientes LIMIT/STOP')
        p=self.prepare(plan)
        return self._send(plan.symbol,p.request,'open',p.plan,risk=p.risk,reward=p.reward,margin=p.margin)

    def market_fields(self,symbol,side):
        info=self.api.symbol_info(symbol);q=self.quote(symbol)
        filling=int(getattr(info,'filling_mode',0))
        mode=1 if filling&2 else 0 if filling&1 else 2
        if int(getattr(info,'trade_exemode',2))==2 and mode==2:raise Blocked('Market Execution sin IOC/FOK compatible')
        fields={'type_filling':mode,'deviation':int(self.cfg['runner']['deviation_points'])}
        if int(getattr(info,'trade_exemode',2))!=2:fields['price']=q.ask if side==1 else q.bid
        return fields

    def send_runner(self,plan):
        if plan.lane!='RUNNER' or plan.kind!='MARKET':raise Blocked('Se requiere una tesis runner')
        snap=self.snapshot();self.permissions(snap)
        evaluation={}
        volume=self.volume_for_plan(plan,snap,evaluation=evaluation)
        p,q,risk,reward,margin=self.validate_plan(plan,snap,volume=volume,evaluation=evaluation)
        req={'action':DEAL,'symbol':p.symbol,'volume':volume,'type':BUY if p.side==1 else SELL,
             'sl':p.sl,'tp':p.tp,'magic':OWN_RUNNER,'comment':'AKR-134-'+uuid.uuid4().hex[:10]}
        req.update(self.market_fields(p.symbol,p.side))
        return self._send(p.symbol,req,'open',p,risk=risk,reward=reward,margin=margin)

    def managed_runner(self,position):
        if int(position.magic)==OWN_RUNNER:return True
        plan=(self.journal.data['positions'].get(str(position.ticket)) or {}).get('plan') or {}
        return bool(int(position.magic)==OWN_PENDING and plan.get('lane')=='PENDING' and self.cfg['management'].get('pending_fills_as_runners',False))

    def close_runner(self,position,reason):
        snap=self.snapshot();self.permissions(snap,entry=False)
        p=next((x for x in snap.positions if int(x.ticket)==int(position.ticket)),None)
        if p is None:return False
        if not self.managed_runner(p):raise Blocked('Cierre runner: ticket manual/externo o de otra estrategia')
        side=-1 if int(p.type)==BUY else 1
        req={'action':DEAL,'symbol':p.symbol,'position':int(p.ticket),'volume':float(p.volume),
             'type':BUY if side==1 else SELL,'magic':int(p.magic),'comment':'AKR-162-exit'}
        req.update(self.market_fields(p.symbol,side))
        return self._send(p.symbol,req,'close',reason=reason,before=self.fingerprint(p,'position'),before_volume=float(p.volume))

    def live_order(self,order):
        snap=self.snapshot();self.permissions(snap,entry=False)
        found=next((o for o in snap.orders if int(o.ticket)==int(order.ticket)),None)
        if found is None:raise Blocked('La pendiente se activó o desapareció; volver a analizar')
        if not self.owned_order(found):raise Blocked('Pendiente manual/externa: no se modifica')
        if self.fingerprint(found,'order')!=self.fingerprint(order,'order'):raise Blocked('La pendiente cambió; volver a consultar')
        return found,snap

    def cancel(self,order,reason):
        live,snap=self.live_order(order);q=self.quote(live.symbol);info=self.api.symbol_info(live.symbol)
        ref=q.ask if int(live.type)%2==0 else q.bid
        if abs(ref-float(live.price_open))<float(info.trade_freeze_level)*float(info.point):raise Blocked('Pendiente dentro de freeze; esperar confirmación MT5')
        req={'action':REMOVE,'order':int(live.ticket),'symbol':live.symbol,'magic':int(live.magic),'comment':'AKP-10-cancel'}
        self.check(req)
        original=order_plan(live,(self.journal.data['orders'].get(str(live.ticket)) or {}).get('plan'))
        risk,_=self.plan_money(original,float(live.volume_current),q)
        margin=self.api.order_calc_margin(BUY if original.side==1 else SELL,live.symbol,float(live.volume_current),original.entry)
        if margin is None or not math.isfinite(float(margin)):raise Blocked('Margen de reserva no calculable')
        return self._send(live.symbol,req,'cancel',reason=reason,risk=risk,margin=float(margin),before=self.fingerprint(live,'order'))

    def pending_parameters_unchanged(self, live, request):
        """Skip an MT5 10025 no-op, comparing effective tick-normalized levels.

        No execution/risk shortcut: a real price/SL/TP change still passes all
        normal gateway checks and order_check before any order_send.
        """
        info=self.api.symbol_info(live.symbol)
        tick=float(getattr(info,'trade_tick_size',0) or getattr(info,'point',0) or 0.00000001)
        if not math.isfinite(tick) or tick<=0:tick=0.00000001
        tolerance=max(tick*0.25,1e-9)
        for old,new in (('price_open','price'),('sl','sl'),('tp','tp')):
            if abs(float(getattr(live,old))-float(request[new]))>tolerance:
                return False
        # A change in expiry is not a no-op.
        if hasattr(live,'type_time') and 'type_time' in request:
            if int(live.type_time)!=int(request['type_time']):return False
        if int(request.get('type_time',0)) in (2,3) and hasattr(live,'time_expiration'):
            if int(getattr(live,'time_expiration',0))!=int(request.get('expiration',0)):return False
        return True

    def modify_pending(self,order,plan,reason):
        live,snap=self.live_order(order);self.permissions(snap)
        side=1 if int(live.type)%2==0 else -1;kind='LIMIT' if int(live.type) in (2,3) else 'STOP'
        if plan.symbol!=live.symbol or plan.side!=side or plan.kind!=kind:raise Blocked('Edición no puede cambiar símbolo/lado/tipo')
        p,q,risk,reward,margin=self.validate_plan(plan,snap,(int(live.ticket),),float(live.volume_current),editing=True)
        req={'action':MODIFY,'order':int(live.ticket),'symbol':live.symbol,'price':p.entry,'sl':p.sl,'tp':p.tp,
             'magic':int(live.magic),'comment':'AKP-10-modify'}
        req.update(self.pending_time_fields(self.api.symbol_info(live.symbol),self.cfg['pending']['ttl_seconds']))
        if self.pending_parameters_unchanged(live,req):
            return None  # AL DÍA, not an MT5 rejection
        return self._send(live.symbol,req,'modify_order',p,risk=risk,reward=reward,margin=margin,reason=reason,before=self.fingerprint(live,'order'))

    def update_stop(self,position,sl,tp=None,reason='protección estructural',allow_restore=False):
        snap=self.snapshot();self.permissions(snap,entry=False)
        p=next((x for x in snap.positions if int(x.ticket)==int(position.ticket)),None)
        if p is None:return False
        if not self.owned(p):raise Blocked('Posición manual/externa: no se modifica')
        if self.fingerprint(p,'position')!=self.fingerprint(position,'position'):raise Blocked('Posición cambió antes de proteger')
        side=1 if int(p.type)==BUY else -1
        target_only=float(sl)==float(p.sl) and tp is not None and float(p.tp)>0 and side*(float(tp)-float(p.tp))>0 and self.cfg['management'].get('extend_targets',False) and self.managed_runner(p)
        if float(p.sl)>0 and side*(float(sl)-float(p.sl))<=0 and not target_only:return False
        if float(p.sl)<=0 and not allow_restore:raise Blocked('Restauración necesita invalidación original registrada')
        q=self.quote(p.symbol);info=self.api.symbol_info(p.symbol);ref=q.bid if side==1 else q.ask
        step=float(info.trade_tick_size or info.point);minimum=max(info.trade_stops_level,info.trade_freeze_level)*info.point+step
        sl=round(float(sl)/step)*step;tp=float(p.tp) if tp is None else round(float(tp)/step)*step
        if side*(ref-sl)<minimum or (tp and side*(tp-ref)<minimum):raise Blocked('Protección dentro de stops/freeze')
        req={'action':SLTP,'symbol':p.symbol,'position':int(p.ticket),'sl':sl,'tp':tp,'magic':int(p.magic),'comment':'AKP-10-protect'}
        self.check(req)
        return self._send(p.symbol,req,'protect',reason=reason,before=self.fingerprint(p,'position'))

    def _send(self,symbol,request,operation,plan=None,**meta):
        if symbol in self.journal.data['intents']:raise Blocked('Esperando confirmación del servidor en '+symbol)
        if self.clock()<self.cooldowns.get(symbol,0):raise Blocked('Bróker rechazó: espera de reintento')
        snap=self.snapshot();self.permissions(snap,entry=operation in ('open','modify_order'))
        action=int(request.get('action',-1))
        if operation=='open':
            if plan is None or action!=(DEAL if plan.lane=='RUNNER' else PENDING):raise Blocked('Solicitud de entrada sin vía estructural válida')
            p,q,risk,reward,margin=self.validate_plan(plan,snap,volume=float(request.get('volume',0)))
            if (request.get('sl'),request.get('tp'))!=(p.sl,p.tp) or (plan.lane=='PENDING' and request.get('price')!=p.entry):raise Blocked('Solicitud no coincide con el plan normalizado')
            if int(request.get('type',-1))!=(BUY if p.side==1 else SELL) and plan.lane=='RUNNER':raise Blocked('Dirección runner no coincide con su tesis')
            if p.lane=='PENDING':
                expected_type=(BUY_LIMIT if p.side==1 else SELL_LIMIT) if p.kind=='LIMIT' else (BUY_STOP if p.side==1 else SELL_STOP)
                if int(request.get('type',-1))!=expected_type:raise Blocked('Tipo de pendiente no coincide con su tesis')
            if int(request.get('magic',0))!=(OWN_RUNNER if p.lane=='RUNNER' else OWN_PENDING):raise Blocked('Identidad de estrategia inválida')
            plan=p
            meta.update(risk=risk,reward=reward,margin=margin)
            guard=getattr(self,'entry_quality_guard',None)
            if guard:guard(plan,snap)
        else:
            order_op=operation in ('cancel','modify_order');field='order' if order_op else 'position'
            pool=snap.orders if order_op else snap.positions
            found=next((x for x in pool if int(x.ticket)==int(request.get(field,0))),None)
            if found is None:return False
            if not (self.owned_order(found) if order_op else self.owned(found)):raise Blocked('Ticket externo')
            if self.fingerprint(found,'order' if order_op else 'position')!=meta.get('before'):raise Blocked('Ticket cambió antes de order_send')
            if operation=='modify_order' and plan is not None:
                guard=getattr(self,'entry_quality_guard',None)
                if guard:guard(plan,snap)
            expected={'cancel':REMOVE,'modify_order':MODIFY,'protect':SLTP,'close':DEAL}
            if expected.get(operation)!=action:raise Blocked('Operación no autorizada por el motor de pendientes')
            if operation=='modify_order':
                self.validate_plan(plan,snap,(int(found.ticket),),float(found.volume_current),editing=True)
            if operation=='protect' and float(found.sl)>0:
                side=1 if int(found.type)==BUY else -1
                equal_sl=abs(float(request['sl'])-float(found.sl))<1e-8
                target_only=equal_sl and float(found.tp)>0 and side*(float(request.get('tp',0))-float(found.tp))>0 and self.cfg['management'].get('extend_targets',False) and self.managed_runner(found)
                if side*(float(request['sl'])-float(found.sl))<=0 and not target_only:raise Blocked('Nunca ampliar un SL existente')
            if operation=='close':
                if not self.managed_runner(found) or float(request.get('volume',0))!=float(found.volume) or int(request.get('type',-1))==int(found.type):raise Blocked('Cierre runner inválido')
        if operation in ('open','modify_order') and plan is not None and plan.lane=='PENDING' and getattr(self,'pending_review_guard',None):
            self.pending_review_guard(plan,snap,float(request.get('volume',0)) if operation=='open' else float(found.volume_current),
                int(request.get('order',0)) if operation=='modify_order' else 0)
        if operation=='modify_order' and self.pending_parameters_unchanged(found,request):
            return None
        self.check(request,plan)
        if operation in ('protect','close'):
            position_meta=self.journal.data['positions'].get(str(request.get('position',0)),{})
            meta['rr_at_request']=position_meta.get('last_rr')
        intent={'operation':operation,'request':dict(request),'created':self.clock(),'retcode':None,
                'plan':plan.to_dict() if plan else None,'build':BUILD_ID,**meta}
        self.journal.data['intents'][symbol]=intent
        if plan is not None and plan.lane=='RUNNER':
            self.journal.data.setdefault('runner_entries',{})[plan.key]=self.clock()
        self.journal.save()
        started=time.perf_counter();result=None
        try:result=self.api.order_send(request)
        except Exception as e:intent['error']=type(e).__name__+': '+str(e)
        self.last_order_send_ms[symbol]=(time.perf_counter()-started)*1000
        code=int(result.retcode) if result is not None else None
        intent.update(retcode=code,order=int(getattr(result,'order',0) or 0),deal=int(getattr(result,'deal',0) or 0))
        if code in REJECTED and not (code==10036 and operation in ('cancel','modify_order')):
            self.journal.data['intents'].pop(symbol,None)
            if plan is not None and plan.lane=='RUNNER':self.journal.data.get('runner_entries',{}).pop(plan.key,None)
            comment=str(getattr(result,'comment','rechazo'))
            self.last_rejection[symbol]=f'MT5 {code}: {comment}'
            if operation=='open' and plan is not None and plan.lane=='PENDING' and code in PENDING_ALTERNATIVE_REJECTIONS:
                self.record_pending_rejection(plan,code,comment)
            else:self.cooldowns[symbol]=self.clock()+(10 if code in (10018,10024,10017,10026,10027) else 2)
            self.log.event(symbol,'RECHAZO MT5 '+str(code),operation=operation,reason=str(getattr(result,'comment','')))
        else:self.log.event(symbol,'ACEPTADA; verificar MT5' if code in (DONE,PLACED,PARTIAL) else 'SIN CONFIRMACIÓN; no se duplica',operation=operation,request=request,
            retcode=code,order=intent['order'],deal=intent['deal'],reason=meta.get('reason',''),
            lane=plan.lane if plan else None,rr_at_request=meta.get('rr_at_request'),
            risk_usd=meta.get('risk'),reward_usd=meta.get('reward'))
        self.journal.save()
        return code in (DONE,PLACED,PARTIAL)

    def reconcile(self,snap):
        dirty=False
        for symbol,i in list(self.journal.data['intents'].items()):
            req=i.get('request') or {};op=i.get('operation');resolved=False
            if op=='open':
                order_id=int(i.get('order',0) or 0);comment=str(req.get('comment',''))
                matched=matching_objects(self,snap,symbol,i)
                orders=[obj for kind,obj in matched if kind=='pending']
                positions=[obj for kind,obj in matched if kind=='position']
                for o in orders:
                    from order_timing import broker_seconds
                    self.journal.data['orders'][str(o.ticket)]={'plan':i.get('plan'),'created':i['created'],
                        'broker_setup_at':broker_seconds(o,'order'),'last_modify':i['created']}
                for p in positions:self.register_position(p,i.get('plan'),requested_at=i['created'],order_ticket=i.get('order'))
                expected_volume=float(req.get('volume',0) or 0)
                visible_volume=sum(float(o.volume_current) for o in orders)+sum(float(p.volume) for p in positions)
                resolved=bool(orders or positions) and expected_volume>0 and visible_volume>=expected_volume-1e-9
                if not resolved and self.clock()-float(i.get('last_lookup',0))>=2:
                    i['last_lookup']=self.clock()
                    rows=self.api.history_orders_get(ticket=order_id) if order_id else self.api.history_orders_get(datetime.fromtimestamp(i['created']-5,timezone.utc),datetime.fromtimestamp(self.clock()+1,timezone.utc))
                    for o in rows or ():
                        matching_id=int(o.ticket)==order_id if order_id else bool(comment and str(getattr(o,'comment',''))==comment)
                        if o.symbol!=symbol or not matching_id:continue
                        if int(o.state) in (2,5,6):resolved=True
                        if int(o.state)==4:
                            pid=int(getattr(o,'position_id',0))
                            if pid and any(p.symbol==symbol and int(getattr(p,'identifier',p.ticket))==pid for p in snap.positions):
                                resolved=True
                            deals=self.api.history_deals_get(position=pid) if pid and not resolved else None
                            if deals:
                                ins=sum(float(d.volume) for d in deals if int(d.entry)==0)
                                outs=sum(float(d.volume) for d in deals if int(d.entry) in (1,3))
                                resolved=ins>0 and outs>=ins-1e-9
                # Empty or unavailable history does not prove an unknown send failed.
            elif op in ('cancel','modify_order'):
                o=next((o for o in snap.orders if int(o.ticket)==int(req['order'])),None)
                resolved=o is not None and op=='modify_order' and all(abs(float(getattr(o,k))-float(req[v]))<1e-8 for k,v in (('price_open','price'),('sl','sl'),('tp','tp')))
                if o is None:
                    if op=='cancel' and i.get('retcode')==DONE:resolved=True
                    else:
                        history=self.api.history_orders_get(ticket=int(req['order']))
                        for old in history or ():
                            if int(old.ticket)!=int(req['order']):continue
                            if int(old.state) in (2,5,6):resolved=True
                            if int(old.state)==4:
                                pid=int(getattr(old,'position_id',0))
                                visible=any(int(getattr(p,'identifier',p.ticket))==pid for p in snap.positions)
                                deals=self.api.history_deals_get(position=pid) if pid and not visible else None
                                ins=sum(float(d.volume) for d in deals or () if int(d.entry)==0)
                                outs=sum(float(d.volume) for d in deals or () if int(d.entry) in (1,3))
                                if visible or (ins>0 and outs>=ins-1e-9):resolved=True
                if resolved and o is not None:
                    previous=self.journal.data['orders'].get(str(o.ticket),{})
                    zones=list(previous.get('recent_zones',[]))
                    before=i.get('before') or {};old_plan=previous.get('plan') or {};new_plan=i.get('plan') or {}
                    horizon=max(float(old_plan.get('horizon_atr',0) or 0),float(new_plan.get('horizon_atr',0) or 0),float(new_plan.get('atr',0) or 0),1e-9)
                    if abs(float(new_plan.get('entry',o.price_open))-float(before.get('entry',o.price_open)))>=horizon*.5:
                        zones.append({'entry':float(before['entry']),'horizon_atr':horizon,
                            'bar_time':int(old_plan.get('bar_time',0)),'quality_score':float(old_plan.get('quality_score',0)),
                            'abandoned_at':self.clock()})
                    self.journal.data['orders'][str(o.ticket)]={**previous,'plan':i['plan'],
                        'created':previous.get('created',i['created']),'last_modify':self.clock(),'recent_zones':zones[-6:]}
            elif op in ('protect','ticket_stop','structural_stop','target','close'):
                p=next((p for p in snap.positions if int(p.ticket)==int(req.get('position',0))),None)
                if op=='close':resolved=p is None or float(p.volume)<float(i.get('before_volume',0))-1e-9
                else:resolved=p is None or (abs(float(p.sl)-float(req.get('sl',p.sl)))<1e-8 and abs(float(p.tp)-float(req.get('tp',p.tp)))<1e-8)
            if resolved:
                if op in ('protect','close'):
                    ticket=str(req.get('position',0));row=self.journal.data['positions'].get(ticket)
                    if row is not None:
                        changes=list(row.get('management_events',[]))
                        changes.append({'time':self.clock(),'operation':op,'reason':i.get('reason',''),
                            'requested_at':i.get('created'),'deal':i.get('deal'),'order':i.get('order'),
                            'request_comment':req.get('comment'),
                            'old_sl':(i.get('before') or {}).get('sl'),'new_sl':req.get('sl'),
                            'rr_at_request':i.get('rr_at_request'),'retcode':i.get('retcode')})
                        row['management_events']=changes[-100:]
                        if op=='protect':
                            row['protection_state']='Protección confirmada en MT5' if p is not None else 'Posición cerrada; revisar el cierre confirmado por MT5'
                self.journal.data['intents'].pop(symbol,None)
                self.log.event(symbol,'CONFIRMADO '+str(op),operation='confirmed_'+str(op),
                    request=req,reason=i.get('reason',''),retcode=i.get('retcode'),
                    ticket=req.get('position') or req.get('order') or i.get('order'))
                dirty=True
            else:self.log.report(symbol,'RECONCILIANDO','Solicitud sin evidencia final MT5; nuevas órdenes de este símbolo en espera')
        for p in snap.positions:
            if self.owned(p) and str(p.ticket) not in self.journal.data['positions']:
                meta=self.journal.data['orders'].get(str(getattr(p,'identifier',p.ticket)),{})
                self.register_position(p,meta.get('plan'));dirty=True
        # Retain historical order plans: fills and learning can arrive later.
        active={str(p.ticket) for p in snap.positions}
        for k,row in self.journal.data['positions'].items():
            if k not in active and not row.get('closed_observed_at'):row['closed_observed_at']=self.clock();dirty=True
        if dirty:self.journal.save()

    def register_position(self,p,plan,requested_at=None,order_ticket=None):
        from order_timing import broker_seconds
        linked=self.journal.data['orders'].get(str(getattr(p,'identifier',p.ticket))) or {}
        self.journal.data['positions'].setdefault(str(p.ticket),{'entry':float(p.price_open),
            'initial_sl':float(p.sl) or float((plan or {}).get('sl',0) or 0),'time':float(getattr(p,'time',self.clock())),
            'opened_at':broker_seconds(p),'requested_at':requested_at or linked.get('created'),
            'order_ticket':order_ticket or (getattr(p,'identifier',p.ticket) if linked else None),
            'plan':plan,'symbol':str(p.symbol),'side':1 if int(p.type)==BUY else -1,'volume':float(p.volume),
            'lane':'RUNNER' if int(getattr(p,'magic',0))==OWN_RUNNER else 'PENDING',
            'identifier':int(getattr(p,'identifier',p.ticket)),'magic':int(getattr(p,'magic',0)),
            'last_modify':0.0,'entry_fees_per_lot':0.0})
