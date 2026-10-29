"""Indicadores y zonas observadas para pendientes BTC/oro."""
from __future__ import annotations
from collections import Counter
from dataclasses import asdict, dataclass, replace,field
import math
from typing import Iterable
from indicators import enrich,context_vote

@dataclass(frozen=True)
class Bar:
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 1.0

    def to_dict(self):
        # Hojas escalares de una vela inmutable: no necesitan la recursión de
        # asdict/deepcopy para cada punto del gráfico y del informe.
        return {'time':self.time,'open':self.open,'high':self.high,'low':self.low,
                'close':self.close,'volume':self.volume}

@dataclass(frozen=True)
class Quote:
    bid: float
    ask: float
    time: float
    sequence: int

    @property
    def spread(self):
        return self.ask - self.bid

def quote_identity(quote):
    """MT5 may publish distinct Bid/Ask values with the same time_msc."""
    return (getattr(quote, 'sequence', None), float(quote.bid), float(quote.ask))

@dataclass(frozen=True)
class Frame:
    name: str
    bars: tuple[Bar, ...]
    atr: float
    fast: float
    slow: float
    trend: float
    volume_ratio: float
    lows: tuple[tuple[float, int], ...]
    highs: tuple[tuple[float, int], ...]
    rsi: float
    macd_hist: float
    band_mid: float
    band_low: float
    band_high: float
    regime: str
    extra: dict=field(default_factory=dict)

@dataclass(frozen=True)
class Setup:
    key: str
    side: int                 # +1 BUY, -1 SELL
    lane: str                 # PENDING
    kind: str                 # LIMIT / STOP
    level: float              # nivel del gráfico BID; no precio final de orden
    stop: float               # invalidación del gráfico BID
    target: float             # objetivo del gráfico BID
    atr: float
    score: float
    created_bar: int
    reason: str
    timeframe: str="M1"
    horizon_atr: float=0.0

@dataclass(frozen=True)
class Plan:
    symbol: str
    key: str
    side: int
    lane: str
    kind: str
    entry: float
    sl: float
    tp: float
    atr: float
    score: float
    reason: str
    bar_time: int
    trigger: float = 0.0
    horizon_atr: float = 0.0
    # V193 separa "que se active pronto" de "que tenga buena geometría".
    # No son probabilidades estadísticas; son puntuaciones comparables 0..100.
    activation_score: float = 0.0
    quality_score: float = 0.0
    # V193: métricas EMPÍRICAS de operaciones reales Akira. -1 = sin muestra suficiente.
    empirical_win_rate: float = -1.0
    empirical_samples: int = 0
    empirical_expectancy: float = 0.0
    learning_features: tuple = ()
    learning_feature_version: str = ''
    signal_timeframe: str = 'M15'
    signal_atr: float = 0.0
    selection_adjustment: float = 0.0
    selection_feature_version: str = ''
    selection_features: tuple = ()
    strategy_id: str = ''
    strategy_version: int = 1
    selector_id: str = ''
    selector_version: int = 0
    execution_build: str = ''
    base_quality_score: float | None = None
    base_activation_score: float | None = None

    @property
    def rr(self):
        return self.side * (self.tp-self.entry) / max(self.side*(self.entry-self.sl), 1e-12)

    def to_dict(self):
        return asdict(self)

def ema(values: Iterable[float], period: int) -> float:
    it = iter(values)
    value = next(it)
    alpha = 2.0/(period+1)
    for number in it:
        value += alpha*(number-value)
    return value

def ema_series(values,period):
    value=values[0]
    result=[value]
    for number in values[1:]:
        value+=2/(period+1)*(number-value)
        result.append(value)
    return result

def rsi_wilder(closes,period=14):
    changes=[b-a for a,b in zip(closes[:-1],closes[1:])]
    gain=sum(max(x,0) for x in changes[:period])/period
    loss=sum(max(-x,0) for x in changes[:period])/period
    for delta in changes[period:]:
        gain=(gain*(period-1)+max(delta,0))/period
        loss=(loss*(period-1)+max(-delta,0))/period
    if loss==0:
        return 50.0 if gain==0 else 100.0
    return 100-100/(1+gain/loss)

def symbol_strategy(cfg,symbol):
    return {**cfg["strategy"],**cfg.get("symbol_profiles",{}).get(symbol,{})}

def frame(name: str, rows: Iterable[Bar]) -> Frame:
    bars = tuple(rows)
    if len(bars) < 60:
        raise ValueError(f"{name}: {len(bars)}/60 velas cerradas")
    for i, b in enumerate(bars):
        if not all(math.isfinite(v) and v > 0 for v in (b.open,b.high,b.low,b.close)):
            raise ValueError(f"{name}: precio inválido")
        if b.low > min(b.open,b.close) or b.high < max(b.open,b.close) or b.low > b.high:
            raise ValueError(f"{name}: OHLC incoherente")
        if i and b.time <= bars[i-1].time:
            raise ValueError(f"{name}: tiempos desordenados")
    closes = [b.close for b in bars]
    true_ranges = [max(b.high-b.low, abs(b.high-a.close), abs(b.low-a.close))
                   for a,b in zip(bars[:-1],bars[1:])]
    atr = sum(true_ranges[-14:])/14
    if atr <= 0:
        raise ValueError(f"{name}: volatilidad nula")
    fast, slow = ema(closes,9), ema(closes,21)
    slope = (slow-ema(closes[:-3],21))/atr
    trend = max(-1.0,min(1.0, (fast-slow)/atr*1.3+slope))
    mean_vol = sum(b.volume for b in bars[-21:-1])/20
    volume_ratio = bars[-1].volume/max(mean_vol,1)
    lows, highs = [], []
    for i in range(max(2,len(bars)-90),len(bars)-2):
        left,right = bars[i-2:i],bars[i+1:i+3]
        b=bars[i]
        if b.low < min(x.low for x in left) and b.low <= min(x.low for x in right):
            lows.append((b.low,b.time))
        if b.high > max(x.high for x in left) and b.high >= max(x.high for x in right):
            highs.append((b.high,b.time))
    macd=[a-b for a,b in zip(ema_series(closes,12),ema_series(closes,26))]
    macd_hist=macd[-1]-ema(macd,9)
    mid=sum(closes[-20:])/20
    std=math.sqrt(sum((c-mid)**2 for c in closes[-20:])/20)
    path=sum(abs(b-a) for a,b in zip(closes[-15:-1],closes[-14:]))
    efficiency=abs(closes[-1]-closes[-15])/max(path,1e-9)
    if true_ranges[-1]>atr*3:
        regime="EXPANSIÓN BRUSCA"
    elif abs(trend)>.25 and efficiency>.32:
        regime="TENDENCIA"
    else:
        regime="RANGO"
    return Frame(name,bars,atr,fast,slow,trend,volume_ratio,tuple(lows),tuple(highs),
                 rsi_wilder(closes),macd_hist,mid,mid-2*std,mid+2*std,regime,enrich(bars,atr))

def direction_context(frames: dict[str,Frame], side: int) -> tuple[float,str]:
    # M1/M5 deciden la entrada. El contexto mayor aporta, sin exigir unanimidad.
    weights = {"M1":3.5,"M5":6.0,"M15":3.5,"H1":3.0,"H4":2.6,"D1":1.8,"W1":.6}
    value=sum(f.trend*side*weights[k] for k,f in frames.items() if k in weights)
    label=", ".join(f"{k} {'↑' if f.trend>0.12 else '↓' if f.trend<-.12 else 'rango'}"
                    for k,f in frames.items())
    return value,label

def structural_target(frames: dict[str,Frame], side: int, entry: float, stop: float,
                      atr: float, lane: str, ignore_level: float | None = None):
    """No elude el obstáculo cercano para inventar un RR mayor."""
    levels=[]
    names=("M5","M15","H1","H4")
    for name in names:
        f=frames.get(name)
        if not f:
            continue
        candidates=f.highs if side==1 else f.lows
        for price,_ in candidates[-20:]:
            # Un nivel ya roto no se considera resistencia/soporte por delante.
            if side*(price-entry)>max(atr*.12,1e-9):
                if ignore_level is None or abs(price-ignore_level)>atr*.1:
                    levels.append(price)
    if levels:
        level=min(levels,key=lambda p:side*(p-entry))
        return level-side*atr*.06,"objetivo: siguiente swing"
    # Proyección explícita cuando no hay swing por delante en el historial usado.
    distance=max(abs(entry-stop)*1.85,atr*1.4)
    return entry+side*distance,"objetivo: proyección de riesgo (sin swing por delante)"

