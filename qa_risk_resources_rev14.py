"""Risk settings through the real Qt/controller/actor. Synthetic broker only."""
import copy,json,tempfile,threading,time
from pathlib import Path
from unittest.mock import patch

DELL_7280={'ram_gb':8,'physical_cores':2,'logical_cores':4}


def run_check():
    from PySide6.QtWidgets import QApplication,QWidget
    from desktop_qt import StudioWindow
    from settings import DEFAULT,load_config,save_config
    from tests.fake_mt5 import Clock,FakeMT5
    from akira_version import BUILD_ID
    from akira_model_runtime import ManagedLlamaProcess,hardware_profile
    app=QApplication.instance() or QApplication([]);checks={};window=None;controller=None
    with tempfile.TemporaryDirectory(prefix='AKIRA_RISK_REV14_') as tmp:
        root=Path(tmp);program=root/'MT5'/'terminal64.exe';program.parent.mkdir();program.write_bytes(b'SYNTHETIC FIXTURE; NEVER EXECUTED')
        clock=Clock();clock.now=time.time();api=FakeMT5(clock)
        api.account.balance=api.account.equity=api.account.margin_free=37.89;api.account.trade_mode=0;api.terminal.path=str(program.parent)
        calls=[]
        def initialize(*args,**kwargs):calls.append(threading.get_ident());return True
        api.initialize=initialize;api.shutdown=lambda:None
        cfg=load_config(DEFAULT);cfg['capital_protection']['enabled']=False;cfg.update(mode='observe',expected_login=123,expected_server='TEST',poll_seconds=.05)
        cfg['risk'].update(max_trade_money=10000000,max_trade_pct=100,portfolio_money_cap=100000000,portfolio_capital_pct=100,daily_loss_money=100000000,daily_loss_pct=100,minimum_margin_level_pct=300)
        cfg['runner'].update(max_trade_budget_pct=100,allow_size_boost=True)
        cfg['assistant'].update(auto_install_local_ai=False,local_runtime_enabled=False);cfg['desktop']['privacy']=False
        save_config(cfg,root/'akira_config.json')
        def wait_for(predicate):
            end=time.monotonic()+10
            while time.monotonic()<end:
                app.processEvents()
                if window:window.poll()
                if predicate():return
                time.sleep(.01)
            raise RuntimeError('Risk UI check timed out: '+str(controller.view.get('mt5_connection'))+' jobs='+str(controller._jobs))
        try:
            with patch('runtime._mt5_api',return_value=api),patch('runtime.ContextWorker'),patch('mt5_connection.running_terminals',return_value=[]),patch('resource_optimizer.desktop_hardware',return_value=DELL_7280):
                window=StudioWindow(root,preview=False,start_actor=False);window.resize(1366,768);window.show();controller=window.controller
                controller._services_started=True;controller._start_actor()
                wait_for(lambda:controller.view.get('connected'));window.navigate(2);window.render(controller.view)
                checks['screenshot_values_preserved']=controller.cfg['risk']==cfg['risk'] and controller.cfg['runner']['allow_size_boost'] is True
                checks['configured_budget_is_distinct_from_empty_usage']=window.budget_limit_bar.value()==100 and window.budget_bar.value()==0 and 'Sin órdenes' in window.budget_text.text()
                checks['effective_limit_matches_account']=controller.view['risk_limits']['portfolio']==37.89 and '37.89' in window.budget_config.text()
                checks['raw_limits_are_visible']='10,000,000' in window.budget_config.text() and '100,000,000' in window.budget_config.text()
                panel=window.settings_panel;window.open_settings(1)
                panel.fields['risk.max_trade_money'][0].setValue(2.5);panel.fields['risk.max_trade_pct'][0].setValue(10)
                panel.fields['risk.portfolio_money_cap'][0].setValue(5);panel.fields['risk.portfolio_capital_pct'][0].setValue(25)
                panel.fields['runner.max_trade_budget_pct'][0].setValue(50)
                checks['edit_preview_explains_unsaved_limits']='2.50' in panel.risk_preview.text() and 'sin guardar' in panel.risk_preview.text()
                # An unrelated unsaved field is not part of the risk transaction.
                old_voice=controller.cfg['voice']['rate'];panel.fields['voice.rate'][0].setValue(137)
                controls=len(panel.findChildren(QWidget))
                for _ in range(10):panel.refresh_risk_preview(force=True)
                with patch.object(window,'apply_visual',wraps=window.apply_visual) as visual,patch.object(window,'set_avatar',wraps=window.set_avatar) as avatar:
                    window.save_risk_limits()
                    wait_for(lambda:not controller._jobs and controller.view.get('risk_limits',{}).get('portfolio')==5)
                    checks['risk_save_does_not_rebuild_appearance_or_avatar']=not visual.called and not avatar.called and len(panel.findChildren(QWidget))==controls
                checks['save_reaches_financial_actor']=controller.view['risk_limits']['per_trade']==2.5 and controller.view['risk_limits']['runner']==1.25
                checks['save_keeps_other_form_edits']=controller.cfg['voice']['rate']==old_voice and panel.fields['voice.rate'][1]()==137
                window.navigate(2);window.render(controller.view)
                checks['main_window_updates_saved_limits']='2.50' in window.metrics['reserved_risk'].value.text() and 'En uso: 0.00' in window.metrics['reserved_risk'].caption.text() and window.budget_limit_bar.value()==13 and window.budget_bar.value()==0
                checks['applied_state_is_confirmed']='Aplicado' in window.budget_status.text()
                from types import SimpleNamespace as NS
                api.add_pending(NS(side=1,kind='LIMIT',symbol='BTCUSDm',entry=59970,sl=59800,tp=60300))
                wait_for(lambda:controller.view.get('reserved_risk',0)>0);window.render(controller.view)
                checks['usage_changes_only_with_broker_reservations']=window.budget_bar.value()>0 and controller.view['portfolio_risk']['pending_orders']==1
                persisted=load_config(root/'akira_config.json')
                checks['limits_survive_reload']=persisted['risk']['portfolio_money_cap']==5 and persisted['risk']['max_trade_money']==2.5 and persisted['risk']['daily_loss_money']==100000000
                window.navigate(3);window.render(controller.view);chart=next(iter(window.analysis_widgets.values()))[2]
                chart.grab();before=chart._raster_count
                for _ in range(4):chart.grab()
                checks['unchanged_chart_repaints_use_cached_image']=chart._raster_count==before
                checks['hidden_source_documents_are_not_built']=not getattr(window.source_content,'_studio_document',None)
                checks['automatic_laptop_profile_is_effective']=window._render_interval==.8 and controller._runtime_cfg['desktop']['performance_profile']=='Ahorro de energía'
                managed=ManagedLlamaProcess({'local_runtime_enabled':True},profile=hardware_profile(8,0,4))
                with patch.object(managed,'_paths',return_value=(Path('/cpu/llama-server.exe'),Path('/model.gguf'))):
                    command=managed.command('http://127.0.0.1:18987/v1/chat/completions',cfg['desktop'])
                value=lambda key:command[command.index(key)+1]
                checks['laptop_model_has_one_thread_small_context_and_no_gpu']=value('--threads')=='1' and value('--ctx-size')=='2048' and value('--n-gpu-layers')=='0'
                checks['one_actor_owns_mt5']=bool(calls) and set(calls)=={controller.actor.ident}
                checks['no_broker_orders_sent']=not api.sent
        finally:
            if window:window.close();app.processEvents()
            if controller and controller.actor:controller.actor.join(8)
        checks['actor_stops_cleanly']=controller is not None and not controller.actor.is_alive()
        if not all(checks.values()):raise RuntimeError('Risk/resource checks failed: '+str(checks))
    return {'status':'PASSED','build':BUILD_ID,'checks':checks,'broker':'FakeMT5','live_account_used':False,
        'hardware_policy':'Dell Latitude 7280 class: simulated 8 GB, 2 physical / 4 logical cores',
        'real_laptop_tested':False,'real_model_in_this_check':False}


if __name__=='__main__':print(json.dumps(run_check(),ensure_ascii=False))
