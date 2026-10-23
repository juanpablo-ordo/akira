"""Production account-switch lifecycle with synthetic MT5. No broker login."""
from __future__ import annotations
import copy,json,queue,tempfile,threading,time
from pathlib import Path
from unittest.mock import patch


def run_check():
    from akira_version import BUILD_ID
    from studio_controller import StudioController
    from settings import DEFAULT,load_config,save_config
    from tests.fake_mt5 import Clock,FakeMT5
    checks={};calls=[];controllers=[];current=[None]
    with tempfile.TemporaryDirectory(prefix='AKIRA_MT5_ACCOUNTS_') as tmp:
        root=Path(tmp);program=root/'MT5'/'terminal64.exe';program.parent.mkdir();program.write_bytes(b'SYNTHETIC FILE; NEVER EXECUTED')
        other=root/'OTHER_MT5'/'terminal64.exe';other.parent.mkdir();other.write_bytes(b'SYNTHETIC FILE; NEVER EXECUTED')
        clock=Clock();clock.now=time.time();api=FakeMT5(clock);api.account.trade_mode=0;api.terminal.path=str(program.parent)
        def initialize(*args,**kwargs):
            calls.append((args,kwargs,threading.get_ident()))
            # Reproduce native initialization's old-account selection behavior.
            if 'login' in kwargs:api.account.login=kwargs['login']
            if 'server' in kwargs:api.account.server=kwargs['server']
            return True
        api.initialize=initialize;api.shutdown=lambda:None
        cfg=load_config(DEFAULT);cfg.update(mode='observe',expected_login=123,expected_server='TEST',poll_seconds=.05)
        cfg['assistant']['auto_install_local_ai']=False
        save_config(cfg,root/'akira_config.json');risk=copy.deepcopy(cfg['risk'])
        def wait_for(predicate,timeout=10):
            end=time.monotonic()+timeout
            while time.monotonic()<end:
                if current[0]:current[0].poll()
                if predicate():return
                time.sleep(.01)
            raise RuntimeError('Account switch timed out: '+str(current[0].view.get('mt5_connection'))+'; jobs='+str(current[0]._jobs))
        def start():
            c=StudioController(root,start_actor=False);controllers.append(c);current[0]=c
            c._services_started=True;c._start_actor();return c
        def close(c):
            c.close()
            if c.actor:c.actor.join(8)
            if c.actor and c.actor.is_alive():raise RuntimeError('The MT5 account owner did not stop')
        try:
            with patch('runtime._mt5_api',return_value=api),patch('runtime.ContextWorker'),patch('mt5_connection.running_terminals',return_value=[]):
                c=start();wait_for(lambda:c.view.get('connected') is True)
                checks['initial_account_verified']=c.view['account']['login']==123 and c.view['account']['server']=='TEST'
                api.account.login=456;api.account.server='SECOND-DEMO'
                wait_for(lambda:c.view.get('mt5_connection',{}).get('code') in ('ACCOUNT_CHANGED','ACCOUNT_MISMATCH'))
                checks['manual_switch_cannot_reuse_old_authorization']=c.view.get('connected') is False and c.view.get('execution_allowed') is False
                if not c.use_open_mt5_account():raise RuntimeError('The controller rejected account inspection')
                wait_for(lambda:not c._jobs and c.view.get('connected') is True and c.view['account']['login']==456)
                checks['adopt_another_number_without_restarting']=c.cfg['expected_login']==456 and c.cfg['expected_server']=='SECOND-DEMO' and c.cfg['mode']=='observe'
                checks['fresh_engine_reads_both_assets']=set(c.view.get('symbols',{}))=={'BTCUSDm','XAUUSDm'}
                api.account.server='THIRD-DEMO'
                wait_for(lambda:c.view.get('connected') is False)
                c.use_open_mt5_account()
                wait_for(lambda:not c._jobs and c.view.get('connected') is True and c.view['account']['server']=='THIRD-DEMO')
                checks['same_number_different_server_is_adopted']=c.cfg['expected_login']==456 and c.cfg['expected_server']=='THIRD-DEMO'
                saved=load_config(root/'akira_config.json')
                checks['preferences_and_risk_preserved']=saved['risk']==risk and saved['mode']=='observe'
                checks['separate_account_journals']=len(list((root/'state').glob('cuenta_*.json')))>=3
                close(c);c=start();wait_for(lambda:c.view.get('connected') is True)
                checks['new_account_survives_restart']=c.cfg['expected_server']=='THIRD-DEMO' and c.view['account']['server']=='THIRD-DEMO'
                api.terminal.path=str(other.parent)
                with patch('mt5_connection.running_terminals',return_value=[str(other)]):
                    c.use_open_mt5_account(terminal_path='')
                    wait_for(lambda:not c._jobs and c.view.get('connected') is True and c.cfg['terminal_path']==str(other))
                checks['running_terminal_can_replace_old_path']=c.cfg['terminal_path']==str(other)
                checks['never_forces_remembered_login_or_server']=bool(calls) and all(set(options)=={'timeout'} for _,options,_ in calls)
                checks['no_credentials_in_connection_metadata']=set(json.loads((root/'state/mt5_connection.json').read_text(encoding='utf-8')))=={'terminal_path','login','server'}
                close(c)
                checks['single_mt5_owner']=all(tid in {c.actor.ident for c in controllers} for _,_,tid in calls) and all(not c.actor.is_alive() for c in controllers)
                checks['no_broker_orders']=not api.sent
        finally:
            for c in controllers:close(c)
        if not all(checks.values()):raise RuntimeError('MT5 account-switch checks failed: '+str(checks))
    return {'status':'PASSED','build':BUILD_ID,'broker':'FakeMT5','engine':'production StudioController, Engine and run_session',
            'live_account_used':False,'native_mt5_login_tested':False,'checks':checks}


if __name__=='__main__':
    print(json.dumps(run_check(),ensure_ascii=False))
