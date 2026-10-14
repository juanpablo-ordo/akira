"""Modelo auxiliar local V186 para M1/M5.

Entrena solo con velas cerradas, separación cronológica y omite movimientos
neutros muy pequeños. La salida es una señal auxiliar: no es probabilidad de
beneficio y solo entra en la fusión si supera al baseline por margen real.
"""
import math


def sigmoid(x): return 1/(1+math.exp(-max(-30,min(30,x))))


def _atr(rows,i,period=14):
    start=max(1,i-period+1); trs=[]
    for j in range(start,i+1):
        a,b=rows[j-1],rows[j]
        trs.append(max(float(b["high"])-float(b["low"]),
                       abs(float(b["high"])-float(a["close"])),
                       abs(float(b["low"])-float(a["close"]))))
    return max(sum(trs)/max(len(trs),1),1e-9)


def features(rows,i):
    w=rows[i-30:i+1]; c=[float(b["close"]) for b in w]
    r=_atr(rows,i)
    v=sum(float(b.get("volume",0)) for b in w[-14:])/14
    last=w[-1]; prev=w[-2]
    body=(float(last["close"])-float(last["open"]))/r
    rng=max(float(last["high"])-float(last["low"]),1e-9)
    upper=(float(last["high"])-max(float(last["open"]),float(last["close"])))/rng
    lower=(min(float(last["open"]),float(last["close"]))-float(last["low"]))/rng
    vol=float(last.get("volume",0))/max(v,1)-1
    fast=sum(c[-5:])/5; slow=sum(c[-20:])/20
    return [
        (c[-1]-c[-2])/r,
        (c[-1]-c[-4])/r,
        (c[-1]-c[-10])/r,
        (fast-slow)/r,
        body,
        (float(last["high"])-float(last["low"]))/r,
        upper-lower,
        vol,
        (float(last["close"])-float(prev["close"]))/max(float(prev["high"])-float(prev["low"]),r*.25),
    ]


def train_report(rows,timeframe="M5"):
    minimum=240
    if len(rows)<minimum:
        return {"state":f"esperando {minimum} velas {timeframe} cerradas","timeframe":timeframe}
    data=[]; neutral=0
    for i in range(30,len(rows)-1):
        r=_atr(rows,i)
        move=(float(rows[i+1]["close"])-float(rows[i]["close"]))/r
        # No enseñar ruido minúsculo como BUY/SELL obligatorio.
        threshold=.10 if timeframe=="M1" else .08
        if abs(move)<threshold:
            neutral+=1; continue
        data.append((features(rows,i),int(move>0)))
    if len(data)<100:
        return {"state":f"pocas velas direccionales {timeframe}","timeframe":timeframe,"samples":len(data)}
    cut=int(len(data)*.70)
    train,test=data[:cut],data[cut+4:]
    if len(train)<60 or len(test)<25:
        return {"state":f"historial direccional {timeframe} insuficiente","timeframe":timeframe}
    dims=len(train[0][0])
    means=[sum(x[j] for x,_ in train)/len(train) for j in range(dims)]
    scales=[max((sum((x[j]-means[j])**2 for x,_ in train)/len(train))**.5,.1) for j in range(dims)]
    def norm(x): return [1.0]+[max(-8,min(8,(x[j]-means[j])/scales[j])) for j in range(dims)]
    train=[(norm(x),y) for x,y in train]; test=[(norm(x),y) for x,y in test]
    weights=[0.0]*(dims+1)
    for _ in range(90):
        grad=[0.0]*len(weights)
        for x,y in train:
            e=sigmoid(sum(a*b for a,b in zip(x,weights)))-y
            for j in range(len(weights)): grad[j]+=e*x[j]
        for j in range(len(weights)):
            weights[j]-=.055*(grad[j]/len(train)+(.04*weights[j] if j else 0))
    probs=[sigmoid(sum(a*b for a,b in zip(x,weights))) for x,_ in test]
    accuracy=sum((p>=.5)==bool(y) for p,(_,y) in zip(probs,test))/len(test)
    majority=int(sum(y for _,y in train)>=len(train)/2)
    baseline=sum(y==majority for _,y in test)/len(test)
    p=sigmoid(sum(a*b for a,b in zip(norm(features(rows,len(rows)-1)),weights)))
    advantage=accuracy-baseline
    coverage=len(data)/max(1,(len(rows)-31))
    # Requiere ventaja material y una señal actual no ambigua.
    better=advantage>=.02 and len(test)>=25
    usable=better and abs(p-.5)>=.06
    return {"state":"auxiliar V186; validación cronológica con zona neutral","timeframe":timeframe,
            "next_direction":"BUY" if p>=.5 else "SELL","model_output":p,
            "test_accuracy":accuracy,"baseline":baseline,"advantage":advantage,
            "train":len(train),"test":len(test),"coverage":coverage,"neutral_skipped":neutral,
            "better_than_baseline":better,"usable_signal":usable,"last_bar":rows[-1]["time"],
            "meaning":f"Clasifica movimiento direccional siguiente {timeframe}; omite ruido y no es probabilidad de alcanzar TP."}
