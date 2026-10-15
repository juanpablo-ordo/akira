"""Contexto externo/IA de Akira V10.

La red NUNCA está en la ruta crítica de order_send. Este worker actualiza en
segundo plano (máximo objetivo: 60 s) y persiste el último snapshot. Engine usa
ese cache de inmediato junto con precio/indicadores/tape/DOM actuales.

Fuentes externas rankean zonas HTF ya calculadas; no inventan Entry/SL/TP.
"""
import copy
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import math
import os
from pathlib import Path
import threading
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from akira_openai import responses as openai_responses
from akira_local_ai import chat as ollama_chat, status as ollama_status, choose_text_model
from urllib.parse import urlencode
import xml.etree.ElementTree as ET

from local_model import train_report
from akira_secrets import get_secret

FED="https://www.federalreserve.gov/feeds/press_monetary.xml"
INVESTING_FEEDS={
    "forex":"https://www.investing.com/rss/news_1.rss",
    "commodities":"https://www.investing.com/rss/news_11.rss",
    "economy":"https://www.investing.com/rss/news_14.rss",
    "indicators":"https://www.investing.com/rss/news_95.rss",
    "crypto":"https://www.investing.com/rss/news_301.rss",
}
METHODS={
    "structure":"Estructura M1→W1, swings, BOS, barridos, oferta/demanda, OB/FVG y Fibonacci",
    "momentum":"EMA9/21/50/200, MACD, RSI, ADX, ROC, VWAP, Bollinger, MFI, CCI y volumen de ticks",
    "micro":"Vela viva + ticks + DOM del bróker para timing; no crean zonas HTF",
    "coinglass":"BTC/XAU: intenta OI, funding, liquidaciones, ratios y orderbook cuando la API/plan lo permite",
    "youtube":"Transcripciones con fecha/fuente, análisis por fragmentos y memoria persistente; sin subtítulos queda marcado como no analizado",
    "investing":"RSS de mercados/economía/commodities/crypto como contexto de bajo peso",
    "ai":"Modelo local M5/M15/H1 + Akira Local Core contextual; OpenAI opcional",
    "risk":"Invalidación estructural, costes, margen y exposición total"
}
QUERIES={
    "XAUUSDm":("XAUUSD gold technical analysis liquidity support resistance",),
    "BTCUSDm":("Bitcoin BTC technical analysis liquidity breakout",)
}
POSITIVE=("bullish","breakout","rally","surge","upside","buy setup","long setup","support holds","recovery","higher high",
          "alcista","subida","compra","rompimiento alcista","recover","gain","gains")
NEGATIVE=("bearish","breakdown","crash","dump","downside","sell setup","short setup","resistance rejection","lower low",
          "bajista","caida","caída","venta","rompimiento bajista","drop","falls","fall")


def clamp(x,a=-1.0,b=1.0): return max(a,min(b,float(x)))
def fnum(x,default=0.0):
    try: return float(x)
    except (TypeError,ValueError): return default


def download(url,headers=None,body=None):
    request=Request(url,data=json.dumps(body).encode() if body is not None else None,
                    headers={"User-Agent":"AkiraResearch/171","Accept":"application/json, application/xml, text/xml, application/rss+xml",**(headers or {})})
    with urlopen(request,timeout=7) as response:
        raw=response.read(2_000_001)
        if len(raw)>2_000_000: raise ValueError("respuesta externa demasiado grande")
        return raw


def parse_rss(url,limit=10):
    root=ET.fromstring(download(url))
    rows=[]
    if root.tag.split('}')[-1] not in ('rss','RDF','feed'):raise ValueError('La fuente no devolvió un feed RSS o Atom')
    atom='{http://www.w3.org/2005/Atom}'
    entries=root.findall('.//item') or root.findall('.//'+atom+'entry') or root.findall('.//entry')
    for item in entries[:limit]:
        def value(name):
            node=item.find(name)
            if node is None:node=item.find(atom+name)
            return ''.join(node.itertext()).strip() if node is not None else ''
        links=item.findall(atom+'link') or item.findall('link')
        link=next((x.get('href') or ''.join(x.itertext()).strip() for x in links if x.get('rel','alternate')=='alternate'),'')
        rows.append({'title':value('title'),'url':link,'date':value('pubDate') or value('published') or value('updated')})
    return rows


