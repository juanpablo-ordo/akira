"""Actual constrained model verdicts for two synthetic exact orders; no sends."""
import argparse,json,tempfile,time,traceback
from pathlib import Path

def run(exe,model,report):
 from settings import load_config,DEFAULT
 from tests.fake_mt5 import Clock,FakeMT5
 from engine import Engine
 from execution import Gateway,Journal,Reporter
 from research import ContextWorker
 from akira_model_runtime import shared_runtime
 from execution_review import facts,fingerprint,request_id,validate
 from akira_version import BUILD_ID
 result={'build':BUILD_ID,'status':'FAILED','model':'REAL GGUF','market_data':'SYNTHETIC','live_account_used':False,'verdicts':{}}
 with tempfile.TemporaryDirectory(prefix='akira-review19-') as tmp:
  root=Path(tmp);cfg=load_config(DEFAULT);cfg['mode']='observe';endpoint='http://127.0.0.1:18996/v1/chat/completions'
  cfg['assistant'].update(local_runtime_enabled=True,local_endpoint=endpoint,local_runtime_exe=str(Path(exe).resolve()),local_runtime_model=str(Path(model).resolve()),provider_mode='local')
  cfg['desktop'].update(performance_profile='Ahorro de energía',model_context_tokens=2048,model_use_gpu=False,model_keep_alive_seconds=30)
  clock=Clock();api=FakeMT5(clock);g=Gateway(api,cfg,Journal(root/'j'),Reporter(root/'logs',console=False),clock);e=Engine(g,cfg,g.log);v=e.step();w=ContextWorker(cfg,root,clock);runtime=shared_runtime(cfg['assistant'],root)
  try:
   for symbol,info in v['symbols'].items():
    atr=info['frames']['H1']['atr'];entry=info['bid']-atr
    p={'symbol':symbol,'key':'QA_H1_NO_SEND','lane':'PENDING','kind':'LIMIT','side':1,'entry':entry,'sl':entry-atr*2,'tp':entry+atr*4,'volume':.01,'review_scope':'EXECUTION','risk_usd':1,'reward_usd':2,'net_rr':2,'reason':'Escenario sintético de revisión geométrica y técnica, no ejecutable.'}
    snap=e.research_snapshot();f=fingerprint(p,snap);started=time.monotonic()
    row=w._pending_summary([{'plan':p,'snapshot':snap,'fingerprint':f}],{}).get(request_id(p))
    if not row:raise AssertionError('No exact-order verdict')
    data=row['data'];validate({k:data[k] for k in ('verdict','reason','contradictions','evidence','missing')},facts(p,snap))
    if row.get('input_scope')!='EXACT_EXECUTION_FACTS':raise AssertionError('Wrong review path')
    result['verdicts'][symbol]={**row,'seconds':round(time.monotonic()-started,3),'fingerprint':f}
   if api.sent:raise AssertionError('Unexpected broker send')
   result.update(status='PASSED',broker_requests=0,effective_parameters=runtime.effective_parameters())
  except Exception:result['error']=traceback.format_exc()
  finally:
   w.close();e.close();runtime.shutdown()
   if result['status']!='PASSED' and runtime.log_path and runtime.log_path.exists():result['runtime_log_tail']=runtime.log_path.read_text(errors='replace')[-3000:]
 Path(report).parent.mkdir(parents=True,exist_ok=True);Path(report).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--exe',required=True);p.add_argument('--model',required=True);p.add_argument('--report',required=True);a=p.parse_args();r=run(a.exe,a.model,a.report);print(json.dumps(r,ensure_ascii=False));raise SystemExit(0 if r['status']=='PASSED' else 1)