def pending_context(frames: dict[str,Frame], side: int) -> tuple[float,str]:
    """Sesgo de pendientes FUTURAS: M15/H1/H4 mandan; M1 solo afina precio.

    No intenta adivinar la siguiente vela. Busca zonas estructurales que todavía
    están por delante del precio y les da más peso cuando varios marcos coinciden.
    """
    weights={"M5":.5,"M15":1.5,"H1":5.0,"H4":6.0,"D1":4.0,"W1":1.0}
    value=0.0; labels=[]
    for name,w in weights.items():
        f=frames.get(name)
        if not f: continue
        value+=f.trend*side*w
        ex=f.extra
        if ex.get("bos")==side: value+=1.4
        if ex.get("sweep")==side: value+=.8
        if side*(f.bars[-1].close-ex.get("ema50",f.bars[-1].close))>0: value+=.35
        if side*(ex.get("ema50",0)-ex.get("ema200",0))>0: value+=.45
        labels.append(f"{name} {'↑' if f.trend>.12 else '↓' if f.trend<-.12 else 'rango'}")
    return value,", ".join(labels)

def _quantile(values, q=0.75):
    rows=sorted(float(x) for x in values if math.isfinite(float(x)) and float(x)>=0)
    if not rows:return 0.0
    q=max(0.0,min(1.0,float(q)))
    pos=(len(rows)-1)*q
    lo=int(math.floor(pos));hi=min(len(rows)-1,lo+1);frac=pos-lo
    return rows[lo]*(1-frac)+rows[hi]*frac

def _wick_noise_floor(frames: dict[str,Frame], side: int, timeframes=None) -> float:
    """Ruido de mecha observado que una invalidación debe sobrevivir.

    Usa M5/M15/H1 y el lado relevante de la vela. No intenta predecir dirección;
    solo evita colocar SL dentro del tamaño habitual de una barrida reciente.
    """
    samples=[]
    weights=(("M5",1.0),("M15",1.15),("H1",1.25)) if timeframes is None else tuple((name,1.0) for name in timeframes)
    for name,weight in weights:
        f=frames.get(name)
        if not f:continue
        for b in f.bars[-36:]:
            wick=(min(b.open,b.close)-b.low) if side==1 else (b.high-max(b.open,b.close))
            if wick>=0:samples.append(wick*weight)
    return _quantile(samples,.75)

def _refine_pending_stop(frames: dict[str,Frame], side: int, level: float,
                         fallback: float, source_atr: float, rules: dict | None=None) -> tuple[float,str]:
    """Afina una zona HTF con invalidación real M5/M15 cuando existe.

    Esto evita el error de usar un SL H1 enorme *o* inventar un SL estrecho. Solo
    se elige un swing observado que esté detrás de la zona de entrada.
    """
    m1=frames["M1"]
    rules=rules or {}
    # V12.1 QUALITY-FIRST: el SL debe sobrevivir no solo ATR, también el tamaño
    # observado de mechas. Si 0.01 lote no puede pagar esa invalidación real, la
    # pendiente se rechaza más adelante; NUNCA comprimimos el stop para hacerla caber.
    wick_floor=_wick_noise_floor(frames,side)
    wick_mult=float(rules.get("pending_wick_clearance_mult",1.25))
    min_risk=max(
        m1.atr*float(rules.get("pending_stop_min_m1_atr",1.8)),
        source_atr*max(.45,float(rules.get("pending_stop_min_source_atr",.55))),
        wick_floor*max(1.0,wick_mult),
    )
    choices=[]
    # Una pendiente H1/H4 necesita una invalidación detrás de un swing de su
    # horizonte. M5/M15 solo afinan cuando ya dejan el mismo colchón estructural.
    for name in ("H1","H4","M15","M5"):
        f=frames.get(name)
        if not f: continue
        rows=f.lows if side==1 else f.highs
        for price,stamp in rows[-20:]:
            behind=side*(level-price)
            if behind>max(m1.atr*.12,1e-9) and behind<=max(source_atr*1.1,f.atr*2.2):
                choices.append((behind,price,name,stamp))
    if side*(level-fallback)>max(m1.atr*.10,1e-9):
        choices.append((side*(level-fallback),fallback,"TF",0))
    if not choices:
        # Fallback sigue siendo estructural: detrás de la zona, nunca se estrecha
        # para hacer que el riesgo "quepa".
        stop=level-side*min_risk
        return stop,f"invalidación: colchón estructural + ruido de mechas (mecha75 {wick_floor:.3f})"
    buffer=max(
        m1.atr*.22,
        source_atr*float(rules.get("pending_liquidity_buffer_source_atr",.14)),
        wick_floor*.65,
    )
    # Elegir el swing MÁS CERCANO que todavía deje una invalidación con espacio
    # estructural suficiente. Si ninguno lo logra, ampliar detrás de la zona en
    # vez de conservar un stop microscópico.
    viable=[x for x in choices if x[0]+buffer>=min_risk]
    if viable:
        structural=[x for x in viable if x[2] in ("H1","H4")] if source_atr>frames.get('M15',m1).atr else []
        _,anchor,name,_=min(structural or viable,key=lambda x:x[0])
        stop=anchor-side*buffer
        return stop,f"invalidación: swing {name} + colchón de liquidez (mecha75 {wick_floor:.3f})"
    stop=level-side*min_risk
    return stop,f"invalidación: piso HTF + ruido de mechas (mecha75 {wick_floor:.3f})"

