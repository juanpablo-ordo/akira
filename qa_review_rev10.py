"""Real small-context reviews and bounded digest for BTC and gold; synthetic MT5, no sends."""
import argparse,json,tempfile,time
from pathlib import Path


def run(exe,model,report):
    from settings import DEFAULT,load_config
    from tests.fake_mt5 import Clock,FakeMT5
    from execution import Gateway,Journal,Reporter
    from engine import Engine
    from research import ContextWorker
    from akira_model_runtime import shared_runtime
    from akira_local_ai import _STATUS,_STATUS_LOCK
    from pending_verification import identity
    from akira_version import BUILD_ID
    result={'build':BUILD_ID,'status':'FAILED','data':'SYNTHETIC','live_account_used':False,'reviews':{}}
    began=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='akira-rev10-review-') as tmp:
        root=Path(tmp);cfg=load_config(DEFAULT);endpoint='http://127.0.0.1:18996/v1/chat/completions'
        cfg['mode']='observe'
        cfg['assistant'].update(local_runtime_enabled=True,local_endpoint=endpoint,local_runtime_exe=str(Path(exe).resolve()),local_runtime_model=str(Path(model).resolve()))
        cfg['desktop'].update(performance_profile='Ahorro de energía',model_context_tokens=2048,model_use_gpu=False,model_keep_alive_seconds=30)
        clock=Clock();api=FakeMT5(clock);gateway=Gateway(api,cfg,Journal(root/'j'),Reporter(root/'logs',console=False),clock)
        engine=Engine(gateway,cfg,gateway.log);view=engine.step();worker=ContextWorker(cfg,root);runtime=shared_runtime(cfg['assistant'],root)
        with _STATUS_LOCK:_STATUS.update(when=time.monotonic(),ok=False,models=[],endpoint=endpoint)
        try:
            stamp=time.time();sources={name:{'updated':stamp,'data':{'items':[{'title':'Dato sintético, sin noticia real ni señal confirmada.','url':'https://example.com/test','date':'2026-10-19T00:00:00Z'}]},'error':''} for name in ['news','fed','macro:FRED']+['global_news:fixture-'+str(i) for i in range(24)]}
            started=time.monotonic();summary=worker._summary(view,sources)
            if not all(symbol in summary for symbol in view['symbols']):raise AssertionError('Falta un activo en la revisión real')
            result['summary']=summary;result['summary_seconds']=round(time.monotonic()-started,3)
            if summary['_meta'].get('digest_version')!=2:raise AssertionError('La revisión real debe usar el resumen acotado nuevo')
            for symbol,row in view['symbols'].items():
                bid=float(row['bid']);atr=float((row.get('frames',{}).get('M15') or {}).get('atr') or bid*.001)
                plan={'symbol':symbol,'key':'QA_ONLY_NO_SEND','side':1,'kind':'LIMIT','entry':bid-atr,'sl':bid-3*atr,'tp':bid+3*atr,'volume':.01,'reason':'Caso sintético para comprobar el formato. No hay una señal validada y no se envía al bróker.'}
                worker.request_pending_reviews([plan],view,force=True)
                request=worker.pending_queue.pop(identity(plan));started=time.monotonic()
                value=worker._pending_summary([request],sources).get(identity(plan),{})
                verdict=(value.get('data') or {}).get('verdict')
                if value.get('digest_version')!=2:raise AssertionError('La revisión individual no usó el resumen nuevo')
                if verdict not in ('APPROVE','REVISE','ABSTAIN'):raise AssertionError('Dictamen incompleto para '+symbol)
                result['reviews'][symbol]={'seconds':round(time.monotonic()-started,3),**value}
            effective=runtime.effective_parameters()
            if effective.get('context_tokens')!=2048 or effective.get('gpu_layers')!=0:raise AssertionError('La prueba debe conservar el contexto pequeño y la CPU')
            if api.sent:raise AssertionError('La prueba intentó enviar una orden')
            result.update(status='PASSED',effective_parameters=effective,broker_requests=len(api.sent))
        except Exception as error:result['error']=type(error).__name__+': '+str(error)
        finally:
            runtime.shutdown();worker.close();engine.close()
            if runtime.log_path and runtime.log_path.exists():result['engine_log_tail']=runtime.log_path.read_text(encoding='utf-8',errors='replace')[-6000:]
            result['seconds']=round(time.monotonic()-began,3)
            Path(report).parent.mkdir(parents=True,exist_ok=True);Path(report).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    if result['status']!='PASSED':raise RuntimeError(result['error'])
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--exe',required=True);parser.add_argument('--model',required=True);parser.add_argument('--report',type=Path,required=True);args=parser.parse_args()
    print(json.dumps(run(args.exe,args.model,args.report),ensure_ascii=False,indent=2))
