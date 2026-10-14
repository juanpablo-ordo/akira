"""Microestructura de ticks observados: niveles congelados antes de su cruce.

No depende de descargas. Una ventana exige >= 5 ticks distintos y >= 1.2 segundos.
El mismo movimiento conserva su identificador para no volver a operar cada tick.
"""
from collections import deque
from strategy import quote_identity


FAST_WINDOW_SECONDS = 1.2
SLOW_WINDOW_SECONDS = 4.5


def velocity_delta(live):
    """Compare observed velocities in equivalent 1.2-second ATR displacement.

    Raw displacements over unequal windows are not an acceleration comparison:
    steady motion naturally travels farther in 4.5 seconds than in 1.2 seconds.
    Actual anchor ages also handle sparse/partial tick history correctly.
    """
    fast_span = max(.001, float(live.get('fast_span_seconds', FAST_WINDOW_SECONDS) or FAST_WINDOW_SECONDS))
    slow_span = max(.001, float(live.get('slow_span_seconds', SLOW_WINDOW_SECONDS) or SLOW_WINDOW_SECONDS))
    fast_velocity = float(live.get('fast_atr', 0.0) or 0.0) / fast_span
    slow_velocity = float(live.get('slow_atr', 0.0) or 0.0) / slow_span
    return FAST_WINDOW_SECONDS * (fast_velocity - slow_velocity)


