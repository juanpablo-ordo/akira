"""Same-input isolated revision probes, not a fabricated account backtest."""
import json,hashlib,subprocess,sys,argparse
from pathlib import Path

def compare(sources):
 data={'plan':{'lane':'PENDING','key':'SWING:1:LIMIT:H1:1','bar_time':0,'signal_timeframe':'H1'},'side':1,'rr':-.2,'entry_time':100,'now':14400,
  'M15':[{'time':t,'open':100,'high':102,'low':98,'close':90 if t==13500 else 100,'volume':100} for t in (10800,11700,12600,13500)],
  'H1':[{'time':t,'open':100,'high':102,'low':98,'close':100,'volume':100} for t in (0,3600,7200,10800)]}
 code='''import sys,json,inspect,hashlib
from types import SimpleNamespace as N
sys.path.insert(0,sys.argv[1])
from runner import runner_exit
from strategy import Bar
from settings import load_config,DEFAULT
p=json.loads(sys.stdin.read());cfg=load_config(DEFAULT);frames={tf:N(bars=tuple(Bar(**b) for b in p[tf]),atr=2,trend=-.4 if tf=='M15' else .4) for tf in ('M15','H1')}
a=runner_exit(p['plan'],frames,1,-.2,cfg,entry_time=100,now=14400)
frames['H1'].bars=tuple(Bar(**{**b,'close':90 if b['time']==10800 else b['close']}) for b in p['H1'])
b=runner_exit(p['plan'],frames,1,-.2,cfg,entry_time=100,now=14400)
print(json.dumps({'m15_noise_exit':bool(a),'reason_noise':a,'h1_break_exit':bool(b),'reason_h1':b,'function_sha256':hashlib.sha256(inspect.getsource(runner_exit).encode()).hexdigest()}))
'''
 results={}
 for name,path in sources.items():
  path=Path(path).resolve();p=subprocess.run([sys.executable,'-c',code,str(path)],input=json.dumps(data),capture_output=True,text=True,timeout=30)
  if p.returncode:raise RuntimeError(p.stderr)
  results[name]=json.loads(p.stdout);results[name]['git_commit']=subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip()
 ok=results['Rev10']['m15_noise_exit'] and results['Rev18']['m15_noise_exit'] and not results['Rev19']['m15_noise_exit'] and results['Rev19']['h1_break_exit']
 return {'status':'PASSED' if ok else 'FAILED','scope':'SYNTHETIC_FUNCTIONAL_REGRESSION','input_sha256':hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest(),'inputs':data,'results':results,
  'profitability':{'status':'NOT_EVALUATED','reason':'Falta el historial bid/ask y comisiones de la prueba histórica referida. Estos casos solo comparan las salidas con las mismas velas y tiempos. No simulan fills, spreads ni curva de patrimonio.','net_profit':None,'profit_factor':None,'drawdown':None,'trades_per_day':None,'holding_time':None,'activation_rate':None},
  'finding':'Rev10 y Rev18 cerraban una tesis H1 por M15. Rev19 requiere invalidación H1 posterior a la entrada. No demuestra mayor rentabilidad.'}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--rev10',required=True);p.add_argument('--rev18',required=True);p.add_argument('--current',default='.');p.add_argument('--report',required=True);a=p.parse_args();r=compare({'Rev10':a.rev10,'Rev18':a.rev18,'Rev19':a.current});Path(a.report).write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(r['status']);raise SystemExit(0 if r['status']=='PASSED' else 1)
