"""Exit evidence uses the original entry horizon; UTC bars only."""
from trade_review import source_timeframe,PERIODS
class RunnerExitPolicy:
 @staticmethod
 def timeframe(plan,cfg):
  tf=source_timeframe(plan)
  return tf if cfg.get('management',{}).get('respect_entry_horizon',True) and plan.get('lane')=='PENDING' and tf in ('H1','H4','D1','W1') else 'M15'
 @classmethod
 def evaluate(cls,plan,frames,side,rr,cfg,entry_time=None,now=None):
  tf=cls.timeframe(plan,cfg);f=frames.get(tf);period=PERIODS[tf]
  out={'policy':'STRUCTURE_V2','timeframe':tf,'exit':False,'state':'NORMAL_NOISE','reason':'','origin':'PENDING' if plan.get('lane')=='PENDING' else 'DIRECT_RUNNER'}
  if f is None or len(f.bars)<4:return {**out,'state':'WAITING_CANDLE'}
  last,previous=f.bars[-1],f.bars[-2];signal_period=PERIODS.get(plan.get('signal_timeframe') or source_timeframe(plan),900)
  if last.time+period<=int(plan.get('bar_time',0))+signal_period:return out
  if entry_time is not None and last.time<float(entry_time):return out
  if now is not None and (last.time+period>now+2 or now-last.time-period>period+60):return {**out,'state':'WAITING_CANDLE'}
  anchor=min(b.low for b in f.bars[-4:-1]) if side==1 else max(b.high for b in f.bars[-4:-1])
  if side*(last.close-anchor)<-f.atr*.05:return {**out,'exit':True,'state':'STRUCTURAL_INVALIDATION','reason':f'Cierre {tf} rompió la estructura de continuación del runner','anchor':anchor,'closed_at':last.time+period}
  reversal=all(side*(b.close-b.open)<-f.atr*.20 and (entry_time is None or b.time>=entry_time) for b in (last,previous))
  if rr>=cfg['runner']['reversal_exit_min_r'] and reversal and side*f.trend<.05:return {**out,'exit':True,'state':'MOMENTUM_LOSS','reason':f'Dos cierres {tf} contrarios y pérdida de impulso; proteger recorrido del runner','closed_at':last.time+period}
  return {**out,'state':'ACCEPTABLE_PULLBACK' if side*(last.close-last.open)<0 else 'CONTINUATION'}

class RunnerPerformanceTracker:
 @staticmethod
 def update(row,plan,rr,profit,now):
  row.setdefault('tracking_started_at',now);row['entry_origin']='PENDING' if plan.get('lane')=='PENDING' else 'DIRECT_RUNNER';row['exit_policy']='STRUCTURE_V2'
  row['max_favorable_r']=max(float(row.get('max_favorable_r',0)),rr);row['max_adverse_r']=max(float(row.get('max_adverse_r',0)),-rr);row['last_rr']=rr
  row['max_favorable_usd']=max(float(row.get('max_favorable_usd',0)),profit)