def build_v184_swing_pendings(frames: dict[str,Frame], rules: dict, rejected: Counter) -> list[Setup]:
    """Pendientes V193: SOLO tesis estructural H1/H4, refinada con M15.

    M1/M5 nunca crean una pendiente. M15 puede afinar el precio/SL dentro de una
    zona H1/H4, pero la tesis, invalidación y objetivo siguen siendo swing.
    """
    if "M1" not in frames or "M15" not in frames or "H1" not in frames:
        rejected["pendiente swing esperando M15/H1"] += 1
        return []
    m1=frames["M1"]; m15=frames["M15"]; current=m1.bars[-1].close; now=m1.bars[-1].time
    out=[]

    def future(side,level): return side*(current-level)
    def refine_entry(side,level,source_atr):
        candidates=[(abs(level-m15.slow),m15.slow,"EMA21 M15"),
                    (abs(level-float(m15.extra.get("ema50",m15.slow))),float(m15.extra.get("ema50",m15.slow)),"EMA50 M15")]
        rows=m15.lows if side==1 else m15.highs
        for price,_ in rows[-14:]: candidates.append((abs(level-price),price,"swing M15"))
        cap=max(source_atr*.20,m15.atr*.65)
        valid=[x for x in candidates if x[0]<=cap and future(side,x[1])>max(m1.atr*.8,m15.atr*.16)]
        if valid:
            _,value,label=min(valid,key=lambda x:x[0]); return value,label
        return level,"nivel HTF"

    def target_for(side,entry,stop):
        risk=side*(entry-stop)
        levels=[]
        for name in ("H1","H4","D1"):
            f=frames.get(name)
            if not f: continue
            rows=f.highs if side==1 else f.lows
            for price,_ in rows[-30:]:
                d=side*(price-entry)
                if d>=max(risk*2.30,f.atr*.30): levels.append((d,price,name))
        if levels:
            _,price,name=min(levels,key=lambda x:x[0]); return price-side*m1.atr*.08,f"target swing {name}"
        return entry+side*max(risk*2.80,frames["H1"].atr*.60),"objetivo proyectado 2.8R (sin swing observado)"

    for side in (1,-1):
        pctx,ptext=pending_context(frames,side)
        h1,h4,d1=frames.get("H1"),frames.get("H4"),frames.get("D1")
        htf_rows=[(h1,.34),(h4,.41),(d1,.25)]
        htf_total=sum(w for f,w in htf_rows if f is not None)
        htf_bias=sum(side*float(f.trend)*w for f,w in htf_rows if f is not None)/max(htf_total,1e-9)
        htf_opp=sum(1 for f,_w in htf_rows if f is not None and side*float(f.trend)<-.45)
        candidates=[]
        for name,weight in (("H1",9.0),("H4",11.0)):
            f=frames.get(name)
            if not f: continue
            floor=max(m1.atr*1.8,f.atr*float(rules.get("pending_min_source_atr",.14)))
            rows=f.lows if side==1 else f.highs
            for idx,(level,stamp) in enumerate(rows[-24:]):
                dist=future(side,level)
                if dist<=floor: continue
                later=[b for b in f.bars if b.time>stamp]
                # Closed-through invalidates the level. Repeated retests consume
                # liquidity and make a nearby level progressively less attractive.
                if any(side*(b.close-level)<-f.atr*.08 for b in later): continue
                touches=sum(1 for b in later if b.low<=level+f.atr*.06 and b.high>=level-f.atr*.06)
                if touches>=2: continue
                if later:
                    impulse=(max(b.high for b in later)-level) if side==1 else (level-min(b.low for b in later))
                    if impulse<f.atr*.55: continue
                con=0
                for value in (f.slow,float(f.extra.get("ema50",f.slow)),float(f.extra.get("fib50",level)),float(f.extra.get("fib618",level))):
                    if abs(value-level)<=f.atr*.20: con+=1
                score=72+weight+min(7.0,con*1.5)+max(-4.0,min(5.0,side*f.trend*5.0))+(idx+1)/24*2-touches*3.0
                if f.extra.get("sweep")==side: score+=2.5
                if f.extra.get("bos")==side: score+=2.0
                candidates.append((score,level,stamp,name,f,"swing HTF"))
            # order block before displacement
            for i in range(max(2,len(f.bars)-40),len(f.bars)):
                a,b=f.bars[i-1],f.bars[i]
                if side*(a.close-a.open)<0 and side*(b.close-b.open)>f.atr*.70:
                    level=(a.high if side==1 else a.low)
                    after=f.bars[i+1:]
                    mitigated=any(x.low<=level+f.atr*.06 and x.high>=level-f.atr*.06 for x in after)
                    if future(side,level)>floor and not mitigated:
                        candidates.append((80+weight+max(0,side*f.trend*4),level,a.time,name,f,"order block HTF no mitigado"))
            # EMA/Fib no son tesis por sí solas. V12.1 los usa solo si el usuario
            # habilita explícitamente el fallback; por defecto no rellenan el mapa.
            if bool(rules.get("pending_dynamic_structural_fallback",False)):
                for label,value in (("EMA21",f.slow),("EMA50",float(f.extra.get("ema50",f.slow))),
                                    ("FIB50",float(f.extra.get("fib50",f.slow))),
                                    ("FIB62",float(f.extra.get("fib618",f.slow)))):
                    if future(side,value)>floor:
                        candidates.append((68+weight+max(-2,side*f.trend*3),value,f.bars[-1].time,name,f,f"{label} HTF fallback"))

        # cluster nearby H1/H4 levels; confluence improves quality, never narrows SL artificially
        clusters=[]
        for row in sorted(candidates,key=lambda x:x[0],reverse=True):
            _,level,_,_,f,_=row
            tol=max(f.atr*.16,m15.atr*.55)
            found=None
            for c in clusters:
                if abs(c['center']-level)<=tol: found=c; break
            if found:
                found['rows'].append(row); found['center']=sum(x[1] for x in found['rows'])/len(found['rows'])
            else: clusters.append({'center':level,'rows':[row]})
        ranked=[]
        for c in clusters:
            best=max(c['rows'],key=lambda x:x[0]); score,level,stamp,name,f,label=best
            refined,refinewhy=refine_entry(side,c['center'],f.atr)
            # FINAL PENDING OPTIMIZER: en vez de convertir una zona en un único
            # número, conserva varias ENTRADAS estructurales observadas dentro del
            # mismo cluster HTF. Cada variante recalcula SL/TP desde estructura; no
            # mueve Entry para 'hacer caber' presupuesto ni fabrica RR.
            variants=[(refined,refinewhy)]
            if bool(rules.get('final_pending_optimizer',True)):
                variants.append((float(c['center']),'centro cluster HTF'))
                variants.append((float(level),f'nivel {name} dominante'))
                # Una confluencia M15 real dentro del cluster puede ser mejor fill.
                for _dist,_value,_why in sorted([(abs(float(c['center'])-float(m15.slow)),float(m15.slow),'EMA21 M15'),
                                                  (abs(float(c['center'])-float((m15.extra or {}).get('ema50',m15.slow))),float((m15.extra or {}).get('ema50',m15.slow)),'EMA50 M15')],key=lambda x:x[0]):
                    if _dist<=max(f.atr*.20,m15.atr*.65): variants.append((_value,_why))
            uniq=[]
            for v,whyv in variants:
                if not math.isfinite(v): continue
                if any(abs(v-u[0])<=max(m1.atr*.10,f.atr*.015) for u in uniq): continue
                uniq.append((v,whyv))
            confluence=len(c['rows'])
            for variant_idx,(entry,entrywhy) in enumerate(uniq[:4]):
                if future(side,entry)<=max(m1.atr*1.25,f.atr*float(rules.get('pending_min_source_atr',.14))): continue
                fallback=entry-side*max(f.atr*.32,m15.atr*.80)
                stop,stopwhy=_refine_pending_stop(frames,side,entry,fallback,f.atr,rules)
                risk=side*(entry-stop)
                if risk<=max(m1.atr*.45,1e-9): continue
                target,targetwhy=target_for(side,entry,stop)
                rr=side*(target-entry)/max(risk,1e-9)
                if rr<2.20: continue
                # Precision bonus is small: the later FINAL meta-edge still ranks
                # activation/EV. Structure remains the dominant source of quality.
                precision=max(0.0,1.8-abs(entry-float(c['center']))/max(f.atr,1e-9)*4.0)
                total=score+min(8.0,(confluence-1)*2.0)+max(-3.0,min(4.0,pctx*.35))+max(-7.0,min(5.0,htf_bias*6.0))-(3.5 if htf_opp>=2 else 0.0)+precision
                reason=(f"PENDIENTE FINAL OPT · {name} {label}; variante {variant_idx+1}/{len(uniq[:4])} {entrywhy}; confluencias HTF {confluence}; "
                        f"{ptext}; HTF H1/H4/D1 {htf_bias:+.2f}; {stopwhy}; {targetwhy}; RR {rr:.2f}; niveles nacen de estructura")
                ranked.append((total,Setup(f"SWING:L:{side}:{name}:{stamp}:{len(ranked)}:OPT{variant_idx}",side,"PENDING","LIMIT",
                                          entry,stop,target,m1.atr,total,now,reason,name,f.atr)))

        # Conservar zonas confluentes Y las estructurales cercanas. Antes las
        # cuatro de mayor score podían estar muy lejos; entonces la puerta de
        # activación rechazaba todas aunque hubiera una H1 cercana en ranked.
        # La cercanía solo añade alternativas: Engine/Gateway no relajan filtros.
        strongest=sorted(ranked,key=lambda x:x[0],reverse=True)[:4]
        nearby_floor=float(rules.get("pending_nearby_min_raw_score",84.0))
        nearby=sorted([x for x in ranked if float(x[1].score)>=nearby_floor],
                      key=lambda x:future(side,x[1].level)/max(x[1].horizon_atr,m1.atr))[:4]
        seen=set()
        for _,setup in strongest+nearby:
            if setup.key not in seen:
                out.append(setup); seen.add(setup.key)
        if not ranked: rejected[f"sin zona swing H1/H4 {'BUY' if side==1 else 'SELL'}"]+=1

        # Conditional breakout: H1 structure only, with H4/D1 not strongly opposite.
        h1=frames.get('H1'); h4=frames.get('H4')
        if h1:
            recent=h1.bars[-10:]; width=max(b.high for b in recent)-min(b.low for b in recent)
            if width<=h1.atr*4.8 and not (h4 and side*h4.trend<-.55) and not (d1 and side*d1.trend<-.55):
                boundary=max(b.high for b in recent) if side==1 else min(b.low for b in recent)
                level=boundary+side*max(m1.atr*.8,h1.atr*.035)
                if (side*(level-current)>max(m1.atr*1.2,h1.atr*.08)):
                    base=(min(b.low for b in recent) if side==1 else max(b.high for b in recent))
                    stop,stopwhy=_refine_pending_stop(frames,side,level,base,h1.atr,rules)
                    risk=side*(level-stop)
                    if risk>0:
                        target,targetwhy=target_for(side,level,stop)
                        rr=side*(target-level)/risk
                        if rr>=2.20:
                            score=76+max(-4,min(5,pctx*.4))+max(0,side*h1.trend*4)
                            out.append(Setup(f"SWING:S:{side}:H1:{h1.bars[-1].time}",side,"PENDING","STOP",
                                             level,stop,target,m1.atr,score,now,
                                             f"PENDIENTE BREAKOUT V193 · ruptura H1; {ptext}; {stopwhy}; {targetwhy}; RR {rr:.2f}",
                                             "H1",h1.atr))
    return out

