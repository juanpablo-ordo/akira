"""Public reference data. Never supplies executable MT5 prices or risk limits."""
import csv,io,math,time
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timedelta,timezone
from urllib.request import Request
from network_tls import urlopen
from urllib.parse import urlencode,urlsplit
from email.utils import parsedate_to_datetime
from providers import _public_json,parse_rss,_freshness_weight,lexical_bias

NEWS_FEEDS={
 'Federal Reserve':'https://www.federalreserve.gov/feeds/press_all.xml',
 'BLS':'https://www.bls.gov/feed/cpi.rss',
 'SEC':'https://www.sec.gov/news/pressreleases.rss',
 'ECB':'https://www.ecb.europa.eu/rss/press.html',
 'CNBC mercados':'https://www.cnbc.com/id/100003114/device/rss/rss.html',
 'CFTC':'https://www.cftc.gov/RSS/RSSGP/rssgp.xml',
}
BLS_NEWS_FEEDS=('https://www.bls.gov/feed/cpi.rss','https://www.bls.gov/feed/empsit.rss','https://www.bls.gov/feed/ppi.rss')
REFERENCE_SOURCES={
 'CME / COMEX':'https://www.cmegroup.com/markets/metals/precious/gold.html',
 'LBMA':'https://www.lbma.org.uk/prices-and-data',
 'World Gold Council':'https://www.gold.org/goldhub',
 'FRED':'https://fred.stlouisfed.org/',
 'Reuters':'https://www.reuters.com/markets/',
 'Bloomberg':'https://www.bloomberg.com/markets',
 'Financial Times':'https://www.ft.com/markets',
}

MACRO_SERIES={'DGS10':'Tesoro EE. UU. 10 años (nominal, %)','DFII10':'Tesoro EE. UU. 10 años (real, %)',
 'DTWEXBGS':'Índice amplio del dólar, ponderado por comercio'}

def public_text(url):
 with urlopen(Request(url,headers={'User-Agent':'AkiraResearch/16.0','Accept':'text/csv,text/plain'}),timeout=8) as response:
  raw=response.read(1_000_001)
  if len(raw)>1_000_000:raise ValueError('Respuesta macro demasiado grande')
  return raw.decode('utf-8-sig')

def fred_macro(fetch=public_text,clock=time.time):
 now=clock();today=datetime.fromtimestamp(now,timezone.utc).date();start=(today-timedelta(days=45)).isoformat();rows=[];errors={}
 for series,title in MACRO_SERIES.items():
  url='https://fred.stlouisfed.org/graph/fredgraph.csv?'+urlencode({'id':series,'cosd':start})
  try:
   values=[]
   for item in csv.DictReader(io.StringIO(fetch(url))):
    date=item.get('observation_date') or item.get('DATE');value=finite(item.get(series))
    if not date or value is None:continue
    observed=datetime.fromisoformat(date).date()
    if observed>today:raise ValueError('Observación macro futura')
    if (today-observed).days<=14:values.append((observed.isoformat(),value))
   if not values:raise ValueError('Sin observaciones recientes')
   values.sort();date,value=values[-1];change=value-values[-2][1] if len(values)>1 else None
   rows.append({'series':series,'name':title,'date':date,'value':value,'last_change':change,'url':url,
    'frequency':'Diaria; con retraso de publicación','used_for':'Contexto de dólar y tipos para oro y BTC; no cotización operativa ni voto direccional independiente'})
  except Exception as exc:errors[series]=type(exc).__name__+': '+str(exc)[:150]
 if not rows:raise ValueError('FRED no disponible: '+str(errors))
 return {'updated':now,'rows':rows,'errors':errors,'detail':'Macro diaria oficial; contexto auxiliar, sin sustituir XAUUSD ni BTCUSD de MT5'}

def finite(value):
 try:
  x=float(value)
  return x if math.isfinite(x) else None
 except (ValueError,TypeError):return None

def levels_imbalance(bids,asks):
 def total(rows):return sum(max(0,finite(r[0]) or 0)*max(0,finite(r[1]) or 0) for r in rows[:20] if len(r)>1)
 b,a=total(bids),total(asks)
 return (b-a)/(b+a) if b+a>0 else None

