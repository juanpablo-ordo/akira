"""Independent broker/session/quote/analysis facts. No orders or fabricated bars."""
from datetime import datetime, timezone
import math
from market_calendar import state_for

PERIOD_SECONDS={'M1':60,'M5':300,'M15':900,'M30':1800,'H1':3600,'H4':14400,'D1':86400,'W1':604800}

def value(obj,key,default=None):
    return obj.get(key,default) if isinstance(obj,dict) else getattr(obj,key,default)

class TimeSynchronizationService:
    @staticmethod
    def tick(tick,now,max_age=10):
        try:
            stamp=float(value(tick,'time_msc',0) or 0)/1000 or float(value(tick,'time',0) or 0)
            bid,ask=float(value(tick,'bid')),float(value(tick,'ask'))
            if not all(math.isfinite(v) for v in (stamp,bid,ask)) or stamp<=0 or bid<=0 or ask<bid:raise ValueError()
        except (ValueError,TypeError):return {'state':'MISSING','reason':'Cotización MT5 ausente o inválida','time':None,'age_seconds':None}
        age=now-stamp
        return {'state':'FRESH' if -2<=age<=max_age else 'STALE','time':stamp,'age_seconds':age,
                'clock_error':age < -2,'reason':'Reloj/tick futuro' if age < -2 else 'Cotización desactualizada' if age>max_age else ''}

class MarketStateResolver:
    @staticmethod
    def resolve(symbol,now,config,terminal=None,account=None,info=None,tick=None,rejection=None):
        calendar=state_for(symbol,datetime.fromtimestamp(now,timezone.utc),config)
        quote=TimeSynchronizationService.tick(tick,now,config.get('strategy',{}).get('max_tick_age_seconds',10))
        connected=bool(value(terminal,'connected',False)) and account is not None
        permissions=connected and bool(value(terminal,'trade_allowed',False)) and not value(terminal,'tradeapi_disabled',False) and bool(value(account,'trade_allowed',False)) and bool(value(account,'trade_expert',False))
        mode=value(info,'trade_mode');reason='';session='UNKNOWN';source='MT5: permisos y cotización; aceptación definitiva en order_send'
        if not connected:reason='Sesión MT5 no disponible'
        elif info is None:reason='Símbolo sin información MT5'
        elif mode==0:session,reason='DISABLED','MT5 deshabilitó este símbolo'
        elif mode==3:session,reason='CLOSE_ONLY','MT5 permite únicamente cierres'
        elif rejection and rejection.get('code')==10018 and 0<=now-rejection.get('at',0)<30:
            session,reason,source='CLOSED','MT5 rechazó una solicitud: mercado cerrado','Respuesta vigente del servidor MT5 (10018)'
        elif calendar.state.startswith('CIERRE EXTRAORDINARIO'):session,reason,source='CLOSED',calendar.state,calendar.source
        elif quote['state']=='FRESH' and mode in (1,2,4):session='OPEN'
        elif not calendar.open:session,reason,source='CLOSED',calendar.state,calendar.source
        else:reason=quote['reason'] or 'Disponibilidad de sesión por comprobar'
        execution='READY' if permissions else 'BROKER_UNAVAILABLE' if not connected else 'ORDER_REJECTED'
        labels={'OPEN':'ABIERTO','CLOSED':'MERCADO CERRADO','CLOSE_ONLY':'SOLO CIERRES','DISABLED':'SÍMBOLO DESHABILITADO','UNKNOWN':'SESIÓN POR COMPROBAR'}
        from locale_time import LocaleTimeSettings
        next_open=LocaleTimeSettings.from_config(config).format(calendar.next_open_utc.timestamp()) if calendar.next_open_utc else ''
        return {'open':session=='OPEN','session':session,'state':labels[session],'reason':reason,
                'quote':quote,'execution':execution,'permissions':permissions,'trade_mode':mode,
                'scheduled_closed':not calendar.open,'schedule_source':calendar.source,
                'next_open':next_open,'source':source,'checked_at':now,
                'execution_confirmed':False}