def build_presence_reserve_pendings(frames: dict[str,Frame], rules: dict, rejected: Counter) -> list[Setup]:
    """Reserva HTF para V12.3 ALWAYS-ON.

    Solo se usa cuando el mapa estricto no cubre un lado. Nace de swings H1/H4
    observados, nunca de EMA/Fib aislados. Su objetivo es que Akira mantenga un
    mapa futuro útil y revisable sin inventar niveles ni acercar el SL al precio.
    Gateway/riesgo/margen siguen siendo obligatorios antes de enviar.
    """
    if not bool(rules.get('presence_structural_reserve',True)):
        return []
    if not all(k in frames for k in ('M1','M15','H1')):
        return []
    m1,m15,h1=frames['M1'],frames['M15'],frames['H1']
    current=float(m1.bars[-1].close); now=int(m1.bars[-1].time)
    out=[]
    def future(side,level): return side*(current-float(level))
    def target(side,entry,stop):
        risk=side*(entry-stop); levels=[]
        for name in ('H1','H4','D1'):
            f=frames.get(name)
            if not f: continue
            rows=f.highs if side==1 else f.lows
            for price,_stamp in rows[-36:]:
                distance=side*(float(price)-entry)
                if distance>=max(risk*1.55,f.atr*.18): levels.append((distance,float(price),name))
        if levels:
            _d,price,name=min(levels,key=lambda x:x[0])
            return price-side*m1.atr*.08,f'PRESENCE target swing {name} observado'
        return entry+side*max(risk*2.0,h1.atr*.55),'PRESENCE target proyectado 2R por falta de swing opuesto'
    for side in (1,-1):
        candidates=[]
        for name,base_score in (('H1',79.0),('H4',82.0)):
            f=frames.get(name)
            if not f: continue
            rows=f.lows if side==1 else f.highs
            floor=max(m1.atr*1.25,f.atr*.055)
            for idx,(level,stamp) in enumerate(rows[-36:]):
                level=float(level);dist=future(side,level)
                if dist<=floor: continue
                later=[b for b in f.bars if b.time>stamp]
                if any(side*(float(b.close)-level)<-f.atr*.16 for b in later): continue
                touches=sum(1 for b in later if float(b.low)<=level+f.atr*.08 and float(b.high)>=level-f.atr*.08)
                if touches>=4: continue
                recency=(idx+1)/max(1,len(rows[-36:]))
                con=0
                other=frames.get('H4' if name=='H1' else 'H1')
                if other:
                    orows=other.lows if side==1 else other.highs
                    if any(abs(float(p)-level)<=max(f.atr*.20,other.atr*.10) for p,_ in orows[-20:]): con+=1
                score=base_score+min(4.0,con*2.0)+recency*2.0-touches*1.2+max(-3.0,min(3.0,side*f.trend*3.0))
                candidates.append((score,dist,level,stamp,name,f,touches))
        # Closest valid HTF zones activate sooner; quality score breaks ties.
        for rank,row in enumerate(sorted(candidates,key=lambda x:(x[1],-x[0]))[:3],1):
            score,dist,level,stamp,name,f,touches=row
            entry=level
            buffer=max(f.atr*.58,m15.atr*1.00,m1.atr*3.2)
            # Put invalidation outside the structural level and observed wick noise.
            stop=entry-side*buffer
            risk=side*(entry-stop)
            if risk<=0: continue
            tp,twhy=target(side,entry,stop)
            rr=side*(tp-entry)/risk
            if rr<1.35:
                tp=entry+side*risk*1.65; rr=1.65; twhy='PRESENCE target mínimo 1.65R'
            reason=(f'PRESENCE RESERVE V12.3 · swing {name} observado; retests {touches}; '
                    f'invalidación fuera de zona {buffer/max(f.atr,1e-9):.2f} ATR-{name}; {twhy}; RR {rr:.2f}; '
                    'solo se usa para cubrir un lado faltante y queda bajo control continuo')
            out.append(Setup(f'SWING:PRESENCE:L:{side}:{name}:{stamp}:{rank}',side,'PENDING','LIMIT',
                             entry,stop,tp,m1.atr,score,now,reason,name,f.atr))
    if not out: rejected['sin reserva HTF de presencia']+=1
    return out

def build_fast_future_map_pendings(frames: dict[str,Frame], rules: dict, rejected: Counter) -> list[Setup]:
    """V12.4 REFLEX: mapa futuro rápido de respaldo con estructura observada.

    No reemplaza el motor QUALITY-FIRST. Solo existe para evitar que Akira se quede
    sin mapa cuando los filtros A/A+ no encuentran una zona perfecta. Construye
    LIMIT y STOP desde swings reales M15/H1/H4, mantiene SL detrás de estructura y
    deja al Planner/Gateway decidir presupuesto, margen y geometría final.
    """
    if not all(k in frames for k in ('M1','M15','H1')):
        rejected['fast-map esperando M1/M15/H1'] += 1
        return []
    m1,m15,h1=frames['M1'],frames['M15'],frames['H1']
    h4=frames.get('H4')
    current=float(m1.bars[-1].close); now=int(m1.bars[-1].time)
    out=[]

    def future_limit(side,level):
        return side*(current-float(level))

    def future_stop(side,level):
        return side*(float(level)-current)

    def observed_target(side,entry,stop,minimum_rr=1.55):
        risk=side*(entry-stop)
        levels=[]
        for name in ('M15','H1','H4','D1'):
            f=frames.get(name)
            if not f: continue
            rows=f.highs if side==1 else f.lows
            for price,_stamp in rows[-40:]:
                d=side*(float(price)-entry)
                if d>=max(risk*minimum_rr,f.atr*.15,m1.atr*.8):
                    levels.append((d,float(price),name))
        if levels:
            _d,price,name=min(levels,key=lambda x:x[0])
            return price-side*m1.atr*.06,f'FAST target swing {name} observado'
        rr=max(1.70,float(rules.get('fast_map_projected_rr',1.85)))
        return entry+side*risk*rr,f'FAST target proyectado {rr:.2f}R por falta de swing opuesto'

    for side in (1,-1):
        # -------- LIMIT: retorno a la zona estructural futura más útil --------
        zones=[]
        for name,base in (('H1',86.0),('H4',89.0),('M15',79.0)):
            f=frames.get(name)
            if not f: continue
            rows=f.lows if side==1 else f.highs
            min_dist=max(m1.atr*1.0,f.atr*(.055 if name!='M15' else .10))
            max_dist=max(f.atr*2.4,h1.atr*2.0)
            for idx,(level,stamp) in enumerate(rows[-42:]):
                level=float(level);dist=future_limit(side,level)
                if dist<=min_dist or dist>max_dist: continue
                later=[b for b in f.bars if b.time>stamp]
                # Una zona cerrada con claridad ya no es un soporte/resistencia futuro.
                if any(side*(float(b.close)-level)<-f.atr*.20 for b in later): continue
                touches=sum(1 for b in later if float(b.low)<=level+f.atr*.07 and float(b.high)>=level-f.atr*.07)
                if touches>=5: continue
                recency=(idx+1)/max(1,len(rows[-42:]))
                trend_bonus=max(-3.0,min(3.5,side*float(f.trend)*3.5))
                score=base+recency*2.0+trend_bonus-touches*.9
                zones.append((dist,-score,level,stamp,name,f,touches,score))
        if zones:
            # Cercanía útil primero; dentro de un rango parecido gana calidad.
            zones.sort(key=lambda x:(x[0]/max(x[5].atr,1e-9),x[1]))
            dist,_neg,level,stamp,name,f,touches,score=zones[0]
            stop,stopwhy=_refine_pending_stop(frames,side,level,level-side*f.atr*.62,f.atr,rules)
            risk=side*(level-stop)
            if risk>0:
                tp,twhy=observed_target(side,level,stop,1.50)
                rr=side*(tp-level)/max(risk,1e-9)
                if rr<1.35:
                    tp=level+side*risk*1.60;rr=1.60;twhy='FAST target mínimo 1.60R'
                reason=(f'REFLEX FAST MAP · LIMIT {name} swing observado; distancia {dist/max(f.atr,1e-9):.2f} ATR-{name}; '
                        f'retests {touches}; {stopwhy}; {twhy}; RR {rr:.2f}; respaldo futuro bajo control continuo')
                out.append(Setup(f'SWING:FAST:L:{side}:{name}:{stamp}',side,'PENDING','LIMIT',
                                 level,stop,tp,m1.atr,max(74.0,score),now,reason,name,f.atr))

        # -------- STOP: ruptura futura del rango H1 reciente --------
        recent=list(h1.bars[-12:])
        if recent:
            boundary=max(float(b.high) for b in recent) if side==1 else min(float(b.low) for b in recent)
            buffer=max(m1.atr*.65,h1.atr*.035)
            level=boundary+side*buffer
            dist=future_stop(side,level)
            if dist>max(m1.atr*.9,h1.atr*.055) and dist<=h1.atr*1.8:
                opposite=min(float(b.low) for b in recent) if side==1 else max(float(b.high) for b in recent)
                # No usar todo el rango como SL si es enorme: buscar swing observado detrás de ruptura.
                fallback=level-side*max(h1.atr*.72,m15.atr*1.1)
                stop,stopwhy=_refine_pending_stop(frames,side,level,fallback,h1.atr,rules)
                risk=side*(level-stop)
                if risk>0:
                    tp,twhy=observed_target(side,level,stop,1.45)
                    rr=side*(tp-level)/max(risk,1e-9)
                    if rr<1.30:
                        tp=level+side*risk*1.55;rr=1.55;twhy='FAST breakout target mínimo 1.55R'
                    trend_agree=sum(1 for f in (m15,h1,h4) if f is not None and side*float(f.trend)>.12)
                    score=78.0+trend_agree*2.2
                    reason=(f'REFLEX FAST MAP · STOP ruptura H1 futura; rango 12 velas; {stopwhy}; {twhy}; RR {rr:.2f}; '
                            f'confirmaciones tendencia {trend_agree}; respaldo de movimiento, no entrada MARKET')
                    out.append(Setup(f'SWING:FAST:S:{side}:H1:{h1.bars[-1].time}',side,'PENDING','STOP',
                                     level,stop,tp,m1.atr,score,now,reason,'H1',h1.atr))

        # -------- STOP RÁPIDO M15: confirmación de giro/continuación --------
        # Si el mercado corre antes de volver a una zona H1/H4, una ruptura M15
        # permite capturar el movimiento FUTURO sin entrar a mercado. En el lado
        # contrario a la tendencia actual actúa como confirmación de reversión:
        # solo se activa después de romper soporte/resistencia real.
        recent15=list(m15.bars[-3:])
        if recent15:
            boundary15=max(float(b.high) for b in recent15) if side==1 else min(float(b.low) for b in recent15)
            buffer15=max(m1.atr*.45,m15.atr*.045)
            level15=boundary15+side*buffer15
            dist15=future_stop(side,level15)
            if dist15>max(m1.atr*.55,m15.atr*.05) and dist15<=m15.atr*2.25:
                fallback15=level15-side*max(m15.atr*.58,m1.atr*2.2)
                stop15,stopwhy15=_refine_pending_stop(frames,side,level15,fallback15,m15.atr,rules)
                risk15=side*(level15-stop15)
                if risk15>0:
                    tp15,twhy15=observed_target(side,level15,stop15,1.35)
                    rr15=side*(tp15-level15)/max(risk15,1e-9)
                    if rr15<1.25:
                        tp15=level15+side*risk15*1.50;rr15=1.50;twhy15='FAST M15 target mínimo 1.50R'
                    trend_agree15=sum(1 for f in (m15,h1,h4) if f is not None and side*float(f.trend)>.12)
                    score15=76.0+trend_agree15*2.0
                    reason15=(f'HUNTER FAST MAP · STOP ruptura M15 futura; rango 3 velas; {stopwhy15}; {twhy15}; RR {rr15:.2f}; '
                              f'confirmaciones tendencia {trend_agree15}; activa solo tras ruptura, nunca MARKET')
                    out.append(Setup(f'SWING:FAST:S:{side}:M15:{m15.bars[-1].time}',side,'PENDING','STOP',
                                     level15,stop15,tp15,m1.atr,score15,now,reason15,'M15',m15.atr))
    if not out: rejected['fast-map sin estructura futura utilizable'] += 1
    return out