def market_feed(venue,fetch=_public_json,clock=time.time):
 now=clock();base={'venue':venue,'asset':'BTC','updated':now,'quote':'USD','purpose':'Referencia externa; ejecución y lotaje exclusivamente MT5'}
 if venue=='OKX':
  url='https://www.okx.com/api/v5/market/books?instId=BTC-USDT&sz=20';d=fetch(url)
  if str(d.get('code'))!='0' or not d.get('data'):raise ValueError('OKX no suministra datos válidos')
  book=d['data'][0];bids=book.get('bids',[]);asks=book.get('asks',[])
  base.update(quote='USDT',source=url,bid=finite(bids[0][0]) if bids else None,ask=finite(asks[0][0]) if asks else None,
   imbalance=levels_imbalance(bids,asks),market_time=finite(book.get('ts'))/1000 if finite(book.get('ts')) else None)
  for field,path,key in [('funding','funding-rate?instId=BTC-USDT-SWAP','fundingRate'),('open_interest_usd','open-interest?instType=SWAP&instId=BTC-USDT-SWAP','oiUsd')]:
   try:
    result=fetch('https://www.okx.com/api/v5/public/'+path)
    if str(result.get('code'))=='0' and result.get('data'):base[field]=finite(result['data'][0].get(key))
   except Exception as exc:base.setdefault('errors',{})[field]=type(exc).__name__
 elif venue=='Coinbase':
  url='https://api.exchange.coinbase.com/products/BTC-USD/book?level=2';d=fetch(url)
  bids=d.get('bids',[]);asks=d.get('asks',[])
  base.update(source=url,bid=finite(bids[0][0]) if bids else None,ask=finite(asks[0][0]) if asks else None,imbalance=levels_imbalance(bids,asks),market_time=None)
 elif venue=='Kraken':
  url='https://api.kraken.com/0/public/Depth?pair=XBTUSD&count=20';d=fetch(url)
  if d.get('error'):raise ValueError('Kraken: '+str(d['error']))
  book=next(iter(d.get('result',{}).values()),{});bids=book.get('bids',[]);asks=book.get('asks',[])
  base.update(source=url,bid=finite(bids[0][0]) if bids else None,ask=finite(asks[0][0]) if asks else None,imbalance=levels_imbalance(bids,asks),market_time=None)
 elif venue=='Bybit':
  url='https://api.bybit.com/v5/market/orderbook?category=linear&symbol=BTCUSDT&limit=25';d=fetch(url)
  if d.get('retCode')!=0:raise ValueError('Bybit no suministra datos válidos')
  book=d.get('result',{});bids=book.get('b',[]);asks=book.get('a',[])
  base.update(quote='USDT',source=url,bid=finite(bids[0][0]) if bids else None,ask=finite(asks[0][0]) if asks else None,imbalance=levels_imbalance(bids,asks),market_time=(finite(book.get('ts')) or 0)/1000)
 else:raise ValueError('Proveedor no soportado')
 if not base.get('bid') or not base.get('ask') or base['ask']<base['bid']:raise ValueError('Libro vacío o cruzado')
 stamp=base.get('market_time')
 if stamp and (now-stamp>90 or stamp>now+5):raise ValueError('Datos externos antiguos o fechados en el futuro')
 base['timestamp_quality']='proveedor' if stamp else 'hora de recepción; sin timestamp del libro'
 return base

def news_feed(name):
 if name=='BLS':
  rows=[];errors=[]
  with ThreadPoolExecutor(max_workers=3,thread_name_prefix='AkiraBLS') as pool:
   jobs={pool.submit(parse_rss,url,12):url for url in BLS_NEWS_FEEDS}
   for future in as_completed(jobs):
    try:rows.extend({**r,'feed_url':jobs[future]} for r in future.result())
    except Exception as exc:errors.append(type(exc).__name__+': '+str(exc)[:100])
  if not rows and errors:raise RuntimeError('BLS no disponible en sus feeds oficiales: '+'; '.join(errors))
 else:rows=parse_rss(NEWS_FEEDS[name],limit=12)
 now=time.time();seen=set();out=[]
 for row in rows:
  title=' '.join(str(row.get('title') or '').split());url=row.get('url','')
  key=title.casefold()
  if not title or key in seen:continue
  seen.add(key)
  try:published=parsedate_to_datetime(row.get('date','')).timestamp()
  except (ValueError,TypeError,OverflowError):
   try:published=datetime.fromisoformat(str(row.get('date','')).replace('Z','+00:00')).timestamp()
   except (ValueError,TypeError,OverflowError):published=None
  # Keep undated material as a reference; never count it as breaking news.
  if published is not None and (published>now+300 or now-published>7*86400):continue
  out.append({**row,'provider':name,'fetched':now,'verified_publication':published is not None,'published_utc':published,
   'importance':'oficial' if name in ('BLS','Federal Reserve','SEC','ECB','CFTC') else 'prensa',
   'impact':'Contexto; dirección del impacto no confirmada por un titular',
   **({'feed_warnings':errors} if name=='BLS' and errors else {})})
 return out

def market_consensus(rows,now):
 fresh=[r for r in rows if isinstance(r,dict) and r.get('asset')=='BTC' and 0<=now-float(r.get('updated',0))<=90]
 values=[finite(r.get('imbalance')) for r in fresh];values=[x for x in values if x is not None]
 if len(values)<2:return 0,0,'Faltan dos libros independientes actuales; sin aporte al ranking'
 # Correlated exchanges form one bounded component, never one vote per API.
 mean=sum(values)/len(values);dispersion=sum(abs(x-mean) for x in values)/len(values)
 weight=.12*max(0,1-dispersion)
 return max(-1,min(1,mean)),weight,f'{len(values)} venues BTC; desequilibrio agregado {mean:+.3f}; divergencia {dispersion:.3f}; precios de referencia USD/USDT separados'