def investing_bundle():
    out=[]; errors={}
    with ThreadPoolExecutor(max_workers=len(INVESTING_FEEDS),thread_name_prefix="akira_investing") as pool:
        jobs={pool.submit(parse_rss,url,8):name for name,url in INVESTING_FEEDS.items()}
        for future in as_completed(jobs):
            name=jobs[future]
            try:
                out.extend({**row,"category":name} for row in future.result())
            except Exception as exc:
                errors[name]=type(exc).__name__ if not isinstance(exc,RuntimeError) else str(exc)
    unique={row.get("url") or (row.get("category"),row.get("title")):row for row in out}
    return {"items":list(unique.values())[:35],"errors":errors}


def _http_error_detail(exc):
    try:
        raw=exc.read(300_000).decode("utf-8","replace")
        data=json.loads(raw) if raw else {}
        if isinstance(data,dict):
            err=data.get("error")
            if isinstance(err,dict):
                message=str(err.get("message") or "")
                errors=err.get("errors") or []
                reason=""
                if errors and isinstance(errors[0],dict):
                    reason=str(errors[0].get("reason") or "")
                return (message or raw),reason
            return str(data.get("msg") or data.get("message") or raw),str(data.get("code") or "")
        return raw,""
    except Exception:
        return str(exc),""


def _youtube_api_search(query,key):
    args={"part":"snippet","type":"video","q":query,"order":"date","maxResults":4,"key":key}
    url="https://www.googleapis.com/youtube/v3/search?"+urlencode(args)
    try:
        data=json.loads(download(url))
    except HTTPError as exc:
        detail,reason=_http_error_detail(exc)
        raise RuntimeError(f"YouTube API HTTP {exc.code}: {reason or detail[:350]}")
    return [{"title":x["snippet"]["title"],"author":x["snippet"]["channelTitle"],
             "date":x["snippet"].get("publishedAt",""),"description":x["snippet"].get("description",""),
             "url":"https://www.youtube.com/watch?v="+x["id"]["videoId"]}
            for x in data.get("items",[]) if isinstance(x,dict) and isinstance(x.get("id"),dict) and x["id"].get("videoId")]


def _youtube_ytdlp_search(query):
    try:
        import yt_dlp
    except ImportError:
        raise RuntimeError("yt-dlp no instalado; ejecuta INSTALAR_TODO_AKIRA_V10.bat")
    class Quiet:
        def debug(self,*args): pass
        def info(self,*args): pass
        def warning(self,*args): pass
        def error(self,*args): pass
    from youtube_support import options, explained
    try:
        with yt_dlp.YoutubeDL(options(extract_flat=True,socket_timeout=6,retries=0,extractor_retries=0,playlistend=4)) as ydl:
            data=ydl.extract_info("ytsearch4:"+query,download=False)
    except Exception as error:raise explained(error) from error
    return [{"title":x.get("title",""),"author":x.get("channel") or x.get("uploader", ""),
             "date":x.get("upload_date") or "fecha no suministrada",
             "description":x.get("description") or x.get("fulltitle") or "",
             "url":"https://www.youtube.com/watch?v="+x["id"]}
            for x in data.get("entries",[]) if x and x.get("id")]


def youtube_api_probe(query="Bitcoin technical analysis"):
    key=get_secret("YOUTUBE_API_KEY")
    if not key:
        return {"ok":False,"state":"sin_key"}
    try:
        rows=_youtube_api_search(query,key)
        return {"ok":True,"state":"api","count":len(rows)}
    except Exception as exc:
        return {"ok":False,"state":"api_error","error":str(exc)}


_YT_LOCK=threading.Lock()
_YT_CACHE={}
_YT_API_BLOCK_UNTIL=0.0