class BrokerSessionService:
    """Read each symbol once per engine cycle; no public Internet dependency."""
    def __init__(self,gateway):self.gateway=gateway;self.states={}
    def refresh(self,symbol,snapshot=None):
        g=self.gateway;snapshot=snapshot or g.snapshot()
        info=g.api.symbol_info(symbol)
        if info is not None and value(info,'visible',True) is False:
            g.api.symbol_select(symbol,True);info=g.api.symbol_info(symbol)
        state=MarketStateResolver.resolve(symbol,g.clock(),g.cfg,snapshot.terminal,snapshot.account,info,
                g.api.symbol_info_tick(symbol),(getattr(g,'session_rejections',{}) or {}).get(symbol))
        self.states[symbol]=state
        return state

def interval_has_session(symbol,start,end,config):
    # Schedules contextualize a missing bar. Never synthesize an OHLC row.
    # Five-minute probes also see short Sunday/daily reopenings within H1/H4.
    cursor=start+min(1,(end-start)/2)
    while cursor<end:
        if state_for(symbol,datetime.fromtimestamp(cursor,timezone.utc),config).open:return True
        cursor+=min(300,max(1,end-start))
    return state_for(symbol,datetime.fromtimestamp(end-.001,timezone.utc),config).open

class MarketDataFreshnessValidator:
    @staticmethod
    def expected_closed(symbol,timeframe,now,config):
        period=PERIOD_SECONDS[timeframe]
        # Unix epoch starts on Thursday; W1 opens Monday in UTC.
        anchor=345600 if timeframe=='W1' else 0
        latest=((int(now)-anchor)//period)*period+anchor-period
        for _ in range(max(3,10*86400//period)):
            if interval_has_session(symbol,latest,latest+period,config):return latest
            latest-=period
        return None

    @classmethod
    def inspect(cls,symbol,timeframe,frame,now,config,grace=5):
        bars=value(frame,'bars',()) or ()
        expected=cls.expected_closed(symbol,timeframe,now,config)
        last=value(bars[-1],'time') if bars else None
        state='MISSING';reason=f'DATOS {timeframe} AUSENTES'
        if last is not None:
            period=PERIOD_SECONDS[timeframe];last=float(last)
            if last+period>now+2:state,reason='INVALID',f'Vela {timeframe} todavía abierta o reloj incorrecto'
            elif expected is None:state,reason='STALE',f'Sesión {timeframe} sin referencia verificable'
            elif last>=expected or (0<=now-(expected+period)<=grace and last>=expected-period):state,reason='FRESH','Última vela cerrada disponible según sesión UTC'
            else:state,reason='STALE',f'DATOS {timeframe} DESACTUALIZADOS: solicitar historial MT5'
        return {'state':state,'ready':state=='FRESH','timeframe':timeframe,'last_open_utc':last,
                'expected_open_utc':expected,'reason':reason,'analysis':'READY' if state=='FRESH' else 'WAITING_CANDLE'}

class CandleGapRecovery:
    """Bounded retries on the MT5 actor. A read never hides another data error."""
    def __init__(self):self.attempts={};self.next_retry={};self.status={}
    def recover(self,api,symbol,tf,name,now,config,count=320):
        key=(symbol,name)
        if now<self.next_retry.get(key,0):return None
        n=self.attempts.get(key,0)+1;self.attempts[key]=n
        self.next_retry[key]=now+min(60,2**min(n,6))
        rows=None;error=''
        try:
            if hasattr(api,'copy_rates_range'):
                period=PERIOD_SECONDS[name]
                rows=api.copy_rates_range(symbol,tf,datetime.fromtimestamp(now-period*(count+3),timezone.utc),datetime.fromtimestamp(now,timezone.utc))
                if rows is not None:
                    rows=[r for r in rows if float(r['time'])+period<=now+2][-count:]
            if rows is None or not len(rows):rows=api.copy_rates_from_pos(symbol,tf,1,count)
        except (ValueError,TypeError,RuntimeError,OSError) as exc:error=f'{type(exc).__name__}: {exc}'
        self.status[name]={'attempt':n,'at':now,'next_retry':self.next_retry[key],
                           'rows':len(rows) if rows is not None else 0,'error':error}
        return rows
    def succeeded(self,symbol,name):
        self.attempts.pop((symbol,name),None);self.next_retry.pop((symbol,name),None)
