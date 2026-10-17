"""Exercise the actual desktop in the frozen executable using disposable data.

Never initialize MT5, connect to a model, research the web, or load live userdata.
This check runs before installer activation and fails on a partially rendered UI.
"""
from pathlib import Path
from types import SimpleNamespace
import json,tempfile,time

from frozen_ui_contract import UI_CHECK_VERSION,require_render_check

def settle_layout(window):
    """Let the 75/170 ms resize and divider callbacks finish before measuring."""
    deadline=time.monotonic()+.25
    while time.monotonic()<deadline:
        window.update()
        time.sleep(.01)
    window.update_idletasks()

def control_geometry(window,widget,check_text=False):
    """Check bounds and the native widget's natural text size on this platform."""
    width,height=widget.winfo_width(),widget.winfo_height()
    x=widget.winfo_rootx()-window.winfo_rootx()
    y=widget.winfo_rooty()-window.winfo_rooty()
    inside=bool(widget.winfo_ismapped() and width>0 and height>0 and x>=-2 and y>=-2
        and x+width<=window.winfo_width()+2 and y+height<=window.winfo_height()+2)
    result={'x':x,'y':y,'width':width,'height':height,'inside':inside}
    if check_text:
        from tkinter import font
        face=font.Font(root=widget,font=widget.cget('font'))
        text=str(widget.cget('text'))
        def pixels(option):return widget.winfo_pixels(widget.cget(option))
        border=pixels('borderwidth')+pixels('highlightthickness')
        usable=width-2*(border+pixels('padx'))
        parts=text.split() if pixels('wraplength')>0 else text.splitlines()
        needed=max((face.measure(part) for part in parts),default=0)
        # Win32 buttons use dialog units and native insets; adding padx/pady
        # to font metrics does not describe their actual requested geometry.
        # An unmapped probe measures the same native control with its explicit
        # width/height removed. It never changes or invokes the real widget.
        import tkinter as tk
        native={'Button':tk.Button,'Label':tk.Label}.get(widget.winfo_class())
        if native is not None:
            keys=widget.keys()
            options={name:widget.cget(name) for name in (
                'text','font','padx','pady','borderwidth','highlightthickness',
                'wraplength','justify','compound','default','anchor','relief',
                'underline','state') if name in keys}
            probe=native(widget.master,**options,width=0,height=0)
            try:
                natural_width,natural_height=probe.winfo_reqwidth(),probe.winfo_reqheight()
            finally:probe.destroy()
            readable=width+2>=natural_width and height+2>=natural_height
            result.update(native_text_width=natural_width,native_text_height=natural_height)
        else:
            readable=usable+2>=needed and height+2>=face.metrics('linespace')+2*(border+pixels('pady'))
        result.update(text_width=needed,available_text_width=usable,readable=bool(readable))
    result['passed']=bool(inside and result.get('readable',True))
    return result

def strategy_directory_rendered(app):
    # Tk returns integer 0/1. The executable contract requires JSON true/false.
    return bool(len(app.strategy_tree.get_children())>=18 and
        app.strategy_refresh_button.winfo_ismapped() and app.strategy_export_button.winfo_ismapped())

