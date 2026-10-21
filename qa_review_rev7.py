"""Production managed CPU review after a negative availability cache, in Eco."""
import argparse,json,tempfile,time
from pathlib import Path


def run(exe,model,report):
    from settings import load_config,DEFAULT
    from tests.fake_mt5 import Clock,FakeMT5
    from execution import Gateway,Journal,Reporter
    from engine import Engine
    from research import ContextWorker
    from akira_model_runtime import shared_runtime
    from akira_local_ai import _STATUS,_STATUS_LOCK
    with tempfile.TemporaryDirectory(prefix='akira-eco-review-') as tmp:
        root=Path(tmp);cfg=load_config(DEFAULT);endpoint='http://127.0.0.1:18996/v1/chat/completions'
        cfg['assistant'].update(local_runtime_enabled=True,local_endpoint=endpoint,local_runtime_exe=str(Path(exe).resolve()),local_runtime_model=str(Path(model).resolve()))
        cfg['desktop'].update(performance_profile='Ahorro de energía',model_context_tokens=2048,model_use_gpu=False,model_keep_alive_seconds=0)
        clock=Clock();api=FakeMT5(clock);gateway=Gateway(api,cfg,Journal(root/'j'),Reporter(root/'logs',console=False),clock)
        engine=Engine(gateway,cfg,gateway.log);view=engine.step();worker=ContextWorker(cfg,root);runtime=shared_runtime(cfg['assistant'],root)
        with _STATUS_LOCK:_STATUS.update(when=time.monotonic(),ok=False,models=[],endpoint=endpoint)
        result={'status':'FAILED','data':'SYNTHETIC','live_account_used':False,'requested_context_tokens':2048};started=time.monotonic()
        try:
            stamp=time.time();sources={name:{'updated':stamp,'data':{'items':[{'title':'Dato sintético de prueba, sin noticia real ni señal confirmada.','url':'https://example.com/test','date':'2026-10-18T00:00:00Z'}]},'error':''} for name in ('news','global_news:BLS')}
            summary=worker._summary(view,sources)
            if not all(symbol in summary for symbol in view['symbols']):raise AssertionError('Falta un activo en la revisión')
            result.update(status='PASSED',summary=summary,effective_parameters=runtime.effective_parameters())
        except Exception as error:result['error']=type(error).__name__+': '+str(error)
        finally:
            runtime.shutdown();worker.close();engine.close()
            if runtime.log_path and runtime.log_path.exists():result['engine_log_tail']=runtime.log_path.read_text(encoding='utf-8',errors='replace')[-5000:]
            result['seconds']=round(time.monotonic()-started,3);Path(report).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        if result['status']!='PASSED':raise RuntimeError(result['error'])
        return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--exe',required=True);parser.add_argument('--model',required=True);parser.add_argument('--report',type=Path,required=True);args=parser.parse_args();args.report.parent.mkdir(parents=True,exist_ok=True);print(json.dumps(run(args.exe,args.model,args.report),ensure_ascii=False,indent=2))
