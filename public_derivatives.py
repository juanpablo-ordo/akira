"""Public, key-free BTC derivatives with bounded, independent venue fallbacks.

Each bundle belongs to ONE venue. Contract quantities and OI history from
different exchanges are never spliced together. No broker operations occur here.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
import math
import time


DOCS = {
    'OKX': 'https://www.okx.com/docs-v5/en/',
    'Bybit': 'https://bybit-exchange.github.io/docs/v5/market/open-interest',
    'Binance': 'https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest',
}
ENDPOINTS = {
    'OKX': {
        'open_interest': 'https://www.okx.com/api/v5/public/open-interest?instType=SWAP&instId=BTC-USDT-SWAP',
        'premium': 'https://www.okx.com/api/v5/public/funding-rate?instId=BTC-USDT-SWAP',
        'depth': 'https://www.okx.com/api/v5/market/books?instId=BTC-USDT-SWAP&sz=50',
        'global_ls': 'https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio?ccy=BTC&period=5m',
    },
    'Bybit': {
        'premium': 'https://api.bybit.com/v5/market/tickers?category=linear&symbol=BTCUSDT',
        'depth': 'https://api.bybit.com/v5/market/orderbook?category=linear&symbol=BTCUSDT&limit=50',
        'oi_history': 'https://api.bybit.com/v5/market/open-interest?category=linear&symbol=BTCUSDT&intervalTime=5min&limit=3',
        'global_ls': 'https://api.bybit.com/v5/market/account-ratio?category=linear&symbol=BTCUSDT&period=5min&limit=2',
    },
    'Binance': {
        'open_interest': 'https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDT',
        'premium': 'https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT',
        'depth': 'https://fapi.binance.com/fapi/v1/depth?symbol=BTCUSDT&limit=50',
        'global_ls': 'https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol=BTCUSDT&period=5m&limit=2',
        'oi_history': 'https://fapi.binance.com/futures/data/openInterestHist?symbol=BTCUSDT&period=5m&limit=3',
        'taker_ratio': 'https://fapi.binance.com/futures/data/takerlongshortRatio?symbol=BTCUSDT&period=5m&limit=3',
    },
}


def number(value):
    n=float(value)
    if not math.isfinite(n):raise ValueError('Métrica no finita')
    return n


def normalize(venue, key, raw, now):
    """Reject provider error envelopes, empty/invalid metrics and stale snapshots."""
    if venue=='OKX':
        if str(raw.get('code'))!='0':raise ValueError('OKX no entregó esta métrica')
        rows=raw.get('data') or []
        if not rows:raise ValueError('OKX sin datos')
        first=rows[0]
        if isinstance(first,dict) and first.get('instId') not in (None,'BTC-USDT-SWAP'):raise ValueError('Instrumento ajeno a BTC')
        if key=='open_interest':value={'openInterest':number(first['oiCcy'])}
        elif key=='premium':value={'lastFundingRate':number(first['fundingRate'])}
        elif key=='depth':value={k:first[k] for k in ('bids','asks')}
        else:value=[{'longShortRatio':number(row[1]),'timestamp':row[0]} for row in reversed(rows)]
        stamp=first.get('ts') if isinstance(first,dict) else first[0]
    elif venue=='Bybit':
        if raw.get('retCode')!=0:raise ValueError('Bybit no entregó esta métrica')
        result=raw.get('result') or {};rows=result.get('list') or []
        if key=='premium':
            first=rows[0]
            if first.get('symbol') not in (None,'BTCUSDT'):raise ValueError('Instrumento ajeno a BTC')
            value={'lastFundingRate':number(first['fundingRate']),
                'markPrice':number(first['markPrice']),'indexPrice':number(first['indexPrice']),
                'openInterest':number(first['openInterest'])}
        elif key=='depth':value={'bids':result['b'],'asks':result['a']}
        elif key=='oi_history':value=[{'sumOpenInterest':number(r['openInterest']),'timestamp':r['timestamp']} for r in reversed(rows)]
        else:value=[{'longShortRatio':number(r['buyRatio'])/max(number(r['sellRatio']),1e-12),'timestamp':r['timestamp']} for r in reversed(rows)]
        stamp=result.get('ts') or raw.get('time')
    else:
        if isinstance(raw,dict) and (raw.get('code') is not None or raw.get('msg')):raise ValueError('Binance no entregó esta métrica')
        value=raw
        stamp=(raw.get('time') or raw.get('E') or raw.get('T')) if isinstance(raw,dict) else raw[-1].get('timestamp') if raw else None
    if not value:raise ValueError('La métrica está vacía')
    # Some public books omit a timestamp. Retrieval time is explicitly recorded;
    # when a server supplies one, old/future observations cannot be refreshed.
    observed=number(stamp)/1000 if stamp else now
    max_age=900 if key in ('global_ls','oi_history','taker_ratio') else 120
    if not -30<=now-observed<=max_age:raise ValueError('Métrica del proveedor fuera de vigencia')
    if key=='open_interest' and number(value['openInterest'])<=0:raise ValueError('Interés abierto inválido')
    if key=='premium':
        number(value['lastFundingRate'])
        if 'markPrice' in value and min(number(value['markPrice']),number(value['indexPrice']))<=0:raise ValueError('Precio derivado inválido')
    if key=='depth':
        for side in ('bids','asks'):
            if not value.get(side):raise ValueError('Libro vacío')
            for row in value[side]:
                if number(row[0])<=0 or number(row[1])<0:raise ValueError('Libro inválido')
            if sum(number(row[1]) for row in value[side])<=0:raise ValueError('Libro sin volumen')
        if number(value['bids'][0][0])>=number(value['asks'][0][0]):raise ValueError('Libro cruzado')
    if key in ('global_ls','oi_history','taker_ratio') and not isinstance(value,list):raise ValueError('Serie inválida')
    if key in ('global_ls','oi_history'):
        field='longShortRatio' if key=='global_ls' else 'sumOpenInterest'
        if any(number(row[field])<=0 for row in value):raise ValueError('Serie no positiva')
    if key=='taker_ratio':
        if any(number(row[k])<0 for row in value for k in ('buySellRatio','buyVol','sellVol') if k in row):raise ValueError('Volumen o ratio negativo')
    return value,observed,bool(stamp)


def bundle(fetch, asset='BTC', clock=time.time, venues=('OKX','Bybit','Binance')):
    if asset!='BTC':
        return {'asset':asset,'state':'UNSUPPORTED','detail':'Los derivados BTC no describen el oro. XAU conserva sus datos MT5 y macro.'}
    now=clock();best={};best_count=0;errors={}
    for venue in venues:
        data={};stamps={};errors_for_venue={}
        with ThreadPoolExecutor(max_workers=4,thread_name_prefix='AkiraPublicDerivatives') as pool:
            jobs={pool.submit(fetch,url):key for key,url in ENDPOINTS[venue].items()}
            for future in as_completed(jobs):
                key=jobs[future]
                try:
                    data[key],stamp,provider_stamp=normalize(venue,key,future.result(),now)
                    stamps[key]={'at':stamp,'provider_timestamp':provider_stamp}
                except Exception as exc:errors_for_venue[key]=type(exc).__name__+': '+str(exc)[:180]
        errors[venue]=errors_for_venue
        if venue=='Bybit' and (data.get('premium') or {}).get('openInterest',0)>0:
            data['open_interest']={'openInterest':data['premium']['openInterest']};stamps['open_interest']=stamps['premium']
        coverage=[k for k in ('open_interest','premium','depth','global_ls','oi_history','taker_ratio') if k in data]
        count=sum(k in data for k in ('open_interest','premium','depth'))
        if coverage and count>best_count:
            best_count=count;best={**data,'source':venue+' public','documentation':DOCS[venue],
                'coverage':coverage,'metric_timestamps':stamps,'retrieved_at':clock()}
        if count==3:break
    missing=[k for k in ('open_interest','premium','depth','global_ls','oi_history','taker_ratio') if k not in best]
    return {'asset':asset,**best,'errors':errors,'state':'OK' if best else 'NO_DATA',
        'missing':missing+['aggregated_liquidations','liquidation_heatmap'],
        'detail':('Derivados BTC de '+best['source']+', sin clave ni plan. Cobertura: '+', '.join(best['coverage'])+'. '
                  'No incluye liquidaciones agregadas ni mapas de liquidación de pago.' if best else
                  'Ningún mercado público respondió con datos vigentes. El análisis técnico MT5 continúa; se volverá a consultar con espera.')}
