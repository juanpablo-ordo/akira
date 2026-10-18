"""Background Internet supervision; endpoint failures never block Tk or MT5."""
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request
from network_tls import urlopen


def recently_connected(snapshot,now=None):
    now=time.time() if now is None else float(now)
    def recent(stamp):
        try:return 0<=now-float(stamp)<=5
        except (TypeError,ValueError):return False
    if snapshot.get('connected') and any(recent(row.get('quote_time')) for row in (snapshot.get('symbols') or {}).values() if isinstance(row,dict)):
        return True
    for name,row in ((snapshot.get('research') or {}).get('sources') or {}).items():
        if name in ('local_ai','pending_ai','model','strategy_reference','cloud') or not isinstance(row,dict):continue
        if not row.get('error') and row.get('usable',True) and row.get('enabled',True) and recent(row.get('updated')):return True
    return False


def internet_available():
    # A TLS-authenticated HTTP response, including a 403, proves connectivity.
    # Service credentials, YouTube quotas and individual provider failures do not.
    for url in ('https://www.gstatic.com/generate_204','https://www.microsoft.com/favicon.ico'):
        try:
            with urlopen(Request(url,headers={'User-Agent':'AKIRA connectivity'}),timeout=1.5) as response:
                response.read(1)
            return True
        except HTTPError:return True
        except (OSError,ValueError):continue
    return False


class ConnectivityMonitor:
    def __init__(self,callback,check=internet_available,clock=time.monotonic):
        self.callback,self.check,self.clock=callback,check,clock
        self.stop=threading.Event();self.wake=threading.Event();self.thread=None
        self.online=None;self.failures=0

    def sample(self):
        try:ok=bool(self.check())
        except Exception:ok=False
        self.failures=0 if ok else self.failures+1
        proposed=True if ok else False if self.failures>=2 else self.online
        changed=proposed is not self.online
        self.online=proposed
        delay=5 if self.online is not False else min(15,5*2**min(4,max(0,self.failures-2)))
        if changed:self.callback({'online':self.online,'checked_at':self.clock(),'retry_seconds':delay})
        return delay

    def start(self):
        if self.thread and self.thread.is_alive():return
        def run():
            while not self.stop.is_set():
                delay=self.sample();self.wake.wait(delay);self.wake.clear()
        self.thread=threading.Thread(target=run,name='AkiraInternet',daemon=True);self.thread.start()

    def close(self):
        self.stop.set();self.wake.set()
