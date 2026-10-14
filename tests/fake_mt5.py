"""Servidor de pruebas: ninguna conexión ni cuenta real."""
from types import SimpleNamespace as NS
import math
from execution import BUY,SELL,DEAL,PENDING,SLTP,MODIFY,REMOVE,OWN_PENDING,LEGACY_POSITIONS


class Clock:
    def __init__(self): self.now=1800000000.0
    def __call__(self): return self.now
    def advance(self,seconds): self.now+=seconds


class FakeMT5:
    def __init__(self,clock):
        self.clock=clock
        self.positions=[]
        self.orders=[]
        self.deals=[]
        self.history_orders=[]
        self.sent=[]
        self.rate_calls=[]
        self.serial=100
        self.fail_positions=False
        self.hide_positions=False
        self.fail_history=False
        self.fail_check=0
        self.send_retcode=None
        self.drop_ack=False
        self.no_effect=False
        self.fill_on_cancel=False
        self.partial_close=False
        self.account=NS(login=123,server="TEST",margin_mode=2,balance=100.0,equity=100.0,margin=0.0,
                        margin_free=100.0,trade_mode=2,trade_allowed=True,trade_expert=True,currency="USD")
        self.terminal=NS(connected=True,trade_allowed=True,tradeapi_disabled=False)
        self.infos={}
        self.ticks={}
        self.rates={}
        for symbol,base,scale,spread in (("BTCUSDm",60000,10,1),("XAUUSDm",2500,.25,.04)):
            self.infos[symbol]=NS(trade_tick_size=.01,point=.01,trade_stops_level=1,trade_freeze_level=0,
                volume_step=.01,volume_min=.01,volume_max=100,trade_mode=4,order_mode=63,
                trade_exemode=2,filling_mode=3,expiration_mode=1)
            for tf,secs in ((1,60),(5,300),(15,900),(30,1800),(16385,3600),(16388,14400),(16408,86400),(32769,604800)):
                end=int(clock()//secs)*secs-secs
                rows=[]
                for i in range(180):
                    c=base+(i-179)*scale*.15+math.sin(i*.5)*scale*.14
                    o=c-scale*.11
                    rows.append(dict(time=end-(179-i)*secs,open=o,close=c,high=c+scale*.4,
                                     low=o-scale*.4,tick_volume=100))
                self.rates[symbol,tf]=rows
            bid=self.rates[symbol,1][-1]["close"]
            self.set_quote(symbol,bid,spread,fill=False)

    def last_error(self): return (0,"test")
    def account_info(self): return self.account
    def terminal_info(self): return self.terminal
    def symbol_info(self,symbol): return self.infos.get(symbol)
    def symbol_select(self,*args): return True
    def symbol_info_tick(self,symbol): return self.ticks.get(symbol)
    def positions_get(self,**kwargs):
        if self.fail_positions: return None
        rows=[] if self.hide_positions else self.positions
        return tuple(p for p in rows if not kwargs.get("symbol") or p.symbol==kwargs["symbol"])
    def orders_get(self,**kwargs):
        return tuple(o for o in self.orders if not kwargs.get("symbol") or o.symbol==kwargs["symbol"])
    def history_deals_get(self,*args,**kwargs):
        if self.fail_history: return None
        if "position" in kwargs:
            return tuple(d for d in self.deals if int(d.position_id)==int(kwargs["position"]))
        if args:
            start,end=args[0].timestamp(),args[1].timestamp()
            return tuple(d for d in self.deals if start<=d.time<=end)
        return tuple(self.deals)
    def history_orders_get(self,*args,**kwargs):
        return tuple(o for o in self.history_orders if "ticket" not in kwargs or o.ticket==kwargs["ticket"])
    def copy_rates_from_pos(self,symbol,tf,start,count):
        assert start==1,"No usar velas vivas para calcular indicadores"
        self.rate_calls.append((symbol,tf,start,count))
        rows=self.rates.get((symbol,tf),[])
        return rows[-count:]
    def order_calc_profit(self,typ,symbol,volume,entry,exit):
        contract=100 if symbol=="XAUUSDm" else 1
        return (exit-entry)*(1 if typ==BUY else -1)*volume*contract
    def order_calc_margin(self,typ,symbol,volume,price): return 1.0
    def order_check(self,r):
        if self.fail_check: return NS(retcode=self.fail_check,comment="rechazo solicitado")
        if r["action"]==PENDING:
            assert r["type_filling"]==2,"pendiente requiere RETURN"
        if r["action"]==DEAL and self.infos[r["symbol"]].trade_exemode==2:
            assert "price" not in r,"Market Execution omite precio"
            assert r["type_filling"]!=2,"Market Execution no permite RETURN"
        return NS(retcode=0,comment="OK")

    def set_quote(self,symbol,bid,spread=None,fill=True):
        if spread is None:
            before=self.ticks[symbol]
            spread=before.ask-before.bid
        self.ticks[symbol]=NS(bid=bid,ask=bid+spread,time=int(self.clock()),time_msc=int(self.clock()*1000))
        if fill:
            for order in list(self.orders):
                q=self.ticks[symbol]
                if order.symbol!=symbol: continue
                hit=(order.type==2 and q.ask<=order.price_open) or (order.type==3 and q.bid>=order.price_open) or (
                     order.type==4 and q.ask>=order.price_open) or (order.type==5 and q.bid<=order.price_open)
                if hit: self.fill_order(order)
        self.revalue()

    def revalue(self):
        for p in self.positions:
            q=self.ticks[p.symbol]
            p.profit=self.order_calc_profit(p.type,p.symbol,p.volume,p.price_open,q.bid if p.type==BUY else q.ask)
        self.account.equity=self.account.balance+sum(p.profit+p.swap for p in self.positions)
        self.account.margin_free=self.account.equity-self.account.margin

    def add_position(self,symbol="BTCUSDm",side=BUY,entry=None,sl=None,tp=None,magic=170001,volume=.01,ticket=None,comment="test"):
        self.serial+=1
        q=self.ticks[symbol]
        entry=entry if entry is not None else (q.ask if side==BUY else q.bid)
        scale=10 if symbol=="BTCUSDm" else .25
        p=NS(ticket=ticket or self.serial,identifier=ticket or self.serial,symbol=symbol,type=side,
             price_open=entry,volume=volume,sl=sl if sl is not None else entry+(-2*scale if side==BUY else 2*scale),
             tp=tp if tp is not None else entry+(4*scale if side==BUY else -4*scale),
             magic=magic,profit=0.0,swap=0.0,time=self.clock(),comment=comment)
        self.positions.append(p)
        self.revalue()
        return p

    def add_pending(self,plan,magic=OWN_PENDING):
        self.serial+=1
        typ=(2 if plan.side==1 else 3) if plan.kind=="LIMIT" else (4 if plan.side==1 else 5)
        o=NS(ticket=self.serial,symbol=plan.symbol,type=typ,price_open=plan.entry,sl=plan.sl,tp=plan.tp,
             volume_current=.01,volume_initial=.01,time_setup=self.clock(),magic=magic,comment="old")
        self.orders.append(o)
        return o

    def record_deal(self,p,entry,volume,profit=0):
        self.serial+=1
        d=NS(ticket=self.serial,position_id=p.identifier,order=p.identifier,entry=entry,volume=volume,
             type=p.type if entry==0 else 1-p.type,symbol=p.symbol,magic=p.magic,profit=profit,
             commission=0.0,fee=0.0,swap=0.0,time=self.clock(),comment=p.comment)
        self.deals.append(d)
        return d

    def fill_order(self,o):
        self.orders.remove(o)
        p=self.add_position(o.symbol,o.type%2,o.price_open,o.sl,o.tp,o.magic,o.volume_current,o.ticket,o.comment)
        self.history_orders.append(NS(ticket=o.ticket,symbol=o.symbol,comment=o.comment,state=4,position_id=o.ticket))
        self.record_deal(p,0,p.volume)
        return p

    def order_send(self,r):
        self.sent.append(dict(r))
        if self.send_retcode and self.send_retcode not in (10008,10009,10010):
            return NS(retcode=self.send_retcode,order=0,deal=0,comment="rechazo solicitado")
        if self.no_effect: return None
        order_id=0
        deal_id=0
        code=10009
        if r["action"]==PENDING:
            self.serial+=1
            order_id=self.serial
            self.orders.append(NS(ticket=order_id,symbol=r["symbol"],type=r["type"],price_open=r["price"],
                                  sl=r["sl"],tp=r["tp"],volume_current=r["volume"],volume_initial=r["volume"],
                                  time_setup=self.clock(),magic=r["magic"],comment=r["comment"]))
            code=10008
        elif r["action"]==MODIFY:
            found=[o for o in self.orders if o.ticket==r["order"]]
            if found:
                o=found[0]
                o.price_open=float(r["price"]); o.sl=float(r["sl"]); o.tp=float(r["tp"])
            else:
                return NS(retcode=10013,order=0,deal=0,comment="orden no encontrada")
        elif r["action"]==REMOVE:
            found=[o for o in self.orders if o.ticket==r["order"]]
            if found:
                o=found[0]
                if self.fill_on_cancel:
                    self.fill_on_cancel=False
                    self.fill_order(o)
                    return NS(retcode=10036,order=0,deal=0,comment="se activó antes de cancelar")
                self.orders.remove(o)
                self.history_orders.append(NS(ticket=o.ticket,symbol=o.symbol,comment=o.comment,state=2,position_id=0))
        elif r["action"]==SLTP:
            p=next(p for p in self.positions if p.ticket==r["position"])
            p.sl,p.tp=r["sl"],r["tp"]
        elif r["action"]==DEAL:
            if "position" in r:
                p=next(p for p in self.positions if p.ticket==r["position"])
                volume=r["volume"]/2 if self.partial_close else r["volume"]
                profit=p.profit*volume/p.volume
                deal_id=self.record_deal(p,1,volume,profit).ticket
                self.account.balance+=profit
                p.volume-=volume
                if p.volume<=1e-10: self.positions.remove(p)
                else: code=10010
                self.revalue()
            else:
                self.serial+=1
                order_id=self.serial
                p=self.add_position(r["symbol"],r["type"],sl=r["sl"],tp=r["tp"],magic=r["magic"],volume=r["volume"],ticket=order_id,comment=r["comment"])
                deal_id=self.record_deal(p,0,p.volume).ticket
                self.history_orders.append(NS(ticket=order_id,symbol=p.symbol,comment=p.comment,state=4,position_id=p.identifier))
        return None if self.drop_ack else NS(retcode=code,order=order_id,deal=deal_id,comment="OK")
