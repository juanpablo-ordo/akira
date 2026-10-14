"""Contexto técnico calculado una vez por vela cerrada; sin E/S ni red."""
import math


def ema(values,n):
    out=values[0]
    for x in values[1:]: out+=2/(n+1)*(x-out)
    return out


def enrich(bars,atr):
    close=[b.close for b in bars]
    typical=[(b.high+b.low+b.close)/3 for b in bars]
    volumes=[b.volume for b in bars]
    window=bars[-14:]
    hi,lo=max(b.high for b in window),min(b.low for b in window)
    stochastic=100*(close[-1]-lo)/max(hi-lo,1e-10)
    mean=sum(typical[-20:])/20
    dev=sum(abs(x-mean) for x in typical[-20:])/20
    cci=(typical[-1]-mean)/max(.015*dev,1e-10)
    positive=negative=0.0
    obv=[0.0]
    for i in range(1,len(bars)):
        sign=1 if close[i]>close[i-1] else -1 if close[i]<close[i-1] else 0
        obv.append(obv[-1]+sign*volumes[i])
        if i>=len(bars)-14:
            flow=typical[i]*volumes[i]
            if typical[i]>typical[i-1]: positive+=flow
            elif typical[i]<typical[i-1]: negative+=flow
    mfi=100-100/(1+positive/negative) if negative else 100 if positive else 50
    day=bars[-1].time//86400
    session=[(b,t) for b,t in zip(bars,typical) if b.time//86400==day]
    weight=sum(max(b.volume,1) for b,_ in session)
    vwap=sum(t*max(b.volume,1) for b,t in session)/weight
    trs=[]; plus=[]; minus=[]
    for a,b in zip(bars[:-1],bars[1:]):
        trs.append(max(b.high-b.low,abs(b.high-a.close),abs(b.low-a.close)))
        up,down=b.high-a.high,a.low-b.low
        plus.append(up if up>down and up>0 else 0)
        minus.append(down if down>up and down>0 else 0)
    tr=sum(trs[:14]); p=sum(plus[:14]); m=sum(minus[:14]); dx=[]
    for i in range(14,len(trs)):
        tr=tr-tr/14+trs[i]; p=p-p/14+plus[i]; m=m-m/14+minus[i]
        dip,dim=100*p/max(tr,1e-10),100*m/max(tr,1e-10)
        dx.append(100*abs(dip-dim)/max(dip+dim,1e-10))
    adx=sum(dx[:14])/max(len(dx[:14]),1)
    for x in dx[14:]: adx=(13*adx+x)/14
    prior=bars[-6:-1]; last=bars[-1]
    top,bottom=max(b.high for b in prior),min(b.low for b in prior)
    bos=1 if last.close>top else -1 if last.close<bottom else 0
    sweep=1 if last.low<bottom and last.close>bottom else -1 if last.high>top and last.close<top else 0
    range_hi=max(b.high for b in bars[-50:]); range_lo=min(b.low for b in bars[-50:])
    return {"ema50":ema(close,50),"ema200":ema(close,200),"ema200_warm":len(close)>=200,
            "adx":adx,"stochastic":stochastic,"williams":stochastic-100,"cci":cci,"mfi":mfi,
            "roc":100*(close[-1]/close[-4]-1),"obv_slope":(obv[-1]-obv[-6])/max(sum(volumes[-5:]),1),
            "vwap":vwap,"vwap_bars":len(session),"bos":bos,"sweep":sweep,
            "fib382":range_hi-(range_hi-range_lo)*.382,"fib50":(range_hi+range_lo)/2,
            "fib618":range_hi-(range_hi-range_lo)*.618,"range_hi":range_hi,"range_lo":range_lo}


def context_vote(extra,side,price,atr):
    trend=(1 if side*(price-extra["ema50"])>0 else -1)+(1 if side*(extra["ema50"]-extra["ema200"])>0 else -1)
    momentum=(side*max(-1,min(1,extra["cci"]/150))+side*max(-1,min(1,extra["roc"]*10)))/2
    volume=(side*extra["obv_slope"]+side*(extra["mfi"]-50)/50)/2
    structure=2 if extra["bos"]==side or extra["sweep"]==side else 0
    return max(-5,min(6,trend+momentum+volume+structure))
