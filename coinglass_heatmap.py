"""CoinGlass V4 liquidation-level estimates, obtained only with a licensed key.

Official provider outputs MODELLED liquidation leverage levels, not observed
executed liquidations. This adapter never falls back to fabricating those levels
from XAU or from candles. No information here approves an MT5 order.
"""
import math


def _finite(value):
    try:
        n=float(value)
        return n if math.isfinite(n) else None
    except (TypeError,ValueError,OverflowError):
        return None


def normalize_heatmap(data, now, symbol='BTC', bins=24):
    result={'symbol':'BTCUSDm','provider':'CoinGlass V4',
            'source_type':'PROVIDER_MODELLED_LIQUIDATION_LEVELS',
            'status':'INVALID_DATA','observed_executions':False,
            'trade_confirmation':False,'generated_at_utc':float(now),
            'provider_pair':'BTCUSDT derivatives, not BTCUSDm spot/CFD',
            'bands':[],'coverage':'Modelled leveraged liquidation exposure, not realized events'}
    if symbol!='BTC' or not isinstance(data,dict):return result
    axis=data.get('y_axis');points=data.get('liquidation_leverage_data')
    candles=data.get('price_candlesticks')
    if not isinstance(axis,list) or not isinstance(points,list) or not isinstance(candles,list):
        return result
    prices=[_finite(v) for v in axis]
    if len(prices)<2 or len(prices)>20000 or any(v is None or v<=0 for v in prices) or not all(prices[i]<=prices[i+1] for i in range(len(prices)-1)):
        return result
    if not candles or len(candles)>100000:return result
    low,high=min(prices),max(prices)
    if high<=low:return result
    count=max(8,min(32,int(bins)))
    step=(high-low)/count
    previous=[0.]*count;current=[0.]*count
    valid=0;cut=len(candles)//2
    # Bound the scan against malformed or unexpectedly enormous provider payloads.
    if len(points)>200000:return result
    for p in points:
        if not isinstance(p,(list,tuple)) or len(p)<3:continue
        x,y,amount=_finite(p[0]),_finite(p[1]),_finite(p[2])
        if any(v is None for v in (x,y,amount)):continue
        if not x.is_integer() or not y.is_integer() or amount<0 or amount>1e15:continue
        x=int(x);y=int(y)
        if x<0 or x>=len(candles) or y<0 or y>=len(prices):continue
        index=min(count-1,max(0,int((prices[y]-low)/step)))
        (previous if x<cut else current)[index]+=amount;valid+=1
    if not valid:return result
    peak=max(*previous,*current,1.0)
    result.update(status='PROVIDER_MODELLED',range='24h',
        intensity_scale='Relative 0-100, based on provider-modelled USD exposure',
        valid_points=valid,quote_currency='USDT (BTCUSDm differs by venue)',
        source_url='https://docs.coinglass.com/reference/liquidation-aggregate-heatmap',
        bands=[{'low':round(low+i*step,4),'high':round(low+(i+1)*step,4),
                'historical_intensity':round(100*previous[i]/peak,1),
                'current_intensity':round(100*current[i]/peak,1),
                'historical_exposure_usd':round(previous[i],2),
                'current_exposure_usd':round(current[i],2)} for i in range(count)])
    return result


def fetch_heatmap():
    from providers import cg_get
    import time
    try:
        data=cg_get('/api/futures/liquidation/aggregated-heatmap/model1',
                    {'symbol':'BTC','range':'24h'})
    except RuntimeError as exc:
        message=str(exc)
        if any(word in message.lower() for word in ('upgrade plan','upgrade','subscription','permission','forbidden','403','not allowed')):
            return {'status':'PLAN_LIMITED','state':'PLAN_LIMITED','detail':
                'El mapa por precio de CoinGlass requiere un plan Professional o Enterprise; se conserva la estimación local.'}
        raise
    result=normalize_heatmap(data,time.time())
    if result['status']!='PROVIDER_MODELLED':
        raise ValueError('CoinGlass devolvió un mapa sin índices de precio/tiempo verificables')
    return result
