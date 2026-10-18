"""Bounded two-core GUI + market actor workload. FakeMT5; no live account."""
import argparse,copy,json,os,sys,tempfile,threading,time
from pathlib import Path


def run(report=None,screenshots=None):
    import psutil
    from PySide6.QtWidgets import QApplication
    from desktop_qt import StudioWindow
    from execution import Gateway,Journal,Reporter
    from engine import Engine
    from research import ContextWorker
    from tests.fake_mt5 import Clock,FakeMT5
    from akira_version import BUILD_ID
    if hasattr(os,'sched_getaffinity'):
        previous=sorted(os.sched_getaffinity(0));selected=previous[:2];os.sched_setaffinity(0,selected);process=None
    else:
        process=psutil.Process();previous=process.cpu_affinity();selected=previous[:2];process.cpu_affinity(selected)
    def rss_mb():
        if process:return process.memory_info().rss/1048576
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
    app=QApplication.instance() or QApplication([]);result={'build':BUILD_ID,'data':'SYNTHETIC','broker':'FakeMT5','live_account_used':False,'logical_cores_available':len(selected),'profiles':{}}
    stop=threading.Event();actor=None;window=None;engine=None;worker=None
    try:
        with tempfile.TemporaryDirectory(prefix='akira-low-resource-') as tmp:
            root=Path(tmp);window=StudioWindow(root,preview=True,start_actor=False);window.resize(1366,768);window.show();window.navigate(3)
            cfg=window.cfg;cfg['mode']='observe';clock=Clock();clock.now=1792407600 # synthetic Monday market session
            api=FakeMT5(clock);gateway=Gateway(api,cfg,Journal(root/'bench.json'),Reporter(root/'bench-log',console=False),clock)
            worker=ContextWorker(cfg,root,clock);worker.sources={'news':{'updated':clock(),'data':{'items':[{'title':'Synthetic market context '+str(i),'url':'https://example.com/'+str(i),'date':'2026-10-19T10:00:00Z'} for i in range(80)]},'error':''}}
            engine=Engine(gateway,cfg,gateway.log,worker);cycles=[]
            def market_loop():
                while not stop.is_set():
                    began=time.monotonic();clock.advance(cfg['poll_seconds']);view=engine.step();cycles.append(float(view['cycle_ms']));window.controller.publish(view);stop.wait(max(.02,cfg['poll_seconds']-(time.monotonic()-began)))
            actor=threading.Thread(target=market_loop,name='AkiraSyntheticActor',daemon=True);actor.start()
            def settle(seconds):
                deadline=time.monotonic()+seconds
                while time.monotonic()<deadline:app.processEvents();time.sleep(.004)
            settle(4)
            for profile,minimized in [('Equilibrado',False),('Ahorro de energía',False),('Ahorro de energía',True)]:
                cfg['desktop']['performance_profile']=profile;window.apply_visual(cfg['studio'])
                if minimized:window.showMinimized()
                else:window.showNormal()
                settle(.5);window.ui_delays=[];first=len(cycles);started=time.monotonic();cpu=time.process_time();settle(8);elapsed=time.monotonic()-started;cpu=time.process_time()-cpu
                delays=sorted(window.ui_delays);times=sorted(cycles[first:]);key='minimized' if minimized else profile
                result['profiles'][key]={'cpu_seconds':round(cpu,3),'wall_seconds':round(elapsed,3),'cpu_percent_of_two_cores':round(cpu/elapsed/max(1,len(selected))*100,2),'ui_delay_p95_ms':round(delays[min(len(delays)-1,int(len(delays)*.95))],2) if delays else None,'engine_cycle_p95_ms':round(times[min(len(times)-1,int(len(times)*.95))],2) if times else None,'engine_cycles':len(times),'rss_mb':round(rss_mb(),1),'financial_poll_seconds':cfg['poll_seconds']}
                if screenshots and not minimized:
                    Path(screenshots).mkdir(parents=True,exist_ok=True);window.grab().save(str(Path(screenshots)/('low_resource_'+('eco' if profile=='Ahorro de energía' else 'balanced')+'.png')))
            eco=result['profiles']['Ahorro de energía'];result['status']='PASSED' if eco['cpu_percent_of_two_cores']<15 and eco['ui_delay_p95_ms']<150 and all(r['engine_cycles']>=15 for r in result['profiles'].values()) else 'FAILED'
    finally:
        stop.set()
        if actor:actor.join(10)
        if engine:engine.close()
        if worker:worker.close()
        if window:window.close();app.processEvents()
        process.cpu_affinity(previous) if process else os.sched_setaffinity(0,previous)
    if report:Path(report).write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path,required=True);parser.add_argument('--screenshots',type=Path);parser.add_argument('--source',type=Path);args=parser.parse_args()
    if args.source:sys.path.insert(0,str(args.source.resolve()))
    args.report.parent.mkdir(parents=True,exist_ok=True);result=run(args.report,args.screenshots);print(json.dumps(result,ensure_ascii=False,indent=2));sys.exit(0 if result['status']=='PASSED' else 1)
