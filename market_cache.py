from collections import Counter
from strategy import Bar,frame,build_setups,symbol_strategy

def _compute_frame_and_setups(name,bars,other_frames,rules):
    """Pure CPU work: no MT5, journal, or UI calls in a worker thread."""
    current=frame(name,bars)
    frames={**other_frames,name:current}
    setups,rejections=build_setups(frames,rules)
    return current,setups,rejections

class MarketCache:
    PERIODS={"M1":(1,.20),"M5":(5,.70),"M15":(15,1.8),"M30":(30,2.5),"H1":(16385,4.0),
             "H4":(16388,10.0),"D1":(16408,30.0),"W1":(32769,90.0)}

    def __init__(self,api,symbol,reporter,cfg):
        self.api,self.symbol,self.log,self.cfg=api,symbol,reporter,cfg
        self.frames={}
        self.due={name:0.0 for name in self.PERIODS}
        self.setups=[]
        self.rejections=Counter()
        self.errors={}
        self.analysis_executor=None
        self.analysis_future=None
        self.analysis_name=None
        self.analysis_signature=()

    def poll_analysis(self):
        future=self.analysis_future
        if future is None or not future.done(): return
        name=self.analysis_name
        self.analysis_future=None; self.analysis_name=None
        try:
            current,setups,rejections=future.result()
            signature=tuple((k,f.bars[-1].time) for k,f in self.frames.items() if k!=name)
            self.frames[name]=current
            if signature!=self.analysis_signature:
                # Si warmup/otra revisión añadió H4/D1 mientras este cálculo
                # estaba en vuelo, no publicar setups hechos con un mapa viejo.
                setups,rejections=build_setups(self.frames,symbol_strategy(self.cfg,self.symbol))
            self.setups,self.rejections=setups,rejections
            self.errors.pop(name,None)
        except (ValueError,TypeError,KeyError,IndexError) as exc:
            self.errors[name]=str(exc)
            self.log.report(self.symbol,'DATOS',f'{name}: {exc}')

    @staticmethod
    def bars(rows):
        return tuple(Bar(int(r["time"]),float(r["open"]),float(r["high"]),float(r["low"]),
                         float(r["close"]),float(r["tick_volume"])) for r in rows)

    def closed_rates(self,tf,count=320):
        """Obtiene velas cerradas con fallback de arranque frío de MT5.

        Algunos terminales devuelven `None` temporalmente para start_pos=1 justo
        después de seleccionar el símbolo. En ese caso pedimos desde la vela viva
        y descartamos la última; así Akira no se queda eternamente en CARGANDO M1/M5.
        """
        rows=self.api.copy_rates_from_pos(self.symbol,tf,1,count)
        if rows is not None and len(rows)>0:
            return rows
        alt=self.api.copy_rates_from_pos(self.symbol,tf,0,count+1)
        if alt is not None and len(alt)>1:
            return alt[:-1]
        return rows

    def advance(self,now,allowed=None):
        self.poll_analysis()
        if self.analysis_future is not None:
            return
        # Una consulta de timeframe por vuelta. Un refresco H4 no retrasa a cada tick.
        allowed_set=set(allowed) if allowed else None
        due=[name for name in self.PERIODS if now>=self.due[name] and (allowed_set is None or name in allowed_set)]
        if not due:
            return
        name=min(due,key=lambda k:self.due[k])
        tf,interval=self.PERIODS[name]
        self.due[name]=now+interval
        try:
            old=self.frames.get(name)
            rows=self.closed_rates(tf,1 if old else 320)
            if rows is None or len(rows)==0:
                raise ValueError(f"sin historial: {self.api.last_error()}")
            if old and int(rows[-1]["time"])==old.bars[-1].time:
                self.errors.pop(name,None)
                return
            if old:
                rows=self.closed_rates(tf,320)
                if rows is None:
                    raise ValueError(f"historial incompleto: {self.api.last_error()}")
            if self.analysis_executor is not None:
                self.analysis_name=name
                self.analysis_signature=tuple((k,f.bars[-1].time) for k,f in self.frames.items() if k!=name)
                self.analysis_future=self.analysis_executor.submit(
                    _compute_frame_and_setups,name,self.bars(rows),dict(self.frames),
                    symbol_strategy(self.cfg,self.symbol))
            else:
                self.frames[name]=frame(name,self.bars(rows))
                self.errors.pop(name,None)
                self.setups,self.rejections=build_setups(self.frames,symbol_strategy(self.cfg,self.symbol))
        except (ValueError,TypeError,KeyError,IndexError) as exc:
            self.errors[name]=str(exc)
            self.due[name]=now+3
            self.log.report(self.symbol,"DATOS",f"{name}: {exc}")


    def prime_fast_structural(self,now):
        """Carga solo M15/H1 para publicar y ejecutar el primer mapa cuanto antes.

        H4/D1 siguen siendo importantes, pero no deben bloquear la primera decisión.
        El scheduler los incorpora inmediatamente después y reconstruye el mapa.
        """
        result={}
        for name in ("M15","H1"):
            tf,interval=self.PERIODS[name]
            try:
                rows=self.closed_rates(tf,320)
                if rows is None or len(rows)==0:
                    raise ValueError(f"sin historial: {self.api.last_error()}")
                self.frames[name]=frame(name,self.bars(rows))
                self.errors.pop(name,None);self.due[name]=now+interval
                result[name]=f"OK · {len(rows)} velas"
            except (ValueError,TypeError,KeyError,IndexError) as exc:
                self.errors[name]=str(exc);self.due[name]=now+.35;result[name]=str(exc)
        if "M1" in self.frames and "M5" in self.frames:
            try:self.setups,self.rejections=build_setups(self.frames,symbol_strategy(self.cfg,self.symbol))
            except (ValueError,TypeError,KeyError,IndexError) as exc:self.log.report(self.symbol,"DATOS",f"warmup FAST MTF: {exc}")
        return result

    def prime_deep_structural(self,now):
        """Carga M30/H4/D1 sin convertirlos en una barrera de arranque."""
        result={}
        for name in ("M30","H4","D1"):
            tf,interval=self.PERIODS[name]
            try:
                rows=self.closed_rates(tf,320)
                if rows is None or len(rows)==0:
                    raise ValueError(f"sin historial: {self.api.last_error()}")
                self.frames[name]=frame(name,self.bars(rows))
                self.errors.pop(name,None);self.due[name]=now+interval
                result[name]=f"OK · {len(rows)} velas"
            except (ValueError,TypeError,KeyError,IndexError) as exc:
                self.errors[name]=str(exc);self.due[name]=now+.8;result[name]=str(exc)
        if "M1" in self.frames and "M5" in self.frames:
            try:self.setups,self.rejections=build_setups(self.frames,symbol_strategy(self.cfg,self.symbol))
            except (ValueError,TypeError,KeyError,IndexError) as exc:self.log.report(self.symbol,"DATOS",f"warmup DEEP MTF: {exc}")
        return result

    def prime_structural(self,now):
        """Carga M15/H1/H4/D1 inmediatamente para que el mapa de pendientes exista
        desde el arranque. No espera a que el scheduler visite esos marcos.
        """
        result={}
        for name in ("M15","M30","H1","H4","D1"):
            tf,interval=self.PERIODS[name]
            try:
                rows=self.closed_rates(tf,320)
                if rows is None or len(rows)==0:
                    raise ValueError(f"sin historial: {self.api.last_error()}")
                self.frames[name]=frame(name,self.bars(rows))
                self.errors.pop(name,None)
                self.due[name]=now+interval
                result[name]=f"OK · {len(rows)} velas"
            except (ValueError,TypeError,KeyError,IndexError) as exc:
                self.errors[name]=str(exc)
                self.due[name]=now+.8
                result[name]=str(exc)
        if "M1" in self.frames and "M5" in self.frames:
            try:
                self.setups,self.rejections=build_setups(self.frames,symbol_strategy(self.cfg,self.symbol))
            except (ValueError,TypeError,KeyError,IndexError) as exc:
                self.log.report(self.symbol,"DATOS",f"warmup HTF: {exc}")
        return result

    def prime_context(self,now):
        """Carga W1 después del primer mapa. D1 ya participó en el primer envío V193."""
        result={}
        for name in ("W1",):
            tf,interval=self.PERIODS[name]
            try:
                rows=self.closed_rates(tf,320)
                if rows is None or len(rows)==0:
                    raise ValueError(f"sin historial: {self.api.last_error()}")
                self.frames[name]=frame(name,self.bars(rows))
                self.errors.pop(name,None); self.due[name]=now+interval
                result[name]=f"OK · {len(rows)} velas"
            except (ValueError,TypeError,KeyError,IndexError) as exc:
                self.errors[name]=str(exc); self.due[name]=now+1.0; result[name]=str(exc)
        if self.frames:
            try:
                self.setups,self.rejections=build_setups(self.frames,symbol_strategy(self.cfg,self.symbol))
            except (ValueError,TypeError,KeyError,IndexError) as exc:
                self.log.report(self.symbol,"DATOS",f"warmup D1/W1: {exc}")
        return result

    def prime_critical(self,now):
        """Carga M1/M5 de forma prioritaria al arrancar.

        V193 podía mostrar "cargando" demasiado tiempo porque el primer ciclo
        recorría todos los timeframes/validaciones antes de publicar un estado útil.
        Aquí solo se calientan los dos marcos que `ready()` necesita; M15/H1/H4/D1/W1
        siguen entrando después por `advance()` sin bloquear la interfaz.
        """
        result={}
        for name in ("M1","M5"):
            tf,interval=self.PERIODS[name]
            try:
                rows=self.closed_rates(tf,320)
                if rows is None or len(rows)==0:
                    raise ValueError(f"sin historial: {self.api.last_error()}")
                self.frames[name]=frame(name,self.bars(rows))
                self.errors.pop(name,None)
                self.due[name]=now+interval
                result[name]=f"OK · {len(rows)} velas"
            except (ValueError,TypeError,KeyError,IndexError) as exc:
                self.errors[name]=str(exc)
                self.due[name]=now+.8
                result[name]=str(exc)
        if self.frames:
            try:
                self.setups,self.rejections=build_setups(self.frames,symbol_strategy(self.cfg,self.symbol))
            except (ValueError,TypeError,KeyError,IndexError) as exc:
                self.log.report(self.symbol,"DATOS",f"warmup: {exc}")
        return result

    def ready(self,now):
        for name,max_age in (("M1",150),("M5",660)):
            f=self.frames.get(name)
            if not f:
                return False,f"cargando {name}: {self.errors.get(name,'historial MT5')}"
            age=now-f.bars[-1].time
            if age>max_age or age<0:
                return False,f"{name} atrasado ({age:.0f}s) o reloj desajustado"
        return True,"OK"