def youtube_search(query,cache_seconds=900):
    """YouTube de bajo peso, cacheado y nunca bloqueante.

    - Intenta Data API cuando no está temporalmente limitada.
    - Si Google responde por cuota/rate-limit/credencial, usa yt-dlp.
    - Cachea 15 min para que el bot no queme cuota repitiendo la misma búsqueda.
    - Los videos aportan contexto/hipótesis; nunca modifican directamente riesgo u órdenes.
    """
    global _YT_API_BLOCK_UNTIL
    q=' '.join(str(query).split()).strip()
    now=time.monotonic()
    with _YT_LOCK:
        row=_YT_CACHE.get(q)
        if row and now-row[0] < max(60,float(cache_seconds)):
            return copy.deepcopy(row[1])
    key=get_secret("YOUTUBE_API_KEY")
    rows=None
    if key and now >= _YT_API_BLOCK_UNTIL:
        try:
            rows=_youtube_api_search(q,key)
        except Exception as exc:
            detail=str(exc).lower()
            # No insistir por una hora cuando Google ya nos dijo que bajemos el ritmo.
            if any(t in detail for t in ('429','ratelimit','quota','403')):
                _YT_API_BLOCK_UNTIL=now+3600
    if rows is None:
        rows=_youtube_ytdlp_search(q)
    with _YT_LOCK:
        _YT_CACHE[q]=(now,copy.deepcopy(rows))
    return rows


_CG_AUTH_LOCK=threading.Lock()
_CG_AUTH_CACHE={"key":"","when":0.0,"ok":None,"error":""}


def _cg_request(path,params):
    key=get_secret("COINGLASS_API_KEY")
    if not key:
        raise RuntimeError("CoinGlass directo sin clave (opcional)")
    url="https://open-api-v4.coinglass.com"+path
    if params:
        url += "?"+urlencode(params)
    try:
        data=json.loads(download(url,{"CG-API-KEY":key}))
    except HTTPError as exc:
        detail,code=_http_error_detail(exc)
        raise RuntimeError(f"CoinGlass HTTP {exc.code}: {detail[:350] or code}")
    if str(data.get("code"))!="0":
        raise RuntimeError("CoinGlass: "+str(data.get("msg") or data.get("message") or data.get("code")))
    return data.get("data")


def coinglass_auth_probe(force=False):
    key=get_secret("COINGLASS_API_KEY")
    if not key:
        return {"ok":False,"state":"sin_key","error":"CoinGlass directo sin clave"}
    # El endpoint supported-coins está documentado como disponible en todos los planes.
    fp=str(hash(key))
    now=time.monotonic()
    with _CG_AUTH_LOCK:
        if (not force and _CG_AUTH_CACHE.get("key")==fp and now-_CG_AUTH_CACHE.get("when",0)<(3600 if _CG_AUTH_CACHE.get('state') in ('plan_limited','invalid_key') else 60)
                and _CG_AUTH_CACHE.get("ok") is not None):
            return dict(_CG_AUTH_CACHE)
        try:
            data=_cg_request("/api/futures/supported-coins",{})
            row={"key":fp,"when":now,"ok":True,"state":"ok","count":len(data or []),"error":""}
        except Exception as exc:
            detail=str(exc)
            plan_limited=('Upgrade plan' in detail or 'upgrade plan' in detail.lower())
            invalid_key=('invalid api key' in detail.lower() or 'invalid key' in detail.lower())
            state='plan_limited' if plan_limited else 'invalid_key' if invalid_key else 'error'
            row={"key":fp,"when":now,"ok":False,"state":state,"count":0,"error":detail}
        _CG_AUTH_CACHE.clear(); _CG_AUTH_CACHE.update(row)
        return dict(row)


def cg_get(path,params):
    probe=coinglass_auth_probe()
    if not probe.get("ok"):
        raise RuntimeError(probe.get("error") or "CoinGlass: autenticación falló")
    return _cg_request(path,params)

def cg_history(path,params):
    try: return cg_get(path,params)
    except RuntimeError as first:
        if params.get("interval") not in ("1h","h1"): raise
        retry=dict(params); retry["interval"]="4h"
        try: return cg_get(path,retry)
        except Exception: raise first