class MarketTape:
    def __init__(self):
        self.ticks=deque(maxlen=1200)
        self.levels=[]
        self.built=0.0
        self.bar=0
        self.minute_bucket=None
        self.minute_open=0.0
        self.minute_high=0.0
        self.minute_low=0.0
        self.five_bucket=None
        self.five_open=0.0
        self.five_high=0.0
        self.five_low=0.0
        self.five_pullback={1:None,-1:None}
        self.five_retest_anchor={1:None,-1:None}
        self.last_metrics={"body_atr":0.0,"fast_atr":0.0,"slow_atr":0.0,"range_pos":0.5,
                           "m5_body_atr":0.0,"m5_range_pos":0.5,"ticks":0,"minute_ticks":0,"direction":0.0}


    def metrics(self,atr,now,bid=None,atr5=None):
        """Lectura viva de la vela M1 actual + impulso de ticks.

        No recalcula indicadores con una vela sin cerrar. Solo mide lo que está
        ocurriendo AHORA: cuerpo desde el primer tick del minuto, posición dentro
        del rango vivo y desplazamiento de ticks a ~1.2 s y ~4.5 s. Todo se
        normaliza por ATR de la última vela cerrada para poder comparar BTC/oro.
        """
        atr=max(float(atr or 0.0),1e-9)
        atr5=max(float(atr5 or atr),1e-9)
        if bid is None:
            bid=float(self.ticks[-1].bid) if self.ticks else self.minute_open
        def anchor(seconds):
            rows=[x for x in self.ticks if now-float(x.time)>=seconds]
            row=rows[-1] if rows else self.ticks[0] if self.ticks else None
            if row is None:
                return float(bid),seconds
            return float(row.bid),max(.001,now-float(row.time))
        fast_anchor,fast_span=anchor(FAST_WINDOW_SECONDS)
        slow_anchor,slow_span=anchor(SLOW_WINDOW_SECONDS)
        fast=(float(bid)-fast_anchor)/atr
        slow=(float(bid)-slow_anchor)/atr
        body=(float(bid)-float(self.minute_open or bid))/atr
        span=max(float(self.minute_high)-float(self.minute_low),1e-9)
        pos=(float(bid)-float(self.minute_low))/span if span>1e-9 else .5
        pos_bias=(pos-.5)*2.0
        m5_body=(float(bid)-float(self.five_open or bid))/atr5
        m5_span=max(float(self.five_high)-float(self.five_low),1e-9)
        m5_pos=(float(bid)-float(self.five_low))/m5_span if m5_span>1e-9 else .5
        # Consistencia micro: diferencia entre "se movió" y "está serruchando".
        # Un BUY rápido exige que los ticks recientes no sean mayoritariamente SELL,
        # aunque el cuerpo del minuto todavía siga verde (y viceversa).
        recent=[x for x in self.ticks if now-float(x.time)<=2.4]
        if len(recent)<3:
            recent=list(self.ticks)[-12:]
        diffs=[float(b.bid)-float(a.bid) for a,b in zip(recent[:-1],recent[1:])]
        travel=sum(abs(x) for x in diffs)
        consistency=(sum(diffs)/travel) if travel>1e-12 else 0.0
        nonzero=[x for x in diffs if abs(x)>1e-12]
        tick_balance=((sum(1 for x in nonzero if x>0)-sum(1 for x in nonzero if x<0))/len(nonzero)) if nonzero else 0.0
        micro=(float(recent[-1].bid)-float(recent[0].bid))/atr if len(recent)>=2 else 0.0
        micro_low=min((float(x.bid) for x in recent),default=float(bid))
        micro_high=max((float(x.bid) for x in recent),default=float(bid))
        direction=max(-2.0,min(2.0,1.05*body+.85*fast+.45*slow+.20*consistency+.12*pos_bias))
        minute_ticks=sum(1 for x in self.ticks if int(float(x.time)//60)==self.minute_bucket) if self.minute_bucket is not None else len(self.ticks)
        return {"body_atr":body,"fast_atr":fast,"slow_atr":slow,"range_pos":pos,
                "fast_span_seconds":fast_span,"slow_span_seconds":slow_span,
                "fast_velocity_atr_s":fast/fast_span,"slow_velocity_atr_s":slow/slow_span,
                "m5_body_atr":m5_body,"m5_range_pos":m5_pos,
                "ticks":len(self.ticks),"minute_ticks":minute_ticks,"direction":direction,"tick_consistency":consistency,
                "tick_balance":tick_balance,"micro_atr":micro,"micro_low":micro_low,"micro_high":micro_high,
                "open":float(self.minute_open or bid),"high":float(self.minute_high or bid),"low":float(self.minute_low or bid),
                "m5_open":float(self.five_open or bid),"m5_high":float(self.five_high or bid),"m5_low":float(self.five_low or bid)}

    def update(self,q,frames,now):
        if self.ticks and float(q.time)<float(self.ticks[-1].time):
            return self.levels if now-self.built<8 else []
        # The broker's tick time determines its candle. Wall-clock polling just
        # after a minute boundary must not invent a new candle from an old tick.
        bucket=int(float(q.time)//60)
        five_bucket=int(float(q.time)//300)
        m1,m5=frames.get("M1"),frames.get("M5")
        if self.minute_bucket!=bucket:
            self.minute_bucket=bucket
            self.minute_open=float(q.bid)
            self.minute_high=float(q.bid)
            self.minute_low=float(q.bid)
        else:
            self.minute_high=max(self.minute_high,float(q.bid))
            self.minute_low=min(self.minute_low,float(q.bid))
        if self.five_bucket!=five_bucket:
            self.five_bucket=five_bucket
            self.five_open=float(q.bid)
            self.five_high=float(q.bid)
            self.five_low=float(q.bid)
            self.five_pullback={1:None,-1:None}
            self.five_retest_anchor={1:None,-1:None}
        else:
            if m1 and m5:
                # Registrar el extremo ANTERIOR al retroceso, nunca el nuevo
                # mínimo/máximo. Sin un retroceso real no hay permiso de rebreak.
                retrace=max(float(m1.atr)*.18,float(q.spread)*2.5)
                impulse=float(m5.atr)*.45
                if self.five_open-self.five_low>=impulse and float(q.bid)-self.five_low>=retrace:
                    self.five_pullback[-1]=(self.five_low,now)
                    prev=self.five_retest_anchor[-1]
                    self.five_retest_anchor[-1]=max(float(q.bid),prev or float(q.bid))
                if self.five_high-self.five_open>=impulse and self.five_high-float(q.bid)>=retrace:
                    self.five_pullback[1]=(self.five_high,now)
                    prev=self.five_retest_anchor[1]
                    self.five_retest_anchor[1]=min(float(q.bid),prev or float(q.bid))
            self.five_high=max(self.five_high,float(q.bid))
            self.five_low=min(self.five_low,float(q.bid))
        if not self.ticks or quote_identity(q)!=quote_identity(self.ticks[-1]):
            self.ticks.append(q)
        while self.ticks and now-self.ticks[0].time>35:
            self.ticks.popleft()
        if not m1 or not m5:
            return []
        self.last_metrics=self.metrics(m1.atr,now,float(q.bid),m5.atr)
        for side,label in ((-1,'sell'),(1,'buy')):
            anchor=self.five_retest_anchor.get(side)
            if anchor is not None:
                self.last_metrics[f'retest_{label}_anchor']=float(anchor)
        for side,label in ((-1,"sell"),(1,"buy")):
            pullback=self.five_pullback.get(side)
            rebreak=False
            if pullback and now-float(pullback[1])>=.35:
                anchor=float(pullback[0]); distance=side*(float(q.bid)-anchor)
                rebreak=(max(float(q.spread)*.5,float(m1.atr)*.04)<=distance<=float(m1.atr)*.25 and
                         side*float(self.last_metrics.get("fast_atr",0.0))>=.006 and
                         side*float(self.last_metrics.get("tick_consistency",0.0))>=.12)
            self.last_metrics[f"pullback_{label}_rebreak"]=bool(rebreak)
        return []
