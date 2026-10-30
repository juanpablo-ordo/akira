"""Per-turn budgets: model loading must never spend the research allowance."""
import threading,time

class TurnBudget:
    DEFAULTS={'prepare':180.,'conversation':150.,'sources':35.,'deep_research':90.,'trade_review':150.}
    def __init__(self,config=None,clock=time.monotonic):
        cfg=(config or {}).get('assistant',{})
        self.limits={k:float(cfg.get(k+'_timeout_seconds',v)) for k,v in self.DEFAULTS.items()}
        self.clock=clock;self.starts={};self.lock=threading.Lock()
    def remaining(self,phase):
        with self.lock:
            now=self.clock();self.starts.setdefault(phase,now)
            return max(0.,self.limits[phase]-(now-self.starts[phase]))
    def diagnostics(self):
        with self.lock:return {k:{'budget_seconds':self.limits[k],'elapsed_seconds':round(max(0,self.clock()-v),3)} for k,v in self.starts.items()}

class AIHealthMonitor:
    def __init__(self,clock=time.monotonic):
        self.clock=clock;self.lock=threading.Lock();self.state={'ready':False,'phase':'UNVERIFIED','last_error':''}
    def begin(self,provider,model):
        with self.lock:
            self.started=self.clock();self.state.update(ready=False,phase='GENERATING',provider=provider,model=model,first_token_seconds=None)
    def token(self,text):
        with self.lock:
            if text and self.state.get('first_token_seconds') is None:self.state['first_token_seconds']=round(self.clock()-getattr(self,'started',self.clock()),3)
    def finish(self,text='',error=None):
        with self.lock:
            self.state.update(ready=bool(str(text).strip()) and error is None,phase='READY' if text and error is None else 'ERROR',
                elapsed_seconds=round(self.clock()-getattr(self,'started',self.clock()),3),last_error=str(error or '')[:300])
    def snapshot(self):
        with self.lock:return dict(self.state)