def coinglass_bundle(asset="BTC"):
    """Carga CoinGlass sin convertir un plan limitado en un apagón total.

    Primero intenta series históricas ricas. Si el plan devuelve ``Upgrade plan``,
    cae a snapshots/listas de exchange que exponen OI, funding, liquidaciones y
    métricas de mercado sin que la estrategia tenga que quedarse sin contexto.
    """
    asset=str(asset).upper()
    if asset!='BTC':return {'asset':asset,'state':'UNSUPPORTED','detail':'CoinGlass no aporta derivados XAU confirmados. Se conserva el contexto MT5 y macro; no se sustituyen por BTC.'}
    if not get_secret('COINGLASS_API_KEY'):
        return {'asset':asset,'state':'CONFIG_REQUIRED','detail':'Clave CoinGlass opcional: Ajustes → IA / INTERNET → ACCESO A FUENTES. Los derivados públicos se consultan por separado.'}
    probe=coinglass_auth_probe()
    if probe.get("state")=="plan_limited":
        detail='CoinGlass reconoció la clave pero el plan no habilita endpoints. '
        detail+=('Para BTC se consultan derivados públicos por separado; su disponibilidad se muestra en Fuentes.' if asset=='BTC' else
            'No hay derivados XAU confirmados de CoinGlass; los datos BTC no se usan para fingir confirmación del oro. El análisis MT5 y macro sigue activo.')
        return {"asset":asset,"state":"PLAN_LIMITED","detail":detail,"errors":{}}
    if not probe.get("ok"):
        raise RuntimeError(probe.get("error") or "CoinGlass no disponible")
    pair="BTCUSDT" if asset=="BTC" else "XAUUSDT"
    jobs={
        "oi_price":("/api/futures/open-interest/exchange-history-chart",{"symbol":asset,"range":"12h","unit":"usd"},False),
        "funding":("/api/futures/funding-rate/oi-weight-history",{"symbol":asset,"interval":"1h","limit":24},True),
        "long_short":("/api/futures/global-long-short-account-ratio/history",{"exchange":"Binance","symbol":pair,"interval":"1h","limit":24},True),
        "liquidations":("/api/futures/liquidation/aggregated-history",{"exchange_list":"Binance,OKX,Bybit","symbol":asset,"interval":"1h","limit":24},True),
        "orderbook":("/api/futures/orderbook/ask-bids-history",{"exchange":"Binance","symbol":pair,"interval":"1h","limit":24,"range":"1"},True),
    }
    result={"asset":asset}; errors={}
    def one(name,row):
        path,params,hist=row
        return name,(cg_history(path,params) if hist else cg_get(path,params))
    with ThreadPoolExecutor(max_workers=5,thread_name_prefix=f"akira_cg_{asset.lower()}") as pool:
        futures={pool.submit(one,name,row):name for name,row in jobs.items()}
        for future in as_completed(futures):
            name=futures[future]
            try:
                key,value=future.result(); result[key]=value
            except Exception as exc:
                errors[name]=str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__

    # V179: fallback de snapshot. Mantiene el contexto activo aun cuando el
    # endpoint histórico del plan actual exige upgrade. Cada llamada es
    # independiente: una puede funcionar aunque las demás no.
    fallback={
        "oi_exchange":("/api/futures/open-interest/exchange-list",{"symbol":asset}),
        "funding_exchange":("/api/futures/funding-rate/exchange-list",{}),
        "liquidation_exchange":("/api/futures/liquidation/exchange-list",{"symbol":asset,"range":"4h"}),
        "pairs_markets":("/api/futures/pairs-markets",{"symbol":asset}),
    }
    for name,(path,params) in fallback.items():
        try:
            result[name]=cg_get(path,params)
            errors.pop(name,None)
        except Exception as exc:
            errors[name]=str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__

    result["errors"]=errors
    usable=[k for k,v in result.items() if k not in ("asset","errors") and v not in (None,[],{})]
    if not usable and errors:
        raise RuntimeError("; ".join(f"{k}: {v}" for k,v in errors.items()))
    return result



def _public_json(url):
    try:
        return json.loads(download(url))
    except Exception as exc:
        raise RuntimeError(f"derivados públicos: {type(exc).__name__}: {exc}")