def build_snap_analyst_pendings(frames: dict[str,Frame], rules: dict, rejected: Counter) -> list[Setup]:
    """V12.8 FLASHMAP: mapa humano rápido basado en estructura cercana observada.

    Se parece al flujo manual: 1) identifica la oferta/demanda futura más cercana
    con confirmación M15/H1; 2) prepara también una ruptura M15 para no perder una
    expansión; 3) deja SL detrás de estructura/ruido; 4) busca el siguiente objetivo
    observado y, solo si no existe, proyecta un RR moderado. No usa web/LLM y por eso
    puede estar listo en el primer ciclo.
    """
    if not all(k in frames for k in ('M1','M5','M15','H1')):
        rejected['snap-map esperando M1/M5/M15/H1'] += 1
        return []
    m1,m5,m15,h1=(frames[k] for k in ('M1','M5','M15','H1'))
    h4=frames.get('H4'); current=float(m1.bars[-1].close); now=int(m1.bars[-1].time)
    out=[]

    def next_target(side,entry,stop,min_rr=1.55):
        risk=side*(entry-stop)
        levels=[]
        for name in ('M15','H1','H4','D1'):
            f=frames.get(name)
            if not f: continue
            rows=f.highs if side==1 else f.lows
            for price,stamp in rows[-48:]:
                d=side*(float(price)-entry)
                if d>=max(risk*min_rr,m1.atr*.55): levels.append((d,float(price),name,stamp))
        if levels:
            _d,price,name,_stamp=min(levels,key=lambda x:x[0])
            return price-side*m1.atr*.05,f'SNAP objetivo swing {name} observado'
        rr=max(1.65,min(2.40,float(rules.get('snap_projected_rr',2.05))))
        return entry+side*risk*rr,f'SNAP objetivo proyectado prudente {rr:.2f}R'

    def intact(f,side,level,stamp):
        # Una zona cerrada con decisión deja de ser futura; las mechas pueden barrerla.
        threshold=max(f.atr*.10,m1.atr*.30)
        return not any(side*(float(b.close)-float(level)) < -threshold for b in f.bars if b.time>stamp)

    for side in (1,-1):
        # -------- LIMIT cercano: M5 puede afinar, pero M15/H1 confirman la zona. --------
        candidates=[]
        htf_rows=[]
        for f in (m15,h1,h4):
            if not f: continue
            rows=f.lows if side==1 else f.highs
            htf_rows.extend((float(level),f) for level,_ in rows[-32:])
        for name,f,base in (('M5',m5,82.0),('M15',m15,86.0),('H1',h1,89.0)):
            rows=f.lows if side==1 else f.highs
            for idx,(level,stamp) in enumerate(rows[-40:]):
                level=float(level);dist=side*(current-level)
                min_dist=max(m1.atr*.32,f.atr*.035)
                max_dist=max(m15.atr*2.2,h1.atr*1.35)
                if dist<=min_dist or dist>max_dist or not intact(f,side,level,stamp): continue
                # M5 solo es válido si cae dentro de una zona M15/H1 cercana o el
                # contexto M15/H1 favorece ese lado. Así se usa precisión sin micro-scalp.
                confirmed=True
                if name=='M5':
                    near_htf=any(abs(level-lvl)<=max(m15.atr*.32,other.atr*.16,m5.atr*.70) for lvl,other in htf_rows)
                    trend_ok=side*(m15.trend*1.3+h1.trend)>=-.10
                    confirmed=near_htf or trend_ok
                if not confirmed: continue
                later=[b for b in f.bars if b.time>stamp]
                touches=sum(1 for b in later if float(b.low)<=level+f.atr*.07 and float(b.high)>=level-f.atr*.07)
                if touches>=5: continue
                alignment=side*(m15.trend*1.4+h1.trend+(h4.trend*.7 if h4 else 0.0))
                recency=(idx+1)/max(1,len(rows[-40:]))
                score=base+max(-4.0,min(5.0,alignment*2.2))+recency*2.0-touches*.8
                # Preferir una zona activable, no la zona más lejana con el score más bonito.
                norm=dist/max(m15.atr,1e-9)
                utility=score-norm*6.0
                candidates.append((utility,score,dist,level,stamp,name,f,touches))
        if candidates:
            candidates.sort(key=lambda x:(x[0],x[1]),reverse=True)
            # Dos LIMIT por lado quedan disponibles para el pool; Engine ejecuta solo
            # la mejor por dirección y conserva la otra como alternativa inmediata.
            for rank,row in enumerate(candidates[:2],1):
                _utility,score,dist,level,stamp,name,f,touches=row
                source=max(m15.atr,f.atr if name!='M5' else m15.atr)
                fallback=level-side*max(source*.58,m1.atr*2.2)
                stop,stopwhy=_refine_pending_stop(frames,side,level,fallback,source,rules)
                risk=side*(level-stop)
                if risk<=0: continue
                tp,twhy=next_target(side,level,stop,1.50)
                rr=side*(tp-level)/max(risk,1e-9)
                if rr<1.30:
                    tp=level+side*risk*1.60;rr=1.60;twhy='SNAP objetivo mínimo 1.60R'
                src_tf='M15' if name=='M5' else name
                reason=(f'FLASHMAP SNAP · LIMIT {name} observado confirmado por M15/H1; '
                        f'distancia {dist/max(m15.atr,1e-9):.2f} ATR-M15; retests {touches}; '
                        f'{stopwhy}; {twhy}; RR {rr:.2f}; alternativa #{rank}')
                out.append(Setup(f'SWING:SNAP:L:{side}:{src_tf}:{stamp}:{rank}',side,'PENDING','LIMIT',
                                 level,stop,tp,m1.atr,max(76.0,score),now,reason,src_tf,source))

        # -------- STOP cercano: ruptura de microestructura M15, no MARKET. --------
        recent=list(m15.bars[-4:])
        if recent:
            boundary=max(float(b.high) for b in recent) if side==1 else min(float(b.low) for b in recent)
            buffer=max(m1.atr*.30,m15.atr*.025)
            level=boundary+side*buffer
            dist=side*(level-current)
            if dist>max(m1.atr*.28,m15.atr*.025) and dist<=m15.atr*1.10:
                fallback=level-side*max(m15.atr*.62,m1.atr*2.0)
                stop,stopwhy=_refine_pending_stop(frames,side,level,fallback,m15.atr,rules)
                risk=side*(level-stop)
                if risk>0:
                    tp,twhy=next_target(side,level,stop,1.40)
                    rr=side*(tp-level)/max(risk,1e-9)
                    if rr<1.25:
                        tp=level+side*risk*1.50;rr=1.50;twhy='SNAP breakout mínimo 1.50R'
                    align=side*(m15.trend*1.6+h1.trend+(h4.trend*.6 if h4 else 0.0))
                    score=82.0+max(-5.0,min(6.0,align*2.4))
                    reason=(f'FLASHMAP SNAP · STOP ruptura M15 de 4 velas; distancia {dist/max(m15.atr,1e-9):.2f} ATR-M15; '
                            f'{stopwhy}; {twhy}; RR {rr:.2f}; captura expansión futura, nunca MARKET')
                    out.append(Setup(f'SWING:SNAP:S:{side}:M15:{m15.bars[-1].time}',side,'PENDING','STOP',
                                     level,stop,tp,m1.atr,max(72.0,score),now,reason,'M15',m15.atr))
    if not out: rejected['snap-map sin estructura cercana utilizable'] += 1
    return out

