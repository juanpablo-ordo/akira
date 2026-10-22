"""Restart and reconnect contracts: synthetic MT5, no broker login or orders."""
import copy,json,queue,tempfile,threading,time,unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch

from settings import DEFAULT,load_config,save_config
from mt5_connection import MT5Connection,ConnectionProblem,CONNECT_TIMEOUT_MS
from execution import Reporter
from tests.fake_mt5 import Clock,FakeMT5


def wait_for(predicate,seconds=4):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if predicate():return True
        time.sleep(.01)
    return False


class Terminal(FakeMT5):
    def __init__(self,folder):
        self.clock=Clock();self.clock.now=time.time();super().__init__(self.clock)
        self.account.trade_mode=0
        self.program=Path(folder)/'MT5'/'terminal64.exe';self.program.parent.mkdir();self.program.write_bytes(b'test fixture; not executable')
        self.terminal.path=str(self.program.parent)
        self.calls=[];self.shutdowns=0;self.outcomes=[];self.on_initialize=None
    def initialize(self,*args,**kwargs):
        self.calls.append((args,kwargs,threading.get_ident()))
        if self.on_initialize:self.on_initialize()
        outcome=self.outcomes.pop(0) if self.outcomes else True
        if isinstance(outcome,Exception):raise outcome
        return outcome
    def last_error(self):return (-10005,'test initialization timeout')
    def shutdown(self):self.shutdowns+=1


class ConnectionTargetTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.api=Terminal(self.root);self.cfg=load_config(DEFAULT);self.cfg['mode']='observe';self.cfg['expected_login']=123
    def test_saved_account_is_passed_to_initialize_with_full_startup_timeout(self):
        MT5Connection(self.api,self.root).connect(self.cfg)
        args,options,_=self.api.calls[-1]
        self.assertEqual(args,());self.assertEqual(options,{'login':123,'timeout':60000});self.assertEqual(CONNECT_TIMEOUT_MS,60000)
    def test_reopening_reuses_only_the_verified_account_server_and_terminal(self):
        MT5Connection(self.api,self.root).connect(self.cfg)
        next_connection=MT5Connection(self.api,self.root);next_connection.connect(load_config(self.cfg))
        args,options,_=self.api.calls[-1]
        self.assertEqual(args,(str(self.api.program),));self.assertEqual(options['server'],'TEST');self.assertEqual(options['login'],123)
        saved=json.loads(next_connection.path.read_text(encoding='utf-8'))
        self.assertEqual(set(saved),{'terminal_path','login','server'});self.assertNotIn('password',saved)
    def test_reopening_keeps_mode_and_risk_while_connecting_the_demo(self):
        self.cfg['risk']['max_trade_money']=1.37;self.cfg['mode']='trade';save_config(self.cfg,self.root/'akira_config.json')
        before=load_config(self.root/'akira_config.json')
        for _ in range(2):MT5Connection(self.api,self.root).connect(load_config(self.root/'akira_config.json'))
        self.assertEqual(load_config(self.root/'akira_config.json'),before);self.assertEqual(self.api.account.trade_mode,0);self.assertFalse(self.api.sent)
    def test_missing_remembered_terminal_recovers_autodetection(self):
        connection=MT5Connection(self.api,self.root);connection.saved={'terminal_path':str(self.root/'removed.exe'),'login':123,'server':'OLD'}
        connection.connect(self.cfg);args,options,_=self.api.calls[-1]
        self.assertEqual(args,());self.assertNotIn('server',options)
    def test_explicit_directory_or_quoted_program_is_accepted(self):
        for value in (str(self.api.program.parent),'"'+str(self.api.program)+'"'):
            self.cfg['terminal_path']=value;MT5Connection(self.api,self.root).connect(self.cfg)
            self.assertEqual(self.api.calls[-1][0],(str(self.api.program),))
    def test_invalid_explicit_path_does_not_silently_open_another_terminal(self):
        self.cfg['terminal_path']=str(self.root/'wrong.exe')
        with self.assertRaisesRegex(ConnectionProblem,'No se encuentra'):MT5Connection(self.api,self.root).connect(self.cfg)
        self.assertFalse(self.api.calls)
    def test_server_of_another_account_or_terminal_is_never_reused(self):
        connection=MT5Connection(self.api,self.root)
        for saved in ({'login':456,'server':'WRONG','terminal_path':str(self.api.program)},
                      {'login':123,'server':'WRONG','terminal_path':str(self.root/'missing.exe')}):
            connection.saved=saved;connection.connect(self.cfg);self.assertNotIn('server',self.api.calls[-1][1])
    def test_wrong_account_cannot_create_a_binding_or_enter_the_engine(self):
        self.api.account.login=456
        with self.assertRaises(ConnectionProblem) as caught:MT5Connection(self.api,self.root).connect(self.cfg)
        self.assertEqual(caught.exception.code,'ACCOUNT_MISMATCH');self.assertFalse((self.root/'state/mt5_connection.json').exists());self.assertFalse(self.api.sent)
    def test_cached_account_does_not_make_a_disconnected_terminal_healthy(self):
        self.api.terminal.connected=False
        with self.assertRaises(ConnectionProblem) as caught:MT5Connection(self.api,self.root).connect(self.cfg)
        self.assertEqual(caught.exception.code,'BROKER_OFFLINE')
    def test_missing_account_and_initialize_failure_have_actionable_states(self):
        connection=MT5Connection(self.api,self.root);self.api.outcomes=[False]
        with self.assertRaises(ConnectionProblem) as caught:connection.connect(self.cfg)
        self.assertEqual(caught.exception.code,'TIMEOUT');self.assertIn('automáticamente',caught.exception.action)
        self.api.account=None
        with self.assertRaises(ConnectionProblem) as caught:connection.connect(self.cfg)
        self.assertEqual(caught.exception.code,'NO_ACCOUNT')
    def test_a_readonly_state_folder_does_not_break_the_connection(self):
        with patch.object(Path,'mkdir',side_effect=PermissionError('fixture')):
            account=MT5Connection(self.api,self.root).connect(self.cfg)
        self.assertEqual(account.login,123)


class SessionReconnectTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.api=Terminal(self.root);self.cfg=load_config(DEFAULT);self.cfg['mode']='observe';self.cfg['expected_login']=123;self.cfg['poll_seconds']=.05
        self.stop=threading.Event();self.commands=queue.Queue();self.rows=[];self.engines=[];self.locks=[]
        self.log=Reporter(self.root/'logs',console=False);self.on_step=None
    def engine(self,g,cfg,log,context):
        parent=self
        class TestEngine:
            paused=False
            def __init__(self):self.g=g;self.cfg=cfg;self.closed=False;self.steps=0
            def handle_command(self,cmd):
                if cmd['action']=='apply_settings':self.cfg.update(load_config(cmd['config']));return {'ok':True}
                if cmd['action']=='pause':self.paused=cmd['paused'];return {'ok':True}
                return {'ok':True}
            def step(self):
                self.steps+=1
                if parent.on_step:parent.on_step(self)
                return {'connected':True,'mode':self.cfg['mode'],'paused':self.paused,'account':{'login':g.api.account.login},'orders':[],'positions':[]}
            def close(self):self.closed=True
        result=TestEngine();self.engines.append(result);return result
    def start(self):
        import runtime
        for context in (patch('runtime._mt5_api',return_value=self.api),patch('runtime.Engine',side_effect=self.engine),patch('runtime.ContextWorker'),patch('runtime.retire'),patch('runtime.AccountLock',side_effect=self.new_lock)):
            context.start();self.addCleanup(context.stop)
        self.thread=threading.Thread(target=runtime.run_session,args=(self.cfg,self.root,self.log,self.stop,self.commands,self.rows.append),daemon=True)
        self.thread.start();self.addCleanup(self.finish)
    def new_lock(self,account):
        result=Mock();self.locks.append(result);return result
    def finish(self):
        self.stop.set();self.thread.join(4);self.assertFalse(self.thread.is_alive())
    def test_initialize_exception_is_recoverable_and_reconnect_wakes_backoff(self):
        self.api.outcomes=[RuntimeError('temporary IPC failure'),True];self.start()
        self.assertTrue(wait_for(lambda:any(r.get('mt5_connection',{}).get('code')=='INITIALIZE' for r in self.rows)),self.rows)
        self.commands.put({'action':'reconnect_mt5'})
        self.assertTrue(wait_for(lambda:any(r.get('connected') for r in self.rows)),self.rows)
        self.assertTrue(self.thread.is_alive());self.assertFalse(self.api.sent)
        self.assertEqual({r[2] for r in self.api.calls},{self.thread.ident})
    def test_offline_settings_are_consumed_before_the_next_initialization(self):
        self.cfg['terminal_path']=str(self.root/'missing.exe');self.start()
        self.assertTrue(wait_for(lambda:bool(self.rows)))
        changed=copy.deepcopy(self.cfg);changed['terminal_path']=str(self.api.program);changed['risk']['max_trade_money']=1.23
        self.commands.put({'action':'apply_settings','config':changed,'changed_paths':['terminal_path','risk.max_trade_money']})
        self.assertTrue(wait_for(lambda:any(r.get('connected') for r in self.rows)),self.rows)
        self.assertEqual(self.api.calls[-1][0],(str(self.api.program),));self.assertEqual(self.engines[-1].cfg['risk']['max_trade_money'],1.23)
    def test_save_during_initialize_is_checked_before_any_engine_cycle(self):
        replacement=copy.deepcopy(self.cfg);replacement['terminal_path']=str(self.api.program)
        def during():
            self.api.on_initialize=None
            self.commands.put({'action':'apply_settings','config':replacement,'changed_paths':['terminal_path']})
        self.api.on_initialize=during;self.start()
        self.assertTrue(wait_for(lambda:any(r.get('connected') for r in self.rows)),self.rows)
        self.assertEqual(len(self.engines),1);self.assertEqual(len(self.api.calls),2);self.assertEqual(self.api.calls[-1][0],(str(self.api.program),))
    def test_disconnect_and_reconnect_preserve_manual_pause_and_release_the_old_lock(self):
        self.cfg['mode']='trade';self.start();self.assertTrue(wait_for(lambda:bool(self.engines)))
        self.commands.put({'action':'pause','paused':True});self.assertTrue(wait_for(lambda:self.engines[0].paused))
        self.commands.put({'action':'reconnect_mt5'});self.assertTrue(wait_for(lambda:len(self.engines)==2))
        self.assertTrue(self.engines[0].closed);self.assertTrue(self.engines[1].paused);self.assertTrue(self.locks[0].close.called)
        self.assertEqual(self.cfg['mode'],'trade');self.assertFalse(self.api.sent)
    def test_broker_disconnect_is_not_published_as_a_healthy_account(self):
        self.api.terminal.connected=False;self.start()
        self.assertTrue(wait_for(lambda:any(r.get('mt5_connection',{}).get('code')=='BROKER_OFFLINE' for r in self.rows)))
        self.assertFalse(self.engines);self.assertFalse(any(r.get('connected') for r in self.rows))
        self.api.terminal.connected=True;self.commands.put({'action':'reconnect_mt5'})
        self.assertTrue(wait_for(lambda:any(r.get('connected') for r in self.rows)))
    def test_wrong_account_stays_blocked_without_constructing_an_engine(self):
        self.api.account.login=456;self.start()
        self.assertTrue(wait_for(lambda:any(r.get('mt5_connection',{}).get('code')=='ACCOUNT_MISMATCH' for r in self.rows)))
        self.assertFalse(self.engines);self.assertFalse(self.api.sent)
        self.api.account.login=123;self.commands.put({'action':'reconnect_mt5'})
        self.assertTrue(wait_for(lambda:any(r.get('connected') for r in self.rows)))
    def test_live_terminal_account_change_cannot_rebind_the_session(self):
        self.cfg['expected_login']=0;self.start();self.assertTrue(wait_for(lambda:any(r.get('connected') for r in self.rows)))
        self.api.account.login=456;self.commands.put({'action':'reconnect_mt5'})
        self.assertTrue(wait_for(lambda:any(r.get('mt5_connection',{}).get('code')=='ACCOUNT_CHANGED' for r in self.rows)))
        self.assertEqual(len(self.engines),1);self.assertTrue(self.engines[0].closed);self.assertFalse(self.api.sent)
    def test_explicit_new_target_in_observe_can_reconnect_without_old_account_journal(self):
        self.start();self.assertTrue(wait_for(lambda:any(r.get('connected') for r in self.rows)))
        changed=copy.deepcopy(self.cfg);changed['expected_login']=456;self.api.account.login=456
        self.commands.put({'action':'apply_settings','config':changed,'changed_paths':['expected_login']})
        self.assertTrue(wait_for(lambda:len(self.engines)==2 and self.rows[-1].get('connected')))
        self.assertTrue(self.engines[0].closed);self.assertEqual(self.engines[1].cfg['mode'],'observe');self.assertEqual(self.rows[-1]['account']['login'],456);self.assertFalse(self.api.sent)
    def test_offline_order_requests_are_rejected_instead_of_replayed(self):
        self.api.outcomes=[False];box={};self.commands.put({'action':'assistant_plan','symbol':'BTCUSDm','_reply':box});self.start()
        self.assertTrue(wait_for(lambda:bool(box)));self.assertFalse(box['result']['ok']);self.assertIn('no se conservan',box['result']['error']);self.assertFalse(self.api.sent)
    def test_runtime_stops_and_reopens_with_the_saved_demo_target(self):
        save_config(self.cfg,self.root/'akira_config.json');self.start()
        self.assertTrue(wait_for(lambda:any(r.get('connected') for r in self.rows)));
        self.finish();self.cfg=load_config(self.root/'akira_config.json');self.stop=threading.Event();self.rows=[]
        import runtime
        self.thread=threading.Thread(target=runtime.run_session,args=(self.cfg,self.root,self.log,self.stop,self.commands,self.rows.append),daemon=True);self.thread.start()
        self.assertTrue(wait_for(lambda:any(r.get('connected') for r in self.rows)),self.rows)
        self.assertEqual(self.api.calls[-1][0],(str(self.api.program),));self.assertEqual(self.api.calls[-1][1]['login'],123);self.assertEqual(self.cfg['mode'],'observe');self.assertFalse(self.api.sent)

    def test_production_engine_reads_both_assets_again_after_demo_reopen(self):
        from qa_mt5_reconnect_rev12 import run_check
        result=run_check()
        self.assertEqual(result['status'],'PASSED');self.assertTrue(result['checks']['fresh_account_and_both_assets'])
        self.assertFalse(result['live_account_used']);self.assertFalse(result['native_mt5_login_tested'])


class ControllerAndWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])
    def test_saving_while_disconnected_updates_the_actor_and_survives_reopening(self):
        from studio_controller import StudioController
        with tempfile.TemporaryDirectory() as tmp:
            controller=StudioController(tmp,start_actor=False)
            try:
                controller.actor=Mock();controller.actor.is_alive.return_value=True
                draft=copy.deepcopy(controller.cfg);draft['terminal_path']='fixture-terminal64.exe';draft['expected_login']=123
                self.assertTrue(controller.save(draft));self.assertTrue(wait_for(lambda:not controller._jobs))
                command=controller.commands.get_nowait();self.assertEqual(command['action'],'apply_settings');self.assertEqual(command['config']['expected_login'],123)
            finally:controller.close()
            reopened=StudioController(tmp,start_actor=False)
            try:self.assertEqual(reopened.cfg['expected_login'],123);self.assertEqual(reopened.cfg['terminal_path'],'fixture-terminal64.exe');self.assertEqual(reopened.cfg['mode'],'observe')
            finally:reopened.close()
    def test_start_actor_uses_settings_saved_before_services_started(self):
        from studio_controller import StudioController
        with tempfile.TemporaryDirectory() as tmp:
            controller=StudioController(tmp,start_actor=False)
            try:
                controller.cfg['expected_login']=123
                with patch('studio_controller.threading.Thread') as thread:
                    controller._start_actor()
                self.assertEqual(thread.call_args.kwargs['args'][0]['expected_login'],123)
            finally:controller.close()
    def test_correcting_a_disconnected_trade_account_saves_it_without_reusing_authorization(self):
        from studio_controller import StudioController
        with tempfile.TemporaryDirectory() as tmp:
            cfg=load_config(DEFAULT);cfg['mode']='trade';cfg['expected_login']=123;save_config(cfg,Path(tmp)/'akira_config.json')
            controller=StudioController(tmp,start_actor=False)
            try:
                draft=copy.deepcopy(controller.cfg);draft['expected_login']=456
                self.assertTrue(controller.save(draft));self.assertTrue(wait_for(lambda:not controller._jobs))
                saved=load_config(Path(tmp)/'akira_config.json');self.assertEqual(saved['expected_login'],456);self.assertEqual(saved['mode'],'observe');self.assertEqual(saved['risk'],cfg['risk'])
                result=next(r['data'] for r in controller.poll() if r['kind']=='settings_saved')
                self.assertTrue(result['result']['account_confirmation_required'])
            finally:controller.close()
    def test_reconnect_button_queues_control_without_requesting_an_order(self):
        from studio_controller import StudioController
        with tempfile.TemporaryDirectory() as tmp:
            controller=StudioController(tmp,start_actor=False)
            try:
                controller.actor=Mock();controller.actor.is_alive.return_value=True;controller._services_started=True
                self.assertTrue(controller.reconnect_mt5());self.assertEqual(controller.commands.get_nowait(),{'action':'reconnect_mt5'})
            finally:controller.close()
    def test_an_old_form_cannot_transfer_trading_authorization_to_another_target(self):
        from studio_controller import StudioController
        with tempfile.TemporaryDirectory() as tmp:
            cfg=load_config(DEFAULT);cfg['mode']='trade';cfg['expected_login']=123;save_config(cfg,Path(tmp)/'akira_config.json')
            controller=StudioController(tmp,start_actor=False)
            try:
                draft=copy.deepcopy(controller.cfg);draft.dirty_paths.add('mode')
                controller.cfg['mode']='observe';controller.cfg['expected_login']=456;save_config(controller.cfg,Path(tmp)/'akira_config.json')
                self.assertTrue(controller.save(draft));self.assertTrue(wait_for(lambda:not controller._jobs))
                saved=load_config(Path(tmp)/'akira_config.json');self.assertEqual(saved['mode'],'observe');self.assertEqual(saved['expected_login'],456)
                self.assertTrue(any(r['kind']=='error' and 'cuenta' in r['data'] for r in controller.poll()))
            finally:controller.close()
    def test_disconnected_trade_mode_does_not_claim_operational_authorization(self):
        from desktop_qt import StudioWindow
        with tempfile.TemporaryDirectory() as tmp:
            window=StudioWindow(tmp,preview=False,start_actor=False)
            try:
                window.render({'connected':False,'mode':'trade','mt5_connection':{'code':'NO_ACCOUNT','message':'MT5 no confirma una cuenta.','next_action':'Inicia sesión en MT5.'}})
                self.assertIn('Sin conexión',window.mode_label.text());self.assertNotIn('AUTORIZADA',window.mode_label.text());self.assertFalse(window.mt5_banner.isHidden());self.assertTrue(window.mt5_retry.isEnabled());self.assertFalse(window.mode_button.isEnabled())
                self.assertIn('Inicia sesión',window.settings_panel.mt5_status.text());self.assertIn('Inicia sesión',window.mt5_detail.text())
                window.render({'connected':True,'mode':'observe','mt5_connection':{'code':'CONNECTED','account_type':'demo'}})
                self.assertTrue(window.mt5_banner.isHidden());self.assertIn('demo',window.settings_panel.mt5_status.text())
            finally:window.close();self.app.processEvents()


if __name__=='__main__':unittest.main()
