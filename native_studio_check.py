"""Exercise the default Qt frontend with disposable FakeMT5 data, no live IO."""
from pathlib import Path
from types import SimpleNamespace as NS
import copy,json,tempfile,time

STUDIO_CHECK_VERSION=1
REQUIRED=('eight_pages','real_records','privacy','stable_selection','responsive','shared_avatar',
          'no_expression_gallery','global_wallpaper','live_theme','language_switch','event_loop','no_broker_requests','per_asset_activity','mt5_reconnect','mt5_account_switch','risk_budget_resources')

def settle(app,seconds=.03):
    until=time.monotonic()+seconds
    while time.monotonic()<until:app.processEvents();time.sleep(.002)

def require_studio_check(report):
    check=report.get('studio_check') or {}
    if check.get('status')!='PASSED' or check.get('version')!=STUDIO_CHECK_VERSION:raise RuntimeError('Falta la autocomprobación de la interfaz Studio predeterminada')
    for key in REQUIRED:
        if check.get(key) is not True:raise RuntimeError('Autocomprobación Studio falló en '+key)
    return check

def run_studio_check(screenshot_dir=None):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication,QPushButton
    from PIL import Image
    from desktop_qt import StudioWindow
    from execution import Gateway,Journal,Reporter
    from engine import Engine
    from settings import load_config,DEFAULT,save_config
    from tests.fake_mt5 import Clock,FakeMT5
    app=QApplication.instance() or QApplication([]);checks={};window=None;engine=None
    with tempfile.TemporaryDirectory(prefix='AKIRA_STUDIO_CHECK_') as tmp:
        root=Path(tmp);cfg=load_config(DEFAULT);cfg['mode']='observe';cfg['desktop']['privacy']=False;cfg['assistant']['auto_install_local_ai']=False;save_config(cfg,root/'akira_config.json')
        try:
            window=StudioWindow(root,preview=True,start_actor=False);window.resize(1680,980);window.show();settle(app)
            clock=Clock();api=FakeMT5(clock)
            api.add_pending(NS(side=1,kind='LIMIT',symbol='BTCUSDm',entry=59970,sl=59800,tp=60300));api.add_position(magic=0,comment='AUTOCHECK SYNTHETIC')
            gateway=Gateway(api,cfg,Journal(root/'check.json'),Reporter(root/'check_logs',console=False),clock);engine=Engine(gateway,cfg,gateway.log)
            view=engine.step();view['preview']=True;window.controller.view=view;window.render(view);before=len(api.sent)
            for i in range(8):
                window.navigate(i);settle(app)
                if screenshot_dir:
                    output=Path(screenshot_dir);output.mkdir(parents=True,exist_ok=True);window.grab().save(str(output/f'page_{i}.png'))
                if window.book.currentIndex()!=i or window.grab().isNull():raise RuntimeError('Página Studio '+str(i)+' no dibujada')
            checks['eight_pages']=window.book.count()==8
            window.navigate(3);settle(app)
            checks['per_asset_activity']=all(view['symbols'][s].get('checked_at') and 'Revisado hace' in window.asset_activity_labels[s].text() for s in ('BTCUSDm','XAUUSDm'))
            window.navigate(2);settle(app)
            checks['real_records']=window.orders.rowCount()==len(view['orders']) and window.positions.rowCount()==len(view['positions']) and bool(view['orders']) and bool(view['positions'])
            window.private=True;window.render(view);checks['privacy']='••••' in window.metrics['balance'].value.text() and str(view['account']['login']) not in window.account_badge.text()
            window.private=False;window.render(view);checks['privacy']=checks['privacy'] and '100' in window.metrics['balance'].value.text()
            window.navigate(1);settle(app);window.pending_table.selectRow(0);key=window.pending_table.selected_key();window.render_pending();checks['stable_selection']=key is not None and key==window.pending_table.selected_key()
            window.resize(1024,768);settle(app);checks['responsive']=window._metric_columns==3 and window.pending_split.orientation().name=='Vertical' and window.nav[-1].isEnabled()
            window.director.publish('thinking','check',force=True);checks['shared_avatar']=all(a.director is window.director and a.selected.id==window.director.selected.id for a in window.avatars)
            checks['no_expression_gallery']=not any('108' in b.text() or 'expresiones' in b.text().lower() for b in window.findChildren(QPushButton))
            image=root/'background.png';Image.new('RGB',(180,120),'#e03472').save(image)
            style=copy.deepcopy(cfg['studio']);style['wallpaper'].update(enabled=True,kind='image',file=str(image),opacity=90)
            window.apply_visual(style);settle(app,.25)
            checks['global_wallpaper']=not window.surface.image.isNull() and all(window.surface.isAncestorOf(page) for page in window.pages)
            a=window.surface.grab().toImage();style['theme']='Nebulosa';style['wallpaper']['enabled']=False;window.apply_visual(style);settle(app);b=window.surface.grab().toImage()
            checks['live_theme']=a.pixel(2,2)!=b.pixel(2,2) and '#100d25' in window.styleSheet()
            style['language_ui']='en';window.apply_visual(style);checks['language_switch']=window.nav[6].text()=='SETTINGS';style['language_ui']='es';window.apply_visual(style)
            tick=[];QTimer.singleShot(10,lambda:tick.append(time.monotonic()));settle(app,.1);checks['event_loop']=bool(tick)
            checks['no_broker_requests']=len(api.sent)==before and window.controller.actor is None
            from qa_mt5_reconnect_rev12 import run_check
            reconnect=run_check();checks['mt5_reconnect']=reconnect['status']=='PASSED'
            from qa_mt5_accounts_rev13 import run_check as check_accounts
            accounts=check_accounts();checks['mt5_account_switch']=accounts['status']=='PASSED'
            from qa_risk_resources_rev14 import run_check as check_risk
            risk=check_risk();checks['risk_budget_resources']=risk['status']=='PASSED'
            result={'version':STUDIO_CHECK_VERSION,'status':'PASSED','data':'SYNTHETIC','broker':'FakeMT5',
                'mt5_reconnect_details':reconnect,'mt5_account_switch_details':accounts,'risk_budget_resources_details':risk,**{k:bool(v) for k,v in checks.items()}}
            require_studio_check({'studio_check':result});return result
        finally:
            if engine:engine.close()
            if window:window.close();settle(app)

