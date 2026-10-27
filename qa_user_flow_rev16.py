"""The two user requests through real Qt controls and a synthetic MT5 actor."""
import copy,json,tempfile,time
from pathlib import Path
from unittest.mock import patch


def run_check(capture=None):
    from PySide6.QtCore import QPoint,QPointF,Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from desktop_qt import StudioWindow
    from settings import DEFAULT,load_config,save_config
    from tests.fake_mt5 import Clock,FakeMT5
    from akira_version import BUILD_ID

    app=QApplication.instance() or QApplication([]);checks={};window=None;controller=None
    capture=Path(capture) if capture else None
    if capture:capture.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='AKIRA_USER_FLOW_') as tmp:
        root=Path(tmp);program=root/'MT5/terminal64.exe';program.parent.mkdir();program.write_bytes(b'OWNED FIXTURE; NOT EXECUTED')
        clock=Clock();clock.now=time.time();api=FakeMT5(clock)
        api.account.balance=api.account.equity=api.account.margin_free=40
        api.account.trade_mode=0;api.terminal.path=str(program.parent)
        api.initialize=lambda *a,**k:True;api.shutdown=lambda:None
        cfg=load_config(DEFAULT);cfg.update(mode='observe',expected_login=123,expected_server='TEST',poll_seconds=.05)
        cfg['risk'].update(max_trade_money=1,max_trade_pct=100,portfolio_money_cap=3,portfolio_capital_pct=100)
        cfg['assistant'].update(local_runtime_enabled=False,auto_install_local_ai=False)
        cfg['desktop']['privacy']=False;save_config(cfg,root/'akira_config.json')

        def wait_for(predicate):
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                app.processEvents();window.poll()
                if predicate():return
                time.sleep(.005)
            raise RuntimeError('User flow timed out: '+str(controller.view.get('mt5_connection')))

        def open_window():
            nonlocal window,controller
            window=StudioWindow(root,preview=False,start_actor=False);window.resize(1366,768);window.show()
            controller=window.controller;window._ai_due=time.monotonic()+120
            window._model_status={'phase':'IDLE','ready':False}
            controller._services_started=True;controller._start_actor()
            wait_for(lambda:controller.view.get('connected'));window.render(controller.view)

        def edit(path,value):
            widget=window.settings_panel.fields[path][0]
            window.settings_panel.tabs.currentWidget().ensureWidgetVisible(widget)
            app.processEvents();QTest.mouseClick(widget.lineEdit(),Qt.MouseButton.LeftButton)
            QTest.keyClick(widget.lineEdit(),Qt.Key.Key_A,Qt.KeyboardModifier.ControlModifier)
            QTest.keyClicks(widget.lineEdit(),str(value));QTest.keyClick(widget.lineEdit(),Qt.Key.Key_Tab)

        def wheel(widget,pixels=False):
            point=widget.rect().center();global_point=widget.mapToGlobal(point)
            event=QWheelEvent(QPointF(point),QPointF(global_point),QPoint(0,-45) if pixels else QPoint(),
                QPoint() if pixels else QPoint(0,-120),Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,
                Qt.ScrollPhase.ScrollUpdate,False)
            QApplication.sendEvent(widget,event);app.processEvents()

        try:
            with patch('runtime._mt5_api',return_value=api),patch('runtime.ContextWorker'), \
                 patch('mt5_connection.running_terminals',return_value=[]), \
                 patch('resource_optimizer.desktop_hardware',return_value={'ram_gb':8,'physical_cores':2,'logical_cores':4}):
                open_window()
                checks['main_number_is_the_configured_order_limit']='1.00' in window.metrics['reserved_risk'].value.text() and 'POR ORDEN' in window.metrics['reserved_risk'].name_label.text()
                checks['zero_exposure_is_separate']='En uso: 0.00' in window.metrics['reserved_risk'].caption.text() and window.budget_bar.value()==0
                QTest.mouseClick(window.risk_adjust,Qt.MouseButton.LeftButton);app.processEvents()
                panel=window.settings_panel;area=panel.tabs.currentWidget()
                checks['adjust_button_opens_risk_controls']=window.page_index==6 and panel.tabs.currentIndex()==1
                spin=panel.fields['risk.max_trade_money'][0];area.ensureWidgetVisible(spin);app.processEvents()
                QTest.mouseClick(spin.lineEdit(),Qt.MouseButton.LeftButton)
                before=spin.value();position=area.verticalScrollBar().value();wheel(spin)
                checks['wheel_scrolls_without_changing_focused_risk']=spin.value()==before and area.verticalScrollBar().value()>position
                area.ensureWidgetVisible(spin);app.processEvents();position=area.verticalScrollBar().value();wheel(spin,True)
                checks['touchpad_scrolls_without_changing_risk']=spin.value()==before and area.verticalScrollBar().value()>position
                edit('risk.max_trade_money','2.5');edit('risk.portfolio_money_cap','8');edit('risk.portfolio_capital_pct','50')
                checks['preview_tracks_typed_values']='2.50' in panel.risk_preview.text() and '8.00' in panel.risk_preview.text() and 'sin guardar' in panel.risk_preview.text()
                area.verticalScrollBar().setValue(area.verticalScrollBar().maximum());app.processEvents()
                checks['risk_save_remains_visible_while_scrolling']=panel.risk_save_button.isVisible() and window.rect().contains(panel.risk_save_button.mapTo(window,panel.risk_save_button.rect().center()))
                QTest.mouseClick(panel.risk_save_button,Qt.MouseButton.LeftButton)
                wait_for(lambda:not controller._jobs and controller.view.get('risk_limits',{}).get('portfolio')==8)
                checks['clicked_save_applies_to_actor']=controller.view['risk_limits']['per_trade']==2.5
                window.navigate(2);window.render(controller.view)
                checks['main_number_changes_after_save']='2.50' in window.metrics['reserved_risk'].value.text()
                checks['budget_shows_limit_and_usage']=window.budget_limit_bar.value()==20 and '8.00' in window.budget_limit_bar.format() and all(s in window.budget_bar.format() for s in ('0.00','en uso'))
                checks['motor_confirms_application']='Aplicado en el motor' in window.budget_status.text()
                window.sync_chat_activity()
                checks['active_market_is_not_presented_as_idle']='Analizando BTC y oro' in window.ai_label.text()
                bot=controller.assistant;bot.conversation.begin('Una pregunta');bot.conversation.update('THINKING');controller.chat_busy=True;window.sync_chat_activity()
                checks['chat_takes_precedence_over_market']='Pensando' in window.ai_label.text()
                bot.conversation.finish();controller.chat_busy=False;window.sync_chat_activity()
                checks['thinking_text_clears_after_conversation']=not window.chat_progress.text()
                window.open_settings(5);memory=panel.fields['desktop.memory_budget_mb'][0];page=panel.tabs.currentWidget();page.ensureWidgetVisible(memory);app.processEvents()
                before=memory.value();wheel(memory)
                checks['scroll_does_not_change_performance_budget']=memory.value()==before
                window.navigate(5)
                for i in range(20):bot.chats.append('assistant',('Contenido de prueba '+str(i)+' · ')*60)
                window.render_chat();app.processEvents();bar=window.chat_view.verticalScrollBar();bar.setValue(bar.maximum()//2);position=bar.value()
                bot.chats.append('assistant','Nueva respuesta de prueba');window.render_chat();app.processEvents()
                checks['new_chat_text_preserves_user_scroll']=abs(bar.value()-position)<=2
                for width in (900,1024,1366):
                    window.resize(width,768);app.processEvents()
                    checks['chat_fits_'+str(width)]=window.book.currentWidget().horizontalScrollBar().maximum()==0
                    if capture:window.grab().save(str(capture/('chat_'+str(width)+'.png')))
                window.resize(1366,768);window.navigate(2);app.processEvents()
                if capture:window.grab().save(str(capture/'risk_saved.png'))
                window.close();app.processEvents();controller.actor.join(8)
                checks['first_actor_stops_before_reopen']=not controller.actor.is_alive()
                open_window();window.navigate(2);window.render(controller.view)
                checks['limits_survive_reopening']=controller.cfg['risk']['max_trade_money']==2.5 and controller.cfg['risk']['portfolio_money_cap']==8 and '2.50' in window.metrics['reserved_risk'].value.text()
                QTest.mouseClick(window.risk_adjust,Qt.MouseButton.LeftButton);app.processEvents()
                checks['controls_survive_reopening']=window.settings_panel.fields['risk.max_trade_money'][1]()==2.5 and window.settings_panel.fields['risk.portfolio_money_cap'][1]()==8
                checks['no_broker_order_was_sent']=not api.sent
        finally:
            if controller:controller.chat_busy=False
            if window:window.close();app.processEvents()
            if controller and controller.actor:controller.actor.join(8)
        checks['last_actor_stops']=bool(controller) and not controller.actor.is_alive()
        if not all(checks.values()):raise RuntimeError('User flow failed: '+json.dumps(checks,ensure_ascii=False))
    return {'status':'PASSED','build':BUILD_ID,'checks':checks,'broker':'SYNTHETIC FakeMT5',
        'real_model_in_this_check':False,'live_account_used':False,'real_laptop_tested':False,
        'input':'QtTest mouse and keyboard; QWheelEvent angle and pixel deltas'}


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);p.add_argument('--capture',type=Path);args=p.parse_args()
    result=run_check(args.capture);args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
