"""Switch accounts through the real actor/controller; never use a broker."""
import copy,json,queue,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from settings import DEFAULT,load_config,save_config
from mt5_connection import MT5Connection,ConnectionProblem,target_signature,confirmation_matches
from tests.test_studio_rev12_mt5_reconnect import Terminal,wait_for


class AccountSwitchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.api=Terminal(self.root);self.cfg=load_config(DEFAULT);self.cfg.update(expected_login=123,expected_server='TEST',mode='observe')
    def test_cached_server_cannot_switch_the_selected_terminal_back(self):
        connection=MT5Connection(self.api,self.root);connection.connect(self.cfg)
        self.api.account.server='OTHER-DEMO';self.cfg['expected_server']='OTHER-DEMO'
        original=self.api.initialize
        def native_behavior(*args,**kwargs):
            if 'server' in kwargs:self.api.account.server=kwargs['server']
            if 'login' in kwargs:self.api.account.login=kwargs['login']
            return original(*args,**kwargs)
        self.api.initialize=native_behavior
        self.assertEqual(connection.connect(self.cfg).server,'OTHER-DEMO')
        self.assertNotIn('login',self.api.calls[-1][1]);self.assertNotIn('server',self.api.calls[-1][1]);self.assertFalse(self.api.sent)
    def test_same_number_on_another_server_is_a_different_target(self):
        changed=copy.deepcopy(self.cfg);changed['expected_server']='OTHER-DEMO'
        self.assertNotEqual(target_signature(self.cfg),target_signature(changed))
        self.api.account.server='OTHER-DEMO'
        with self.assertRaises(ConnectionProblem) as error:MT5Connection(self.api,self.root).connect(self.cfg)
        self.assertEqual(error.exception.code,'SERVER_MISMATCH')
    def test_inspection_returns_current_account_without_overwriting_saved_binding(self):
        connection=MT5Connection(self.api,self.root);connection.connect(self.cfg);before=connection.path.read_bytes()
        self.api.account.login=456;self.api.account.server='OTHER-DEMO'
        result=connection.connect(self.cfg,verify_target=False,prefer_open=True)
        self.assertEqual((result.login,result.server),(456,'OTHER-DEMO'));self.assertEqual(connection.observed['login'],456)
        self.assertEqual(connection.path.read_bytes(),before);self.assertFalse(self.api.sent)
    def test_a_single_running_terminal_wins_over_an_old_remembered_program(self):
        connection=MT5Connection(self.api,self.root);connection.connect(self.cfg)
        other=self.root/'other'/'terminal64.exe';other.parent.mkdir();other.write_bytes(b'fixture')
        self.api.terminal.path=str(other.parent)
        with patch('mt5_connection.running_terminals',return_value=[str(other)]):connection.connect(self.cfg)
        self.assertEqual(self.api.calls[-1][0],(str(other),))
    def test_multiple_open_terminals_require_an_explicit_choice_during_inspection(self):
        other=self.root/'other.exe';other.write_bytes(b'fixture')
        with patch('mt5_connection.running_terminals',return_value=[str(self.api.program),str(other)]):
            with self.assertRaises(ConnectionProblem) as error:MT5Connection(self.api,self.root).connect(self.cfg,verify_target=False,prefer_open=True)
        self.assertEqual(error.exception.code,'MULTIPLE_TERMINALS');self.assertFalse(self.api.calls)
    def test_explicit_terminal_is_respected_even_when_another_one_is_running(self):
        self.cfg['terminal_path']=str(self.api.program)
        with patch('mt5_connection.running_terminals',return_value=['other.exe']):MT5Connection(self.api,self.root).connect(self.cfg)
        self.assertEqual(self.api.calls[-1][0],(str(self.api.program),))
    def test_legacy_trading_binding_checks_the_saved_server_without_forcing_it(self):
        connection=MT5Connection(self.api,self.root);connection.connect(self.cfg)
        self.cfg.update(mode='trade',expected_server='');self.api.account.server='OTHER-DEMO'
        with self.assertRaises(ConnectionProblem) as error:connection.connect(self.cfg)
        self.assertEqual(error.exception.code,'SERVER_MISMATCH');self.assertEqual(self.api.account.server,'OTHER-DEMO')
    def test_confirmation_is_bound_to_the_number_and_server(self):
        self.assertTrue(confirmation_matches((123,'TEST'),self.api.account))
        for wrong in (123,(123,'OTHER-DEMO'),(456,'TEST'),None):
            self.assertFalse(confirmation_matches(wrong,self.api.account))
    def test_server_preferences_survive_reload_and_normalize_outer_whitespace(self):
        self.cfg['expected_server']=' TEST ';save_config(self.cfg,self.root/'akira_config.json')
        self.assertEqual(load_config(self.root/'akira_config.json')['expected_server'],'TEST')
    def test_production_controller_and_engine_can_adopt_and_restart_two_accounts(self):
        from qa_mt5_accounts_rev13 import run_check
        result=run_check()
        self.assertEqual(result['status'],'PASSED');self.assertTrue(all(result['checks'].values()))
        self.assertFalse(result['live_account_used']);self.assertFalse(result['native_mt5_login_tested'])