def public_derivatives_bundle(asset="BTC"):
    """Fallback GRATUITO/no autenticado para señales de derivados BTC.

    No pretende replicar CoinGlass. Recupera directamente métricas públicas de
    Binance Futures (OI, funding, ratios y profundidad). Si Binance no está
    disponible en la red del usuario, falla en segundo plano sin bloquear MT5.
    """
    asset=str(asset).upper()
    if asset!="BTC":
        return {"asset":asset,"state":"sin mercado de futuros público equivalente configurado"}
    symbol="BTCUSDT"
    base="https://fapi.binance.com"
    result={"asset":asset,"source":"Binance Futures public","errors":{}}
    endpoints={
        "open_interest":f"{base}/fapi/v1/openInterest?symbol={symbol}",
        "premium":f"{base}/fapi/v1/premiumIndex?symbol={symbol}",
        "global_ls":f"{base}/futures/data/globalLongShortAccountRatio?symbol={symbol}&period=5m&limit=2",
        "top_position_ls":f"{base}/futures/data/topLongShortPositionRatio?symbol={symbol}&period=5m&limit=2",
        "depth":f"{base}/fapi/v1/depth?symbol={symbol}&limit=100",
        "oi_history":f"{base}/futures/data/openInterestHist?symbol={symbol}&period=5m&limit=3",
        "taker_ratio":f"{base}/futures/data/takerlongshortRatio?symbol={symbol}&period=5m&limit=3",
    }
    def one(name,url): return name,_public_json(url)
    with ThreadPoolExecutor(max_workers=len(endpoints),thread_name_prefix="akira_public_deriv") as pool:
        jobs={pool.submit(one,n,u):n for n,u in endpoints.items()}
        for fut in as_completed(jobs):
            name=jobs[fut]
            try:
                k,v=fut.result(); result[k]=v
            except Exception as exc:
                result["errors"][name]=str(exc)
    useful=[k for k,v in result.items() if k not in ("asset","source","errors") and v not in (None,[],{})]
    result["state"]="OK" if useful else "sin datos públicos utilizables"
    return result


def public_derivatives_bias(bundle):
    bundle=bundle or {}; comps=[]; details=[]
    oi=bundle.get("open_interest") or {}
    oi_now=fnum(oi.get("openInterest"))
    premium=bundle.get("premium") or {}
    funding=fnum(premium.get("lastFundingRate"))
    mark=fnum(premium.get("markPrice")); index=fnum(premium.get("indexPrice"))
    if funding:
        comps.append((-math.tanh(funding*4000),.22)); details.append(f"funding {funding:+.5f}")
    if mark and index:
        basis=(mark-index)/max(index,1e-9)
        comps.append((-math.tanh(basis*500),.12)); details.append(f"basis {basis*100:+.3f}%")
    gl=bundle.get("global_ls") or []
    if gl:
        ratio=fnum(gl[-1].get("longShortRatio"),1.0)
        comps.append((-clamp((ratio-1)/max(ratio+1,1e-9)),.18)); details.append(f"global L/S {ratio:.2f}")
    tp=bundle.get("top_position_ls") or []
    if tp:
        ratio=fnum(tp[-1].get("longShortRatio"),1.0)
        comps.append((clamp((ratio-1)/max(ratio+1,1e-9)),.16)); details.append(f"top pos L/S {ratio:.2f}")
    depth=bundle.get("depth") or {}
    bids=sum(fnum(x[1]) for x in depth.get("bids",[])[:50] if isinstance(x,list) and len(x)>1)
    asks=sum(fnum(x[1]) for x in depth.get("asks",[])[:50] if isinstance(x,list) and len(x)>1)
    if bids or asks:
        imb=clamp((bids-asks)/max(bids+asks,1e-9)); comps.append((imb,.28)); details.append(f"book {imb:+.2f}")
    # FINAL: OI delta + taker imbalance distinguish fresh participation from a
    # static OI snapshot. They remain context, never a hard order_send blocker.
    oih=bundle.get("oi_history") or []
    if isinstance(oih,list) and len(oih)>=2:
        prev=fnum(oih[-2].get("sumOpenInterest")); curr=fnum(oih[-1].get("sumOpenInterest"))
        if prev>0 and curr>0:
            delta=(curr-prev)/prev
            price_bias=0.0
            comps.append((math.tanh(delta*35.0),.14)); details.append(f"OIΔ5m {delta*100:+.2f}%")
    taker=bundle.get("taker_ratio") or []
    if isinstance(taker,list) and taker:
        row=taker[-1]; ratio=fnum(row.get("buySellRatio"),1.0)
        buyv=fnum(row.get("buyVol")); sellv=fnum(row.get("sellVol"))
        if buyv or sellv:
            imb=clamp((buyv-sellv)/max(buyv+sellv,1e-9)); comps.append((imb,.22)); details.append(f"taker {imb:+.2f}")
        elif ratio>0:
            imb=clamp((ratio-1.0)/max(ratio+1.0,1e-9)); comps.append((imb,.18)); details.append(f"taker ratio {ratio:.2f}")
    if not comps: return 0.0,0.0,"derivados públicos sin datos"
    w=sum(c for _,c in comps); bias=sum(v*c for v,c in comps)/w
    return clamp(bias),min(.42,.08+w/4),"Binance público "+", ".join(details[:5])

