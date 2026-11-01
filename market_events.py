"""Dated event alerts request analysis, never manufacture a buy/sell signal."""
from datetime import datetime,timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit
import hashlib,math,re,unicodedata


def publication(row):
    stamp=row.get('published_utc')
    if not isinstance(stamp,(int,float)):
        text=str(row.get('date') or row.get('published') or '')
        try:dt=parsedate_to_datetime(text)
        except (ValueError,TypeError,OverflowError):
            try:dt=datetime.fromisoformat(text.replace('Z','+00:00'))
            except (ValueError,TypeError,OverflowError):return None
        if dt.tzinfo is None:return None
        stamp=dt.astimezone(timezone.utc).timestamp()
    return float(stamp) if math.isfinite(stamp) else None


def event_alerts(news,now,maximum_age=86400):
    rows=[];seen=set()
    for item in news:
        if not isinstance(item,dict):continue
        stamp=publication(item);title=' '.join(str(item.get('title') or '').split())[:300]
        url=str(item.get('url') or '');host=urlsplit(url).hostname or ''
        if stamp is None or not 0<=now-stamp<=maximum_age or not title or urlsplit(url).scheme!='https':continue
        text=''.join(c for c in unicodedata.normalize('NFKD',title.casefold()) if not unicodedata.combining(c))
        crypto=bool(re.search(r'\b(bitcoin|btc|binance|coinbase|kraken|bybit|crypto|cripto\w*)\b',text))
        gold=bool(re.search(r'\b(gold|oro|xau\w*|inflation|inflacion|fed|federal reserve|interest rate\w*|tasas? de interes|dolar|dollar|geopolit\w*)\b',text))
        category=('SECURITY' if re.search(r'\b(hack\w*|exploit\w*|breach|robo|ataque|security incident|unauthorized|compromis\w*)\b',text)
                  else 'VENUE_STATUS' if re.search(r'\b(withdraw\w*|retiro\w*|outage|suspend\w*|resum\w*)\b',text)
                  else 'MACRO' if gold else '')
        if not category or not (crypto or gold):continue
        key=hashlib.sha256((text+'|'+str(int(stamp))).encode()).hexdigest()[:24]
        if key in seen:continue
        seen.add(key)
        official=host in ('binance.com','www.binance.com','federalreserve.gov','www.federalreserve.gov',
                          'bls.gov','www.bls.gov','ecb.europa.eu','www.ecb.europa.eu','sec.gov','www.sec.gov')
        rows.append({'id':key,'title':title,'url':url,'published_utc':stamp,'category':category,
            'symbols':(['BTCUSDm'] if crypto else [])+(['XAUUSDm'] if gold else []),
            'verification':'PRIMARY_DOMAIN_HEADLINE' if official else 'DATED_REPORT',
            'coverage':'Titular fechado; contenido completo y efecto direccional no verificados.',
            'action':'REASSESS','direction':None})
    return sorted(rows,key=lambda r:(-r['published_utc'],r['id']))[:12]
