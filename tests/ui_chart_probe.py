"""Real high-DPI widgets in a child process with a parent-owned deadline."""
from pathlib import Path
import json,subprocess,sys,tempfile,time,traceback


def run_probe_process(command,folder,timeout=45):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    report=folder/'CHART_VIEWPORT.json'
    report.unlink(missing_ok=True)
    stdout=folder/'CHART_VIEWPORT.stdout.log';stderr=folder/'CHART_VIEWPORT.stderr.log'
    issue=None
    with stdout.open('w',encoding='utf-8') as out,stderr.open('w',encoding='utf-8') as err:
        try:
            result=subprocess.run(command,cwd=Path(__file__).resolve().parents[1],
                stdout=out,stderr=err,timeout=timeout)
            if result.returncode:issue=f'código {result.returncode}'
        except subprocess.TimeoutExpired:
            issue=f'límite de {timeout} s agotado; proceso detenido'
    try:state=json.loads(report.read_text(encoding='utf-8'))
    except (OSError,ValueError):state={'status':'MISSING_REPORT'}
    if issue or state.get('status')!='PASSED':
        detail=stderr.read_text(encoding='utf-8',errors='replace')[-14000:]
        raise RuntimeError('Prueba gráfica: '+(issue or 'autocontrol fallido')+
            '\nÚltimo estado: '+json.dumps(state,ensure_ascii=False)+
            '\nRegistro: '+str(stderr)+'\n'+detail)
    return state


def probe(output):
    import tkinter as tk
    import faulthandler
    from desktop import Desktop
    from native_ui_check import chart_layout
    from settings import DEFAULT,load_config,save_config
    from engine import Engine
    from execution import Gateway,Journal,Reporter
    from tests.fake_mt5 import Clock,FakeMT5
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    state={'status':'RUNNING','phase':'initializing','platform':sys.platform,'network':'blocked',
           'python':sys.version,'snapshots':[]}
    root=None;app=None;engine=None
    def checkpoint(phase):
        state['phase']=phase
        if root is not None:
            state['window']={'width':root.winfo_width(),'height':root.winfo_height(),
                'screen_width':root.winfo_screenwidth(),'screen_height':root.winfo_screenheight(),
                'tk_scaling':float(root.tk.call('tk','scaling'))}
        if app is not None:
            state['charts']=chart_layout(app)
            state['caption_configures']=len(changes)
        temporary=output.with_suffix('.tmp')
        temporary.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
        temporary.replace(output)
        print('CHART_VIEWPORT: '+phase,flush=True)
    def require(ok,detail):
        if not ok:raise AssertionError(detail)
    def settle():
        deadline=time.monotonic()+.35
        while time.monotonic()<deadline:
            # Drain native geometry as the real self-check does. The parent
            # process enforces the deadline even if update() never returns.
            root.update()
            time.sleep(.01)
    faulthandler.enable()
    faulthandler.dump_traceback_later(10,repeat=True)
    changes=[]
    checkpoint('initializing')
    try:
        with tempfile.TemporaryDirectory(prefix='AKIRA_CHART_PROBE_') as tmp:
            folder=Path(tmp);cfg=load_config(DEFAULT);cfg['mode']='observe'
            cfg['assistant']['auto_install_local_ai']=False
            cfg['desktop'].update(privacy=False,notifications=False,notification_popup=False,notification_sound=False)
            save_config(cfg,folder/'akira_config.json')
            root=tk.Tk();root.tk.call('tk','scaling',2.0)
            state.update(tcl=root.tk.call('info','patchlevel'),tk=root.tk.call('package','provide','Tk'))
            checkpoint('constructing_desktop')
            app=Desktop(root,folder,preview=True,start_actor=False)
            for chart,title,caption,tf in app.charts.values():
                caption.bind('<Configure>',lambda event:changes.append((event.width,event.height)),add='+')
            app.assistant.local_ai_status=lambda:{'ready':False,'phase':'DISABLED','detail':'Prueba sintética'}
            clock=Clock();api=FakeMT5(clock);log=Reporter(folder/'proof_logs',console=False)
            gateway=Gateway(api,cfg,Journal(folder/'journal.json'),log,clock)
            engine=Engine(gateway,cfg,log);view=engine.step();view['preview']=True
            app.view=view;app.navigate(0)
            for width,height in ((1366,768),(1024,640)):
                checkpoint(f'before_resize_{width}x{height}')
                root.geometry(f'{width}x{height}+0+0');settle()
                checkpoint(f'before_render_{width}x{height}')
                app.render(view);settle()
                require((root.winfo_width(),root.winfo_height())==(width,height),
                    'La ventana no alcanzó el tamaño solicitado: '+root.geometry())
                layout=chart_layout(app);require(bool(layout),'No hay gráficos')
                for symbol,row in layout.items():
                    require(row['height']>=70 and row['bars']>0 and row['items']>20,(symbol,row))
                state['snapshots'].append({'requested_window':[width,height],
                    'actual_window':[root.winfo_width(),root.winfo_height()],'charts':layout})
                checkpoint(f'drawn_{width}x{height}')
            app.layout.dragging.add('dashboard_neon_lower')
            pane=app.layout.widgets['dashboard_neon_lower'][0]
            checkpoint('before_short_pane')
            pane.sash_place(0,0,115);settle()
            scroll=app.dashboard_market_scroll;scroll._sync_content()
            region=tuple(float(v) for v in root.tk.splitlist(scroll.cget('scrollregion')))
            require(region[3]-region[1]>scroll.winfo_height(),'El contenido debe ser desplazable')
            for row in chart_layout(app).values():
                require(row['height']>=70 and row['items']>20,row)
            require(not api.sent,'No se deben enviar órdenes')
            require(len(changes)<100,'El ajuste de texto no converge: '+str(len(changes)))
            checkpoint('closing')
            engine.close();engine=None
            app.close();app=None;root=None
        state['status']='PASSED';checkpoint('complete')
        return 0
    except Exception as exc:
        state.update(status='FAILED',error=f'{type(exc).__name__}: {exc}')
        checkpoint('failed');traceback.print_exc()
        return 1
    finally:
        # Preserve the diagnostic before attempting native cleanup: a stuck
        # cleanup is also terminated by the parent and remains a failure.
        if engine:engine.close()
        if app:app.close()
        elif root:root.destroy()
        faulthandler.cancel_dump_traceback_later()


if __name__=='__main__':
    import socket
    from unittest.mock import patch
    from offline_test_runner import denied
    with patch.object(socket,'getaddrinfo',denied),patch.object(socket.socket,'connect',denied), \
         patch.object(socket.socket,'connect_ex',denied),patch.object(socket,'create_connection',denied):
        raise SystemExit(probe(sys.argv[1]))