def _freshness_weight(raw_date,unknown=.15):
    """Pesa titulares recientes y casi ignora material viejo.

    YouTube/Investing habían podido aportar análisis de 2024 al mismo nivel que
    noticias actuales. V179 hace que una fuente sin fecha tenga poco peso y que
    piezas antiguas no dominen una decisión viva.
    """
    text=str(raw_date or "").strip()
    if not text or text.lower().startswith("fecha no"):
        return float(unknown)
    dt=None
    for parser in (
        lambda s: datetime.fromisoformat(s.replace("Z","+00:00")),
        lambda s: parsedate_to_datetime(s),
        lambda s: datetime.strptime(s,"%Y%m%d").replace(tzinfo=timezone.utc),
    ):
        try:
            dt=parser(text); break
        except Exception:
            pass
    if dt is None:
        return float(unknown)
    if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
    age=max(0.0,(datetime.now(timezone.utc)-dt.astimezone(timezone.utc)).total_seconds()/86400)
    if age<=2: return 1.0
    if age<=7: return .78
    if age<=14: return .55
    if age<=30: return .28
    if age<=90: return .10
    return .03


def lexical_bias(items,symbol,label,unknown_date_weight=.15):
    rows=[]
    for item in items:
        title=str(item.get("title","")).lower()
        if symbol.startswith("XAU") and not any(k in title for k in ("gold","xau","oro","fed","dollar","rates","inflation")): continue
        if symbol.startswith("BTC") and not any(k in title for k in ("btc","bitcoin","crypto","fed","dollar","rates")): continue
        pos=sum(k in title for k in POSITIVE); neg=sum(k in title for k in NEGATIVE)
        if pos or neg:
            fresh=_freshness_weight(item.get("date"),unknown_date_weight)
            rows.append((clamp((pos-neg)/max(pos+neg,1)),fresh))
    if not rows: return 0.0,0.0,f"{label} sin señal lexical"
    total=sum(w for _,w in rows)
    avg=sum(v*w for v,w in rows)/max(total,1e-9)
    return clamp(avg),min(.28,.04+.04*min(total,6)),f"{label} n={len(rows)} peso fresco {total:.2f} sesgo {avg:+.2f}"


def title_bias(videos,symbol,unknown_date_weight=.15): return lexical_bias(videos,symbol,"YouTube",unknown_date_weight)
def investing_bias(bundle,symbol,unknown_date_weight=.15): return lexical_bias((bundle or {}).get("items",[]),symbol,"Investing",unknown_date_weight)


def fed_gold_bias(news):
    value=0.0; hits=0
    bull=("rate cut","lower rates","easing","dovish","lowering the target range")
    bear=("rate hike","higher rates","hawkish","raising the target range","inflation remains elevated")
    for item in news[:8]:
        title=str(item.get("title","")).lower(); p=sum(x in title for x in bull); n=sum(x in title for x in bear)
        fresh=_freshness_weight(item.get('date'),.08)
        if p or n: value+=(p-n)*fresh; hits+=(p+n)*fresh
    if not hits: return 0.0,0.0,"FED neutral/no clasificado"
    return clamp(value/max(hits,1)),min(.25,.08+.04*hits),f"FED titulares n={hits}"


def _cg_rows(value):
    """Flatten tolerante para los distintos envelopes/listas de CoinGlass V4."""
    out=[]
    def walk(x):
        if isinstance(x,dict):
            out.append(x)
            for v in x.values():
                if isinstance(v,(dict,list)): walk(v)
        elif isinstance(x,list):
            for v in x: walk(v)
    walk(value)
    return out