def build_intraday_structural_pendings(frames,rules,rejected):
    """Zonas M5 reales dentro de M15/H1; SL fuera de la zona, nunca inventado.

    Las EMAs solo confirman tendencia. El nivel procede de un swing confirmado
    por dos cierres a cada lado y del cuerpo/mecha de su vela de demanda/oferta.
    Los objetivos son obstáculos observados; este motor no proyecta un TP.
    """
    if not rules.get('intraday_structural_map',True):return []
    m1,m5,m15,h1=(frames.get(tf) for tf in ('M1','M5','M15','H1'))
    if not all((m1,m5,m15,h1)) or min(m1.atr,m5.atr,m15.atr)<=0:return []
    current=m1.bars[-1].close;now=m1.bars[-1].time;out=[]
    by_time={b.time:i for i,b in enumerate(m5.bars)}
    for side in (1,-1):
        aligned=side*m15.trend>=.12 and side*h1.trend>=.08
        htf=[]
        for f in (m15,h1,frames.get('H4')):
            if f:htf.extend((float(v),f.atr) for v,_ in (f.lows if side==1 else f.highs))
        rows=m5.lows if side==1 else m5.highs
        for extreme,stamp in rows[-16:]:
            i=by_time.get(stamp,-1)
            if i<2 or i+2>=len(m5.bars):continue
            origin=m5.bars[i];neighbors=m5.bars[i-2:i]+m5.bars[i+1:i+3]
            # Revalidar los swings; también protege caches/importaciones defectuosas.
            observed=origin.low if side==1 else origin.high
            if abs(float(extreme)-observed)>m5.atr*.001:continue
            if side==1 and any(b.low<origin.low for b in neighbors):continue
            if side==-1 and any(b.high>origin.high for b in neighbors):continue
            near_htf=any(abs(float(extreme)-v)<=max(m5.atr*.60,a*.16) for v,a in htf)
            # Un fade de una tendencia fuerte necesita un rechazo YA observado.
            last=m15.bars[-1]
            rejected_htf=near_htf and side*(last.close-last.open)>m15.atr*.15 and side*m15.trend>=-.25
            if not aligned and not rejected_htf:continue
            later=m5.bars[i+1:]
            if any(side*(b.close-float(extreme))<-m5.atr*.10 for b in later):continue
            touches=sum(b.low<=float(extreme)+m5.atr*.12 and b.high>=float(extreme)-m5.atr*.12 for b in later)
            if touches>=4:continue
            body_edge=min(origin.open,origin.close) if side==1 else max(origin.open,origin.close)
            level=(float(extreme)+float(body_edge))*.5
            distance=side*(current-level)
            if not m5.atr*.12<distance<=m5.atr*1.65:continue
            # La invalidación pertenece a M5. Una mecha H1 no es ruido de M5;
            # medirla como tal vuelve imposible cualquier zona intradía válida.
            wick=_wick_noise_floor(frames,side,('M1','M5'))
            buffer=max(m5.atr*.20,m1.atr*.40,wick*.65)
            stop=float(extreme)-side*buffer
            risk=side*(level-stop)
            noise=max(m5.atr*float(rules.get('pending_stop_min_source_atr',.55)),
                      m1.atr*float(rules.get('pending_stop_min_m1_atr',1.8)),
                      wick*float(rules.get('pending_wick_clearance_mult',1.25)))
            if risk<noise or risk>m5.atr*1.8:continue
            targets=[]
            for f in (m5,m15,h1,frames.get('H4'),frames.get('D1')):
                if not f:continue
                targets.extend(float(v) for v,_ in (f.highs if side==1 else f.lows)
                               if side*(float(v)-level)>m5.atr*.15)
            if not targets:continue
            # El PRIMER obstáculo determina el recorrido; no saltar una oferta
            # cercana para fabricar una relación riesgo/beneficio más bonita.
            boundary=min(targets,key=lambda v:side*(v-level))
            target=boundary-side*max(m5.atr*.05,m1.atr*.12)
            rr=side*(target-level)/risk
            if rr<max(1.6,float(rules.get('min_rr_pending',1.4))) or side*(target-level)>m5.atr*float(rules.get('pending_target_max_source_atr',6.0)):continue
            age_bars=(m5.bars[-1].time-stamp)/300
            score=87+min(4,max(0,side*(m15.trend+h1.trend))*2)+(3 if near_htf else 0)-touches*.8-min(3,age_bars*.08)
            reason=(f'INTRADAY ESTRUCTURAL · swing M5 y zona cuerpo/mecha observados; '
                    f'{"tendencia M15/H1 alineada" if aligned else "rechazo M15 de zona HTF observado"}; '
                    f'SL fuera de la zona M5 y ruido; primer objetivo observado {boundary:g}; RR {rr:.2f}; retests {touches}')
            out.append(Setup(f'SWING:INTRADAY:{side}:M5:{stamp}',side,'PENDING','LIMIT',
                level,stop,target,m1.atr,score,now,reason,'M5',m5.atr))
    if not out:rejected['intraday sin zona M5 observada con confluencia/recorrido']+=1
    return out


def round_price(price: float, step: float, direction: int=0) -> float:
    if not math.isfinite(price) or step<=0:
        raise ValueError("precio/tick_size inválido")
    units=price/step
    n=math.ceil(units-1e-8) if direction>0 else math.floor(units+1e-8) if direction<0 else round(units)
    return round(n*step,10)

def normalize(plan: Plan, step: float) -> Plan:
    # Nunca encoger SL para pasar el presupuesto; solo redondearlo hacia fuera.
    return replace(plan,entry=round_price(plan.entry,step),
                   sl=round_price(plan.sl,step,-plan.side),tp=round_price(plan.tp,step,-plan.side))

