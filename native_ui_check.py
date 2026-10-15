"""Exercise the actual desktop in the frozen executable using disposable data.

Never initialize MT5, connect to a model, research the web, or load live userdata.
This check runs before installer activation and fails on a partially rendered UI.
"""
from pathlib import Path
from types import SimpleNamespace
import json,tempfile

from frozen_ui_contract import UI_CHECK_VERSION,require_render_check

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
            app.navigate(6);app.settings_notebook.select(app.settings_interface_tab);window.update_idletasks();window.update()
            checks['uninstall_control']=bool(app.uninstall_button.winfo_ismapped() and
                app.uninstall_button.winfo_width()>30 and app.uninstall_button.cget('command'))
            from akira_expressions import get_catalog,MIN_EXPRESSIONS
            from akira_live2d import _root
            artwork=get_catalog(_root()).validate_artwork()
            checks['expression_catalog']=artwork['count']>=MIN_EXPRESSIONS
            checks['avatar_artwork']=all(avatar.expression_count>=MIN_EXPRESSIONS for avatar in app.avatars)
            window.geometry('1024x640+0+0');window.update_idletasks();app._apply_responsive_shell();window.update_idletasks()
            app.navigate(5);window.update_idletasks()
            checks['compact_controls']=all(item.winfo_ismapped() and item.winfo_width()>30
                and item.winfo_rootx()+item.winfo_width()<=window.winfo_rootx()+window.winfo_width()+2
                and item.winfo_rooty()+item.winfo_height()<=window.winfo_rooty()+window.winfo_height()+2
                for item in (*app._toolbar_buttons,app.chat_entry,app.chat_send_button,app.call_icon))
            checks['compact_controls']=bool(checks['compact_controls'] and app.privacy_button.winfo_width()>100
                and app.privacy_button.winfo_height()<60 and app.chat_welcome_title.winfo_reqwidth()>150)
            window.geometry('1280x760+0+0');window.update_idletasks();app._apply_responsive_shell();window.update_idletasks()
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
            if not all(checks.values()):raise RuntimeError('No se completó el dibujado de '+', '.join(k for k,v in checks.items() if not v))
            if (root/'logs/INTERFAZ_ERRORES.log').exists():raise RuntimeError('La autocomprobación detectó errores de interfaz; no se activa el ejecutable.')
            report={'version':UI_CHECK_VERSION,'status':'PASSED','data':'SYNTHETIC','broker':'FakeMT5',
                'network_used':False,'live_account_used':False,'order_rows':len(snapshot['orders']),
                'position_rows':len(snapshot['positions']),'frame_rows':len(app.frames.get_children()),
                'expression_count':artwork['count'],'distinct_expression_cells':artwork['distinct_cells'],**checks}
            # Exercise the exact installer gate here as well, before reporting success.
            require_render_check({'render_check':report})
            return report
        finally:
            if engine:engine.close()
            if app:app.close()
