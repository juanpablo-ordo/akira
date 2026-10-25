"""Comparable UI-only workload, usable against both Rev13 and current source."""
import argparse,copy,json,math,os,sys,tempfile,time
from pathlib import Path


def benchmark(source):
    sys.path.insert(0,str(Path(source).resolve()))
    import psutil
    from PySide6.QtWidgets import QApplication
    from desktop_qt import StudioWindow
    from settings import DEFAULT,load_config,save_config
    from tests.fake_mt5 import Clock,FakeMT5
    from engine import Engine
    from execution import Gateway,Journal,Reporter
    from akira_version import BUILD_ID
    if hasattr(os,'sched_getaffinity'):
        original=sorted(os.sched_getaffinity(0));os.sched_setaffinity(0,original[:2]);process=None
    else:
        process=psutil.Process();original=process.cpu_affinity();process.cpu_affinity(original[:2])
    app=QApplication.instance() or QApplication([]);window=None;engine=None
    result={'build':BUILD_ID,'broker':'FakeMT5','live_account_used':False,'logical_cpus':len(original[:2]),'workload':{'news_items':80,'sources':80,'text_characters_per_item':3200,'network':False,'inference':False},'pages':{}}
    def stats(values):
        values=sorted(values);return {'median_ms':round(values[len(values)//2],3),'p95_ms':round(values[min(len(values)-1,int(len(values)*.95))],3)}
    temporary=None
    try:
        temporary=tempfile.TemporaryDirectory(prefix='AKIRA_UI_COST_');tmp=temporary.name
        root=Path(tmp);cfg=load_config(DEFAULT);cfg['mode']='observe';cfg['desktop'].update(performance_profile='Ahorro de energía',privacy=False);cfg['assistant']['auto_install_local_ai']=False
        save_config(cfg,root/'akira_config.json')
        window=StudioWindow(root,preview=True,start_actor=False);window.resize(1366,768);window.show()
        window.poll_timer.stop();window.animation_timer.stop();window.controller.job=lambda *args,**kwargs:False
        clock=Clock();clock.now=1792407600;api=FakeMT5(clock);gateway=Gateway(api,cfg,Journal(root/'bench.json'),Reporter(root/'logs',console=False),clock);engine=Engine(gateway,cfg,gateway.log)
        view=engine.step();view['research']=view.get('research') or {}
        view['research']['sources']={f'global_news_{i}':{'enabled':True,'fresh':True,'age_seconds':1,'updated':clock(),'last_attempt':clock(),'detail':'Synthetic received source'} for i in range(80)}
        view['research']['news']=[{'title':'Synthetic source '+str(i),'url':'https://example.com/'+str(i),'text':('Synthetic educational information. '*100)[:3200]} for i in range(80)]
        window.controller.view=view
        for index,title in [(0,'trading'),(2,'account'),(3,'analysis'),(4,'sources'),(6,'settings')]:
            window.navigate(index);app.processEvents();values=[]
            for n in range(18):
                view['updated']+=.2
                for row in view['research']['sources'].values():row['age_seconds']+=.2
                start=time.perf_counter();window.render(view);app.processEvents();values.append((time.perf_counter()-start)*1000)
            result['pages'][title]=stats(values)
        window.navigate(3);app.processEvents();values=[]
        for n in range(25):
            start=time.perf_counter();window.grab();values.append((time.perf_counter()-start)*1000)
        result['forced_full_window_repaint']=stats(values)
        values=[]
        for n in range(24):
            start=time.perf_counter();window.resize(1336+(n%5)*10,738+(n%4)*10);app.processEvents();values.append((time.perf_counter()-start)*1000)
        result['resize_events']=stats(values)
        result['status']='PASSED'
    finally:
        if engine:engine.close()
        if window:window.close();app.processEvents()
        process.cpu_affinity(original) if process else os.sched_setaffinity(0,original)
        if temporary:temporary.cleanup()
    return result


def compare(before,after):
    from akira_version import BUILD_ID
    result={'status':'PASSED','scope':'UI-only synthetic workload; not a measurement on the physical Dell laptop','before':before,'after':after}
    result['analysis_median_reduction_pct']=round((1-after['pages']['analysis']['median_ms']/max(.001,before['pages']['analysis']['median_ms']))*100,2)
    result['sources_median_reduction_pct']=round((1-after['pages']['sources']['median_ms']/max(.001,before['pages']['sources']['median_ms']))*100,2)
    if before.get('build')!='AKIRA_16_4_8_STUDIO_REV13' or after.get('build')!=BUILD_ID or after['pages']['analysis']['p95_ms']>=150 or after['forced_full_window_repaint']['p95_ms']>=150:result['status']='FAILED'
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source');parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--before',type=Path);parser.add_argument('--after',type=Path)
    args=parser.parse_args()
    out=compare(json.loads(args.before.read_text(encoding='utf-8')),json.loads(args.after.read_text(encoding='utf-8'))) if args.before and args.after else benchmark(args.source)
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(out,ensure_ascii=False));raise SystemExit(0 if out['status']=='PASSED' else 1)
