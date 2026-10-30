"""Source-local failures and bounded retry windows. Never disables MT5."""
import socket,ssl,threading,time,random,re
from urllib.error import HTTPError
from urllib.parse import urlsplit

def classify_failure(error,url=''):
    reason=getattr(error,'reason',error);message=str(error)
    code=getattr(error,'code',None);err=getattr(reason,'errno',None)
    low=message.lower()
    if isinstance(reason,socket.gaierror) or err in (11001,11002,11003,11004,-2,-3) or any(x in low for x in ('11002','getaddrinfo','name resolution')):kind='DNS_ERROR'
    elif isinstance(reason,(TimeoutError,socket.timeout)) or any(x in low for x in ('timed out','timeout','superó su plazo')):kind='TIMEOUT'
    elif code in (401,403):kind='AUTH_ERROR' if code==401 else 'ACCESS_DENIED'
    elif code==429:kind='QUOTA_EXCEEDED'
    elif isinstance(reason,ssl.SSLError) or 'certificate' in low:kind='TLS_ERROR'
    elif isinstance(error,HTTPError) or code:kind='HTTP_ERROR'
    elif isinstance(error,(ValueError,TypeError)):kind='INVALID_DATA'
    else:kind='NETWORK_ERROR'
    host=(urlsplit(str(url)).hostname or '')
    # URLs in exception messages can carry API query keys. Keep domain/error,
    # never credentials, headers or query strings in diagnostics.
    message=re.sub(r'https?://[^\s<>]+',lambda m:(urlsplit(m[0]).hostname or 'servicio'),message)
    message=re.sub(r'(?i)(?:bearer\s+|(?:key|token|password|secret)[=:]\s*)[^\s,;]+','[REDACTADO]',message)
    return {'kind':kind,'domain':host,'error_type':type(error).__name__,'original_error':message[:350],'errno':err,'http_status':code}

class SourceHealthManager:
    def __init__(self,clock=time.monotonic,jitter=None):
        self.clock=clock;self.jitter=jitter or (lambda:random.uniform(.85,1.15));self.rows={};self.lock=threading.Lock()
    def permitted(self,key):
        with self.lock:return self.clock()>=self.rows.get(key,{}).get('retry_at',0)
    def failure(self,key,error,url=''):
        with self.lock:
            old=self.rows.get(key,{});n=old.get('failures',0)+1;detail=classify_failure(error,url)
            base=30 if detail['kind']=='DNS_ERROR' else 15
            delay=min(3600,base*2**min(n-1,7))*self.jitter()
            if detail['kind'] in ('AUTH_ERROR','ACCESS_DENIED','QUOTA_EXCEEDED'):delay=max(300,delay)
            row={**old,**detail,'failures':n,'last_attempt':self.clock(),'retry_at':self.clock()+delay,'circuit_open':n>=3,'available':False}
            self.rows[key]=row;return dict(row)
    def success(self,key):
        with self.lock:self.rows[key]={'available':True,'failures':0,'last_success':self.clock(),'retry_at':0,'circuit_open':False}
    def snapshot(self):
        with self.lock:
            now=self.clock();return {k:{**v,'retry_after_seconds':max(0,round(v.get('retry_at',0)-now,1))} for k,v in self.rows.items()}

class SourceCoolingDown(ConnectionError):pass

HTTP_HEALTH=SourceHealthManager()

def guarded_open(opener,url,*args,**kwargs):
    target=getattr(url,'full_url',str(url));host=urlsplit(target).hostname or ''
    # Local inference and test servers have their own lifecycle and budgets.
    if host in ('localhost','127.0.0.1','::1'):return opener(url,*args,**kwargs)
    endpoint=host+urlsplit(target).path
    blocked=host if not HTTP_HEALTH.permitted(host) else endpoint
    if not HTTP_HEALTH.permitted(blocked):
        row=HTTP_HEALTH.snapshot()[blocked]
        raise SourceCoolingDown(f"{host}: {row.get('kind','NETWORK_ERROR')}; próximo intento en {row['retry_after_seconds']:g} s")
    try:response=opener(url,*args,**kwargs)
    except Exception as exc:
        key=host if classify_failure(exc,target)['kind']=='DNS_ERROR' else endpoint
        HTTP_HEALTH.failure(key,exc,target);raise
    HTTP_HEALTH.success(host);HTTP_HEALTH.success(endpoint);return response

class NetworkDiagnostics:
    @staticmethod
    def inspect():
        from urllib.request import getproxies
        return {'sources':HTTP_HEALTH.snapshot(),'proxy_configured':bool(getproxies()),
                'scope':'Estado observado de solicitudes reales por dominio; una caída no certifica caída de Internet ni de MT5.'}
