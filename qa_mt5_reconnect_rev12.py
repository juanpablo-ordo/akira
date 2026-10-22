"""Exercise the real session/engine across a restart with synthetic broker data."""
from __future__ import annotations
import copy,json,os,queue,tempfile,threading,time
from pathlib import Path
from unittest.mock import patch


def run_check():
    from akira_version import BUILD_ID
    from execution import Reporter
    from settings import DEFAULT,load_config,save_config
    from tests.fake_mt5 import Clock,FakeMT5
    import runtime
    native_library=None
    if os.name=='nt':
        import MetaTrader5
        if not all(callable(getattr(MetaTrader5,name,None)) for name in ('initialize','account_info','terminal_info','shutdown')):
            raise RuntimeError('The installed MT5 Python component is incomplete')
        native_library=str(MetaTrader5.__version__)
    checks={};rows=[];actors=[]
    with tempfile.TemporaryDirectory(prefix='AKIRA_MT5_RECONNECT_') as tmp:
        root=Path(tmp);terminal=root/'MetaTrader 5'/'terminal64.exe';terminal.parent.mkdir();terminal.write_bytes(b'SYNTHETIC FILE; NEVER EXECUTED')
        clock=Clock();clock.now=time.time();api=FakeMT5(clock);api.account.trade_mode=0;api.terminal.path=str(terminal.parent)
        calls=[];shutdowns=[];fail=[False]
        def initialize(*args,**kwargs):
            calls.append((args,kwargs,threading.get_ident()))
            if fail[0]:return False
            return True
        api.initialize=initialize;api.shutdown=lambda:shutdowns.append(True);api.last_error=lambda:(-10005,'SYNTHETIC timeout')
        cfg=load_config(DEFAULT);cfg['mode']='observe';cfg['expected_login']=123;cfg['assistant']['auto_install_local_ai']=False
        save_config(cfg,root/'akira_config.json');baseline=copy.deepcopy(cfg)
        log=Reporter(root/'logs',console=False)
        def wait_for(predicate,timeout=8):
            end=time.monotonic()+timeout
            while time.monotonic()<end:
                if predicate():return
                time.sleep(.01)
            raise RuntimeError('MT5 restart scenario did not complete: '+str([r.get('mt5_connection',{}).get('code') for r in rows[-5:]]))
        def start():
            stop=threading.Event();commands=queue.Queue()
            actor=threading.Thread(target=runtime.run_session,args=(load_config(root/'akira_config.json'),root,log,stop,commands,rows.append),name='AkiraMT5Check',daemon=True)
            actors.append((actor,stop));actor.start();return actor,stop,commands
        def close(actor,stop):
            stop.set();actor.join(8)
            if actor.is_alive():raise RuntimeError('The MT5 owner did not stop')
        try:
            with patch('runtime._mt5_api',return_value=api),patch('runtime.ContextWorker'):
                actor,stop,commands=start();wait_for(lambda:any(r.get('connected') for r in rows))
                checks['first_connection_to_demo']=rows[-1].get('mt5_connection',{}).get('account_type')=='demo'
                close(actor,stop);checks['shutdown_before_reopen']=bool(shutdowns)
                rows.clear();actor,stop,commands=start();wait_for(lambda:any(r.get('connected') for r in rows))
                checks['saved_target_on_restart']=calls[-1][0]==(str(terminal),) and calls[-1][1].get('login')==123 and calls[-1][1].get('server')=='TEST'
                checks['fresh_account_and_both_assets']=set(rows[-1].get('symbols',{}))=={'BTCUSDm','XAUUSDm'} and rows[-1].get('account',{}).get('login')==123
                api.terminal.connected=False
                wait_for(lambda:rows[-1].get('mt5_connection',{}).get('code')=='BROKER_OFFLINE')
                checks['lost_broker_cannot_claim_ready']=rows[-1].get('execution_allowed') is False and rows[-1]['execution_gate']['code']=='MT5_DISCONNECTED'
                api.terminal.connected=True;commands.put({'action':'reconnect_mt5'})
                wait_for(lambda:rows[-1].get('connected') is True)
                checks['recover_without_restarting_ui']=actor.is_alive() and len(calls)>=3
                close(actor,stop)
                rows.clear();fail[0]=True;actor,stop,commands=start()
                wait_for(lambda:rows[-1].get('mt5_connection',{}).get('code')=='TIMEOUT' if rows else False)
                fail[0]=False;commands.put({'action':'reconnect_mt5'})
                wait_for(lambda:rows[-1].get('connected') is True)
                checks['timeout_recovery']=actor.is_alive();close(actor,stop)
                rows.clear();api.account.login=456;actor,stop,commands=start()
                wait_for(lambda:rows[-1].get('mt5_connection',{}).get('code')=='ACCOUNT_MISMATCH' if rows else False)
                checks['wrong_account_rejected']=not any(r.get('connected') for r in rows);close(actor,stop)
                checks['preferences_unchanged']=load_config(root/'akira_config.json')==baseline
                checks['no_broker_orders']=not api.sent
                checks['single_mt5_owner']=all(call[2] in {a.ident for a,_ in actors} for call in calls) and all(not a.is_alive() for a,_ in actors)
        finally:
            for actor,stop in actors:close(actor,stop)
        if not all(checks.values()):raise RuntimeError('MT5 reconnect checks failed: '+str(checks))
    return {'status':'PASSED','build':BUILD_ID,'broker':'FakeMT5','engine':'production Engine and run_session',
            'native_mt5_library_version':native_library,'live_account_used':False,'native_mt5_login_tested':False,'checks':checks}


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path);args=parser.parse_args();result=run_check()
    if args.report:args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