def build_setups(frames: dict[str,Frame], rules: dict | None=None) -> tuple[list[Setup],Counter]:
    """V193 separa dos motores y conserva varias zonas candidatas.

    PENDING = dos mapas simultáneos: ESTRUCTURAL H1/H4 y TÁCTICO M5/M15/M30.
    Todos los planes de entrada son LIMIT o STOP con invalidación estructural.
    """
    rules=rules or {}
    if "M1" not in frames or "M5" not in frames:
        return [],Counter({"cargando M1/M5":1})
    m1,m5=frames["M1"],frames["M5"]
    now=m1.bars[-1].time
    current=m1.bars[-1].close
    result=[]; rejected=Counter()
    # V197: conservar el mapa estructural H1/H4 y construir EN PARALELO el mapa
    # táctico M5/M15/M30. V195 anunciaba ambos mapas, pero el bucle táctico quedó
    # literalmente desactivado (for side in ()), por eso la terminal mostraba
    # TÁCTICAS=0 de forma permanente.
    result.extend(build_v184_swing_pendings(frames,rules,rejected))
    result.extend(build_intraday_structural_pendings(frames,rules,rejected))
    # V12.3: reservas HTF observadas; Planner las oculta del mapa estricto y solo
    # las deja competir si falta BUY o SELL en el mapa ALWAYS-ON.
    result.extend(build_presence_reserve_pendings(frames,rules,rejected))
    # V12.4 REFLEX: respaldo futuro rápido. Planner lo mantiene fuera del mapa
    # estricto y solo lo deja competir cuando falta BUY o SELL.
    result.extend(build_fast_future_map_pendings(frames,rules,rejected))
    # V12.8 FLASHMAP: mapa humano rápido que siempre compite en el pase PRESENCE.
    result.extend(build_snap_analyst_pendings(frames,rules,rejected))

    # ------------------------------------------------------------------
    # 1) MAPA TÁCTICO + ESTRUCTURAL COMPLEMENTARIO
    # ------------------------------------------------------------------
    # Objetivo: reproducir el tipo de mapa manual que se prepara al analizar
    # el gráfico: BUY LIMIT + SELL LIMIT de retorno a demanda/oferta y
    # BUY STOP + SELL STOP de ruptura estructural. Las candidatas luego compiten
    # escenarios principales, lejos del precio actual; el microentrada no participa
    # en sus niveles.
    tf_weight={"M5":2.6,"M15":4.2,"M30":4.5,"H1":6.0,"H4":4.5}

    def major_target(side,entry,stop):
        risk=side*(entry-stop)
        # Para pendientes no elegir el primer micro-swing M1. Buscar un objetivo
        # M15/H1/H4 que deje espacio de verdad, como en los mapas manuales.
        levels=[]
        for name in ("M15","M30","H1","H4"):
            f=frames.get(name)
            if not f: continue
            rows=f.highs if side==1 else f.lows
            for price,_ in rows[-24:]:
                distance=side*(price-entry)
                if distance>=max(risk*1.55,m1.atr*1.8):
                    levels.append((distance,price,name))
        if levels:
            _,price,name=min(levels,key=lambda x:x[0])
            return price-side*m1.atr*.10,f"objetivo: swing {name} con espacio estructural"
        distance=max(risk*1.9,m1.atr*3.0)
        return entry+side*distance,"objetivo: proyección estructural 1.9R"

    def collect_limit_zones(side):
        zones=[]
        # V193 añade una zona M5 "activable" solo cuando M15/H1 no la contradicen.
        # No es un microentrada disfrazado: debe ser un swing/OB/FVG real que haya nacido
        # antes del precio actual y el SL continúa detrás de la estructura.
        for name in ("M5","M15","M30","H1","H4"):
            f=frames.get(name)
            if not f: continue
            if name=="M5":
                higher=[frames.get("M15"),frames.get("H1")]
                higher=[x for x in higher if x is not None]
                aligned=(sum(side*x.trend for x in higher)>=-.04 or
                         any(x.extra.get("bos")==side for x in higher))
                if not higher or not aligned:
                    continue
            zone_floor=(max(m1.atr*float(rules.get("pending_m5_floor_m1_atr",.55)),
                            f.atr*float(rules.get("pending_m5_floor_source_atr",.08))) if name=="M5" else
                        max(m1.atr*float(rules.get("pending_htf_floor_m1_atr",.95)),
                            f.atr*float(rules.get("pending_htf_floor_source_atr",.11))))
            rows=f.lows if side==1 else f.highs
            recent=rows[-24:]
            for idx,(level,stamp) in enumerate(recent):
                future=side*(current-level)
                if future<=zone_floor:
                    continue
                # No utilizar swings rotos después de formarse.
                later=[b for b in f.bars if b.time>stamp]
                broken=any(side*(b.close-level)<-max(f.atr*.06,m1.atr*.20) for b in later)
                if broken:
                    continue
                recency=(idx+1)/max(len(recent),1)
                score=tf_weight[name]+recency*2.0
                score+=max(-2.0,min(2.0,f.trend*side*2.0))
                if f.extra.get("sweep")==side: score+=1.3
                if f.extra.get("bos")==side: score+=1.0
                # Confluencias de EMA/Fib: no crean la zona, solo refuerzan un swing.
                near=[]
                for label,value in (("EMA21",f.slow),("EMA50",f.extra.get("ema50",f.slow)),
                                    ("FIB38",f.extra.get("fib382",level)),("FIB50",f.extra.get("fib50",level)),
                                    ("FIB62",f.extra.get("fib618",level))):
                    if abs(value-level)<=max(f.atr*.18,m1.atr*.55): near.append(label)
                score+=min(3.0,len(near)*.75)
                zones.append({"level":level,"stamp":stamp,"name":name,"atr":f.atr,
                              "score":score,"label":f"swing {name}"+(" + "+"/".join(near) if near else "")})

            # Order block real: vela contraria inmediatamente antes de un desplazamiento.
            for i in range(max(2,len(f.bars)-42),len(f.bars)):
                a,b=f.bars[i-1],f.bars[i]
                displacement=side*(b.close-b.open)
                broke=side*(b.close-(a.high if side==1 else a.low))
                if side*(a.close-a.open)<0 and displacement>f.atr*.80 and broke>f.atr*.05:
                    level=(a.high if side==1 else a.low)
                    if side*(current-level)>zone_floor:
                        zones.append({"level":level,"stamp":a.time,"name":name,"atr":f.atr,
                                      "score":tf_weight[name]+4.0+max(0,f.trend*side*2),
                                      "label":f"oferta/demanda OB {name}"})

            # FVG no mitigado: útil como zona, no como gatillo inmediato.
            for i in range(max(2,len(f.bars)-48),len(f.bars)):
                a,b=f.bars[i-2],f.bars[i]
                after=f.bars[i+1:]
                if side==1 and b.low>a.high+f.atr*.06 and all(x.low>b.low for x in after):
                    level=(a.high+b.low)/2
                elif side==-1 and b.high<a.low-f.atr*.06 and all(x.high<b.high for x in after):
                    level=(a.low+b.high)/2
                else:
                    continue
                if side*(current-level)>zone_floor:
                    zones.append({"level":level,"stamp":b.time,"name":name,"atr":f.atr,
                                  "score":tf_weight[name]+3.0+max(0,f.trend*side*1.5),
                                  "label":f"FVG no mitigado {name}"})

            # Zonas dinámicas SOLO como respaldo cuando el mapa no tiene un swing
            # limpio en ese lado. Sirven para que siempre exista el escenario
            # alcista y bajista del mapa, pero puntúan por debajo de OB/swing/FVG.
            if name=="M5" and side*f.trend>.12:
                # Pullback rápido, pero no pegado al precio: EMA9/21 de M5 solo
                # cuando M5 y el contexto superior ya apuntan al mismo lado.
                # Esta es la alternativa activable que evita esperar horas por H1.
                for label,value in (("EMA9",f.fast),("EMA21",f.slow)):
                    future=side*(current-value)
                    if zone_floor<future<=f.atr*1.10:
                        zones.append({"level":value,"stamp":f.bars[-1].time,"name":name,"atr":f.atr,
                                      "score":tf_weight[name]+3.0+max(0.0,f.trend*side*2.0),
                                      "label":f"pullback activable {label} M5 + contexto M15/H1"})
            elif name!="M5":
                for label,value in (("EMA21",f.slow),("EMA50",f.extra.get("ema50",f.slow)),
                                    ("FIB50",f.extra.get("fib50",f.slow)),("FIB62",f.extra.get("fib618",f.slow))):
                    if side*(current-value)>max(m1.atr*1.10,f.atr*.14):
                        zones.append({"level":value,"stamp":f.bars[-1].time,"name":name,"atr":f.atr,
                                      "score":tf_weight[name]+1.2+max(-1.0,f.trend*side),
                                      "label":f"zona dinámica {label} {name}"})

        if not zones:
            # Mercado en expansión sin swing futuro visible: solo se permite una
            # proyección si YA existe M15/H1. Antes de cargar esos marcos Akira
            # espera unas décimas/ciclos en lugar de mandar una pendiente M5
            # prematura que después parezca un microentrada.
            ref=frames.get("H1") or frames.get("M15")
            if ref is not None:
                distance=max(m1.atr*2.4,ref.atr*.38)
                level=current-side*distance
                zones.append({"level":level,"stamp":ref.bars[-1].time,"name":ref.name,"atr":ref.atr,
                              "score":tf_weight.get(ref.name,2.0),
                              "label":f"zona proyectada {ref.name} por expansión"})
        return zones

    for side in (1,-1):  # V197: mapa táctico REAL habilitado
        pctx,ptext=pending_context(frames,side)
        zones=collect_limit_zones(side)
        if zones:
            # Agrupar niveles próximos para escoger oferta/demanda con confluencia,
            # no el primer swing que aparezca.
            zones=sorted(zones,key=lambda z:z["level"])
            clusters=[]
            for z in zones:
                tolerance=max(m1.atr*.70,z["atr"]*.14)
                hit=next((c for c in clusters if abs(c["center"]-z["level"])<=max(c["tol"],tolerance)),None)
                if hit is None:
                    clusters.append({"rows":[z],"center":z["level"],"tol":tolerance})
                else:
                    hit["rows"].append(z)
                    total=sum(max(1.0,x["score"]) for x in hit["rows"])
                    hit["center"]=sum(x["level"]*max(1.0,x["score"]) for x in hit["rows"])/total
                    hit["tol"]=max(hit["tol"],tolerance)
            ranked=[]
            for c in clusters:
                level=c["center"]
                rows=c["rows"]
                best=max(rows,key=lambda x:x["score"])
                future=side*(current-level)
                floor=(max(m1.atr*.55,best["atr"]*.08) if best["name"]=="M5" else
                       max(m1.atr*.95,best["atr"]*.11))
                if future<=floor: continue
                confluence=len({(x["name"],x["label"]) for x in rows})
                # Premiar confluencia y H1/M15; penalizar solo levemente distancia.
                quality=max(57.0,56+pctx+best["score"]+min(9,confluence*1.7)-future/max(m1.atr,1e-9)*.22)
                ranked.append((quality,level,best,confluence))
            if rules.get('pending_zone_alternatives',False):
                # A confluence cluster can contain a genuine M5/M15 zone and an
                # H1/H4 zone. Keeping only the highest TF gives every alternative
                # the widest invalidation. Retain the observed lower-TF anchors
                # too; the engine still checks noise, quality, money and broker.
                seen_alternatives=set();anchor_options=[];per_frame=Counter()
                for cluster in clusters:
                    confluence=len({(x['name'],x['label']) for x in cluster['rows']})
                    for anchor in cluster['rows']:
                        name=anchor['name'];level=float(anchor['level'])
                        if name not in ('M5','M15','M30'):continue
                        identity=(name,level,anchor['stamp'])
                        if identity in seen_alternatives:continue
                        seen_alternatives.add(identity)
                        future=side*(current-level)
                        floor=max(m1.atr*.55,anchor['atr']*.08) if name=='M5' else max(m1.atr*.95,anchor['atr']*.11)
                        if future<=floor:continue
                        quality=max(57.0,56+pctx+anchor['score']+min(9,confluence*1.7)-future/max(m1.atr,1e-9)*.22)
                        anchor_options.append((quality,anchor,confluence))
                for quality,anchor,confluence in sorted(anchor_options,key=lambda row:row[0],reverse=True):
                    name=anchor['name'];level=float(anchor['level'])
                    if per_frame[name]>=4:continue
                    per_frame[name]+=1
                    fallback=level-side*anchor['atr']*.30
                    stop,stopwhy=_refine_pending_stop(frames,side,level,fallback,anchor['atr'],rules)
                    target,why=major_target(side,level,stop)
                    key=f"MAP:L:{side}:A{name}{per_frame[name]}:{name}:{anchor['stamp']}"
                    result.append(Setup(key,side,'PENDING','LIMIT',level,stop,target,m1.atr,
                        quality,now,f"PENDIENTE FUTURA · zona observada alternativa {anchor['label']}; confluencias {confluence}; {ptext}; {stopwhy}; {why}",name,anchor['atr']))
            if ranked:
                # V193 conserva varias zonas por lado. Después, Engine las rankea
                # con TODO el contexto disponible (modelo, fuentes y DOM) sin mover
                # los niveles estructurales. Así no dependemos de "la primera zona".
                pool=max(4,int(float(rules.get("pending_candidate_pool",8))))
                for rank,(quality,level,best,confluence) in enumerate(sorted(ranked,key=lambda x:x[0],reverse=True)[:pool],1):
                    fallback=level-side*best["atr"]*.30
                    stop,stopwhy=_refine_pending_stop(frames,side,level,fallback,best["atr"],rules)
                    if side*(level-stop)>m1.atr*.20:
                        target,why=major_target(side,level,stop)
                        rr=side*(target-level)/max(side*(level-stop),1e-9)
                        # V193: un R:R enorme producido por SL apretado deja de ser
                        # una ventaja de score. Preferimos geometrías realistas que
                        # sobrevivan ruido y aun mantengan recompensa suficiente.
                        preferred=float(rules.get("pending_preferred_max_rr",4.5))
                        rr_quality=0.0 if rr<=preferred else -min(8.0,(rr-preferred)*1.6)
                        result.append(Setup(f"MAP:L:{side}:{rank}:{best['name']}:{best['stamp']}",side,"PENDING","LIMIT",
                                            level,stop,target,m1.atr,quality-(rank-1)*.35+rr_quality,now,
                                            f"PENDIENTE FUTURA · MAPA V193 · zona #{rank} retorno a {'demanda' if side==1 else 'oferta'}; {best['label']}; "
                                            f"confluencias {confluence}; {ptext}; {stopwhy}; {why}; RR geométrico {rr:.2f}",best["name"],best["atr"]))
        else:
            rejected[f"sin zona {'demanda' if side==1 else 'oferta'} HTF válida"]+=1

        # Ruptura condicional: M5/M15 comprimidos, siempre con contexto superior.
        # Se coloca antes de romper; por eso no espera la vela completa para enviar.
        breakout_rows=[]
        for name in ("M5","M15","M30"):
            f=frames.get(name)
            if not f: continue
            higher=frames.get("M15") if name=="M5" else frames.get("H1")
            if higher is not None and side*higher.trend<-.22 and higher.extra.get("bos")!=side:
                continue
            recent=f.bars[-12:]
            width=max(b.high for b in recent)-min(b.low for b in recent)
            compression=width/max(f.atr,1e-9)
            if compression>4.2:
                continue
            boundary=max(b.high for b in recent) if side==1 else min(b.low for b in recent)
            breakout_rows.append((tf_weight[name]+max(-2,min(2,f.trend*side*2))+
                                  max(0.0,2.0-compression)*1.2,boundary,name,f))
        if breakout_rows:
            pool=max(2,int(float(rules.get("pending_candidate_pool",8))))
            for rank,(_,boundary,name,f) in enumerate(sorted(breakout_rows,key=lambda x:x[0],reverse=True)[:min(4,pool)],1):
                buffer=max(m1.atr*.55,f.atr*.055)
                level=boundary+side*buffer
                recent=f.bars[-8:]
                inner=(min(b.low for b in recent) if side==1 else max(b.high for b in recent))
                structural=boundary-side*max(m1.atr*.55,f.atr*.11)
                base=min(inner,structural) if side==1 else max(inner,structural)
                stop,stopwhy=_refine_pending_stop(frames,side,level,base,f.atr,rules)
                if side*(level-stop)>m1.atr*.24:
                    target,why=major_target(side,level,stop)
                    rr=side*(target-level)/max(side*(level-stop),1e-9)
                    preferred=float(rules.get("pending_preferred_max_rr",4.5))
                    rr_quality=0.0 if rr<=preferred else -min(8.0,(rr-preferred)*1.6)
                    score=max(57.0,58+pctx+tf_weight[name]+max(-1.5,min(2.5,f.trend*side*2.0))-(rank-1)*.25)
                    result.append(Setup(f"MAP:S:{side}:{rank}:{name}:{f.bars[-1].time}",side,"PENDING","STOP",
                                        level,stop,target,m1.atr,score+rr_quality,now,
                                        f"PENDIENTE FUTURA · CONDICIONAL V193 · ruptura {'alcista' if side==1 else 'bajista'} {name}; "
                                        f"activación lejos del precio; {ptext}; {stopwhy}; {why}; RR geométrico {rr:.2f}",name,f.atr))

    return result,rejected