def _cg_num(row,*names,default=0.0):
    if not isinstance(row,dict): return default
    lowered={str(k).lower():v for k,v in row.items()}
    for name in names:
        if name in row: return fnum(row.get(name),default)
        if str(name).lower() in lowered: return fnum(lowered[str(name).lower()],default)
    return default


def _cg_symbol_row(value,asset):
    asset=str(asset or '').upper()
    rows=_cg_rows(value)
    # Primero una fila agregada/all para el activo, luego cualquier fila del activo.
    ranked=[]
    for row in rows:
        text=' '.join(str(row.get(k,'')) for k in ('symbol','instrument','pair','exchange','exchange_name','name')).upper()
        score=0
        if asset and asset in text: score+=5
        if 'ALL' in text or 'TOTAL' in text: score+=2
        if isinstance(row,dict) and len(row)>=3: score+=1
        ranked.append((score,row))
    ranked.sort(key=lambda x:x[0],reverse=True)
    return ranked[0][1] if ranked and ranked[0][0]>0 else (rows[0] if rows else {})


def coinglass_bias(bundle):
    bundle=bundle or {}; comps=[]; details=[]; asset=str(bundle.get('asset') or 'BTC').upper()
    chart=bundle.get("oi_price") or {}; prices=chart.get("price_list") or []; data_map=chart.get("data_map") or {}
    if len(prices)>=3 and data_map:
        lengths=[len(x) for x in data_map.values() if isinstance(x,list)]
        n=min([len(prices),*lengths]) if lengths else 0
        if n>=3:
            oi=[sum(fnum(values[i]) for values in data_map.values() if isinstance(values,list) and len(values)>i) for i in range(n)]
            look=max(0,n-4); pc=(fnum(prices[-1])-fnum(prices[look]))/max(abs(fnum(prices[look])),1e-9); oc=(oi[-1]-oi[look])/max(abs(oi[look]),1e-9)
            if abs(oc)>.001:
                directional=(1 if pc>0 else -1 if pc<0 else 0)*(0.65 if oc>0 else 0.25)
                comps.append((directional,.85)); details.append(f"OI+precio {pc*100:+.2f}%/{oc*100:+.2f}%")
    funding=bundle.get("funding") or []
    if funding:
        fr=fnum(funding[-1].get("close")); comps.append((-math.tanh(fr*4500),.35)); details.append(f"funding {fr:+.5f}")
    ls=bundle.get("long_short") or []
    if ls:
        ratio=fnum(ls[-1].get("global_account_long_short_ratio"),1.0); comps.append((-clamp((ratio-1)/(ratio+1 if ratio+1 else 1)),.20)); details.append(f"L/S {ratio:.2f}")
    liq=bundle.get("liquidations") or []
    if liq:
        row=liq[-1]; longv=fnum(row.get("aggregated_long_liquidation_usd")); shortv=fnum(row.get("aggregated_short_liquidation_usd")); b=clamp((shortv-longv)/max(shortv+longv,1.0)); comps.append((b,.30)); details.append(f"liq {b:+.2f}")
    ob=bundle.get("orderbook") or []
    if ob:
        row=ob[-1]; bids=fnum(row.get("bids_usd")); asks=fnum(row.get("asks_usd")); b=clamp((bids-asks)/max(bids+asks,1.0)); comps.append((b,.55)); details.append(f"book {b:+.2f}")

    # Fallback V179 para planes que rechazan las series históricas. El peso es
    # deliberadamente menor que el histórico: sirve para no operar ciego, no
    # para convertir un snapshot aislado en una señal dominante.
    market=_cg_symbol_row(bundle.get('pairs_markets'),asset)
    price1=_cg_num(market,'price_change_percent_1h','price_change_1h','price_change_percent_4h','price_change_percent_24h')
    oi1=_cg_num(market,'open_interest_change_percent_1h','open_interest_change_1h','open_interest_change_percent_4h')
    if price1 or oi1:
        direction=1 if price1>0 else -1 if price1<0 else 0
        magnitude=min(1.0,abs(price1)/2.0)
        leverage=1.0 if oi1>=0 else .55
        if direction:
            comps.append((direction*max(.20,magnitude)*leverage,.32))
            details.append(f"snapshot precio/OI {price1:+.2f}%/{oi1:+.2f}%")

    oirow=_cg_symbol_row(bundle.get('oi_exchange'),asset)
    oich=_cg_num(oirow,'open_interest_change_percent_1h','open_interest_change_percent_4h','open_interest_change_percent_24h')
    if oich and price1:
        direction=1 if price1>0 else -1
        # OI creciente refuerza el movimiento; OI cayendo lo debilita.
        strength=min(.55,.15+abs(oich)/8.0)*(1.0 if oich>0 else .45)
        comps.append((direction*strength,.25)); details.append(f"OI exchange {oich:+.2f}%")

    frows=[r for r in _cg_rows(bundle.get('funding_exchange')) if asset in ' '.join(str(v) for v in r.values()).upper()]
    frs=[]
    for row in frows:
        val=_cg_num(row,'funding_rate','fundingRate','rate','funding_rate_oi_weighted')
        if val: frs.append(val)
    if frs:
        fr=sum(frs)/len(frs)
        comps.append((-math.tanh(fr*3500),.22)); details.append(f"funding snapshot {fr:+.5f}")

    lrows=_cg_rows(bundle.get('liquidation_exchange'))
    long_total=short_total=0.0
    for row in lrows:
        text=' '.join(str(v) for v in row.values()).upper()
        if asset not in text and asset not in ('BTC','XAU'):
            continue
        long_total += _cg_num(row,'long_liquidation_usd','longLiquidationUsd','long_liquidation','long')
        short_total += _cg_num(row,'short_liquidation_usd','shortLiquidationUsd','short_liquidation','short')
    if long_total or short_total:
        b=clamp((short_total-long_total)/max(short_total+long_total,1.0))
        comps.append((b,.22)); details.append(f"liq snapshot {b:+.2f}")

    if not comps: return 0.0,0.0,"CoinGlass sin datos utilizables"
    weight=sum(w for _,w in comps); bias=sum(x*w for x,w in comps)/weight
    return clamp(bias),min(.65,.12+weight/4),"CoinGlass "+", ".join(details[:7])

