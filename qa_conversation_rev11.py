"""Real bundled conversation with a live Qt UI and a synthetic BTC/XAU actor.

Two logical CPUs, no live account, no Internet requests. Measures the app AND its
owned model process while the real model answers, rather than an idle GUI only.
"""
import argparse
import json
import math
import tempfile
import threading
import time
import traceback
from pathlib import Path


def run(exe, model, report):
    import psutil
    from PySide6.QtWidgets import QApplication
    from desktop_qt import StudioWindow
    from engine import Engine
    from execution import Gateway, Journal, Reporter
    from resource_optimizer import profile_budget
    from settings import DEFAULT, load_config, save_config
    from tests.fake_mt5 import Clock, FakeMT5
    from akira_version import BUILD_ID

    report=Path(report);report.parent.mkdir(parents=True,exist_ok=True)
    process=psutil.Process();previous=process.cpu_affinity();selected=previous[:2]
    process.cpu_affinity(selected)
    result={'status':'FAILED','build':BUILD_ID,'live_account_used':False,
        'market_data':'SYNTHETIC FakeMT5','conversation_model':'REAL bundled GGUF',
        'internet_requests_enabled':False,'logical_cpus':len(selected),'scenarios':[]}
    app=QApplication.instance() or QApplication([])
    stop=threading.Event();done=threading.Event();window=None;engine=None
    market_thread=None;chat_thread=None;actor_errors=[];cycles=[];fresh=[]
    cpu={};peak_mb=0;started=time.monotonic();_qa_temp=None

    def sample():
        nonlocal peak_mb
        procs=[process]
        if window:
            owned=window.controller.assistant._managed_model.proc
            if owned and owned.poll() is None:
                try:procs.append(psutil.Process(owned.pid))
                except psutil.Error:pass
        memory=0
        for proc in procs:
            try:
                times=proc.cpu_times();total=times.user+times.system
                if proc.pid not in cpu:cpu[proc.pid]=[total if proc.pid==process.pid else 0,total]
                cpu[proc.pid][1]=max(cpu[proc.pid][1],total)
                memory+=proc.memory_info().rss
            except psutil.Error:pass
        peak_mb=max(peak_mb,memory/1048576)

    try:
        _qa_temp=tempfile.TemporaryDirectory(prefix='AKIRA_REAL_REV11_');temporary=_qa_temp.name
        root=Path(temporary);cfg=load_config(DEFAULT)
        cfg['mode']='observe'
        cfg['desktop'].update(profile_budget('Ahorro de energía'),performance_profile='Ahorro de energía')
        cfg['assistant'].update(local_runtime_enabled=True,local_runtime_exe=str(Path(exe).resolve()),
            local_runtime_model=str(Path(model).resolve()),
            local_endpoint='http://127.0.0.1:18996/v1/chat/completions',
            local_runtime_start_on_launch=False,auto_research=False,auto_youtube_research=False,
            self_review=False,cloud=False,fast_chat_timeout_seconds=120)
        save_config(cfg,root/'akira_config.json')
        window=StudioWindow(root,preview=True,start_actor=False)
        window.resize(1366,768);window.show();window.navigate(3)
        clock=Clock();clock.now=1792407600
        api=FakeMT5(clock);gateway=Gateway(api,cfg,Journal(root/'bench.json'),Reporter(root/'bench-log',console=False),clock)
        engine=Engine(gateway,cfg,gateway.log)
        base={symbol:tick.bid for symbol,tick in api.ticks.items()}

        def market():
            try:
                while not stop.is_set():
                    began=time.monotonic();clock.advance(cfg['poll_seconds'])
                    for symbol in base:
                        api.set_quote(symbol,base[symbol]+math.sin(clock.now*2)*(5 if symbol.startswith('BTC') else .15),fill=False)
                    view=engine.step();cycles.append(view['cycle_ms'])
                    fresh.append(all(0<=clock()-row['quote_time']<1 for row in view['symbols'].values()))
                    window.controller.publish(view)
                    stop.wait(max(.02,cfg['poll_seconds']-(time.monotonic()-began)))
            except Exception:
                actor_errors.append(traceback.format_exc());done.set()

        def converse():
            try:
                bot=window.controller.assistant
                cases=[
                    ('identity','¿Quién eres?',lambda a:'akira' in a),
                    ('presence_typo','¿Me escuhas, Akira?',lambda a:'leo' in a),
                    ('capabilities','Oye Akira, ¿qué puedes hacer?',lambda a:'conversar' in a),
                    ('new_topic_typo','Me esplicas la diferncia entre la memroia RAM y el disco de una compuadora?',lambda a:'ram' in a and any(w in a for w in ('disco','ssd','almacenamiento'))),
                    ('followup','¿Cuál pierde los datos cuando apago la computadora?',lambda a:'ram' in a and any(w in a for w in ('pierde','perder','borra','volatil','volátil','apaga','apagado'))),
                    ('personal_conversation','Hoy me siento nervioso por una entrevista. ¿Qué puedo hacer para calmarme?',lambda a:any(w in a for w in ('respir','practic','calm','pausa','tranquil')))
                ]
                for name,question,check in cases:
                    if stop.is_set():raise RuntimeError('QA interrupted')
                    window.controller.chat_busy=True;began=time.monotonic()
                    events=[];original_progress=bot.progress_callback
                    def progress(row):
                        events.append((time.monotonic(),row))
                        if original_progress:original_progress(row)
                    bot.progress_callback=progress
                    try:answer=bot.reply(question,dict(window.controller.view),use_cloud=False)
                    finally:bot.progress_callback=original_progress
                    window.controller.chat_busy=False
                    first=next((at-began for at,event in events if event.get('stage')=='RESPONDIENDO'),None)
                    row={'name':name,'question':question,'answer':answer,'seconds':round(time.monotonic()-began,3),
                         'first_visible_seconds':round(first,3) if first is not None else None}
                    result['scenarios'].append(row)
                    print(name+' '+str(row['seconds'])+'s '+answer[:180],flush=True)
                    if not check(answer.casefold()):raise AssertionError('Irrelevant answer: '+name)
                    if any(x in answer.casefold() for x in ('no llegó una respuesta de ia','no pude completar','motor de conversación no consiguió')):
                        raise AssertionError('Conversation fallback instead of a real answer: '+name)
                result['model_effective_parameters']=bot._managed_model.effective_parameters()
                command=bot._managed_model._launch_command or []
                result['model_command_limits']={key:command[command.index(key)+1] for key in
                    ('--threads','--threads-batch','--poll','--poll-batch','--ctx-size','--n-gpu-layers','--load-mode','--cache-ram') if key in command}
            except Exception:
                result['conversation_error']=traceback.format_exc()
            finally:
                window.controller.chat_busy=False;done.set()

        started=time.monotonic();sample();market_thread=threading.Thread(target=market,daemon=True);market_thread.start()
        chat_thread=threading.Thread(target=converse,daemon=True);chat_thread.start()
        deadline=time.monotonic()+600
        while not done.is_set() and time.monotonic()<deadline:
            app.processEvents();sample();time.sleep(.01)
        app.processEvents();sample()
        elapsed=time.monotonic()-started
        delays=sorted(window.ui_delays);ordered=sorted(cycles)
        cpu_seconds=sum(max(0,end-begin) for begin,end in cpu.values())
        result.update(wall_seconds=round(elapsed,3),cpu_seconds_app_and_owned_model=round(cpu_seconds,3),
            cpu_percent_of_available_cpus=round(cpu_seconds/max(.01,elapsed)/max(1,len(selected))*100,2),
            peak_app_and_model_mb=round(peak_mb,1),memory_peak_limit_mb=3200,
            ui_delay_p95_ms=round(delays[min(len(delays)-1,int(len(delays)*.95))],2) if delays else None,
            engine_cycle_p95_ms=round(ordered[min(len(ordered)-1,int(len(ordered)*.95))],2) if ordered else None,
            engine_cycles=len(cycles),fresh_quote_cycles=sum(fresh),actor_errors=actor_errors)
        result['status']='PASSED' if (done.is_set() and not actor_errors and not result.get('conversation_error')
            and len(result['scenarios'])==6 and result['cpu_percent_of_available_cpus']<80
            and result['ui_delay_p95_ms'] is not None and result['ui_delay_p95_ms']<200
            and peak_mb<=3200 and len(cycles)>=20 and all(fresh)) else 'FAILED'
    except Exception:
        result['error']=traceback.format_exc()
    finally:
        stop.set()
        if window:window.controller.assistant.cancel_current_reply()
        if market_thread:market_thread.join(10)
        if chat_thread:chat_thread.join(10)
        if engine:engine.close()
        if window:
            window.controller.assistant._managed_model.shutdown()
            window.close();app.processEvents()
        process.cpu_affinity(previous)
        if _qa_temp:_qa_temp.cleanup()
        report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--exe',required=True);parser.add_argument('--model',required=True);parser.add_argument('--report',required=True)
    args=parser.parse_args();out=run(args.exe,args.model,args.report)
    print(json.dumps(out,ensure_ascii=False,indent=2));raise SystemExit(0 if out['status']=='PASSED' else 1)