class ControllerIdentityTests(unittest.TestCase):
    def controller(self,folder,mode='trade',server='TEST'):
        from studio_controller import StudioController
        cfg=load_config(DEFAULT);cfg.update(mode=mode,expected_login=123,expected_server=server);save_config(cfg,Path(folder)/'akira_config.json')
        result=StudioController(folder,start_actor=False);self.addCleanup(result.close);return result
    def test_changing_only_server_revokes_previous_authorization(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=self.controller(tmp);draft=copy.deepcopy(c.cfg);draft['expected_server']='OTHER-DEMO'
            self.assertTrue(c.save(draft));self.assertTrue(wait_for(lambda:not c._jobs))
            self.assertEqual(c.cfg['mode'],'observe');self.assertEqual(c.cfg['expected_server'],'OTHER-DEMO')
            self.assertEqual(c.cfg['risk'],draft['risk'])
    def test_changing_only_terminal_revokes_previous_authorization(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=self.controller(tmp);draft=copy.deepcopy(c.cfg);draft['terminal_path']='other-terminal64.exe'
            self.assertTrue(c.save(draft));self.assertTrue(wait_for(lambda:not c._jobs));self.assertEqual(c.cfg['mode'],'observe')
    def test_authorization_records_the_current_server(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=self.controller(tmp,mode='observe',server='');c.bridge.connected=True;c.view={'account':{'login':123,'server':'TEST'}}
            c.bridge.request=Mock(return_value={'ok':True,'settings_applied':True})
            draft=copy.deepcopy(c.cfg);draft['mode']='trade'
            self.assertTrue(c.save(draft,confirmed_account=(123,'TEST')));self.assertTrue(wait_for(lambda:not c._jobs))
            self.assertEqual(c.cfg['mode'],'trade');self.assertEqual(c.cfg['expected_server'],'TEST')
            self.assertEqual(c.bridge.request.call_args.args[0]['authorized_identity'],(123,'TEST'))
    def test_number_only_confirmation_cannot_authorize_a_different_server(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=self.controller(tmp,mode='observe');c.bridge.connected=True;c.view={'account':{'login':123,'server':'TEST'}}
            draft=copy.deepcopy(c.cfg);draft['mode']='trade'
            with self.assertRaisesRegex(ValueError,'servidor'):c.save(draft,confirmed_account=123)
    def test_account_changes_between_confirmation_and_persistence_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=self.controller(tmp,mode='observe');c.bridge.connected=True;c.view={'account':{'login':123,'server':'TEST'}}
            queued=[]
            def collect(name,function,event=None,executor=None):queued.append(function);return True
            with patch.object(c,'job',side_effect=collect):
                draft=copy.deepcopy(c.cfg);draft['mode']='trade';c.save(draft,confirmed_account=(123,'TEST'))
            c.view['account']['server']='OTHER-DEMO'
            with self.assertRaisesRegex(ValueError,'cuenta cambió'):queued.pop()()
            self.assertEqual(load_config(Path(tmp)/'akira_config.json')['mode'],'observe')
    def test_failed_inspection_preserves_identity_and_persists_observe_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=self.controller(tmp);c._services_started=True;c.actor=Mock();c.actor.is_alive.return_value=True
            c.bridge.request=Mock(return_value={'ok':False,'error':'MT5 no confirma una cuenta'})
            self.assertTrue(c.use_open_mt5_account());self.assertTrue(wait_for(lambda:not c._jobs))
            saved=load_config(Path(tmp)/'akira_config.json');self.assertEqual(saved['mode'],'observe')
            self.assertEqual((saved['expected_login'],saved['expected_server']),(123,'TEST'))
    def test_preview_cannot_inspect_a_real_account(self):
        from studio_controller import StudioController
        with tempfile.TemporaryDirectory() as tmp:
            c=StudioController(tmp,preview=True,start_actor=False)
            try:self.assertFalse(c.use_open_mt5_account());self.assertTrue(c.commands.empty())
            finally:c.close()


class AccountSwitchWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])
    def test_account_adoption_updates_connection_fields_without_losing_other_edits(self):
        from desktop_qt import StudioWindow
        with tempfile.TemporaryDirectory() as tmp:
            window=StudioWindow(tmp,preview=False,start_actor=False)
            try:
                panel=window.settings_panel;panel.fields['expected_server'][0].setText('TYPED-OLD')
                panel.fields['risk.max_trade_money'][0].setValue(2.73)
                saved=copy.deepcopy(window.controller.cfg);saved.update(mode='observe',expected_login=456,expected_server='OTHER-DEMO',terminal_path='other.exe')
                panel.saved({'config':saved,'submitted':saved,'adopted_mt5_account':True})
                self.assertEqual(panel.fields['expected_server'][1](),'OTHER-DEMO');self.assertEqual(panel.fields['expected_login'][1](),456)
                self.assertEqual(panel.fields['risk.max_trade_money'][1](),2.73)
                self.assertTrue(panel.use_mt5_button.isEnabled())
            finally:window.close();self.app.processEvents()
    def test_the_use_open_account_button_passes_the_chosen_terminal(self):
        from desktop_qt import StudioWindow
        with tempfile.TemporaryDirectory() as tmp:
            window=StudioWindow(tmp,preview=False,start_actor=False)
            try:
                panel=window.settings_panel;panel.fields['terminal_path'][0].setText('chosen.exe')
                with patch.object(window.controller,'use_open_mt5_account',return_value=True) as detect:
                    panel.use_open_account();detect.assert_called_once_with('chosen.exe')
                self.assertFalse(panel.use_mt5_button.isEnabled());self.assertIn('Comprobando',panel.mt5_status.text())
            finally:window.close();self.app.processEvents()


class InspectionShutdownTests(unittest.TestCase):
    def test_close_cancels_a_queued_inspection_before_the_actor_can_start_it(self):
        from command_bridge import CommandBridge,dispatch
        commands=queue.Queue();bridge=CommandBridge(commands);stop=threading.Event();results=[]
        worker=threading.Thread(target=lambda:results.append(bridge.request({'action':'inspect_mt5'},cancel_event=stop)))
        worker.start();command=commands.get(timeout=1);stop.set();worker.join(1)
        self.assertFalse(worker.is_alive());self.assertTrue(results[0]['cancelled'])
        handler=Mock();dispatch(None,command,handler);handler.assert_not_called()
    def test_close_cancels_the_wait_for_an_inspection_already_started(self):
        from command_bridge import CommandBridge
        commands=queue.Queue();bridge=CommandBridge(commands);stop=threading.Event();results=[]
        worker=threading.Thread(target=lambda:results.append(bridge.request({'action':'inspect_mt5'},cancel_event=stop)))
        worker.start();command=commands.get(timeout=1)
        with command['_lock']:command['_started']=True
        stop.set();worker.join(1)
        self.assertFalse(worker.is_alive());self.assertTrue(results[0]['cancelled'])


if __name__=='__main__':unittest.main()