def cloud_value(state,symbol):
    data=state.get("cloud") or {}; row=data.get(symbol) or {} if isinstance(data,dict) else {}
    if not isinstance(row,dict): return 0.0,0.0,"IA cloud sin símbolo"
    return clamp(fnum(row.get("bias"))),clamp(fnum(row.get("confidence")),0,1),str(row.get("note","IA cloud"))[:180]

def cloud_pending_key(state,symbol):
    data=state.get("cloud") or {}; row=data.get(symbol) or {} if isinstance(data,dict) else {}
    return str(row.get("pending_key","") or "")[:240] if isinstance(row,dict) else ""


def model_component(report,name,max_conf=.45):
    # El modelo local puede abstenerse. V179 no deja que una precisión igual a
    # la clase mayoritaria se disfrace de IA útil ni que el ruido neutral vote.
    if not report or "model_output" not in report:
        return None
    advantage=max(0.0,fnum(report.get("advantage"),fnum(report.get("test_accuracy"))-fnum(report.get("baseline"))))
    usable=bool(report.get("usable_signal",report.get("better_than_baseline",False)))
    if not usable or advantage<.02:
        return None
    p=clamp((fnum(report["model_output"])-.5)*2)
    if abs(p)<.12:
        return None
    coverage=clamp(fnum(report.get("coverage",1.0)),0.0,1.0)
    conf=min(max_conf,(.10+advantage*2.6)*(.55+.45*coverage))
    return (name,p,conf,f"{name} p={fnum(report['model_output']):.2f} ventaja={advantage*100:.1f}pp cov={coverage:.2f}")


def fuse_components(components,selected_pending=""):
    if not components:
        return {"bias":0.0,"confidence":0.0,"pending_key":selected_pending,"components":[],"label":"solo técnico local"}
    total=sum(max(.01,c) for _,_,c,_ in components); bias=sum(b*max(.01,c) for _,b,c,_ in components)/total; confidence=min(.84,total/(total+1.25))
    return {"bias":clamp(bias),"confidence":confidence,"pending_key":selected_pending,
            "components":[{"name":n,"bias":round(b,4),"weight":round(c,4),"detail":d} for n,b,c,d in components],
            "label":" | ".join(d for *_,d in components)[:700]}