def run_ui_check(window):
    from desktop import Desktop
    from settings import DEFAULT,load_config
    from execution import Gateway,Journal,Reporter
    from engine import Engine
    from tests.fake_mt5 import Clock,FakeMT5
    app=None;engine=None
    with tempfile.TemporaryDirectory(prefix='AKIRA_AUTOCOMPROBACION_') as tmp:
        root=Path(tmp);cfg=load_config(DEFAULT);cfg['mode']='observe'
        cfg['assistant']['auto_install_local_ai']=False
        cfg['desktop'].update(privacy=False,notifications=False,notification_sound=False,notification_popup=False)
        (root/'akira_config.json').write_text(json.dumps(cfg),encoding='utf-8')
        try:
            app=Desktop(window,root,preview=True,start_actor=False)
            app.assistant.local_ai_status=lambda:{'ready':False,'phase':'DISABLED','detail':'Autocomprobación; asistente y red no consultados.'}
            clock=Clock();api=FakeMT5(clock)
            for symbol in ('BTCUSDm','XAUUSDm'):
                quote=api.ticks[symbol];gap=30 if symbol.startswith('BTC') else 1
                api.add_pending(SimpleNamespace(side=1,kind='LIMIT',symbol=symbol,
                    entry=quote.bid-gap,sl=quote.bid-gap*3,tp=quote.bid+gap*3))
            api.add_position(magic=0,comment='Posición manual sintética de autocomprobación')
            log=Reporter(root/'proof_logs',console=False)
            gateway=Gateway(api,cfg,Journal(root/'proof_journal.json'),log,clock)
            engine=Engine(gateway,cfg,log);snapshot=engine.step();snapshot['preview']=True
            snapshot['research']['sources']={name:{'fresh':True,'usable':True,'age_seconds':1,
                'detail':'Fuente sintética para comprobar widgets; no consulta externa.'}
                for name in ('news','fed','youtube','coinglass:BTC','venue:binance','macro:FRED')}
            app.view=snapshot;app.bridge.connected=True
            app.navigate(0)
            window.geometry('1600x900-20000-20000');window.deiconify();window.update_idletasks();window.update()
            app.render(snapshot)
            window.update_idletasks()
            # Native chart widgets repaint 175ms after the last resize; wait
            # for real geometry before asserting the new split dashboard.
            settle_layout(window)
            # A split-pane resize may settle one or more animation frames later
            # depending on OS DPI and widget scheduling. Wait up to 1.5 s for
            # the actual canvas drawing, rather than falsely failing pre-paint.
            chart_deadline=time.monotonic()+1.5
            while time.monotonic()<chart_deadline:
                window.update()
                if all(c.data.get('bars') and len(c.find_all())>20 for c,_,_,_ in app.charts.values()):
                    break
                time.sleep(.03)
            if not app._render_health.get('complete'):raise RuntimeError('Paneles incompletos: '+', '.join(app._render_health.get('errors') or []))
            checks={
                'orders':len(app.orders.get_children())==len(snapshot['orders'])>0,
                'positions':len(app.positions.get_children())==len(snapshot['positions'])>0,
                'charts':all(chart.data.get('bars') and len(chart.find_all())>20 for chart,title,state,tf in app.charts.values()),
                'analysis':bool(app.frames.get_children()) and 'BITCOIN' in app.analysis_summary.get('1.0','end'),
                'sources':app.source_status['mt5'].cget('text')=='ACTIVO' and bool(app.analysis_sources.get_children()),
                'context':'BITCOIN' in app.sources_summary.get('1.0','end') and 'BTCUSDm' in app.brain_status.get('1.0','end')}
            checks['visible_amounts']='USD' in app.metrics['balance'].cget('text') and app.privacy_button.cget('text')=='OCULTAR IMPORTES'
            checks['verification_bar']=all(float(panel.verify_bar.cget('maximum'))==100 and len(panel.verify_stages.cells)==12 for panel in app.panels.values())
            app.open_verification();window.update_idletasks();window.update()
            checks['pending_verification']=len(app.pending_verification_tree.get_children())==len(snapshot['pending_verifications'])>0
            checks['verification_controls']=all(button.winfo_ismapped() and button.winfo_width()>30 for button in (app.pending_verify_request_button,app.pending_verify_deep_button,app.pending_verify_all_button))
            app.pending_verification_window.destroy()
            app.open_strategy_directory();window.update_idletasks();window.update()
            checks['strategy_directory']=strategy_directory_rendered(app)
            app.strategy_window.destroy()
            checks['live_cycle']=all('ciclo' in panel.verify_label.cget('text') and 'COBERTURA' in panel.verify_label.cget('text') for panel in app.panels.values())
            # Confirmed, synthetic history tests the same closure-notification path.
            from position_events import summarize_closure
            sample=[{'ticket':901,'position_id':900,'symbol':'BTCUSDm','type':0,'entry':0,'volume':.01,'time':clock()-70,'price':60000,'commission':-.03},
                {'ticket':902,'position_id':900,'symbol':'BTCUSDm','type':1,'entry':1,'volume':.01,'time':clock(),'price':59993,'profit':-.07,'reason':4}]
            close=summarize_closure(900,{'identifier':900,'symbol':'BTCUSDm','side':1},sample);close['currency']='USD'
            snapshot['position_closures']=[close];app.render(snapshot);app.render(snapshot)
            notices=app.notice_center.list('operación cerrada')
            checks['closure_notifications']=len(notices)==1 and '-0.10 USD' in notices[0]['body'] and 'Stop Loss' in notices[0]['body']
            for index in range(8):app.navigate(index);window.update_idletasks()
            app.navigate(6);app.settings_notebook.select(app.settings_maintenance_tab);window.update_idletasks();window.update()
            checks['uninstall_control']=bool(app.uninstall_button.winfo_ismapped() and
                app.uninstall_button.winfo_width()>30 and app.uninstall_button.cget('command'))
            from akira_expressions import get_catalog,MIN_EXPRESSIONS
            from akira_live2d import _root
            artwork=get_catalog(_root()).validate_artwork()
            checks['expression_catalog']=artwork['count']>=MIN_EXPRESSIONS
            checks['avatar_artwork']=all(avatar.expression_count>=MIN_EXPRESSIONS for avatar in app.avatars)
            app.avatars[0].set_expression('listening','autocontrol')
            checks['avatar_sync']=len({a.selected.id for a in app.avatars})==1 and len({id(a.director) for a in app.avatars})==1
            app.settings_notebook.select(app.settings_sources_tab);window.update_idletasks()
            checks['source_access_controls']=set(app.source_key_entries)=={'COINGLASS_API_KEY','YOUTUBE_API_KEY'} and all(e.cget('show') for e in app.source_key_entries.values()) and bool(app.source_save_button.cget('command'))
            from desktop_layout import _descendants
            captions=[str(w.cget('text')).lower() for w in _descendants(window) if 'text' in w.keys()]
            checks['private_avatar_controls']=not any('108 caras' in text or 'ver las 108' in text for text in captions)
            checks['operation_mode_visible']=bool(app.mode_button.winfo_ismapped() and 'NO ENVÍA ÓRDENES' in app.connection.cget('text'))
            checks['settings_navigation']=len(app.settings_notebook.tabs())>=11 and {'IDIOMA Y VOZ','PERSONALIZACIÓN','AVATAR STUDIO'}.issubset(set(app.settings_notebook.tab(i,'text') for i in app.settings_notebook.tabs())) and bool(app.settings_section.get())
            avatar=app.avatars[0];app.chat_busy=True;app.chat_started=time.monotonic();avatar.director.busy(True);settle_layout(window)
            start=avatar.canvas.itemcget(avatar._spinner,'start');settle_layout(window)
            checks['state_animation']=bool(avatar.canvas.itemcget(avatar._spinner,'state')=='normal' and avatar.canvas.itemcget(avatar._spinner,'start')!=start)
            app.chat_busy=False;avatar.director.busy(False)
            window.geometry('1024x640+0+0');window.update_idletasks();app._apply_responsive_shell();window.update_idletasks()
            app.navigate(5);settle_layout(window)
            controls=dict(zip(('reset','report','pause'),app._toolbar_buttons))
            controls.update(chat_entry=app.chat_entry,chat_send=app.chat_send_button,call=app.call_icon,
                privacy=app.privacy_button,welcome_title=app.chat_welcome_title)
            compact_layout={name:control_geometry(window,widget,name not in ('chat_entry','call'))
                for name,widget in controls.items()}
            checks['compact_controls']=all(row['passed'] for row in compact_layout.values())
            window.geometry('1280x760+0+0');window.update_idletasks();app._apply_responsive_shell();window.update_idletasks()
            settle_layout(window)
            checks['resizable_layout']=bool(app.chat_entry.winfo_ismapped() and app.chat_entry.winfo_width()>100)
            # Exercise privacy while Settings is open: hidden financial panes
            # must still invalidate immediately, even with lazy tab rendering.
            app.cfg['desktop']['privacy']=True;app._account_revealed=False;app.render(snapshot)
            mask=('******','••••••')
            checks['privacy']=bool(app.metrics['balance'].cget('text') in mask
                and app.budget_value.cget('text') in mask
                and 'CAPITAL PRIVADO' in app.dashboard_stats.cget('text')
                and 'Importes privados' in app.portfolio_help.cget('text'))
            app.poll();checks['loop_alive']=bool(app._poll_after_id)
            checks['no_broker_requests']=not api.sent
            if not all(checks.values()):
                detail='No se completó el dibujado de '+', '.join(k for k,v in checks.items() if not v)
                failed={name:row for name,row in compact_layout.items() if not row['passed']}
                if failed:detail+='; controles: '+json.dumps(failed,ensure_ascii=False)
                raise RuntimeError(detail)
            if (root/'logs/INTERFAZ_ERRORES.log').exists():raise RuntimeError('La autocomprobación detectó errores de interfaz; no se activa el ejecutable.')
            report={'version':UI_CHECK_VERSION,'status':'PASSED','data':'SYNTHETIC','broker':'FakeMT5',
                'network_used':False,'live_account_used':False,'order_rows':len(snapshot['orders']),
                'position_rows':len(snapshot['positions']),'frame_rows':len(app.frames.get_children()),
                'expression_count':artwork['count'],'distinct_expression_cells':artwork['distinct_cells'],
                'compact_layout':compact_layout,**checks}
            # Exercise the exact installer gate here as well, before reporting success.
            require_render_check({'render_check':report})
            return report
        finally:
            if engine:engine.close()
            if app:app.close()
